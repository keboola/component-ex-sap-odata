from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from keboola.component.exceptions import UserException

from .async_base_client import AsyncODataClientBase, JsonDict
from .metadata import ODataVersion


class AsyncODataV4Client(AsyncODataClientBase):
    def _get_odata_version(self) -> ODataVersion:
        return ODataVersion.V4

    def _build_query_params(
        self,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        top: int | None = None,
        skip: int | None = None,
        count: bool = False,
    ) -> dict[str, str]:
        params = {}

        if select:
            params["$select"] = ",".join(select)
        if filter_expr:
            params["$filter"] = filter_expr
        if expand:
            params["$expand"] = ",".join(expand)
        if order_by:
            params["$orderby"] = order_by
        if top is not None:
            params["$top"] = str(top)
        if skip is not None:
            params["$skip"] = str(skip)
        if count:
            params["$count"] = "true"

        return params

    async def fetch_entity_set(  # type: ignore[override]
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        top: int | None = None,
        skip: int | None = None,
    ) -> AsyncIterator[JsonDict]:
        params = self._build_query_params(
            select=select,
            filter_expr=filter_expr,
            expand=expand,
            order_by=order_by,
            top=top,
            skip=skip,
        )

        data = await self._get_json(endpoint_path=entity_set, params=params)

        results = data.get("value", [])

        for record in results:
            yield self._clean_record(record)

    async def fetch_with_pagination(  # type: ignore[override]
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        page_size: int = 1000,
        max_records: int | None = None,
    ) -> AsyncIterator[JsonDict]:
        """Fetch entity set with automatic pagination.

        If enable_parallel is True and we can determine total count, fetches multiple
        pages in parallel for better performance.
        """
        if self.enable_parallel and max_records is None:
            # Try to get total count to enable parallel fetching
            total_count = await self.get_record_count(entity_set, filter_expr)
            if total_count and total_count > page_size:
                # Use parallel fetching with known count
                async for record in self._fetch_parallel_with_count(
                    entity_set=entity_set,
                    select=select,
                    filter_expr=filter_expr,
                    expand=expand,
                    order_by=order_by,
                    page_size=page_size,
                    total_count=total_count,
                ):
                    yield record
                return

        # Fall back to sequential pagination (with nextLink)
        async for record in self._fetch_sequential(
            entity_set=entity_set,
            select=select,
            filter_expr=filter_expr,
            expand=expand,
            order_by=order_by,
            page_size=page_size,
            max_records=max_records,
        ):
            yield record

    async def _fetch_sequential(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        page_size: int = 1000,
        max_records: int | None = None,
    ) -> AsyncIterator[JsonDict]:
        """Sequential pagination following @odata.nextLink."""
        endpoint_path = entity_set
        is_absolute = False
        params: dict[str, str] | None = self._build_query_params(
            select=select,
            filter_expr=filter_expr,
            expand=expand,
            order_by=order_by,
            top=page_size,
        )

        total_fetched = 0

        while endpoint_path:
            if max_records and total_fetched >= max_records:
                break

            data = await self._get_json(
                endpoint_path=endpoint_path,
                params=params if not is_absolute else None,
                is_absolute_path=is_absolute,
            )

            results = data.get("value", [])
            next_link = data.get("@odata.nextLink")

            for record in results:
                if max_records and total_fetched >= max_records:
                    break
                yield self._clean_record(record)
                total_fetched += 1

            if next_link:
                endpoint_path = next_link
                is_absolute = True
                params = None
                logging.debug(f"Following @odata.nextLink, fetched {total_fetched} records so far")
            else:
                break

        logging.info(f"Finished fetching {total_fetched} records from {entity_set}")

    async def _fetch_parallel_with_count(
        self,
        entity_set: str,
        total_count: int,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        page_size: int = 1000,
    ) -> AsyncIterator[JsonDict]:
        """Fetch pages in parallel when total count is known."""
        total_pages = (total_count + page_size - 1) // page_size
        logging.info(
            f"Parallel fetching enabled: {total_count} records in {total_pages} pages "
            f"(batch size: {self.parallel_pages})"
        )

        # Fetch pages in batches
        for batch_start in range(0, total_pages, self.parallel_pages):
            batch_end = min(batch_start + self.parallel_pages, total_pages)
            page_numbers = list(range(batch_start, batch_end))

            # Build jobs for parallel fetching
            jobs = []
            for page_num in page_numbers:
                skip_value = page_num * page_size
                params = self._build_query_params(
                    select=select,
                    filter_expr=filter_expr,
                    expand=expand,
                    order_by=order_by,
                    top=page_size,
                    skip=skip_value,
                )
                jobs.append({"method": "GET", "endpoint": entity_set, "params": params})

            # Fetch batch of pages in parallel
            logging.debug(f"Fetching pages {batch_start}-{batch_end-1} in parallel")
            responses = await self._client.process_multiple(jobs)

            # Yield records from all responses in order
            for page_num, response in zip(page_numbers, responses):
                results = response.get("value", [])
                logging.debug(f"Page {page_num}: {len(results)} records")
                for record in results:
                    yield self._clean_record(record)

        logging.info(f"Finished parallel fetching {total_count} records from {entity_set}")

    async def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        """Get total record count for entity set.

        Returns None if count is not available (expected for some OData implementations)
        or on recoverable errors. Raises UserException for authentication/permission errors.
        """
        endpoint_path = f"{entity_set}/$count"
        params = {}
        if filter_expr:
            params["$filter"] = filter_expr

        try:
            response_text = await self._get_raw(endpoint_path=endpoint_path, params=params if params else None)
            return int(response_text.strip())
        except UserException as e:
            # Authentication or permission errors should propagate
            error_msg = str(e)
            if "Authentication failed" in error_msg or "Access forbidden" in error_msg:
                logging.error(f"Cannot get record count due to auth/permission error: {e}")
                raise
            # 404 or other errors - count endpoint may not be supported
            logging.info(f"Record count not available ($count not supported or failed): {e}")
            return None
        except ValueError as e:
            # Invalid response format
            logging.warning(f"Failed to parse record count response: {e}")
            return None
        except Exception as e:
            # Unexpected error - log but continue without count
            logging.warning(f"Unexpected error getting record count: {e}")
            return None

    def _clean_record(self, record: JsonDict, _depth: int = 0) -> JsonDict:
        """Clean OData record by removing OData metadata fields.

        Args:
            record: The record to clean
            _depth: Current recursion depth (internal use only)

        Returns:
            Cleaned record dictionary

        Raises:
            RecursionError: If depth exceeds maximum (prevents stack overflow)
        """
        MAX_DEPTH = 50  # Prevent stack overflow on deeply nested data

        if _depth > MAX_DEPTH:
            logging.warning(f"Maximum recursion depth ({MAX_DEPTH}) reached while cleaning record")
            return {}

        cleaned: JsonDict = {}
        for key, value in record.items():
            if key.startswith("@odata."):
                continue
            if isinstance(value, dict):
                if "@odata.navigationLink" in value:
                    continue
                cleaned[key] = self._clean_record(value, _depth + 1)
            elif isinstance(value, list):
                cleaned[key] = [
                    self._clean_record(item, _depth + 1) if isinstance(item, dict) else item for item in value
                ]
            else:
                cleaned[key] = value
        return cleaned

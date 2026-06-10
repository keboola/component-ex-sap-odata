from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from keboola.component.exceptions import UserException

from .async_base_client import MAX_PAGE_SIZE_PER_REQUEST, AsyncODataClientBase, JsonDict
from .metadata import ODataVersion


class AsyncODataV2Client(AsyncODataClientBase):
    def _get_odata_version(self) -> ODataVersion:
        return ODataVersion.V2

    def _build_query_params(
        self,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        top: int | None = None,
        skip: int | None = None,
        inline_count: bool = False,
    ) -> dict[str, str]:
        params = {"$format": "json"}

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
        if inline_count:
            params["$inlinecount"] = "allpages"

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

        results = data.get("d", {})
        if isinstance(results, dict):
            results = results.get("results", [])

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
        # Cap the per-request page size so a single response never materialises an
        # excessive number of wide rows in memory, regardless of the configured
        # page_size. Larger page sizes simply page through in capped requests. (CFTL-681)
        if page_size > MAX_PAGE_SIZE_PER_REQUEST:
            logging.info(
                f"Configured page size {page_size} exceeds the per-request limit; "
                f"fetching in {MAX_PAGE_SIZE_PER_REQUEST}-record requests to bound memory."
            )
            page_size = MAX_PAGE_SIZE_PER_REQUEST

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

        # Fall back to sequential pagination (with __next link)
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
        """Sequential pagination, server-driven (__next) with $skip fallback.

        SAP Gateway treats ``$top`` as a hard total cap and does NOT return a
        ``__next`` link when one is set, so relying on ``__next`` alone stops
        after the first page. When no next link is present but a full page came
        back, we advance the offset with ``$skip`` (client-driven paging) so the
        whole entity set is fetched. Only one page is held in memory at a time.
        """
        endpoint_path = entity_set
        is_absolute = False
        next_skip = page_size
        params: dict[str, str] | None = self._build_query_params(
            select=select,
            filter_expr=filter_expr,
            expand=expand,
            order_by=order_by,
            top=page_size,
        )

        total_fetched = 0
        max_pages = 100_000
        page_count = 0

        while endpoint_path:
            if page_count >= max_pages:
                logging.warning(f"Reached page safety limit ({max_pages}) for {entity_set}, stopping.")
                break
            page_count += 1
            if max_records and total_fetched >= max_records:
                break

            data = await self._get_json(
                endpoint_path=endpoint_path,
                params=params if not is_absolute else None,
                is_absolute_path=is_absolute,
            )

            results = data.get("d", {})
            next_link = None

            if isinstance(results, dict):
                next_link = results.get("__next")
                results = results.get("results", [])

            page_len = len(results)
            for record in results:
                if max_records and total_fetched >= max_records:
                    break
                yield self._clean_record(record)
                total_fetched += 1

            if next_link:
                # Server-driven paging: follow the canonical next link.
                endpoint_path = next_link
                is_absolute = True
                params = None
                logging.debug(f"Following __next link, fetched {total_fetched} records so far")
            elif page_len == page_size:
                # No next link but the page was exactly full — SAP capped on $top.
                # Using == (not >=) avoids infinite looping if a non-conformant server
                # ignores $top and returns more than page_size records. Advance the
                # offset manually (client-driven paging) to get the next page.
                params = self._build_query_params(
                    select=select,
                    filter_expr=filter_expr,
                    expand=expand,
                    order_by=order_by,
                    top=page_size,
                    skip=next_skip,
                )
                next_skip += page_size
                is_absolute = False
                endpoint_path = entity_set
                logging.debug(f"No __next link; advancing with $skip, fetched {total_fetched} records so far")
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
            logging.debug(f"Fetching pages {batch_start}-{batch_end - 1} in parallel")
            responses = await self._client.process_multiple(jobs)

            # Yield records from all responses in order
            for page_num, response in zip(page_numbers, responses, strict=True):
                results = response.get("d", {})
                if isinstance(results, dict):
                    results = results.get("results", [])
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
        params = {"$format": "json"}
        if filter_expr:
            params["$filter"] = filter_expr

        try:
            response = await self._probe_client.get_raw(endpoint=endpoint_path, params=params)
            response.raise_for_status()
            return int(response.text.strip())
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                logging.error(f"Cannot get record count due to auth error: {e}")
                raise UserException(f"Authentication failed: {e}") from e
            if "403" in error_msg:
                logging.error(f"Cannot get record count due to permission error: {e}")
                raise UserException(f"Access forbidden: {e}") from e
            # Any other error (404, 400, 500, parse error) — this service doesn't support
            # $count (common for SAP CDS query views). Not a problem: we fall back to
            # sequential pagination. Keep the raw error at debug level so it doesn't look
            # like a failure in the job log.
            logging.info(
                f"Total record count is unavailable for '{entity_set}' "
                f"(the service does not support $count); using sequential pagination."
            )
            logging.debug(f"$count probe error detail: {e}")
            return None

    def _clean_record(self, record: JsonDict, _depth: int = 0) -> JsonDict:
        max_depth = 50  # Prevent stack overflow on deeply nested data
        if _depth > max_depth:
            logging.warning(f"Maximum recursion depth ({max_depth}) reached while cleaning record")
            return {}
        cleaned: JsonDict = {}
        for key, value in record.items():
            if key.startswith("__"):
                continue
            if isinstance(value, dict):
                if "__deferred" in value:
                    continue
                if "results" in value:
                    cleaned[key] = value["results"]
                else:
                    cleaned[key] = self._clean_record(value, _depth + 1)
            else:
                cleaned[key] = value
        return cleaned

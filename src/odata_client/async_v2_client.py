from __future__ import annotations

import logging

from keboola.component.exceptions import UserException

from .async_base_client import AsyncODataClientBase, JsonDict
from .metadata import ODataVersion


class AsyncODataV2Client(AsyncODataClientBase):
    """OData V2 parsing hooks. The pagination state machine lives in the base."""

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

        return params

    def _extract_page(self, response: JsonDict) -> tuple[list[JsonDict], str | None]:
        """V2 wraps the page under ``d`` (or ``d.results``) with a ``__next`` link."""
        results = response.get("d", {})
        next_link: str | None = None
        if isinstance(results, dict):
            next_link = results.get("__next")
            results = results.get("results", [])
        return results, next_link

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
            # $count (common for SAP CDS query views). Not a problem: pagination still works
            # (parallel-speculative when parallel_pages > 1, sequential otherwise). Keep the
            # raw error at debug level so it doesn't look like a failure in the job log.
            logging.info(f"Total record count is unavailable for '{entity_set}' (the service does not support $count).")
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

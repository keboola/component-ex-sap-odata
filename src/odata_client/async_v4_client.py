from __future__ import annotations

import logging

from keboola.component.exceptions import UserException

from .async_base_client import AsyncODataClientBase, JsonDict
from .metadata import ODataVersion


class AsyncODataV4Client(AsyncODataClientBase):
    """OData V4 parsing hooks. The pagination state machine lives in the base."""

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
    ) -> dict[str, str]:
        params: dict[str, str] = {}

        if select:
            params["$select"] = ",".join(select)
        if filter_expr:
            params["$filter"] = filter_expr
        if expand:
            params["$expand"] = self._build_v4_expand(expand)
        if order_by:
            params["$orderby"] = order_by
        if top is not None:
            params["$top"] = str(top)
        if skip is not None:
            params["$skip"] = str(skip)

        return params

    def _extract_page(self, response: JsonDict) -> tuple[list[JsonDict], str | None]:
        """V4 returns the page under ``value`` with an ``@odata.nextLink``."""
        return response.get("value", []), response.get("@odata.nextLink")

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
            response = await self._probe_client.get_raw(endpoint=endpoint_path, params=params if params else None)
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

    @staticmethod
    def _build_v4_expand(expand: list[str]) -> str:
        """Convert a list of expand paths to OData V4 nested ``$expand`` syntax.

        OData V2 uses slash-separated paths directly (``Items,Items/Partner``),
        but OData V4 requires nested syntax: ``Items($expand=Partner)``.

        Paths that share a common root are merged into a single nested expression.
        For example ``["Items/Partner", "Items/Partner/Address", "Items/Schedule"]``
        becomes ``Items($expand=Partner($expand=Address),Schedule)``.

        Simple (single-level) paths are left as-is.
        """
        # Build a tree from all expand paths
        tree: dict = {}
        for path in expand:
            parts = path.split("/")
            node = tree
            for part in parts:
                if part not in node:
                    node[part] = {}
                node = node[part]

        def _render(subtree: dict) -> str:
            segments: list[str] = []
            for key, children in subtree.items():
                if children:
                    child_expand = _render(children)
                    segments.append(f"{key}($expand={child_expand})")
                else:
                    segments.append(key)
            return ",".join(segments)

        return _render(tree)

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
        max_depth = 50  # Prevent stack overflow on deeply nested data

        if _depth > max_depth:
            logging.warning(f"Maximum recursion depth ({max_depth}) reached while cleaning record")
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

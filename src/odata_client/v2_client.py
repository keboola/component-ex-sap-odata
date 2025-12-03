import logging
from collections.abc import Iterator
from typing import Any

from odata_client.base_client import ODataClientBase
from odata_client.metadata import ODataVersion


class ODataV2Client(ODataClientBase):
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

    def fetch_entity_set(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        top: int | None = None,
        skip: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        params = self._build_query_params(
            select=select,
            filter_expr=filter_expr,
            expand=expand,
            order_by=order_by,
            top=top,
            skip=skip,
        )

        data = self._get_json(endpoint_path=entity_set, params=params)

        results = data.get("d", {})
        if isinstance(results, dict):
            results = results.get("results", [])

        for record in results:
            yield self._clean_record(record)

    def fetch_with_pagination(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        page_size: int = 1000,
        max_records: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        endpoint_path = entity_set
        is_absolute = False
        params = self._build_query_params(
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

            data = self._get_json(
                endpoint_path=endpoint_path,
                params=params if not is_absolute else None,
                is_absolute_path=is_absolute,
            )

            results = data.get("d", {})
            next_link = None

            if isinstance(results, dict):
                next_link = results.get("__next")
                results = results.get("results", [])

            for record in results:
                if max_records and total_fetched >= max_records:
                    break
                yield self._clean_record(record)
                total_fetched += 1

            if next_link:
                endpoint_path = next_link
                is_absolute = True
                params = None
                logging.debug(f"Following __next link, fetched {total_fetched} records so far")
            else:
                break

        logging.info(f"Finished fetching {total_fetched} records from {entity_set}")

    def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        endpoint_path = f"{entity_set}/$count"
        params = {"$format": "json"}
        if filter_expr:
            params["$filter"] = filter_expr

        try:
            response_text = self._get_raw(endpoint_path=endpoint_path, params=params)
            return int(response_text.strip())
        except Exception as e:
            logging.warning(f"Failed to get record count: {e}")
            return None

    def _clean_record(self, record: dict[str, Any]) -> dict[str, Any]:
        cleaned = {}
        for key, value in record.items():
            if key.startswith("__"):
                continue
            if isinstance(value, dict):
                if "__deferred" in value:
                    continue
                if "results" in value:
                    cleaned[key] = value["results"]
                else:
                    cleaned[key] = self._clean_record(value)
            else:
                cleaned[key] = value
        return cleaned

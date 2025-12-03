import logging
from collections.abc import Iterator
from typing import Any

from odata_client.base_client import ODataClientBase
from odata_client.metadata import ODataVersion


class ODataV4Client(ODataClientBase):
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
        url = f"{self.base_url}/{entity_set}"
        params = self._build_query_params(
            select=select,
            filter_expr=filter_expr,
            expand=expand,
            order_by=order_by,
            top=top,
            skip=skip,
        )

        response = self._make_request("GET", url, params=params)
        data = response.json()

        results = data.get("value", [])

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
        url = f"{self.base_url}/{entity_set}"
        params = self._build_query_params(
            select=select,
            filter_expr=filter_expr,
            expand=expand,
            order_by=order_by,
            top=page_size,
        )

        total_fetched = 0

        while url:
            if max_records and total_fetched >= max_records:
                break

            response = self._make_request("GET", url, params=params if not url.startswith("http") else None)
            data = response.json()

            results = data.get("value", [])
            next_link = data.get("@odata.nextLink")

            for record in results:
                if max_records and total_fetched >= max_records:
                    break
                yield self._clean_record(record)
                total_fetched += 1

            if next_link:
                url = next_link
                params = None
                logging.debug(f"Following @odata.nextLink, fetched {total_fetched} records so far")
            else:
                break

        logging.info(f"Finished fetching {total_fetched} records from {entity_set}")

    def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        url = f"{self.base_url}/{entity_set}/$count"
        params = {}
        if filter_expr:
            params["$filter"] = filter_expr

        try:
            response = self._make_request("GET", url, params=params)
            return int(response.text.strip())
        except Exception as e:
            logging.warning(f"Failed to get record count: {e}")
            return None

    def _clean_record(self, record: dict[str, Any]) -> dict[str, Any]:
        cleaned = {}
        for key, value in record.items():
            if key.startswith("@odata."):
                continue
            if isinstance(value, dict):
                if "@odata.navigationLink" in value:
                    continue
                cleaned[key] = self._clean_record(value)
            elif isinstance(value, list):
                cleaned[key] = [self._clean_record(item) if isinstance(item, dict) else item for item in value]
            else:
                cleaned[key] = value
        return cleaned

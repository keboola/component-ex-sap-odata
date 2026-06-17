from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
from keboola.component.exceptions import UserException
from keboola.http_client import AsyncHttpClient

from .auth import ApiKeyAuthHandler, AuthHandler, BasicAuthHandler
from .catalog_parser import CatalogParser, ServiceInfo
from .metadata import EntityProperty, EntitySet, MetadataParser, ODataMetadata, ODataVersion

# Type alias for JSON-serializable data
JsonDict = dict[str, Any]


class AsyncODataClientBase(ABC):
    def __init__(
        self,
        base_url: str,
        auth_handler: AuthHandler,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
        parallel_pages: int = 1,
        max_requests_per_second: float | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_handler = auth_handler
        self.timeout = timeout
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl
        # Pages fetched concurrently; 1 = sequential, > 1 = parallel.
        self.parallel_pages = parallel_pages
        self._metadata: ODataMetadata | None = None
        self._metadata_lock = asyncio.Lock()
        self._client = AsyncHttpClient(
            base_url=self.base_url + "/",
            retries=max_retries,
            timeout=float(timeout),
            verify_ssl=verify_ssl,
            retry_status_codes=[500, 502, 503, 504],
            auth_header=auth_handler.get_auth_headers(),
            backoff_factor=0.3,
            max_requests_per_second=max_requests_per_second,
        )
        # No-retry client for optional probing requests (e.g. $count).
        # $count is used only to enable parallel fetching — retrying a failed
        # count wastes time on endpoints that never support it (e.g. SCI).
        self._probe_client = AsyncHttpClient(
            base_url=self.base_url + "/",
            retries=0,
            timeout=float(timeout),
            verify_ssl=verify_ssl,
            retry_status_codes=[],
            auth_header=auth_handler.get_auth_headers(),
        )
        # SAP OData services redirect to the canonical trailing-slash URL
        # (e.g. .../SERVICE -> .../SERVICE/) with a 307. httpx does not follow
        # redirects by default, which surfaces loadServices / loadEntities /
        # metadata fetches as a hard "307 Temporary Redirect" error even though
        # browsers and Postman handle it transparently. Follow redirects so the
        # canonical URL is reached automatically. (CFTL-681)
        self._client.client.follow_redirects = True
        self._probe_client.client.follow_redirects = True

    @classmethod
    def from_basic_auth(
        cls,
        username: str,
        password: str,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
        parallel_pages: int = 1,
        max_requests_per_second: float | None = None,
    ) -> AsyncODataClientBase:
        auth_handler = BasicAuthHandler(username, password)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            parallel_pages=parallel_pages,
            max_requests_per_second=max_requests_per_second,
        )

    @classmethod
    def from_api_key(
        cls,
        api_key: str,
        header_name: str,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
        parallel_pages: int = 1,
        max_requests_per_second: float | None = None,
    ) -> AsyncODataClientBase:
        auth_handler = ApiKeyAuthHandler(api_key, header_name)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            parallel_pages=parallel_pages,
            max_requests_per_second=max_requests_per_second,
        )

    async def __aenter__(self):
        await self._client.__aenter__()
        await self._probe_client.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._client.__aexit__(*args)
        await self._probe_client.__aexit__(*args)

    async def close(self):
        await self._client.close()
        await self._probe_client.close()

    async def _get_json(
        self,
        endpoint_path: str,
        params: dict[str, str] | None = None,
        is_absolute_path: bool = False,
    ) -> JsonDict:
        try:
            return cast(
                JsonDict,
                await self._client.get(
                    endpoint=endpoint_path,
                    params=params,
                    headers={"Accept": "application/json"},
                    is_absolute_path=is_absolute_path,
                ),
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 400:
                hint = ""
                body = e.response.text
                if "$filter" in body or "filter" in body.lower():
                    hint = (
                        "\n\nFilter syntax error detected. Common issues:\n"
                        "• Date fields (Edm.Date): Use YYYY-MM-DD without quotes (e.g., DocumentDate gt 2024-01-01)\n"
                        "• DateTime fields (Edm.DateTimeOffset): Use ISO format without quotes (e.g., CreatedAt gt 2024-01-01T00:00:00Z)\n"
                        "• String fields: Use single quotes (e.g., Status eq 'Active')\n"
                        "• OData V2: Use datetime'YYYY-MM-DDTHH:MM:SS' format for dates"
                    )
                raise UserException(f"Invalid request - check your filter/query syntax: {e}{hint}") from e
            if status == 401:
                raise UserException(f"Authentication failed: {e}") from e
            if status == 403:
                raise UserException(f"Access forbidden: {e}") from e
            if status == 404:
                raise UserException(f"Resource not found: {e}") from e
            if status == 429:
                raise UserException(f"Rate limit exceeded: {e}") from e
            raise UserException(f"HTTP {status} error: {e}") from e
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                raise UserException(f"Request timeout after {self.timeout}s: {e}") from e
            raise UserException(f"HTTP request failed: {e}") from e

    async def _get_raw(
        self,
        endpoint_path: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        is_absolute_path: bool = False,
    ) -> str:
        try:
            response = await self._client.get_raw(
                endpoint=endpoint_path,
                params=params,
                headers=headers,
                is_absolute_path=is_absolute_path,
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 401:
                raise UserException(f"Authentication failed: {e}") from e
            if status == 403:
                raise UserException(f"Access forbidden: {e}") from e
            if status == 404:
                raise UserException(f"Resource not found: {e}") from e
            raise UserException(f"HTTP {status} error: {e}") from e
        except httpx.TimeoutException as e:
            raise UserException(f"Request timeout after {self.timeout}s: {e}") from e
        except httpx.ConnectError as e:
            raise UserException(f"Connection failed: {e}") from e
        except Exception as e:
            raise UserException(f"Request failed: {e}") from e

    async def get_metadata(self, force_refresh: bool = False) -> ODataMetadata:
        """Get OData metadata with fallback to service document if $metadata is not available.

        This method attempts to retrieve metadata in the following order:
        1. Try $metadata endpoint (standard OData)
        2. If $metadata fails with 404, try to get entity sets from service document
        3. If both fail, return empty metadata

        Uses a lock to prevent multiple concurrent metadata fetches.

        Args:
            force_refresh: Force refresh of cached metadata

        Returns:
            ODataMetadata object (may be empty if both methods fail)
        """
        # Fast path: return cached metadata without locking
        if self._metadata is not None and not force_refresh:
            return self._metadata

        # Slow path: fetch metadata with lock
        async with self._metadata_lock:
            # Double-check after acquiring lock (another coroutine may have fetched it)
            if self._metadata is not None and not force_refresh:
                return self._metadata

            # Try standard $metadata endpoint first
            try:
                metadata_text = await self._get_raw(
                    endpoint_path="$metadata",
                    headers={"Accept": "application/xml"},
                )

                # Validate that we received XML content before parsing
                stripped = metadata_text.strip() if metadata_text else ""
                if not stripped:
                    raise UserException(
                        "Metadata endpoint returned an empty response. "
                        "The OData service may be unavailable or misconfigured."
                    )
                if not stripped.startswith("<"):
                    # Response is not XML — likely an error page, JSON, or the service is down
                    preview = stripped[:200]
                    raise UserException(
                        f"Metadata endpoint returned a non-XML response (the service may be unavailable). "
                        f"Response starts with: {preview}"
                    )

                self._metadata = MetadataParser.parse(metadata_text, self._get_odata_version())
                return self._metadata
            except UserException as e:
                # Check if it's a 404 (metadata not available)
                if "404" in str(e) or "not found" in str(e).lower():
                    logging.warning(f"$metadata endpoint not available: {e}")
                    logging.info("Attempting to get entity sets from service document")

                    # Try fallback: get entity sets from service document
                    fallback_metadata = await self._try_get_service_document_metadata()
                    if fallback_metadata and fallback_metadata.entity_sets:
                        self._metadata = fallback_metadata
                        logging.info(
                            f"Successfully extracted {len(fallback_metadata.entity_sets)} entity sets "
                            f"from service document"
                        )
                        return self._metadata

                    # If fallback also failed, return empty metadata but don't raise
                    logging.warning("Service document fallback also failed, returning empty metadata")
                    self._metadata = ODataMetadata(version=self._get_odata_version())
                    return self._metadata

                # For other errors (auth, network, non-XML response, etc.), raise
                raise
            except Exception as e:
                raise UserException(f"Failed to parse metadata: {e}") from e

    async def _try_get_service_document_metadata(self) -> ODataMetadata | None:
        """Try to get entity sets from service document (fallback when $metadata is not available).

        Returns:
            ODataMetadata with entity sets if successful, None otherwise
        """
        try:
            # Try to get service document (root of service)
            # Use absolute path to avoid trailing slash (SAP endpoints are sensitive to it)
            # _get_json already sets Accept: application/json header
            data = await self._get_json(endpoint_path=self.base_url, is_absolute_path=True)
            return CatalogParser.try_parse_from_response(data, self._get_odata_version())
        except Exception as e:
            logging.debug(f"Failed to get service document: {e}")
            return None

    async def list_entity_sets(self) -> list[EntitySet]:
        """List available entity sets.

        Returns:
            List of EntitySet objects (may be empty if metadata is not available)
        """
        metadata = await self.get_metadata()
        return metadata.list_entity_sets()

    async def list_fields(self, entity_set_name: str) -> list[EntityProperty]:
        """List fields for a specific entity set.

        Args:
            entity_set_name: Name of the entity set

        Returns:
            List of EntityProperty objects (may be empty if metadata is not available)

        Raises:
            UserException: If entity set is not found
        """
        metadata = await self.get_metadata()
        entity_set = metadata.get_entity_set(entity_set_name)
        if entity_set is None:
            # If metadata is empty (fallback scenario), return empty list instead of error
            if not metadata.entity_sets:
                logging.warning(
                    f"Cannot list fields for '{entity_set_name}' - metadata not available. "
                    f"Fields will be discovered from actual data."
                )
                return []
            raise UserException(f"Entity set '{entity_set_name}' not found")
        return entity_set.properties

    async def list_catalog_services(self, url: str | None = None) -> list[ServiceInfo]:
        """List available OData services from SAP Service Catalog.

        This method is specifically for SAP catalog endpoints that return a list
        of available OData services instead of entity sets.

        Args:
            url: Explicit catalog URL to fetch. If not provided, falls back to self.base_url.
                 Callers should always pass the catalog URL explicitly so the client's base_url
                 does not need to point at the catalog endpoint.

        Returns:
            List of ServiceInfo objects (empty if not a catalog endpoint)
        """
        target_url = url if url else self.base_url
        try:
            # Use absolute path to avoid trailing slash (SAP endpoints are sensitive to it)
            # SAP catalog endpoints typically return XML (application/atom+xml) by default
            logging.debug(f"list_catalog_services: fetching {target_url}")

            # Try to get XML response (SAP catalog returns ATOM/XML by default)
            xml_text = await self._get_raw(
                endpoint_path=target_url,
                headers={"Accept": "application/atom+xml, application/xml, */*"},
                is_absolute_path=True,
            )

            logging.debug(f"list_catalog_services: got response, length={len(xml_text)} from {target_url}")

            # Check if this is XML (starts with <)
            if xml_text.strip().startswith("<"):
                logging.debug("Response is XML, parsing as ATOM feed")
                services = CatalogParser.parse_sap_catalog_xml(xml_text)
                logging.info(f"list_catalog_services: parsed {len(services)} services from SAP catalog XML")
                return services

            # If not XML, try parsing as JSON
            logging.debug("Response is not XML, trying JSON")
            data = json.loads(xml_text)

            # Check if this is a SAP catalog response
            is_catalog = CatalogParser.is_sap_catalog(data)
            logging.debug(f"list_catalog_services: is_sap_catalog={is_catalog}")

            if is_catalog:
                services = CatalogParser.parse_sap_catalog(data)
                logging.info(f"list_catalog_services: parsed {len(services)} services from SAP catalog JSON")
                return services

            # Not a catalog, return empty list
            logging.debug("Response is not a SAP catalog format")
            return []
        except UserException:
            raise  # HTTP/auth errors must propagate to the caller so the UI sees them
        except Exception as e:
            logging.warning(f"Failed to parse catalog response: {e}")
            return []

    async def test_connection(self) -> tuple[bool, str]:
        try:
            metadata = await self.get_metadata(force_refresh=True)
            version = metadata.version.value.upper()
            return True, f"Connection successful. OData {version} service detected."
        except UserException as e:
            return False, str(e)
        except Exception as e:
            return False, f"Connection failed: {e}"

    # ------------------------------------------------------------------
    # Version-specific hooks (implemented by V2/V4 subclasses)
    # ------------------------------------------------------------------

    @abstractmethod
    def _get_odata_version(self) -> ODataVersion:
        pass

    @abstractmethod
    def _build_query_params(
        self,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        top: int | None = None,
        skip: int | None = None,
    ) -> dict[str, str]:
        """Build OData query parameters for the concrete protocol version."""
        ...

    @abstractmethod
    def _extract_page(self, response: JsonDict) -> tuple[list[JsonDict], str | None]:
        """Extract ``(records, next_link)`` from a raw OData response page.

        ``next_link`` is the server-driven paging continuation link
        (``__next`` in V2, ``@odata.nextLink`` in V4), or ``None`` when the
        response carries no next link.
        """
        ...

    @abstractmethod
    def _clean_record(self, record: JsonDict, _depth: int = 0) -> JsonDict:
        """Strip protocol metadata from a record (``__*`` in V2, ``@odata.*`` in V4)."""
        ...

    @abstractmethod
    async def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        pass

    # ------------------------------------------------------------------
    # Pagination state machine (shared by all OData versions)
    # ------------------------------------------------------------------

    async def fetch_entity_set(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        top: int | None = None,
        skip: int | None = None,
    ) -> AsyncIterator[JsonDict]:
        """Fetch a single page of an entity set (no automatic pagination)."""
        params = self._build_query_params(
            select=select,
            filter_expr=filter_expr,
            expand=expand,
            order_by=order_by,
            top=top,
            skip=skip,
        )
        data = await self._get_json(endpoint_path=entity_set, params=params)
        records, _ = self._extract_page(data)
        for record in records:
            yield self._clean_record(record)

    async def fetch_with_pagination(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        page_size: int = 1000,
        max_records: int | None = None,
    ) -> AsyncIterator[JsonDict]:
        """Fetch an entire entity set, paging automatically.

        With ``parallel_pages > 1`` and no record cap, pages are fetched
        concurrently — precisely when ``$count`` is available, speculatively
        otherwise (SAP CDS query views reject ``$count`` with 400). Every other
        case falls back to sequential server-driven paging. Only one batch of
        pages is held in memory at a time. (CFTL-681)
        """
        if self.parallel_pages > 1 and max_records is None:
            # Try to get total count to enable precise parallel fetching
            total_count = await self.get_record_count(entity_set, filter_expr)
            if total_count and total_count > page_size:
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
            if total_count is None:
                # Count unavailable (e.g. SAP CDS query views return 400 on $count).
                # Fetch pages speculatively in parallel instead of crawling
                # sequentially — far faster over high-latency links. (CFTL-681)
                async for record in self._fetch_parallel_speculative(
                    entity_set=entity_set,
                    select=select,
                    filter_expr=filter_expr,
                    expand=expand,
                    order_by=order_by,
                    page_size=page_size,
                ):
                    yield record
                return

        # Fall back to sequential pagination (server-driven next link + $skip)
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
        """Sequential server-driven paging with a client-driven ``$skip`` fallback.

        SAP Gateway treats ``$top`` as a hard total cap and does NOT return a
        next link when one is set, so relying on the next link alone stops after
        the first page. When no next link is present but a full page came back,
        the offset is advanced with ``$skip`` (client-driven paging) so the whole
        entity set is fetched. Only one page is held in memory at a time.
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

            results, next_link = self._extract_page(data)

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
                logging.debug(f"Following next link, fetched {total_fetched} records so far")
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
                logging.debug(f"No next link; advancing with $skip, fetched {total_fetched} records so far")
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
        """Fetch pages in parallel when the total count is known."""
        total_pages = (total_count + page_size - 1) // page_size
        logging.info(
            f"Parallel fetching enabled: {total_count} records in {total_pages} pages "
            f"(batch size: {self.parallel_pages})"
        )
        self._log_batch_peak(page_size)

        # Fetch pages in batches
        for batch_start in range(0, total_pages, self.parallel_pages):
            batch_end = min(batch_start + self.parallel_pages, total_pages)
            page_numbers = list(range(batch_start, batch_end))

            # Build jobs for parallel fetching
            jobs = []
            for page_num in page_numbers:
                params = self._build_query_params(
                    select=select,
                    filter_expr=filter_expr,
                    expand=expand,
                    order_by=order_by,
                    top=page_size,
                    skip=page_num * page_size,
                )
                jobs.append({"method": "GET", "endpoint": entity_set, "params": params})

            # Fetch batch of pages in parallel
            logging.debug(f"Fetching pages {batch_start}-{batch_end - 1} in parallel")
            responses = await self._client.process_multiple(jobs)

            # Yield records from all responses in order
            for page_num, response in zip(page_numbers, responses, strict=True):
                records, next_link = self._extract_page(response)
                self._guard_against_server_paging(entity_set, len(records), page_size, next_link)
                logging.debug(f"Page {page_num}: {len(records)} records")
                for record in records:
                    yield self._clean_record(record)

        logging.info(f"Finished parallel fetching {total_count} records from {entity_set}")

    async def _fetch_parallel_speculative(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        page_size: int = 1000,
    ) -> AsyncIterator[JsonDict]:
        """Fetch pages in parallel without a known total count.

        Fires ``parallel_pages`` requests concurrently at increasing ``$skip``
        offsets and keeps launching batches until a page returns fewer than
        ``page_size`` records (end of data). Used when ``$count`` is unavailable
        (e.g. SAP CDS query views return 400 on ``$count``), giving parallel
        throughput where the code would otherwise crawl sequentially.

        Memory stays bounded at ``parallel_pages × page_size`` records per batch.
        """
        logging.info(
            f"Speculative parallel fetching enabled for {entity_set} "
            f"(no $count; batch size: {self.parallel_pages}, page size: {page_size})"
        )
        self._log_batch_peak(page_size)
        total_fetched = 0
        page_index = 0
        done = False

        while not done:
            page_numbers = list(range(page_index, page_index + self.parallel_pages))
            jobs = []
            for page_num in page_numbers:
                params = self._build_query_params(
                    select=select,
                    filter_expr=filter_expr,
                    expand=expand,
                    order_by=order_by,
                    top=page_size,
                    skip=page_num * page_size,
                )
                jobs.append({"method": "GET", "endpoint": entity_set, "params": params})

            responses = await self._client.process_multiple(jobs)

            for response in responses:
                records, next_link = self._extract_page(response)
                page_len = len(records)
                if page_len < page_size:
                    # Short page → end of data, UNLESS the server attached a
                    # continuation link (server-driven paging): it then capped the
                    # response below $top and our $skip stride would skip rows.
                    self._guard_against_server_paging(entity_set, page_len, page_size, next_link)
                    for record in records:
                        yield self._clean_record(record)
                        total_fetched += 1
                    done = True
                    break
                for record in records:
                    yield self._clean_record(record)
                    total_fetched += 1

            page_index += self.parallel_pages

        logging.info(f"Finished speculative parallel fetching {total_fetched} records from {entity_set}")

    def _log_batch_peak(self, page_size: int) -> None:
        """Log the estimated per-batch memory peak before parallel fetching starts.

        The peak driver for parallel fetching is ``page_size × parallel_pages``
        records held at once. Surfacing it gives support a hint when a wide
        entity OOMs (the job log otherwise gave no clue why). (CFTL-681)
        """
        peak = page_size * self.parallel_pages
        logging.info(
            f"Parallel fetch holds up to ~{peak:,} records in memory per batch "
            f"(page_size {page_size:,} × parallel_pages {self.parallel_pages}); "
            f"lower either setting if the job runs out of memory."
        )

    def _guard_against_server_paging(
        self, entity_set: str, page_len: int, page_size: int, next_link: str | None
    ) -> None:
        """Fail loud if a parallel fetch hits server-driven paging.

        Parallel fetching strides by computed ``$skip`` offsets and assumes the
        server returns full ``page_size`` pages. If the server caps a response
        below ``$top`` and signals more data with a continuation link, the stride
        would jump past the un-returned rows and silently drop them. Raising here
        (rather than truncating) prevents silent data loss; the user can set
        ``parallel_pages = 1`` to fall back to sequential paging, which follows
        the server's links. (CFTL-681)
        """
        if next_link and page_len < page_size:
            raise UserException(
                f"Server-driven paging detected for '{entity_set}' during parallel fetching: "
                f"a page returned {page_len} of {page_size} requested records but included a "
                f"continuation link, so the server caps responses below the requested page size. "
                f"Parallel fetching strides by offset and would silently drop rows here. "
                f"Set 'parallel_pages' to 1 for this entity to fetch sequentially (which follows "
                f"the server's paging links)."
            )

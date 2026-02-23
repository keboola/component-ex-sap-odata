from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, cast

from keboola.component.exceptions import UserException
from keboola.http_client import AsyncHttpClient

from .auth import ApiKeyAuthHandler, AuthHandler, BasicAuthHandler, OAuthHandler
from .catalog_parser import CatalogParser, ServiceInfo
from .metadata import EntitySet, MetadataParser, ODataMetadata, ODataVersion

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
        enable_parallel: bool = True,
        parallel_pages: int = 5,
        max_requests_per_second: float | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_handler = auth_handler
        self.timeout = timeout
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl
        self.enable_parallel = enable_parallel
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

    @classmethod
    def from_basic_auth(
        cls,
        username: str,
        password: str,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
        enable_parallel: bool = True,
        parallel_pages: int = 5,
        max_requests_per_second: float | None = None,
    ) -> AsyncODataClientBase:
        auth_handler = BasicAuthHandler(username, password)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            enable_parallel=enable_parallel,
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
        enable_parallel: bool = True,
        parallel_pages: int = 5,
        max_requests_per_second: float | None = None,
    ) -> AsyncODataClientBase:
        auth_handler = ApiKeyAuthHandler(api_key, header_name)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            enable_parallel=enable_parallel,
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
        except Exception as e:
            # Handle httpx exceptions more specifically
            # Note: AsyncHttpClient may wrap httpx exceptions, so we check the error message
            error_msg = str(e)

            # Check for HTTP status codes
            if "400" in error_msg or "Bad Request" in error_msg:
                # 400 often indicates a problem with the query (filter, select, expand, etc.)
                hint = ""
                if "$filter" in error_msg or "filter" in error_msg.lower():
                    hint = (
                        "\n\nFilter syntax error detected. Common issues:\n"
                        "• Date fields (Edm.Date): Use YYYY-MM-DD without quotes (e.g., DocumentDate gt 2024-01-01)\n"
                        "• DateTime fields (Edm.DateTimeOffset): Use ISO format without quotes (e.g., CreatedAt gt 2024-01-01T00:00:00Z)\n"
                        "• String fields: Use single quotes (e.g., Status eq 'Active')\n"
                        "• OData V2: Use datetime'YYYY-MM-DDTHH:MM:SS' format for dates"
                    )
                raise UserException(f"Invalid request - check your filter/query syntax: {e}{hint}") from e
            if "401" in error_msg or "Unauthorized" in error_msg:
                raise UserException(f"Authentication failed: {e}") from e
            if "403" in error_msg or "Forbidden" in error_msg:
                raise UserException(f"Access forbidden: {e}") from e
            if "404" in error_msg or "Not Found" in error_msg:
                raise UserException(f"Resource not found: {e}") from e
            if "429" in error_msg or "Too Many Requests" in error_msg:
                raise UserException(f"Rate limit exceeded: {e}") from e
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                raise UserException(f"Request timeout after {self.timeout}s: {e}") from e

            # Generic HTTP error
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
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                raise UserException(f"Authentication failed: {e}") from e
            if "403" in error_msg:
                raise UserException(f"Access forbidden: {e}") from e
            if "404" in error_msg:
                raise UserException(f"Resource not found: {e}") from e
            if "timeout" in error_msg.lower():
                raise UserException(f"Request timeout after {self.timeout}s") from e
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
                self._metadata = MetadataParser.parse(metadata_text, self._get_odata_version())
                return self._metadata
            except UserException as e:
                # Check if it's a 404 (metadata not available)
                if "404" in str(e) or "not found" in str(e).lower():
                    import logging
                    logging.warning(f"$metadata endpoint not available: {e}")
                    logging.info("Attempting to get entity sets from service document")

                    # Try fallback: get entity sets from service document
                    fallback_metadata = await self._try_get_service_document_metadata()
                    if fallback_metadata and fallback_metadata.entity_sets:
                        self._metadata = fallback_metadata
                        logging.info(
                            f"Successfully extracted {len(fallback_metadata.entity_sets)} entity sets from service document"
                        )
                        return self._metadata

                    # If fallback also failed, return empty metadata but don't raise
                    logging.warning("Service document fallback also failed, returning empty metadata")
                    self._metadata = ODataMetadata(version=self._get_odata_version())
                    return self._metadata

                # For other errors (auth, network, etc.), raise
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
            import logging
            logging.debug(f"Failed to get service document: {e}")
            return None

    async def list_entity_sets(self) -> list[EntitySet]:
        """List available entity sets.

        Returns:
            List of EntitySet objects (may be empty if metadata is not available)
        """
        metadata = await self.get_metadata()
        return metadata.list_entity_sets()

    async def list_fields(self, entity_set_name: str) -> list:
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
                import logging
                logging.warning(
                    f"Cannot list fields for '{entity_set_name}' - metadata not available. "
                    f"Fields will be discovered from actual data."
                )
                return []
            raise UserException(f"Entity set '{entity_set_name}' not found")
        return entity_set.properties

    async def list_catalog_services(self) -> list[ServiceInfo]:
        """List available OData services from SAP Service Catalog.

        This method is specifically for SAP catalog endpoints that return a list
        of available OData services instead of entity sets.

        Returns:
            List of ServiceInfo objects (empty if not a catalog endpoint)
        """
        import logging
        try:
            # Try to get the service root
            # Use absolute path to avoid trailing slash (SAP endpoints are sensitive to it)
            # SAP catalog endpoints typically return XML (application/atom+xml) by default
            logging.debug(f"list_catalog_services: fetching {self.base_url}")

            # Try to get XML response (SAP catalog returns ATOM/XML by default)
            xml_text = await self._get_raw(
                endpoint_path=self.base_url,
                headers={"Accept": "application/atom+xml, application/xml, */*"},
                is_absolute_path=True
            )

            logging.debug(f"list_catalog_services: got response, length={len(xml_text)}")

            # Check if this is XML (starts with <)
            if xml_text.strip().startswith('<'):
                logging.debug("Response is XML, parsing as ATOM feed")
                services = CatalogParser.parse_sap_catalog_xml(xml_text)
                logging.info(f"list_catalog_services: parsed {len(services)} services from SAP catalog XML")
                return services

            # If not XML, try parsing as JSON
            logging.debug("Response is not XML, trying JSON")
            import json
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
        except Exception as e:
            logging.warning(f"Failed to get catalog services: {e}")
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

    @abstractmethod
    def _get_odata_version(self) -> ODataVersion:
        pass

    @abstractmethod
    def fetch_entity_set(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        top: int | None = None,
        skip: int | None = None,
    ) -> AsyncIterator[JsonDict]:
        """Fetch entity set without pagination."""
        pass

    @abstractmethod
    def fetch_with_pagination(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        page_size: int = 1000,
        max_records: int | None = None,
    ) -> AsyncIterator[JsonDict]:
        """Fetch entity set with automatic pagination."""
        pass

    @abstractmethod
    async def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        pass

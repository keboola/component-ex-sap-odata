from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any, cast

from keboola.component.exceptions import UserException
from keboola.http_client import HttpClient
from requests import HTTPError, RequestException, Timeout

from .auth import ApiKeyAuthHandler, AuthHandler, BasicAuthHandler
from .catalog_parser import CatalogParser, ServiceInfo
from .metadata import EntitySet, EntityProperty, MetadataParser, ODataMetadata, ODataVersion

# Type alias for JSON-serializable data
JsonDict = dict[str, Any]


class ODataClientBase(ABC):
    def __init__(
        self,
        base_url: str,
        auth_handler: AuthHandler,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_handler = auth_handler
        self.timeout = timeout
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl
        self._metadata: ODataMetadata | None = None
        self._client = HttpClient(
            base_url=self.base_url + "/",
            max_retries=max_retries,
            backoff_factor=0.3,
            status_forcelist=(500, 502, 503, 504),
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
    ) -> ODataClientBase:
        auth_handler = BasicAuthHandler(username, password)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
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
    ) -> ODataClientBase:
        auth_handler = ApiKeyAuthHandler(api_key, header_name)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
        )

    def _get_json(
        self,
        endpoint_path: str,
        params: dict[str, str] | None = None,
        is_absolute_path: bool = False,
    ) -> JsonDict:
        try:
            return cast(
                JsonDict,
                self._client.get(
                    endpoint_path=endpoint_path,
                    params=params,
                    headers={"Accept": "application/json"},
                    is_absolute_path=is_absolute_path,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                ),
            )
        except HTTPError as e:
            resp = getattr(e, "response", None)
            code = resp.status_code if resp is not None else None
            if code == 401:
                raise UserException(f"Authentication failed: {e}") from e
            if code == 403:
                raise UserException(f"Access forbidden: {e}") from e
            if code == 404:
                raise UserException(f"Resource not found: {e}") from e
            raise UserException(f"HTTP error: {e}") from e
        except Timeout as e:
            raise UserException(f"Request timeout after {self.timeout}s") from e
        except RequestException as e:
            raise UserException(f"Request failed: {e}") from e

    def _get_raw(
        self,
        endpoint_path: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        is_absolute_path: bool = False,
    ) -> str:
        try:
            response = self._client.get_raw(
                endpoint_path=endpoint_path,
                params=params,
                headers=headers,
                is_absolute_path=is_absolute_path,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            return response.text
        except HTTPError as e:
            resp = getattr(e, "response", None)
            code = resp.status_code if resp is not None else None
            if code == 401:
                raise UserException(f"Authentication failed: {e}") from e
            if code == 403:
                raise UserException(f"Access forbidden: {e}") from e
            if code == 404:
                raise UserException(f"Resource not found: {e}") from e
            raise UserException(f"HTTP error: {e}") from e
        except Timeout as e:
            raise UserException(f"Request timeout after {self.timeout}s") from e
        except RequestException as e:
            raise UserException(f"Request failed: {e}") from e

    def get_metadata(self, force_refresh: bool = False) -> ODataMetadata:
        """Get OData metadata with fallback to service document if $metadata is not available.

        This method attempts to retrieve metadata in the following order:
        1. Try $metadata endpoint (standard OData)
        2. If $metadata fails with 404, try to get entity sets from service document
        3. If both fail, return empty metadata

        Args:
            force_refresh: Force refresh of cached metadata

        Returns:
            ODataMetadata object (may be empty if both methods fail)
        """
        if self._metadata is not None and not force_refresh:
            return self._metadata

        # Try standard $metadata endpoint first
        try:
            metadata_text = self._get_raw(
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
                fallback_metadata = self._try_get_service_document_metadata()
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

            # For other errors (auth, network, non-XML response, etc.), raise
            raise
        except Exception as e:
            raise UserException(f"Failed to parse metadata: {e}") from e

    def _try_get_service_document_metadata(self) -> ODataMetadata | None:
        """Try to get entity sets from service document (fallback when $metadata is not available).

        Returns:
            ODataMetadata with entity sets if successful, None otherwise
        """
        try:
            # Try to get service document (root of service)
            # Use absolute path to avoid trailing slash (SAP endpoints are sensitive to it)
            # _get_json already sets Accept: application/json header
            data = self._get_json(endpoint_path=self.base_url, is_absolute_path=True)
            return CatalogParser.try_parse_from_response(data, self._get_odata_version())
        except Exception as e:
            logging.debug(f"Failed to get service document: {e}")
            return None

    def list_entity_sets(self) -> list[EntitySet]:
        """List available entity sets.

        Returns:
            List of EntitySet objects (may be empty if metadata is not available)
        """
        metadata = self.get_metadata()
        return metadata.list_entity_sets()

    def list_fields(self, entity_set_name: str) -> list[EntityProperty]:
        """List fields for a specific entity set.

        Args:
            entity_set_name: Name of the entity set

        Returns:
            List of EntityProperty objects (may be empty if metadata is not available)

        Raises:
            UserException: If entity set is not found
        """
        metadata = self.get_metadata()
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

    def list_catalog_services(self) -> list[ServiceInfo]:
        """List available OData services from SAP Service Catalog.

        This method is specifically for SAP catalog endpoints that return a list
        of available OData services instead of entity sets.

        Returns:
            List of ServiceInfo objects (empty if not a catalog endpoint)
        """
        try:
            # Try to get the service root
            # Use absolute path to avoid trailing slash (SAP endpoints are sensitive to it)
            # SAP catalog endpoints typically return XML (application/atom+xml) by default
            logging.debug(f"list_catalog_services: fetching {self.base_url}")

            # Try to get XML response (SAP catalog returns ATOM/XML by default)
            xml_text = self._get_raw(
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

    def test_connection(self) -> tuple[bool, str]:
        try:
            metadata = self.get_metadata(force_refresh=True)
            entity_count = len(self.list_entity_sets())
            version = metadata.version.value.upper()
            return True, f"Connection successful. OData {version} service detected with {entity_count} entity sets."
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
    ) -> Iterator[JsonDict]:
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
    ) -> Iterator[JsonDict]:
        """Fetch entity set with automatic pagination."""
        pass

    @abstractmethod
    def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        pass

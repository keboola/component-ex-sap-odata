from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import requests as req
import urllib3
from keboola.component.base import ComponentBase, sync_action
from keboola.component.dao import BaseType, ColumnDefinition
from keboola.component.exceptions import UserException
from keboola.csvwriter import ElasticDictWriter
from keboola.http_client import HttpClient
from pydantic import ValidationError

from configuration import (
    AuthType,
    ComponentState,
    Configuration,
    FetchType,
    LoadType,
    ODataVersionChoice,
    StateEntry,
)
from odata_client.auth import ApiKeyAuthHandler, AuthHandler, BasicAuthHandler, OAuthHandler
from odata_client.metadata import MetadataParser, ODataMetadata, ODataVersion
from odata_client.sync_wrapper import SyncODataV2Client, SyncODataV4Client
from odata_client.type_mapping import map_edm_type_to_base_type

# Type alias for JSON-like dictionaries
JsonDict = dict[str, Any]
# Type alias for client types
ODataClient = SyncODataV4Client | SyncODataV2Client

_PROGRESS_LOG_INTERVAL = 10_000


def _simplify_error_message(error: Exception, base_url: str | None = None) -> str:
    """Convert Python exceptions to user-friendly error messages.

    Args:
        error: The exception to simplify
        base_url: Optional base URL for context

    Returns:
        User-friendly error message
    """
    error_str = str(error)

    # Handle SSL errors first. requests.exceptions.SSLError is a subclass of
    # ConnectionError, so it must be checked before the ConnectionError branch
    # below - otherwise a certificate verification failure is mislabeled as a
    # generic "Connection failed", hiding the real cause (e.g. an internal /
    # self-signed cert on an on-premise or VPN-tunnelled endpoint).
    if isinstance(error, req.exceptions.SSLError):
        target = base_url or "the server"
        return (
            f"SSL certificate verification failed for {target}. "
            "The server's certificate is not trusted (self-signed / internal CA) "
            "or its hostname does not match. For on-premise or VPN endpoints, "
            "disable 'Verify SSL Certificate' in the configuration or provide a trusted CA."
        )

    # Handle requests connection errors
    if isinstance(error, req.exceptions.ConnectionError):
        # Extract domain from error or use base_url
        if base_url:
            return f"Cannot reach server at {base_url}: Connection failed"
        # Try to extract URL from error message
        match = re.search(r"host='([^']+)'", error_str)
        if match:
            host = match.group(1)
            return f"Cannot reach server at {host}: Connection failed"
        return "Cannot reach server: Connection failed"

    # Handle HTTP errors
    if isinstance(error, req.exceptions.HTTPError):
        if hasattr(error, "response") and error.response is not None:
            status = error.response.status_code
            url = error.response.url
            return f"HTTP {status} error at {url}"
        return f"HTTP error: {error_str}"

    # Handle timeout errors
    if isinstance(error, req.exceptions.Timeout):
        if base_url:
            return f"Connection to {base_url} timed out"
        return "Connection timed out"

    # For other errors, return simplified message
    # Remove long tracebacks and technical details
    if "HTTPSConnectionPool" in error_str or "HTTPConnectionPool" in error_str:
        if base_url:
            return f"Cannot reach server at {base_url}: Connection failed"
        match = re.search(r"host='([^']+)'", error_str)
        if match:
            host = match.group(1)
            return f"Cannot reach server at https://{host}: Connection failed"

    # Default: return first line of error only
    return error_str.split("\n")[0] if "\n" in error_str else error_str


class Component(ComponentBase):
    def __init__(self):
        super().__init__()
        try:
            self._config = Configuration(**self.configuration.parameters)
        except ValidationError as e:
            # Convert Pydantic validation errors to user-friendly messages
            errors = []
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                msg = error["msg"]
                errors.append(f"{field}: {msg}")
            raise UserException(f"Configuration validation failed: {'; '.join(errors)}") from e
        self._client: ODataClient | None = None
        self._detected_version: ODataVersion | None = None

        # When TLS verification is disabled (common for on-premise / VPN SAP
        # systems behind an internal certificate), urllib3 emits an
        # InsecureRequestWarning. Sync actions require stdout to be a single
        # JSON object - the warning text leaks onto that stream and breaks the
        # runner with "Decoding JSON response from component failed". Suppress
        # it so the result stream stays clean. (CFTL-681)
        if not self._config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _build_auth_handler(self) -> AuthHandler:
        config = self._config
        try:
            config.validate_authentication()
        except ValueError as e:
            raise UserException(str(e)) from e
        if config.auth_type == AuthType.OAUTH:
            return OAuthHandler(
                token_url=config.token_url or "",
                client_id=config.client_id or "",
                client_secret=config.client_secret or "",
            )
        if config.auth_type == AuthType.API_KEY:
            return ApiKeyAuthHandler(config.api_key or "", config.api_key_header_name)
        return BasicAuthHandler(config.username or "", config.password or "")

    def _build_client(self) -> ODataClient:
        if self._client is not None:
            return self._client

        config = self._config
        version = self._detect_or_get_version(config)

        client_class = SyncODataV4Client if version == ODataVersion.V4 else SyncODataV2Client

        # Get the full service URL (handles both service_url and base_url+service_path)
        # Map ODataVersion to ODataVersionChoice for get_service_url()
        detected_version_choice = ODataVersionChoice.V4 if version == ODataVersion.V4 else ODataVersionChoice.V2
        service_url = config.get_service_url(detected_version_choice)

        # Common client parameters including parallel fetching options
        client_params = {
            "base_url": service_url,
            "timeout": config.timeout,
            "max_retries": config.max_retries,
            "verify_ssl": config.verify_ssl,
            "enable_parallel": config.enable_parallel,
            "parallel_pages": config.parallel_pages,
            "max_requests_per_second": config.max_requests_per_second,
        }

        auth_handler = self._build_auth_handler()
        self._client = client_class(auth_handler=auth_handler, **client_params)
        return self._client

    def _detect_or_get_version(self, config: Configuration) -> ODataVersion:
        if self._detected_version is not None:
            return self._detected_version

        if config.odata_version == ODataVersionChoice.V2:
            self._detected_version = ODataVersion.V2
        elif config.odata_version == ODataVersionChoice.V4:
            self._detected_version = ODataVersion.V4
        else:
            self._detected_version = self._detect_version_from_metadata(config)

        return self._detected_version

    def _detect_version_from_metadata(self, config: Configuration) -> ODataVersion:
        auth_handler = self._build_auth_handler()

        # Get service URL - for AUTO detection with base_url+service_path, this will infer from path structure
        base_url = config.get_service_url().rstrip("/") + "/"
        client = HttpClient(
            base_url=base_url,
            max_retries=config.max_retries,
            auth_header=auth_handler.get_auth_headers(),
        )

        try:
            response = client.get_raw(
                endpoint_path="$metadata",
                headers={"Accept": "application/xml"},
                timeout=config.timeout,
                verify=config.verify_ssl,
            )
            response.raise_for_status()
            return MetadataParser.detect_version(response.text)
        except req.exceptions.HTTPError as e:
            resp = getattr(e, "response", None)
            if resp is not None and resp.status_code in (401, 403):
                raise UserException(f"Authentication failed during OData version detection: {e}") from e
            logging.warning(f"Failed to detect OData version from $metadata, defaulting to V2: {e}")
            return ODataVersion.V2
        except req.exceptions.SSLError as e:
            raise UserException(f"SSL certificate verification failed during OData version detection: {e}") from e
        except Exception as e:
            logging.warning(f"Failed to detect OData version from $metadata, defaulting to V2: {e}")
            return ODataVersion.V2

    def run(self) -> None:
        logging.info("Starting SAP OData extraction")

        try:
            self._config.validate_for_extraction()
        except ValueError as e:
            raise UserException(f"Configuration validation failed: {e}") from e

        state = self._load_state()

        try:
            self._extract_entity(state)
        except UserException:
            raise
        except Exception as e:
            logging.error(f"Failed to extract entity {self._config.entity_set}: {e}")
            raise UserException(f"Failed to extract entity {self._config.entity_set}: {e}") from e
        finally:
            # Cleanup resources
            if self._client is not None:
                try:
                    self._client.close()
                except Exception as e:
                    logging.warning(f"Failed to close client: {e}")

        self._save_state(state)
        logging.info("SAP OData extraction completed")

    def _extract_entity(self, state: ComponentState) -> None:
        """Extract entity data and write to output table."""
        logging.info(f"Extracting entity: {self._config.entity_set}")

        client = self._build_client()
        entity_state = state.get_entity_state(self._config.entity_set)

        filter_expr = self._build_filter_expression(entity_state)
        # First create the table only to obtain its output path (columns are
        # discovered from the data). The manifest is written afterwards with a
        # proper typed schema built from the columns actually extracted.
        table_def = self._create_output_table()

        records_count, last_incremental_value, columns = self._process_records(client, table_def, filter_expr)

        if records_count > 0:
            schema = self._build_output_schema(columns)
            table_def = self._create_output_table(schema=schema)
            self.write_manifest(table_def)

        self._update_extraction_state(state, records_count, last_incremental_value)
        logging.info(f"Extracted {records_count} records from {self._config.entity_set}")

    def _build_filter_expression(self, entity_state: StateEntry) -> str | None:
        """Build OData filter expression including incremental filtering."""
        filter_expr = self._config.filter_expression

        if (
            self._config.fetch_type == FetchType.INCREMENTAL
            and self._config.incremental_field
            and entity_state.last_incremental_value
        ):
            literal = self._format_filter_literal(
                entity_state.last_incremental_value,
                self._config.incremental_field,
            )
            incremental_filter = f"{self._config.incremental_field} gt {literal}"
            filter_expr = f"({filter_expr}) and ({incremental_filter})" if filter_expr else incremental_filter

        return filter_expr

    def _format_filter_literal(self, value: str, field_name: str) -> str:
        """Format a value as an OData filter literal based on the field's EDM type.

        OData literal formatting rules:
        - OData V4 Edm.Date: YYYY-MM-DD without quotes (e.g., 2024-01-01)
        - OData V4 Edm.DateTimeOffset: ISO format without quotes (e.g., 2024-01-01T00:00:00Z)
        - OData V2 Edm.DateTime: datetime'YYYY-MM-DDTHH:MM:SS' format
        - String fields: single quotes (e.g., 'Active')
        - Numeric fields: no quotes (e.g., 123)
        """
        edm_type = self._get_field_edm_type(field_name)
        odata_version = self._detect_or_get_version(self._config)

        if edm_type:
            if odata_version == ODataVersion.V4 and edm_type in ("Edm.Date", "Edm.DateTimeOffset"):
                return value
            elif odata_version == ODataVersion.V2 and edm_type == "Edm.DateTime":
                datetime_value = value if "T" in value else f"{value}T00:00:00"
                return f"datetime'{datetime_value}'"

            if edm_type.startswith("Edm.Int") or edm_type in (
                "Edm.Decimal",
                "Edm.Double",
                "Edm.Single",
                "Edm.Byte",
                "Edm.SByte",
            ):
                return value

        return f"'{value}'"

    def _get_field_edm_type(self, field_name: str) -> str | None:
        """Get the EDM type of a field from metadata."""
        try:
            client = self._build_client()
            metadata = client.get_metadata()
            entity_set = metadata.get_entity_set(self._config.entity_set or "")
            if entity_set:
                for prop in entity_set.properties:
                    if prop.name == field_name:
                        return prop.edm_type
        except Exception as e:
            logging.warning(f"Could not determine EDM type for field '{field_name}': {e}")
        return None

    def _create_output_table(self, schema: dict[str, ColumnDefinition] | None = None):
        """Create output table definition.

        Called twice per run: once without a schema just to resolve the output
        path (columns aren't known until the first record is read), then again
        with the typed ``schema`` to write a proper manifest. Setting an explicit
        ``destination`` and ``schema`` also silences the platform's "neither
        manifest file nor mapping set" fallback warning.
        """
        output_table_name = self._config.get_output_table_name()
        return self.create_out_table_definition(
            f"{output_table_name}.csv",
            destination=output_table_name,
            schema=schema,
            # primary_key/has_header only make sense once we have the schema;
            # passing primary_key without columns would force legacy manifest mode.
            primary_key=(self._config.primary_key or None) if schema else None,
            incremental=self._config.load_type == LoadType.INCREMENTAL,
            has_header=True if schema else None,
        )

    def _build_output_schema(self, columns: list[str]) -> dict[str, ColumnDefinition]:
        """Build a typed output schema for the given (flattened) column names.

        Column EDM types come from the entity metadata; columns without metadata
        (flattened/expanded nested fields, or services without $metadata) default
        to STRING via map_edm_type_to_base_type.
        """
        edm_types = self._get_entity_property_edm_types()
        primary_key = set(self._config.primary_key or [])
        schema: dict[str, ColumnDefinition] = {}
        for column in columns:
            base_type = map_edm_type_to_base_type(edm_types.get(column))
            is_pk = column in primary_key
            schema[column] = ColumnDefinition(
                data_types=BaseType(dtype=base_type),
                primary_key=is_pk,
                nullable=not is_pk,
            )
        return schema

    def _get_entity_property_edm_types(self) -> dict[str, str]:
        """Return a {property_name: edm_type} map for the configured entity set.

        Returns an empty map (callers fall back to STRING) if metadata is
        unavailable — e.g. services that don't expose $metadata.
        """
        try:
            client = self._build_client()
            metadata = client.get_metadata()
            entity_set = metadata.get_entity_set(self._config.entity_set or "")
            if entity_set:
                return {prop.name: prop.edm_type for prop in entity_set.properties}
        except Exception as e:
            logging.warning(f"Could not load entity property types for output schema: {e}")
        return {}

    def _process_records(
        self, client: ODataClient, table_def, filter_expr: str | None
    ) -> tuple[int, str | None, list[str]]:
        """Process and write records from OData service.

        Returns:
            Tuple of (records_count, last_incremental_value, columns) where
            ``columns`` is the final, flattened column list written to the CSV
            (used to build the typed output manifest schema).
        """
        records_count = 0
        last_incremental_value: str | None = None
        columns: list[str] = []
        writer: ElasticDictWriter | None = None

        try:
            max_records = self._config.max_records if self._config.max_records > 0 else None

            for record in client.fetch_with_pagination(
                entity_set=self._config.entity_set,
                select=self._config.select_fields if self._config.select_fields else None,
                filter_expr=filter_expr,
                expand=self._config.expand_properties if self._config.expand_properties else None,
                page_size=self._config.page_size,
                max_records=max_records,
            ):
                flat_record = self._flatten_record(record)

                if writer is None:
                    # ElasticDictWriter buffers the ENTIRE dataset in its temp directory
                    # until close() (only then is the final CSV written). Its default temp
                    # dir is tempfile.mkdtemp() -> /tmp, which in a Keboola job container is
                    # tmpfs (RAM-backed) and counts against the component memory limit — so a
                    # large extraction grows in memory with total row count and OOMs. Put the
                    # temp dir on the data volume (same filesystem as the output) so the
                    # buffered CSV streams to real disk regardless of dataset size. (CFTL-681)
                    os.makedirs(self.tables_out_path, exist_ok=True)
                    writer_temp_dir = tempfile.mkdtemp(dir=self.tables_out_path)
                    writer = ElasticDictWriter(
                        table_def.full_path,
                        list(flat_record.keys()),
                        temp_directory=writer_temp_dir,
                    )
                    writer.writeheader()

                writer.writerow(flat_record)
                records_count += 1

                last_incremental_value = self._track_incremental_value(flat_record, last_incremental_value)

                if records_count % _PROGRESS_LOG_INTERVAL == 0:
                    logging.info(f"Extracted {records_count} records from {self._config.entity_set}")

        finally:
            if writer is not None:
                writer.close()
                columns = list(writer.fieldnames)

        return records_count, last_incremental_value, columns

    def _track_incremental_value(self, record: JsonDict, current_max: str | None) -> str | None:
        """Track the maximum incremental value from records.

        Normalizes OData V2 /Date(millis)/ timestamps to ISO format so they
        can be used safely in $filter expressions on the next run.
        """
        if not self._config.incremental_field or self._config.incremental_field not in record:
            return current_max

        value = record[self._config.incremental_field]
        if not value:
            return current_max

        normalized = self._normalize_odata_datetime(str(value))
        if current_max is None or normalized > current_max:
            return normalized

        return current_max

    @staticmethod
    def _normalize_odata_datetime(value: str) -> str:
        """Convert OData V2 /Date(milliseconds)/ to ISO datetime string.

        OData V2 JSON format returns DateTime as /Date(1704067200000)/.
        We normalize this to 2024-01-01T00:00:00 so it can be used in
        $filter expressions like: LastChangeDate gt datetime'2024-01-01T00:00:00'
        """
        match = re.match(r"^/Date\((\d+)(?:[+-]\d+)?\)/$", value)
        if match:
            millis = int(match.group(1))
            dt = datetime.fromtimestamp(millis / 1000, tz=UTC)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        return value

    def _update_extraction_state(
        self, state: ComponentState, records_count: int, last_incremental_value: str | None
    ) -> None:
        """Update component state with extraction results."""
        state.update_entity_state(
            entity_set=self._config.entity_set,
            last_sync_timestamp=datetime.now(UTC).isoformat(),
            last_incremental_value=last_incremental_value,
            records_synced=records_count,
        )

    def _flatten_record(self, record: JsonDict, prefix: str = "") -> JsonDict:
        """Flatten nested record structure."""
        flat: JsonDict = {}
        for key, value in record.items():
            full_key = f"{prefix}_{key}" if prefix else key
            if isinstance(value, dict):
                flat.update(self._flatten_record(value, full_key))
            elif isinstance(value, list):
                flat[full_key] = json.dumps(value)
            else:
                flat[full_key] = value
        return flat

    def _load_state(self) -> ComponentState:
        try:
            state_data = self.get_state_file()
            if state_data:
                return ComponentState(**state_data)
        except Exception as e:
            logging.warning(f"Failed to load state file: {e}")
        return ComponentState()

    def _save_state(self, state: ComponentState) -> None:
        try:
            self.write_state_file(state.model_dump())
        except Exception as e:
            logging.warning(f"Failed to save state file: {e}")

    @sync_action("testConnection")
    def test_connection(self) -> dict[str, str]:
        """Test connection to SAP OData service.

        Performs a lightweight connectivity check by making a simple HTTP request
        to the service URL with authentication headers. Does not fetch $metadata
        because some SAP CPI iFlows don't expose a $metadata sub-path.
        """
        try:
            config = self._config

            # Validate configuration - just need base_url for testConnection
            if not config.base_url:
                return {"status": "error", "message": "base_url is required"}

            auth_handler = self._build_auth_handler()
            headers = auth_handler.get_auth_headers()
            headers["Accept"] = "application/xml"

            timeout = config.timeout
            verify_ssl = config.verify_ssl

            # Test 1: Always test base_url
            test_url = config.base_url

            response = req.get(
                test_url,
                headers=headers,
                timeout=timeout,
                verify=verify_ssl,
            )

            if response.status_code == 401:
                return {
                    "status": "error",
                    "message": f"Authentication failed (401) at {test_url}. Check your credentials.",
                }
            if response.status_code == 403:
                return {"status": "error", "message": f"Access forbidden (403) at {test_url}. Check permissions."}
            if response.status_code == 404:
                # 404 on base_url without catalog_path is a warning - server reachable but endpoint not found
                if not config.catalog_path:
                    return {
                        "status": "warning",
                        "message": "Connection partially successful - server is reachable but returned 404. Verify your URL and credentials.",
                    }
                # If catalog_path is set, we'll test that next

            # Test 2: If catalog_path is set, also test catalog URL
            if config.catalog_path and config.base_url:
                catalog_url = config.get_catalog_url()

                catalog_response = req.get(
                    catalog_url,
                    headers=headers,
                    timeout=timeout,
                    verify=verify_ssl,
                )

                if catalog_response.status_code == 401:
                    return {
                        "status": "error",
                        "message": f"Authentication failed (401) at catalog {catalog_url}. Check your credentials.",
                    }
                if catalog_response.status_code == 403:
                    return {
                        "status": "error",
                        "message": f"Access forbidden (403) at catalog {catalog_url}. Check permissions.",
                    }
                if catalog_response.status_code == 404:
                    return {
                        "status": "error",
                        "message": f"Catalog not found (404) at {catalog_url}. Check Catalog Path.",
                    }

                return {
                    "status": "success",
                    "message": "Connection successful! Base URL and Catalog both responded with HTTP 200.",
                }

            return {
                "status": "success",
                "message": f"Connection successful! Server responded with HTTP {response.status_code}.",
            }
        except UserException as e:
            return {"status": "error", "message": str(e)}
        except req.exceptions.SSLError as e:
            return {"status": "error", "message": _simplify_error_message(e, config.base_url)}
        except req.exceptions.ConnectionError as e:
            return {"status": "error", "message": _simplify_error_message(e, config.base_url)}
        except req.exceptions.Timeout as e:
            return {"status": "error", "message": _simplify_error_message(e, config.base_url)}
        except ValueError as e:
            return {"status": "error", "message": f"Configuration error: {e}"}
        except Exception as e:
            return {"status": "error", "message": _simplify_error_message(e, config.base_url)}

    @sync_action("loadServices")
    def load_services(self) -> list[dict[str, str]]:
        """Load available OData services from SAP catalog.

        Returns:
            List of services with value (service_path) and label (title + description)

        Raises:
            UserException: When API returns an error (decorator writes to stderr, UI shows notification)
        """
        # Validate configuration - raise errors for missing config so UI shows notification
        if not self._config.base_url:
            raise UserException("Base URL is not configured. Please set it in the root configuration.")
        if not self._config.catalog_path:
            # No catalog configured. Browsing the service list isn't possible, but
            # it isn't required either - the user can type the Service Path directly.
            # Return a non-blocking hint in the dropdown rather than a hard error so
            # the manual path (per the field tooltip) is discoverable. (CFTL-681)
            return [
                {
                    "value": "",
                    "label": (
                        "⚠️ Catalog Path is not set, so services can't be listed automatically. "
                        "You can skip this and enter the Service Path manually "
                        "(e.g. /sap/opu/odata/sap/MY_SERVICE), then use Load Entity Sets. "
                        "Set Catalog Path in the connection settings only if you want to browse services."
                    ),
                }
            ]
        logging.info(
            f"loadServices called - base_url: {self._config.base_url}, catalog_path: {self._config.catalog_path}"
        )

        # First test catalog URL to get meaningful error messages
        catalog_url = self._config.get_catalog_url()

        auth_handler = self._build_auth_handler()
        headers = auth_handler.get_auth_headers()
        headers["Accept"] = "application/atom+xml, application/xml, application/json, */*"

        try:
            catalog_response = req.get(
                catalog_url,
                headers=headers,
                timeout=self._config.timeout,
                verify=self._config.verify_ssl,
            )
        except req.exceptions.ConnectionError as e:
            raise UserException(f"Failed to load services: {_simplify_error_message(e, catalog_url)}") from e
        except req.exceptions.Timeout as e:
            raise UserException(f"Failed to load services from {catalog_url}: Connection timed out") from e

        if catalog_response.status_code == 404:
            raise UserException(f"Failed to load services from {catalog_url}: HTTP 404 Not Found")
        if catalog_response.status_code == 401:
            raise UserException(
                f"Failed to load services from {catalog_url}: HTTP 401 Unauthorized - Check credentials"
            )
        if catalog_response.status_code == 403:
            raise UserException(f"Failed to load services from {catalog_url}: HTTP 403 Forbidden - Check permissions")
        if catalog_response.status_code >= 500:
            raise UserException(
                f"Failed to load services from {catalog_url}: HTTP {catalog_response.status_code} Server Error"
            )

        # Now get catalog services with client (pass catalog_url explicitly so the
        # client's base_url does not need to point at the catalog endpoint)
        client = self._build_client()
        catalog_services = client.list_catalog_services(url=catalog_url)
        if not catalog_services:
            raise UserException(f"No services found in catalog at {catalog_url}")

        logging.info(f"loadServices: found {len(catalog_services)} services in SAP catalog")

        # Convert internal service URLs to proxy-compatible service paths
        result = []
        for service in catalog_services:
            # Parse internal URL: http://20.113.120.45:50000/sap/opu/odata/sap/SERVICE_NAME
            parsed = urlparse(service.service_url)
            internal_path = parsed.path.lstrip("/")  # sap/opu/odata/sap/SERVICE_NAME

            # Detect proxy prefix from catalog_path
            # If catalog_path is "http/keboola/catalog", prefix is "http/keboola/connector/"
            if self._config.catalog_path and "keboola" in self._config.catalog_path:
                service_path = f"http/keboola/connector/{internal_path}"
            else:
                # For other proxies, use internal path as-is
                service_path = internal_path

            result.append(
                {
                    "value": service_path,
                    "label": f"{service.title} - {service.description}" if service.description else service.title,
                }
            )

        return result

    @sync_action("loadEntities")
    def load_entities(self) -> list[dict[str, str]]:
        """Load available entity sets from OData service metadata.

        Returns:
            List of entity sets with value and label (entity set name)

        Raises:
            UserException: When API returns an error (decorator writes to stderr, UI shows notification)
        """
        if not self._config.base_url:
            raise UserException("Base URL is not configured. Please set it in the root configuration.")
        logging.info(
            f"loadEntities called - base_url: {self._config.base_url}, service_path: {self._config.service_path}"
        )
        client = self._build_client()

        # Get entity sets from service metadata
        entities = client.list_entity_sets()
        logging.info(f"loadEntities: found {len(entities)} entity sets")

        if not entities:
            raise UserException(
                "No entity sets found in service metadata. "
                "If you haven't set a Service Path yet, enter it (e.g. /sap/opu/odata/sap/MY_SERVICE) - "
                "it points to the specific OData service and is required unless the Base URL already "
                "targets a service directly. Otherwise verify the Service Path is correct and that the "
                "service exposes entity sets."
            )

        return [{"value": e.name, "label": e.name} for e in entities]

    @sync_action("loadFields")
    def load_fields(self) -> list[dict[str, str]]:
        """Load available fields for the selected entity set.

        Raises:
            UserException: When API returns an error (decorator writes to stderr, UI shows notification)
        """
        logging.info(f"loadFields called with entity_set: {self._config.entity_set}")
        if not self._config.entity_set:
            raise UserException("Entity Set is required to load fields. Please select an entity above.")

        client = self._build_client()
        logging.info(f"loadFields: fetching fields for {self._config.entity_set}")

        # Get metadata to check for key fields
        metadata = client.get_metadata()
        entity = metadata.get_entity_set(self._config.entity_set)
        key_fields = set(entity.key_properties) if entity else set()

        fields = client.list_fields(self._config.entity_set)
        logging.info(f"loadFields: found {len(fields)} fields")

        result = []
        for field in fields:
            # Build label: FieldName (SAP Label) - Type [KEY, filterable] - QuickInfo
            label_parts = []

            # Field name with SAP label
            if field.sap_label:
                label_parts.append(f"{field.name} ({field.sap_label})")
            else:
                label_parts.append(field.name)

            # EDM type
            label_parts.append(field.edm_type)

            # Capabilities [KEY, filterable]
            caps = []
            if field.name in key_fields:
                caps.append("KEY")
            if field.sap_filterable:
                caps.append("filterable")

            if caps:
                label_parts.append(f"[{', '.join(caps)}]")

            # QuickInfo (only if different from label)
            if field.sap_quickinfo and field.sap_quickinfo != field.sap_label:
                label_parts.append(field.sap_quickinfo)

            result.append({"value": field.name, "label": " - ".join(label_parts)})

        return result

    @sync_action("loadPossiblePrimaryKeys")
    def load_possible_primary_keys(self) -> list[dict[str, str]]:
        """Load possible primary key fields for the selected entity set.

        Raises:
            UserException: When API returns an error (decorator writes to stderr, UI shows notification)
        """
        logging.info(f"loadPossiblePrimaryKeys called with entity_set: {self._config.entity_set}")
        if not self._config.entity_set:
            raise UserException("Entity Set is required to load primary keys. Please select an entity above.")

        client = self._build_client()
        metadata = client.get_metadata()
        entity = metadata.get_entity_set(self._config.entity_set)
        if entity is None:
            raise UserException(f"Entity set '{self._config.entity_set}' not found in service metadata")

        logging.info(f"loadPossiblePrimaryKeys: found {len(entity.key_properties)} key properties")
        return [{"value": k, "label": f"{k} (Key)"} for k in entity.key_properties]

    @sync_action("loadIncrementalFields")
    def load_incremental_fields(self) -> list[dict[str, str]]:
        """Load candidate fields for incremental fetching.

        Raises:
            UserException: When API returns an error (decorator writes to stderr, UI shows notification)
        """
        if not self._config.entity_set:
            raise UserException("Entity Set is required to load incremental fields. Please select an entity above.")

        client = self._build_client()
        fields = client.list_fields(self._config.entity_set)

        datetime_types = {"Edm.DateTime", "Edm.DateTimeOffset", "Edm.Date"}
        incremental_patterns = [
            "lastchanged",
            "lastupdated",
            "modifiedat",
            "updatedat",
            "changedat",
            "createdat",
            "timestamp",
            "modified",
            "changed",
        ]

        candidates = []
        for field in fields:
            score = 0
            name_lower = field.name.lower()

            if field.edm_type in datetime_types:
                score += 10

            for pattern in incremental_patterns:
                if pattern in name_lower:
                    score += 5
                    break

            if score > 0:
                candidates.append(
                    {
                        "value": field.name,
                        "label": f"{field.name} ({field.edm_type})",
                        "score": score,
                    }
                )

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return [{"value": c["value"], "label": c["label"]} for c in candidates]

    @sync_action("loadNavigationProperties")
    def load_navigation_properties(self) -> list[dict[str, str]]:
        """Load navigation properties for the selected entity set.

        Recursively discovers navigation properties following the entity type
        graph.  Cycle detection (via ``visited_types``) and a configurable
        depth limit (``expand_max_depth``, default 5) prevent infinite recursion.

        Raises:
            UserException: When API returns an error (decorator writes to stderr, UI shows notification)
        """
        logging.info(f"loadNavigationProperties called with entity_set: {self._config.entity_set}")
        if not self._config.entity_set:
            raise UserException("Entity Set is required to load navigation properties. Please select an entity above.")

        client = self._build_client()
        metadata = client.get_metadata()
        logging.info(f"loadNavigationProperties: fetching entity set {self._config.entity_set}")
        entity = metadata.get_entity_set(self._config.entity_set)
        if entity is None:
            raise UserException(f"Entity set '{self._config.entity_set}' not found in service metadata")

        results: list[dict[str, str]] = []
        self._collect_nav_properties_recursive(
            metadata=metadata,
            nav_properties=entity.navigation_properties,
            prefix="",
            depth=1,
            max_depth=self._config.expand_max_depth,
            results=results,
            visited_types=set(),
        )

        logging.info(f"loadNavigationProperties: found {len(results)} navigation properties")

        if not results:
            logging.info(f"No navigation properties found for entity set '{self._config.entity_set}'")
            return [
                {
                    "value": "",
                    "label": f"No navigation properties found for '{self._config.entity_set}' "
                    f"— this entity set does not support $expand.",
                }
            ]

        return results

    def _collect_nav_properties_recursive(
        self,
        metadata: ODataMetadata,
        nav_properties: list,
        prefix: str,
        depth: int,
        max_depth: int,
        results: list[dict[str, str]],
        visited_types: set[str],
    ) -> None:
        """Recursively collect navigation properties into a flat list of paths.

        Traversal terminates when a cycle is detected (the target entity type
        has already been visited on the current path) or when ``max_depth`` is
        reached.

        Args:
            metadata: Parsed OData metadata containing entity type definitions.
            nav_properties: Navigation properties to process at this level.
            prefix: Path prefix for values (e.g. ``Items/`` for level 2).
            depth: Current depth level (1-based, used for indentation and limit check).
            max_depth: Maximum recursion depth (configurable, default 5).
            results: Accumulator list for the results.
            visited_types: Set of already-visited entity type names to prevent cycles.
        """
        for np in nav_properties:
            path = f"{prefix}{np.name}" if prefix else np.name
            indent = "  " * (depth - 1)
            label = f"{indent}{path} -> {np.target_entity}"
            results.append({"value": path, "label": label})

            # Recurse into sub-navigation properties (depth limit + cycle detection stop recursion)
            if depth < max_depth and np.target_entity and np.target_entity not in visited_types:
                sub_nav_props = metadata.get_navigation_properties_for_type(np.target_entity)
                if sub_nav_props:
                    self._collect_nav_properties_recursive(
                        metadata=metadata,
                        nav_properties=sub_nav_props,
                        prefix=f"{path}/",
                        depth=depth + 1,
                        max_depth=max_depth,
                        results=results,
                        visited_types=visited_types | {np.target_entity},
                    )

    @sync_action("previewData")
    def preview_data(self) -> JsonDict:
        """Preview first 10 records from entity set.

        Raises:
            UserException: When API returns an error (decorator writes to stderr, UI shows notification)
        """
        if not self._config.entity_set:
            raise UserException("No entity set selected for preview")

        client = self._build_client()

        data = list(
            client.fetch_entity_set(
                entity_set=self._config.entity_set,
                select=self._config.select_fields if self._config.select_fields else None,
                filter_expr=self._config.filter_expression,
                expand=self._config.expand_properties if self._config.expand_properties else None,
                top=10,
            )
        )

        message = f"Loaded {len(data)} records"

        if data:
            # Format data as markdown table
            columns = list(data[0].keys())

            # Create table header
            header = "| " + " | ".join(columns) + " |"
            separator = "|" + "|".join([" --- " for _ in columns]) + "|"

            # Create table rows
            rows = []
            for record in data:
                row_values = []
                for col in columns:
                    value = record.get(col)
                    # Convert value to string and escape pipe characters
                    str_value = str(value) if value is not None else ""
                    str_value = str_value.replace("|", "\\|")
                    # Truncate long values
                    if len(str_value) > 50:
                        str_value = str_value[:47] + "..."
                    row_values.append(str_value)
                rows.append("| " + " | ".join(row_values) + " |")

            # Build the table with message
            table = "\n".join([header, separator] + rows)
            message = f"Preview of {self._config.entity_set} ({len(data)} records):\n\n{table}"

        return {
            "status": "success",
            "message": message,
            "data": data,
        }

    @sync_action("validateFilter")
    def validate_filter(self) -> dict[str, str]:
        """Validate OData filter expression.

        Raises:
            UserException: When API returns an error (decorator writes to stderr, UI shows notification)
        """
        if not self._config.entity_set:
            raise UserException("No entity set selected for filter validation")
        if not self._config.filter_expression:
            return {"status": "success", "message": "No filter to validate"}

        client = self._build_client()
        select = self._config.select_fields if self._config.select_fields else None
        try:
            next(
                client.fetch_entity_set(
                    entity_set=self._config.entity_set,
                    select=select,
                    filter_expr=self._config.filter_expression,
                    top=1,
                ),
                None,
            )
        except UserException:
            # Some SAP endpoints (e.g. SAP IBP) reject $top combined with $filter with a 400.
            # Retry without $top to avoid a false "invalid filter" error.
            next(
                client.fetch_entity_set(
                    entity_set=self._config.entity_set,
                    select=select,
                    filter_expr=self._config.filter_expression,
                ),
                None,
            )

        return {"status": "success", "message": "Filter expression is valid"}

    @sync_action("loadMetadataSummary")
    def load_metadata_summary(
        self,
    ) -> JsonDict:
        """Load metadata summary for the OData service.

        Raises:
            UserException: When API returns an error (decorator writes to stderr, UI shows notification)
        """
        client = self._build_client()
        metadata = client.get_metadata()
        entities = client.list_entity_sets()

        return {
            "status": "success",
            "data": {
                "odata_version": metadata.version.value.upper(),
                "entity_count": len(entities),
                "entities": [{"name": e.name, "field_count": len(e.properties)} for e in entities],
            },
        }


if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)

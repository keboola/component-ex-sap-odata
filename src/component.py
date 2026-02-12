from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from keboola.component.base import ComponentBase, sync_action
from keboola.component.exceptions import UserException
from keboola.csvwriter import ElasticDictWriter
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
from odata_client.metadata import MetadataParser, ODataVersion
from odata_client.sync_wrapper import SyncODataV2Client, SyncODataV4Client

# Type alias for JSON-like dictionaries
JsonDict = dict[str, Any]
# Type alias for client types
ODataClient = SyncODataV4Client | SyncODataV2Client


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

        if config.auth_type == AuthType.OAUTH:
            from odata_client.auth import OAuthHandler
            auth_handler = OAuthHandler(
                token_url=config.token_url or "",
                client_id=config.client_id or "",
                client_secret=config.client_secret or "",
            )
            self._client = client_class(
                base_url=service_url,
                auth_handler=auth_handler,
                timeout=config.timeout,
                max_retries=config.max_retries,
                verify_ssl=config.verify_ssl,
                enable_parallel=config.enable_parallel,
                parallel_pages=config.parallel_pages,
                max_requests_per_second=config.max_requests_per_second,
            )
        elif config.auth_type == AuthType.API_KEY:
            self._client = client_class.from_api_key(
                api_key=config.api_key or "",
                header_name=config.api_key_header_name,
                **client_params,
            )
        else:
            self._client = client_class.from_basic_auth(
                username=config.username or "",
                password=config.password or "",
                **client_params,
            )

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
        from keboola.http_client import HttpClient

        from odata_client.auth import ApiKeyAuthHandler, AuthHandler, BasicAuthHandler, OAuthHandler

        auth_handler: AuthHandler
        if config.auth_type == AuthType.OAUTH:
            auth_handler = OAuthHandler(
                token_url=config.token_url or "",
                client_id=config.client_id or "",
                client_secret=config.client_secret or "",
            )
        elif config.auth_type == AuthType.API_KEY:
            auth_handler = ApiKeyAuthHandler(config.api_key or "", config.api_key_header_name)
        else:
            auth_handler = BasicAuthHandler(config.username or "", config.password or "")

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
        except Exception as e:
            logging.warning(f"Failed to detect OData version, defaulting to V2: {e}")
            return ODataVersion.V2

    def run(self) -> None:
        logging.info("Starting SAP OData extraction")

        if not self._config.entity_set:
            logging.warning("No entity_set configured, nothing to extract")
            return

        try:
            self._config.validate_for_extraction()
        except ValueError as e:
            raise UserException(f"Configuration validation failed: {e}") from e

        state = self._load_state()

        try:
            self._extract_entity(state)
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
        entity_state = state.get_entity_state(self._config.entity_set or "")

        filter_expr = self._build_filter_expression(entity_state)
        table_def = self._create_output_table()

        records_count, last_incremental_value = self._process_records(client, table_def, filter_expr)

        if records_count > 0:
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

    def _create_output_table(self):
        """Create output table definition."""
        output_table_name = self._config.get_output_table_name()
        return self.create_out_table_definition(
            f"{output_table_name}.csv",
            primary_key=self._config.primary_key if self._config.primary_key else None,
            incremental=self._config.load_type == LoadType.INCREMENTAL,
        )

    def _process_records(
        self, client: ODataClient, table_def, filter_expr: str | None
    ) -> tuple[int, str | None]:
        """Process and write records from OData service.

        Returns:
            Tuple of (records_count, last_incremental_value)
        """
        records_count = 0
        last_incremental_value: str | None = None
        writer: ElasticDictWriter | None = None

        try:
            max_records = self._config.max_records if self._config.max_records > 0 else None

            for record in client.fetch_with_pagination(
                entity_set=self._config.entity_set or "",
                select=self._config.select_fields if self._config.select_fields else None,
                filter_expr=filter_expr,
                expand=self._config.expand_properties if self._config.expand_properties else None,
                page_size=self._config.page_size,
                max_records=max_records,
            ):
                if writer is None:
                    columns = list(record.keys())
                    writer = ElasticDictWriter(table_def.full_path, columns)
                    writer.writeheader()

                flat_record = self._flatten_record(record)
                writer.writerow(flat_record)
                records_count += 1

                last_incremental_value = self._track_incremental_value(flat_record, last_incremental_value)

                if records_count % 10000 == 0:
                    logging.info(f"Extracted {records_count} records from {self._config.entity_set}")

        finally:
            if writer is not None:
                writer.close()

        return records_count, last_incremental_value

    def _track_incremental_value(self, record: JsonDict, current_max: str | None) -> str | None:
        """Track the maximum incremental value from records."""
        if not self._config.incremental_field or self._config.incremental_field not in record:
            return current_max

        value = record[self._config.incremental_field]
        if value and (current_max is None or str(value) > current_max):
            return str(value)

        return current_max

    def _update_extraction_state(
        self, state: ComponentState, records_count: int, last_incremental_value: str | None
    ) -> None:
        """Update component state with extraction results."""
        state.update_entity_state(
            entity_set=self._config.entity_set or "",
            last_sync_timestamp=datetime.now(UTC).isoformat(),
            last_incremental_value=last_incremental_value,
            records_synced=records_count,
        )

    def _flatten_record(
        self, record: JsonDict, prefix: str = ""
    ) -> JsonDict:
        """Flatten nested record structure."""
        flat: JsonDict = {}
        for key, value in record.items():
            full_key = f"{prefix}_{key}" if prefix else key
            if isinstance(value, dict):
                flat.update(self._flatten_record(value, full_key))
            elif isinstance(value, list):
                flat[full_key] = str(value)
            else:
                flat[full_key] = value  # type: ignore[assignment]
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
        """Test connection to SAP OData service."""
        try:
            client = self._build_client()
            ok, message = client.test_connection()
            if ok:
                return {"status": "success", "message": message}
            return {"status": "error", "message": message}
        except Exception as e:
            return {"status": "error", "message": f"Connection failed: {e}"}

    @sync_action("loadEntities")
    def load_entities(self) -> list[dict[str, str]]:
        try:
            # Check required fields
            if not self._config.base_url:
                logging.error("loadEntities: base_url is not set")
                return [
                    {
                        "value": "",
                        "label": "⚠️ Error: Base URL not configured. Please check root configuration.",
                    }
                ]
            if not self._config.service_path:
                logging.error("loadEntities: service_path is not set")
                return [
                    {
                        "value": "",
                        "label": "⚠️ Error: Service Path is required. Please fill it in above.",
                    }
                ]

            logging.info(
                f"loadEntities called - base_url: {self._config.base_url}, "
                f"service_path: {self._config.service_path}"
            )
            client = self._build_client()
            entities = client.list_entity_sets()
            logging.info(f"loadEntities: found {len(entities)} entity sets")

            if not entities:
                return [{"value": "", "label": "No entity sets found in service metadata"}]

            return [{"value": e.name, "label": e.name} for e in entities]
        except UserException as e:
            # User-facing errors (auth, connection, etc.)
            logging.error(f"Failed to load entities: {e}")
            return [{"value": "", "label": f"⚠️ Error: {e}"}]
        except Exception as e:
            # Unexpected errors
            logging.error(f"Failed to load entities: {e}", exc_info=True)
            return [
                {
                    "value": "",
                    "label": f"⚠️ Error loading entity sets. Check logs for details.",
                }
            ]

    @sync_action("loadFields")
    def load_fields(self) -> list[dict[str, str]]:
        try:
            logging.info(f"loadFields called with entity_set: {self._config.entity_set}")
            if not self._config.entity_set:
                logging.warning("loadFields: entity_set is not set")
                return []

            client = self._build_client()
            logging.info(f"loadFields: fetching fields for {self._config.entity_set}")
            fields = client.list_fields(self._config.entity_set)
            logging.info(f"loadFields: found {len(fields)} fields")
            return [{"value": f.name, "label": f"{f.name} ({f.edm_type})"} for f in fields]
        except Exception as e:
            logging.error(f"Failed to load fields for entity_set '{self._config.entity_set}': {e}", exc_info=True)
            return []

    @sync_action("loadPossiblePrimaryKeys")
    def load_possible_primary_keys(self) -> list[dict[str, str]]:
        try:
            logging.info(f"loadPossiblePrimaryKeys called with entity_set: {self._config.entity_set}")
            if not self._config.entity_set:
                logging.warning("loadPossiblePrimaryKeys: entity_set is not set")
                return []

            client = self._build_client()
            metadata = client.get_metadata()
            entity = metadata.get_entity_set(self._config.entity_set)
            if entity is None:
                logging.warning(f"loadPossiblePrimaryKeys: entity set '{self._config.entity_set}' not found in metadata")
                return []

            logging.info(f"loadPossiblePrimaryKeys: found {len(entity.key_properties)} key properties")
            return [{"value": k, "label": f"{k} (Key)"} for k in entity.key_properties]
        except Exception as e:
            logging.error(f"Failed to load primary keys for entity_set '{self._config.entity_set}': {e}", exc_info=True)
            return []

    @sync_action("loadIncrementalFields")
    def load_incremental_fields(self) -> list[dict[str, str]]:
        try:
            if not self._config.entity_set:
                return []

            client = self._build_client()
            fields = client.list_fields(self._config.entity_set)

            datetime_types = {"Edm.DateTime", "Edm.DateTimeOffset"}
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
        except Exception as e:
            logging.error(f"Failed to load incremental fields: {e}")
            return []

    @sync_action("loadNavigationProperties")
    def load_navigation_properties(self) -> list[dict[str, str]]:
        try:
            logging.info(f"loadNavigationProperties called with entity_set: {self._config.entity_set}")
            if not self._config.entity_set:
                logging.warning("loadNavigationProperties: entity_set is not set")
                return []

            client = self._build_client()
            metadata = client.get_metadata()
            logging.info(f"loadNavigationProperties: fetching entity set {self._config.entity_set}")
            entity = metadata.get_entity_set(self._config.entity_set)
            if entity is None:
                logging.warning(f"loadNavigationProperties: entity set '{self._config.entity_set}' not found in metadata")
                return []

            logging.info(f"loadNavigationProperties: found {len(entity.navigation_properties)} navigation properties")
            return [
                {"value": np.name, "label": f"{np.name} -> {np.target_entity}"} for np in entity.navigation_properties
            ]
        except Exception as e:
            logging.error(f"Failed to load navigation properties for entity_set '{self._config.entity_set}': {e}", exc_info=True)
            return []

    @sync_action("previewData")
    def preview_data(self) -> JsonDict:
        """Preview first 10 records from entity set."""
        try:
            if not self._config.entity_set:
                return {"status": "error", "message": "No entity set selected"}

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
        except Exception as e:
            return {"status": "error", "message": f"Preview failed: {e}"}

    @sync_action("validateFilter")
    def validate_filter(self) -> dict[str, str]:
        """Validate OData filter expression."""
        try:
            if not self._config.entity_set:
                return {"status": "error", "message": "No entity set selected"}
            if not self._config.filter_expression:
                return {"status": "success", "message": "No filter to validate"}

            client = self._build_client()
            list(
                client.fetch_entity_set(
                    entity_set=self._config.entity_set,
                    filter_expr=self._config.filter_expression,
                    top=1,
                )
            )

            return {"status": "success", "message": "Filter expression is valid"}
        except Exception as e:
            return {"status": "error", "message": f"Invalid filter: {e}"}

    @sync_action("loadMetadataSummary")
    def load_metadata_summary(
        self,
    ) -> JsonDict:
        """Load metadata summary for the OData service."""
        try:
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
        except Exception as e:
            return {"status": "error", "message": f"Failed to load metadata: {e}"}


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

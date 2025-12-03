import logging
from datetime import UTC, datetime
from typing import Any

from keboola.component.base import ComponentBase, sync_action
from keboola.component.dao import OauthCredentials
from keboola.component.exceptions import UserException
from keboola.csvwriter import ElasticDictWriter

from configuration import (
    AuthType,
    ComponentState,
    Configuration,
    ODataVersionChoice,
    RowConfiguration,
    SyncType,
)
from odata_client.base_client import ODataClientBase
from odata_client.metadata import MetadataParser, ODataVersion
from odata_client.v2_client import ODataV2Client
from odata_client.v4_client import ODataV4Client


class Component(ComponentBase):
    def __init__(self):
        super().__init__()
        self._client: ODataClientBase | None = None
        self._detected_version: ODataVersion | None = None

    @property
    def config(self) -> Configuration:
        return Configuration(**self.configuration.parameters)

    def _build_client(self) -> ODataClientBase:
        if self._client is not None:
            return self._client

        config = self.config
        version = self._detect_or_get_version(config)

        client_class = ODataV4Client if version == ODataVersion.V4 else ODataV2Client

        if config.auth_type == AuthType.OAUTH:
            oauth: OauthCredentials = self.configuration.oauth_credentials
            self._client = client_class.from_oauth(
                oauth=oauth,
                base_url=config.service_url,
                timeout=config.timeout,
                max_retries=config.max_retries,
                verify_ssl=config.verify_ssl,
            )
        else:
            self._client = client_class.from_basic_auth(
                username=config.username or "",
                password=config.password or "",
                base_url=config.service_url,
                timeout=config.timeout,
                max_retries=config.max_retries,
                verify_ssl=config.verify_ssl,
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
        import requests

        from odata_client.auth import BasicAuthHandler, OAuthHandler

        if config.auth_type == AuthType.OAUTH:
            oauth: OauthCredentials = self.configuration.oauth_credentials
            auth_handler = OAuthHandler(oauth)
        else:
            auth_handler = BasicAuthHandler(config.username or "", config.password or "")

        metadata_url = f"{config.service_url.rstrip('/')}/$metadata"
        headers = auth_handler.get_auth_headers()
        headers["Accept"] = "application/xml"

        try:
            response = requests.get(
                metadata_url,
                headers=headers,
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

        state = self._load_state()

        row_configs = self._get_row_configurations()
        if not row_configs:
            logging.warning("No row configurations found, nothing to extract")
            return

        for row_config in row_configs:
            try:
                self._extract_entity(row_config, state)
            except Exception as e:
                logging.error(f"Failed to extract entity {row_config.entity_set}: {e}")
                raise UserException(f"Failed to extract entity {row_config.entity_set}: {e}") from e

        self._save_state(state)
        logging.info("SAP OData extraction completed")

    def _get_row_configurations(self) -> list[RowConfiguration]:
        rows = self.configuration.parameters.get("rows", [])
        if not rows:
            if "entity_set" in self.configuration.parameters:
                return [RowConfiguration(**self.configuration.parameters)]
            return []

        return [RowConfiguration(**row) for row in rows]

    def _extract_entity(self, row_config: RowConfiguration, state: ComponentState) -> None:
        logging.info(f"Extracting entity: {row_config.entity_set}")

        client = self._build_client()
        entity_state = state.get_entity_state(row_config.entity_set)

        filter_expr = row_config.filter_expression
        if (
            row_config.sync_type == SyncType.INCREMENTAL
            and row_config.incremental_field
            and entity_state.last_incremental_value
        ):
            incremental_filter = f"{row_config.incremental_field} gt '{entity_state.last_incremental_value}'"
            filter_expr = f"({filter_expr}) and ({incremental_filter})" if filter_expr else incremental_filter

        output_table_name = row_config.get_output_table_name()
        table_def = self.create_out_table_definition(
            f"{output_table_name}.csv",
            primary_key=row_config.primary_key if row_config.primary_key else None,
            incremental=row_config.sync_type == SyncType.INCREMENTAL,
        )

        records_count = 0
        last_incremental_value = entity_state.last_incremental_value
        writer: ElasticDictWriter | None = None

        try:
            max_records = row_config.max_records if row_config.max_records > 0 else None

            for record in client.fetch_with_pagination(
                entity_set=row_config.entity_set,
                select=row_config.select_fields if row_config.select_fields else None,
                filter_expr=filter_expr,
                expand=row_config.expand_properties if row_config.expand_properties else None,
                order_by=row_config.order_by,
                page_size=row_config.page_size,
                max_records=max_records,
            ):
                if writer is None:
                    columns = list(record.keys())
                    writer = ElasticDictWriter(table_def.full_path, columns)

                flat_record = self._flatten_record(record)
                writer.writerow(flat_record)
                records_count += 1

                if row_config.incremental_field and row_config.incremental_field in flat_record:
                    value = flat_record[row_config.incremental_field]
                    if value and (last_incremental_value is None or str(value) > str(last_incremental_value)):
                        last_incremental_value = str(value)

                if records_count % 10000 == 0:
                    logging.info(f"Extracted {records_count} records from {row_config.entity_set}")

        finally:
            if writer is not None:
                writer.writeheader()
                writer.close()

        if records_count > 0:
            self.write_manifest(table_def)

        state.update_entity_state(
            entity_set=row_config.entity_set,
            last_sync_timestamp=datetime.now(UTC).isoformat(),
            last_incremental_value=last_incremental_value,
            records_synced=records_count,
        )

        logging.info(f"Extracted {records_count} records from {row_config.entity_set}")

    def _flatten_record(self, record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        flat = {}
        for key, value in record.items():
            full_key = f"{prefix}_{key}" if prefix else key
            if isinstance(value, dict):
                flat.update(self._flatten_record(value, full_key))
            elif isinstance(value, list):
                flat[full_key] = str(value)
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
    def test_connection(self) -> dict[str, Any]:
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
            client = self._build_client()
            entities = client.list_entity_sets()
            return [{"value": e.name, "label": e.name} for e in entities]
        except Exception as e:
            logging.error(f"Failed to load entities: {e}")
            return []

    @sync_action("loadFields")
    def load_fields(self) -> list[dict[str, str]]:
        try:
            entity_set = self.configuration.parameters.get("entity_set")
            if not entity_set:
                return []

            client = self._build_client()
            fields = client.list_fields(entity_set)
            return [{"value": f.name, "label": f"{f.name} ({f.edm_type})"} for f in fields]
        except Exception as e:
            logging.error(f"Failed to load fields: {e}")
            return []

    @sync_action("loadPossiblePrimaryKeys")
    def load_possible_primary_keys(self) -> list[dict[str, str]]:
        try:
            entity_set = self.configuration.parameters.get("entity_set")
            if not entity_set:
                return []

            client = self._build_client()
            metadata = client.get_metadata()
            entity = metadata.get_entity_set(entity_set)
            if entity is None:
                return []

            return [{"value": k, "label": f"{k} (Key)"} for k in entity.key_properties]
        except Exception as e:
            logging.error(f"Failed to load primary keys: {e}")
            return []

    @sync_action("loadIncrementalFields")
    def load_incremental_fields(self) -> list[dict[str, str]]:
        try:
            entity_set = self.configuration.parameters.get("entity_set")
            if not entity_set:
                return []

            client = self._build_client()
            fields = client.list_fields(entity_set)

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
            entity_set = self.configuration.parameters.get("entity_set")
            if not entity_set:
                return []

            client = self._build_client()
            metadata = client.get_metadata()
            entity = metadata.get_entity_set(entity_set)
            if entity is None:
                return []

            return [
                {"value": np.name, "label": f"{np.name} -> {np.target_entity}"} for np in entity.navigation_properties
            ]
        except Exception as e:
            logging.error(f"Failed to load navigation properties: {e}")
            return []

    @sync_action("previewData")
    def preview_data(self) -> dict[str, Any]:
        try:
            entity_set = self.configuration.parameters.get("entity_set")
            if not entity_set:
                return {"status": "error", "message": "No entity set selected"}

            client = self._build_client()
            select_fields = self.configuration.parameters.get("select_fields")
            filter_expr = self.configuration.parameters.get("filter_expression")
            expand_props = self.configuration.parameters.get("expand_properties")

            data = list(
                client.fetch_entity_set(
                    entity_set=entity_set,
                    select=select_fields if select_fields else None,
                    filter_expr=filter_expr,
                    expand=expand_props if expand_props else None,
                    top=10,
                )
            )

            return {
                "status": "success",
                "message": f"Loaded {len(data)} records",
                "data": data,
            }
        except Exception as e:
            return {"status": "error", "message": f"Preview failed: {e}"}

    @sync_action("validateFilter")
    def validate_filter(self) -> dict[str, Any]:
        try:
            entity_set = self.configuration.parameters.get("entity_set")
            filter_expr = self.configuration.parameters.get("filter_expression")

            if not entity_set:
                return {"status": "error", "message": "No entity set selected"}
            if not filter_expr:
                return {"status": "success", "message": "No filter to validate"}

            client = self._build_client()
            list(
                client.fetch_entity_set(
                    entity_set=entity_set,
                    filter_expr=filter_expr,
                    top=1,
                )
            )

            return {"status": "success", "message": "Filter expression is valid"}
        except Exception as e:
            return {"status": "error", "message": f"Invalid filter: {e}"}

    @sync_action("loadMetadataSummary")
    def load_metadata_summary(self) -> dict[str, Any]:
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

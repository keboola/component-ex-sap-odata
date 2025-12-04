from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuthType(str, Enum):
    BASIC = "basic"
    OAUTH = "oauth"
    API_KEY = "apiKey"


class ODataVersionChoice(str, Enum):
    AUTO = "auto"
    V2 = "v2"
    V4 = "v4"


class SyncType(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


class Configuration(BaseModel):
    """Configuration model that combines root config and row config fields.

    In Keboola row mode, root config (service_url, auth, etc.) and row config
    (entity_set, select_fields, etc.) are merged into a single parameters object.
    """

    # Root configuration fields (from configSchema.json)
    # URL Configuration - Option 1: Full service URL (legacy/backward compatible)
    service_url: str | None = Field(
        default=None,
        description="Full OData service URL (without entity set). Example: https://my-sap.com/sap/opu/odata/sap/API_BUSINESS_PARTNER",
    )
    # URL Configuration - Option 2: Split base URL + service path (recommended)
    base_url: str | None = Field(
        default=None,
        description="Base URL of SAP system. Example: https://my-sap-server.com or https://sandbox.api.sap.com/s4hanacloud",
    )
    service_path: str | None = Field(
        default=None,
        description="OData service path. For V2: API_BUSINESS_PARTNER. For V4: api_fixedassetacquisition/srvd_a2x/sap/fixedassetacquisition/0001",
    )

    odata_version: ODataVersionChoice = Field(
        default=ODataVersionChoice.AUTO, description="OData protocol version (auto, v2, v4)"
    )
    auth_type: AuthType = Field(default=AuthType.BASIC, description="Authentication type")
    username: str | None = Field(default=None, description="Username for basic authentication")
    password: str | None = Field(default=None, alias="#password", description="Password for basic authentication")
    api_key: str | None = Field(default=None, alias="#api_key", description="API key for API key authentication")
    api_key_header_name: str = Field(default="APIKey", description="HTTP header name for the API key")
    timeout: int = Field(default=60, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries for failed requests")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")

    # Row configuration fields (from configRowSchema.json)
    entity_set: str | None = Field(default=None, description="Name of the OData EntitySet to extract")
    output_table_name: str | None = Field(default=None, description="Name of the output table in Keboola Storage")
    select_fields: list[str] = Field(default_factory=list, description="Fields to select ($select)")
    filter_expression: str | None = Field(default=None, description="OData $filter expression")
    expand_properties: list[str] = Field(default_factory=list, description="Navigation properties to expand ($expand)")
    order_by: str | None = Field(default=None, description="Field for ordering ($orderby)")
    sync_type: SyncType = Field(default=SyncType.FULL, description="Sync type: full or incremental")
    incremental_field: str | None = Field(default=None, description="Field used for incremental sync")
    primary_key: list[str] = Field(default_factory=list, description="Primary key fields")
    page_size: int = Field(default=1000, description="Number of records per page")
    max_records: int = Field(default=0, description="Maximum records to fetch (0 = unlimited)")

    def model_post_init(self, __context: Any) -> None:
        # Validate URL configuration - exactly one method must be used
        has_service_url = self.service_url is not None
        has_split_url = self.base_url is not None and self.service_path is not None

        if not has_service_url and not has_split_url:
            raise ValueError(
                "Either 'service_url' or both 'base_url' and 'service_path' must be provided. "
                "Use 'service_url' for full URL or 'base_url'+'service_path' for split configuration."
            )

        if has_service_url and has_split_url:
            raise ValueError(
                "Cannot use both 'service_url' and 'base_url'+'service_path'. "
                "Choose one URL configuration method."
            )

        if self.base_url is not None and self.service_path is None:
            raise ValueError("'service_path' is required when 'base_url' is provided")

        if self.service_path is not None and self.base_url is None:
            raise ValueError("'base_url' is required when 'service_path' is provided")

        # Validate authentication
        if self.auth_type == AuthType.BASIC:
            if not self.username:
                raise ValueError("Username is required for basic authentication")
            if not self.password:
                raise ValueError("Password is required for basic authentication")
        elif self.auth_type == AuthType.API_KEY:
            if not self.api_key:
                raise ValueError("API key is required for API key authentication")

    def get_service_url(self, detected_version: ODataVersionChoice | None = None) -> str:
        """Get the full OData service URL.

        If service_url is provided, returns it directly.
        If base_url + service_path are provided, constructs the URL with the appropriate gateway path.

        Args:
            detected_version: The detected OData version (used when odata_version is AUTO).
                            If not provided and version is AUTO, attempts to infer from service_path structure.

        Returns:
            Full OData service URL without entity set.
        """
        if self.service_url:
            return self.service_url

        # Construct URL from base_url + service_path
        if not self.base_url or not self.service_path:
            raise ValueError("Either service_url or both base_url and service_path must be provided")

        base = self.base_url.rstrip("/")  # Remove trailing slash if present

        # Determine which OData version to use for gateway path
        version = self.odata_version
        if version == ODataVersionChoice.AUTO:
            if detected_version:
                version = detected_version
            else:
                # Try to infer from service_path structure
                # V4 paths typically have multiple components (e.g., "api_name/srvd_a2x/sap/service/0001")
                # V2 paths are usually simple service names (e.g., "API_BUSINESS_PARTNER")
                if self.service_path.count("/") >= 2:
                    version = ODataVersionChoice.V4
                else:
                    version = ODataVersionChoice.V2

        # Add appropriate gateway path
        if version == ODataVersionChoice.V2:
            gateway_path = "/sap/opu/odata/sap"
        else:  # V4
            gateway_path = "/sap/opu/odata4/sap"

        service_path = self.service_path.lstrip("/")  # Remove leading slash if present
        return f"{base}{gateway_path}/{service_path}"

    def get_output_table_name(self) -> str:
        return self.output_table_name or self.entity_set or "output"


class StateEntry(BaseModel):
    last_sync_timestamp: str | None = None
    last_incremental_value: str | None = None
    records_synced: int = 0


class ComponentState(BaseModel):
    entity_states: dict[str, StateEntry] = Field(default_factory=dict)

    def get_entity_state(self, entity_set: str) -> StateEntry:
        if entity_set not in self.entity_states:
            self.entity_states[entity_set] = StateEntry()
        return self.entity_states[entity_set]

    def update_entity_state(
        self,
        entity_set: str,
        last_sync_timestamp: str | None = None,
        last_incremental_value: str | None = None,
        records_synced: int = 0,
    ) -> None:
        state = self.get_entity_state(entity_set)
        if last_sync_timestamp:
            state.last_sync_timestamp = last_sync_timestamp
        if last_incremental_value:
            state.last_incremental_value = last_incremental_value
        state.records_synced = records_synced

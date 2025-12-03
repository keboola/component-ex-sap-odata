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
    service_url: str = Field(description="Base URL of the OData service")
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
        if self.auth_type == AuthType.BASIC:
            if not self.username:
                raise ValueError("Username is required for basic authentication")
            if not self.password:
                raise ValueError("Password is required for basic authentication")
        elif self.auth_type == AuthType.API_KEY:
            if not self.api_key:
                raise ValueError("API key is required for API key authentication")

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

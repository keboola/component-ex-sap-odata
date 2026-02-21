from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AuthType(str, Enum):
    BASIC = "basic"
    OAUTH = "oauth"
    API_KEY = "apiKey"


class ODataVersionChoice(str, Enum):
    AUTO = "auto"
    V2 = "v2"
    V4 = "v4"


class LoadType(str, Enum):
    """How data is written to Keboola Storage."""
    FULL = "full"
    INCREMENTAL = "incremental"


class FetchType(str, Enum):
    """How data is fetched from SAP OData API."""
    FULL = "full"
    INCREMENTAL = "incremental"


# Nested models matching config schema structure


class Connection(BaseModel):
    """Connection settings from root config."""
    base_url: str | None = Field(default=None, description="Base URL of SAP system")
    catalog_path: str | None = Field(default=None, description="SAP Service Catalog path")


class Authentication(BaseModel):
    """Authentication settings from root config."""
    auth_type: AuthType = Field(default=AuthType.BASIC, description="Authentication type")
    username: str | None = Field(default=None, description="Username for basic authentication")
    password: str | None = Field(default=None, alias="#password", description="Password for basic authentication")
    api_key: str | None = Field(default=None, alias="#api_key", description="API key for API key authentication")
    api_key_header_name: str = Field(default="APIKey", description="HTTP header name for the API key")
    token_url: str | None = Field(default=None, description="OAuth 2.0 token endpoint URL")
    client_id: str | None = Field(default=None, description="OAuth 2.0 client ID")
    client_secret: str | None = Field(default=None, alias="#client_secret", description="OAuth 2.0 client secret")


class ConnectionOptions(BaseModel):
    """Advanced connection options."""
    timeout: int = Field(default=60, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries for failed requests")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")
    enable_parallel: bool = Field(default=True, description="Enable parallel page fetching")
    parallel_pages: int = Field(default=5, description="Number of pages to fetch in parallel")
    max_requests_per_second: float | None = Field(default=None, description="Maximum requests per second")


class PaginationDefaults(BaseModel):
    """Default pagination settings."""
    page_size: int = Field(default=1000, description="Number of records per page")
    max_records: int = Field(default=0, description="Maximum records to fetch (0 = unlimited)")


class RootAdvancedOptions(BaseModel):
    """Advanced options from root config."""
    model_config = ConfigDict(extra="forbid")
    connection_options: list[ConnectionOptions] = Field(default_factory=list, description="Connection options")
    pagination_defaults: list[PaginationDefaults] = Field(default_factory=list, description="Pagination defaults")


class QueryOptions(BaseModel):
    """OData query options from row config."""
    select_fields: list[str] = Field(default_factory=list, description="Fields to select ($select)")
    filter_expression: str | None = Field(default=None, description="OData $filter expression")
    expand_properties: list[str] = Field(default_factory=list, description="Navigation properties to expand")

    @field_validator("filter_expression")
    @classmethod
    def validate_filter_expression(cls, v: str | None) -> str | None:
        """Remove quotes around dates for OData V4."""
        if not v:
            return v

        import re
        pattern = r"(?<!datetime)'(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z)?)?)'"
        fixed = re.sub(pattern, r'\1', v)

        if fixed != v:
            import logging
            logging.warning(f"Filter expression auto-fixed: {v} -> {fixed}")

        return fixed


class FetchingOptions(BaseModel):
    """Fetching options from row config."""
    fetch_type: FetchType = Field(default=FetchType.FULL, description="How data is fetched")
    incremental_field: str | None = Field(default=None, description="Field used for incremental fetch")


class Destination(BaseModel):
    """Destination configuration from row config."""
    output_table_name: str | None = Field(default=None, description="Output table name")
    load_type: LoadType = Field(default=LoadType.FULL, description="How data is written to Storage")
    primary_key: list[str] = Field(default_factory=list, description="Primary key fields")


class RowAdvancedOptions(BaseModel):
    """Advanced entity options from row config."""
    model_config = ConfigDict(extra="forbid")
    page_size: int | None = Field(default=None, description="Override page size for this entity")
    max_records: int | None = Field(default=None, description="Override max records for this entity")


class Configuration(BaseModel):
    """Configuration exactly as received from Keboola UI.

    Root config fields (nested):
    - connection: Connection settings
    - authentication: Authentication settings
    - advanced_options: Root advanced options (conflicts with row!)

    Row config fields (top-level + nested):
    - odata_version, service_path, entity_set: top-level strings
    - query_options, fetching_options, destination: nested objects
    - advanced_options: array (conflicts with root!)
    """

    # Root config - nested blocks
    connection: Connection | None = Field(default=None, description="Connection settings")
    authentication: Authentication | None = Field(default=None, description="Authentication settings")

    # Row config - top-level fields
    odata_version: ODataVersionChoice = Field(default=ODataVersionChoice.AUTO, description="OData version")
    service_path: str | None = Field(default=None, description="OData service path")
    entity_set: str | None = Field(default=None, description="Entity set name")

    # Row config - nested blocks
    query_options: QueryOptions | None = Field(default=None, description="Query options")
    fetching_options: FetchingOptions | None = Field(default=None, description="Fetching options")
    destination: Destination | None = Field(default=None, description="Destination configuration")

    # Advanced options - can be root (dict) or row (array → converted to single dict by validator)
    # RootAdvancedOptions and RowAdvancedOptions use extra="forbid" so Pydantic can distinguish them
    advanced_options: RootAdvancedOptions | RowAdvancedOptions | None = Field(
        default=None, description="Advanced options"
    )

    @model_validator(mode="before")
    @classmethod
    def convert_arrays_to_objects(cls, data: Any) -> dict[str, Any]:
        """Convert array fields (maxItems: 1) to single objects.

        Keboola sends arrays for maxItems: 1, we convert to objects or None.
        """
        if not isinstance(data, dict):
            return data

        result = dict(data)

        # Convert advanced_options array to single object
        if "advanced_options" in result:
            adv = result["advanced_options"]
            if isinstance(adv, list):
                result["advanced_options"] = adv[0] if adv else None
            elif isinstance(adv, dict):
                # Check if it's root format (has connection_options/pagination_defaults)
                # or row format (has page_size/max_records)
                # Convert arrays inside root advanced_options
                if "connection_options" in adv:
                    conn_opts = adv["connection_options"]
                    if isinstance(conn_opts, list):
                        adv["connection_options"] = conn_opts if conn_opts else []
                if "pagination_defaults" in adv:
                    pag_def = adv["pagination_defaults"]
                    if isinstance(pag_def, list):
                        adv["pagination_defaults"] = pag_def if pag_def else []

        return result

    @field_validator("service_path", "entity_set", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Any:
        """Convert empty strings to None."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("entity_set")
    @classmethod
    def strip_entity_set(cls, v: str | None) -> str | None:
        """Strip whitespace from entity_set."""
        return v.strip() if v else v

    # Property accessors for convenient access
    @property
    def base_url(self) -> str | None:
        return self.connection.base_url if self.connection else None

    @property
    def catalog_path(self) -> str | None:
        return self.connection.catalog_path if self.connection else None

    @property
    def auth_type(self) -> AuthType:
        return self.authentication.auth_type if self.authentication else AuthType.BASIC

    @property
    def username(self) -> str | None:
        return self.authentication.username if self.authentication else None

    @property
    def password(self) -> str | None:
        return self.authentication.password if self.authentication else None

    @property
    def api_key(self) -> str | None:
        return self.authentication.api_key if self.authentication else None

    @property
    def api_key_header_name(self) -> str:
        return self.authentication.api_key_header_name if self.authentication else "APIKey"

    @property
    def token_url(self) -> str | None:
        return self.authentication.token_url if self.authentication else None

    @property
    def client_id(self) -> str | None:
        return self.authentication.client_id if self.authentication else None

    @property
    def client_secret(self) -> str | None:
        return self.authentication.client_secret if self.authentication else None

    @property
    def timeout(self) -> int:
        if isinstance(self.advanced_options, RootAdvancedOptions):
            if self.advanced_options.connection_options:
                return self.advanced_options.connection_options[0].timeout
        return 60

    @property
    def max_retries(self) -> int:
        if isinstance(self.advanced_options, RootAdvancedOptions):
            if self.advanced_options.connection_options:
                return self.advanced_options.connection_options[0].max_retries
        return 3

    @property
    def verify_ssl(self) -> bool:
        if isinstance(self.advanced_options, RootAdvancedOptions):
            if self.advanced_options.connection_options:
                return self.advanced_options.connection_options[0].verify_ssl
        return True

    @property
    def enable_parallel(self) -> bool:
        if isinstance(self.advanced_options, RootAdvancedOptions):
            if self.advanced_options.connection_options:
                return self.advanced_options.connection_options[0].enable_parallel
        return True

    @property
    def parallel_pages(self) -> int:
        if isinstance(self.advanced_options, RootAdvancedOptions):
            if self.advanced_options.connection_options:
                return self.advanced_options.connection_options[0].parallel_pages
        return 5

    @property
    def max_requests_per_second(self) -> float | None:
        if isinstance(self.advanced_options, RootAdvancedOptions):
            if self.advanced_options.connection_options:
                return self.advanced_options.connection_options[0].max_requests_per_second
        return None

    @property
    def page_size(self) -> int:
        # Row advanced_options takes precedence
        if isinstance(self.advanced_options, RowAdvancedOptions):
            if self.advanced_options.page_size is not None:
                return self.advanced_options.page_size
        # Then root pagination_defaults
        if isinstance(self.advanced_options, RootAdvancedOptions):
            if self.advanced_options.pagination_defaults:
                return self.advanced_options.pagination_defaults[0].page_size
        return 1000

    @property
    def max_records(self) -> int:
        # Row advanced_options takes precedence
        if isinstance(self.advanced_options, RowAdvancedOptions):
            if self.advanced_options.max_records is not None:
                return self.advanced_options.max_records
        # Then root pagination_defaults
        if isinstance(self.advanced_options, RootAdvancedOptions):
            if self.advanced_options.pagination_defaults:
                return self.advanced_options.pagination_defaults[0].max_records
        return 0

    @property
    def select_fields(self) -> list[str]:
        return self.query_options.select_fields if self.query_options else []

    @property
    def filter_expression(self) -> str | None:
        return self.query_options.filter_expression if self.query_options else None

    @property
    def expand_properties(self) -> list[str]:
        return self.query_options.expand_properties if self.query_options else []

    @property
    def fetch_type(self) -> FetchType:
        return self.fetching_options.fetch_type if self.fetching_options else FetchType.FULL

    @property
    def incremental_field(self) -> str | None:
        return self.fetching_options.incremental_field if self.fetching_options else None

    @property
    def output_table_name(self) -> str | None:
        return self.destination.output_table_name if self.destination else None

    @property
    def load_type(self) -> LoadType:
        return self.destination.load_type if self.destination else LoadType.FULL

    @property
    def primary_key(self) -> list[str]:
        return self.destination.primary_key if self.destination else []

    def model_post_init(self, __context: Any) -> None:
        """Validate authentication after initialization."""
        if not self.authentication:
            raise ValueError("Authentication configuration is required")

        if self.authentication.auth_type == AuthType.BASIC:
            if not self.authentication.username:
                raise ValueError("Username is required for basic authentication")
            if not self.authentication.password:
                raise ValueError("Password is required for basic authentication")
        elif self.authentication.auth_type == AuthType.API_KEY:
            if not self.authentication.api_key:
                raise ValueError("API key is required for API key authentication")
        elif self.authentication.auth_type == AuthType.OAUTH:
            if not self.authentication.token_url:
                raise ValueError("Token URL is required for OAuth authentication")
            if not self.authentication.client_id:
                raise ValueError("Client ID is required for OAuth authentication")
            if not self.authentication.client_secret:
                raise ValueError("Client Secret is required for OAuth authentication")

    def validate_for_extraction(self) -> None:
        """Validate configuration before data extraction."""
        # URL validation
        if not self.base_url and not self.service_path:
            raise ValueError("Either base_url or service_path is required for data extraction")

        if self.fetch_type == FetchType.INCREMENTAL and not self.incremental_field:
            raise ValueError("'incremental_field' is required when fetch_type is 'incremental'")

        if self.load_type == LoadType.INCREMENTAL and not self.primary_key:
            raise ValueError("'primary_key' is required when load_type is 'incremental'")

    def get_catalog_url(self) -> str:
        """Get the full catalog URL (base_url + catalog_path)."""
        if not self.base_url:
            raise ValueError("base_url is required")
        if not self.catalog_path:
            raise ValueError("catalog_path is required")

        base = self.base_url.rstrip("/")
        catalog = self.catalog_path.lstrip("/")
        return f"{base}/{catalog}"

    def get_service_url(self, detected_version: ODataVersionChoice | None = None) -> str:
        """Get the full OData service URL."""
        if not self.base_url:
            raise ValueError("base_url is required")

        base = self.base_url.rstrip("/")

        # Priority 1: service_path
        if self.service_path:
            return f"{base}/{self.service_path.lstrip('/')}"

        # Priority 2: catalog_path
        if self.catalog_path:
            return f"{base}/{self.catalog_path.lstrip('/')}"

        # Priority 3: just base_url (for tests/simple setups where base_url is complete)
        return base

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

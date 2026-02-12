from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


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


class ConnectionOptions(BaseModel):
    """Advanced connection options."""
    timeout: int = Field(default=60, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries for failed requests")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")
    enable_parallel: bool = Field(default=True, description="Enable parallel page fetching for better performance")
    parallel_pages: int = Field(default=5, description="Number of pages to fetch in parallel (when enabled)")
    max_requests_per_second: float | None = Field(
        default=None, description="Maximum requests per second (rate limiting)"
    )


class PaginationDefaults(BaseModel):
    """Default pagination settings."""
    page_size: int = Field(default=1000, description="Number of records per page")
    max_records: int = Field(default=0, description="Maximum records to fetch (0 = unlimited)")


class QueryOptions(BaseModel):
    """OData query options."""
    select_fields: list[str] = Field(default_factory=list, description="Fields to select ($select)")
    filter_expression: str | None = Field(default=None, description="OData $filter expression")
    expand_properties: list[str] = Field(default_factory=list, description="Navigation properties to expand ($expand)")

    @field_validator("filter_expression")
    @classmethod
    def validate_filter_expression(cls, v: str | None) -> str | None:
        """Validate and fix common filter expression errors.

        For OData V4, removes quotes around date/datetime literals.
        Keeps OData V2 datetime'...' format intact.
        """
        if not v:
            return v

        import re

        # Remove quotes around ISO date formats for OData V4
        # Match patterns like '2024-01-01' or '2024-01-01T00:00:00Z'
        # but NOT datetime'2024-01-01T00:00:00' (OData V2 format)

        # Pattern for quoted dates: '2024-01-01' or '2024-01-01T00:00:00Z' or '2024-01-01T00:00:00'
        # NOT preceded by "datetime" (to preserve OData V2 format)
        pattern = r"(?<!datetime)'(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z)?)?)'"

        fixed = re.sub(pattern, r'\1', v)

        if fixed != v:
            import logging
            logging.warning(
                f"Filter expression contained quoted dates. Auto-fixed for OData V4 compatibility.\n"
                f"Original: {v}\n"
                f"Fixed: {fixed}\n"
                f"Note: For OData V4, use dates without quotes (e.g., 2024-01-01). "
                f"For OData V2, use datetime'2024-01-01T00:00:00' format."
            )

        return fixed


class FetchingOptions(BaseModel):
    """Fetching options for OData API."""
    fetch_type: FetchType = Field(default=FetchType.FULL, description="How data is fetched from SAP OData API")
    incremental_field: str | None = Field(default=None, description="Field used for incremental fetch")


class Destination(BaseModel):
    """Destination configuration for Keboola Storage."""
    output_table_name: str | None = Field(default=None, description="Name of the output table in Keboola Storage")
    load_type: LoadType = Field(default=LoadType.FULL, description="How data is written to Keboola Storage")
    primary_key: list[str] = Field(default_factory=list, description="Primary key fields for incremental load")


class AdvancedEntityOptions(BaseModel):
    """Advanced entity-specific options."""
    page_size: int | None = Field(default=None, description="Override page size for this entity")
    max_records: int | None = Field(default=None, description="Override max records for this entity")


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
    token_url: str | None = Field(default=None, description="OAuth 2.0 token endpoint URL")
    client_id: str | None = Field(default=None, description="OAuth 2.0 client ID")
    client_secret: str | None = Field(default=None, alias="#client_secret", description="OAuth 2.0 client secret")

    # Optional nested blocks (arrays with maxItems: 1)
    connection_options: list[ConnectionOptions] | None = Field(
        default=None, description="Advanced connection options"
    )
    pagination_defaults: list[PaginationDefaults] | None = Field(
        default=None, description="Default pagination settings"
    )

    # Row configuration fields (from configRowSchema.json)
    entity_set: str | None = Field(default=None, description="Name of the OData EntitySet to extract")

    # Nested object blocks
    query_options: QueryOptions | None = Field(default=None, description="OData query options")
    fetching_options: FetchingOptions | None = Field(default=None, description="Fetching options for OData API")
    destination: Destination | None = Field(default=None, description="Destination configuration for Keboola Storage")

    # Advanced entity options as optional nested block
    advanced_options: list[AdvancedEntityOptions] | None = Field(
        default=None, description="Advanced entity-specific options"
    )

    @field_validator("entity_set")
    @classmethod
    def strip_entity_set(cls, v: str | None) -> str | None:
        """Strip whitespace from entity_set to handle user input errors."""
        return v.strip() if v else v

    # Property accessors for backward-compatible field access
    @property
    def timeout(self) -> int:
        """Get timeout value from connection_options or default."""
        if self.connection_options:
            return self.connection_options[0].timeout
        return 60

    @property
    def max_retries(self) -> int:
        """Get max_retries value from connection_options or default."""
        if self.connection_options:
            return self.connection_options[0].max_retries
        return 3

    @property
    def verify_ssl(self) -> bool:
        """Get verify_ssl value from connection_options or default."""
        if self.connection_options:
            return self.connection_options[0].verify_ssl
        return True

    @property
    def enable_parallel(self) -> bool:
        """Get enable_parallel value from connection_options or default."""
        if self.connection_options:
            return self.connection_options[0].enable_parallel
        return True

    @property
    def parallel_pages(self) -> int:
        """Get parallel_pages value from connection_options or default."""
        if self.connection_options:
            return self.connection_options[0].parallel_pages
        return 5

    @property
    def max_requests_per_second(self) -> float | None:
        """Get max_requests_per_second value from connection_options or None."""
        if self.connection_options:
            return self.connection_options[0].max_requests_per_second
        return None

    @property
    def page_size(self) -> int:
        """Get page_size value from advanced_options, pagination_defaults, or default."""
        # Entity-specific override takes precedence
        if self.advanced_options and self.advanced_options[0].page_size is not None:
            return self.advanced_options[0].page_size
        # Then global default
        if self.pagination_defaults:
            return self.pagination_defaults[0].page_size
        return 1000

    @property
    def max_records(self) -> int:
        """Get max_records value from advanced_options, pagination_defaults, or default."""
        # Entity-specific override takes precedence
        if self.advanced_options and self.advanced_options[0].max_records is not None:
            return self.advanced_options[0].max_records
        # Then global default
        if self.pagination_defaults:
            return self.pagination_defaults[0].max_records
        return 0

    @property
    def select_fields(self) -> list[str]:
        """Get select_fields from query_options or empty list."""
        if self.query_options:
            return self.query_options.select_fields
        return []

    @property
    def filter_expression(self) -> str | None:
        """Get filter_expression from query_options or None."""
        if self.query_options:
            return self.query_options.filter_expression
        return None

    @property
    def expand_properties(self) -> list[str]:
        """Get expand_properties from query_options or empty list."""
        if self.query_options:
            return self.query_options.expand_properties
        return []

    @property
    def fetch_type(self) -> FetchType:
        """Get fetch_type from fetching_options or default."""
        if self.fetching_options:
            return self.fetching_options.fetch_type
        return FetchType.FULL

    @property
    def incremental_field(self) -> str | None:
        """Get incremental_field from fetching_options or None."""
        if self.fetching_options:
            return self.fetching_options.incremental_field
        return None

    @property
    def output_table_name(self) -> str | None:
        """Get output_table_name from destination or None."""
        if self.destination:
            return self.destination.output_table_name
        return None

    @property
    def load_type(self) -> LoadType:
        """Get load_type from destination or default."""
        if self.destination:
            return self.destination.load_type
        return LoadType.FULL

    @property
    def primary_key(self) -> list[str]:
        """Get primary_key from destination or empty list."""
        if self.destination:
            return self.destination.primary_key
        return []

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
        elif self.auth_type == AuthType.OAUTH:
            if not self.token_url:
                raise ValueError("Token URL is required for OAuth authentication")
            if not self.client_id:
                raise ValueError("Client ID is required for OAuth authentication")
            if not self.client_secret:
                raise ValueError("Client Secret is required for OAuth authentication")

        # Validate incremental configurations
        if self.fetch_type == FetchType.INCREMENTAL and not self.incremental_field:
            raise ValueError("'incremental_field' is required when fetch_type is 'incremental'")

        if self.load_type == LoadType.INCREMENTAL and not self.primary_key:
            raise ValueError("'primary_key' is required when load_type is 'incremental'")

    def get_service_url(self, detected_version: ODataVersionChoice | None = None) -> str:
        """Get the full OData service URL.

        If service_url is provided, returns it directly.
        If base_url + service_path are provided, constructs the URL by joining them.

        Args:
            detected_version: The detected OData version (unused, kept for backward compatibility).

        Returns:
            Full OData service URL without entity set.
        """
        if self.service_url:
            return self.service_url

        if not self.base_url or not self.service_path:
            raise ValueError("Either service_url or both base_url and service_path must be provided")

        base = self.base_url.rstrip("/")
        service_path = self.service_path.lstrip("/")

        return f"{base}/{service_path}"

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

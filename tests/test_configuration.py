import pytest

from configuration import (
    AuthType,
    ComponentState,
    Configuration,
    FetchType,
    LoadType,
    ODataVersionChoice,
    QueryOptions,
    StateEntry,
)


class TestConfiguration:
    def test_basic_configuration(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
        )

        assert config.service_url == "https://example.com/odata"
        assert config.auth_type == AuthType.BASIC
        assert config.username == "user"
        assert config.password == "pass"
        assert config.odata_version == ODataVersionChoice.AUTO
        assert config.timeout == 60
        assert config.max_retries == 3

    def test_oauth_configuration(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.OAUTH,
        )

        assert config.auth_type == AuthType.OAUTH
        assert config.username is None
        assert config.password is None

    def test_api_key_configuration(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.API_KEY,
            **{"#api_key": "my-secret-api-key"},
        )

        assert config.auth_type == AuthType.API_KEY
        assert config.api_key == "my-secret-api-key"
        assert config.api_key_header_name == "APIKey"

    def test_api_key_with_custom_header_name(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.API_KEY,
            api_key_header_name="X-API-Key",
            **{"#api_key": "my-secret-api-key"},
        )

        assert config.api_key == "my-secret-api-key"
        assert config.api_key_header_name == "X-API-Key"

    def test_api_key_auth_requires_api_key(self) -> None:
        with pytest.raises(ValueError, match="API key is required"):
            Configuration(
                service_url="https://example.com/odata",
                auth_type=AuthType.API_KEY,
            )

    def test_basic_auth_requires_username(self) -> None:
        with pytest.raises(ValueError, match="Username is required"):
            Configuration(
                service_url="https://example.com/odata",
                auth_type=AuthType.BASIC,
                password="pass",
            )

    def test_basic_auth_requires_password(self) -> None:
        with pytest.raises(ValueError, match="Password is required"):
            Configuration(
                service_url="https://example.com/odata",
                auth_type=AuthType.BASIC,
                username="user",
            )

    def test_custom_timeout_and_retries(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.BASIC,
            username="user",
            connection_options=[{"timeout": 120, "max_retries": 5, "verify_ssl": True}],
            **{"#password": "pass"},
        )

        assert config.timeout == 120
        assert config.max_retries == 5

    def test_odata_version_choices(self) -> None:
        for version in [ODataVersionChoice.AUTO, ODataVersionChoice.V2, ODataVersionChoice.V4]:
            config = Configuration(
                service_url="https://example.com/odata",
                auth_type=AuthType.BASIC,
                username="user",
                odata_version=version,
                **{"#password": "pass"},
            )
            assert config.odata_version == version


class TestConfigurationWithRowFields:
    """Tests for row configuration fields merged into Configuration."""

    def test_configuration_with_entity_set(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.BASIC,
            username="user",
            entity_set="Products",
            **{"#password": "pass"},
        )

        assert config.entity_set == "Products"
        assert config.output_table_name is None
        assert config.select_fields == []
        assert config.filter_expression is None
        assert config.load_type == LoadType.FULL
        assert config.fetch_type == FetchType.FULL
        assert config.page_size == 1000
        assert config.max_records == 0

    def test_full_configuration_with_row_fields(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.BASIC,
            username="user",
            entity_set="Products",
            query_options={
                "select_fields": ["ProductID", "ProductName"],
                "filter_expression": "IsActive eq true",
                "expand_properties": ["Category"],
            },
            fetching_options={
                "fetch_type": "incremental",
                "incremental_field": "ModifiedAt",
            },
            destination={
                "output_table_name": "my_products",
                "load_type": "incremental",
                "primary_key": ["ProductID"],
            },
            advanced_options=[{"page_size": 500, "max_records": 10000}],
            **{"#password": "pass"},
        )

        assert config.entity_set == "Products"
        assert config.output_table_name == "my_products"
        assert config.select_fields == ["ProductID", "ProductName"]
        assert config.filter_expression == "IsActive eq true"
        assert config.expand_properties == ["Category"]
        assert config.load_type == LoadType.INCREMENTAL
        assert config.fetch_type == FetchType.INCREMENTAL
        assert config.incremental_field == "ModifiedAt"
        assert config.primary_key == ["ProductID"]
        assert config.page_size == 500
        assert config.max_records == 10000

    def test_get_output_table_name_with_custom_name(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.BASIC,
            username="user",
            entity_set="Products",
            destination={"output_table_name": "custom_table"},
            **{"#password": "pass"},
        )
        assert config.get_output_table_name() == "custom_table"

    def test_get_output_table_name_default(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.BASIC,
            username="user",
            entity_set="Products",
            **{"#password": "pass"},
        )
        assert config.get_output_table_name() == "Products"

    def test_get_output_table_name_fallback(self) -> None:
        config = Configuration(
            service_url="https://example.com/odata",
            auth_type=AuthType.OAUTH,
        )
        assert config.get_output_table_name() == "output"


class TestStateEntry:
    def test_default_state_entry(self) -> None:
        entry = StateEntry()

        assert entry.last_sync_timestamp is None
        assert entry.last_incremental_value is None
        assert entry.records_synced == 0

    def test_state_entry_with_values(self) -> None:
        entry = StateEntry(
            last_sync_timestamp="2024-01-15T10:30:00Z",
            last_incremental_value="2024-01-15T10:30:00Z",
            records_synced=15000,
        )

        assert entry.last_sync_timestamp == "2024-01-15T10:30:00Z"
        assert entry.last_incremental_value == "2024-01-15T10:30:00Z"
        assert entry.records_synced == 15000


class TestComponentState:
    def test_empty_state(self) -> None:
        state = ComponentState()
        assert state.entity_states == {}

    def test_get_entity_state_creates_new(self) -> None:
        state = ComponentState()
        entry = state.get_entity_state("Products")

        assert entry is not None
        assert entry.last_sync_timestamp is None
        assert "Products" in state.entity_states

    def test_get_entity_state_returns_existing(self) -> None:
        state = ComponentState(
            entity_states={
                "Products": StateEntry(
                    last_sync_timestamp="2024-01-15T10:30:00Z",
                    records_synced=100,
                )
            }
        )

        entry = state.get_entity_state("Products")
        assert entry.last_sync_timestamp == "2024-01-15T10:30:00Z"
        assert entry.records_synced == 100

    def test_update_entity_state(self) -> None:
        state = ComponentState()
        state.update_entity_state(
            entity_set="Products",
            last_sync_timestamp="2024-01-15T10:30:00Z",
            last_incremental_value="2024-01-15T10:30:00Z",
            records_synced=500,
        )

        entry = state.get_entity_state("Products")
        assert entry.last_sync_timestamp == "2024-01-15T10:30:00Z"
        assert entry.last_incremental_value == "2024-01-15T10:30:00Z"
        assert entry.records_synced == 500

    def test_update_entity_state_partial(self) -> None:
        state = ComponentState()
        state.update_entity_state(
            entity_set="Products",
            last_sync_timestamp="2024-01-15T10:30:00Z",
            records_synced=100,
        )

        state.update_entity_state(
            entity_set="Products",
            records_synced=200,
        )

        entry = state.get_entity_state("Products")
        assert entry.last_sync_timestamp == "2024-01-15T10:30:00Z"
        assert entry.records_synced == 200


class TestURLConfiguration:
    """Tests for the new URL configuration options (service_url vs base_url+service_path)"""

    def test_legacy_service_url(self) -> None:
        """Test that legacy service_url still works"""
        config = Configuration(
            service_url="https://sap-server.com/sap/opu/odata/sap/API_BUSINESS_PARTNER",
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/sap/opu/odata/sap/API_BUSINESS_PARTNER"

    def test_split_url_v2(self) -> None:
        """Test split URL configuration for OData V2"""
        config = Configuration(
            base_url="https://sap-server.com",
            service_path="API_BUSINESS_PARTNER",
            odata_version=ODataVersionChoice.V2,
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/API_BUSINESS_PARTNER"

    def test_split_url_v4(self) -> None:
        """Test split URL configuration for OData V4"""
        config = Configuration(
            base_url="https://sap-server.com",
            service_path="api_fixedasset/srvd_a2x/sap/fixedasset/0001",
            odata_version=ODataVersionChoice.V4,
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/api_fixedasset/srvd_a2x/sap/fixedasset/0001"

    def test_split_url_auto_v2_inference(self) -> None:
        """Test that AUTO version uses simple path joining"""
        config = Configuration(
            base_url="https://sap-server.com",
            service_path="API_BUSINESS_PARTNER",
            odata_version=ODataVersionChoice.AUTO,
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/API_BUSINESS_PARTNER"

    def test_split_url_auto_v4_inference(self) -> None:
        """Test that AUTO version uses simple path joining"""
        config = Configuration(
            base_url="https://sap-server.com",
            service_path="api_fixedasset/srvd_a2x/sap/fixedasset/0001",
            odata_version=ODataVersionChoice.AUTO,
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/api_fixedasset/srvd_a2x/sap/fixedasset/0001"

    def test_split_url_with_trailing_slash(self) -> None:
        """Test that trailing/leading slashes are handled correctly"""
        config = Configuration(
            base_url="https://sap-server.com/",
            service_path="/API_BUSINESS_PARTNER",
            odata_version=ODataVersionChoice.V2,
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/API_BUSINESS_PARTNER"

    def test_neither_url_config_raises_error(self) -> None:
        """Test that providing neither URL configuration raises an error"""
        with pytest.raises(ValueError, match="Either 'service_url' or both 'base_url' and 'service_path'"):
            Configuration(
                auth_type=AuthType.BASIC,
                username="user",
                **{"#password": "pass"},
            )

    def test_both_url_configs_raises_error(self) -> None:
        """Test that providing both URL configurations raises an error"""
        with pytest.raises(ValueError, match="Cannot use both 'service_url' and 'base_url'"):
            Configuration(
                service_url="https://sap-server.com/sap/opu/odata/sap/API_BUSINESS_PARTNER",
                base_url="https://sap-server.com",
                service_path="API_BUSINESS_PARTNER",
                auth_type=AuthType.BASIC,
                username="user",
                **{"#password": "pass"},
            )

    def test_base_url_without_service_path_raises_error(self) -> None:
        """Test that base_url without service_path raises an error"""
        with pytest.raises(Exception, match="Either 'service_url' or both 'base_url' and 'service_path'"):
            Configuration(
                base_url="https://sap-server.com",
                auth_type=AuthType.BASIC,
                username="user",
                **{"#password": "pass"},
            )

    def test_service_path_without_base_url_raises_error(self) -> None:
        """Test that service_path without base_url raises an error"""
        with pytest.raises(Exception, match="Either 'service_url' or both 'base_url' and 'service_path'"):
            Configuration(
                service_path="API_BUSINESS_PARTNER",
                auth_type=AuthType.BASIC,
                username="user",
                **{"#password": "pass"},
            )


class TestFilterValidation:
    """Test filter expression validation"""

    def test_filter_with_quoted_date_v4_format(self) -> None:
        """Test that quoted dates are automatically fixed for OData V4"""
        config = Configuration(
            service_url="https://sap-server.com/odata/API_PARTNER",
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
            query_options=QueryOptions(filter_expression="DocumentDate gt '2024-01-01'"),
        )
        # Quotes should be removed
        assert config.filter_expression == "DocumentDate gt 2024-01-01"

    def test_filter_with_quoted_datetime_v4_format(self) -> None:
        """Test that quoted datetime values are fixed"""
        config = Configuration(
            service_url="https://sap-server.com/odata/API_PARTNER",
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
            query_options=QueryOptions(filter_expression="CreatedAt gt '2024-01-01T00:00:00Z'"),
        )
        assert config.filter_expression == "CreatedAt gt 2024-01-01T00:00:00Z"

    def test_filter_with_v2_datetime_format_preserved(self) -> None:
        """Test that OData V2 datetime'...' format is preserved"""
        config = Configuration(
            service_url="https://sap-server.com/odata/API_PARTNER",
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
            query_options=QueryOptions(filter_expression="CreatedAt gt datetime'2024-01-01T00:00:00'"),
        )
        # V2 format should NOT be changed
        assert config.filter_expression == "CreatedAt gt datetime'2024-01-01T00:00:00'"

    def test_filter_with_string_quotes_preserved(self) -> None:
        """Test that string values keep their quotes"""
        config = Configuration(
            service_url="https://sap-server.com/odata/API_PARTNER",
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
            query_options=QueryOptions(filter_expression="Status eq 'Active'"),
        )
        # String quotes should be preserved (not a date pattern)
        assert config.filter_expression == "Status eq 'Active'"

    def test_filter_with_multiple_quoted_dates(self) -> None:
        """Test complex filter with multiple date conditions"""
        config = Configuration(
            service_url="https://sap-server.com/odata/API_PARTNER",
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
            query_options=QueryOptions(
                filter_expression="DocumentDate gt '2024-01-01' and DocumentDate lt '2024-12-31'"
            ),
        )
        assert config.filter_expression == "DocumentDate gt 2024-01-01 and DocumentDate lt 2024-12-31"

    def test_filter_without_quotes_unchanged(self) -> None:
        """Test that correctly formatted filters are not modified"""
        config = Configuration(
            service_url="https://sap-server.com/odata/API_PARTNER",
            auth_type=AuthType.BASIC,
            username="user",
            **{"#password": "pass"},
            query_options=QueryOptions(filter_expression="DocumentDate gt 2024-01-01"),
        )
        assert config.filter_expression == "DocumentDate gt 2024-01-01"

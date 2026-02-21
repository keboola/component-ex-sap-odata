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
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            }
        )

        assert config.base_url == "https://example.com/odata"
        assert config.auth_type == AuthType.BASIC
        assert config.username == "user"
        assert config.password == "pass"
        assert config.odata_version == ODataVersionChoice.AUTO
        assert config.timeout == 60
        assert config.max_retries == 3

    def test_oauth_configuration(self) -> None:
        config = Configuration(
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "oauth",
                "token_url": "https://auth.example.com/oauth/token",
                "client_id": "my-client-id",
                "#client_secret": "my-client-secret"
            }
        )

        assert config.auth_type == AuthType.OAUTH
        assert config.token_url == "https://auth.example.com/oauth/token"
        assert config.client_id == "my-client-id"
        assert config.client_secret == "my-client-secret"
        assert config.username is None
        assert config.password is None

    def test_api_key_configuration(self) -> None:
        config = Configuration(
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "apiKey",
                "#api_key": "my-secret-api-key"
            }
        )

        assert config.auth_type == AuthType.API_KEY
        assert config.api_key == "my-secret-api-key"
        assert config.api_key_header_name == "APIKey"

    def test_api_key_with_custom_header_name(self) -> None:
        config = Configuration(
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "apiKey",
                "api_key_header_name": "X-API-Key",
                "#api_key": "my-secret-api-key"
            }
        )

        assert config.api_key == "my-secret-api-key"
        assert config.api_key_header_name == "X-API-Key"

    def test_api_key_auth_requires_api_key(self) -> None:
        with pytest.raises(ValueError, match="API key is required"):
            Configuration(
                connection={"base_url": "https://example.com/odata"},
                authentication={"auth_type": "apiKey"}
            )

    def test_basic_auth_requires_username(self) -> None:
        with pytest.raises(ValueError, match="Username is required"):
            Configuration(
                connection={"base_url": "https://example.com/odata"},
                authentication={
                    "auth_type": "basic",
                    "#password": "pass"
                }
            )

    def test_basic_auth_requires_password(self) -> None:
        with pytest.raises(ValueError, match="Password is required"):
            Configuration(
                connection={"base_url": "https://example.com/odata"},
                authentication={
                    "auth_type": "basic",
                    "username": "user"
                }
            )

    def test_custom_timeout_and_retries(self) -> None:
        config = Configuration(
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            advanced_options={
                "connection_options": [{"timeout": 120, "max_retries": 5, "verify_ssl": True}]
            }
        )

        assert config.timeout == 120
        assert config.max_retries == 5
        assert config.verify_ssl is True

    def test_odata_version_choices(self) -> None:
        for version in [ODataVersionChoice.AUTO, ODataVersionChoice.V2, ODataVersionChoice.V4]:
            config = Configuration(
                connection={"base_url": "https://example.com/odata"},
                authentication={
                    "auth_type": "basic",
                    "username": "user",
                    "#password": "pass"
                },
                odata_version=version
            )
            assert config.odata_version == version


class TestConfigurationWithRowFields:
    """Tests for row configuration fields merged into Configuration."""

    def test_configuration_with_entity_set(self) -> None:
        config = Configuration(
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            entity_set="Products"
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
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
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
            advanced_options={
                "connection_options": [],
                "pagination_defaults": [{"page_size": 500, "max_records": 10000}]
            }
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
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            entity_set="Products",
            destination={"output_table_name": "custom_table"}
        )
        assert config.get_output_table_name() == "custom_table"

    def test_get_output_table_name_default(self) -> None:
        config = Configuration(
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            entity_set="Products"
        )
        assert config.get_output_table_name() == "Products"

    def test_get_output_table_name_fallback(self) -> None:
        config = Configuration(
            connection={"base_url": "https://example.com/odata"},
            authentication={
                "auth_type": "oauth",
                "token_url": "https://auth.example.com/oauth/token",
                "client_id": "my-client-id",
                "#client_secret": "my-client-secret"
            }
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
        """Test that complete base_url still works"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com/sap/opu/odata/sap/API_BUSINESS_PARTNER"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            }
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/sap/opu/odata/sap/API_BUSINESS_PARTNER"

    def test_split_url_v2(self) -> None:
        """Test split URL configuration for OData V2"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            service_path="API_BUSINESS_PARTNER",
            odata_version=ODataVersionChoice.V2
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/API_BUSINESS_PARTNER"

    def test_split_url_v4(self) -> None:
        """Test split URL configuration for OData V4"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            service_path="api_fixedasset/srvd_a2x/sap/fixedasset/0001",
            odata_version=ODataVersionChoice.V4
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/api_fixedasset/srvd_a2x/sap/fixedasset/0001"

    def test_split_url_auto_v2_inference(self) -> None:
        """Test that AUTO version uses simple path joining"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            service_path="API_BUSINESS_PARTNER",
            odata_version=ODataVersionChoice.AUTO
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/API_BUSINESS_PARTNER"

    def test_split_url_auto_v4_inference(self) -> None:
        """Test that AUTO version uses simple path joining"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            service_path="api_fixedasset/srvd_a2x/sap/fixedasset/0001",
            odata_version=ODataVersionChoice.AUTO
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/api_fixedasset/srvd_a2x/sap/fixedasset/0001"

    def test_split_url_with_trailing_slash(self) -> None:
        """Test that trailing/leading slashes are handled correctly"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com/"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            service_path="/API_BUSINESS_PARTNER",
            odata_version=ODataVersionChoice.V2
        )

        url = config.get_service_url()
        assert url == "https://sap-server.com/API_BUSINESS_PARTNER"

    def test_neither_url_config_raises_error(self) -> None:
        """Test that providing neither URL configuration raises an error when validating for extraction"""
        config = Configuration(
            connection={},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            }
        )
        with pytest.raises(ValueError, match="Either base_url or service_path is required"):
            config.validate_for_extraction()

    def test_both_url_configs_no_error(self) -> None:
        """Test that providing both base_url and service_path works (service_path takes precedence)"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            service_path="API_BUSINESS_PARTNER"
        )
        # service_path takes precedence, should work fine
        url = config.get_service_url()
        assert url == "https://sap-server.com/API_BUSINESS_PARTNER"

    def test_base_url_without_service_path_ok(self) -> None:
        """Test that base_url without service_path is valid (for root config or simple setups)"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com/odata/API_PARTNER"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            }
        )
        # This should work - get_service_url returns base_url if no service_path
        url = config.get_service_url()
        assert url == "https://sap-server.com/odata/API_PARTNER"

    def test_service_path_without_base_url_raises_error(self) -> None:
        """Test that service_path without base_url raises an error when getting service URL"""
        config = Configuration(
            connection={},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            service_path="API_BUSINESS_PARTNER"
        )
        with pytest.raises(ValueError, match="base_url is required"):
            config.get_service_url()


class TestFilterValidation:
    """Test filter expression validation"""

    def test_filter_with_quoted_date_v4_format(self) -> None:
        """Test that quoted dates are automatically fixed for OData V4"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com/odata/API_PARTNER"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            query_options=QueryOptions(filter_expression="DocumentDate gt '2024-01-01'")
        )
        # Quotes should be removed
        assert config.filter_expression == "DocumentDate gt 2024-01-01"

    def test_filter_with_quoted_datetime_v4_format(self) -> None:
        """Test that quoted datetime values are fixed"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com/odata/API_PARTNER"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            query_options=QueryOptions(filter_expression="CreatedAt gt '2024-01-01T00:00:00Z'")
        )
        assert config.filter_expression == "CreatedAt gt 2024-01-01T00:00:00Z"

    def test_filter_with_v2_datetime_format_preserved(self) -> None:
        """Test that OData V2 datetime'...' format is preserved"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com/odata/API_PARTNER"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            query_options=QueryOptions(filter_expression="CreatedAt gt datetime'2024-01-01T00:00:00'")
        )
        # V2 format should NOT be changed
        assert config.filter_expression == "CreatedAt gt datetime'2024-01-01T00:00:00'"

    def test_filter_with_string_quotes_preserved(self) -> None:
        """Test that string values keep their quotes"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com/odata/API_PARTNER"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            query_options=QueryOptions(filter_expression="Status eq 'Active'")
        )
        # String quotes should be preserved (not a date pattern)
        assert config.filter_expression == "Status eq 'Active'"

    def test_filter_with_multiple_quoted_dates(self) -> None:
        """Test complex filter with multiple date conditions"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com/odata/API_PARTNER"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            query_options=QueryOptions(
                filter_expression="DocumentDate gt '2024-01-01' and DocumentDate lt '2024-12-31'"
            )
        )
        assert config.filter_expression == "DocumentDate gt 2024-01-01 and DocumentDate lt 2024-12-31"

    def test_filter_without_quotes_unchanged(self) -> None:
        """Test that correctly formatted filters are not modified"""
        config = Configuration(
            connection={"base_url": "https://sap-server.com/odata/API_PARTNER"},
            authentication={
                "auth_type": "basic",
                "username": "user",
                "#password": "pass"
            },
            query_options=QueryOptions(filter_expression="DocumentDate gt 2024-01-01")
        )
        assert config.filter_expression == "DocumentDate gt 2024-01-01"


class TestValidateForExtraction:
    """Tests for validate_for_extraction() validation logic."""

    _BASIC_AUTH = {
        "auth_type": "basic",
        "username": "user",
        "#password": "pass",
    }

    def _base_config(self, **kwargs) -> Configuration:
        """Return a minimal valid config with base_url set."""
        return Configuration(
            connection={"base_url": "https://example.com"},
            authentication=self._BASIC_AUTH,
            **kwargs,
        )

    def test_incremental_fetch_without_incremental_field_raises(self) -> None:
        """fetch_type=incremental without incremental_field should raise ValueError."""
        config = self._base_config(
            fetching_options={"fetch_type": "incremental"},
        )
        with pytest.raises(ValueError, match="'incremental_field' is required when fetch_type is 'incremental'"):
            config.validate_for_extraction()

    def test_incremental_fetch_with_incremental_field_passes(self) -> None:
        """fetch_type=incremental with incremental_field should not raise."""
        config = self._base_config(
            fetching_options={"fetch_type": "incremental", "incremental_field": "ModifiedAt"},
        )
        config.validate_for_extraction()  # must not raise

    def test_full_fetch_without_incremental_field_passes(self) -> None:
        """fetch_type=full without incremental_field should not raise."""
        config = self._base_config(
            fetching_options={"fetch_type": "full"},
        )
        config.validate_for_extraction()  # must not raise

    def test_incremental_load_without_primary_key_raises(self) -> None:
        """load_type=incremental without primary_key should raise ValueError."""
        config = self._base_config(
            destination={"load_type": "incremental"},
        )
        with pytest.raises(ValueError, match="'primary_key' is required when load_type is 'incremental'"):
            config.validate_for_extraction()

    def test_incremental_load_with_primary_key_passes(self) -> None:
        """load_type=incremental with primary_key should not raise."""
        config = self._base_config(
            destination={"load_type": "incremental", "primary_key": ["ID"]},
        )
        config.validate_for_extraction()  # must not raise

    def test_full_load_without_primary_key_passes(self) -> None:
        """load_type=full without primary_key should not raise."""
        config = self._base_config(
            destination={"load_type": "full"},
        )
        config.validate_for_extraction()  # must not raise

    def test_no_base_url_no_service_path_raises(self) -> None:
        """Both base_url and service_path being None should raise ValueError."""
        config = Configuration(
            connection={},
            authentication=self._BASIC_AUTH,
        )
        with pytest.raises(ValueError, match="Either base_url or service_path is required"):
            config.validate_for_extraction()

    def test_only_service_path_passes(self) -> None:
        """service_path without base_url should pass validate_for_extraction (URL check only)."""
        config = Configuration(
            connection={},
            authentication=self._BASIC_AUTH,
            service_path="sap/opu/odata/sap/MY_SERVICE",
        )
        config.validate_for_extraction()  # must not raise


class TestOAuthValidation:
    """Tests for OAuth-specific validation errors raised in model_post_init."""

    _BASE_CONN = {"base_url": "https://example.com"}
    _FULL_OAUTH = {
        "auth_type": "oauth",
        "token_url": "https://auth.example.com/token",
        "client_id": "my-client-id",
        "#client_secret": "my-client-secret",
    }

    def test_oauth_missing_token_url_raises(self) -> None:
        """OAuth auth without token_url should raise ValueError."""
        auth = dict(self._FULL_OAUTH)
        del auth["token_url"]
        with pytest.raises(ValueError, match="Token URL is required for OAuth authentication"):
            Configuration(
                connection=self._BASE_CONN,
                authentication=auth,
            )

    def test_oauth_missing_client_id_raises(self) -> None:
        """OAuth auth without client_id should raise ValueError."""
        auth = dict(self._FULL_OAUTH)
        del auth["client_id"]
        with pytest.raises(ValueError, match="Client ID is required for OAuth authentication"):
            Configuration(
                connection=self._BASE_CONN,
                authentication=auth,
            )

    def test_oauth_missing_client_secret_raises(self) -> None:
        """OAuth auth without client_secret should raise ValueError."""
        auth = dict(self._FULL_OAUTH)
        del auth["#client_secret"]
        with pytest.raises(ValueError, match="Client Secret is required for OAuth authentication"):
            Configuration(
                connection=self._BASE_CONN,
                authentication=auth,
            )

    def test_oauth_all_fields_present_passes(self) -> None:
        """OAuth auth with all required fields should not raise."""
        config = Configuration(
            connection=self._BASE_CONN,
            authentication=self._FULL_OAUTH,
        )
        assert config.auth_type == AuthType.OAUTH
        assert config.token_url == "https://auth.example.com/token"
        assert config.client_id == "my-client-id"
        assert config.client_secret == "my-client-secret"

    def test_oauth_empty_token_url_raises(self) -> None:
        """OAuth auth with empty string token_url should raise ValueError."""
        auth = dict(self._FULL_OAUTH)
        auth["token_url"] = ""
        with pytest.raises(ValueError, match="Token URL is required for OAuth authentication"):
            Configuration(
                connection=self._BASE_CONN,
                authentication=auth,
            )

    def test_oauth_empty_client_id_raises(self) -> None:
        """OAuth auth with empty string client_id should raise ValueError."""
        auth = dict(self._FULL_OAUTH)
        auth["client_id"] = ""
        with pytest.raises(ValueError, match="Client ID is required for OAuth authentication"):
            Configuration(
                connection=self._BASE_CONN,
                authentication=auth,
            )

    def test_oauth_empty_client_secret_raises(self) -> None:
        """OAuth auth with empty string client_secret should raise ValueError."""
        auth = dict(self._FULL_OAUTH)
        auth["#client_secret"] = ""
        with pytest.raises(ValueError, match="Client Secret is required for OAuth authentication"):
            Configuration(
                connection=self._BASE_CONN,
                authentication=auth,
            )

import pytest

from configuration import (
    AuthType,
    ComponentState,
    Configuration,
    ODataVersionChoice,
    RowConfiguration,
    StateEntry,
    SyncType,
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
            timeout=120,
            max_retries=5,
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


class TestRowConfiguration:
    def test_basic_row_configuration(self) -> None:
        row = RowConfiguration(entity_set="Products")

        assert row.entity_set == "Products"
        assert row.output_table_name is None
        assert row.select_fields == []
        assert row.filter_expression is None
        assert row.sync_type == SyncType.FULL
        assert row.page_size == 1000
        assert row.max_records == 0

    def test_full_row_configuration(self) -> None:
        row = RowConfiguration(
            entity_set="Products",
            output_table_name="my_products",
            select_fields=["ProductID", "ProductName"],
            filter_expression="IsActive eq true",
            expand_properties=["Category"],
            order_by="ProductName asc",
            sync_type=SyncType.INCREMENTAL,
            incremental_field="ModifiedAt",
            primary_key=["ProductID"],
            page_size=500,
            max_records=10000,
        )

        assert row.entity_set == "Products"
        assert row.output_table_name == "my_products"
        assert row.select_fields == ["ProductID", "ProductName"]
        assert row.filter_expression == "IsActive eq true"
        assert row.expand_properties == ["Category"]
        assert row.order_by == "ProductName asc"
        assert row.sync_type == SyncType.INCREMENTAL
        assert row.incremental_field == "ModifiedAt"
        assert row.primary_key == ["ProductID"]
        assert row.page_size == 500
        assert row.max_records == 10000

    def test_get_output_table_name_with_custom_name(self) -> None:
        row = RowConfiguration(
            entity_set="Products",
            output_table_name="custom_table",
        )
        assert row.get_output_table_name() == "custom_table"

    def test_get_output_table_name_default(self) -> None:
        row = RowConfiguration(entity_set="Products")
        assert row.get_output_table_name() == "Products"


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

"""Tests for Component class methods."""

from unittest.mock import Mock, PropertyMock, patch

import pytest
import requests as req

from component import Component, _simplify_error_message
from configuration import AuthType, Configuration, ODataVersionChoice
from odata_client.metadata import EntityProperty, EntitySet, ODataVersion


class TestFormatFilterLiteral:
    """Tests for _format_filter_literal method."""

    @pytest.fixture
    def component(self):
        """Create a Component instance with minimal configuration."""
        with patch.object(Component, "__init__", lambda self: None):
            comp = Component()
            comp._config = Mock(spec=Configuration)
            comp._config.entity_set = "TestEntity"
            comp._config.base_url = "https://api.example.com"
            comp._config.service_path = "/test"
            comp._config.timeout = 30
            comp._config.max_retries = 3
            comp._config.verify_ssl = True
            comp._config.enable_parallel = False
            comp._config.parallel_pages = 5
            comp._config.max_requests_per_second = 10
            comp._config.auth_type = AuthType.BASIC
            comp._config.username = "test"
            comp._config.password = "test"
            comp._client = None
            comp._detected_version = None
            return comp

    def test_odata_v4_date_without_quotes(self, component):
        """Test OData V4 Edm.Date returns value without quotes."""
        component._get_field_edm_type = Mock(return_value="Edm.Date")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._format_filter_literal("2024-01-01", "CreatedDate")
        assert result == "2024-01-01"

    def test_odata_v4_datetimeoffset_without_quotes(self, component):
        """Test OData V4 Edm.DateTimeOffset returns value without quotes."""
        component._get_field_edm_type = Mock(return_value="Edm.DateTimeOffset")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._format_filter_literal("2024-01-01T10:30:00Z", "LastModified")
        assert result == "2024-01-01T10:30:00Z"

    def test_odata_v2_datetime_with_datetime_prefix(self, component):
        """Test OData V2 Edm.DateTime uses datetime'...' format."""
        component._get_field_edm_type = Mock(return_value="Edm.DateTime")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V2)

        result = component._format_filter_literal("2024-01-01T10:30:00", "LastChangedAt")
        assert result == "datetime'2024-01-01T10:30:00'"

    def test_odata_v2_datetime_adds_time_if_missing(self, component):
        """Test OData V2 DateTime adds T00:00:00 if time is missing."""
        component._get_field_edm_type = Mock(return_value="Edm.DateTime")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V2)

        result = component._format_filter_literal("2024-01-01", "CreatedAt")
        assert result == "datetime'2024-01-01T00:00:00'"

    def test_numeric_int32_without_quotes(self, component):
        """Test Edm.Int32 returns value without quotes."""
        component._get_field_edm_type = Mock(return_value="Edm.Int32")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._format_filter_literal("12345", "OrderID")
        assert result == "12345"

    def test_numeric_decimal_without_quotes(self, component):
        """Test Edm.Decimal returns value without quotes."""
        component._get_field_edm_type = Mock(return_value="Edm.Decimal")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._format_filter_literal("123.45", "Price")
        assert result == "123.45"

    def test_numeric_double_without_quotes(self, component):
        """Test Edm.Double returns value without quotes."""
        component._get_field_edm_type = Mock(return_value="Edm.Double")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._format_filter_literal("99.99", "Amount")
        assert result == "99.99"

    def test_string_with_quotes(self, component):
        """Test Edm.String returns value with quotes."""
        component._get_field_edm_type = Mock(return_value="Edm.String")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._format_filter_literal("Active", "Status")
        assert result == "'Active'"

    def test_unknown_type_fallback_to_quotes(self, component):
        """Test unknown type falls back to quoted string."""
        component._get_field_edm_type = Mock(return_value="Edm.Unknown")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._format_filter_literal("SomeValue", "CustomField")
        assert result == "'SomeValue'"

    def test_no_edm_type_fallback_to_quotes(self, component):
        """Test when EDM type cannot be determined, falls back to quotes."""
        component._get_field_edm_type = Mock(return_value=None)
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._format_filter_literal("SomeValue", "UnknownField")
        assert result == "'SomeValue'"

    def test_all_numeric_types_without_quotes(self, component):
        """Test all numeric EDM types return value without quotes."""
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        numeric_types = [
            "Edm.Int16",
            "Edm.Int32",
            "Edm.Int64",
            "Edm.Decimal",
            "Edm.Double",
            "Edm.Single",
            "Edm.Byte",
            "Edm.SByte",
        ]

        for edm_type in numeric_types:
            component._get_field_edm_type = Mock(return_value=edm_type)
            result = component._format_filter_literal("123", "TestField")
            assert result == "123", f"Failed for {edm_type}"

    def test_detect_version_called_with_config(self, component):
        """Test that _detect_or_get_version is called with config argument.

        This test catches the bug where _detect_or_get_version was called
        without the required config argument, which would cause TypeError
        at runtime even though mocked tests would pass.
        """
        # Don't mock _detect_or_get_version, instead set _detected_version directly
        # This way the real method gets called and we verify it works with the config
        component._detected_version = ODataVersion.V4
        component._get_field_edm_type = Mock(return_value="Edm.Date")

        # This should not raise TypeError about missing config argument
        result = component._format_filter_literal("2024-01-01", "TestField")
        assert result == "2024-01-01"


class TestGetFieldEdmType:
    """Tests for _get_field_edm_type method."""

    @pytest.fixture
    def component(self):
        """Create a Component instance with minimal configuration."""
        with patch.object(Component, "__init__", lambda self: None):
            comp = Component()
            comp._config = Mock(spec=Configuration)
            comp._config.entity_set = "Products"
            comp._config.base_url = "https://api.example.com"
            comp._config.service_path = "/test"
            comp._config.timeout = 30
            comp._config.max_retries = 3
            comp._config.verify_ssl = True
            comp._config.enable_parallel = False
            comp._config.parallel_pages = 5
            comp._config.max_requests_per_second = 10
            comp._config.auth_type = AuthType.BASIC
            comp._config.username = "test"
            comp._config.password = "test"
            comp._client = None
            comp._detected_version = None
            return comp

    def test_get_field_edm_type_success(self, component):
        """Test successfully getting EDM type from metadata."""
        # Create mock entity set with properties
        mock_entity_set = EntitySet(
            name="Products",
            entity_type="Product",
            properties=[
                EntityProperty(name="ID", edm_type="Edm.Int32", nullable=False),
                EntityProperty(name="Name", edm_type="Edm.String", nullable=False),
                EntityProperty(name="CreatedAt", edm_type="Edm.DateTimeOffset", nullable=True),
            ],
            key_properties=["ID"],
            navigation_properties=[],
        )

        # Mock the client and metadata
        mock_metadata = Mock()
        mock_metadata.get_entity_set.return_value = mock_entity_set

        mock_client = Mock()
        mock_client.get_metadata.return_value = mock_metadata

        component._build_client = Mock(return_value=mock_client)

        # Test getting EDM type for existing field
        result = component._get_field_edm_type("CreatedAt")
        assert result == "Edm.DateTimeOffset"

    def test_get_field_edm_type_field_not_found(self, component):
        """Test returns None when field is not found in entity set."""
        mock_entity_set = EntitySet(
            name="Products",
            entity_type="Product",
            properties=[
                EntityProperty(name="ID", edm_type="Edm.Int32", nullable=False),
            ],
            key_properties=["ID"],
            navigation_properties=[],
        )

        mock_metadata = Mock()
        mock_metadata.get_entity_set.return_value = mock_entity_set

        mock_client = Mock()
        mock_client.get_metadata.return_value = mock_metadata

        component._build_client = Mock(return_value=mock_client)

        result = component._get_field_edm_type("NonExistentField")
        assert result is None

    def test_get_field_edm_type_entity_set_not_found(self, component):
        """Test returns None when entity set is not found."""
        mock_metadata = Mock()
        mock_metadata.get_entity_set.return_value = None

        mock_client = Mock()
        mock_client.get_metadata.return_value = mock_metadata

        component._build_client = Mock(return_value=mock_client)

        result = component._get_field_edm_type("SomeField")
        assert result is None

    def test_get_field_edm_type_exception_handling(self, component):
        """Test returns None and logs warning when exception occurs."""
        mock_client = Mock()
        mock_client.get_metadata.side_effect = Exception("Metadata fetch failed")

        component._build_client = Mock(return_value=mock_client)

        with patch("logging.warning") as mock_warning:
            result = component._get_field_edm_type("SomeField")
            assert result is None
            mock_warning.assert_called_once()
            assert "Could not determine EDM type for field 'SomeField'" in str(mock_warning.call_args)

    def test_get_field_edm_type_multiple_properties(self, component):
        """Test getting EDM type from entity set with multiple properties."""
        mock_entity_set = EntitySet(
            name="Orders",
            entity_type="Order",
            properties=[
                EntityProperty(name="OrderID", edm_type="Edm.Int32", nullable=False),
                EntityProperty(name="CustomerName", edm_type="Edm.String", nullable=False),
                EntityProperty(name="OrderDate", edm_type="Edm.Date", nullable=False),
                EntityProperty(name="TotalAmount", edm_type="Edm.Decimal", nullable=False),
                EntityProperty(name="IsActive", edm_type="Edm.Boolean", nullable=False),
            ],
            key_properties=["OrderID"],
            navigation_properties=[],
        )

        mock_metadata = Mock()
        mock_metadata.get_entity_set.return_value = mock_entity_set

        mock_client = Mock()
        mock_client.get_metadata.return_value = mock_metadata

        component._build_client = Mock(return_value=mock_client)

        # Test each property
        assert component._get_field_edm_type("OrderID") == "Edm.Int32"
        assert component._get_field_edm_type("CustomerName") == "Edm.String"
        assert component._get_field_edm_type("OrderDate") == "Edm.Date"
        assert component._get_field_edm_type("TotalAmount") == "Edm.Decimal"
        assert component._get_field_edm_type("IsActive") == "Edm.Boolean"


class TestBuildFilterExpression:
    """Tests for _build_filter_expression method with date literal formatting."""

    @pytest.fixture
    def component(self):
        """Create a Component instance with minimal configuration."""
        with patch.object(Component, "__init__", lambda self: None):
            comp = Component()
            comp._config = Mock(spec=Configuration)
            comp._config.entity_set = "Products"
            comp._config.filter_expression = ""
            comp._config.incremental_field = None
            comp._config.base_url = "https://api.example.com"
            comp._config.service_path = "/test"
            comp._config.timeout = 30
            comp._config.max_retries = 3
            comp._config.verify_ssl = True
            comp._config.enable_parallel = False
            comp._config.parallel_pages = 5
            comp._config.max_requests_per_second = 10
            comp._config.auth_type = AuthType.BASIC
            comp._config.username = "test"
            comp._config.password = "test"
            comp._client = None
            comp._detected_version = None
            return comp

    def test_incremental_filter_with_date_v4(self, component):
        """Test incremental filter uses correct date format for OData V4."""
        component._config.fetch_type = "incremental"
        component._config.incremental_field = "LastChangedAt"

        # Mock entity state
        mock_state = Mock()
        mock_state.last_incremental_value = "2024-01-01T00:00:00Z"

        # Mock the helper methods
        component._get_field_edm_type = Mock(return_value="Edm.DateTimeOffset")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._build_filter_expression(mock_state)

        # Should not have quotes for OData V4 date
        assert result == "LastChangedAt gt 2024-01-01T00:00:00Z"

    def test_incremental_filter_with_date_v2(self, component):
        """Test incremental filter uses correct date format for OData V2."""
        component._config.fetch_type = "incremental"
        component._config.incremental_field = "CreatedAt"

        mock_state = Mock()
        mock_state.last_incremental_value = "2024-01-01T10:30:00"

        component._get_field_edm_type = Mock(return_value="Edm.DateTime")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V2)

        result = component._build_filter_expression(mock_state)

        # Should use datetime'...' format for OData V2
        assert result == "CreatedAt gt datetime'2024-01-01T10:30:00'"

    def test_incremental_filter_combined_with_existing_filter(self, component):
        """Test incremental filter combines correctly with existing filter."""
        component._config.fetch_type = "incremental"
        component._config.incremental_field = "UpdatedAt"
        component._config.filter_expression = "Status eq 'Active'"

        mock_state = Mock()
        mock_state.last_incremental_value = "2024-01-01"

        component._get_field_edm_type = Mock(return_value="Edm.Date")
        component._detect_or_get_version = Mock(return_value=ODataVersion.V4)

        result = component._build_filter_expression(mock_state)

        # Should combine filters with 'and'
        assert result == "(Status eq 'Active') and (UpdatedAt gt 2024-01-01)"

    def test_no_incremental_filter_when_no_last_value(self, component):
        """Test no incremental filter when no last value in state."""
        component._config.fetch_type = "incremental"
        component._config.incremental_field = "UpdatedAt"
        component._config.filter_expression = "Status eq 'Active'"

        mock_state = Mock()
        mock_state.last_incremental_value = None

        result = component._build_filter_expression(mock_state)

        # Should return only the base filter
        assert result == "Status eq 'Active'"


class TestSimplifyErrorMessage:
    """Tests for _simplify_error_message (CFTL-681)."""

    def test_ssl_error_reported_as_ssl_not_connection(self):
        """SSLError must be labeled as a certificate failure, not 'Connection failed'.

        requests.exceptions.SSLError subclasses ConnectionError, so it must be
        checked first or the real cause (cert verification) is hidden.
        """
        error = req.exceptions.SSLError("certificate verify failed")
        msg = _simplify_error_message(error, "https://sap.example.com:40003/sap/opu/odata/")

        assert "SSL certificate verification failed" in msg
        assert "Verify SSL Certificate" in msg
        assert "Connection failed" not in msg

    def test_plain_connection_error_still_reports_connection_failed(self):
        """A non-SSL ConnectionError should still produce the connection message."""
        error = req.exceptions.ConnectionError("connection refused")
        msg = _simplify_error_message(error, "https://sap.example.com:40003/sap/opu/odata/")

        assert "Connection failed" in msg
        assert "SSL certificate" not in msg


class TestInsecureWarningSuppressed:
    """verify_ssl=False must suppress urllib3 InsecureRequestWarning (CFTL-681).

    In a sync action the runner parses stdout as a single JSON object; a leaked
    InsecureRequestWarning corrupts it ("Decoding JSON response failed").
    """

    def _init_component(self, verify_ssl: bool):
        fake_config = Mock(spec=Configuration)
        fake_config.verify_ssl = verify_ssl

        with (
            patch("component.ComponentBase.__init__", lambda self: None),
            patch.object(
                Component, "configuration", new_callable=PropertyMock, return_value=Mock(parameters={})
            ),
            patch("component.Configuration", return_value=fake_config),
            patch("component.urllib3.disable_warnings") as mock_disable,
        ):
            Component()
        return mock_disable

    def test_warning_disabled_when_verify_ssl_false(self):
        mock_disable = self._init_component(verify_ssl=False)
        mock_disable.assert_called_once()

    def test_warning_not_touched_when_verify_ssl_true(self):
        mock_disable = self._init_component(verify_ssl=True)
        mock_disable.assert_not_called()

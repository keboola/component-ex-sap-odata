"""Tests for sync actions with mocked OData servers.

This test module focuses on testing all sync actions (testConnection, loadEntities,
loadFields, etc.) using mocked HTTP responses.

Key test scenarios:
- Each sync action works with correct mocked server
- URL chain: loadServices returns service_path → loadEntities works with that path
- Manual service_path input (user-typed) works in loadEntities
- Keboola proxy path format (http/keboola/connector/...) is handled correctly
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import responses as responses_lib
import respx


class TestConnectionAction:
    """Test testConnection sync action."""

    @respx.mock
    def test_connection_v4_success(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test successful connection to V4 service."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "testConnection")
        assert comp is not None

    @respx.mock
    def test_connection_v2_success(self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir):
        """Test successful connection to V2 service."""
        mock_v2_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v2_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v2",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "testConnection")
        assert comp is not None

    @respx.mock
    def test_connection_unauthorized(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test connection with invalid credentials (401)."""
        # Mock 401 response
        respx_mock.get("{mock_v4_server.base_url}/").mock(return_value=httpx.Response(401, content="Unauthorized"))

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "wrong_user", "#password": "wrong_password"},
            "odata_version": "v4",
        }
        datadir = datadir_factory(config)

        # testConnection should handle error gracefully
        comp = run_sync_action_with_datadir(datadir, "testConnection")
        assert comp is not None

    @respx.mock
    def test_connection_not_found(self, respx_mock, datadir_factory, run_sync_action_with_datadir):
        """Test connection to non-existent service (404)."""
        base_url = "https://api.example.com/nonexistent"
        respx_mock.get("{base_url}/").mock(return_value=httpx.Response(404, content="Not Found"))

        config = {
            "connection": {"base_url": base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "testConnection")
        assert comp is not None

    @respx.mock
    def test_connection_split_url(self, respx_mock, datadir_factory, run_sync_action_with_datadir):
        """Test connection using base_url + service_path."""
        base_url = "https://api.example.com"
        service_path = "odata/v4/service"
        full_url = f"{base_url}/{service_path}"

        respx_mock.get("{full_url}/").mock(return_value=httpx.Response(200, content="OK"))

        config = {
            "connection": {"base_url": base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "service_path": service_path,
            "odata_version": "v4",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "testConnection")
        assert comp is not None


class TestLoadServicesAction:
    """Test loadServices sync action."""

    def test_load_services_no_catalog_returns_manual_hint(
        self, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """No catalog_path must return a non-blocking hint, not raise (CFTL-681).

        Catalog browsing is optional - the user can type the Service Path manually.
        loadServices should return a single dropdown hint item (exit 0) pointing to
        manual entry, instead of a hard error.
        """
        config = {
            "connection": {"base_url": "https://api.example.com", "catalog_path": ""},
            "authentication": {"auth_type": "basic", "username": "user", "#password": "pass"},
        }
        datadir = datadir_factory(config)

        run_sync_action_with_datadir(datadir, "loadServices")

        result = json.loads(capsys.readouterr().out)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["value"] == ""
        assert "Service Path manually" in result[0]["label"]

    @responses_lib.activate
    @respx.mock
    def test_load_services_from_catalog(
        self, respx_mock, mock_catalog_server, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """Test loadServices returns correct direct service paths from catalog.

        loadServices uses requests.get() for initial availability check,
        then httpx (via OData client) to fetch the catalog ATOM feed.
        This test verifies both layers and that returned service_path values
        are in the direct format (no proxy prefix) for non-keboola catalogs.
        """
        base_url = "https://api.example.com"
        catalog_path = "sap/opu/odata/IWFND/CATALOGSERVICE;v=2"
        catalog_url = f"{base_url}/{catalog_path}"

        # Mock requests.get() used by loadServices for initial catalog check
        responses_lib.add(responses_lib.GET, catalog_url, status=200, body="OK")

        # Mock httpx catalog fetch (what list_catalog_services() actually calls)
        mock_catalog_server.setup(respx_mock)

        config = {
            "connection": {"base_url": base_url, "catalog_path": catalog_path},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
        }
        datadir = datadir_factory(config)

        run_sync_action_with_datadir(datadir, "loadServices")

        # Capture and verify output
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert isinstance(result, list)
        assert len(result) > 0

        values = [item["value"] for item in result if item.get("value")]
        # catalog_path has no "keboola" → paths are returned in direct format
        assert "sap/opu/odata/sap/API_BUSINESS_PARTNER" in values, (
            f"Expected direct service path in: {values}"
        )
        # Labels should be human-readable service titles
        labels = [item["label"] for item in result if item.get("value")]
        assert any("Business Partner" in lbl for lbl in labels)

    @responses_lib.activate
    @respx.mock
    def test_load_services_returns_keboola_proxy_path(
        self, respx_mock, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """Test loadServices returns keboola proxy-prefixed paths when catalog_path contains 'keboola'.

        When base_url points to a Keboola HTTP proxy (catalog_path contains 'keboola'),
        the returned service_path must include 'http/keboola/connector/' prefix so that
        the full URL resolves through the proxy correctly.
        """
        base_url = "https://sap-proxy.example.com"
        catalog_path = "http/keboola/catalog"
        catalog_url = f"{base_url}/{catalog_path}"

        # Mock requests.get() for initial catalog check
        responses_lib.add(responses_lib.GET, catalog_url, status=200, body="OK")

        # Create catalog server at the keboola catalog URL and mock it
        from tests.fixtures.mock_odata_server_respx import MockSAPCatalogServer
        catalog_server = MockSAPCatalogServer(catalog_url)
        catalog_server.setup(respx_mock)

        config = {
            "connection": {"base_url": base_url, "catalog_path": catalog_path},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
        }
        datadir = datadir_factory(config)

        run_sync_action_with_datadir(datadir, "loadServices")

        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert isinstance(result, list)
        values = [item["value"] for item in result if item.get("value")]
        # catalog_path contains "keboola" → proxy prefix must be added
        assert any(v.startswith("http/keboola/connector/") for v in values), (
            f"Expected keboola proxy prefix in service paths, got: {values}"
        )
        assert "http/keboola/connector/sap/opu/odata/sap/API_BUSINESS_PARTNER" in values

    @responses_lib.activate
    @respx.mock
    def test_load_services_auth_error_propagates(
        self, respx_mock, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """HTTP auth errors from catalog must propagate as UserException, not become 'No services found'.

        When the catalog endpoint returns 401, the error must surface to the UI
        with a meaningful message ('Authentication failed'), not be swallowed and
        replaced with the misleading 'No services found in catalog' message.
        """
        base_url = "https://api.example.com"
        catalog_path = "sap/opu/odata/IWFND/CATALOGSERVICE;v=2"
        catalog_url = f"{base_url}/{catalog_path}"

        # Pre-flight check passes (200 OK)
        responses_lib.add(responses_lib.GET, catalog_url, status=200, body="OK")

        # But the actual httpx catalog fetch returns 401
        respx_mock.get(catalog_url).mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        config = {
            "connection": {"base_url": base_url, "catalog_path": catalog_path},
            "authentication": {"auth_type": "basic", "username": "user", "#password": "wrong"},
        }
        datadir = datadir_factory(config)

        # @sync_action decorator writes UserException to stderr and calls exit(1)
        with pytest.raises(SystemExit) as exc_info:
            run_sync_action_with_datadir(datadir, "loadServices")

        assert exc_info.value.code == 1

        # Stderr must contain auth error, not the misleading "No services found"
        stderr = capsys.readouterr().err
        assert "no services found" not in stderr.lower(), (
            "Auth error must not be swallowed and replaced with 'No services found'"
        )
        assert "401" in stderr or "authentication failed" in stderr.lower() or "unauthorized" in stderr.lower()

    @responses_lib.activate
    @respx.mock
    def test_load_services_empty_catalog_raises(
        self, respx_mock, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """Empty catalog (valid response, 0 services) must raise UserException so UI shows error.

        If catalog responds OK but lists no services, the user would see an empty
        dropdown with no explanation. Raising UserException surfaces the message via
        the @sync_action decorator stderr → UI error notification.
        """
        base_url = "https://api.example.com"
        catalog_path = "sap/opu/odata/IWFND/CATALOGSERVICE;v=2"
        catalog_url = f"{base_url}/{catalog_path}"

        responses_lib.add(responses_lib.GET, catalog_url, status=200, body="OK")

        # Catalog returns valid XML but with no services
        empty_atom = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>SAP Service Catalog</title>
</feed>"""
        respx_mock.get(catalog_url).mock(
            return_value=httpx.Response(200, text=empty_atom,
                                        headers={"content-type": "application/atom+xml"})
        )

        config = {
            "connection": {"base_url": base_url, "catalog_path": catalog_path},
            "authentication": {"auth_type": "basic", "username": "user", "#password": "pass"},
        }
        datadir = datadir_factory(config)

        # Empty catalog → UserException → decorator writes to stderr, exit(1)
        with pytest.raises(SystemExit) as exc_info:
            run_sync_action_with_datadir(datadir, "loadServices")

        assert exc_info.value.code == 1
        stderr = capsys.readouterr().err
        assert "No services found" in stderr


class TestLoadEntitiesAction:
    """Test loadEntities sync action."""

    @respx.mock
    def test_load_entities_v4(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test loading entity sets from V4 service."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadEntities")
        assert comp is not None

        # In production, this would output JSON with entity sets

    @respx.mock
    def test_load_entities_v2(self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir):
        """Test loading entity sets from V2 service."""
        mock_v2_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v2_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v2",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadEntities")
        assert comp is not None

    @respx.mock
    def test_load_entities_empty_metadata(
        self, respx_mock, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """Service responds OK but exposes no entity sets → UserException so UI shows error.

        If the service returns empty metadata, the user would see an empty dropdown
        with no explanation. Raising UserException surfaces the message via the
        @sync_action decorator stderr → UI error notification.
        """
        base_url = "https://api.example.com"
        service_path = "/odata/v4"

        respx_mock.get(f"{base_url}{service_path}/$metadata").mock(
            return_value=httpx.Response(
                200,
                content="""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="Empty" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityContainer Name="EmptyService">
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>""",
                headers={"Content-Type": "application/xml"},
            )
        )

        config = {
            "connection": {"base_url": base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "service_path": service_path,  # must be set so we get past the missing-config guard
        }
        datadir = datadir_factory(config)

        # Empty entity sets → UserException → decorator writes to stderr, exit(1)
        with pytest.raises(SystemExit) as exc_info:
            run_sync_action_with_datadir(datadir, "loadEntities")

        assert exc_info.value.code == 1
        stderr = capsys.readouterr().err
        assert "No entity sets found" in stderr


class TestLoadFieldsAction:
    """Test loadFields sync action."""

    @respx.mock
    def test_load_fields_v4(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test loading fields from V4 entity set."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadFields")
        assert comp is not None

    @respx.mock
    def test_load_fields_v2(self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir):
        """Test loading fields from V2 entity set."""
        mock_v2_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v2_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v2",
            "entity_set": "A_BusinessPartner",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadFields")
        assert comp is not None

    @respx.mock
    def test_load_fields_missing_entity_set(
        self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """Test loadFields without entity_set raises UserException shown as UI notification."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            # entity_set not specified
        }
        datadir = datadir_factory(config)

        with pytest.raises(SystemExit) as exc_info:
            run_sync_action_with_datadir(datadir, "loadFields")
        assert exc_info.value.code == 1
        stderr = capsys.readouterr().err
        assert "Entity Set is required" in stderr


class TestLoadPrimaryKeysAction:
    """Test loadPossiblePrimaryKeys sync action."""

    @respx.mock
    def test_load_primary_keys_v4(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test loading primary keys from V4 entity set."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadPossiblePrimaryKeys")
        assert comp is not None

    @respx.mock
    def test_load_primary_keys_v2(self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir):
        """Test loading primary keys from V2 entity set."""
        mock_v2_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v2_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v2",
            "entity_set": "A_BusinessPartner",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadPossiblePrimaryKeys")
        assert comp is not None


class TestLoadIncrementalFieldsAction:
    """Test loadIncrementalFields sync action."""

    @respx.mock
    def test_load_incremental_fields_v4(
        self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test loading incremental field candidates from V4."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadIncrementalFields")
        assert comp is not None
        # Should return fields with datetime types and relevant names

    @respx.mock
    def test_load_incremental_fields_v2(
        self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test loading incremental field candidates from V2."""
        mock_v2_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v2_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v2",
            "entity_set": "A_BusinessPartner",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadIncrementalFields")
        assert comp is not None


class TestLoadNavigationPropertiesAction:
    """Test loadNavigationProperties sync action."""

    @respx.mock
    def test_load_navigation_properties_v4(
        self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test loading navigation properties from V4."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadNavigationProperties")
        assert comp is not None

    @respx.mock
    def test_load_navigation_properties_v2(
        self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test loading navigation properties from V2."""
        mock_v2_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v2_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v2",
            "entity_set": "A_BusinessPartner",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadNavigationProperties")
        assert comp is not None


class TestPreviewDataAction:
    """Test previewData sync action."""

    @respx.mock
    def test_preview_data_v4(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test preview data from V4 entity set."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "previewData")
        assert comp is not None

    @respx.mock
    def test_preview_data_with_filter(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test preview data with filter applied."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "Products",
            "query_options": {
                    "filter_expression": "Category eq 'Electronics'",
                },
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "previewData")
        assert comp is not None


class TestValidateFilterAction:
    """Test validateFilter sync action."""

    @respx.mock
    def test_validate_filter_valid(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test validating a valid filter expression."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "Products",
            "query_options": {
                    "filter_expression": "Category eq 'Electronics'",
                },
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "validateFilter")
        assert comp is not None

    @respx.mock
    def test_validate_filter_no_filter(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test validating when no filter is set."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "validateFilter")
        assert comp is not None

    @respx.mock
    def test_validate_filter_fallback_when_top_rejected(
        self, respx_mock, datadir_factory, run_sync_action_with_datadir
    ):
        """Test that validateFilter succeeds when endpoint rejects $top+$filter (SAP IBP pattern).

        SAP IBP's PLANNING_DATA_API_SRV returns 400 when $top and $filter are combined.
        The fix retries without $top so a valid filter is not falsely reported as invalid.
        """
        base_url = "https://api.example.com/sap/opu/odata/IBP/PLANNING_DATA_API_SRV"

        def entity_side_effect(request):
            if "$top" in str(request.url):
                return httpx.Response(400, json={"error": {"message": "top not supported with filter"}})
            return httpx.Response(200, json={"value": [{"ID": "1"}]})

        respx_mock.get(f"{base_url}/DPFASTDP2").mock(side_effect=entity_side_effect)

        config = {
            "connection": {"base_url": base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "DPFASTDP2",
            "query_options": {"filter_expression": "UOMTOIDe eq '1BU'"},
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "validateFilter")
        assert comp is not None

    @respx.mock
    def test_validate_filter_includes_select_fields(
        self, respx_mock, datadir_factory, run_sync_action_with_datadir
    ):
        """Test that validateFilter passes $select when select_fields are configured.

        SAP IBP's PLANNING_DATA_API_SRV requires $select — requests without it return 400.
        The fix forwards the configured select_fields into the validation request.
        """
        base_url = "https://api.example.com/sap/opu/odata/IBP/PLANNING_DATA_API_SRV"

        captured = {}

        def entity_side_effect(request):
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"value": [{"UOMTOID": "1BU", "LOCID": "1000"}]})

        respx_mock.get(f"{base_url}/DPFASTDP2").mock(side_effect=entity_side_effect)

        config = {
            "connection": {"base_url": base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            "entity_set": "DPFASTDP2",
            "query_options": {
                "filter_expression": "UOMTOID eq '1BU'",
                "select_fields": ["UOMTOID", "LOCID"],
            },
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "validateFilter")
        assert comp is not None
        assert "%24select" in captured["url"] or "$select" in captured["url"], (
            f"Expected $select in validation request URL, got: {captured['url']}"
        )


class TestSyncActionsChain:
    """Test that URLs returned by one sync action work correctly in the next.

    Sync actions have a dependency chain:
      loadServices → service_path → loadEntities → entity_set → loadFields etc.

    Users can either:
    a) Select service_path from loadServices dropdown
    b) Type service_path manually

    Both input formats must work identically in subsequent actions.
    """

    @respx.mock
    def test_load_entities_with_direct_service_path(
        self, respx_mock, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """loadEntities works with direct service_path (format returned by loadServices for non-proxy catalogs).

        loadServices returns 'sap/opu/odata/sap/API_BUSINESS_PARTNER' for direct catalogs.
        This is also the format users type manually. Both cases are equivalent.
        """
        base_url = "https://api.example.com"
        service_path = "sap/opu/odata/sap/API_BUSINESS_PARTNER"
        # Full URL that loadEntities will call for metadata
        service_url = f"{base_url}/{service_path}"

        # Mock the metadata endpoint that loadEntities will call
        v2_metadata = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices m:DataServiceVersion="2.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="SAP" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityContainer Name="API_BUSINESS_PARTNER" m:IsDefaultEntityContainer="true">
        <EntitySet Name="A_BusinessPartner" EntityType="SAP.BusinessPartner"/>
        <EntitySet Name="A_CompanyCode" EntityType="SAP.CompanyCode"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""
        respx_mock.get(f"{service_url}/$metadata").mock(
            return_value=httpx.Response(200, content=v2_metadata, headers={"Content-Type": "application/xml"})
        )

        config = {
            "connection": {"base_url": base_url},
            "authentication": {"auth_type": "basic", "username": "user", "#password": "pass"},
            "odata_version": "v2",
            "service_path": service_path,
        }
        datadir = datadir_factory(config)

        run_sync_action_with_datadir(datadir, "loadEntities")

        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert isinstance(result, list)
        entity_names = [item["value"] for item in result]
        assert "A_BusinessPartner" in entity_names
        assert "A_CompanyCode" in entity_names

    @respx.mock
    def test_load_entities_with_keboola_proxy_service_path(
        self, respx_mock, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """loadEntities works with keboola proxy service_path returned by loadServices.

        loadServices returns 'http/keboola/connector/sap/opu/odata/sap/API_BUSINESS_PARTNER'
        when catalog_path contains 'keboola'. loadEntities must build the correct full URL:
          base_url/http/keboola/connector/sap/opu/odata/sap/API_BUSINESS_PARTNER/$metadata
        """
        base_url = "https://sap-proxy.example.com"
        service_path = "http/keboola/connector/sap/opu/odata/sap/API_BUSINESS_PARTNER"
        service_url = f"{base_url}/{service_path}"

        v2_metadata = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices m:DataServiceVersion="2.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="SAP" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityContainer Name="API_BUSINESS_PARTNER" m:IsDefaultEntityContainer="true">
        <EntitySet Name="A_BusinessPartner" EntityType="SAP.BusinessPartner"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""
        respx_mock.get(f"{service_url}/$metadata").mock(
            return_value=httpx.Response(200, content=v2_metadata, headers={"Content-Type": "application/xml"})
        )

        config = {
            "connection": {"base_url": base_url},
            "authentication": {"auth_type": "basic", "username": "user", "#password": "pass"},
            "odata_version": "v2",
            "service_path": service_path,  # keboola proxy format from loadServices
        }
        datadir = datadir_factory(config)

        run_sync_action_with_datadir(datadir, "loadEntities")

        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert isinstance(result, list)
        entity_names = [item["value"] for item in result]
        assert "A_BusinessPartner" in entity_names

    @respx.mock
    def test_load_fields_after_selecting_entity_from_load_entities(
        self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """loadFields works with entity_set value returned by loadEntities.

        loadEntities returns entity names (e.g. 'A_BusinessPartner').
        loadFields must work when that value is set as entity_set.
        This simulates the full chain: loadEntities value → entity_set → loadFields.
        """
        mock_v2_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v2_server.base_url},
            "authentication": {"auth_type": "basic", "username": "user", "#password": "pass"},
            "odata_version": "v2",
            "entity_set": "A_BusinessPartner",  # value from loadEntities
        }
        datadir = datadir_factory(config)

        run_sync_action_with_datadir(datadir, "loadFields")

        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert isinstance(result, list)
        assert len(result) > 0
        field_names = [item["value"] for item in result]
        assert "BusinessPartner" in field_names

    @respx.mock
    def test_manual_service_path_and_entity_set_work_in_load_fields(
        self, respx_mock, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """loadFields works when both service_path and entity_set are entered manually.

        Users should be able to bypass loadServices and loadEntities entirely
        and type both service_path and entity_set manually. This tests that
        the full manual-entry flow works end-to-end.
        """
        base_url = "https://api.example.com"
        service_path = "sap/opu/odata/sap/API_BUSINESS_PARTNER"  # typed manually
        entity_set = "A_BusinessPartner"  # typed manually
        service_url = f"{base_url}/{service_path}"

        v2_metadata = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices m:DataServiceVersion="2.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="SAP" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityType Name="BusinessPartner">
        <Key><PropertyRef Name="BusinessPartner"/></Key>
        <Property Name="BusinessPartner" Type="Edm.String" Nullable="false"/>
        <Property Name="BusinessPartnerName" Type="Edm.String"/>
        <Property Name="CreatedDate" Type="Edm.DateTime"/>
      </EntityType>
      <EntityContainer Name="API_BUSINESS_PARTNER" m:IsDefaultEntityContainer="true">
        <EntitySet Name="A_BusinessPartner" EntityType="SAP.BusinessPartner"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""
        respx_mock.get(f"{service_url}/$metadata").mock(
            return_value=httpx.Response(200, content=v2_metadata, headers={"Content-Type": "application/xml"})
        )

        config = {
            "connection": {"base_url": base_url},
            "authentication": {"auth_type": "basic", "username": "user", "#password": "pass"},
            "odata_version": "v2",
            "service_path": service_path,  # manually entered
            "entity_set": entity_set,       # manually entered
        }
        datadir = datadir_factory(config)

        run_sync_action_with_datadir(datadir, "loadFields")

        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert isinstance(result, list)
        assert len(result) > 0
        field_names = [item["value"] for item in result]
        assert "BusinessPartner" in field_names
        assert "BusinessPartnerName" in field_names


class TestLoadMetadataSummaryAction:
    """Test loadMetadataSummary sync action."""

    @respx.mock
    def test_load_metadata_summary_v4(
        self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test loading metadata summary from V4 service."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadMetadataSummary")
        assert comp is not None

    @respx.mock
    def test_load_metadata_summary_v2(
        self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test loading metadata summary from V2 service."""
        mock_v2_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v2_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v2",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadMetadataSummary")
        assert comp is not None

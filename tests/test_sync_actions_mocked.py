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

    @respx.mock
    def test_load_services_from_catalog(
        self, respx_mock, mock_catalog_server, datadir_factory, run_sync_action_with_datadir, capsys
    ):
        """Test loadServices returns correct direct service paths from catalog.

        loadServices uses httpx (via OData client) to fetch the catalog ATOM feed.
        This test verifies returned service_path values are in the direct format
        (no proxy prefix) for non-keboola catalogs.
        """
        base_url = "https://api.example.com"
        catalog_path = "sap/opu/odata/IWFND/CATALOGSERVICE;v=2"

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
    def test_load_entities_empty_metadata(self, respx_mock, datadir_factory, run_sync_action_with_datadir, capsys):
        """Test loading entities when metadata has no entity sets returns guidance item."""
        base_url = "https://api.example.com"
        service_path = "odata"
        service_url = f"{base_url}/{service_path}"

        # Empty metadata
        respx_mock.get(f"{service_url}/$metadata").mock(
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
            "service_path": "odata",
        }
        datadir = datadir_factory(config)

        run_sync_action_with_datadir(datadir, "loadEntities")

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["value"] == ""
        assert "No entity sets found" in result[0]["label"]


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
        self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test loadFields without entity_set configured."""
        mock_v4_server.setup(respx_mock)

        config = {
            "connection": {"base_url": mock_v4_server.base_url},
            "authentication": {"auth_type": "basic", "username": "test_user", "#password": "test_password"},
            "odata_version": "v4",
            # entity_set not specified
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadFields")
        assert comp is not None
        # Should return empty list


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

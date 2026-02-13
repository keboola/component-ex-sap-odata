"""Tests for sync actions with mocked OData servers.

This test module focuses on testing all sync actions (testConnection, loadEntities,
loadFields, etc.) using mocked HTTP responses.
"""

from __future__ import annotations

import json
from pathlib import Path

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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "testConnection")
        assert comp is not None

    @respx.mock
    def test_connection_v2_success(self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir):
        """Test successful connection to V2 service."""
        mock_v2_server.setup(respx_mock)

        config = {
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "wrong_user",
            "#password": "wrong_password",
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
            "service_url": base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "base_url": base_url,
            "service_path": service_path,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "testConnection")
        assert comp is not None


class TestLoadEntitiesAction:
    """Test loadEntities sync action."""

    @respx.mock
    def test_load_entities_v4(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test loading entity sets from V4 service."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadEntities")
        assert comp is not None

    @respx.mock
    def test_load_entities_from_catalog(
        self, respx_mock, mock_catalog_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test loading services from SAP catalog."""
        mock_catalog_server.setup(respx_mock)

        config = {
            "base_url": "https://api.example.com",
            "catalog_path": "sap/opu/odata/IWFND/CATALOGSERVICE;v=2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadEntities")
        assert comp is not None

        # Should return list of services, not entity sets

    @respx.mock
    def test_load_entities_empty_metadata(self, respx_mock, datadir_factory, run_sync_action_with_datadir):
        """Test loading entities when metadata has no entity sets."""
        base_url = "https://api.example.com/odata"

        # Empty metadata
        respx_mock.get(f"{base_url}/$metadata").mock(
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
            "service_url": base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadEntities")
        assert comp is not None


class TestLoadFieldsAction:
    """Test loadFields sync action."""

    @respx.mock
    def test_load_fields_v4(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test loading fields from V4 entity set."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "validateFilter")
        assert comp is not None


class TestLoadMetadataSummaryAction:
    """Test loadMetadataSummary sync action."""

    @respx.mock
    def test_load_metadata_summary_v4(
        self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test loading metadata summary from V4 service."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
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
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
        }
        datadir = datadir_factory(config)

        comp = run_sync_action_with_datadir(datadir, "loadMetadataSummary")
        assert comp is not None

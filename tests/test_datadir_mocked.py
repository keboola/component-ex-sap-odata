"""Comprehensive datadir tests with mocked OData servers.

These tests use the respx library to mock HTTP responses from OData V2 and V4 servers,
allowing for comprehensive testing without requiring a live SAP system.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
import responses

from tests.fixtures.mock_odata_server_respx import (
    MockODataV2Server,
    MockODataV4Server,
    MockSAPCatalogServer,
)


class TestODataV4BasicExtraction:
    """Test basic extraction from OData V4 service."""

    @respx.mock
    def test_v4_basic_extraction(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test basic V4 extraction with all products."""
        # Setup mock server
        mock_v4_server.setup(respx_mock)

        # Create datadir
        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        # Run component
        run_component_with_datadir(datadir)

        # Verify output
        rows = verify_output_table(
            datadir,
            "Products",
            min_rows=5,
            expected_columns=["ID", "Name", "Price", "Category"],
        )

        assert len(rows) == 5
        assert rows[0]["Name"] == "Laptop"
        assert rows[0]["Category"] == "Electronics"

    @respx.mock
    def test_v4_extraction_with_select(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test V4 extraction with field selection."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
            "query_options": {
                    "select_fields": ["ID", "Name", "Price"],
                },
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "Products", min_rows=5)

        # Verify only selected fields are present
        assert "ID" in rows[0]
        assert "Name" in rows[0]
        assert "Price" in rows[0]
        assert "Category" not in rows[0]

    @respx.mock
    def test_v4_extraction_with_filter(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test V4 extraction with filter expression."""
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

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "Products", min_rows=1)

        # All returned rows should have Category = Electronics
        for row in rows:
            assert row["Category"] == "Electronics"

    @respx.mock
    def test_v4_extraction_with_pagination(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test V4 extraction with pagination."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
            "pagination_defaults": [{
                    "page_size": 2,  # Small page size to test pagination
                }],
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "Products", min_rows=5)
        assert len(rows) == 5  # Should get all records despite small page size

    @respx.mock
    def test_v4_extraction_with_max_records(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test V4 extraction with max_records limit."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
            "pagination_defaults": [{
                    "max_records": 3,
                }],
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "Products", min_rows=1)
        assert len(rows) == 3  # Should limit to max_records


class TestODataV2BasicExtraction:
    """Test basic extraction from OData V2 service."""

    @respx.mock
    def test_v2_basic_extraction(
        self, respx_mock, mock_v2_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test basic V2 extraction with all business partners."""
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

        run_component_with_datadir(datadir)

        rows = verify_output_table(
            datadir,
            "A_BusinessPartner",
            min_rows=5,
            expected_columns=["BusinessPartner", "BusinessPartnerName", "BusinessPartnerCategory"],
        )

        assert len(rows) == 5
        assert rows[0]["BusinessPartnerName"] == "Acme Corporation"

    @respx.mock
    def test_v2_extraction_with_select(
        self, respx_mock, mock_v2_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test V2 extraction with field selection."""
        mock_v2_server.setup(respx_mock)

        config = {
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "A_BusinessPartner",
            "query_options": {
                    "select_fields": ["BusinessPartner", "BusinessPartnerName"],
                },
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "A_BusinessPartner", min_rows=5)

        # Verify only selected fields are present
        assert "BusinessPartner" in rows[0]
        assert "BusinessPartnerName" in rows[0]
        assert "OrganizationBPName1" not in rows[0]

    @respx.mock
    def test_v2_extraction_with_filter(
        self, respx_mock, mock_v2_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test V2 extraction with filter expression."""
        mock_v2_server.setup(respx_mock)

        config = {
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "A_BusinessPartner",
            "query_options": {
                    "filter_expression": "BusinessPartnerCategory eq '1'",
                },
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "A_BusinessPartner", min_rows=1)

        # All returned rows should have BusinessPartnerCategory = 1
        for row in rows:
            assert row["BusinessPartnerCategory"] == "1"


class TestIncrementalExtraction:
    """Test incremental extraction with state management."""

    @respx.mock
    def test_v4_incremental_first_run(
        self,
        respx_mock, mock_v4_server,
        datadir_factory,
        run_component_with_datadir,
        verify_output_table,
        verify_state,
    ):
        """Test first run of incremental extraction (no state)."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
            "fetching_options": {
                    "fetch_type": "incremental",
                    "incremental_field": "LastModified",
                },
            "destination": {
                    "load_type": "incremental",
                    "primary_key": ["ID"],
                },
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        # Verify all records were extracted
        rows = verify_output_table(datadir, "Products", min_rows=5)
        assert len(rows) == 5

        # Verify state was saved with last incremental value
        state = verify_state(datadir)
        assert "entity_states" in state
        assert "Products" in state["entity_states"]
        assert state["entity_states"]["Products"]["last_incremental_value"] is not None
        assert state["entity_states"]["Products"]["records_synced"] == 5

    @respx.mock
    def test_v4_incremental_subsequent_run(
        self,
        respx_mock, mock_v4_server,
        datadir_factory,
        run_component_with_datadir,
        verify_output_table,
        verify_state,
    ):
        """Test subsequent run of incremental extraction (with state)."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
            "fetching_options": {
                    "fetch_type": "incremental",
                    "incremental_field": "LastModified",
                },
            "destination": {
                    "load_type": "incremental",
                    "primary_key": ["ID"],
                },
        }

        # Provide initial state - only records after 2024-01-16 should be fetched
        in_state = {
            "entity_states": {
                "Products": {
                    "last_incremental_value": "2024-01-16T00:00:00Z",
                    "last_sync_timestamp": "2024-01-16T10:00:00Z",
                    "records_synced": 2,
                }
            }
        }
        datadir = datadir_factory(config, in_state=in_state)

        run_component_with_datadir(datadir)

        # Should only get records with LastModified > 2024-01-16T00:00:00Z
        # This includes ID 2 (2024-01-16T09:15:00Z), ID 3, 4, 5
        rows = verify_output_table(datadir, "Products", min_rows=1)
        assert len(rows) == 4  # IDs 2, 3, 4, 5
        assert rows[0]["ID"] == "2"
        assert rows[1]["ID"] == "3"
        assert rows[2]["ID"] == "4"
        assert rows[3]["ID"] == "5"

        # Verify state was updated
        state = verify_state(datadir)
        assert state["entity_states"]["Products"]["records_synced"] == 4
        # Last incremental value should be updated to latest record
        assert state["entity_states"]["Products"]["last_incremental_value"] > "2024-01-16T00:00:00Z"

    @respx.mock
    def test_v2_incremental_with_datetime(
        self,
        respx_mock, mock_v2_server,
        datadir_factory,
        run_component_with_datadir,
        verify_output_table,
        verify_state,
    ):
        """Test V2 incremental extraction with datetime field."""
        mock_v2_server.setup(respx_mock)

        config = {
            "service_url": mock_v2_server.base_url,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "A_BusinessPartner",
            "fetching_options": {
                    "fetch_type": "incremental",
                    "incremental_field": "LastChangeDateTime",
                },
            "destination": {
                    "load_type": "incremental",
                    "primary_key": ["BusinessPartner"],
                },
        }

        # Provide initial state
        in_state = {
            "entity_states": {
                "A_BusinessPartner": {
                    "last_incremental_value": "2024-01-24T00:00:00",
                    "last_sync_timestamp": "2024-01-24T10:00:00Z",
                    "records_synced": 2,
                }
            }
        }
        datadir = datadir_factory(config, in_state=in_state)

        run_component_with_datadir(datadir)

        # Should extract records with LastChangeDateTime > 2024-01-24
        rows = verify_output_table(datadir, "A_BusinessPartner", min_rows=1)

        # Verify state was updated
        state = verify_state(datadir)
        assert "A_BusinessPartner" in state["entity_states"]
        assert state["entity_states"]["A_BusinessPartner"]["last_incremental_value"] is not None


class TestSyncActions:
    """Test sync actions with mocked servers."""

    @respx.mock
    def test_test_connection_v4_success(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test successful connection test for V4."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
        }
        datadir = datadir_factory(config)

        # Run testConnection sync action
        comp = run_sync_action_with_datadir(datadir, "testConnection")

        # Check that connection was successful (would write to stdout in real scenario)
        # For now, just verify no exception was raised
        assert comp is not None

    @respx.mock
    def test_test_connection_v2_success(self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir):
        """Test successful connection test for V2."""
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
    def test_load_entities_v4(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test loadEntities sync action for V4."""
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

        # Verify that entity sets were loaded
        # In a real test, we'd check the JSON output
        assert comp is not None

    @respx.mock
    def test_load_entities_v2(self, respx_mock, mock_v2_server, datadir_factory, run_sync_action_with_datadir):
        """Test loadEntities sync action for V2."""
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
    def test_load_fields_v4(self, respx_mock, mock_v4_server, datadir_factory, run_sync_action_with_datadir):
        """Test loadFields sync action for V4."""
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
        """Test loadFields sync action for V2."""
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


class TestSAPCatalog:
    """Test SAP Service Catalog browsing."""

    @respx.mock
    def test_load_catalog_services(
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

        # Should return list of services instead of entity sets
        assert comp is not None


class TestErrorScenarios:
    """Test error handling scenarios."""

    @respx.mock
    def test_authentication_error(self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir):
        """Test handling of authentication errors."""
        # Setup server to return 401
        respx_mock.get(f"{mock_v4_server.base_url}/$metadata").mock(
            return_value=httpx.Response(401, content="Unauthorized")
        )

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "wrong_user",
            "#password": "wrong_password",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        # Should raise an exception
        with pytest.raises(Exception):
            run_component_with_datadir(datadir)

    @respx.mock
    def test_missing_entity_set(self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir):
        """Test error when entity_set is not configured."""
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

        # Should complete without error (logs warning and returns)
        run_component_with_datadir(datadir)

        # No output table should be created
        out_tables_dir = datadir / "out" / "tables"
        csv_files = list(out_tables_dir.glob("*.csv"))
        assert len(csv_files) == 0

    def test_invalid_configuration(self, datadir_factory, run_component_with_datadir):
        """Test error with invalid configuration."""
        config = {
            # Missing required fields
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        # Should raise validation error
        with pytest.raises(Exception):
            run_component_with_datadir(datadir)

    @respx.mock
    def test_incremental_without_field(self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir):
        """Test error when incremental fetch is set without incremental_field."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
            "fetching_options": {
                    "fetch_type": "incremental",
                    # incremental_field not specified
                },
            "destination": {
                    "load_type": "incremental",
                    "primary_key": ["ID"],
                },
        }
        datadir = datadir_factory(config)

        # Should raise validation error
        with pytest.raises(Exception):
            run_component_with_datadir(datadir)


class TestSplitURLConfiguration:
    """Test split URL configuration (base_url + service_path)."""

    @respx.mock
    def test_v4_split_url(
        self, respx_mock, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test V4 extraction using base_url + service_path."""
        # Setup mock for split URL
        base_url = "https://api.example.com"
        service_path = "odata/v4"
        full_url = f"{base_url}/{service_path}"

        from tests.fixtures.mock_odata_server_respx import MockODataV4Server as V4Server

        server = V4Server(full_url)
        server.setup(respx_mock)

        config = {
            "base_url": base_url,
            "service_path": service_path,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "Products", min_rows=5)
        assert len(rows) == 5

    @respx.mock
    def test_v2_split_url(
        self, respx_mock, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test V2 extraction using base_url + service_path."""
        base_url = "https://sap-server.com"
        service_path = "sap/opu/odata/sap/API_BUSINESS_PARTNER"
        full_url = f"{base_url}/{service_path}"

        from tests.fixtures.mock_odata_server_respx import MockODataV2Server as V2Server

        server = V2Server(full_url)
        server.setup(respx_mock)

        config = {
            "base_url": base_url,
            "service_path": service_path,
            "odata_version": "v2",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "A_BusinessPartner",
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "A_BusinessPartner", min_rows=5)
        assert len(rows) == 5


class TestAuthenticationMethods:
    """Test different authentication methods."""

    @respx.mock
    def test_api_key_auth(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test API key authentication."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "apiKey",
            "#api_key": "test_api_key_12345",
            "api_key_header_name": "APIKey",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "Products", min_rows=5)
        assert len(rows) == 5

    @respx.mock
    @responses.activate
    def test_oauth_auth(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test OAuth 2.0 authentication."""
        # Mock OAuth token endpoint (uses requests library)
        token_url = "https://auth.example.com/oauth/token"
        responses.add(
            responses.POST,
            token_url,
            json={
                "access_token": "test_access_token_12345",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
            status=200,
        )

        # Mock OData endpoints (uses httpx)
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "oauth",
            "token_url": token_url,
            "client_id": "test_client_id",
            "#client_secret": "test_client_secret",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        rows = verify_output_table(datadir, "Products", min_rows=5)
        assert len(rows) == 5


class TestLoadTypeAndDestination:
    """Test load type and destination configuration."""

    @respx.mock
    def test_full_load(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir
    ):
        """Test full load (replace) to Keboola Storage."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
            "destination": {
                    "load_type": "full",
                },
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        # Verify manifest has incremental=false
        manifest_path = datadir / "out" / "tables" / "Products.csv.manifest"
        assert manifest_path.exists()

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest.get("incremental") is False

    @respx.mock
    def test_incremental_load_with_primary_key(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir
    ):
        """Test incremental load with primary key."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
            "destination": {
                    "load_type": "incremental",
                    "primary_key": ["ID"],
                },
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        # Verify manifest has incremental=true and primary_key
        manifest_path = datadir / "out" / "tables" / "Products.csv.manifest"
        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest.get("incremental") is True
        assert manifest.get("primary_key") == ["ID"]

    @respx.mock
    def test_custom_output_table_name(
        self, respx_mock, mock_v4_server, datadir_factory, run_component_with_datadir, verify_output_table
    ):
        """Test custom output table name."""
        mock_v4_server.setup(respx_mock)

        config = {
            "service_url": mock_v4_server.base_url,
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
            "destination": {
                    "output_table_name": "my_products",
                },
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        # Should use custom name
        rows = verify_output_table(datadir, "my_products", min_rows=5)
        assert len(rows) == 5


class TestCatalogWorkflow:
    """Test SAP Catalog workflow scenarios."""

    @respx.mock
    def test_catalog_path_priority_over_service_path(
        self,
        respx_mock,
        mock_v4_server,
        mock_catalog_server,
        datadir_factory,
        run_component_with_datadir,
        verify_output_table,
    ):
        """Test that service_path takes priority over catalog_path when both are set.

        This is the critical bug we fixed - when user browses catalog (catalog_path set)
        and then selects a service (service_path set), component should use service_path
        for extraction, not catalog_path.
        """
        # Setup both servers
        mock_v4_server.setup(respx_mock)
        mock_catalog_server.setup(respx_mock)

        config = {
            "base_url": "https://api.example.com",
            "catalog_path": "sap/opu/odata/IWFND/CATALOGSERVICE;v=2",  # This should be IGNORED
            "service_path": mock_v4_server.base_url.replace("https://api.example.com/", ""),  # This should be USED
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        # Should extract from service_path, not catalog_path
        run_component_with_datadir(datadir)

        # Should successfully extract Products from V4 server
        rows = verify_output_table(datadir, "Products", min_rows=5)
        assert len(rows) == 5
        assert rows[0]["Name"] == "Laptop"

    @respx.mock
    def test_catalog_only_for_browsing(
        self, respx_mock, mock_catalog_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test catalog_path is used only when service_path is not set (browsing mode)."""
        mock_catalog_server.setup(respx_mock)

        config = {
            "base_url": "https://api.example.com",
            "catalog_path": "sap/opu/odata/IWFND/CATALOGSERVICE;v=2",
            # No service_path - browsing mode
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
        }
        datadir = datadir_factory(config)

        # Should use catalog for loadEntities sync action
        comp = run_sync_action_with_datadir(datadir, "loadEntities")
        assert comp is not None

    @respx.mock
    def test_extraction_with_catalog_selected_service(
        self,
        respx_mock,
        mock_v4_server,
        datadir_factory,
        run_component_with_datadir,
        verify_output_table,
    ):
        """Test full workflow: user selects service from catalog and extracts data.

        Simulates:
        1. User sets base_url + catalog_path
        2. UI calls loadEntities sync action → returns service list
        3. User selects a service → writes to service_path field
        4. Component runs extraction using service_path
        """
        mock_v4_server.setup(respx_mock)

        # This is what config looks like AFTER user selects service from catalog
        config = {
            "base_url": "https://api.example.com",
            # catalog_path might still be set from browsing step, but should be ignored
            "service_path": mock_v4_server.base_url.replace("https://api.example.com/", ""),
            "odata_version": "v4",
            "auth_type": "basic",
            "username": "test_user",
            "#password": "test_password",
            "entity_set": "Products",
        }
        datadir = datadir_factory(config)

        run_component_with_datadir(datadir)

        # Should successfully extract using selected service
        rows = verify_output_table(datadir, "Products", min_rows=5)
        assert len(rows) == 5

    @respx.mock
    def test_catalog_url_conversion_in_load_entities(
        self, respx_mock, mock_catalog_server, datadir_factory, run_sync_action_with_datadir
    ):
        """Test that loadEntities converts internal catalog URLs to proxy-compatible paths.

        SAP catalog returns internal URLs like http://20.113.120.45:50000/sap/opu/odata/sap/SERVICE
        Component should convert these to proxy paths like http/keboola/connector/sap/opu/odata/sap/SERVICE
        """
        mock_catalog_server.setup(respx_mock)

        config = {
            "base_url": "https://26db83b8trial.it-cpitrial03-rt.cfapps.ap21.hana.ondemand.com",
            "catalog_path": "http/keboola/catalog",  # Contains "keboola" - triggers proxy path conversion
            "auth_type": "oauth",
            "token_url": "https://auth.example.com/oauth/token",
            "client_id": "test_client",
            "#client_secret": "test_secret",
        }
        datadir = datadir_factory(config)

        # Should return services with converted paths
        comp = run_sync_action_with_datadir(datadir, "loadEntities")
        assert comp is not None
        # Note: Actual validation of URL conversion would require inspecting sync action output

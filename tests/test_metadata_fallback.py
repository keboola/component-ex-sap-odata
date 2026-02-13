"""Tests for metadata fallback behavior when $metadata is not available."""

import pytest
import responses
from responses import matchers

from src.odata_client.auth import BasicAuthHandler
from src.odata_client.v2_client import ODataV2Client


class TestMetadataFallback:
    """Test metadata retrieval with fallback to service document."""

    @responses.activate
    def test_metadata_endpoint_available(self):
        """Test normal case where $metadata endpoint is available."""
        base_url = "http://example.com/odata.svc"

        # Mock $metadata endpoint (note: $ gets URL-encoded to %24)
        responses.add(
            responses.GET,
            f"{base_url}/%24metadata",
            body="""<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
    <edmx:DataServices xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
        <Schema Namespace="TestModel" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
            <EntityType Name="Product">
                <Key><PropertyRef Name="ProductID" /></Key>
                <Property Name="ProductID" Type="Edm.Int32" Nullable="false" />
                <Property Name="ProductName" Type="Edm.String" />
            </EntityType>
            <EntityContainer Name="TestContainer">
                <EntitySet Name="Products" EntityType="TestModel.Product" />
            </EntityContainer>
        </Schema>
    </edmx:DataServices>
</edmx:Edmx>""",
            status=200,
            content_type="application/xml",
        )

        auth_handler = BasicAuthHandler("user", "pass")
        client = ODataV2Client(base_url=base_url, auth_handler=auth_handler)

        # Get metadata should succeed
        metadata = client.get_metadata()

        assert metadata is not None
        assert len(metadata.entity_sets) == 1
        assert "Products" in metadata.entity_sets
        assert len(metadata.entity_sets["Products"].properties) == 2

    @responses.activate
    def test_metadata_not_found_fallback_to_service_document(self):
        """Test fallback to service document when $metadata returns 404."""
        base_url = "http://example.com/catalog"

        # Mock $metadata endpoint returning 404
        responses.add(
            responses.GET,
            f"{base_url}/%24metadata",
            status=404,
            body="<html><body>Not Found</body></html>",
        )

        # Mock service document (fallback)
        responses.add(
            responses.GET,
            base_url,
            json={
                "d": {
                    "EntitySets": [
                        "Products",
                        "Categories",
                        "Orders"
                    ]
                }
            },
            status=200,
        )

        auth_handler = BasicAuthHandler("user", "pass")
        client = ODataV2Client(base_url=base_url, auth_handler=auth_handler)

        # Get metadata should fall back to service document
        metadata = client.get_metadata()

        assert metadata is not None
        assert len(metadata.entity_sets) == 3
        assert "Products" in metadata.entity_sets
        assert "Categories" in metadata.entity_sets
        assert "Orders" in metadata.entity_sets

        # Entity sets from service document have no properties/keys
        assert metadata.entity_sets["Products"].properties == []
        assert metadata.entity_sets["Products"].key_properties == []

    @responses.activate
    def test_metadata_not_found_and_service_document_fails(self):
        """Test when both $metadata and service document fail."""
        base_url = "http://example.com/catalog"

        # Mock $metadata endpoint returning 404
        responses.add(
            responses.GET,
            f"{base_url}/%24metadata",
            status=404,
        )

        # Mock service document also failing
        responses.add(
            responses.GET,
            base_url,
            
            status=500,
            body="Internal Server Error",
        )

        auth_handler = BasicAuthHandler("user", "pass")
        client = ODataV2Client(base_url=base_url, auth_handler=auth_handler)

        # Get metadata should return empty metadata (not raise)
        metadata = client.get_metadata()

        assert metadata is not None
        assert len(metadata.entity_sets) == 0

    @responses.activate
    def test_metadata_auth_error_raises(self):
        """Test that authentication errors are still raised (not fallback)."""
        base_url = "http://example.com/odata.svc"

        # Mock $metadata endpoint returning 401
        responses.add(
            responses.GET,
            f"{base_url}/%24metadata",
            status=401,
            body="Unauthorized",
        )

        auth_handler = BasicAuthHandler("user", "pass")
        client = ODataV2Client(base_url=base_url, auth_handler=auth_handler)

        # Should raise UserException for auth error (not attempt fallback)
        with pytest.raises(Exception) as exc_info:
            client.get_metadata()

        assert "Authentication failed" in str(exc_info.value) or "401" in str(exc_info.value)

    @responses.activate
    def test_list_entity_sets_with_fallback(self):
        """Test list_entity_sets works with fallback metadata."""
        base_url = "http://example.com/catalog"

        # Mock $metadata endpoint returning 404
        responses.add(
            responses.GET,
            f"{base_url}/%24metadata",
            status=404,
        )

        # Mock service document
        responses.add(
            responses.GET,
            base_url,
            
            json={
                "d": {
                    "EntitySets": ["Products", "Orders"]
                }
            },
            status=200,
        )

        auth_handler = BasicAuthHandler("user", "pass")
        client = ODataV2Client(base_url=base_url, auth_handler=auth_handler)

        # list_entity_sets should work with fallback
        entity_sets = client.list_entity_sets()

        assert len(entity_sets) == 2
        assert entity_sets[0].name in ("Products", "Orders")
        assert entity_sets[1].name in ("Products", "Orders")

    @responses.activate
    def test_list_fields_with_no_metadata(self):
        """Test list_fields returns empty list when metadata is not available."""
        base_url = "http://example.com/catalog"

        # Mock $metadata endpoint returning 404
        responses.add(
            responses.GET,
            f"{base_url}/%24metadata",
            status=404,
        )

        # Mock service document also failing
        responses.add(
            responses.GET,
            base_url,
            
            status=404,
        )

        auth_handler = BasicAuthHandler("user", "pass")
        client = ODataV2Client(base_url=base_url, auth_handler=auth_handler)

        # list_fields should return empty list instead of raising
        fields = client.list_fields("Products")

        assert fields == []

    @responses.activate
    def test_metadata_caching_with_fallback(self):
        """Test that fallback metadata is cached properly."""
        base_url = "http://example.com/catalog"

        # Mock $metadata endpoint returning 404
        responses.add(
            responses.GET,
            f"{base_url}/%24metadata",
            status=404,
        )

        # Mock service document
        responses.add(
            responses.GET,
            base_url,
            
            json={
                "d": {
                    "EntitySets": ["Products"]
                }
            },
            status=200,
        )

        auth_handler = BasicAuthHandler("user", "pass")
        client = ODataV2Client(base_url=base_url, auth_handler=auth_handler)

        # First call should use fallback
        metadata1 = client.get_metadata()
        assert len(metadata1.entity_sets) == 1

        # Second call should use cached metadata (only 1 request to service document)
        metadata2 = client.get_metadata()
        assert len(metadata2.entity_sets) == 1
        assert metadata1 is metadata2  # Same object

        # Only 2 requests should have been made: $metadata (404) and service document
        assert len(responses.calls) == 2

    @responses.activate
    def test_force_refresh_with_fallback(self):
        """Test force_refresh works with fallback metadata."""
        base_url = "http://example.com/catalog"

        # Mock $metadata endpoint returning 404 (twice for force refresh)
        responses.add(
            responses.GET,
            f"{base_url}/%24metadata",
            status=404,
        )
        responses.add(
            responses.GET,
            f"{base_url}/%24metadata",
            status=404,
        )

        # Mock service document (twice)
        responses.add(
            responses.GET,
            base_url,
            
            json={
                "d": {
                    "EntitySets": ["Products"]
                }
            },
            status=200,
        )
        responses.add(
            responses.GET,
            base_url,
            
            json={
                "d": {
                    "EntitySets": ["Products", "Orders"]  # Changed
                }
            },
            status=200,
        )

        auth_handler = BasicAuthHandler("user", "pass")
        client = ODataV2Client(base_url=base_url, auth_handler=auth_handler)

        # First call
        metadata1 = client.get_metadata()
        assert len(metadata1.entity_sets) == 1

        # Force refresh should get updated entity sets
        metadata2 = client.get_metadata(force_refresh=True)
        assert len(metadata2.entity_sets) == 2

        # 4 requests total: 2x $metadata (404), 2x service document
        assert len(responses.calls) == 4

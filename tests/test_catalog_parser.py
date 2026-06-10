"""Tests for catalog_parser.py - parsing service catalogs and service documents."""

from src.odata_client.catalog_parser import CatalogParser
from src.odata_client.metadata import ODataVersion


class TestCatalogParser:
    """Test parsing of SAP service catalogs and OData service documents."""

    def test_parse_odata_v2_service_document(self):
        """Test parsing standard OData V2 service document."""
        data = {"d": {"EntitySets": ["Products", "Categories", "Orders", "Customers"]}}

        metadata = CatalogParser.parse_service_document(data, ODataVersion.V2)

        assert metadata.version == ODataVersion.V2
        assert len(metadata.entity_sets) == 4
        assert "Products" in metadata.entity_sets
        assert "Categories" in metadata.entity_sets
        assert "Orders" in metadata.entity_sets
        assert "Customers" in metadata.entity_sets

        # Check entity set structure
        products = metadata.entity_sets["Products"]
        assert products.name == "Products"
        assert products.entity_type == "Unknown.Products"  # Type unknown without metadata
        assert products.properties == []  # No properties without metadata
        assert products.key_properties == []  # No keys without metadata

    def test_parse_odata_v4_service_document(self):
        """Test parsing OData V4 service document."""
        data = {
            "value": [
                {"name": "Products", "kind": "EntitySet", "url": "Products"},
                {"name": "Categories", "kind": "EntitySet", "url": "Categories"},
                {"name": "Orders", "kind": "EntitySet", "url": "Orders"},
            ]
        }

        metadata = CatalogParser.parse_service_document(data, ODataVersion.V4)

        assert metadata.version == ODataVersion.V4
        assert len(metadata.entity_sets) == 3
        assert "Products" in metadata.entity_sets
        assert "Categories" in metadata.entity_sets
        assert "Orders" in metadata.entity_sets

    def test_parse_sap_catalog_format(self):
        """Test parsing SAP service catalog format (deferred entity sets)."""
        data = {
            "d": {
                "results": [
                    {
                        "ID": "SERVICE_001",
                        "Title": "Test Service",
                        "EntitySets": {
                            "__deferred": {
                                "uri": "http://example.com/catalog/ServiceCollection('SERVICE_001')/EntitySets"
                            }
                        },
                    }
                ]
            }
        }

        metadata = CatalogParser.parse_service_document(data, ODataVersion.V2)

        # SAP catalog has deferred entity sets - cannot extract without additional requests
        assert metadata.version == ODataVersion.V2
        assert len(metadata.entity_sets) == 0  # Cannot extract from deferred

    def test_parse_empty_service_document(self):
        """Test parsing empty service document."""
        data = {"d": {"EntitySets": []}}

        metadata = CatalogParser.parse_service_document(data, ODataVersion.V2)

        assert metadata.version == ODataVersion.V2
        assert len(metadata.entity_sets) == 0

    def test_parse_malformed_service_document(self):
        """Test parsing malformed service document."""
        data = {"invalid": "format"}

        metadata = CatalogParser.parse_service_document(data, ODataVersion.V2)

        assert metadata.version == ODataVersion.V2
        assert len(metadata.entity_sets) == 0

    def test_parse_null_service_document(self):
        """Test parsing null/empty service document."""
        metadata = CatalogParser.parse_service_document({}, ODataVersion.V2)

        assert metadata.version == ODataVersion.V2
        assert len(metadata.entity_sets) == 0

    def test_try_parse_from_response_with_service_document(self):
        """Test try_parse_from_response with valid service document."""
        data = {"d": {"EntitySets": ["Products", "Orders"]}}

        metadata = CatalogParser.try_parse_from_response(data, ODataVersion.V2)

        assert metadata is not None
        assert len(metadata.entity_sets) == 2

    def test_try_parse_from_response_with_invalid_data(self):
        """Test try_parse_from_response with invalid data."""
        data = {"invalid": "data"}

        metadata = CatalogParser.try_parse_from_response(data, ODataVersion.V2)

        # Should return metadata with empty entity sets, not None
        assert metadata is not None
        assert len(metadata.entity_sets) == 0

    def test_parse_service_document_with_mixed_types(self):
        """Test parsing service document with non-EntitySet items."""
        data = {
            "value": [
                {"name": "Products", "kind": "EntitySet", "url": "Products"},
                {"name": "GetOrders", "kind": "FunctionImport", "url": "GetOrders"},  # Not an EntitySet
                {"name": "Categories", "kind": "EntitySet", "url": "Categories"},
            ]
        }

        metadata = CatalogParser.parse_service_document(data, ODataVersion.V4)

        # Should only include EntitySets
        assert len(metadata.entity_sets) == 2
        assert "Products" in metadata.entity_sets
        assert "Categories" in metadata.entity_sets
        assert "GetOrders" not in metadata.entity_sets

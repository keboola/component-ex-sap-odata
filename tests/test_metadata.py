from pathlib import Path

import pytest

from odata_client.metadata import (
    EntityProperty,
    EntitySet,
    MetadataParser,
    NavigationProperty,
    ODataVersion,
)


@pytest.fixture
def fixtures_path() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def v2_metadata_xml(fixtures_path: Path) -> str:
    return (fixtures_path / "metadata_v2.xml").read_text()


@pytest.fixture
def v4_metadata_xml(fixtures_path: Path) -> str:
    return (fixtures_path / "metadata_v4.xml").read_text()


@pytest.fixture
def v4_multischema_metadata_xml(fixtures_path: Path) -> str:
    return (fixtures_path / "metadata_v4_multischema.xml").read_text()


class TestMetadataParser:
    def test_detect_version_v2(self, v2_metadata_xml: str) -> None:
        version = MetadataParser.detect_version(v2_metadata_xml)
        assert version == ODataVersion.V2

    def test_detect_version_v4(self, v4_metadata_xml: str) -> None:
        version = MetadataParser.detect_version(v4_metadata_xml)
        assert version == ODataVersion.V4

    def test_parse_v2_metadata(self, v2_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v2_metadata_xml, ODataVersion.V2)

        assert metadata.version == ODataVersion.V2
        assert len(metadata.entity_sets) == 2
        assert "BusinessPartnerSet" in metadata.entity_sets
        assert "AddressSet" in metadata.entity_sets

    def test_parse_v2_entity_properties(self, v2_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v2_metadata_xml, ODataVersion.V2)
        entity_set = metadata.get_entity_set("BusinessPartnerSet")

        assert entity_set is not None
        assert entity_set.name == "BusinessPartnerSet"
        assert len(entity_set.properties) == 6

        property_names = [p.name for p in entity_set.properties]
        assert "BusinessPartner" in property_names
        assert "BusinessPartnerName" in property_names
        assert "CreatedAt" in property_names
        assert "LastChangedAt" in property_names
        assert "IsActive" in property_names
        assert "Revenue" in property_names

    def test_parse_v2_key_properties(self, v2_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v2_metadata_xml, ODataVersion.V2)
        entity_set = metadata.get_entity_set("BusinessPartnerSet")

        assert entity_set is not None
        assert entity_set.key_properties == ["BusinessPartner"]

    def test_parse_v2_navigation_properties(self, v2_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v2_metadata_xml, ODataVersion.V2)
        entity_set = metadata.get_entity_set("BusinessPartnerSet")

        assert entity_set is not None
        assert len(entity_set.navigation_properties) == 1
        assert entity_set.navigation_properties[0].name == "to_Address"

    def test_parse_v4_metadata(self, v4_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v4_metadata_xml, ODataVersion.V4)

        assert metadata.version == ODataVersion.V4
        assert len(metadata.entity_sets) == 3
        assert "Products" in metadata.entity_sets
        assert "Categories" in metadata.entity_sets
        assert "Suppliers" in metadata.entity_sets

    def test_parse_v4_entity_properties(self, v4_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v4_metadata_xml, ODataVersion.V4)
        entity_set = metadata.get_entity_set("Products")

        assert entity_set is not None
        assert entity_set.name == "Products"
        assert len(entity_set.properties) == 7

        property_names = [p.name for p in entity_set.properties]
        assert "ProductID" in property_names
        assert "ProductName" in property_names
        assert "Price" in property_names
        assert "CreatedAt" in property_names
        assert "ModifiedAt" in property_names

    def test_parse_v4_key_properties(self, v4_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v4_metadata_xml, ODataVersion.V4)
        entity_set = metadata.get_entity_set("Products")

        assert entity_set is not None
        assert entity_set.key_properties == ["ProductID"]

    def test_parse_v4_navigation_properties(self, v4_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v4_metadata_xml, ODataVersion.V4)
        entity_set = metadata.get_entity_set("Products")

        assert entity_set is not None
        assert len(entity_set.navigation_properties) == 2

        nav_names = [np.name for np in entity_set.navigation_properties]
        assert "Category" in nav_names
        assert "Suppliers" in nav_names

    def test_parse_v4_multi_schema_entity_sets(self, v4_multischema_metadata_xml: str) -> None:
        """Regression test: EntityContainer in a different Schema element than EntityTypes.

        Northwind V4 uses two schemas: EntityTypes in 'NorthwindModel' and
        EntityContainer in 'ODataWebV4.Northwind.Model'. The parser must search
        all schemas so that it finds entity sets even when they are in a different
        schema than the EntityType definitions.
        """
        metadata = MetadataParser.parse(v4_multischema_metadata_xml, ODataVersion.V4)

        assert metadata.version == ODataVersion.V4
        assert len(metadata.entity_sets) == 2
        assert "Categories" in metadata.entity_sets
        assert "Products" in metadata.entity_sets

        # Properties must be resolved cross-schema (EntityType in schema 1, EntitySet in schema 2)
        categories = metadata.get_entity_set("Categories")
        assert categories is not None
        assert len(categories.properties) == 3
        assert categories.key_properties == ["CategoryID"]

        products = metadata.get_entity_set("Products")
        assert products is not None
        assert len(products.properties) == 3
        assert products.key_properties == ["ProductID"]

    def test_parse_auto_detection_v2(self, v2_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v2_metadata_xml, ODataVersion.AUTO)
        assert metadata.version == ODataVersion.V2

    def test_parse_auto_detection_v4(self, v4_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v4_metadata_xml, ODataVersion.AUTO)
        assert metadata.version == ODataVersion.V4

    def test_list_entity_sets(self, v2_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v2_metadata_xml, ODataVersion.V2)
        entity_sets = metadata.list_entity_sets()

        assert len(entity_sets) == 2
        names = [es.name for es in entity_sets]
        assert "BusinessPartnerSet" in names
        assert "AddressSet" in names

    def test_get_nonexistent_entity_set(self, v2_metadata_xml: str) -> None:
        metadata = MetadataParser.parse(v2_metadata_xml, ODataVersion.V2)
        entity_set = metadata.get_entity_set("NonExistent")

        assert entity_set is None


class TestEntityProperty:
    def test_to_dict(self) -> None:
        prop = EntityProperty(
            name="TestProp",
            edm_type="Edm.String",
            nullable=True,
            max_length=100,
            precision=None,
            scale=None,
        )

        result = prop.to_dict()
        assert result["name"] == "TestProp"
        assert result["edm_type"] == "Edm.String"
        assert result["nullable"] is True
        assert result["max_length"] == 100


class TestNavigationProperty:
    def test_to_dict(self) -> None:
        nav_prop = NavigationProperty(
            name="to_Address",
            target_entity="Address",
            is_collection=True,
        )

        result = nav_prop.to_dict()
        assert result["name"] == "to_Address"
        assert result["target_entity"] == "Address"
        assert result["is_collection"] is True


class TestEntitySet:
    def test_to_dict(self) -> None:
        entity_set = EntitySet(
            name="TestSet",
            entity_type="Test.Entity",
            properties=[
                EntityProperty(name="ID", edm_type="Edm.String", nullable=False),
            ],
            key_properties=["ID"],
            navigation_properties=[
                NavigationProperty(name="Related", target_entity="Other", is_collection=False),
            ],
        )

        result = entity_set.to_dict()
        assert result["name"] == "TestSet"
        assert result["entity_type"] == "Test.Entity"
        assert len(result["properties"]) == 1
        assert result["key_properties"] == ["ID"]
        assert len(result["navigation_properties"]) == 1

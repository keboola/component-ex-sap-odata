"""Tests for SAP annotation parsing in OData V2 metadata."""
import sys
sys.path.insert(0, 'src')

from odata_client.metadata import MetadataParser, ODataVersion


def test_parse_sap_annotations_v2():
    """Test parsing SAP-specific annotations from V2 metadata."""
    metadata_xml = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="API_BP"
            xmlns="http://schemas.microsoft.com/ado/2008/09/edm"
            xmlns:sap="http://www.sap.com/Protocols/SAPData">
      <EntityType Name="A_BusinessPartnerType">
        <Key>
          <PropertyRef Name="BusinessPartner"/>
        </Key>
        <Property Name="BusinessPartner" Type="Edm.String" Nullable="false" MaxLength="10"
                  sap:label="Business Partner"
                  sap:creatable="false"
                  sap:updatable="false"
                  sap:filterable="true"/>
        <Property Name="BusinessPartnerName" Type="Edm.String" MaxLength="81"
                  sap:label="BP Name"
                  sap:quickinfo="Business Partner Full Name"
                  sap:creatable="true"
                  sap:updatable="true"
                  sap:filterable="true"/>
        <Property Name="FormOfAddress" Type="Edm.String" MaxLength="4"
                  sap:label="Title"
                  sap:quickinfo="Form of Address"
                  sap:filterable="false"/>
      </EntityType>
      <EntityContainer Name="API_BP_Entities" m:IsDefaultEntityContainer="true">
        <EntitySet Name="A_BusinessPartner" EntityType="API_BP.A_BusinessPartnerType"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

    metadata = MetadataParser.parse(metadata_xml, ODataVersion.V2)
    entity = metadata.get_entity_set("A_BusinessPartner")

    assert entity is not None
    assert len(entity.properties) == 3

    # Test BusinessPartner field with annotations
    bp_field = next(p for p in entity.properties if p.name == "BusinessPartner")
    assert bp_field.sap_label == "Business Partner"
    assert bp_field.sap_filterable is True
    assert bp_field.sap_creatable is False
    assert bp_field.sap_updatable is False
    assert bp_field.sap_quickinfo is None

    # Test BusinessPartnerName with quickinfo
    name_field = next(p for p in entity.properties if p.name == "BusinessPartnerName")
    assert name_field.sap_label == "BP Name"
    assert name_field.sap_quickinfo == "Business Partner Full Name"
    assert name_field.sap_filterable is True
    assert name_field.sap_creatable is True
    assert name_field.sap_updatable is True

    # Test FormOfAddress with filterable=false
    form_field = next(p for p in entity.properties if p.name == "FormOfAddress")
    assert form_field.sap_label == "Title"
    assert form_field.sap_quickinfo == "Form of Address"
    assert form_field.sap_filterable is False


def test_sap_annotations_in_to_dict():
    """Test that SAP annotations are included in to_dict() output."""
    metadata_xml = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="API_BP"
            xmlns="http://schemas.microsoft.com/ado/2008/09/edm"
            xmlns:sap="http://www.sap.com/Protocols/SAPData">
      <EntityType Name="TestType">
        <Key><PropertyRef Name="ID"/></Key>
        <Property Name="ID" Type="Edm.String" sap:label="Identifier" sap:filterable="true"/>
      </EntityType>
      <EntityContainer Name="API_BP_Entities" m:IsDefaultEntityContainer="true">
        <EntitySet Name="TestSet" EntityType="API_BP.TestType"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

    metadata = MetadataParser.parse(metadata_xml, ODataVersion.V2)
    entity = metadata.get_entity_set("TestSet")

    field = entity.properties[0]
    field_dict = field.to_dict()

    assert field_dict["name"] == "ID"
    assert field_dict["sap_label"] == "Identifier"
    assert field_dict["sap_filterable"] is True


def test_missing_sap_annotations():
    """Test that missing SAP annotations result in None values."""
    metadata_xml = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="API_BP" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityType Name="TestType">
        <Key><PropertyRef Name="ID"/></Key>
        <Property Name="ID" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="API_BP_Entities" m:IsDefaultEntityContainer="true">
        <EntitySet Name="TestSet" EntityType="API_BP.TestType"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

    metadata = MetadataParser.parse(metadata_xml, ODataVersion.V2)
    entity = metadata.get_entity_set("TestSet")

    field = entity.properties[0]
    assert field.sap_label is None
    assert field.sap_quickinfo is None
    assert field.sap_filterable is None
    assert field.sap_creatable is None
    assert field.sap_updatable is None


if __name__ == "__main__":
    test_parse_sap_annotations_v2()
    test_sap_annotations_in_to_dict()
    test_missing_sap_annotations()
    print("✅ All SAP annotation tests passed!")

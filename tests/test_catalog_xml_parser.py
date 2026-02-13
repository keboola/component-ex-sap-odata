"""Tests for SAP Catalog XML/ATOM parsing."""
import pytest

from src.odata_client.catalog_parser import CatalogParser, ServiceInfo


class TestCatalogXMLParser:
    """Test XML/ATOM parsing for SAP Service Catalog."""

    def test_parse_sap_catalog_xml_basic(self):
        """Test parsing basic SAP catalog ATOM feed."""
        xml_text = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
  <entry>
    <id>https://example.com/sap/opu/odata/IWFND/CATALOGSERVICE;v=2/ServiceCollection('SERVICE_001')</id>
    <title type="text">Service Collection</title>
    <content type="application/xml">
      <m:properties>
        <d:ID>SERVICE_001</d:ID>
        <d:Title>Test Service 1</d:Title>
        <d:Description>This is test service 1</d:Description>
        <d:ServiceUrl>http://example.com/sap/opu/odata/TEST/SERVICE1</d:ServiceUrl>
        <d:MetadataUrl>http://example.com/sap/opu/odata/TEST/SERVICE1/$metadata</d:MetadataUrl>
      </m:properties>
    </content>
  </entry>
  <entry>
    <id>https://example.com/sap/opu/odata/IWFND/CATALOGSERVICE;v=2/ServiceCollection('SERVICE_002')</id>
    <title type="text">Service Collection</title>
    <content type="application/xml">
      <m:properties>
        <d:ID>SERVICE_002</d:ID>
        <d:Title>Test Service 2</d:Title>
        <d:Description>This is test service 2</d:Description>
        <d:ServiceUrl>http://example.com/sap/opu/odata/TEST/SERVICE2</d:ServiceUrl>
        <d:MetadataUrl>http://example.com/sap/opu/odata/TEST/SERVICE2/$metadata</d:MetadataUrl>
      </m:properties>
    </content>
  </entry>
</feed>"""

        services = CatalogParser.parse_sap_catalog_xml(xml_text)

        assert len(services) == 2
        assert services[0].id == "SERVICE_001"
        assert services[0].title == "Test Service 1"
        assert services[0].description == "This is test service 1"
        assert services[0].service_url == "http://example.com/sap/opu/odata/TEST/SERVICE1"
        assert services[0].metadata_url == "http://example.com/sap/opu/odata/TEST/SERVICE1/$metadata"

        assert services[1].id == "SERVICE_002"
        assert services[1].title == "Test Service 2"

    def test_parse_sap_catalog_xml_minimal(self):
        """Test parsing catalog with minimal fields (no description, no URLs)."""
        xml_text = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
  <entry>
    <content type="application/xml">
      <m:properties>
        <d:ID>SERVICE_MIN</d:ID>
        <d:Title>Minimal Service</d:Title>
      </m:properties>
    </content>
  </entry>
</feed>"""

        services = CatalogParser.parse_sap_catalog_xml(xml_text)

        assert len(services) == 1
        assert services[0].id == "SERVICE_MIN"
        assert services[0].title == "Minimal Service"
        assert services[0].description == ""
        assert services[0].service_url is None
        assert services[0].metadata_url is None

    def test_parse_sap_catalog_xml_no_title(self):
        """Test parsing when title is missing (uses ID as title)."""
        xml_text = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
  <entry>
    <content type="application/xml">
      <m:properties>
        <d:ID>NO_TITLE_SERVICE</d:ID>
        <d:Description>Service without title</d:Description>
      </m:properties>
    </content>
  </entry>
</feed>"""

        services = CatalogParser.parse_sap_catalog_xml(xml_text)

        assert len(services) == 1
        assert services[0].id == "NO_TITLE_SERVICE"
        assert services[0].title == "NO_TITLE_SERVICE"  # Uses ID as title
        assert services[0].description == "Service without title"

    def test_parse_sap_catalog_xml_empty_feed(self):
        """Test parsing empty ATOM feed."""
        xml_text = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
</feed>"""

        services = CatalogParser.parse_sap_catalog_xml(xml_text)

        assert len(services) == 0

    def test_parse_sap_catalog_xml_skip_missing_id(self):
        """Test that entries without ID are skipped."""
        xml_text = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
  <entry>
    <content type="application/xml">
      <m:properties>
        <d:ID>VALID_SERVICE</d:ID>
        <d:Title>Valid Service</d:Title>
      </m:properties>
    </content>
  </entry>
  <entry>
    <content type="application/xml">
      <m:properties>
        <d:Title>Invalid Service - No ID</d:Title>
      </m:properties>
    </content>
  </entry>
</feed>"""

        services = CatalogParser.parse_sap_catalog_xml(xml_text)

        # Only the valid entry should be included
        assert len(services) == 1
        assert services[0].id == "VALID_SERVICE"

    def test_parse_sap_catalog_xml_invalid_xml(self):
        """Test handling of invalid XML."""
        xml_text = "This is not XML at all"

        services = CatalogParser.parse_sap_catalog_xml(xml_text)

        # Should return empty list on parse error
        assert len(services) == 0

    def test_parse_sap_catalog_xml_malformed_xml(self):
        """Test handling of malformed XML."""
        xml_text = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <content>
      <!-- Missing closing tag -->
</feed>"""

        services = CatalogParser.parse_sap_catalog_xml(xml_text)

        # Should return empty list on parse error
        assert len(services) == 0

    def test_parse_sap_catalog_xml_real_world_example(self):
        """Test parsing with realistic SAP catalog structure."""
        xml_text = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xml:base="http://20.113.120.45:50000/sap/opu/odata/IWFND/CATALOGSERVICE;v=2/">
  <id>http://20.113.120.45:50000/sap/opu/odata/IWFND/CATALOGSERVICE;v=2/ServiceCollection</id>
  <title type="text">ServiceCollection</title>
  <updated>2024-01-01T00:00:00Z</updated>
  <author>
    <name />
  </author>
  <entry>
    <id>http://20.113.120.45:50000/sap/opu/odata/IWFND/CATALOGSERVICE;v=2/ServiceCollection('ZFCLM_CASH_ALI_SRV_0001')</id>
    <title type="text">ServiceCollection</title>
    <updated>2024-01-01T00:00:00Z</updated>
    <category term="IWFND.ServiceCollection" scheme="http://schemas.microsoft.com/ado/2007/08/dataservices/scheme" />
    <link href="ServiceCollection('ZFCLM_CASH_ALI_SRV_0001')" rel="edit" title="ServiceCollection" />
    <link href="ServiceCollection('ZFCLM_CASH_ALI_SRV_0001')/TechnicalServiceVersionSet" rel="http://schemas.microsoft.com/ado/2007/08/dataservices/related/TechnicalServiceVersionSet" type="application/atom+xml;type=feed" title="TechnicalServiceVersionSet" />
    <content type="application/xml">
      <m:properties>
        <d:ID>ZFCLM_CASH_ALI_SRV_0001</d:ID>
        <d:Title>FCLM_CASH_ALI_SRV</d:Title>
        <d:Author>SAP</d:Author>
        <d:Description>Detect Abnormal Liquidity Items</d:Description>
        <d:ImageUrl></d:ImageUrl>
        <d:ServiceUrl>/sap/opu/odata/sap/FCLM_CASH_ALI_SRV</d:ServiceUrl>
        <d:MetadataUrl>/sap/opu/odata/sap/FCLM_CASH_ALI_SRV/$metadata</d:MetadataUrl>
      </m:properties>
    </content>
  </entry>
</feed>"""

        services = CatalogParser.parse_sap_catalog_xml(xml_text)

        assert len(services) == 1
        assert services[0].id == "ZFCLM_CASH_ALI_SRV_0001"
        assert services[0].title == "FCLM_CASH_ALI_SRV"
        assert services[0].description == "Detect Abnormal Liquidity Items"
        assert services[0].service_url == "/sap/opu/odata/sap/FCLM_CASH_ALI_SRV"
        assert services[0].metadata_url == "/sap/opu/odata/sap/FCLM_CASH_ALI_SRV/$metadata"

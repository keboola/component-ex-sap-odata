"""Parser for SAP Service Catalog responses (alternative to $metadata)."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from .metadata import EntitySet, ODataMetadata, ODataVersion

JsonDict = dict[str, Any]


@dataclass
class ServiceInfo:
    """Information about an OData service from SAP catalog."""

    id: str
    title: str
    description: str
    service_url: str | None = None
    metadata_url: str | None = None

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "service_url": self.service_url,
            "metadata_url": self.metadata_url,
        }


class CatalogParser:
    """Parse SAP Service Catalog responses when $metadata is not available."""

    @classmethod
    def parse_sap_catalog_xml(cls, xml_text: str) -> list[ServiceInfo]:
        """Parse SAP Service Catalog from ATOM/XML format.

        ATOM feed format:
        <feed xmlns="http://www.w3.org/2005/Atom" ...>
          <entry>
            <id>SERVICE_001</id>
            <title>Service Title</title>
            <content type="application/xml">
              <m:properties>
                <d:ID>SERVICE_001</d:ID>
                <d:Title>Service Title</d:Title>
                <d:Description>Service Description</d:Description>
                <d:ServiceUrl>http://...</d:ServiceUrl>
                <d:MetadataUrl>http://.../$metadata</d:MetadataUrl>
              </m:properties>
            </content>
          </entry>
        </feed>

        Args:
            xml_text: Raw XML response from SAP catalog

        Returns:
            List of ServiceInfo objects
        """
        services = []

        try:
            # Parse XML
            root = ET.fromstring(xml_text)

            # Define namespaces used in ATOM feeds
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'm': 'http://schemas.microsoft.com/ado/2007/08/dataservices/metadata',
                'd': 'http://schemas.microsoft.com/ado/2007/08/dataservices',
            }

            # Find all entry elements
            entries = root.findall('.//atom:entry', namespaces)

            for entry in entries:
                # Get properties from content/m:properties
                properties = entry.find('.//m:properties', namespaces)
                if properties is not None:
                    # Extract service information
                    service_id_elem = properties.find('d:ID', namespaces)
                    title_elem = properties.find('d:Title', namespaces)
                    description_elem = properties.find('d:Description', namespaces)
                    service_url_elem = properties.find('d:ServiceUrl', namespaces)
                    metadata_url_elem = properties.find('d:MetadataUrl', namespaces)

                    service_id = service_id_elem.text if service_id_elem is not None and service_id_elem.text else ""
                    title = title_elem.text if title_elem is not None and title_elem.text else ""
                    description = description_elem.text if description_elem is not None and description_elem.text else ""
                    service_url = service_url_elem.text if service_url_elem is not None and service_url_elem.text else None
                    metadata_url = metadata_url_elem.text if metadata_url_elem is not None and metadata_url_elem.text else None

                    # Only include if has ID
                    if service_id:
                        services.append(
                            ServiceInfo(
                                id=service_id,
                                title=title or service_id,
                                description=description or "",
                                service_url=service_url,
                                metadata_url=metadata_url,
                            )
                        )

            logging.info(f"Parsed {len(services)} services from SAP catalog XML")
            return services

        except ET.ParseError as e:
            logging.error(f"Failed to parse SAP catalog XML: {e}")
            return []
        except Exception as e:
            logging.error(f"Unexpected error parsing SAP catalog XML: {e}")
            return []

    @classmethod
    def parse_sap_catalog(cls, data: JsonDict) -> list[ServiceInfo]:
        """Parse SAP Service Catalog to extract list of available services.

        SAP Catalog format:
        {
          "d": {
            "results": [
              {
                "ID": "SERVICE_001",
                "Title": "Service Title",
                "Description": "Service Description",
                "ServiceUrl": "http://...",
                "MetadataUrl": "http://.../$metadata",
                ...
              }
            ]
          }
        }

        Args:
            data: Parsed JSON response from SAP catalog

        Returns:
            List of ServiceInfo objects
        """
        services = []

        if isinstance(data, dict) and "d" in data:
            d_value = data["d"]

            # SAP Catalog format with results array
            if isinstance(d_value, dict) and "results" in d_value:
                results = d_value["results"]
                if isinstance(results, list):
                    for item in results:
                        if isinstance(item, dict):
                            service_id = item.get("ID", "")
                            title = item.get("Title", "")
                            description = item.get("Description", "")
                            service_url = item.get("ServiceUrl")
                            metadata_url = item.get("MetadataUrl")

                            # Only include if has ID
                            if service_id:
                                services.append(
                                    ServiceInfo(
                                        id=service_id,
                                        title=title or service_id,
                                        description=description or "",
                                        service_url=service_url,
                                        metadata_url=metadata_url,
                                    )
                                )

        logging.info(f"Parsed {len(services)} services from SAP catalog")
        return services

    @classmethod
    def is_sap_catalog(cls, data: JsonDict) -> bool:
        """Check if the response is a SAP Service Catalog.

        Args:
            data: Parsed JSON response

        Returns:
            True if this is a SAP catalog response
        """
        if not isinstance(data, dict):
            return False

        # Check for catalog structure
        if "d" in data and isinstance(data["d"], dict):
            d_value = data["d"]
            if "results" in d_value and isinstance(d_value["results"], list):
                # Check if first item looks like a service entry
                results = d_value["results"]
                if results and isinstance(results[0], dict):
                    first_item = results[0]
                    # SAP catalog services have ID, Title, ServiceUrl
                    return bool(
                        first_item.get("ID")
                        and first_item.get("Title")
                        and (first_item.get("ServiceUrl") or first_item.get("MetadataUrl"))
                    )
        return False

    @classmethod
    def parse_service_document(cls, data: JsonDict, version: ODataVersion = ODataVersion.V2) -> ODataMetadata:
        """Parse OData service document to extract entity sets.

        Service document format (OData V2/V4):
        {
          "d": {
            "EntitySets": ["Products", "Categories", "Orders"]
          }
        }

        Or for SAP Catalog:
        {
          "d": {
            "results": [
              {
                "ID": "SERVICE_001",
                "EntitySets": {"__deferred": {...}}
              }
            ]
          }
        }

        Args:
            data: Parsed JSON response
            version: OData version (V2 or V4)

        Returns:
            ODataMetadata with basic entity set information
        """
        metadata = ODataMetadata(version=version)

        # Try OData V2/V4 service document format
        if isinstance(data, dict) and "d" in data:
            d_value = data["d"]

            # Standard service document with EntitySets array
            if isinstance(d_value, dict) and "EntitySets" in d_value:
                entity_sets = d_value["EntitySets"]
                if isinstance(entity_sets, list):
                    for entity_set_name in entity_sets:
                        if isinstance(entity_set_name, str):
                            metadata.entity_sets[entity_set_name] = EntitySet(
                                name=entity_set_name,
                                entity_type=f"Unknown.{entity_set_name}",  # Type unknown without metadata
                                properties=[],  # Properties unknown without metadata
                                key_properties=[],  # Keys unknown without metadata
                            )
                    logging.info(f"Parsed {len(metadata.entity_sets)} entity sets from service document")
                    return metadata

            # SAP Catalog format with results array
            if isinstance(d_value, dict) and "results" in d_value:
                results = d_value["results"]
                if isinstance(results, list) and results:
                    logging.warning(
                        "Catalog response detected but cannot extract entity sets without accessing deferred URLs"
                    )
                    # We cannot get entity sets from catalog without making additional requests
                    # to the deferred EntitySets URLs, which are internal and not accessible
                    return metadata

        # V4 format (no "d" wrapper)
        if isinstance(data, dict) and "value" in data:
            value = data["value"]
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        name = item.get("name")
                        kind = item.get("kind")
                        if name and kind == "EntitySet":
                            metadata.entity_sets[name] = EntitySet(
                                name=name,
                                entity_type=f"Unknown.{name}",
                                properties=[],
                                key_properties=[],
                            )
                logging.info(f"Parsed {len(metadata.entity_sets)} entity sets from V4 service document")
                return metadata

        logging.warning("Could not parse service document - unknown format")
        return metadata

    @classmethod
    def try_parse_from_response(cls, data: JsonDict, version: ODataVersion = ODataVersion.V2) -> ODataMetadata | None:
        """Try to parse entity sets from any OData response.

        When metadata is not available, we can try to infer entity sets from:
        1. Service document response
        2. First page of data (extract keys from response structure)

        Args:
            data: Any JSON response from the service
            version: OData version

        Returns:
            ODataMetadata if parsing succeeded, None otherwise
        """
        try:
            return cls.parse_service_document(data, version)
        except Exception as e:
            logging.debug(f"Failed to parse catalog/service document: {e}")
            return None

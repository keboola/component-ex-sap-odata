from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from lxml import etree


class ODataVersion(str, Enum):
    V2 = "v2"
    V4 = "v4"
    AUTO = "auto"


@dataclass
class EntityProperty:
    name: str
    edm_type: str
    nullable: bool = True
    max_length: int | None = None
    precision: int | None = None
    scale: int | None = None

    def to_dict(self) -> dict[str, str | int | bool | list | dict | None]:
        return {
            "name": self.name,
            "edm_type": self.edm_type,
            "nullable": self.nullable,
            "max_length": self.max_length,
            "precision": self.precision,
            "scale": self.scale,
        }


@dataclass
class NavigationProperty:
    name: str
    target_entity: str
    is_collection: bool = False

    def to_dict(self) -> dict[str, str | int | bool | list | dict | None]:
        return {
            "name": self.name,
            "target_entity": self.target_entity,
            "is_collection": self.is_collection,
        }


@dataclass
class EntitySet:
    name: str
    entity_type: str
    properties: list[EntityProperty] = field(default_factory=list)
    key_properties: list[str] = field(default_factory=list)
    navigation_properties: list[NavigationProperty] = field(default_factory=list)

    def to_dict(self) -> dict[str, str | int | bool | list | dict | None]:
        return {
            "name": self.name,
            "entity_type": self.entity_type,
            "properties": [p.to_dict() for p in self.properties],
            "key_properties": self.key_properties,
            "navigation_properties": [np.to_dict() for np in self.navigation_properties],
        }


@dataclass
class ODataMetadata:
    version: ODataVersion
    entity_sets: dict[str, EntitySet] = field(default_factory=dict)
    entity_types: dict[str, dict] = field(default_factory=dict)

    def get_entity_set(self, name: str) -> EntitySet | None:
        return self.entity_sets.get(name)

    def list_entity_sets(self) -> list[EntitySet]:
        return list(self.entity_sets.values())


class MetadataParser:
    V2_NAMESPACES = {
        "edmx": "http://schemas.microsoft.com/ado/2007/06/edmx",
        "edm": "http://schemas.microsoft.com/ado/2008/09/edm",
        "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
    }

    V2_NAMESPACES_ALT = {
        "edmx": "http://schemas.microsoft.com/ado/2007/06/edmx",
        "edm": "http://schemas.microsoft.com/ado/2006/04/edm",
        "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
    }

    V4_NAMESPACES = {
        "edmx": "http://docs.oasis-open.org/odata/ns/edmx",
        "edm": "http://docs.oasis-open.org/odata/ns/edm",
    }

    @classmethod
    def detect_version(cls, metadata_xml: str) -> ODataVersion:
        # Parse XML to check actual version attributes
        try:
            root = etree.fromstring(metadata_xml.encode("utf-8"))

            # Check Edmx Version attribute (V2 uses "1.0", V4 uses "4.0")
            # Get the root element (Edmx) regardless of namespace
            edmx_version = root.get("Version")
            if edmx_version:
                if edmx_version.startswith("1."):
                    return ODataVersion.V2
                if edmx_version.startswith("4."):
                    return ODataVersion.V4

            # Check DataServiceVersion attribute (V2 uses "2.0")
            for elem in root.iter():
                ds_version = elem.get("{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}DataServiceVersion")
                if ds_version and ds_version.startswith("2."):
                    return ODataVersion.V2

            # Fallback: check namespace in root element (but only as last resort)
            if root.nsmap.get("edmx") == "http://docs.oasis-open.org/odata/ns/edmx":
                # Still need to verify it's actually V4 by checking if V2 namespaces are present
                if "schemas.microsoft.com/ado" in metadata_xml:
                    return ODataVersion.V2
                return ODataVersion.V4

        except Exception:
            pass

        # Final fallback: check for namespace strings
        if "schemas.microsoft.com/ado" in metadata_xml:
            return ODataVersion.V2
        return ODataVersion.V2

    @classmethod
    def parse(cls, metadata_xml: str, version: ODataVersion = ODataVersion.AUTO) -> ODataMetadata:
        if version == ODataVersion.AUTO:
            version = cls.detect_version(metadata_xml)

        if version == ODataVersion.V4:
            return cls._parse_v4(metadata_xml)
        return cls._parse_v2(metadata_xml)

    @classmethod
    def _parse_v2(cls, metadata_xml: str) -> ODataMetadata:
        root = etree.fromstring(metadata_xml.encode("utf-8"))

        ns = cls.V2_NAMESPACES
        schema = root.find(".//edm:Schema", namespaces=ns)
        if schema is None:
            ns = cls.V2_NAMESPACES_ALT
            schema = root.find(".//edm:Schema", namespaces=ns)

        if schema is None:
            for _ns_prefix, ns_uri in root.nsmap.items():
                if "edm" in ns_uri.lower() or "schemas.microsoft.com" in ns_uri.lower():
                    ns = {"edm": ns_uri, "edmx": root.nsmap.get(None, cls.V2_NAMESPACES["edmx"])}
                    schema = root.find(f".//{{{ns_uri}}}Schema")
                    if schema is not None:
                        break

        if schema is None:
            return ODataMetadata(version=ODataVersion.V2)

        schema_namespace = schema.get("Namespace", "")
        entity_types = cls._parse_entity_types_v2(schema, ns, schema_namespace)
        entity_sets = cls._parse_entity_sets_v2(schema, ns, entity_types, schema_namespace)

        return ODataMetadata(
            version=ODataVersion.V2,
            entity_sets=entity_sets,
            entity_types=entity_types,
        )

    @classmethod
    def _parse_entity_types_v2(
        cls, schema: etree._Element, ns: dict[str, str], schema_namespace: str
    ) -> dict[str, dict]:
        entity_types = {}
        edm_ns = ns.get("edm", "")

        for entity_type in schema.findall(f".//{{{edm_ns}}}EntityType") if edm_ns else schema.findall(".//EntityType"):
            type_name = entity_type.get("Name", "")
            full_name = f"{schema_namespace}.{type_name}" if schema_namespace else type_name

            properties = []
            for prop in entity_type.findall(f"{{{edm_ns}}}Property") if edm_ns else entity_type.findall("Property"):
                properties.append(
                    EntityProperty(
                        name=prop.get("Name", ""),
                        edm_type=prop.get("Type", "Edm.String"),
                        nullable=prop.get("Nullable", "true").lower() == "true",
                        max_length=int(prop.get("MaxLength")) if prop.get("MaxLength") else None,
                        precision=int(prop.get("Precision")) if prop.get("Precision") else None,
                        scale=int(prop.get("Scale")) if prop.get("Scale") else None,
                    )
                )

            key_properties = []
            key_elem = entity_type.find(f"{{{edm_ns}}}Key") if edm_ns else entity_type.find("Key")
            if key_elem is not None:
                for prop_ref in (
                    key_elem.findall(f"{{{edm_ns}}}PropertyRef") if edm_ns else key_elem.findall("PropertyRef")
                ):
                    key_properties.append(prop_ref.get("Name", ""))

            nav_properties = []
            for nav_prop in (
                entity_type.findall(f"{{{edm_ns}}}NavigationProperty")
                if edm_ns
                else entity_type.findall("NavigationProperty")
            ):
                relationship = nav_prop.get("Relationship", "")
                to_role = nav_prop.get("ToRole", "")
                nav_properties.append(
                    NavigationProperty(
                        name=nav_prop.get("Name", ""),
                        target_entity=to_role or relationship.split(".")[-1] if relationship else "",
                        is_collection=False,
                    )
                )

            entity_types[full_name] = {
                "name": type_name,
                "properties": properties,
                "key_properties": key_properties,
                "navigation_properties": nav_properties,
            }
            entity_types[type_name] = entity_types[full_name]

        return entity_types

    @classmethod
    def _parse_entity_sets_v2(
        cls, schema: etree._Element, ns: dict[str, str], entity_types: dict[str, dict], schema_namespace: str
    ) -> dict[str, EntitySet]:
        entity_sets = {}
        edm_ns = ns.get("edm", "")

        entity_container = (
            schema.find(f".//{{{edm_ns}}}EntityContainer") if edm_ns else schema.find(".//EntityContainer")
        )
        if entity_container is None:
            return entity_sets

        for entity_set_elem in (
            entity_container.findall(f"{{{edm_ns}}}EntitySet") if edm_ns else entity_container.findall("EntitySet")
        ):
            set_name = entity_set_elem.get("Name", "")
            entity_type_name = entity_set_elem.get("EntityType", "")

            if "." in entity_type_name:
                type_key = entity_type_name
            else:
                type_key = f"{schema_namespace}.{entity_type_name}" if schema_namespace else entity_type_name

            entity_type_info = entity_types.get(type_key) or entity_types.get(entity_type_name.split(".")[-1], {})

            entity_sets[set_name] = EntitySet(
                name=set_name,
                entity_type=entity_type_name,
                properties=entity_type_info.get("properties", []),
                key_properties=entity_type_info.get("key_properties", []),
                navigation_properties=entity_type_info.get("navigation_properties", []),
            )

        return entity_sets

    @classmethod
    def _parse_v4(cls, metadata_xml: str) -> ODataMetadata:
        root = etree.fromstring(metadata_xml.encode("utf-8"))
        ns = cls.V4_NAMESPACES

        schema = root.find(".//edm:Schema", namespaces=ns)
        if schema is None:
            edm_ns = "http://docs.oasis-open.org/odata/ns/edm"
            schema = root.find(f".//{{{edm_ns}}}Schema")

        if schema is None:
            return ODataMetadata(version=ODataVersion.V4)

        schema_namespace = schema.get("Namespace", "")
        entity_types = cls._parse_entity_types_v4(schema, schema_namespace)
        entity_sets = cls._parse_entity_sets_v4(schema, entity_types, schema_namespace)

        return ODataMetadata(
            version=ODataVersion.V4,
            entity_sets=entity_sets,
            entity_types=entity_types,
        )

    @classmethod
    def _parse_entity_types_v4(cls, schema: etree._Element, schema_namespace: str) -> dict[str, dict]:
        entity_types = {}
        edm_ns = "http://docs.oasis-open.org/odata/ns/edm"

        for entity_type in schema.findall(f".//{{{edm_ns}}}EntityType"):
            type_name = entity_type.get("Name", "")
            full_name = f"{schema_namespace}.{type_name}" if schema_namespace else type_name

            properties = []
            for prop in entity_type.findall(f"{{{edm_ns}}}Property"):
                properties.append(
                    EntityProperty(
                        name=prop.get("Name", ""),
                        edm_type=prop.get("Type", "Edm.String"),
                        nullable=prop.get("Nullable", "true").lower() == "true",
                        max_length=int(prop.get("MaxLength")) if prop.get("MaxLength") else None,
                        precision=int(prop.get("Precision")) if prop.get("Precision") else None,
                        scale=int(prop.get("Scale")) if prop.get("Scale") else None,
                    )
                )

            key_properties = []
            key_elem = entity_type.find(f"{{{edm_ns}}}Key")
            if key_elem is not None:
                for prop_ref in key_elem.findall(f"{{{edm_ns}}}PropertyRef"):
                    key_properties.append(prop_ref.get("Name", ""))

            nav_properties = []
            for nav_prop in entity_type.findall(f"{{{edm_ns}}}NavigationProperty"):
                nav_type = nav_prop.get("Type", "")
                is_collection = nav_type.startswith("Collection(")
                target = nav_type.replace("Collection(", "").rstrip(")") if is_collection else nav_type
                nav_properties.append(
                    NavigationProperty(
                        name=nav_prop.get("Name", ""),
                        target_entity=target.split(".")[-1] if target else "",
                        is_collection=is_collection,
                    )
                )

            entity_types[full_name] = {
                "name": type_name,
                "properties": properties,
                "key_properties": key_properties,
                "navigation_properties": nav_properties,
            }
            entity_types[type_name] = entity_types[full_name]

        return entity_types

    @classmethod
    def _parse_entity_sets_v4(
        cls, schema: etree._Element, entity_types: dict[str, dict], schema_namespace: str
    ) -> dict[str, EntitySet]:
        entity_sets = {}
        edm_ns = "http://docs.oasis-open.org/odata/ns/edm"

        entity_container = schema.find(f".//{{{edm_ns}}}EntityContainer")
        if entity_container is None:
            return entity_sets

        for entity_set_elem in entity_container.findall(f"{{{edm_ns}}}EntitySet"):
            set_name = entity_set_elem.get("Name", "")
            entity_type_name = entity_set_elem.get("EntityType", "")

            if "." in entity_type_name:
                type_key = entity_type_name
            else:
                type_key = f"{schema_namespace}.{entity_type_name}" if schema_namespace else entity_type_name

            entity_type_info = entity_types.get(type_key) or entity_types.get(entity_type_name.split(".")[-1], {})

            entity_sets[set_name] = EntitySet(
                name=set_name,
                entity_type=entity_type_name,
                properties=entity_type_info.get("properties", []),
                key_properties=entity_type_info.get("key_properties", []),
                navigation_properties=entity_type_info.get("navigation_properties", []),
            )

        return entity_sets

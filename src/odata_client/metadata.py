from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from lxml import etree

# Type alias for JSON-like dictionaries
JsonDict = dict[str, Any]


def _safe_int(value: str | None) -> int | None:
    """Safely convert string to int, returning None if conversion fails.

    OData metadata can contain non-numeric values like 'variable' or 'max'
    for MaxLength, Precision, and Scale attributes.
    """
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class ODataVersion(StrEnum):
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
    # SAP-specific annotations
    sap_label: str | None = None
    sap_quickinfo: str | None = None
    sap_filterable: bool | None = None
    sap_creatable: bool | None = None
    sap_updatable: bool | None = None

    def to_dict(self) -> JsonDict:
        result = {
            "name": self.name,
            "edm_type": self.edm_type,
            "nullable": self.nullable,
            "max_length": self.max_length,
            "precision": self.precision,
            "scale": self.scale,
        }
        # Include SAP annotations if present
        if self.sap_label is not None:
            result["sap_label"] = self.sap_label
        if self.sap_quickinfo is not None:
            result["sap_quickinfo"] = self.sap_quickinfo
        if self.sap_filterable is not None:
            result["sap_filterable"] = self.sap_filterable
        if self.sap_creatable is not None:
            result["sap_creatable"] = self.sap_creatable
        if self.sap_updatable is not None:
            result["sap_updatable"] = self.sap_updatable
        return result


@dataclass
class NavigationProperty:
    name: str
    target_entity: str
    is_collection: bool = False

    def to_dict(self) -> JsonDict:
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

    def to_dict(self) -> JsonDict:
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

    def get_navigation_properties_for_type(self, entity_type_name: str) -> list[NavigationProperty]:
        """Get navigation properties for an entity type by name.

        Looks up the entity type in the metadata (tries both short and qualified names)
        and returns its navigation properties.
        """
        type_info = self.entity_types.get(entity_type_name)
        if type_info is None:
            # Try without namespace prefix
            short_name = entity_type_name.split(".")[-1] if "." in entity_type_name else entity_type_name
            type_info = self.entity_types.get(short_name)
        if type_info is None:
            return []
        return type_info.get("navigation_properties", [])


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
                ds_version = elem.get(
                    "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}DataServiceVersion"
                )
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
        schemas = root.findall(".//edm:Schema", namespaces=ns)
        if not schemas:
            ns = cls.V2_NAMESPACES_ALT
            schemas = root.findall(".//edm:Schema", namespaces=ns)

        if not schemas:
            # Fallback: discover EDM namespace from any element in the tree.
            # Some services (e.g. Northwind) declare the EDM namespace only on
            # child <Schema> elements, so root.nsmap alone is not sufficient.
            edm_ns_uri = cls._discover_edm_namespace(root)
            if edm_ns_uri:
                ns = {"edm": edm_ns_uri, "edmx": root.nsmap.get("edmx", cls.V2_NAMESPACES["edmx"])}
                schemas = root.findall(f".//{{{edm_ns_uri}}}Schema")

        if not schemas:
            return ODataMetadata(version=ODataVersion.V2)

        # Collect entity types and associations from ALL schemas, then entity
        # sets.  This mirrors the V4 parser approach and handles multi-schema
        # EDMX documents (e.g. Northwind where EntityTypes and EntityContainer
        # live in separate <Schema> elements).
        all_entity_types: dict[str, dict] = {}
        all_association_map: dict[tuple[str, str], str] = {}
        for schema in schemas:
            schema_namespace = schema.get("Namespace", "")
            assoc_map = cls._parse_associations_v2(schema, ns, schema_namespace)
            all_association_map.update(assoc_map)
            entity_types = cls._parse_entity_types_v2(schema, ns, schema_namespace, assoc_map)
            all_entity_types.update(entity_types)

        all_entity_sets: dict[str, EntitySet] = {}
        for schema in schemas:
            schema_namespace = schema.get("Namespace", "")
            entity_sets = cls._parse_entity_sets_v2(schema, ns, all_entity_types, schema_namespace)
            if entity_sets:
                all_entity_sets.update(entity_sets)

        return ODataMetadata(
            version=ODataVersion.V2,
            entity_sets=all_entity_sets,
            entity_types=all_entity_types,
        )

    @classmethod
    def _discover_edm_namespace(cls, root: etree._Element) -> str:
        """Walk the element tree to find the EDM namespace URI.

        OData V2 metadata uses varying EDM namespace versions (2006, 2008,
        2009).  Some services declare the namespace on the root ``<edmx:Edmx>``
        element, others only on child ``<Schema>`` elements.  This helper
        inspects *all* elements' ``nsmap`` to find the first URI that looks
        like an EDM namespace.
        """
        for elem in root.iter():
            for _prefix, uri in elem.nsmap.items():
                if uri and (
                    "schemas.microsoft.com/ado" in uri
                    and "/edm" in uri.lower()
                    and "edmx" not in uri.lower()
                    and "metadata" not in uri.lower()
                    and "dataservices" not in uri.lower()
                ):
                    return uri
        return ""

    @classmethod
    def _parse_associations_v2(
        cls, schema: etree._Element, ns: dict[str, str], schema_namespace: str
    ) -> dict[tuple[str, str], str]:
        """Parse V2 Association elements to map (relationship, role) to entity type.

        In OData V2 metadata, ``NavigationProperty`` references a ``Relationship``
        (association name) and a ``ToRole``.  The actual target entity type is
        declared inside the ``<Association>`` element's ``<End>`` children::

            <Association Name="Assoc_BP_Address">
              <End Type="NS.BusinessPartner" … Role="FromRole"/>
              <End Type="NS.Address"         … Role="ToRole"/>
            </Association>

        Returns:
            Mapping of ``(qualified_association_name, role_name)`` → short entity
            type name (without namespace prefix).
        """
        association_map: dict[tuple[str, str], str] = {}
        edm_ns = ns.get("edm", "")

        associations = schema.findall(f".//{{{edm_ns}}}Association") if edm_ns else schema.findall(".//Association")
        for assoc in associations:
            assoc_name = assoc.get("Name", "")
            qualified_name = f"{schema_namespace}.{assoc_name}" if schema_namespace else assoc_name

            ends = assoc.findall(f"{{{edm_ns}}}End") if edm_ns else assoc.findall("End")
            for end in ends:
                role = end.get("Role", "")
                entity_type = end.get("Type", "")
                # Strip namespace prefix to get the short type name
                short_type = entity_type.split(".")[-1] if entity_type else ""
                if role and short_type:
                    association_map[(qualified_name, role)] = short_type
                    # Also store with short association name for fallback
                    association_map[(assoc_name, role)] = short_type

        return association_map

    @classmethod
    def _parse_entity_types_v2(
        cls,
        schema: etree._Element,
        ns: dict[str, str],
        schema_namespace: str,
        association_map: dict[tuple[str, str], str] | None = None,
    ) -> dict[str, dict]:
        entity_types = {}
        edm_ns = ns.get("edm", "")
        if association_map is None:
            association_map = {}

        for entity_type in schema.findall(f".//{{{edm_ns}}}EntityType") if edm_ns else schema.findall(".//EntityType"):
            type_name = entity_type.get("Name", "")
            full_name = f"{schema_namespace}.{type_name}" if schema_namespace else type_name

            properties = []
            for prop in entity_type.findall(f"{{{edm_ns}}}Property") if edm_ns else entity_type.findall("Property"):
                # Parse SAP annotations (namespace: http://www.sap.com/Protocols/SAPData)
                sap_ns = "{http://www.sap.com/Protocols/SAPData}"
                sap_label = prop.get(f"{sap_ns}label")
                sap_quickinfo = prop.get(f"{sap_ns}quickinfo")
                sap_filterable_str = prop.get(f"{sap_ns}filterable")
                sap_creatable_str = prop.get(f"{sap_ns}creatable")
                sap_updatable_str = prop.get(f"{sap_ns}updatable")

                # Convert string booleans to bool | None
                sap_filterable = sap_filterable_str.lower() == "true" if sap_filterable_str else None
                sap_creatable = sap_creatable_str.lower() == "true" if sap_creatable_str else None
                sap_updatable = sap_updatable_str.lower() == "true" if sap_updatable_str else None

                properties.append(
                    EntityProperty(
                        name=prop.get("Name", ""),
                        edm_type=prop.get("Type", "Edm.String"),
                        nullable=prop.get("Nullable", "true").lower() == "true",
                        max_length=_safe_int(prop.get("MaxLength")),
                        precision=_safe_int(prop.get("Precision")),
                        scale=_safe_int(prop.get("Scale")),
                        sap_label=sap_label,
                        sap_quickinfo=sap_quickinfo,
                        sap_filterable=sap_filterable,
                        sap_creatable=sap_creatable,
                        sap_updatable=sap_updatable,
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

                # Resolve the actual target entity type from Association End elements.
                # Try qualified name first, then short name as fallback.
                target_entity = (
                    association_map.get((relationship, to_role))
                    or association_map.get((relationship.split(".")[-1], to_role) if relationship else ("", ""))
                    or to_role
                    or (relationship.split(".")[-1] if relationship else "")
                )

                nav_properties.append(
                    NavigationProperty(
                        name=nav_prop.get("Name", ""),
                        target_entity=target_entity,
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
        entity_sets: dict[str, EntitySet] = {}
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
        edm_ns = "http://docs.oasis-open.org/odata/ns/edm"

        schemas = root.findall(".//edm:Schema", namespaces=ns)
        if not schemas:
            schemas = root.findall(f".//{{{edm_ns}}}Schema")

        if not schemas:
            return ODataMetadata(version=ODataVersion.V4)

        # Collect entity types from ALL schemas (handles multi-schema EDMX like Northwind V4)
        all_entity_types: dict[str, dict] = {}
        for schema in schemas:
            schema_namespace = schema.get("Namespace", "")
            all_entity_types.update(cls._parse_entity_types_v4(schema, schema_namespace))

        # Find EntityContainer across ALL schemas (may be in a different schema than EntityTypes)
        all_entity_sets: dict[str, EntitySet] = {}
        for schema in schemas:
            schema_namespace = schema.get("Namespace", "")
            schema_entity_sets = cls._parse_entity_sets_v4(schema, all_entity_types, schema_namespace)
            if schema_entity_sets:
                all_entity_sets.update(schema_entity_sets)

        return ODataMetadata(
            version=ODataVersion.V4,
            entity_sets=all_entity_sets,
            entity_types=all_entity_types,
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
                        max_length=_safe_int(prop.get("MaxLength")),
                        precision=_safe_int(prop.get("Precision")),
                        scale=_safe_int(prop.get("Scale")),
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
        entity_sets: dict[str, EntitySet] = {}
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

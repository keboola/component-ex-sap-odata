"""Mock OData server for testing using respx library for httpx/AsyncHttpClient.

Provides realistic OData V2 and V4 mock responses for comprehensive testing.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import respx

JsonDict = dict[str, Any]


class MockODataV4Server:
    """Mock OData V4 server with realistic SAP responses."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.metadata_xml = self._get_v4_metadata()
        self.products_data = self._get_products_data()

    def _get_v4_metadata(self) -> str:
        """Return OData V4 metadata XML."""
        return """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="ODataDemo" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Product">
        <Key>
          <PropertyRef Name="ID"/>
        </Key>
        <Property Name="ID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="Name" Type="Edm.String"/>
        <Property Name="Description" Type="Edm.String"/>
        <Property Name="Price" Type="Edm.Decimal" Scale="2" Precision="10"/>
        <Property Name="Category" Type="Edm.String"/>
        <Property Name="CreatedAt" Type="Edm.DateTimeOffset"/>
        <Property Name="LastModified" Type="Edm.DateTimeOffset"/>
        <Property Name="IsActive" Type="Edm.Boolean"/>
        <NavigationProperty Name="Supplier" Type="ODataDemo.Supplier"/>
      </EntityType>
      <EntityType Name="Supplier">
        <Key>
          <PropertyRef Name="ID"/>
        </Key>
        <Property Name="ID" Type="Edm.Int32" Nullable="false"/>
        <Property Name="Name" Type="Edm.String"/>
        <Property Name="Country" Type="Edm.String"/>
      </EntityType>
      <EntityContainer Name="DemoService">
        <EntitySet Name="Products" EntityType="ODataDemo.Product"/>
        <EntitySet Name="Suppliers" EntityType="ODataDemo.Supplier"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

    def _get_products_data(self) -> list[JsonDict]:
        """Return mock product data."""
        return [
            {
                "ID": 1,
                "Name": "Laptop",
                "Description": "High-performance laptop",
                "Price": 1299.99,
                "Category": "Electronics",
                "CreatedAt": "2024-01-01T10:00:00Z",
                "LastModified": "2024-01-15T14:30:00Z",
                "IsActive": True,
            },
            {
                "ID": 2,
                "Name": "Mouse",
                "Description": "Wireless mouse",
                "Price": 29.99,
                "Category": "Electronics",
                "CreatedAt": "2024-01-02T11:00:00Z",
                "LastModified": "2024-01-16T09:15:00Z",
                "IsActive": True,
            },
            {
                "ID": 3,
                "Name": "Keyboard",
                "Description": "Mechanical keyboard",
                "Price": 89.99,
                "Category": "Electronics",
                "CreatedAt": "2024-01-03T12:00:00Z",
                "LastModified": "2024-01-17T16:45:00Z",
                "IsActive": True,
            },
            {
                "ID": 4,
                "Name": "Monitor",
                "Description": "4K display",
                "Price": 499.99,
                "Category": "Electronics",
                "CreatedAt": "2024-01-04T13:00:00Z",
                "LastModified": "2024-01-18T11:20:00Z",
                "IsActive": False,
            },
            {
                "ID": 5,
                "Name": "Desk Chair",
                "Description": "Ergonomic office chair",
                "Price": 299.99,
                "Category": "Furniture",
                "CreatedAt": "2024-01-05T14:00:00Z",
                "LastModified": "2024-01-19T13:00:00Z",
                "IsActive": True,
            },
        ]

    def setup(self, respx_mock: respx.MockRouter) -> None:
        """Setup mock responses for OData V4 server."""
        # Metadata endpoint
        respx_mock.get(f"{self.base_url}/$metadata").mock(
            return_value=httpx.Response(
                200,
                content=self.metadata_xml,
                headers={"Content-Type": "application/xml"},
            )
        )

        # Service document (root endpoint)
        respx_mock.get(self.base_url + "/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "@odata.context": f"{self.base_url}/$metadata",
                    "value": [
                        {"name": "Products", "kind": "EntitySet", "url": "Products"},
                        {"name": "Suppliers", "kind": "EntitySet", "url": "Suppliers"},
                    ],
                },
            )
        )

        # Products endpoint with dynamic response
        respx_mock.get(url__regex=f"{re.escape(self.base_url)}/Products(\\?.*)?$").mock(
            side_effect=self._handle_products_request
        )

        # $count endpoint
        respx_mock.get(url__regex=f"{re.escape(self.base_url)}/Products/\\$count(\\?.*)?$").mock(
            side_effect=self._handle_count_request
        )

    def _handle_products_request(self, request: httpx.Request) -> httpx.Response:
        """Handle Products entity set requests with filtering and pagination."""
        parsed_url = urlparse(str(request.url))
        query_params = parse_qs(parsed_url.query)

        # Get pagination parameters
        skip = int(query_params.get("$skip", ["0"])[0])
        top = int(query_params.get("$top", ["1000"])[0])

        # Apply filter
        data = self.products_data.copy()
        filter_expr = query_params.get("$filter", [None])[0]
        if filter_expr:
            data = self._apply_filter(data, filter_expr)

        # Apply select
        select_fields = query_params.get("$select", [None])[0]
        if select_fields:
            fields = [f.strip() for f in select_fields.split(",")]
            data = [{k: v for k, v in item.items() if k in fields} for item in data]

        # Apply pagination
        total_count = len(data)
        paginated_data = data[skip : skip + top]

        # Build response
        response_data: JsonDict = {
            "@odata.context": f"{self.base_url}/$metadata#Products",
            "value": paginated_data,
        }

        # Add next link if there are more records
        if skip + top < total_count:
            next_skip = skip + top
            response_data["@odata.nextLink"] = f"{self.base_url}/Products?$skip={next_skip}&$top={top}"
            if filter_expr:
                response_data["@odata.nextLink"] += f"&$filter={filter_expr}"
            if select_fields:
                response_data["@odata.nextLink"] += f"&$select={select_fields}"

        return httpx.Response(200, json=response_data)

    def _handle_count_request(self, request: httpx.Request) -> httpx.Response:
        """Handle $count requests."""
        parsed_url = urlparse(str(request.url))
        query_params = parse_qs(parsed_url.query)

        data = self.products_data.copy()
        filter_expr = query_params.get("$filter", [None])[0]
        if filter_expr:
            data = self._apply_filter(data, filter_expr)

        return httpx.Response(200, content=str(len(data)), headers={"Content-Type": "text/plain"})

    def _apply_filter(self, data: list[JsonDict], filter_expr: str) -> list[JsonDict]:
        """Apply simple OData filter expression."""
        # Handle simple equality filters: Category eq 'Electronics'
        if " eq " in filter_expr:
            parts = filter_expr.split(" eq ")
            field = parts[0].strip()
            value = parts[1].strip().strip("'\"")

            # Handle boolean values
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False

            return [item for item in data if str(item.get(field)) == str(value)]

        # Handle greater than filters: LastModified gt 2024-01-15T00:00:00Z
        if " gt " in filter_expr:
            parts = filter_expr.split(" gt ")
            field = parts[0].strip()
            value = parts[1].strip()
            return [item for item in data if item.get(field, "") > value]

        # Handle combined filters with 'and'
        if " and " in filter_expr:
            filters = filter_expr.split(" and ")
            result = data
            for f in filters:
                f = f.strip().strip("()")
                result = self._apply_filter(result, f)
            return result

        return data


class MockODataV2Server:
    """Mock OData V2 server with realistic SAP responses."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.metadata_xml = self._get_v2_metadata()
        self.business_partners_data = self._get_business_partners_data()

    def _get_v2_metadata(self) -> str:
        """Return OData V2 metadata XML."""
        return """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices m:DataServiceVersion="2.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="SAP" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityType Name="BusinessPartner">
        <Key>
          <PropertyRef Name="BusinessPartner"/>
        </Key>
        <Property Name="BusinessPartner" Type="Edm.String" Nullable="false" MaxLength="10"/>
        <Property Name="BusinessPartnerName" Type="Edm.String" MaxLength="80"/>
        <Property Name="BusinessPartnerCategory" Type="Edm.String" MaxLength="1"/>
        <Property Name="OrganizationBPName1" Type="Edm.String" MaxLength="40"/>
        <Property Name="CreatedDate" Type="Edm.DateTime"/>
        <Property Name="LastChangeDateTime" Type="Edm.DateTime"/>
        <Property Name="IsActive" Type="Edm.Boolean"/>
      </EntityType>
      <EntityType Name="CompanyCode">
        <Key>
          <PropertyRef Name="CompanyCode"/>
        </Key>
        <Property Name="CompanyCode" Type="Edm.String" Nullable="false" MaxLength="4"/>
        <Property Name="CompanyCodeName" Type="Edm.String" MaxLength="25"/>
        <Property Name="Country" Type="Edm.String" MaxLength="3"/>
        <Property Name="Currency" Type="Edm.String" MaxLength="5"/>
      </EntityType>
      <EntityContainer Name="API_BUSINESS_PARTNER" m:IsDefaultEntityContainer="true">
        <EntitySet Name="A_BusinessPartner" EntityType="SAP.BusinessPartner"/>
        <EntitySet Name="A_CompanyCode" EntityType="SAP.CompanyCode"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

    def _get_business_partners_data(self) -> list[JsonDict]:
        """Return mock business partner data."""
        return [
            {
                "BusinessPartner": "0000001",
                "BusinessPartnerName": "Acme Corporation",
                "BusinessPartnerCategory": "1",
                "OrganizationBPName1": "Acme Corp",
                "CreatedDate": "/Date(1704067200000)/",
                "LastChangeDateTime": "/Date(1705968000000)/",
                "IsActive": True,
            },
            {
                "BusinessPartner": "0000002",
                "BusinessPartnerName": "Tech Solutions Ltd",
                "BusinessPartnerCategory": "1",
                "OrganizationBPName1": "Tech Solutions",
                "CreatedDate": "/Date(1704153600000)/",
                "LastChangeDateTime": "/Date(1706054400000)/",
                "IsActive": True,
            },
            {
                "BusinessPartner": "0000003",
                "BusinessPartnerName": "Global Industries",
                "BusinessPartnerCategory": "2",
                "OrganizationBPName1": "Global Ind",
                "CreatedDate": "/Date(1704240000000)/",
                "LastChangeDateTime": "/Date(1706140800000)/",
                "IsActive": True,
            },
            {
                "BusinessPartner": "0000004",
                "BusinessPartnerName": "Retail Partners",
                "BusinessPartnerCategory": "1",
                "OrganizationBPName1": "Retail Partners",
                "CreatedDate": "/Date(1704326400000)/",
                "LastChangeDateTime": "/Date(1706227200000)/",
                "IsActive": False,
            },
            {
                "BusinessPartner": "0000005",
                "BusinessPartnerName": "Services Group",
                "BusinessPartnerCategory": "1",
                "OrganizationBPName1": "Services Grp",
                "CreatedDate": "/Date(1704412800000)/",
                "LastChangeDateTime": "/Date(1706313600000)/",
                "IsActive": True,
            },
        ]

    def setup(self, respx_mock: respx.MockRouter) -> None:
        """Setup mock responses for OData V2 server."""
        # Metadata endpoint
        respx_mock.get(f"{self.base_url}/$metadata").mock(
            return_value=httpx.Response(
                200,
                content=self.metadata_xml,
                headers={"Content-Type": "application/xml"},
            )
        )

        # Service document (root endpoint)
        respx_mock.get(self.base_url + "/").mock(
            return_value=httpx.Response(
                200,
                content="""<?xml version="1.0" encoding="utf-8"?>
<service xmlns="http://www.w3.org/2007/app" xmlns:atom="http://www.w3.org/2005/Atom">
  <workspace>
    <atom:title>Default</atom:title>
    <collection href="A_BusinessPartner">
      <atom:title>A_BusinessPartner</atom:title>
    </collection>
    <collection href="A_CompanyCode">
      <atom:title>A_CompanyCode</atom:title>
    </collection>
  </workspace>
</service>""",
                headers={"Content-Type": "application/xml"},
            )
        )

        # Business Partner endpoint with dynamic response
        respx_mock.get(url__regex=f"{re.escape(self.base_url)}/A_BusinessPartner(\\?.*)?$").mock(
            side_effect=self._handle_business_partner_request
        )

        # $count endpoint
        respx_mock.get(url__regex=f"{re.escape(self.base_url)}/A_BusinessPartner/\\$count(\\?.*)?$").mock(
            side_effect=self._handle_count_request
        )

    def _handle_business_partner_request(self, request: httpx.Request) -> httpx.Response:
        """Handle A_BusinessPartner entity set requests."""
        parsed_url = urlparse(str(request.url))
        query_params = parse_qs(parsed_url.query)

        # Get pagination parameters
        skip = int(query_params.get("$skip", ["0"])[0])
        top = int(query_params.get("$top", ["1000"])[0])

        # Apply filter
        data = self.business_partners_data.copy()
        filter_expr = query_params.get("$filter", [None])[0]
        if filter_expr:
            data = self._apply_filter(data, filter_expr)

        # Apply select
        select_fields = query_params.get("$select", [None])[0]
        if select_fields:
            fields = [f.strip() for f in select_fields.split(",")]
            data = [{k: v for k, v in item.items() if k in fields} for item in data]

        # Apply pagination
        total_count = len(data)
        paginated_data = data[skip : skip + top]

        # Build OData V2 JSON response
        response_data: JsonDict = {
            "d": {
                "results": paginated_data,
            }
        }

        # Add __count for inline count
        if "$inlinecount" in query_params:
            response_data["d"]["__count"] = str(total_count)

        # Add __next link if there are more records
        if skip + top < total_count:
            next_url = f"{self.base_url}/A_BusinessPartner?$skip={skip + top}&$top={top}"
            if filter_expr:
                next_url += f"&$filter={filter_expr}"
            if select_fields:
                next_url += f"&$select={select_fields}"
            response_data["d"]["__next"] = next_url

        return httpx.Response(200, json=response_data)

    def _handle_count_request(self, request: httpx.Request) -> httpx.Response:
        """Handle $count requests."""
        parsed_url = urlparse(str(request.url))
        query_params = parse_qs(parsed_url.query)

        data = self.business_partners_data.copy()
        filter_expr = query_params.get("$filter", [None])[0]
        if filter_expr:
            data = self._apply_filter(data, filter_expr)

        return httpx.Response(200, content=str(len(data)), headers={"Content-Type": "text/plain"})

    def _apply_filter(self, data: list[JsonDict], filter_expr: str) -> list[JsonDict]:
        """Apply simple OData V2 filter expression."""
        # Handle equality filters
        if " eq " in filter_expr:
            parts = filter_expr.split(" eq ")
            field = parts[0].strip()
            value = parts[1].strip().strip("'\"")

            # Handle boolean values
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False

            return [item for item in data if str(item.get(field)) == str(value)]

        # Handle datetime filters with gt (greater than)
        if " gt datetime" in filter_expr:
            parts = filter_expr.split(" gt datetime")
            field = parts[0].strip()
            datetime_value = parts[1].strip().strip("'\"")
            return [item for item in data if item.get(field, "") > f"/Date(1706054400000)/"]

        # Handle combined filters
        if " and " in filter_expr:
            filters = filter_expr.split(" and ")
            result = data
            for f in filters:
                f = f.strip().strip("()")
                result = self._apply_filter(result, f)
            return result

        return data


class MockSAPCatalogServer:
    """Mock SAP Service Catalog server."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def setup(self, respx_mock: respx.MockRouter) -> None:
        """Setup mock responses for SAP catalog."""
        # Catalog metadata
        catalog_metadata = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices m:DataServiceVersion="2.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="CATALOGSERVICE" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityType Name="Service">
        <Key>
          <PropertyRef Name="ID"/>
        </Key>
        <Property Name="ID" Type="Edm.String" Nullable="false"/>
        <Property Name="Title" Type="Edm.String"/>
        <Property Name="Author" Type="Edm.String"/>
        <Property Name="Updated" Type="Edm.DateTime"/>
      </EntityType>
      <EntityContainer Name="CatalogService" m:IsDefaultEntityContainer="true">
        <EntitySet Name="ServiceCollection" EntityType="CATALOGSERVICE.Service"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

        respx_mock.get(f"{self.base_url}/$metadata").mock(
            return_value=httpx.Response(
                200,
                content=catalog_metadata,
                headers={"Content-Type": "application/xml"},
            )
        )

        # ServiceCollection with available services
        catalog_response = {
            "d": {
                "results": [
                    {
                        "ID": "API_BUSINESS_PARTNER",
                        "Title": "Business Partner API",
                        "Author": "SAP",
                        "Updated": "/Date(1704067200000)/",
                        "TechnicalServiceName": "API_BUSINESS_PARTNER",
                        "TechnicalServiceVersion": "0001",
                        "__metadata": {
                            "uri": "http://sap-server:50000/sap/opu/odata/sap/API_BUSINESS_PARTNER"
                        },
                    },
                    {
                        "ID": "API_FIXEDASSET",
                        "Title": "Fixed Asset API",
                        "Author": "SAP",
                        "Updated": "/Date(1704153600000)/",
                        "TechnicalServiceName": "API_FIXEDASSET",
                        "TechnicalServiceVersion": "0001",
                        "__metadata": {
                            "uri": "http://sap-server:50000/sap/opu/odata/sap/API_FIXEDASSET"
                        },
                    },
                ]
            }
        }

        respx_mock.get(f"{self.base_url}/ServiceCollection").mock(
            return_value=httpx.Response(200, json=catalog_response)
        )

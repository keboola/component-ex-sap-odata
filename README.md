# SAP OData Extractor

Keboola component for extracting data from SAP OData services. Supports both OData V2 and V4 protocols.

## Features

- **Universal SAP OData connector** - supports any SAP OData service (S/4HANA, BW, CRM, SuccessFactors, etc.)
- **OData V2 and V4 support** - automatic version detection or explicit selection
- **Multiple authentication methods** - Basic authentication and OAuth 2.0
- **Full data extraction** - filtering, column selection, navigation property expansion
- **Incremental sync** - delta synchronization using state file
- **Dynamic UI** - entity sets and fields loaded from $metadata

## Configuration

### Main Configuration

| Parameter | Required | Description |
|-----------|----------|-------------|
| `service_url` | Yes | Base URL of the OData service |
| `odata_version` | No | OData version: `auto`, `v2`, or `v4` (default: `auto`) |
| `auth_type` | Yes | Authentication type: `basic` or `oauth` |
| `username` | For basic | Username for basic authentication |
| `#password` | For basic | Password for basic authentication |
| `timeout` | No | Request timeout in seconds (default: 60) |
| `max_retries` | No | Maximum retries for failed requests (default: 3) |

### Row Configuration

| Parameter | Required | Description |
|-----------|----------|-------------|
| `entity_set` | Yes | Name of the OData EntitySet to extract |
| `output_table_name` | No | Output table name (default: entity set name) |
| `select_fields` | No | Fields to select ($select) |
| `filter_expression` | No | OData $filter expression |
| `expand_properties` | No | Navigation properties to expand ($expand) |
| `order_by` | No | Field for ordering ($orderby) |
| `sync_type` | No | Sync type: `full` or `incremental` (default: `full`) |
| `incremental_field` | No | Field for incremental sync |
| `primary_key` | No | Primary key fields |
| `page_size` | No | Records per page (default: 1000) |
| `max_records` | No | Maximum records to fetch (0 = unlimited) |

## Development

### Prerequisites

- Python 3.13+
- uv (recommended) or pip

### Setup

```bash
# Clone the repository
git clone https://github.com/keboola/component-ex-sap-odata.git
cd component-ex-sap-odata

# Install dependencies
uv sync

# Run tests
uv run pytest
```

### Local Testing

Create a `data/config.json` file with your configuration:

```json
{
  "parameters": {
    "service_url": "https://your-sap-server/sap/opu/odata/sap/API_BUSINESS_PARTNER",
    "auth_type": "basic",
    "username": "your-username",
    "#password": "your-password",
    "entity_set": "A_BusinessPartner",
    "select_fields": ["BusinessPartner", "BusinessPartnerName"],
    "page_size": 100
  }
}
```

Run the component:

```bash
cd src
python component.py
```

## License

MIT License

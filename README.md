# SAP OData Extractor

Keboola component for extracting data from SAP OData services. Supports both OData V2 and V4 protocols.

## Features

- **Universal SAP OData connector** - supports any SAP OData service (S/4HANA, BW, CRM, SuccessFactors, etc.)
- **OData V2 and V4 support** - automatic version detection with smart SAP metadata parsing
- **Multiple authentication methods** - Basic authentication, OAuth 2.0, and API Key
- **Full data extraction** - filtering, column selection, navigation property expansion
- **Incremental sync** - delta synchronization using state file
- **Dynamic UI** - entity sets and fields loaded from $metadata
- **SAP-optimized** - handles SAP's mixed V2/V4 metadata correctly

## Configuration

### Main Configuration

#### URL Configuration (choose one method):

**Option 1: Full Service URL (Legacy)**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `service_url` | Yes* | Full OData service URL (e.g., `https://sap.com/sap/opu/odata/sap/API_BUSINESS_PARTNER`) |

**Option 2: Split URL (Recommended)**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `base_url` | Yes* | Base URL of SAP system (e.g., `https://my-sap-server.com`) |
| `service_path` | Yes* | Service path (e.g., `API_BUSINESS_PARTNER` for V2, or `api_name/srvd_a2x/sap/service/0001` for V4) |

*Either provide `service_url` OR both `base_url` + `service_path`

#### Other Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `odata_version` | No | OData version: `auto`, `v2`, or `v4` (default: `auto`) |
| `auth_type` | Yes | Authentication type: `basic`, `oauth`, or `apiKey` |
| `username` | For basic | Username for basic authentication |
| `#password` | For basic | Password for basic authentication |
| `#api_key` | For apiKey | API key for API key authentication |
| `api_key_header_name` | For apiKey | HTTP header name for API key (default: `APIKey`) |
| `timeout` | No | Request timeout in seconds (default: 60) |
| `max_retries` | No | Maximum retries for failed requests (default: 3) |
| `verify_ssl` | No | Verify SSL certificates (default: `true`) |

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
KBC_DATADIR=./data python3 src/component.py
```

### Running Tests

```bash
# Unit tests
PYTHONPATH=src uv run pytest

# Functional tests (requires SAP_API_KEY)
export SAP_API_KEY="your-api-key"
PYTHONPATH=src uv run pytest tests/functional/
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for detailed development instructions including:
- How to get SAP API Key for testing
- Local testing with sample configs
- Debugging and troubleshooting

## Documentation

- [URL Structure Analysis](docs/URL_STRUCTURE_ANALYSIS.md) - Detailed analysis of SAP OData URL patterns
- [Development Guide](docs/DEVELOPMENT.md) - Complete development and testing guide
- [Sample Configurations](data/README.md) - Example configurations for different scenarios

## License

MIT License

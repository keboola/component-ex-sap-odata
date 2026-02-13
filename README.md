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
| `page_size` | No | Default page size for all entities (default: 1000) |
| `max_records` | No | Default max records for all entities (0 = unlimited) |

### Row Configuration

Each row extracts one entity set. Multiple rows can be configured for different entities.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `entity_set` | Yes | Name of the OData EntitySet to extract |
| `output_table_name` | No | Output table name (default: entity set name) |
| `select_fields` | No | Fields to select ($select) - multiselect array |
| `filter_expression` | No | OData $filter expression |
| `expand_properties` | No | Navigation properties to expand ($expand) - multiselect array |
| `order_by` | No | Field for ordering ($orderby) |
| `sync_type` | No | Sync type: `full` or `incremental` (default: `full`) |
| `incremental_field` | For incremental | Field for incremental sync (shows when sync_type=incremental) |
| `primary_key` | For incremental | Primary key fields - multiselect array (shows when sync_type=incremental) |
| `page_size` | No | Override default page size for this entity |
| `max_records` | No | Override default max records for this entity |

## SAP Service Catalog Support

### What is a Service Catalog?

A **Service Catalog** is a SAP-specific endpoint that lists all available OData services in your SAP system. This is **not part of the OData standard** - it's SAP proprietary.

Instead of directly connecting to an OData service, you can browse the catalog to see what services are available, then copy the service path to your configuration.

### Using Service Catalog

#### Step 1: Configure Catalog Endpoint

Set `catalog_path` instead of `service_path`:

```json
{
  "parameters": {
    "base_url": "https://your-sap-system.com",
    "catalog_path": "sap/opu/odata/IWFND/CATALOGSERVICE;v=2/ServiceCollection",
    "auth_type": "oauth",
    "token_url": "https://your-auth.com/oauth/token",
    "client_id": "your-client-id",
    "#client_secret": "your-secret"
  }
}
```

#### Step 2: Browse Available Services

Run the **loadEntities** sync action. Instead of entity sets, you'll get a list of available OData services:

```json
[
  {
    "value": "ZAPI_BUSINESS_PARTNER_0001",
    "label": "API_BUSINESS_PARTNER - Business Partner API"
  },
  {
    "value": "ZFCLM_CASH_BANKTRANSFER_SRV_0001",
    "label": "FCLM_CASH_BANKTRANSFER_SRV - Bank Transfer"
  }
]
```

#### Step 3: Use Service Path

From the catalog results, copy the service name (without the `Z...._0001` prefix) and use it as `service_path`:

```json
{
  "parameters": {
    "base_url": "https://your-sap-system.com",
    "service_path": "sap/opu/odata/sap/FCLM_CASH_BANKTRANSFER_SRV",
    "auth_type": "oauth",
    ...
  }
}
```

Now **loadEntities** will return entity sets from that service, and you can proceed with normal data extraction.

### Important Limitations

#### 1. Authentication Issue

**Problem:** Catalog and actual services may require different authentication.

**Example:**
- Catalog is accessed via SAP CPI proxy with OAuth 2.0
- Catalog returns service URLs like `http://20.113.120.45:50000/sap/opu/odata/sap/SERVICE_NAME`
- Those internal URLs require SAP Basic Auth (username/password), not OAuth

**Solution:** Use the catalog to **browse only**. Don't try to use the exact URLs returned by the catalog. Instead, use your proxy/gateway URL structure.

#### 2. Internal URLs

**Problem:** Catalog often returns **internal private IP addresses** (e.g., `http://20.113.120.45:50000` or `http://10.x.x.x`).

**Why this happens:**
- `20.x.x.x`, `10.x.x.x`, `192.168.x.x` are private IP ranges
- Only accessible from inside the SAP network
- Not routable from the internet

**Solution:**
- Extract only the **service name** from catalog entries (e.g., `FCLM_CASH_BANKTRANSFER_SRV`)
- Construct your own URL using your **public gateway/proxy** URL
- Example: `https://your-cpi-proxy.com/http/path/to/FCLM_CASH_BANKTRANSFER_SRV`

### Catalog vs. Direct Service

| Mode | catalog_path set | service_path set | loadEntities returns |
|------|-----------------|------------------|---------------------|
| **Browsing catalog** | ✅ Yes | ❌ No | List of OData services |
| **Using service** | ❌ No | ✅ Yes | List of entity sets |

**Note:** You cannot set both `catalog_path` and `service_path` at the same time. If `catalog_path` is set, it takes precedence.

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
    "base_url": "https://sandbox.api.sap.com/s4hanacloud",
    "service_path": "API_BUSINESS_PARTNER",
    "odata_version": "auto",
    "auth_type": "apiKey",
    "#api_key": "your-api-key",
    "page_size": 1000,
    "max_records": 0
  },
  "storage": {
    "output": {
      "tables": [
        {
          "source": "A_BusinessPartner.csv",
          "destination": "out.c-sap.business-partners"
        }
      ]
    }
  }
}
```

Create `data/config_row.json` for entity configuration:

```json
{
  "parameters": {
    "entity_set": "A_BusinessPartner",
    "output_table_name": "A_BusinessPartner",
    "select_fields": ["BusinessPartner", "BusinessPartnerName", "CreatedByUser"],
    "filter_expression": "BusinessPartnerCategory eq '1'",
    "sync_type": "full",
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

### UI Schema Development

Use the schema-tester tool to develop and test configuration schemas:

```bash
# Open schema tester (from project root)
open schema-tester/index.html

# Or use the plugin version directly
open ~/.claude/plugins/marketplaces/keboola-claude-kit/plugins/component-ui-developer/tools/schema-tester/index.html
```

The schema-tester provides:
- **Live preview** of configSchema.json and configRowSchema.json
- **Conditional fields testing** - verify options.dependencies work correctly
- **Button visualization** - see sync action buttons (Test Connection, Validate Filter, Preview Data)
- **Multiselect testing** - test array fields with format: select
- **Real-time validation** - see JSON output and errors instantly

For UI development help, use the Claude plugin:
```bash
/plugin component-ui-developer ui-developer
```

## Documentation

- **[Configuration Patterns](docs/CONFIGURATION_PATTERNS.md)** - Recommended patterns for load_type & fetch_type combinations
- [URL Structure Analysis](docs/URL_STRUCTURE_ANALYSIS.md) - Detailed analysis of SAP OData URL patterns
- [Development Guide](docs/DEVELOPMENT.md) - Complete development and testing guide
- [Sample Configurations](data/README.md) - Example configurations for different scenarios

## License

MIT License

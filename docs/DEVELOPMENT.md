# Development Guide

## Getting Started

### Prerequisites
- Python 3.12+
- uv (Python package manager)
- SAP API Business Hub API Key (for testing)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd component-ex-sap-odata
```

2. Install dependencies:
```bash
uv sync --all-extras
```

3. Run tests:
```bash
PYTHONPATH=src uv run pytest
```

## Getting SAP API Key for Testing

To run functional tests, you need an API key from SAP API Business Hub.

### Step 1: Create SAP Account

1. Go to [SAP API Business Hub](https://api.sap.com/)
2. Click **Log On** in the top right
3. Create a new account or log in with existing SAP credentials

### Step 2: Get API Key

1. Once logged in, click on your profile icon (top right)
2. Click **Settings** or **Show API Key**
3. Your API key will be displayed - copy it
4. Alternatively, navigate to any API and click **Try Out** - your API key will be shown there

### Step 3: Test Your API Key

Test with a simple curl command:

```bash
curl -H "APIKey: YOUR-API-KEY" \
  "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_COMPANYCODE_SRV/A_CompanyCode?\$format=json&\$top=5"
```

You should get a JSON response with company code data.

### Useful SAP API Business Hub APIs for Testing

#### OData V2 APIs

**Company Code API**
- URL: `https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_COMPANYCODE_SRV`
- Entity: `A_CompanyCode`
- Try it: [API_COMPANYCODE_SRV](https://api.sap.com/api/API_COMPANYCODE_SRV/tryout)

**Business Partner API**
- URL: `https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_BUSINESS_PARTNER`
- Entity: `A_BusinessPartner`
- Try it: [API_BUSINESS_PARTNER](https://api.sap.com/api/API_BUSINESS_PARTNER/tryout)

#### OData V4 APIs

**Fixed Asset Acquisition API**
- URL: `https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata4/sap/api_fixedassetacquisition/srvd_a2x/sap/fixedassetacquisition/0001`
- Entity: `FixedAssetAcquisition`
- Try it: [CE_FIXEDASSETACQUISITION_0001](https://api.sap.com/api/CE_FIXEDASSETACQUISITION_0001/tryout)

## Running Functional Tests

### Local Development

1. Set your API key as environment variable:
```bash
export SAP_API_KEY="your-api-key-here"
```

2. Run functional tests:
```bash
PYTHONPATH=src uv run pytest tests/functional/ -v
```

### Environment Variables

Create a `.env` file (NOT committed to git):
```bash
# .env
SAP_API_KEY=your-api-key-here
```

Load it before running tests:
```bash
source .env
PYTHONPATH=src uv run pytest tests/functional/ -v
```

### Skip Functional Tests

Functional tests are automatically skipped if `SAP_API_KEY` is not set:
```bash
# This will skip functional tests
PYTHONPATH=src uv run pytest
```

## Manual Testing

### Using Sample Configs

1. Copy a sample config:
```bash
cp data/config.sample.v4-api-key.json data/config.json
```

2. Edit `data/config.json` with your API key:
```json
{
  "parameters": {
    "#api_key": "your-api-key-here",
    ...
  }
}
```

3. Create output directory:
```bash
mkdir -p data/out/tables
```

4. Run the component:
```bash
KBC_DATADIR=./data python3 src/component.py
```

5. Check results:
```bash
ls -lh data/out/tables/
cat data/out/tables/*.csv | head -20
```

## Testing Different Scenarios

### Test OData V2 with Basic Auth
```bash
cp data/config.sample.v2-basic-auth.json data/config.json
# Edit with your SAP credentials
KBC_DATADIR=./data python3 src/component.py
```

### Test OData V4 with API Key
```bash
cp data/config.sample.v4-api-key.json data/config.json
# Edit with your API key
KBC_DATADIR=./data python3 src/component.py
```

### Test Split URL Configuration
```bash
cp data/config.sample.v2-split-url.json data/config.json
# Edit with your credentials
KBC_DATADIR=./data python3 src/component.py
```

### Test Incremental Sync
```bash
cp data/config.sample.incremental-sync.json data/config.json
# Edit with your credentials
KBC_DATADIR=./data python3 src/component.py

# Run again - should only fetch new records
KBC_DATADIR=./data python3 src/component.py
```

## Code Quality

### Run Linter
```bash
uv run ruff check src/ tests/
```

### Run Type Checker
```bash
uv run mypy src/ tests/
```

### Format Code
```bash
uv run ruff format src/ tests/
```

## Debugging

### Enable Debug Logging
Set the logging level in your config:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Inspect HTTP Requests
The component uses `keboola.http_client` which logs all requests. Check logs for:
- Request URLs
- Response status codes
- Error messages

### Check Metadata
```bash
# Fetch metadata to understand entity structure
curl -H "APIKey: YOUR-KEY" \
  "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_COMPANYCODE_SRV/\$metadata"
```

## CI/CD

### GitHub Actions

Functional tests run in GitHub Actions when `SAP_API_KEY` secret is set.

**Setting up GitHub Secret:**
1. Go to repository **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `SAP_API_KEY`
4. Value: Your SAP API key
5. Click **Add secret**

### Running Tests in CI

The workflow automatically:
- Runs unit tests on every push
- Runs functional tests when `SAP_API_KEY` secret is available
- Skips functional tests if secret is not set (e.g., in forks)

## Troubleshooting

### "401 Unauthorized" Error
- Check your API key is correct
- Verify the API key hasn't expired
- Try regenerating your API key on SAP API Business Hub

### "404 Not Found" Error
- Verify the service URL is correct
- Check the entity set name matches the API documentation
- Ensure you're using the correct OData version (v2 vs v4)

### "No data extracted"
- Check your filter expression syntax
- Verify the entity set contains data
- Try removing the filter to see all data
- Check `max_records` isn't set to 0 or too low

### Tests Failing Locally
- Ensure `PYTHONPATH=src` is set when running pytest
- Check Python version is 3.12+
- Run `uv sync --all-extras` to update dependencies
- Clear pytest cache: `rm -rf .pytest_cache`

## Resources

- [SAP API Business Hub](https://api.sap.com/)
- [SAP S/4HANA OData APIs](https://api.sap.com/package/SAPS4HANACloud/odata)
- [OData V2 Specification](https://www.odata.org/documentation/odata-version-2-0/)
- [OData V4 Specification](https://www.odata.org/documentation/)
- [Keboola Developer Documentation](https://developers.keboola.com/)

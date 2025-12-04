# Functional Tests (Datadir Pattern)

This directory contains functional tests using the Keboola datadir test pattern.

## Test Structure

Each test case is a directory with the following structure:

```
test-case-name/
├── config.json              # Component configuration with env placeholders
├── expected-code            # Expected exit code (0 = success)
├── source/
│   └── data/
│       ├── in/
│       │   ├── tables/      # Input CSV tables (usually empty for extractors)
│       │   └── files/       # Input files
│       └── ...
└── expected/
    └── data/
        └── out/
            ├── tables/      # Expected output CSV tables (optional)
            └── files/       # Expected output files (optional)
```

## Environment Variables in Config

Use the placeholder format `%env(TYPE:VAR_NAME)%` in `config.json`:

```json
{
  "parameters": {
    "#api_key": "%env(string:SAP_API_KEY)%",
    "max_records": "%env(int:MAX_RECORDS)%"
  }
}
```

Supported types: `string`, `int`, `float`, `bool`

## Running Tests

### Run all functional tests:
```bash
export SAP_API_KEY="your-api-key"
PYTHONPATH=src uv run pytest tests/functional/run_datadir_tests.py -v
```

### Run specific test case:
```bash
PYTHONPATH=src uv run pytest tests/functional/run_datadir_tests.py::TestDatadirFunctional::test_datadir_case[test-v2-company-code] -v
```

### Tests are automatically skipped if SAP_API_KEY is not set:
```bash
# Without API key - tests will be skipped
PYTHONPATH=src uv run pytest tests/functional/ -v
```

## Available Test Cases

### `test-v2-company-code`
- Tests OData V2 extraction
- API: SAP Company Code API (API_COMPANYCODE_SRV)
- Entity: A_CompanyCode
- Features: Basic extraction with field selection

### `test-v4-fixed-asset`
- Tests OData V4 extraction with split URL configuration
- API: Fixed Asset Acquisition API
- Entity: FixedAssetAcquisition
- Features: Split URL (base_url + service_path), filtering

## Adding New Test Cases

1. Create a new directory: `test-your-test-name/`
2. Create the directory structure:
   ```bash
   mkdir -p test-your-test-name/{source/data/{in/tables,in/files},expected/data/{out/tables,out/files}}
   ```
3. Create `config.json` with your test configuration
4. Create `expected-code` with the expected exit code (usually `0`)
5. (Optional) Add expected output CSV files to `expected/data/out/tables/`
6. Run the test:
   ```bash
   export SAP_API_KEY="your-key"
   PYTHONPATH=src uv run pytest tests/functional/run_datadir_tests.py -v
   ```

## How It Works

The test runner (`run_datadir_tests.py`):
1. Discovers all directories starting with `test-`
2. Processes `config.json` and replaces environment variable placeholders
3. Creates a temporary data directory
4. Runs the component with `KBC_DATADIR` set to the temp directory
5. Compares the exit code with `expected-code`
6. Verifies that output files were created
7. (Optional) Compares output with expected files

## CI/CD

In GitHub Actions, functional tests run when the `SAP_API_KEY` secret is set:

```yaml
- name: Run Functional Tests
  if: ${{ secrets.SAP_API_KEY != '' }}
  env:
    SAP_API_KEY: ${{ secrets.SAP_API_KEY }}
  run: |
    docker run -e SAP_API_KEY=${{ secrets.SAP_API_KEY }} component:latest \
      python -m pytest /code/tests/functional -v
```

## Troubleshooting

**Tests are skipped:**
- Make sure `SAP_API_KEY` environment variable is set
- Check that the API key is valid

**Component fails:**
- Check the STDOUT/STDERR in the test output
- Try running the component manually with the test config
- Verify the API endpoint is accessible

**No output files created:**
- Check if the entity set exists in the API
- Verify filter expressions are correct
- Check max_records isn't set to 0

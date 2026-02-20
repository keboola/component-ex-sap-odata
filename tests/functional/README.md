# Functional Tests

This directory contains datadir tests for the SAP OData extractor component.

## Test Categories

### Sync Actions (8 tests)
- `test-sync-testconnection` - testConnection sync action
- `test-sync-loadentities` - loadEntities sync action
- `test-sync-loadfields` - loadFields sync action
- `test-sync-loadincrementalfields` - loadIncrementalFields sync action
- `test-sync-loadprimarykeys` - loadPossiblePrimaryKeys sync action
- `test-sync-loadnavproperties` - loadNavigationProperties sync action
- `test-sync-validatefilter` - validateFilter sync action
- `test-sync-previewdata` - previewData sync action

### Authentication (2 tests)
- `test-auth-apikey` - API Key authentication
- `test-auth-basic` - Basic authentication

### Extraction Types (4 tests)
- `test-extract-full-full` - Full fetch + Full load
- `test-extract-full-incremental` - Full fetch + Incremental load
- `test-extract-incremental-full` - Incremental fetch + Full load
- `test-extract-incremental-incremental` - Incremental fetch + Incremental load

### Query Options (4 tests)
- `test-query-select` - Select fields ($select)
- `test-query-filter` - Filter expression ($filter)
- `test-query-expand` - Expand navigation properties ($expand)
- `test-query-combined` - Combined query options

### OData Versions (3 tests)
- `test-version-auto` - Auto version detection
- `test-version-v2` - Forced OData V2
- `test-version-v4` - Forced OData V4

### Advanced Options (3 tests)
- `test-advanced-connection` - Connection options (timeout, retries, SSL)
- `test-advanced-pagination-global` - Global pagination defaults
- `test-advanced-pagination-row` - Row-level pagination override

## Test Data Sources

Tests use publicly available OData services:

- **Northwind OData V4**: https://services.odata.org/V4/Northwind/Northwind.svc
  - Used for: V4 tests, basic auth tests
  - No API key required

- **TripPin OData V4**: https://services.odata.org/V4/TripPinServiceRW
  - Used for: Sample OData V4 service
  - No API key required

## Running Tests

### Generate Expected Data

```bash
cd tests/functional
./generate_expected_data.sh
```

### Run All Tests

```bash
PYTHONPATH=src uv run pytest tests/functional/run_datadir_tests.py -v
```

### Run Specific Test

```bash
PYTHONPATH=src uv run pytest tests/functional/run_datadir_tests.py::test_functional[test-version-v4] -v
```

## Notes

- SAP API Business Hub tests require API key (set SAP_API_KEY environment variable)
- Some SAP endpoints may not be available on sandbox environment
- Tests use small page sizes (5-20 records) to minimize test execution time

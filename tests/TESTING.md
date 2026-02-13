# SAP OData Component Testing Guide

This document describes the comprehensive test suite for the SAP OData component.

## Test Structure

The test suite includes:

1. **Unit Tests** - Testing individual functions and methods
2. **Mocked Integration Tests** - Testing component with mocked OData servers
3. **Datadir Tests** - Production-like functional tests with real/test OData endpoints

## Test Organization

```
tests/
├── fixtures/
│   ├── mock_odata_server.py       # Mock OData V2/V4/Catalog servers
│   └── __init__.py
├── functional/                     # Datadir-style functional tests
│   ├── test-v4-basic-mocked/       # V4 basic extraction
│   ├── test-v4-incremental-mocked/ # V4 incremental with state
│   ├── test-v4-filter-select/      # V4 with filtering and field selection
│   ├── test-v2-basic-mocked/       # V2 basic extraction
│   ├── test-error-missing-entity/  # Error scenario: missing entity_set
│   ├── test-v2-basic-auth/         # Existing V2 test (real endpoint)
│   ├── test-v4-fixed-asset/        # Existing V4 test (real endpoint)
│   └── run_datadir_tests.py        # Datadir test runner
├── conftest.py                     # Shared pytest fixtures
├── test_datadir_mocked.py          # Comprehensive mocked tests
├── test_component.py               # Unit tests for Component class
├── test_configuration.py           # Unit tests for Configuration
├── test_metadata.py                # Unit tests for metadata parsing
└── TESTING.md                      # This file
```

## Mocked Tests

### Overview

The mocked tests (`test_datadir_mocked.py`) use the `responses` library to mock HTTP responses from OData servers. This allows for:

- Fast test execution (no network calls)
- Deterministic results
- Testing edge cases and error scenarios
- No dependency on external SAP systems

### Mock Server Implementations

**`MockODataV4Server`** - Mocks OData V4 service with:
- Products entity set with 5 sample records
- Support for $filter, $select, $skip, $top
- Pagination with @odata.nextLink
- Metadata endpoint with realistic V4 schema

**`MockODataV2Server`** - Mocks OData V2 service with:
- A_BusinessPartner entity set with 5 sample records
- Support for $filter, $select, $skip, $top
- Pagination with __next link
- Metadata endpoint with realistic V2 schema
- SAP-style JSON format (d.results)

**`MockSAPCatalogServer`** - Mocks SAP Service Catalog with:
- ServiceCollection endpoint
- List of available OData services
- Catalog metadata

### Running Mocked Tests

```bash
# Run all mocked tests
pytest tests/test_datadir_mocked.py -v

# Run specific test class
pytest tests/test_datadir_mocked.py::TestODataV4BasicExtraction -v

# Run specific test
pytest tests/test_datadir_mocked.py::TestODataV4BasicExtraction::test_v4_basic_extraction -v

# Run with coverage
pytest tests/test_datadir_mocked.py --cov=src --cov-report=html
```

### Test Coverage

The mocked tests cover:

#### OData V4
- Basic extraction (all records)
- Field selection ($select)
- Filtering ($filter)
- Pagination (small page size)
- Max records limit
- Incremental extraction (first run)
- Incremental extraction (subsequent run with state)
- Split URL configuration (base_url + service_path)

#### OData V2
- Basic extraction (all records)
- Field selection ($select)
- Filtering ($filter)
- Incremental extraction with datetime fields
- Split URL configuration

#### Sync Actions
- testConnection (V2 and V4)
- loadEntities (V2 and V4)
- loadFields (V2 and V4)
- Catalog browsing (loadEntities with catalog_path)

#### Authentication
- Basic authentication
- API Key authentication
- OAuth 2.0 authentication

#### Load Types
- Full load (incremental=false)
- Incremental load with primary key
- Custom output table name

#### Error Scenarios
- Authentication error (401)
- Missing entity_set configuration
- Invalid configuration
- Incremental without incremental_field

## Datadir Tests

### Overview

Datadir tests follow the Keboola component testing pattern where each test case is a directory containing:

- `config.json` - Component configuration
- `expected-code` - Expected exit code (0 for success, 1 for user error, 2 for system error)
- `source/data/in/` - Input data (state, tables)
- `expected/data/out/` - Expected output (optional)

### Running Datadir Tests

```bash
# Run all functional tests (requires SAP_API_KEY or other credentials)
pytest tests/functional/run_datadir_tests.py -v

# Run specific test case
pytest tests/functional/run_datadir_tests.py -v -k "test-v4-basic"

# Skip tests requiring environment variables
pytest tests/functional/run_datadir_tests.py -v --skip-missing-env
```

### Environment Variables for Datadir Tests

Tests can reference environment variables using `%env(TYPE:VAR_NAME)%` syntax in config.json:

```json
{
  "parameters": {
    "username": "%env(string:SAP_USERNAME)%",
    "#password": "%env(string:SAP_PASSWORD)%",
    "#api_key": "%env(string:SAP_API_KEY)%"
  }
}
```

Supported types:
- `string` - String value
- `int` - Integer value
- `float` - Float value
- `bool` - Boolean value

## Unit Tests

### Running Unit Tests

```bash
# Run all unit tests
pytest tests/test_*.py -v --ignore=tests/functional

# Run specific test file
pytest tests/test_component.py -v

# Run with coverage
pytest tests/test_component.py --cov=src.component --cov-report=term-missing
```

### Test Files

- `test_component.py` - Component class methods (_format_filter_literal, _get_field_edm_type, etc.)
- `test_configuration.py` - Configuration model validation
- `test_metadata.py` - OData metadata parsing (V2 and V4)
- `test_catalog_parser.py` - SAP catalog XML parsing
- `test_type_mapping.py` - EDM type to Python type mapping

## Fixtures

### Pytest Fixtures (conftest.py)

**`mock_v4_server`** - Provides MockODataV4Server instance

**`mock_v2_server`** - Provides MockODataV2Server instance

**`mock_catalog_server`** - Provides MockSAPCatalogServer instance

**`datadir_factory`** - Factory to create test datadir structures
```python
def test_example(datadir_factory):
    config = {"entity_set": "Products", ...}
    in_state = {"entity_states": {...}}
    datadir = datadir_factory(config, in_state=in_state)
```

**`run_component_with_datadir`** - Run component with specific datadir
```python
def test_example(datadir_factory, run_component_with_datadir):
    datadir = datadir_factory(config)
    run_component_with_datadir(datadir)
```

**`run_sync_action_with_datadir`** - Run sync action with specific datadir
```python
def test_example(datadir_factory, run_sync_action_with_datadir):
    datadir = datadir_factory(config)
    run_sync_action_with_datadir(datadir, "testConnection")
```

**`verify_output_table`** - Verify output table structure and content
```python
def test_example(datadir_factory, run_component_with_datadir, verify_output_table):
    datadir = datadir_factory(config)
    run_component_with_datadir(datadir)
    rows = verify_output_table(
        datadir,
        "Products",
        min_rows=5,
        expected_columns=["ID", "Name"]
    )
```

**`verify_state`** - Verify output state
```python
def test_example(datadir_factory, run_component_with_datadir, verify_state):
    datadir = datadir_factory(config)
    run_component_with_datadir(datadir)
    state = verify_state(datadir)
    assert state["entity_states"]["Products"]["records_synced"] == 5
```

## Best Practices

### Writing New Tests

1. **Use mocked tests for logic testing** - Fast, deterministic, no external dependencies
2. **Use datadir tests for integration testing** - Real network calls, production-like scenarios
3. **Test both happy path and error scenarios**
4. **Verify state management for incremental extractions**
5. **Check manifest files (incremental, primary_key) in output**

### Example: Adding a New Test

```python
# In test_datadir_mocked.py
@responses.activate
def test_my_new_feature(
    mock_v4_server,
    datadir_factory,
    run_component_with_datadir,
    verify_output_table
):
    """Test description."""
    # Setup mock
    mock_v4_server.setup(responses)

    # Configure
    config = {
        "service_url": mock_v4_server.base_url,
        "odata_version": "v4",
        "auth_type": "basic",
        "username": "test",
        "#password": "test",
        "entity_set": "Products",
        # Your specific config
    }

    # Create datadir
    datadir = datadir_factory(config)

    # Run
    run_component_with_datadir(datadir)

    # Verify
    rows = verify_output_table(datadir, "Products", min_rows=1)
    assert rows[0]["SomeField"] == "ExpectedValue"
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-cov responses

      - name: Run unit tests
        run: pytest tests/test_*.py --ignore=tests/functional -v --cov=src

      - name: Run mocked integration tests
        run: pytest tests/test_datadir_mocked.py -v --cov=src --cov-append

      - name: Run datadir tests (if credentials available)
        if: env.SAP_API_KEY != ''
        env:
          SAP_API_KEY: ${{ secrets.SAP_API_KEY }}
        run: pytest tests/functional/run_datadir_tests.py -v
```

## Troubleshooting

### Common Issues

**Event loop conflicts**
- The `reset_event_loop` fixture in conftest.py handles this
- If issues persist, run tests in isolation: `pytest --forked`

**State file not created**
- Check that component runs successfully (exit code 0)
- Verify `write_state_file()` is called in component

**Manifest validation fails**
- Ensure manifest is valid JSON
- Check that incremental/primary_key match expected values

**Mock server not responding**
- Verify `mock_server.setup(responses)` is called
- Check that `@responses.activate` decorator is present
- Ensure URLs match exactly (trailing slashes, etc.)

## Test Metrics

Run tests with coverage to see test quality metrics:

```bash
# Generate HTML coverage report
pytest tests/test_datadir_mocked.py --cov=src --cov-report=html

# View report
open htmlcov/index.html
```

Target coverage: 80%+ for core components (component.py, configuration.py, metadata.py)

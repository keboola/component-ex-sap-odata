# SAP OData Component Tests

Quick reference for running tests. For detailed documentation, see [TESTING.md](TESTING.md).

## Quick Start

```bash
# Run all mocked tests (recommended for development)
./tests/run_mocked_tests.sh

# Or with pytest
pytest tests/test_datadir_mocked.py tests/test_sync_actions_mocked.py -v
```

## Test Categories

### 1. Mocked Integration Tests (Fast, No SAP Access Needed)

```bash
# All mocked tests
pytest tests/test_datadir_mocked.py tests/test_sync_actions_mocked.py -v

# Just datadir mocked tests
pytest tests/test_datadir_mocked.py -v

# Just sync action tests
pytest tests/test_sync_actions_mocked.py -v

# With coverage
pytest tests/test_datadir_mocked.py --cov=src --cov-report=html
```

**What's tested:**
- OData V2 and V4 extraction
- All authentication methods
- All sync actions
- Incremental extraction
- Filtering, pagination, field selection
- Error scenarios

### 2. Unit Tests

```bash
# All unit tests
pytest tests/test_*.py --ignore=tests/functional -v

# Specific test file
pytest tests/test_component.py -v
pytest tests/test_configuration.py -v
pytest tests/test_metadata.py -v
```

### 3. Datadir Tests (Requires SAP Credentials)

```bash
# All functional tests
pytest tests/functional/run_datadir_tests.py -v

# With SAP credentials
export SAP_API_KEY="your-api-key"
pytest tests/functional/run_datadir_tests.py -v
```

## Test Files

- `test_datadir_mocked.py` - Mocked datadir-style tests (30+ tests)
- `test_sync_actions_mocked.py` - Sync action tests (20+ tests)
- `test_component.py` - Component unit tests
- `test_configuration.py` - Configuration validation tests
- `test_metadata.py` - Metadata parsing tests
- `fixtures/mock_odata_server.py` - Mock server implementations
- `conftest.py` - Shared pytest fixtures

## Documentation

- [TESTING.md](TESTING.md) - Comprehensive testing guide
- [TEST_SUMMARY.md](TEST_SUMMARY.md) - Complete test suite summary

## Common Commands

```bash
# Run single test
pytest tests/test_datadir_mocked.py::TestODataV4BasicExtraction::test_v4_basic_extraction -v

# Run test class
pytest tests/test_datadir_mocked.py::TestODataV4BasicExtraction -v

# Run with detailed output
pytest tests/test_datadir_mocked.py -vv

# Run with print statements
pytest tests/test_datadir_mocked.py -v -s

# Generate coverage report
pytest tests/test_datadir_mocked.py --cov=src --cov-report=html
open htmlcov/index.html
```

## Requirements

```bash
pip install pytest responses pytest-cov
```

## Features Tested

✅ OData V2 and V4 protocols
✅ Basic, API Key, and OAuth authentication
✅ Full and incremental extraction
✅ State management
✅ Filtering and field selection
✅ Pagination
✅ All sync actions (testConnection, loadEntities, etc.)
✅ SAP Catalog browsing
✅ Error handling
✅ Split URL configuration

## Coverage

Run tests with coverage to ensure quality:

```bash
pytest tests/test_datadir_mocked.py tests/test_sync_actions_mocked.py \
  --cov=src --cov-report=term-missing --cov-report=html
```

Target: 80%+ coverage for core components

## Need Help?

See [TESTING.md](TESTING.md) for:
- Detailed test descriptions
- Writing new tests
- Troubleshooting
- CI/CD integration
- Best practices

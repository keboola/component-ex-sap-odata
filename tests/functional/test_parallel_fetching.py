#!/usr/bin/env python3
"""Functional tests for parallel fetching with async clients."""

import os

# Add src to path
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from odata_client.sync_wrapper import SyncODataV4Client

# Configuration
SAP_BASE_URL = "https://sandbox.api.sap.com/s4hanacloud"
SAP_SERVICE_PATH = "/sap/opu/odata4/sap/api_fixedassetacquisition/srvd_a2x/sap/fixedassetacquisition/0001"
SAP_API_KEY = os.getenv("SAP_API_KEY", "")
ENTITY_SET = "FixedAssetAcquisition"

pytestmark = pytest.mark.skipif(not SAP_API_KEY, reason="SAP_API_KEY environment variable not set")


@pytest.fixture
def sync_client_parallel() -> SyncODataV4Client:
    """Create sync client with parallel fetching enabled."""
    client = SyncODataV4Client.from_api_key(
        api_key=SAP_API_KEY,
        header_name="APIKey",
        base_url=f"{SAP_BASE_URL}{SAP_SERVICE_PATH}",
        parallel_pages=5,
    )
    yield client
    client.close()


@pytest.fixture
def sync_client_sequential() -> SyncODataV4Client:
    """Create sync client with parallel fetching disabled."""
    client = SyncODataV4Client.from_api_key(
        api_key=SAP_API_KEY,
        header_name="APIKey",
        base_url=f"{SAP_BASE_URL}{SAP_SERVICE_PATH}",
        parallel_pages=1,
    )
    yield client
    client.close()


def test_parallel_fetching_returns_same_data(
    sync_client_parallel: SyncODataV4Client, sync_client_sequential: SyncODataV4Client
):
    """Test that parallel fetching returns the same data as sequential."""
    # Fetch with parallel
    parallel_records = list(
        sync_client_parallel.fetch_with_pagination(
            entity_set=ENTITY_SET,
            page_size=100,
        )
    )

    # Fetch with sequential
    sequential_records = list(
        sync_client_sequential.fetch_with_pagination(
            entity_set=ENTITY_SET,
            page_size=100,
        )
    )

    # Should have same number of records
    assert len(parallel_records) == len(sequential_records)

    # Records should be identical (order may differ in real scenarios but not with $skip pagination)
    assert parallel_records == sequential_records


def test_parallel_fetching_is_faster(
    sync_client_parallel: SyncODataV4Client, sync_client_sequential: SyncODataV4Client
):
    """Test that parallel fetching is faster than sequential for large datasets."""
    # Note: This test may be flaky depending on API performance
    # We're not asserting hard timing requirements, just measuring

    # Parallel fetch
    start_parallel = time.time()
    parallel_records = list(
        sync_client_parallel.fetch_with_pagination(
            entity_set=ENTITY_SET,
            page_size=100,
        )
    )
    parallel_time = time.time() - start_parallel

    # Sequential fetch
    start_sequential = time.time()
    sequential_records = list(
        sync_client_sequential.fetch_with_pagination(
            entity_set=ENTITY_SET,
            page_size=100,
        )
    )
    sequential_time = time.time() - start_sequential

    print(f"\nParallel fetch: {len(parallel_records)} records in {parallel_time:.2f}s")
    print(f"Sequential fetch: {len(sequential_records)} records in {sequential_time:.2f}s")
    print(f"Speedup: {sequential_time / parallel_time:.2f}x")

    # For reporting purposes - parallel should generally be faster for multiple pages
    # But we don't assert this as it depends on API performance and network conditions
    assert len(parallel_records) == len(sequential_records)


def test_parallel_fetching_with_filter(sync_client_parallel: SyncODataV4Client):
    """Test parallel fetching with filter expression."""
    records = list(
        sync_client_parallel.fetch_with_pagination(
            entity_set=ENTITY_SET,
            filter_expr="CompanyCode eq '1710'",
            page_size=50,
        )
    )

    assert len(records) > 0
    # Verify all records match filter
    for record in records:
        assert record.get("CompanyCode") == "1710"


def test_parallel_fetching_with_select(sync_client_parallel: SyncODataV4Client):
    """Test parallel fetching with field selection."""
    selected_fields = ["FixedAssetPostingUUID", "CompanyCode", "MasterFixedAsset"]

    records = list(
        sync_client_parallel.fetch_with_pagination(
            entity_set=ENTITY_SET,
            select=selected_fields,
            page_size=100,
        )
    )

    assert len(records) > 0
    # Verify selected fields are present (API may include additional fields like keys)
    for record in records:
        for field in selected_fields:
            assert field in record, f"Field {field} not in record"


def test_parallel_fetching_with_orderby(sync_client_parallel: SyncODataV4Client):
    """Test parallel fetching with ordering."""
    records = list(
        sync_client_parallel.fetch_with_pagination(
            entity_set=ENTITY_SET,
            order_by="CompanyCode",
            page_size=50,
        )
    )

    assert len(records) > 0
    # Verify records are ordered
    company_codes = [r.get("CompanyCode") for r in records]
    assert company_codes == sorted(company_codes)


def test_parallel_pages_configuration(sync_client_parallel: SyncODataV4Client):
    """Test that parallel_pages configuration is respected."""
    # Client is configured with parallel_pages=5
    # We can't directly verify batch size, but we can verify it works correctly
    records = list(
        sync_client_parallel.fetch_with_pagination(
            entity_set=ENTITY_SET,
            page_size=20,  # Small pages to ensure multiple batches
        )
    )

    assert len(records) > 0


def test_get_record_count(sync_client_parallel: SyncODataV4Client):
    """Test getting total record count."""
    count = sync_client_parallel.get_record_count(ENTITY_SET)

    assert count is not None
    assert count > 0
    print(f"\nTotal records in {ENTITY_SET}: {count}")


def test_metadata_operations(sync_client_parallel: SyncODataV4Client):
    """Test metadata operations work with async client."""
    # List entity sets
    entity_sets = sync_client_parallel.list_entity_sets()
    assert len(entity_sets) > 0
    assert any(es.name == ENTITY_SET for es in entity_sets)

    # List fields
    fields = sync_client_parallel.list_fields(ENTITY_SET)
    assert len(fields) > 0

    # Test connection
    success, message = sync_client_parallel.test_connection()
    assert success is True
    assert "successful" in message.lower()


@pytest.mark.parametrize("page_size", [10, 50, 100, 500])
def test_different_page_sizes(sync_client_parallel: SyncODataV4Client, page_size: int):
    """Test parallel fetching with different page sizes."""
    records = list(
        sync_client_parallel.fetch_with_pagination(
            entity_set=ENTITY_SET,
            page_size=page_size,
        )
    )

    assert len(records) > 0
    print(f"\nPage size {page_size}: fetched {len(records)} records")


def test_rate_limiting():
    """Test rate limiting configuration."""
    client = SyncODataV4Client.from_api_key(
        api_key=SAP_API_KEY,
        header_name="APIKey",
        base_url=f"{SAP_BASE_URL}{SAP_SERVICE_PATH}",
        parallel_pages=3,
        max_requests_per_second=2.0,  # Limit to 2 requests per second
    )

    start = time.time()
    records = list(
        client.fetch_with_pagination(
            entity_set=ENTITY_SET,
            page_size=100,
        )
    )
    elapsed = time.time() - start

    assert len(records) > 0
    print(f"\nWith rate limiting (2 req/s): {len(records)} records in {elapsed:.2f}s")

    client.close()


if __name__ == "__main__":
    # Run with: pytest tests/functional/test_parallel_fetching.py -v -s
    pytest.main([__file__, "-v", "-s"])

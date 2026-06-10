"""Regression tests for full-load pagination against SAP-style OData services.

Reproduces CFTL-681 follow-up: a full load of a SAP CDS truncated to a single
page (e.g. 1000 rows) instead of fetching the whole entity set.

Two compounding root causes are covered here:

1. ``get_record_count`` passed ``endpoint_path=`` to ``AsyncHttpClient.get_raw``,
   which only accepts ``endpoint=``. The bad kwarg leaked to ``httpx`` and raised,
   so the count was always swallowed as ``None`` and parallel fetching never engaged.

2. Sequential pagination sent ``$top=page_size`` and then relied on a server-driven
   ``__next`` / ``@odata.nextLink``. SAP Gateway treats ``$top`` as a hard total cap
   and returns **no** next link, so the loop stopped after the first page. The fix
   falls back to client-driven ``$skip`` paging when no next link is present.

The mock servers here intentionally model SAP Gateway behaviour: they honour
``$skip``/``$top`` but never emit a next link.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import httpx
import respx

from odata_client.async_base_client import MAX_PAGE_SIZE_PER_REQUEST
from odata_client.sync_wrapper import SyncODataV2Client, SyncODataV4Client

V2_BASE_URL = "https://sap.example.com/sap/opu/odata/sap/Z_BILL_CDS"
V4_BASE_URL = "https://sap.example.com/sap/opu/odata4/sap/z_bill/0001"

TOTAL_RECORDS = 25
PAGE_SIZE = 10


def _make_records(n: int) -> list[dict]:
    return [{"ID": i, "Name": f"Row {i}"} for i in range(n)]


class _SapV2Mock:
    """SAP-style OData V2 service: honours $skip/$top, never returns __next."""

    def __init__(self, base_url: str, total: int, count_supported: bool = True):
        self.base_url = base_url.rstrip("/")
        self.records = _make_records(total)
        self.requested_tops: list[int] = []
        self.requested_skips: list[int] = []
        self.count_supported = count_supported

    def setup(self, respx_mock: respx.MockRouter) -> None:
        respx_mock.get(url__regex=f"{re.escape(self.base_url)}/Items/\\$count(\\?.*)?$").mock(
            side_effect=self._count,
        )
        respx_mock.get(url__regex=f"{re.escape(self.base_url)}/Items(\\?.*)?$").mock(
            side_effect=self._items,
        )

    def _items(self, request: httpx.Request) -> httpx.Response:
        qs = parse_qs(urlparse(str(request.url)).query)
        skip = int(qs.get("$skip", ["0"])[0])
        top = int(qs.get("$top", ["1000"])[0])
        self.requested_tops.append(top)
        self.requested_skips.append(skip)
        page = self.records[skip : skip + top]
        # SAP Gateway does NOT emit __next when $top is set — page is the hard cap.
        return httpx.Response(200, json={"d": {"results": page}})

    def _count(self, request: httpx.Request) -> httpx.Response:
        # SAP CDS query views reject $count with 400; model that with count_supported=False.
        if not self.count_supported:
            return httpx.Response(400, content="Bad Request")
        return httpx.Response(200, content=str(len(self.records)))


class _SapV4Mock:
    """SAP-style OData V4 service: honours $skip/$top, never returns nextLink."""

    def __init__(self, base_url: str, total: int, count_supported: bool = True):
        self.base_url = base_url.rstrip("/")
        self.records = _make_records(total)
        self.requested_skips: list[int] = []
        self.count_supported = count_supported

    def setup(self, respx_mock: respx.MockRouter) -> None:
        respx_mock.get(url__regex=f"{re.escape(self.base_url)}/Items/\\$count(\\?.*)?$").mock(
            side_effect=self._count,
        )
        respx_mock.get(url__regex=f"{re.escape(self.base_url)}/Items(\\?.*)?$").mock(
            side_effect=self._items,
        )

    def _items(self, request: httpx.Request) -> httpx.Response:
        qs = parse_qs(urlparse(str(request.url)).query)
        skip = int(qs.get("$skip", ["0"])[0])
        top = int(qs.get("$top", ["1000"])[0])
        self.requested_skips.append(skip)
        page = self.records[skip : skip + top]
        return httpx.Response(200, json={"value": page})

    def _count(self, request: httpx.Request) -> httpx.Response:
        if not self.count_supported:
            return httpx.Response(400, content="Bad Request")
        return httpx.Response(200, content=str(len(self.records)))


@respx.mock
def test_v2_sequential_full_load_fetches_all_pages(respx_mock):
    """Bug #2 (V2): without a __next link, $skip paging must still fetch everything."""
    _SapV2Mock(V2_BASE_URL, TOTAL_RECORDS).setup(respx_mock)
    client = SyncODataV2Client.from_basic_auth(username="u", password="p", base_url=V2_BASE_URL, enable_parallel=False)
    try:
        records = list(client.fetch_with_pagination("Items", page_size=PAGE_SIZE))
    finally:
        client.close()
    assert len(records) == TOTAL_RECORDS
    assert [r["ID"] for r in records] == list(range(TOTAL_RECORDS))


@respx.mock
def test_v4_sequential_full_load_fetches_all_pages(respx_mock):
    """Bug #2 (V4): without a nextLink, $skip paging must still fetch everything."""
    _SapV4Mock(V4_BASE_URL, TOTAL_RECORDS).setup(respx_mock)
    client = SyncODataV4Client.from_basic_auth(username="u", password="p", base_url=V4_BASE_URL, enable_parallel=False)
    try:
        records = list(client.fetch_with_pagination("Items", page_size=PAGE_SIZE))
    finally:
        client.close()
    assert len(records) == TOTAL_RECORDS
    assert [r["ID"] for r in records] == list(range(TOTAL_RECORDS))


@respx.mock
def test_v2_get_record_count_uses_correct_kwarg(respx_mock):
    """Bug #1 (V2): $count probe must succeed (was passing the wrong kwarg)."""
    _SapV2Mock(V2_BASE_URL, TOTAL_RECORDS).setup(respx_mock)
    client = SyncODataV2Client.from_basic_auth(username="u", password="p", base_url=V2_BASE_URL)
    try:
        count = client.get_record_count("Items")
    finally:
        client.close()
    assert count == TOTAL_RECORDS


@respx.mock
def test_v4_get_record_count_uses_correct_kwarg(respx_mock):
    """Bug #1 (V4): $count probe must succeed (was passing the wrong kwarg)."""
    _SapV4Mock(V4_BASE_URL, TOTAL_RECORDS).setup(respx_mock)
    client = SyncODataV4Client.from_basic_auth(username="u", password="p", base_url=V4_BASE_URL)
    try:
        count = client.get_record_count("Items")
    finally:
        client.close()
    assert count == TOTAL_RECORDS


@respx.mock
def test_v2_parallel_full_load_fetches_all_pages(respx_mock):
    """With a working $count, parallel fetching must also return the whole set."""
    _SapV2Mock(V2_BASE_URL, TOTAL_RECORDS).setup(respx_mock)
    client = SyncODataV2Client.from_basic_auth(
        username="u", password="p", base_url=V2_BASE_URL, enable_parallel=True, parallel_pages=3
    )
    try:
        records = list(client.fetch_with_pagination("Items", page_size=PAGE_SIZE))
    finally:
        client.close()
    assert sorted(r["ID"] for r in records) == list(range(TOTAL_RECORDS))


@respx.mock
def test_v2_max_records_caps_full_load(respx_mock):
    """max_records must still cap the sequential $skip loop."""
    _SapV2Mock(V2_BASE_URL, TOTAL_RECORDS).setup(respx_mock)
    client = SyncODataV2Client.from_basic_auth(username="u", password="p", base_url=V2_BASE_URL, enable_parallel=False)
    try:
        records = list(client.fetch_with_pagination("Items", page_size=PAGE_SIZE, max_records=12))
    finally:
        client.close()
    assert len(records) == 12


@respx.mock
def test_v2_large_page_size_is_capped_per_request(respx_mock):
    """A configured page_size above the per-request cap must be chunked into
    capped requests (bounds memory) while still fetching the whole set."""
    total = 2500
    mock = _SapV2Mock(V2_BASE_URL, total)
    mock.setup(respx_mock)
    client = SyncODataV2Client.from_basic_auth(username="u", password="p", base_url=V2_BASE_URL, enable_parallel=False)
    try:
        records = list(client.fetch_with_pagination("Items", page_size=10000))
    finally:
        client.close()
    # Everything fetched despite the oversized configured page size.
    assert len(records) == total
    assert [r["ID"] for r in records] == list(range(total))
    # No single HTTP request asked for more than the per-request cap.
    assert mock.requested_tops, "expected at least one data request"
    assert max(mock.requested_tops) == MAX_PAGE_SIZE_PER_REQUEST


@respx.mock
def test_v2_speculative_parallel_when_count_unavailable(respx_mock):
    """When $count 400s (SAP CDS query views), parallel fetching must still engage
    speculatively and return the whole set in order."""
    total = 25
    mock = _SapV2Mock(V2_BASE_URL, total, count_supported=False)
    mock.setup(respx_mock)
    client = SyncODataV2Client.from_basic_auth(
        username="u", password="p", base_url=V2_BASE_URL, enable_parallel=True, parallel_pages=3
    )
    try:
        records = list(client.fetch_with_pagination("Items", page_size=10))
    finally:
        client.close()
    assert [r["ID"] for r in records] == list(range(total))
    # It paged by $skip in batches (more than one distinct skip offset requested).
    assert len(set(mock.requested_skips)) >= 3


@respx.mock
def test_v4_speculative_parallel_when_count_unavailable(respx_mock):
    """V4 counterpart of the speculative parallel path."""
    total = 25
    mock = _SapV4Mock(V4_BASE_URL, total, count_supported=False)
    mock.setup(respx_mock)
    client = SyncODataV4Client.from_basic_auth(
        username="u", password="p", base_url=V4_BASE_URL, enable_parallel=True, parallel_pages=3
    )
    try:
        records = list(client.fetch_with_pagination("Items", page_size=10))
    finally:
        client.close()
    assert [r["ID"] for r in records] == list(range(total))


@respx.mock
def test_v2_speculative_parallel_exact_multiple_no_duplicates(respx_mock):
    """When total is an exact multiple of page_size, speculative paging must fetch
    every row exactly once (the trailing empty page just signals the end)."""
    total = 20  # exact multiple of page_size 10
    mock = _SapV2Mock(V2_BASE_URL, total, count_supported=False)
    mock.setup(respx_mock)
    client = SyncODataV2Client.from_basic_auth(
        username="u", password="p", base_url=V2_BASE_URL, enable_parallel=True, parallel_pages=3
    )
    try:
        records = list(client.fetch_with_pagination("Items", page_size=10))
    finally:
        client.close()
    ids = [r["ID"] for r in records]
    assert ids == list(range(total)), "must fetch every row exactly once, in order"
    assert len(ids) == len(set(ids)), "no duplicates"

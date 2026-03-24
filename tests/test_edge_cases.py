"""Edge-case tests for SAP OData component.

These tests target specific code paths that are not covered by the main datadir
test suite.  All tests use respx mocks so they run without a live SAP system.

Scenarios covered
-----------------
1. Filter auto-fix: date quotes stripped for OData V4 (configuration.py:83-98)
2. Empty entity_set: silent no-op, no CSV output (component.py:219-221)
3. Incremental field absent in returned records: state unchanged (component.py:379-396)
4. OData V2 /Date(ms)/ normalization persisted in state (component.py:399-413)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

# ---------------------------------------------------------------------------
# Minimal OData XML metadata templates
# ---------------------------------------------------------------------------

V4_METADATA_XML = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="TEST" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="Product">
        <Key><PropertyRef Name="ProductID"/></Key>
        <Property Name="ProductID" Type="Edm.String" Nullable="false"/>
        <Property Name="Name" Type="Edm.String"/>
        <Property Name="LastChangedAt" Type="Edm.DateTimeOffset"/>
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="Products" EntityType="TEST.Product"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""

V2_METADATA_XML = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices>
    <Schema Namespace="TEST" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityType Name="Product">
        <Key><PropertyRef Name="ProductID"/></Key>
        <Property Name="ProductID" Type="Edm.String" Nullable="false"/>
        <Property Name="Name" Type="Edm.String"/>
        <Property Name="LastChangeDate" Type="Edm.DateTime"/>
      </EntityType>
      <EntityContainer Name="TEST_Entities" m:IsDefaultEntityContainer="true">
        <EntitySet Name="Products" EntityType="TEST.Product"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


# ---------------------------------------------------------------------------
# Helper: minimal respx mock for a V4 service
# ---------------------------------------------------------------------------


def _setup_v4_mock(
    respx_mock: respx.MockRouter,
    base_url: str,
    records: list[dict[str, Any]],
) -> None:
    """Register minimal OData V4 mock routes for the given base_url."""
    base = base_url.rstrip("/")

    # $metadata
    respx_mock.get(f"{base}/$metadata").mock(
        return_value=httpx.Response(
            200,
            content=V4_METADATA_XML,
            headers={"Content-Type": "application/xml"},
        )
    )

    # Service document
    respx_mock.get(f"{base}/").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.context": f"{base}/$metadata",
                "value": [{"name": "Products", "kind": "EntitySet", "url": "Products"}],
            },
        )
    )

    # Products entity set (handles pagination + filter via side_effect)
    def _handle(request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        params = parse_qs(parsed.query)
        skip = int(params.get("$skip", ["0"])[0])
        top = int(params.get("$top", ["1000"])[0])
        data = records[skip : skip + top]
        return httpx.Response(
            200,
            json={"@odata.context": f"{base}/$metadata#Products", "value": data},
        )

    respx_mock.get(url__regex=rf"{re.escape(base)}/Products(\?.*)?$").mock(side_effect=_handle)


# ---------------------------------------------------------------------------
# Helper: minimal respx mock for a V2 service
# ---------------------------------------------------------------------------


def _setup_v2_mock(
    respx_mock: respx.MockRouter,
    base_url: str,
    records: list[dict[str, Any]],
) -> None:
    """Register minimal OData V2 mock routes for the given base_url."""
    base = base_url.rstrip("/")

    # $metadata
    respx_mock.get(f"{base}/$metadata").mock(
        return_value=httpx.Response(
            200,
            content=V2_METADATA_XML,
            headers={"Content-Type": "application/xml"},
        )
    )

    # Service document
    respx_mock.get(f"{base}/").mock(
        return_value=httpx.Response(
            200,
            content="""<?xml version="1.0" encoding="utf-8"?>
<service xmlns="http://www.w3.org/2007/app" xmlns:atom="http://www.w3.org/2005/Atom">
  <workspace>
    <atom:title>Default</atom:title>
    <collection href="Products"><atom:title>Products</atom:title></collection>
  </workspace>
</service>""",
            headers={"Content-Type": "application/xml"},
        )
    )

    # Products entity set
    def _handle(request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        params = parse_qs(parsed.query)
        skip = int(params.get("$skip", ["0"])[0])
        top = int(params.get("$top", ["1000"])[0])
        data = records[skip : skip + top]
        return httpx.Response(
            200,
            json={"d": {"results": data}},
        )

    respx_mock.get(url__regex=rf"{re.escape(base)}/Products(\?.*)?$").mock(side_effect=_handle)


# ---------------------------------------------------------------------------
# Reusable config snippets
# ---------------------------------------------------------------------------

BASE_URL_V4 = "https://edge-test.example.com/odata/v4"
BASE_URL_V2 = "https://edge-test.example.com/odata/v2"

BASIC_AUTH = {
    "auth_type": "basic",
    "username": "test_user",
    "#password": "test_pass",
}

NO_ADVANCED_OPTIONS = {
    "connection_options": [],
    "pagination_defaults": [],
}


# ===========================================================================
# Scenario 1: Filter expression auto-fix
# ===========================================================================


class TestFilterAutoFix:
    """Validate the filter_expression validator in QueryOptions (configuration.py:83-98)."""

    def test_v4_date_quotes_are_removed(self):
        """Quoted ISO dates like '2024-01-01T00:00:00Z' should have quotes stripped.

        The validator uses a regex that looks for single-quoted date strings that
        are NOT preceded by the literal text 'datetime'.  For OData V4 $filter
        expressions, dates must be passed without quotes:
            LastModified gt 2024-01-01T00:00:00Z   (correct V4)
            LastModified gt '2024-01-01T00:00:00Z' (wrong – auto-fixed)
        """
        import sys
        from pathlib import Path as PathLib

        src_path = PathLib(__file__).parent.parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        from configuration import QueryOptions

        # Date-only variant (YYYY-MM-DD)
        qo = QueryOptions(filter_expression="CreatedAt gt '2024-01-01'")
        assert qo.filter_expression == "CreatedAt gt 2024-01-01", (
            "Quotes around YYYY-MM-DD date should be removed for V4"
        )

        # Full ISO datetime with Z
        qo2 = QueryOptions(filter_expression="CreatedAt gt '2024-01-01T00:00:00Z'")
        assert qo2.filter_expression == "CreatedAt gt 2024-01-01T00:00:00Z", (
            "Quotes around ISO datetime with Z should be removed for V4"
        )

        # ISO datetime without Z
        qo3 = QueryOptions(filter_expression="CreatedAt gt '2024-06-15T12:30:00'")
        assert qo3.filter_expression == "CreatedAt gt 2024-06-15T12:30:00", (
            "Quotes around ISO datetime without Z should be removed for V4"
        )

        # Combined with other predicates (AND)
        qo4 = QueryOptions(filter_expression="Category eq 'Electronics' and LastModified gt '2024-01-01T00:00:00Z'")
        # 'Electronics' is NOT an ISO date so it must keep its quotes;
        # the date part must lose its quotes
        assert "Category eq 'Electronics'" in qo4.filter_expression, "Non-date string quotes must be preserved"
        assert "LastModified gt 2024-01-01T00:00:00Z" in qo4.filter_expression, (
            "Date quotes must still be removed in combined expression"
        )

    def test_v2_datetime_prefix_not_touched(self):
        """OData V2 datetime'...' syntax must NOT have its quotes removed.

        The validator uses a negative lookbehind (?<!datetime) to protect V2-style
        literals:  datetime'2024-01-01T00:00:00'
        """
        import sys
        from pathlib import Path as PathLib

        src_path = PathLib(__file__).parent.parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        from configuration import QueryOptions

        # Classic V2 filter expression – must be left alone
        v2_filter = "LastChangeDate gt datetime'2024-01-01T00:00:00'"
        qo = QueryOptions(filter_expression=v2_filter)
        assert qo.filter_expression == v2_filter, (
            "V2 datetime'...' syntax must not be modified by the auto-fix validator"
        )

    def test_non_date_strings_untouched(self):
        """Filter values that are not ISO dates must keep their quotes."""
        import sys
        from pathlib import Path as PathLib

        src_path = PathLib(__file__).parent.parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        from configuration import QueryOptions

        qo = QueryOptions(filter_expression="Status eq 'Active'")
        assert qo.filter_expression == "Status eq 'Active'", "Non-date string literals must keep their quotes"

        qo2 = QueryOptions(filter_expression="Code eq '1234'")
        assert qo2.filter_expression == "Code eq '1234'", "Numeric string literals must keep their quotes"


# ===========================================================================
# Scenario 2: Missing entity_set → UserException
# ===========================================================================


class TestEmptyEntitySet:
    """When entity_set is None/empty the component raises UserException.
    (configuration.py validate_for_extraction)
    """

    @respx.mock
    def test_no_entity_set_raises(
        self,
        respx_mock,
        datadir_factory,
        run_component_with_datadir,
    ):
        """Component must raise UserException when entity_set is not configured."""
        from keboola.component.exceptions import UserException

        config = {
            "connection": {"base_url": BASE_URL_V4},
            "authentication": BASIC_AUTH,
            "advanced_options": NO_ADVANCED_OPTIONS,
            "odata_version": "v4",
            # entity_set is intentionally absent
        }
        datadir = datadir_factory(config)

        with pytest.raises(UserException, match="entity_set"):
            run_component_with_datadir(datadir)

    @respx.mock
    def test_empty_string_entity_set_raises(
        self,
        respx_mock,
        datadir_factory,
        run_component_with_datadir,
    ):
        """An empty-string entity_set (converted to None) must also raise UserException."""
        from keboola.component.exceptions import UserException

        config = {
            "connection": {"base_url": BASE_URL_V4},
            "authentication": BASIC_AUTH,
            "advanced_options": NO_ADVANCED_OPTIONS,
            "odata_version": "v4",
            "entity_set": "",  # empty string converted to None by validator
        }
        datadir = datadir_factory(config)

        with pytest.raises(UserException, match="entity_set"):
            run_component_with_datadir(datadir)


# ===========================================================================
# Scenario 3: Incremental field absent in returned records → state unchanged
# ===========================================================================


class TestIncrementalFieldAbsentInRecords:
    """When the configured incremental_field is not present in any returned
    record, _track_incremental_value returns None on every call.

    Because update_entity_state only sets last_incremental_value when the new
    value is truthy, the pre-existing state value must be preserved.
    (component.py:379-396, configuration.py:452-462)
    """

    @respx.mock
    def test_state_unchanged_when_field_missing_from_records(
        self,
        respx_mock,
        datadir_factory,
        run_component_with_datadir,
        verify_state,
    ):
        """Pre-existing state.last_incremental_value must be retained when
        the incremental field is not present in any fetched record."""
        PREV_VALUE = "2020-01-01T00:00:00"

        # Records deliberately do NOT include LastChangedAt
        records_without_field = [
            {"ProductID": "P1", "Name": "Widget"},
            {"ProductID": "P2", "Name": "Gadget"},
        ]

        _setup_v4_mock(respx_mock, BASE_URL_V4, records_without_field)

        config = {
            "connection": {"base_url": BASE_URL_V4},
            "authentication": BASIC_AUTH,
            "advanced_options": NO_ADVANCED_OPTIONS,
            "odata_version": "v4",
            # No service_path – BASE_URL_V4 is the complete service URL
            "entity_set": "Products",
            "fetching_options": {
                "fetch_type": "incremental",
                "incremental_field": "LastChangedAt",
            },
            "destination": {
                "load_type": "incremental",
                "primary_key": ["ProductID"],
            },
        }

        # Pre-populate input state with a known incremental value
        in_state = {
            "entity_states": {
                "Products": {
                    "last_sync_timestamp": "2020-01-01T00:00:00",
                    "last_incremental_value": PREV_VALUE,
                    "records_synced": 10,
                }
            }
        }

        datadir = datadir_factory(config, in_state=in_state)
        run_component_with_datadir(datadir)

        # Verify output state: last_incremental_value must still be PREV_VALUE
        state = verify_state(datadir)
        entity_state = state["entity_states"]["Products"]

        # The field was missing from every record so no new max was computed.
        # update_entity_state only overwrites last_incremental_value when the
        # new value is truthy – so the original value must be preserved.
        assert entity_state["last_incremental_value"] == PREV_VALUE, (
            f"Expected last_incremental_value={PREV_VALUE!r} (unchanged), "
            f"got {entity_state['last_incremental_value']!r}"
        )

        # But records were still extracted
        csv_files = list((datadir / "out" / "tables").glob("*.csv"))
        assert len(csv_files) == 1, "CSV output should still be written even without incremental field"


# ===========================================================================
# Scenario 4: OData V2 /Date(ms)/ normalization in state
# ===========================================================================


class TestODataV2DateNormalization:
    """When a V2 server returns /Date(milliseconds)/ values, the component
    normalises them to ISO datetime strings before persisting them in state.

    /Date(1704067200000)/ → 2024-01-01T00:00:00  (UTC)

    (component.py:399-413 _normalize_odata_datetime)
    """

    @respx.mock
    def test_slash_date_ms_normalized_in_state(
        self,
        respx_mock,
        datadir_factory,
        run_component_with_datadir,
        verify_state,
    ):
        """State last_incremental_value must be an ISO string, not /Date(...)/ ."""
        # 1704067200000 ms  →  2024-01-01T00:00:00 UTC
        DATE_MS = "/Date(1704067200000)/"
        EXPECTED_ISO = "2024-01-01T00:00:00"

        records = [
            {"ProductID": "P1", "Name": "Alpha", "LastChangeDate": DATE_MS},
            {"ProductID": "P2", "Name": "Beta", "LastChangeDate": "/Date(1704153600000)/"},
        ]
        # 1704153600000 ms → 2024-01-02T00:00:00 UTC
        EXPECTED_MAX_ISO = "2024-01-02T00:00:00"

        _setup_v2_mock(respx_mock, BASE_URL_V2, records)

        config = {
            "connection": {"base_url": BASE_URL_V2},
            "authentication": BASIC_AUTH,
            "advanced_options": NO_ADVANCED_OPTIONS,
            "odata_version": "v2",
            # No service_path – BASE_URL_V2 is the complete service URL
            "entity_set": "Products",
            "fetching_options": {
                "fetch_type": "incremental",
                "incremental_field": "LastChangeDate",
            },
            "destination": {
                "load_type": "incremental",
                "primary_key": ["ProductID"],
            },
        }

        datadir = datadir_factory(config)
        run_component_with_datadir(datadir)

        state = verify_state(datadir)
        entity_state = state["entity_states"]["Products"]
        saved_value = entity_state["last_incremental_value"]

        # Must NOT be the raw /Date(...)/ format
        assert not saved_value.startswith("/Date("), f"/Date(ms)/ was not normalised – got {saved_value!r} in state"

        # Must be a recognisable ISO datetime string
        assert saved_value == EXPECTED_MAX_ISO, (
            f"Expected normalised ISO value {EXPECTED_MAX_ISO!r}, got {saved_value!r}"
        )

    def test_normalize_odata_datetime_unit(self):
        """Unit test for the static _normalize_odata_datetime helper method."""
        import sys
        from pathlib import Path as PathLib

        src_path = PathLib(__file__).parent.parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        from component import Component

        # Standard /Date(ms)/ format
        result = Component._normalize_odata_datetime("/Date(1704067200000)/")
        assert result == "2024-01-01T00:00:00", f"Expected '2024-01-01T00:00:00', got {result!r}"

        # With timezone offset (e.g., /Date(1704067200000+0000)/)
        result_tz = Component._normalize_odata_datetime("/Date(1704067200000+0000)/")
        assert result_tz == "2024-01-01T00:00:00", (
            f"Expected '2024-01-01T00:00:00' for +0000 variant, got {result_tz!r}"
        )

        # Already ISO format must be returned unchanged
        iso_value = "2024-06-15T12:30:00"
        assert Component._normalize_odata_datetime(iso_value) == iso_value, (
            "Already-ISO values must pass through unchanged"
        )

        # Plain string (non-date) must pass through unchanged
        plain = "some-string"
        assert Component._normalize_odata_datetime(plain) == plain, "Non-date strings must pass through unchanged"

"""Pytest configuration and shared fixtures for SAP OData component tests."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
import respx

from tests.fixtures.mock_odata_server_respx import (
    MockODataV2Server,
    MockODataV4Server,
    MockSAPCatalogServer,
)


@pytest.fixture
def mock_v4_server():
    """Fixture providing a mocked OData V4 server."""
    base_url = "https://api.example.com/odata/v4"
    server = MockODataV4Server(base_url)
    return server


@pytest.fixture
def mock_v2_server():
    """Fixture providing a mocked OData V2 server."""
    base_url = "https://api.example.com/sap/opu/odata/sap/API_BUSINESS_PARTNER"
    server = MockODataV2Server(base_url)
    return server


@pytest.fixture
def mock_catalog_server():
    """Fixture providing a mocked SAP catalog server."""
    base_url = "https://api.example.com/sap/opu/odata/IWFND/CATALOGSERVICE;v=2"
    server = MockSAPCatalogServer(base_url)
    return server


@pytest.fixture
def datadir_factory(tmp_path):
    """Factory fixture to create datadir test structures."""

    def _create_datadir(
        config: dict,
        in_state: dict | None = None,
        source_tables: dict[str, list[dict]] | None = None,
    ) -> Path:
        """Create a test datadir structure.

        Args:
            config: Configuration parameters
            in_state: Optional input state
            source_tables: Optional source table data (for non-extractor tests)

        Returns:
            Path to the created datadir
        """
        datadir = tmp_path / "data"

        # Create directory structure
        (datadir / "in" / "tables").mkdir(parents=True)
        (datadir / "in" / "files").mkdir(parents=True)
        (datadir / "out" / "tables").mkdir(parents=True)
        (datadir / "out" / "files").mkdir(parents=True)

        # Write config (must be nested structure matching config schemas)
        with open(datadir / "config.json", "w") as f:
            json.dump({"parameters": config}, f, indent=2)

        # Write input state if provided
        if in_state:
            with open(datadir / "in" / "state.json", "w") as f:
                json.dump(in_state, f, indent=2)

        # Write source tables if provided
        if source_tables:
            for table_name, rows in source_tables.items():
                table_path = datadir / "in" / "tables" / f"{table_name}.csv"
                if rows:
                    import csv

                    with open(table_path, "w", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                        writer.writeheader()
                        writer.writerows(rows)

        return datadir

    return _create_datadir


@pytest.fixture
def run_component_with_datadir(monkeypatch):
    """Fixture to run component with a specific datadir."""

    def _run(datadir: Path):
        """Run the component with KBC_DATADIR set."""
        # Add src to path
        import sys
        from pathlib import Path as PathLib

        src_path = PathLib(__file__).parent.parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        # Import here to avoid circular imports
        from component import Component

        # Set environment variable
        monkeypatch.setenv("KBC_DATADIR", str(datadir))

        # Create and run component
        comp = Component()
        comp.run()

        return comp

    return _run


@pytest.fixture
def run_sync_action_with_datadir(monkeypatch):
    """Fixture to run sync action with a specific datadir."""

    def _run(datadir: Path, action: str):
        """Run a sync action with KBC_DATADIR set."""
        # Add src to path
        import sys
        from pathlib import Path as PathLib

        src_path = PathLib(__file__).parent.parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        from component import Component

        # Set environment variables
        monkeypatch.setenv("KBC_DATADIR", str(datadir))
        monkeypatch.setenv("KBC_ACTION", action)

        # Create component and execute action
        comp = Component()
        comp.execute_action()

        return comp

    return _run


@pytest.fixture
def verify_output_table():
    """Fixture to verify output table structure and content."""

    def _verify(
        datadir: Path,
        table_name: str,
        min_rows: int = 1,
        expected_columns: list[str] | None = None,
    ) -> list[dict]:
        """Verify output table exists and has correct structure.

        Args:
            datadir: Path to datadir
            table_name: Name of the output table (without .csv)
            min_rows: Minimum expected number of rows
            expected_columns: Expected column names (optional)

        Returns:
            List of rows as dictionaries
        """
        import csv

        table_path = datadir / "out" / "tables" / f"{table_name}.csv"
        manifest_path = Path(str(table_path) + ".manifest")

        # Verify files exist
        assert table_path.exists(), f"Table {table_name}.csv not found"
        assert manifest_path.exists(), f"Manifest for {table_name}.csv not found"

        # Read and verify table content
        with open(table_path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) >= min_rows, f"Expected at least {min_rows} rows, got {len(rows)}"

        if expected_columns:
            actual_columns = rows[0].keys() if rows else []
            for col in expected_columns:
                assert col in actual_columns, f"Expected column '{col}' not found in output"

        return rows

    return _verify


@pytest.fixture
def verify_state():
    """Fixture to verify output state."""

    def _verify(datadir: Path) -> dict:
        """Verify and return the output state.

        Args:
            datadir: Path to datadir

        Returns:
            State dictionary
        """
        state_path = datadir / "out" / "state.json"
        assert state_path.exists(), "State file not found"

        with open(state_path) as f:
            state = json.load(f)

        return state

    return _verify


@pytest.fixture(autouse=True)
def reset_event_loop():
    """Reset event loop between tests to avoid conflicts."""
    import asyncio

    # Close any existing event loop
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.close()
    except RuntimeError:
        pass

    # Create fresh event loop
    asyncio.set_event_loop(asyncio.new_event_loop())

    yield

    # Cleanup after test
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.close()
    except RuntimeError:
        pass

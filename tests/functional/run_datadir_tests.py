"""Datadir-style functional tests runner for SAP OData component.

This implements the Keboola datadir test pattern where each test case is a directory with:
- config.json (with %env(TYPE:VAR)% placeholders)
- expected-code (expected exit code)
- source/data/in (input data - usually empty for extractors)
- expected/data/out (expected output files - optional)

Environment variables can be referenced in config using: %env(string:VAR_NAME)%
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

# Delay between tests that call the SAP sandbox API to avoid QuotaViolation (HTTP 500).
# Configurable via SAP_TEST_DELAY env var (seconds, float). Default: 2.0s.
# Set to 0 to disable (e.g. when running a single test manually).
_SAP_TEST_DELAY = float(os.environ.get("SAP_TEST_DELAY", "2.0"))


def find_test_cases(base_dir: Path) -> list[Path]:
    """Find all test case directories (those starting with 'test-')."""
    return sorted([d for d in base_dir.iterdir() if d.is_dir() and d.name.startswith("test-")])


def replace_env_placeholders(content: str) -> str:
    """Replace %env(TYPE:VAR_NAME)% placeholders with actual environment variables.

    Supported types: string, int, float, bool
    """
    pattern = r'%env\((?:string|int|float|bool):(\w+)\)%'

    def replace(match):
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            pytest.skip(f"Environment variable {var_name} not set")
        return value

    return re.sub(pattern, replace, content)


def prepare_test_datadir(test_case: Path, tmp_path: Path) -> Path:
    """Prepare test data directory by copying source and processing config.

    Returns path to the temporary data directory.
    """
    # Create temporary data dir
    temp_datadir = tmp_path / "data"

    # Copy source/data to temp location
    source_data = test_case / "source" / "data"
    if source_data.exists():
        shutil.copytree(source_data, temp_datadir)
    else:
        temp_datadir.mkdir()
        (temp_datadir / "in" / "tables").mkdir(parents=True)
        (temp_datadir / "in" / "files").mkdir(parents=True)

    # Create out directories
    (temp_datadir / "out" / "tables").mkdir(parents=True)
    (temp_datadir / "out" / "files").mkdir(parents=True)

    # Process config.json with environment variable replacement
    config_file = test_case / "config.json"
    if config_file.exists():
        with open(config_file) as f:
            config_content = f.read()

        # Replace environment variables
        config_content = replace_env_placeholders(config_content)

        # Write processed config
        with open(temp_datadir / "config.json", "w") as f:
            f.write(config_content)

    return temp_datadir


def run_component(datadir: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run the component with KBC_DATADIR set to the test directory."""
    env = os.environ.copy()
    env["KBC_DATADIR"] = str(datadir)

    result = subprocess.run(
        ["python3", "src/component.py"],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=Path.cwd(),
    )

    return result


def get_expected_exit_code(test_case: Path) -> int:
    """Read expected exit code from expected-code file."""
    expected_code_file = test_case / "expected-code"
    if expected_code_file.exists():
        return int(expected_code_file.read_text().strip())
    return 0  # Default to success


def verify_output_exists(datadir: Path, test_case: Path) -> None:
    """Verify that output files were created."""
    import json

    # Check if this is a sync action test (doesn't produce CSV output)
    config_file = test_case / "config.json"
    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
            # Sync actions don't produce CSV output
            if "action" in config:
                return

    out_tables = datadir / "out" / "tables"

    # Check if any CSV files were created
    csv_files = list(out_tables.glob("*.csv"))
    assert len(csv_files) > 0, f"No output CSV files created in {out_tables}"

    # Check that each CSV has a manifest
    for csv_file in csv_files:
        manifest_file = Path(str(csv_file) + ".manifest")
        assert manifest_file.exists(), f"Manifest not created for {csv_file.name}"


class TestDatadirFunctional:
    """Datadir-style functional tests."""

    @pytest.fixture
    def functional_tests_dir(self) -> Path:
        """Get the functional tests directory."""
        return Path(__file__).parent

    @pytest.mark.parametrize("test_case", find_test_cases(Path(__file__).parent))
    def test_datadir_case(self, test_case: Path, tmp_path: Path) -> None:
        """Run a single datadir test case."""
        # Skip SCI tests unless SCI_ENABLED is set
        if test_case.name.startswith("test-sci-") and not os.environ.get("SCI_ENABLED"):
            pytest.skip("SCI tests skipped — set SCI_ENABLED=1 to run")

        # Throttle tests that call the SAP sandbox API to avoid QuotaViolation.
        # Only applies when SAP_API_KEY is set and this test actually uses it.
        config_file = test_case / "config.json"
        if _SAP_TEST_DELAY > 0 and os.environ.get("SAP_API_KEY") and config_file.exists():
            if "SAP_API_KEY" in config_file.read_text():
                time.sleep(_SAP_TEST_DELAY)

        # Prepare test data directory (will skip automatically if required env vars are missing)
        datadir = prepare_test_datadir(test_case, tmp_path)

        # Get expected exit code
        expected_code = get_expected_exit_code(test_case)

        # Run component
        result = run_component(datadir)

        # Verify exit code
        assert result.returncode == expected_code, (
            f"Test case {test_case.name} failed.\n"
            f"Expected exit code: {expected_code}\n"
            f"Actual exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

        # If successful, verify output files were created
        if expected_code == 0:
            verify_output_exists(datadir, test_case)

            # Compare stdout for sync actions
            expected_stdout = test_case / "expected" / "data" / "stdout.txt"
            if expected_stdout.exists():
                import json as _json
                actual_stdout = result.stdout.strip()
                expected_stdout_content = expected_stdout.read_text(encoding="utf-8").strip()
                # Try JSON semantic comparison first (handles unicode escaping differences)
                try:
                    actual_json = _json.loads(actual_stdout)
                    expected_json = _json.loads(expected_stdout_content)
                    stdout_match = actual_json == expected_json
                except (_json.JSONDecodeError, ValueError):
                    stdout_match = actual_stdout == expected_stdout_content
                assert stdout_match, (
                    f"Stdout mismatch for {test_case.name}\n"
                    f"Expected:\n{expected_stdout_content}\n"
                    f"Actual:\n{actual_stdout}"
                )

            # Optional: Compare with expected output if it exists
            expected_out = test_case / "expected" / "data" / "out" / "tables"
            if expected_out.exists() and any(expected_out.iterdir()):
                # Could add CSV content comparison here if needed
                pass

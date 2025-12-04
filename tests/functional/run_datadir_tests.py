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
from pathlib import Path

import pytest


def find_test_cases(base_dir: Path) -> list[Path]:
    """Find all test case directories (those starting with 'test-')."""
    return [d for d in base_dir.iterdir() if d.is_dir() and d.name.startswith("test-")]


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


def verify_output_exists(datadir: Path, _test_case: Path) -> None:
    """Verify that output files were created."""
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
        # Check if SAP_API_KEY is available
        if not os.environ.get("SAP_API_KEY"):
            pytest.skip("SAP_API_KEY environment variable not set")

        # Prepare test data directory
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

            # Optional: Compare with expected output if it exists
            expected_out = test_case / "expected" / "data" / "out" / "tables"
            if expected_out.exists() and any(expected_out.iterdir()):
                # Could add CSV content comparison here if needed
                pass

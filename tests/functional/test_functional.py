"""Functional tests for SAP OData component using datadir pattern.

These tests run the component with real SAP API endpoints (sandbox).
Credentials are provided via environment variables.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


class TestFunctional:
    """Functional tests using datadir pattern."""

    @pytest.fixture
    def temp_datadir(self, tmp_path: Path) -> Path:
        """Create temporary data directory."""
        datadir = tmp_path / "data"
        datadir.mkdir()
        (datadir / "in" / "tables").mkdir(parents=True)
        (datadir / "in" / "files").mkdir(parents=True)
        (datadir / "out" / "tables").mkdir(parents=True)
        (datadir / "out" / "files").mkdir(parents=True)
        return datadir

    def run_component(self, datadir: Path) -> subprocess.CompletedProcess:
        """Run the component with KBC_DATADIR set to test directory."""
        env = os.environ.copy()
        env["KBC_DATADIR"] = str(datadir)

        result = subprocess.run(
            ["python3", "src/component.py"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result

    def load_config_template(self, template_path: Path) -> dict:
        """Load config template and replace environment variable placeholders.

        Supports placeholders like %env(string:API_KEY)% in JSON.
        """
        with open(template_path) as f:
            content = f.read()

        # Replace environment variable placeholders
        import re
        pattern = r'%env\((?:string|int|float|bool):(\w+)\)%'

        def replace_env(match):
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                pytest.skip(f"Environment variable {var_name} not set")
            return value

        content = re.sub(pattern, replace_env, content)
        return json.loads(content)

    @pytest.mark.skipif(
        not os.environ.get("SAP_API_KEY"),
        reason="SAP_API_KEY environment variable not set"
    )
    def test_v4_api_key_extraction(self, temp_datadir: Path) -> None:
        """Test OData V4 extraction with API Key authentication (SAP API Business Hub)."""
        # Load config template
        config = {
            "parameters": {
                "base_url": "https://sandbox.api.sap.com/s4hanacloud",
                "service_path": "api_fixedassetacquisition/srvd_a2x/sap/fixedassetacquisition/0001",
                "odata_version": "v4",
                "auth_type": "apiKey",
                "#api_key": os.environ.get("SAP_API_KEY"),
                "api_key_header_name": "APIKey",
                "entity_set": "FixedAssetAcquisition",
                "select_fields": ["FixedAssetPostingUUID", "CompanyCode", "MasterFixedAsset"],
                "filter_expression": "CompanyCode eq '1010'",
                "page_size": 10,
                "max_records": 10,
            }
        }

        # Write config
        config_file = temp_datadir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        # Run component
        result = self.run_component(temp_datadir)

        # Assert success
        assert result.returncode == 0, f"Component failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

        # Check output file exists
        output_file = temp_datadir / "out" / "tables" / "FixedAssetAcquisition.csv"
        assert output_file.exists(), f"Output file not created. Files: {list((temp_datadir / 'out' / 'tables').iterdir())}"

        # Check manifest exists
        manifest_file = temp_datadir / "out" / "tables" / "FixedAssetAcquisition.csv.manifest"
        assert manifest_file.exists(), "Manifest file not created"

        # Verify data was extracted
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) > 1, "No data extracted (only header)"
            assert len(lines) <= 11, f"Too many records extracted: {len(lines)-1} (expected max 10)"

        # Verify manifest structure
        with open(manifest_file) as f:
            manifest = json.load(f)
            assert "columns" in manifest
            assert "FixedAssetPostingUUID" in manifest["columns"]

    @pytest.mark.skipif(
        not os.environ.get("SAP_API_KEY"),
        reason="SAP_API_KEY environment variable not set"
    )
    def test_v2_company_code_extraction(self, temp_datadir: Path) -> None:
        """Test OData V2 extraction (SAP API Business Hub)."""
        config = {
            "parameters": {
                "service_url": "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_COMPANYCODE_SRV",
                "odata_version": "v2",
                "auth_type": "apiKey",
                "#api_key": os.environ.get("SAP_API_KEY"),
                "api_key_header_name": "APIKey",
                "entity_set": "A_CompanyCode",
                "select_fields": ["CompanyCode", "CompanyCodeName"],
                "page_size": 10,
                "max_records": 10,
            }
        }

        # Write config
        config_file = temp_datadir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        # Run component
        result = self.run_component(temp_datadir)

        # Assert success
        assert result.returncode == 0, f"Component failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

        # Check output file exists
        output_file = temp_datadir / "out" / "tables" / "A_CompanyCode.csv"
        assert output_file.exists(), "Output file not created"

        # Verify data
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) > 1, "No data extracted"

    def test_invalid_credentials_fails(self, temp_datadir: Path) -> None:
        """Test that invalid credentials produce proper error."""
        config = {
            "parameters": {
                "service_url": "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_COMPANYCODE_SRV",
                "odata_version": "v2",
                "auth_type": "apiKey",
                "#api_key": "invalid-api-key-123",
                "api_key_header_name": "APIKey",
                "entity_set": "A_CompanyCode",
                "page_size": 10,
                "max_records": 10,
            }
        }

        # Write config
        config_file = temp_datadir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        # Run component
        result = self.run_component(temp_datadir)

        # Should fail with 401 error
        assert result.returncode != 0, "Component should fail with invalid credentials"
        assert "401" in result.stderr or "Unauthorized" in result.stderr, "Should contain authentication error"

    def test_split_url_configuration(self, temp_datadir: Path) -> None:
        """Test that split URL configuration (base_url + service_path) works correctly."""
        if not os.environ.get("SAP_API_KEY"):
            pytest.skip("SAP_API_KEY not set")

        config = {
            "parameters": {
                "base_url": "https://sandbox.api.sap.com/s4hanacloud",
                "service_path": "API_COMPANYCODE_SRV",
                "odata_version": "v2",
                "auth_type": "apiKey",
                "#api_key": os.environ.get("SAP_API_KEY"),
                "api_key_header_name": "APIKey",
                "entity_set": "A_CompanyCode",
                "page_size": 5,
                "max_records": 5,
            }
        }

        # Write config
        config_file = temp_datadir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        # Run component
        result = self.run_component(temp_datadir)

        # Assert success
        assert result.returncode == 0, f"Component failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

        # Check output exists
        output_file = temp_datadir / "out" / "tables" / "A_CompanyCode.csv"
        assert output_file.exists(), "Output file not created"

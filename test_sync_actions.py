#!/usr/bin/env python3
"""Test script to verify all sync actions work correctly."""

import sys
import os
import json
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

# Set up environment
os.environ['KBC_DATADIR'] = './data'
os.environ['SAP_API_KEY'] = '__SAP_API_KEY__'

# Import component
from component import Component

def write_config(params):
    """Write config for testing."""
    config = {"parameters": params}
    with open('./data/config.json', 'w') as f:
        json.dump(config, f, indent=2)

def test_sync_action(name, params, method):
    """Test a sync action."""
    print(f"\n{'='*80}")
    print(f"Testing: {name}")
    print(f"{'='*80}")

    try:
        write_config(params)
        comp = Component()
        result = method(comp)

        print(f"✅ Status: SUCCESS")
        print(f"📊 Result type: {type(result)}")

        if isinstance(result, dict):
            print(f"📝 Keys: {list(result.keys())}")
            if 'status' in result:
                print(f"   Status: {result.get('status')}")
            if 'message' in result:
                msg = result.get('message', '')
                if len(msg) > 100:
                    print(f"   Message: {msg[:100]}...")
                else:
                    print(f"   Message: {msg}")
            if 'data' in result:
                data = result.get('data')
                if isinstance(data, list):
                    print(f"   Data items: {len(data)}")
                else:
                    print(f"   Data: {str(data)[:100]}...")
        elif isinstance(result, list):
            print(f"📝 List items: {len(result)}")
            if result:
                print(f"   First item: {result[0]}")
        else:
            print(f"📝 Result: {str(result)[:200]}")

        return True
    except Exception as e:
        print(f"❌ Status: FAILED")
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

# Base config
base_config = {
    "base_url": "https://sandbox.api.sap.com/s4hanacloud",
    "auth_type": "apiKey",
    "#api_key": "__SAP_API_KEY__",
    "api_key_header_name": "APIKey",
    "service_path": "api_fixedassetacquisition/srvd_a2x/sap/fixedassetacquisition/0001",
    "odata_version": "auto",
}

# Test configuration
tests = [
    {
        "name": "testConnection",
        "params": base_config,
        "method": lambda c: c.test_connection()
    },
    {
        "name": "loadEntities",
        "params": base_config,
        "method": lambda c: c.load_entities()
    },
    {
        "name": "loadFields",
        "params": {**base_config, "entity_set": "FixedAssetAcquisition"},
        "method": lambda c: c.load_fields()
    },
    {
        "name": "loadPossiblePrimaryKeys",
        "params": {**base_config, "entity_set": "FixedAssetAcquisition"},
        "method": lambda c: c.load_possible_primary_keys()
    },
    {
        "name": "loadIncrementalFields",
        "params": {**base_config, "entity_set": "FixedAssetAcquisition"},
        "method": lambda c: c.load_incremental_fields()
    },
    {
        "name": "loadNavigationProperties",
        "params": {**base_config, "entity_set": "FixedAssetAcquisition"},
        "method": lambda c: c.load_navigation_properties()
    },
    {
        "name": "previewData",
        "params": {
            **base_config,
            "entity_set": "FixedAssetAcquisition",
            "fetching_options": {"fetch_type": "full"},
            "query_options": {
                "select_fields": [],
                "filter_expression": "",
                "expand_properties": [],
                "order_by": ""
            },
            "destination": {"load_type": "full", "output_table_name": ""},
            "pagination_defaults": [],
            "connection_options": [],
            "advanced_options": []
        },
        "method": lambda c: c.preview_data()
    },
    {
        "name": "validateFilter",
        "params": {
            **base_config,
            "entity_set": "FixedAssetAcquisition",
            "query_options": {
                "filter_expression": "CompanyCode eq '1710'"
            }
        },
        "method": lambda c: c.validate_filter()
    },
    {
        "name": "loadMetadataSummary",
        "params": base_config,
        "method": lambda c: c.load_metadata_summary()
    },
]

# Run tests
print("\n" + "="*80)
print("SAP OData Extractor - Sync Actions Test Suite")
print("="*80)

results = []
for test in tests:
    success = test_sync_action(test["name"], test["params"], test["method"])
    results.append((test["name"], success))

# Summary
print("\n" + "="*80)
print("Test Summary")
print("="*80)

passed = sum(1 for _, success in results if success)
failed = len(results) - passed

for name, success in results:
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} - {name}")

print(f"\n{'='*80}")
print(f"Total: {len(results)} tests | Passed: {passed} | Failed: {failed}")
print(f"{'='*80}\n")

sys.exit(0 if failed == 0 else 1)

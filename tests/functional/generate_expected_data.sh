#!/bin/bash
set -e

# Script to generate expected data for functional tests
# Usage: SAP_API_KEY="your-key" ./generate_expected_data.sh [test-case-name]

if [ -z "$SAP_API_KEY" ]; then
    echo "Error: SAP_API_KEY environment variable is not set"
    echo "Usage: SAP_API_KEY=\"your-key\" $0 [test-case-name]"
    exit 1
fi

# Get test case from argument or run all
TEST_CASE="${1:-}"
FUNCTIONAL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$FUNCTIONAL_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

if [ -n "$TEST_CASE" ]; then
    TEST_CASES=("$FUNCTIONAL_DIR/$TEST_CASE")
else
    TEST_CASES=("$FUNCTIONAL_DIR"/test-*)
fi

for test_dir in "${TEST_CASES[@]}"; do
    if [ ! -d "$test_dir" ]; then
        echo "Test case not found: $test_dir"
        continue
    fi

    test_name=$(basename "$test_dir")
    echo "================================================"
    echo "Generating expected data for: $test_name"
    echo "================================================"

    # Create temporary data directory
    temp_dir=$(mktemp -d)
    trap "rm -rf $temp_dir" EXIT

    # Copy source data structure
    if [ -d "$test_dir/source/data" ]; then
        cp -r "$test_dir/source/data" "$temp_dir/"
    else
        mkdir -p "$temp_dir/data/in/tables"
        mkdir -p "$temp_dir/data/in/files"
    fi

    mkdir -p "$temp_dir/data/out/tables"
    mkdir -p "$temp_dir/data/out/files"

    # Process config.json with environment variable replacement
    if [ -f "$test_dir/config.json" ]; then
        # Replace %env(string:SAP_API_KEY)% with actual value
        sed "s|%env(string:SAP_API_KEY)%|$SAP_API_KEY|g" "$test_dir/config.json" > "$temp_dir/data/config.json"
    else
        echo "Error: config.json not found in $test_dir"
        continue
    fi

    echo "Running component..."
    # Run component
    if KBC_DATADIR="$temp_dir/data" python3 src/component.py; then
        echo "✓ Component succeeded"

        # Copy output to expected directory
        expected_dir="$test_dir/expected/data/out"
        mkdir -p "$expected_dir/tables"
        mkdir -p "$expected_dir/files"

        # Copy CSV files (without manifests for now)
        if [ -d "$temp_dir/data/out/tables" ]; then
            echo "Copying output files..."
            cp "$temp_dir/data/out/tables"/*.csv "$expected_dir/tables/" 2>/dev/null || echo "No CSV files to copy"
            ls -lh "$expected_dir/tables/"
        fi

        echo "✓ Expected data saved to: $expected_dir"
    else
        echo "✗ Component failed with exit code $?"
        echo "Check the error above"
    fi

    echo ""
done

echo "Done! Review the expected data in tests/functional/test-*/expected/data/out/"
echo ""
echo "To run tests:"
echo "  SAP_API_KEY=\"your-key\" PYTHONPATH=src uv run pytest tests/functional/run_datadir_tests.py -v"

#!/bin/bash
set -e

if [ -z "$SAP_API_KEY" ]; then
    echo "Error: SAP_API_KEY environment variable is not set"
    exit 1
fi

FUNCTIONAL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$FUNCTIONAL_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

# Process only sync action tests
for test_dir in "$FUNCTIONAL_DIR"/test-sync-*/; do
    if [ ! -d "$test_dir" ]; then
        continue
    fi

    test_name=$(basename "$test_dir")
    echo "================================================"
    echo "Generating expected output for: $test_name"
    echo "================================================"

    # Create temporary data directory
    temp_dir=$(mktemp -d)
    trap "rm -rf $temp_dir" EXIT

    mkdir -p "$temp_dir/in/tables"
    mkdir -p "$temp_dir/in/files"
    mkdir -p "$temp_dir/out/tables"
    mkdir -p "$temp_dir/out/files"

    # Process config.json with environment variable replacement
    if [ -f "$test_dir/config.json" ]; then
        sed "s|%env(string:SAP_API_KEY)%|$SAP_API_KEY|g" "$test_dir/config.json" > "$temp_dir/config.json"
    else
        echo "Error: config.json not found in $test_dir"
        continue
    fi

    echo "Running component..."
    # Run component and capture stdout
    if output=$(KBC_DATADIR="$temp_dir" python3 src/component.py 2>&1); then
        echo "✓ Component succeeded"
        
        # Save stdout to expected directory
        expected_dir="$test_dir/expected/data"
        mkdir -p "$expected_dir"
        
        echo "$output" > "$expected_dir/stdout.txt"
        echo "✓ Expected output saved to: $expected_dir/stdout.txt"
        
        # Show the output
        echo "Output:"
        echo "$output"
    else
        exit_code=$?
        echo "✗ Component failed with exit code $exit_code"
        echo "Output:"
        echo "$output"
    fi

    echo ""
done

echo "Done! Expected outputs saved to tests/functional/test-sync-*/expected/data/stdout.txt"

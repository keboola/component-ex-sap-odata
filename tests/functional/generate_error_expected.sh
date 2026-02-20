#!/bin/bash
set -e

FUNCTIONAL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$FUNCTIONAL_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

# Process error tests
for test_dir in "$FUNCTIONAL_DIR"/test-error-*/; do
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

    # Process config.json with environment variable replacement if needed
    if [ -f "$test_dir/config.json" ]; then
        if grep -q "%env(string:SAP_API_KEY)%" "$test_dir/config.json"; then
            if [ -z "$SAP_API_KEY" ]; then
                echo "⚠️  Skipping (SAP_API_KEY not set)"
                echo ""
                continue
            fi
            sed "s|%env(string:SAP_API_KEY)%|$SAP_API_KEY|g" "$test_dir/config.json" > "$temp_dir/config.json"
        else
            cp "$test_dir/config.json" "$temp_dir/config.json"
        fi
    else
        echo "Error: config.json not found in $test_dir"
        continue
    fi

    echo "Running component..."
    # Run component and capture stdout (errors are expected!)
    if output=$(KBC_DATADIR="$temp_dir" python3 src/component.py 2>&1); then
        echo "✓ Component succeeded"
    else
        echo "✓ Component returned error (expected for error tests)"
    fi

    # Save stdout to expected directory
    expected_dir="$test_dir/expected/data"
    mkdir -p "$expected_dir"

    echo "$output" > "$expected_dir/stdout.txt"
    echo "✓ Expected output saved to: $expected_dir/stdout.txt"

    # Show first line of output
    first_line=$(echo "$output" | head -n 1)
    echo "Output: $first_line"

    echo ""
done

echo "Done! Expected outputs saved to tests/functional/test-error-*/expected/data/stdout.txt"

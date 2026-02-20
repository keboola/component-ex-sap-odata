#!/bin/bash
set -e

FUNCTIONAL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$FUNCTIONAL_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

# Process only SCI sync action tests
for test_dir in "$FUNCTIONAL_DIR"/test-sci-*/; do
    if [ ! -d "$test_dir" ]; then
        continue
    fi

    # Skip extraction test (not a sync action)
    test_name=$(basename "$test_dir")
    if [[ "$test_name" == "test-sci-extraction" ]]; then
        continue
    fi

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

    # Copy config.json as-is (no environment variable replacement needed)
    if [ -f "$test_dir/config.json" ]; then
        cp "$test_dir/config.json" "$temp_dir/config.json"
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

        # Show first line of output
        first_line=$(echo "$output" | head -n 1)
        echo "First line: $first_line"
    else
        exit_code=$?
        echo "✗ Component failed with exit code $exit_code"
        echo "Output:"
        echo "$output"
    fi

    echo ""
done

echo "Done! Expected outputs saved to tests/functional/test-sci-*/expected/data/stdout.txt"

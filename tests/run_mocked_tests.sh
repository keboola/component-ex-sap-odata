#!/bin/bash
# Run mocked integration tests without requiring external SAP systems

set -e

echo "============================================"
echo "Running Mocked SAP OData Component Tests"
echo "============================================"
echo ""

# Check if running from correct directory
if [ ! -f "src/component.py" ]; then
    echo "Error: Must run from project root directory"
    exit 1
fi

# Install test dependencies if not present
echo "Checking test dependencies..."
pip install -q responses pytest pytest-cov 2>/dev/null || true

echo ""
echo "Running mocked integration tests..."
echo "--------------------------------------------"
pytest tests/test_datadir_mocked.py -v --tb=short

echo ""
echo "============================================"
echo "Test run completed successfully!"
echo "============================================"
echo ""
echo "To run with coverage report:"
echo "  pytest tests/test_datadir_mocked.py --cov=src --cov-report=html"
echo "  open htmlcov/index.html"
echo ""

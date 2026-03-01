#!/usr/bin/env bash
# Run the full Task2 test suite and persist output to a timestamped log file.
#
# Usage:
#   cd Task2
#   bash run_tests.sh
#
# Output:
#   tests/test-results.log  — pytest runtime log (overwritten each run by pytest.ini)
#   tests/run-<timestamp>.log — full console output including pytest summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
CONSOLE_LOG="tests/run-${TIMESTAMP}.log"

echo "=========================================="
echo "  Task2 — Kubernetes manifest & Locust tests"
echo "  $(date)"
echo "=========================================="

# Install dependencies if not present
if ! python -c "import pytest" 2>/dev/null; then
    echo "[INFO] Installing test dependencies..."
    pip install -r requirements-test.txt
fi

echo "[INFO] Running pytest..."
echo ""

# Run pytest; tee output to the timestamped log file.
# pytest.ini already writes tests/test-results.log via log_file.
python -m pytest \
    --cov=. \
    --cov-report=term-missing \
    --cov-report="html:tests/htmlcov" \
    2>&1 | tee "$CONSOLE_LOG"

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "=========================================="
echo "  Console log : $CONSOLE_LOG"
echo "  Runtime log : tests/test-results.log"
echo "  HTML report : tests/htmlcov/index.html"
echo "  Exit code   : $EXIT_CODE"
echo "=========================================="

exit $EXIT_CODE

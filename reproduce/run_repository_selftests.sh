#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" tools/run_public_selftests.py .
"$PYTHON_BIN" tools/audit_public_repo.py .
echo PASS_REPOSITORY_SELFTEST_WRAPPER_V001

#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:?Usage: $0 /path/to/malonaldehyde_mtp_al}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" scripts/tables/build_supplementary_table_s1_complete_numerical_audit_v023.py --root "$ROOT"

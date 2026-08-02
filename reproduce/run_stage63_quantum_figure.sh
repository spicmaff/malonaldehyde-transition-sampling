#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:?Usage: $0 /path/to/malonaldehyde_mtp_al}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" scripts/quantum/render_stage63_supplementary_figure_s3_quantum_audit_v005.py --root "$ROOT"

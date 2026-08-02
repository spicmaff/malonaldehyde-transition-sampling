#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:?Usage: $0 /path/to/malonaldehyde_mtp_al}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" scripts/quantum/stage62_frozen_path_1d_tunneling_audit_v003.py --root "$ROOT"

#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:?Usage: run_stage62_quantum_audit.sh /path/to/project-root}"
python3 scripts/stage62_frozen_path_1d_tunneling_audit_v003.py --root "$ROOT"

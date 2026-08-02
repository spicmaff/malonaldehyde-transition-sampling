#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:?Usage: run_stage63_quantum_figure.sh /path/to/project-root}"
python3 scripts/render_stage63_supplementary_figure_s3_quantum_audit_v005.py --root "$ROOT"

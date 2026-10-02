#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${1:-$REPO_ROOT}"
SOURCE_ROOT="${2:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SOURCE_ARGS=()
if [[ -n "$SOURCE_ROOT" ]]; then SOURCE_ARGS=(--source-root "$SOURCE_ROOT"); fi
for script in \
  scripts/figures/render_figure01_equal_budget_design_focus_v019.py \
  scripts/figures/render_figure02_primary_frozen_audit_spacious_v009.py \
  scripts/figures/render_figure03_deployment_applicability_text_clear_v013.py \
  scripts/figures/render_figure04_secondary_mtp_neb_v014.py \
  scripts/figures/render_supplementary_figure_s1_selection_interface_consistency_v020.py \
  scripts/figures/render_supplementary_figure_s2_applicability_grades_spacious_v022.py; do
  "$PYTHON_BIN" "$script" --root "$ROOT" "${SOURCE_ARGS[@]}"
done
"$PYTHON_BIN" scripts/quantum/stage62_frozen_path_1d_tunneling_audit_v003.py --root "$ROOT" "${SOURCE_ARGS[@]}"
"$PYTHON_BIN" scripts/quantum/render_stage63_supplementary_figure_s3_quantum_audit_v005.py --root "$ROOT"
echo PASS_RENDER_ALL_FINAL_FIGURES

#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${1:-$REPO_ROOT}"
SOURCE_ROOT="${2:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SOURCE_ARGS=()
if [[ -n "$SOURCE_ROOT" ]]; then SOURCE_ARGS=(--source-root "$SOURCE_ROOT"); fi
for script in \
  scripts/videos/render_video01_relaxed_path_clean_v030.py \
  scripts/videos/render_video02_proton_transfer_pbe_mep_clean_v034.py \
  scripts/videos/render_supplementary_video_s1_first_update_rejection_v031.py; do
  "$PYTHON_BIN" "$script" --root "$ROOT" "${SOURCE_ARGS[@]}"
done
echo PASS_RENDER_ALL_FINAL_VIDEOS

#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:?Usage: $0 /path/to/malonaldehyde_mtp_al}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
for script in   scripts/videos/render_video01_relaxed_path_clean_v030.py   scripts/videos/render_video02_proton_transfer_pbe_mep_clean_v034.py   scripts/videos/render_supplementary_video_s1_first_update_rejection_v031.py; do
  "$PYTHON_BIN" "$script" --root "$ROOT"
done
echo PASS_RENDER_ALL_FINAL_VIDEOS

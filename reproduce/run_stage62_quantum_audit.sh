#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${1:-$REPO_ROOT}"
SOURCE_ROOT="${2:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SOURCE_ARGS=()
if [[ -n "$SOURCE_ROOT" ]]; then SOURCE_ARGS=(--source-root "$SOURCE_ROOT"); fi
"$PYTHON_BIN" scripts/quantum/stage62_frozen_path_1d_tunneling_audit_v003.py --root "$ROOT" "${SOURCE_ARGS[@]}"

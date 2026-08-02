#!/usr/bin/env bash
set -euo pipefail
OWNER="${1:-}"
REPO="${2:-malonaldehyde-transition-sampling}"
ACK="${3:-}"

if [[ -z "$OWNER" ]]; then
  echo "Usage: $0 OWNER [REPOSITORY] I_UNDERSTAND_THIS_WILL_BE_PUBLIC" >&2
  exit 2
fi
if [[ "$ACK" != "I_UNDERSTAND_THIS_WILL_BE_PUBLIC" ]]; then
  echo "Refusing public push without exact acknowledgement." >&2
  exit 3
fi
command -v git >/dev/null
command -v gh >/dev/null
gh auth status
python3 tools/audit_public_repo.py .
if [[ -n "$(git status --porcelain)" ]]; then
  git add .
  python3 tools/audit_public_repo.py .
  git commit -m "Initial public release"
fi
if git remote get-url origin >/dev/null 2>&1; then
  echo "Remote origin already exists; refusing to replace it." >&2
  exit 4
fi
gh repo create "$OWNER/$REPO" --public --source=. --remote=origin --push
echo "PUBLIC_REPOSITORY=https://github.com/$OWNER/$REPO"

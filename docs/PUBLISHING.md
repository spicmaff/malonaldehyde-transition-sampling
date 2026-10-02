# Publishing a release

Before publishing:

    python3 tools/run_public_selftests.py .
    python3 tools/audit_public_repo.py .
    git status --short
    git diff --cached

Confirm that the release tag matches CITATION.cff, CI is green, public manifests have been regenerated, and no private paths or credentials are tracked.

Create releases with a semantic version matching the repository state. Do not reuse or move an existing release tag.

Large release assets are optional when the same media are already tracked in Git. Release notes should state the scientific wording changes separately from numerical-result changes.

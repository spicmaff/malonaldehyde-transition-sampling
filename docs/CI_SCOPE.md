# Continuous-integration scope

GitHub Actions performs repository-integrity and public-release checks.

`tools/run_public_selftests.py` verifies Python compilation, the 12-entry core
manifest, the exhaustive script index, dependency declarations, required docs,
and absence of deprecated duplicate quantum-script locations.

`tools/audit_public_repo.py` checks private machine paths, common secret/token
patterns, oversized Git files, and required public metadata.

CI deliberately does not run DFT, MTP training, relaxed NEB, or video rendering.
Green CI certifies repository integrity and release hygiene, not end-to-end
scientific recomputation.

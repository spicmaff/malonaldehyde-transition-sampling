# CI scope

CI is intentionally narrower than full scientific recomputation.

It checks:
- Python compilation;
- core and complete script manifests;
- every row of PUBLIC_ASSET_MANIFEST.tsv;
- compact publication-source and frozen-model manifests;
- absence of private machine paths and common credential patterns;
- exact numerical recomputation of the original v030r primary metrics from included CFG payloads;
- expected endpoint-overlap count;
- renderer and quantum input validation in the reproduction smoke job.

CI does not run Quantum ESPRESSO, MTP training, LAMMPS, NEB or reactive molecular dynamics.

A green CI status therefore means that the published compact package is internally consistent and its supported lightweight reproductions pass. It is not an end-to-end reproduction of the heavy calculation.

## Reproduction smoke

The `reproduction-smoke` job installs the declared Python dependencies, validates figure/table/video/quantum inputs, then performs actual figure, supplementary-table, and frozen-path quantum rendering in a temporary clean-checkout output root. It does not run QE, MLIP training, LAMMPS dynamics, or DFT. Video inputs are validated in CI; full video encoding additionally requires ffmpeg and is documented as a separate clean-copy verification boundary.

## Ledger semantic regression

The integrity selftest also runs `tools/check_ledger_semantics.py`. It reads the accepted V005 ledger and source-verdict excerpts, preserves scientific-negative and superseded cases, and rejects twenty deliberate ledger mutations. Hash consistency alone is not treated as semantic correctness.

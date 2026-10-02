# Pipeline and authority order

Historical script filenames are preserved because they are part of the provenance record. Names containing independent refer to the independently computed PBE path, not to a claim that every evaluation geometry is training-independent.

## Original public pipeline

1. v024 / step26: compute the nine-image PBE NEB path.
2. v025 / step27: PBE single points on NEB9.
3. v026 / step28: construct branch-specific equal-budget additions. The transition pool has 24 candidates and K = 24.
4. v027 / step29: DFT labels for the 48 branch-specific configurations.
5. v028 / step30: train the two 60-configuration L12 MTPs.
6. v029 / step31: evaluate frozen Audit21.
7. v030: superseded primary-metric implementation.
8. v030r / step32b: authoritative repaired primary metrics.
9. v031: secondary relaxed MTP-NEB.
10. v032 plus v032d/v032k: first-update applicability and exact source-oracle diagnostics.
11. v033: historical closeout.

The v030r repair changes metric definitions only; it does not retrain models.

## Holdout correction

Audit21 is not a completely independent holdout. audit_neb_01 and audit_neb_09 are endpoint geometries also present in common36. The seven interior NEB geometries are not present in Train60 in the frozen geometry audit.

## Later continuation

The transition-tube Stage69–91 program is documented separately in docs/POST_PUBLICATION_CONTINUATION.md. Later adaptive development is not folded into the original pipeline or presented as a single preregistered validation experiment.

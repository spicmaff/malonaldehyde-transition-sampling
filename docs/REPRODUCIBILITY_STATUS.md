# Reproducibility status

## Included

- Accepted strict-comparison scripts from independent PBE NEB through project
  closeout.
- Frozen-audit and primary-metric recovery code.
- Relaxed MTP-NEB and first-update applicability diagnostics.
- Exact source-oracle and geometry-provenance audits.
- Final renderers for Figures 1–4 and Supplementary Figures S1–S3.
- Supplementary Table S1 builder.
- Final renderers for all three videos.
- Frozen-path one-dimensional H/D quantum-level audit.
- Compact source tables, final figures, videos, manifests, checksums, and CI.

## Not redistributed

- Quantum ESPRESSO, MLIP, and LAMMPS binaries.
- Pseudopotentials whose redistribution terms must be handled separately.
- Full scratch directories and all historical failed attempts.
- Large intermediate DFT outputs that are not needed to inspect the published
  numerical claims.

## Scientific limitation

Static agreement with the frozen PBE reaction path does not establish
deployment-ready free dynamics. The six first unconstrained updates exceeded
the predefined applicability threshold. The one-dimensional H/D audit is a
frozen-path spectral diagnostic, not a full-dimensional tunneling-rate
prediction.

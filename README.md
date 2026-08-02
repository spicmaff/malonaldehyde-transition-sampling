# malonaldehyde-transition-sampling

Code, compact source tables, and publication-facing outputs for an equal-budget
comparison of basin-focused and transition-focused training data for proton
transfer in malonaldehyde.

## Main result

Both Moment Tensor Potential (MTP) models used 60 DFT configurations: 36 shared
configurations and 24 strategy-specific additions. Relative to placing the 24
additional configurations near the stable basins, placing them in the
proton-transfer region reduced the frozen-PBE-path barrier error from 35.25 to
4.10 meV and the transition-region force-component RMSE from 0.1760 to
0.0787 eV/Å.

The conclusion is deliberately limited: static reaction-path fidelity did not
establish deployment-ready dynamics. All six first unconstrained updates
exceeded the predefined applicability threshold.

> Transition-focused equal-budget sampling improves static barrier fidelity,
> but does not by itself guarantee deployable reactive dynamics.

## Repository contents

- `scripts/core_pipeline/` — accepted strict-comparison scripts from the
  independent PBE NEB calculation through project closeout.
- `scripts/figures/` — final renderers for Main Figures 1–4 and Supplementary
  Figures S1–S2.
- `scripts/quantum/` — frozen-path H/D audit and Supplementary Figure S3.
- `scripts/tables/` — Supplementary Table S1 builder.
- `scripts/videos/` — final renderers for all three videos.
- `scripts/audits/` — exact replay, source-oracle, and provenance diagnostics.
- `data/` — compact frozen-path and quantum-audit source tables.
- `docs/` — methods, limitations, provenance, and execution boundaries.
- `tools/` — public-release audit and repository-integrity self-tests.

Large release assets may be attached to a GitHub Release instead of stored in
ordinary Git history.

## Clean-clone verification

A clean clone can verify repository integrity, manifests, checksums, Python
syntax, dependency declarations, and public-release hygiene:

```bash
python3 tools/run_public_selftests.py .
python3 tools/audit_public_repo.py .
```

Equivalent wrapper:

```bash
./reproduce/run_repository_selftests.sh
```

## Scientific reproduction

The accepted scientific pipeline is ordered in
[`docs/PIPELINE.md`](docs/PIPELINE.md). It requires a compatible project tree
containing the locked upstream inputs and the external scientific programs used
by the original calculation.

```bash
conda env create -f environment.yml
conda activate malonaldehyde-transition-sampling
```

Examples using an existing compatible project root:

```bash
./reproduce/run_quantum_audit.sh /path/to/malonaldehyde_mtp_al
./reproduce/render_all_figures.sh /path/to/malonaldehyde_mtp_al
./reproduce/build_supplementary_table_s1.sh /path/to/malonaldehyde_mtp_al
./reproduce/render_all_videos.sh /path/to/malonaldehyde_mtp_al
```

The video renderers require the `ffmpeg` executable. It is included in the
Conda environment specification but is not installed by `pip`.

## Reproducibility boundary

This repository contains the accepted versioned code and compact public inputs.
It does not redistribute Quantum ESPRESSO, MLIP, LAMMPS/MLIP, pseudopotential
files, all historical attempt directories, or large scratch outputs.

Therefore:

- repository-integrity verification works from a clean clone;
- final renderers and audits work with a compatible project tree;
- the complete heavy DFT/MTP calculation is not containerized into this Git
  repository.

See [`docs/EXECUTION_BOUNDARY.md`](docs/EXECUTION_BOUNDARY.md) and
[`docs/REPRODUCIBILITY_STATUS.md`](docs/REPRODUCIBILITY_STATUS.md).

## Scientific scope

The PBE NEB path is an internal fixed reference. The one-dimensional H/D level
gaps are frozen-path spectral diagnostics, not experimental tunneling rates and
not full-dimensional quantum dynamics. MaxVol applicability grade is an
extrapolation diagnostic, not a quantitative DFT error.

See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## References

- [Shapeev 2016: Moment Tensor Potentials](https://doi.org/10.1137/15M1054183)
- [Podryabinkin and Shapeev 2017: Active Learning of Linearly Parametrized Interatomic Potentials](https://doi.org/10.1016/j.commatsci.2017.08.031)
- [Henkelman, Uberuaga, and Jónsson 2000: Climbing-image NEB](https://doi.org/10.1063/1.1329672)
- [Tikhonov 2022: A Simplistic Computational Procedure for Tunneling Splittings Caused by Proton Transfer](https://doi.org/10.1007/s11224-021-01845-4)

## Citation

GitHub renders citation metadata from [`CITATION.cff`](CITATION.cff).

## Licensing

- Code: MIT.
- Original compact data and media: CC BY 4.0, unless noted otherwise.

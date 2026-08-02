# malonaldehyde-transition-sampling

Code, compact source tables, and publication-facing visual outputs for an
equal-budget comparison of basin-focused and transition-focused training data
for proton transfer in malonaldehyde.

## Main result

Both MTP models used 60 DFT configurations: 36 shared configurations and 24
strategy-specific additions. Relative to adding the 24 configurations near
the stable basins, placing them in the proton-transfer region reduced the
frozen-PBE-path barrier error from 35.25 to 4.10 meV and the transition-region
force-component RMSE from 0.1760 to 0.0787 eV/Å.

The result is deliberately limited: static reaction-path fidelity did not
establish deployment-ready dynamics. All six first unconstrained updates
exceeded the predefined applicability threshold.

> Transition-focused equal-budget sampling improves static barrier fidelity,
> but does not by itself guarantee deployable reactive dynamics.

## Repository contents

- `scripts/` — versioned analysis and figure-generation code.
- `data/frozen_audit/` — compact frozen-path source tables and NEB9 geometry.
- `data/quantum_audit/` — compact one-dimensional quantum-audit tables.
- `figures/` — final selected figures.
- `media/` — media small enough for ordinary Git, when present.
- `docs/` — methods, provenance, limitations, and publishing instructions.
- `tools/audit_public_repo.py` — local release audit.
- `provenance/PUBLIC_ASSET_MANIFEST.tsv` — sanitized public provenance.

Large videos are kept outside Git history under the sibling `release_assets/`
directory and can be published as GitHub Release assets.

## Reproduction

```bash
conda env create -f environment.yml
conda activate malonaldehyde-transition-sampling
./reproduce/run_stage62_quantum_audit.sh /path/to/malonaldehyde_mtp_al
./reproduce/run_stage63_quantum_figure.sh /path/to/malonaldehyde_mtp_al
```

## Scientific scope

The PBE NEB path is an internal fixed reference. The one-dimensional H/D level
gaps are frozen-path spectral diagnostics, not experimental tunneling rates
and not full-dimensional quantum dynamics. MaxVol applicability grade is an
extrapolation diagnostic, not a quantitative DFT error.

See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## References

- [Shapeev 2016: Moment Tensor Potentials](https://doi.org/10.1137/15M1054183)
- [Podryabinkin and Shapeev 2017: Active Learning of Linearly Parametrized Interatomic Potentials](https://doi.org/10.1016/j.commatsci.2017.08.031)
- [Henkelman, Uberuaga, and Jónsson 2000: Climbing-image NEB](https://doi.org/10.1063/1.1329672)
- [Tikhonov 2022: A Simplistic Computational Procedure for Tunneling Splittings Caused by Proton Transfer](https://doi.org/10.1007/s11224-021-01845-4)

## Citation

GitHub renders citation metadata from [`CITATION.cff`](CITATION.cff). Replace
the placeholder repository URL and verify author metadata before public push.

## Licensing

- Code: `MIT`.
- Original compact data and media: `CC-BY-4.0`, unless noted otherwise.

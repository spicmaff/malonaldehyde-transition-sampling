# Local Train119 PBE-reference diagnostic

Published as an additive post-publication saved-data diagnostic. The original Stage91J failure remains authoritative.

A separate diagnostic study evaluated the unchanged Train119 model on selected, already generated configurations after its frozen static applicability check had failed. The historical `STATIC_APPLICABILITY_FAIL` remains unchanged.

Seven neighboring configurations from a previously saved Train109 trajectory form Crossing7: Replay228 indices 142–148, including five recorded crossings of the Train119 coverage threshold. Four nearby development challenges from another saved trajectory form Challenge4: indices 93–96, adjacent to the later training additions 97–100. Seven new PBE single points were used for Crossing7; Challenge4 reused four existing PBE references. No new model training, selector construction, or dynamics was performed in this diagnostic study.

All eleven configurations satisfy the inherited per-configuration Cartesian force-component RMSE criterion of 0.09 eV/Å. The largest RMSE is 0.027965 eV/Å on Crossing7 and 0.029823 eV/Å on Challenge4. This is a local observation: recorded coverage rejection can coexist with small PBE-reference force error. It does not calibrate a universal gamma-to-error relationship or justify increasing a deployment threshold.

A separate saved-data evaluation on the fixed PBE Audit21 path gives a discrete lower-endpoint barrier error of 0.123 meV and central-three-image force-component RMSE of 0.013834 eV/Å for Train119. These are development diagnostics, not independent generalization results. Two known NEB endpoint geometries overlap the training set within the established geometric comparison tolerance. The small barrier error is not a bound on every energy-profile error.

A narrow lossless-output patch resolves the recorded CFG serialization problem in a separate executable copy; it does not alter the frozen model or remove historical nonconformance. Proton H2 and the historical crossing force component C3/y are identified separately.

The selected data and source/public hashes are described below;
[the correction note](TRAIN119_CORRECTIONS.md) records historical reporting
issues. The saved payload can be checked without QE, MLIP inference, or dynamics:

```bash
python tools/verify_train119_diagnostic.py \
  --data data/post_publication/train119_diagnostic_v001
```

Crossing7, Challenge4, Validation11, and the reused audit are development data. Their success does not establish deployment-ready reactive dynamics, experimental accuracy, or an independent final test. Blind12 remains unrevealed.


## Reproduction and provenance

The frozen, pseudopotential-identified source files are in
`data/post_publication/train119_diagnostic_v001`. PBE SCF results and XML are
saved, and each of the original 57 inputs/outputs is connected to a source
archive member and two SHA-256 identifiers in `SOURCE_MANIFEST.json`.
The public data are an allowlisted subset of the diagnostic completed on
2026-10-05, not a rerun of first-principles calculations.

The numerical checker verifies all eleven exact PBE input geometries, formal
QE output and XML labels, species mappings, stored model predictions, all 21
Audit21 predictions, Validation11 output precision, and model/training identity.
It compares the recorded selector scores, but does not reconstruct the active
basis, recalibrate applicability or replicate model training.

Run from the repository root:

```bash
python3 -B tools/verify_train119_diagnostic.py \
  --data data/post_publication/train119_diagnostic_v001
```

For a compact provenance explanation see
`provenance/TRAIN119_DATASET_ROLES.tsv` and
`provenance/TRAIN119_GEOMETRY_RELATIONS.tsv`.
The latter is an ordered-atom pair-distance screen, not a complete
permutation-aware or statistically independent holdout study.
See `docs/TRAIN119_CORRECTIONS.md` for the strict-vs-screen threshold
difference and the proper-alignment caveat.

## Physical interpretation and limits

This is an observation of local PBE-relative numerical agreement, not an
experimentally calibrated proton-transfer potential. The saved K=24/pool=24
original equal-budget experiment is separate and has its own seed-sensitivity
limits. This Train119 model has 119 training configurations and was developed
adaptively using Replay228; it is not an equal-budget strategy comparison.
All eleven local test configurations are from two saved 100 K trajectory
segments that were used in development; none is a Train119 free trajectory.

The discrete barrier error of 0.123 meV is not a profile error bound: the
maximum energy-profile error in the nine saved NEB images, after referencing
each series to its own lower endpoint, is about 0.504 meV. No new formal energy PASS was defined.
A2=0.09 eV/Å is a per-configuration 27-component RMSE criterion; on Challenge4
some individual component errors exceed 0.09 eV/Å without violating A2.
No calibrated error tolerance across higher-temperature conditions is claimed.

The old threshold 1.0000012996964838 and its five Replay228 crossings remain
unchanged. No Train119 Gate1, Gate2, long MD or prospective independent
validation was performed and Blind12 was not accessed. The seven new PBE
single points in Crossing7 were completed in the historical October-5 study,
not by this packaging step.

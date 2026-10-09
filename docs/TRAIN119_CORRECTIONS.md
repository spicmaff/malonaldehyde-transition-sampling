# Train119 diagnostic corrections and scope

This is an additive correction note. It does not rewrite frozen models, inputs,
predictions, historical protocols, or the original Stage91J outcome.

## Endpoint geometry dependence

The historical review found one ordered-distance match using a 1e-12 angstrom
criterion. That statement is correct for that criterion but is not a complete
classification of relevant training dependence. The two known NEB endpoints
match training configurations 9 and 10 under the previously used 2.1e-6 angstrom
geometric screen. Their maximum ordered pair-distance discrepancies are about
8.66e-15 and 8.64e-11 angstrom, respectively.

For the right endpoint, a proper rotation of approximately 0.767609 degrees aligns
the structures with maximum Cartesian residual about 4.81e-11 angstrom. Its force
vectors must be transformed into the same frame before comparison. The aligned
reference-label force-component difference is approximately 3.04e-5 eV/angstrom.
This small difference is not, by itself, evidence of a serious reference-label
failure. Its physical cause was not established by the selected-frame check.

The historical strict-match count is preserved in the saved report;
[the geometric-dependence table](../provenance/TRAIN119_GEOMETRY_RELATIONS.tsv)
records the two comparison thresholds separately. Two known overlaps do not
establish the absence of all other same-species permutation matches or
statistical dependencies.

## Force-component labels and chronology

Zero-based atom index 2 denotes C3, whereas the transferred proton is H2, zero-based
index 1. The original execution scalar named `winning_atom2_y_error_eV_A` contained
H2/y. Report proton H2/y and the historical crossing component C3/y separately.
Do not claim C3/y is the winning selector component on every Challenge4 frame
without corresponding per-frame winner provenance.

The geometry-unit correction was recorded before the new scientific calls.
The atom-index annotation was corrected after Challenge4 evaluation and before
Crossing7 evaluation. These are not the same chronological claim. Primary raw
force arrays and per-configuration RMSE are not changed by this annotation fix.

## Dataset roles and frozen failures

Origin features such as `training_eligible=false` are not a substitute for the
later, stage-specific authorization and membership index. Preserve the frozen
CFG bytes. The subsequently authorized training role is recorded in the
[external provenance table](../provenance/TRAIN119_DATASET_ROLES.tsv). A held-out neighboring frame is still not an IID final test.

Preserve old Stage91J `STATIC_APPLICABILITY_FAIL`, the old output-serialization
nonconformance, and the later local force-RMSE result as distinct outcomes.
No change of global gamma threshold, model promotion, or Blind12 disclosure follows.

## Metrics

A2 refers to each configuration's 27-component Cartesian force RMSE. It is not
a maximum-component or single-atom vector-error bound. The barrier metric uses
nine fixed PBE-path energies and the lower endpoint. It is not a continuous MEP,
free-energy barrier, uniform profile error bound, or experimental prediction.

## Quantum appendix

The saved effective 1D gap can be retained with explicit model assumptions.
In primary targeted-H, E1 is approximately 1.25214 meV above the model barrier;
a subbarrier doublet is therefore not reproduced in that case. Coordinate-dependent
mass, kinetic-operator ordering/measure, walls and path interpolation need separate
physical justification for a stronger tunneling interpretation. This does not
block the selected classical Train119 diagnostic publication.

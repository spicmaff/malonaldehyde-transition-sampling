# Limitations

1. PBE is an internal computational reference, not experimental ground truth.
2. The original headline comparison is one stochastic training realization per branch. The original v028 RNG seed was not recorded.
3. A five-seed post-publication paired audit is seed-sensitive: targeted wins both primary metrics in only 3 of 5 pairs.
4. The transition v026 pool contained exactly 24 candidates with K = 24, so the experiment does not test subset ranking inside a larger transition pool.
5. Two NEB endpoint geometries overlap common36. Audit21 and the whole NEB9 path are not fully independent holdouts.
6. The primary transition-force metric uses interior images and is not affected by those endpoint overlaps.
7. Basin relaxed MTP-NEB is geometrically invalid. The targeted relaxed path is strongly extrapolative by historical MaxVol grade.
8. Historical MaxVol gamma is not a quantitative DFT-error estimate. Later calibration does not support a universal scalar gamma-to-force-error map.
9. The public first-update diagnostic contains captured first attempted updates, not a validated free MD trajectory.
10. Late Replay228 was repeatedly used for adaptive diagnosis and remediation and is not an unbiased final holdout.
11. Validation11 is a frozen diagnostic set, not an independent holdout; at least one geometry is present in Train119 and two additional cases are serialization-scale near-duplicates.
12. The Train119 Validation11 saved payload is 11/11 below A2, but a frozen pair-distance serialization guard remains formally nonconforming.
13. Train119 fails the frozen static applicability criterion on five Replay228 configurations. No Train119 Gate1 or Blind12 result exists.
14. Blind12 remains unrevealed and was not used for training.
15. The H/D audit is one-dimensional and is not a rate model or full-dimensional quantum dynamics.
16. Full DFT and model-training recomputation requires external scientific software and pseudopotentials that are not redistributed here.

## Limits of the later local Train119 diagnostic

The October 5 follow-up does not change limitations 10-14. Crossing7 and
Challenge4 comprise correlated, post-selected development configurations at
100 K. Challenge4 is adjacent to training additions from the same trajectory.
Its A2 pass is not a maximum-component bound, and the separate 0.123 meV
Audit21 barrier error is not an error bound for the full energy profile.
The historical serialization failure and later output-only qualification
remain distinct facts. Small local PBE errors do not authorize relaxing the
applicability stop or establish prospective dynamics or experimental accuracy.
See [the full scoped diagnostic](TRAIN119_LOCAL_DIAGNOSTIC.md).

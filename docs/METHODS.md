# Methods summary

## Equal-budget design

The original comparison used two L12 Moment Tensor Potentials with the same architecture, hyperparameters and total DFT configuration count. Each training set contains common36 plus 24 strategy-specific configurations, for 60 configurations total.

The basin branch places its additional configurations near the stable minima. The transition branch uses 24 generated transition-region candidates. Because the transition pool contained exactly 24 candidates and K = 24, all 24 passed into the branch. This is an equal-budget spatial-allocation comparison, not a test of MaxVol subset ranking from a larger transition pool.

## Original stochastic training

The original v028 MLIP command used random initialization and did not record an explicit RNG seed. No hyperparameter search, warm start or post-audit model selection was performed, but this missing seed prevents deterministic retraining of the exact original model pair.

The original model bytes and predictions are preserved and included in data/frozen_models_v028.

## Frozen-path audit

Both original models were evaluated against the same independently computed nine-image PBE NEB path.

The seven interior NEB images are absent from both Train60 sets in the frozen geometry audit. The two endpoint geometries overlap common36. Therefore the nine-image path is not a wholly independent holdout.

Primary metrics use the repaired v030r definitions:
- lower-endpoint barrier error: absolute difference between model and PBE values of max(E) minus min(endpoint E);
- transition force-component RMSE: combined Cartesian force components for NEB images with absolute qPT <= 0.15 A.

The transition-force primary metric uses three central images and is unaffected by the endpoint overlaps.

## Post-publication training-randomness audit

Five paired 64-bit seeds were derived deterministically from SHA-256 strings before retraining. For each seed, basin60 and targeted60 were trained from the same locked untrained L12 template with the original max-iter and loss weights. A patched MLIP binary replaces random_device by the frozen MLIP_RANDOM_SEED value; no retry, warm start, hyperparameter search or best-seed selection was allowed.

No DFT was recomputed. Each resulting model was evaluated on the same frozen Audit21 labels. This audit is post-publication and is not part of the original preregistered comparison.

## Secondary relaxed-path audit

The basin-trained original model underwent a geometric collapse in relaxed MTP-NEB and does not have a physically meaningful optimized barrier. The targeted original model converged close to the PBE path but had very large historical applicability grades, so this is secondary evidence only.

## First-update applicability diagnostic

Six endpoint-to-first-update cases were generated at 100, 300 and 500 K from the left and right minima. Exact later replay shows that the captured configurations after the first attempted integration update are above the historical MaxVol threshold. The diagnostic contains no usable free trajectory and no DFT force-error measurement on those six frames.

## Post-publication Train119 continuation

The later transition-tube program used separate protocol-freeze, execution, review and interpretation stages. It eventually produced deterministic Train119.

The final Stage91J execution constructed one fresh Train119 X0.1 force-aware selector, derived a fresh numerical applicability stop, graded Replay228, and evaluated Validation11 until a frozen serialization guard stopped execution. The saved Validation11 payload is complete; all 11 force RMSE values are <= 0.09 eV/A. Validation11 is not an independent holdout. Replay228 has been repeatedly used for adaptive development and is a development benchmark.

Five Replay228 configurations, indices 143 through 147, exceed the fresh Train119 stop. The Train119 lineage is therefore closed as a static-applicability failure, without Gate1 promotion.

## Quantum diagnostic

A one-dimensional stationary Schrodinger equation was solved with PBE, basin-MTP and targeted-MTP energies on the same frozen PBE path. These level gaps are spectral diagnostics, not experimental tunneling rates or full-dimensional quantum dynamics.

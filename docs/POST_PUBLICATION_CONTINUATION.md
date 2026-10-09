# Post-publication continuation

After the original equal-budget comparison, a separate transition-tube program tested whether additional transition-region coverage could improve deployment applicability.

## Governance

Stage69 froze a continuation protocol with fixed budgets, seeds, software hashes, geometry guards and explicit forbidden claims. Subsequent failures led to adaptive diagnostic and remediation stages. Those later stages are model development, not one continuous confirmatory experiment.

## Applicability versus force accuracy

The original energy-only applicability gate failed early for Tube92. Later PBE calculations on the rejected neighborhood did not show force errors near the inherited A2 = 0.09 eV/A scale. Stage88 calibration over 22 PBE-labelled frames found only a weak global association between force-aware gamma and force RMSE and inconsistent condition-specific behavior.

The project therefore treats gamma as a coverage/applicability diagnostic, not a universal physical-error threshold.

## Adaptive models

The continuation produced Train109, Train112, Train115 and finally Train119. Local validation diagnostics generally showed force errors below A2, while static applicability failures continued to identify narrow active-space coverage deficiencies.

Because Replay228 was repeatedly used to locate those deficiencies and choose remediation frames, it is a development benchmark rather than an untouched final validation set.

## Train119 final check

Train119 training was deterministic: primary and replay model files are byte-identical.

The frozen Stage91J check used:
- a fresh Train119 X0.1 norm-matched force-aware selector;
- fresh self-grade and numerical stop;
- fresh Replay228 grading;
- one Validation11 model evaluation before the frozen serialization guard stopped execution.

Fresh stop: 1.0000012996964838.
Replay228 crossings: 5, at indices 143, 144, 145, 146 and 147.

The saved Validation11 payload has all 11 force RMSE values <= 0.09 eV/A, but Validation11 is not an independent holdout. Its historical pair-distance serialization guard fails narrowly at 1.128283744e-6 A against the frozen 1.1e-6 A tolerance; that tolerance was not relaxed.

The independent recovery review confirmed the saved results. The lineage is closed as STATIC_APPLICABILITY_FAIL. This does not establish a Train119 force-accuracy failure.

No Train119 Gate1, Gate2, additional remediation, or Blind12 reveal was performed.

## Final boundary

The continuation does not establish deployment-ready reactive dynamics. Blind12 remains unrevealed.

## Separate October 5, 2026 local physical diagnosis

After frozen Stage91J closure, a distinct, bounded post-closure diagnostic
qualified a lossless CFG writer and examined eleven already generated 100 K
development geometries with authenticated PBE labels. Five saved applicability
crossings in the right-minimum neighborhood coexisted with RMSE below A2.
A further saved Audit21 evaluation gave a 0.123 meV lower-endpoint barrier
error and 0.013834 eV/Å central-transition force-component RMSE, both
development diagnostics with known training endpoint overlaps.

This follow-up did not re-run Train119, re-grade Replay228, change the old
numerical stop, create a Train119 trajectory, or clear the historical
`STATIC_APPLICABILITY_FAIL`. The historical Validation11 serialization
nonconformance remains recorded even though a later output-only patch
qualifies on the same frozen inputs. See [the separate diagnostic](TRAIN119_LOCAL_DIAGNOSTIC.md)
and [its corrections](TRAIN119_CORRECTIONS.md).

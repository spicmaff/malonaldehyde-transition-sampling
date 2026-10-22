# Scientific finale: an improvement of which objective?

This review develops the existing Optimization chapter, not a thirteenth route.
The research result is a diagnosed objective tradeoff in one audited MTP refit.
C-PROX-COV remains a constructive hypothesis, not a demonstrated real-data winner.
Production is unchanged until a separate owner-approved merge.

## Sources and what can be checked now

The only numerical input is the unchanged, already-public
`data/optimization_story/v001/OPTIMIZATION_STORY.json` at published base
`d713f60a3050f6a7b27a0d3e679e0bf58b93ddf0`, SHA-256
`91ba4b11b43a6966b2e1cc4ef43eef765bedd58a7de1f0975ae14b2550185131`.
`tools/build_scientific_finale.py` validates its semantics and derives scalars using
140-digit Decimal arithmetic. It opens no restricted source and runs no native
model, refit, DFT, dynamics, training or recovery. Output `data/finale.json`
includes exact source fields and the public input identity.

The source export reports earlier physical measurements. This review does not
repeat them: the full private recovery bundle remains unavailable. Recomputing
aggregate arithmetic is not independent re-establishment of its native replay.
No source hash is substituted for missing source bytes.

## Central comparison and the two baselines

The native sequence compares S0 and S2 using native weighted training J, including
its radial penalty. Diagnostic copies S1c and S2q are not accepted native steps;
S3 retains a null, NOT_MEASURED objective.

The new principal figure instead compares S1c and S2 in ROW_EXACT_FIXED_D:

    ell(beta) = ||A beta - y||^2 / 60
    R(beta)   = beta^T D beta / 60
    Q(beta)   = ell(beta) + R(beta)

S1c is the compensated incumbent in the changed radial frame. All three plotted
terms share a linear scale from zero to 0.004. The displayed row loss, coefficient
ridge and total Q are not force RMSE, and Q is not native J. Q falls by approximately
28.64276%, with an increased residual outweighed by a larger penalty reduction.
The source signed balance and every Q=sum identity are checked independently.
Regularization can intentionally trade training fit for other properties. Neither
a better nor a worse external model follows from this arithmetic alone.

| Finale statement | Exact payload field | Evidence / limitation |
|---|---|---|
| Same-system tradeoff | `theory.linear_system.row_loss_table` | Public aggregate arithmetic; not a new solve |
| Signed balance | `theory.linear_system.signed_ridge_balance` | One fixed D and /60 normalization |
| Native S2/S0 ratio | `theory.main4500.states`, `S2_to_S0_ratio` | Earlier native measurements; different comparison |
| Precision control | `theory.main4500.S2q_minus_S2_native_J`, `linear_system.systems` | S2q targets ROW_EXACT_FIXED_D, not ACTUAL_K_CAPTURE |
| Direction control | `theory.prediction_prox.native_ridge_direction` and `data_loss_incumbent` | Rounded saved quadratic; no new model calls |
| main50 counterexample | `observer.short_main50` | Historical reported summary, not a new physical replay |
| Metric transport | `theory.transport`, `theory.COV.covariance_scope` | Allowed invertible transport and one chosen metric |
| COV percentage | `theory.COV` | S1c incumbent, fixed-row calculation, no physical candidate |
| T1 / T2 | `scope`, `t1.statuses` | Synthetic-only qualification; T2 unexecuted |

## Precision and the shorter-step control

ROW_EXACT_FIXED_D, CAPTURE_G_PLUS_EXACT_D and ACTUAL_K_CAPTURE remain explicitly
separate systems. The physical S2q comparison barely changes the elevated native J;
it is not described as an exact solution of the same captured native matrix.

The calculated alpha curve is `ell(0)+a*alpha+b*alpha^2/2`. Its coefficients come
from the saved direction diagnostic, not a reconstruction of inaccessible A or
beta. Both a and b are positive, so the minimum on [0,1] is alpha=0. Its origin
agrees with the separate row table within 1e-16; the endpoint within 1e-15 absolute
error. These tolerances acknowledge rounded records, not a precision certificate.
The curve is expressly labelled DERIVED_QUADRATIC_NOT_PHYSICAL_TRAJECTORY. It
concerns the direction from compensated S1c toward native ridge coefficients with
fixed A, y and radial block. It does not test damping the full S0-to-S4 operation.
The opposite main50 example remains visibly adjacent.

## Coordinate diagram and candidate scope

With A'=A T^T and beta'=T^-T beta, predictions agree. The equality of one chosen
quadratic penalty requires D'=T D T^T. The diagram is conceptual, not a measured
248-dimensional landscape. The specific graph uses an allowed lower-triangular
channel transformation; force parity needs a smooth geometry region. Fixed-
composition candidate increments use the existing 32-by-30 feasible map.
Reconstructing an arbitrary diagonal metric in each frame is not a globally
invariant policy. A different positive metric can also guarantee fixed-system
increment descent; no unique superiority is attributed to covariance here.

The COV percentage is not the repair of the native S2 jump. It compares a candidate
to compensated S1c. Its potential was not exported or physically evaluated.
A native-J acceptance test and complete rollback can guard a chosen objective;
they do not guarantee faster complete training, a better final minimum, unseen
force accuracy or MD suitability. T1 is engineering on synthetic fixtures. T2
requires cost-matched full training and an independent physical evaluation;
PBE14 has already been used for development.

## Editorial and accessibility contract

All twelve routes, six original Optimization anchor IDs, native state reader,
coefficient atlas, films, geometry renderers and negative verdicts remain. The
existing title and native snapshots stay; the hero's secondary emphasis changes
from prospective COV performance to the diagnosed Q tradeoff. The old final anchor
`opt-next-study` now contains an explicit conclusion, with future work subordinate.
There is no claimed causal explanation of earlier seed or regional effects.

The new six-step reader never changes stored numbers or chart geometry. It changes
highlight emphasis and explanatory text. Playback is finite, user initiated,
stoppable, keyboard accessible, and cancelled on route/visibility changes. Reduced
motion keeps manual steps and disables auto-play. Two source-bound static bars and
an exact table remain without JavaScript. A mobile HTML rendering uses the same
fixed scale and source rows, rather than unreadably shrinking SVG labels.
Both original optimization JSON and the finale JSON must validate before controls
enable. Missing, malformed or semantically inconsistent data leave static evidence
visible and controls disabled. No runtime dependency or scientific computation is
introduced; the slider only evaluates the displayed scalar quadratic.

## Reproduce

    python -B tools/build_scientific_finale.py
    python -O -B tools/build_scientific_finale.py
    python -B -m unittest discover -s tests -p test_scientific_finale.py
    python -O -B -m unittest discover -s tests -p test_scientific_finale.py
    python -B tools/build_research_site.py --out _site
    python -m http.server 8000 --directory _site

Open `http://localhost:8000/?still#opt-finale-tradeoff`. The original three browser
runners and presentation/cinematic supplements remain mandatory. The additional
`tools/site/browser_finale_test.mjs` checks every new state and fallback against a
real HTTP build, records axe incomplete nodes without declaring them passes, and
captures the final and baseline build in the same browser. Local static renderings
must be labelled separately and cannot substitute for these CI receipts.

## Retained first-browser findings

The first exact-tree research-site PR run, `39699868218` at `3bd6868`,
failed its unchanged Optimization axe test. The new main50 counterexample
used a tinted panel and inherited accent foregrounds for its eyebrow and
source link; those two text nodes had insufficient contrast in light mode.
The correction uses the existing theme's ink foreground for those nodes,
retains the visible underline and adds the counterexample to the new scoped
axe run. A palette arithmetic regression checks both themes. The old failure
is retained, not relabelled as success; no old test or numerical criterion
is relaxed.

The first Windows HTTP supplement independently encountered a server MIME
configuration: `.mjs` was served as `text/plain`, so Chrome correctly refused
the module scripts. A review-only HTTP handler explicitly serves JavaScript,
JSON and CSS MIME types. Browser security settings and site scientific code
were not bypassed. This is an environment receipt, not a scientific failure.

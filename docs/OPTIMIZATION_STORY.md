# The fit is not the finish: optimization methods and evidence

The additive `#optimization` chapter asks what a periodic linear refit, a final
model save and a proposed safer update actually establish. It follows one
source-verified long-run boundary, contrasts two saved checkpoints and reports
historical synthetic qualification. It does not establish a better real-data
optimizer or replace the project's original sampling experiment.

The chapter is a **review build**. The
[published exhibit](https://spicmaff.github.io/malonaldehyde-transition-sampling/)
already includes [Off the path](https://spicmaff.github.io/malonaldehyde-transition-sampling/#offpath).
The optimization preview is served from this branch or its review artifact;
`#optimization` is not presented here as an already published production route.

## Numerical authority and reading levels

The sole chapter payload is
[OPTIMIZATION_STORY.json](../data/optimization_story/v001/OPTIMIZATION_STORY.json).
[CLAIM_DATA_MAP.tsv](../data/optimization_story/v001/CLAIM_DATA_MAP.tsv) contains
90 statements with source fields, units, evidence classes, access tiers and review
checks. [PROVENANCE.json](../data/optimization_story/v001/PROVENANCE.json) identifies
71 reviewed sources, including 23 existing public sources with immutable URLs.
[PUBLICATION_ALLOWLIST.json](../data/optimization_story/v001/PUBLICATION_ALLOWLIST.json)
binds the small public package. Rounded numbers below are explanatory views of
those canonical values, not a second input to the interface.

The claim map's `source_field` is populated for every claim. The optional
`data_field` is relative to the named section for theory; observer/T1 rows rely
on their source field and named table rather than a populated data-field locator.
`status` is the common evidence category. `verification_status` preserves the
more specific finding, including `REPORTED_*` for the recovered historical
main50 reader. Restricted audit-relative source names are identifiers, not
paths in the public repository or hidden download links.

Three different questions remain separate throughout:

| Question | Evidence here | Limit |
|---|---|---|
| What follows mathematically? | Finite-graph transport identities and a conditional fixed-system COV inequality | Stated graph, rank, smoothness, feasible-space and metric assumptions |
| What happened in the saved numerical case? | One recovered diagnostic training, six physical replays, saved-array arithmetic and one historical checkpoint pair | One selected boundary/pair; measured values and reported summaries have different tiers |
| Does a proposed optimizer improve prediction reliably? | Historical synthetic T1 engineering; a future T2 design | No real-data COV optimizer superiority or independent external validation demonstrated |

## Four spaces, not one parameter count

An isolated nonlinear nine-atom geometry has 27 Cartesian coordinates and,
locally after removing three translations and three rotations, 21 internal
coordinates. Special geometries need separate treatment. Those geometry counts
are different from the fitted representation's 248 nominal parameters:

| Representation block | Count | Meaning |
|---|---:|---|
| Radial coefficients | 216 | Three species × three directed neighbor species × three channels × eight radial functions |
| Invariant coefficients | 29 | Effective coefficients include the stored linear multipliers |
| Species offsets | 3 | One offset per species; only one composition-weighted combination is observed at fixed C₃H₄O₂ composition |

The radial coefficients form a 3 × 72 channel matrix. At regular radial rank
three, the identified invertible lower-triangular channel transformations have
six degrees of freedom. Their local quotient is the partial flag
$F_1 \subset F_2 \subset F_3 \subset \mathbb{R}^{72}$ with dimensions 1, 2 and 3:
$71 + 70 + 69 = 210 = 216 - 6$. The fixed-composition offsets add two identified
null directions. Thus $248 - 6 - 2 = 240$ is the dimension after these known local
symmetries are removed. It is **not a proved exact rank of the physical E/F
Jacobian**, a complete symmetry classification or an optimizer-convergence result.

The model maps a geometry and its parameters to energy and forces. Training J,
row loss and external force RMSE then summarize different aspects of those
predictions. Scaling, multipliers, caches, the inverse Hessian and line-search
state also affect implementation behavior; they are not extra independent
coordinates of the same 248-vector. See claims `OPT_THEORY_001`–`005`, sources
`theory.architecture_atlas`, `theory.architecture_bridge`, `theory.exact_math` and
`theory.native_contracts` in the claim map.

## Native J, row loss and the inner refit

For the frozen Train60 convention—nine atoms, energy weight 1, force weight 0.01,
stress weight 0, vibrations and no relative-force normalization—the native
objective is

$$
J = \frac{1}{60}\sum_i\left[\frac{(E_i-E_i^{\mathrm{ref}})^2}{9}
  + 0.01\sum_{a,d}(F_{iad}-F_{iad}^{\mathrm{ref}})^2\right]
  + 10^{-9}P(\Theta).
$$

Here $S=\Theta\Theta^T$ and
$P=\sum_k(S_{kk}-1)^2+\sum_{k<l}S_{kl}^2$. Cross-channel terms appear once;
the radial penalty is not divided by 60 a second time. J is reported under
these weighted training conventions. It is not a force RMSE in eV/Å.

There are 32 effective linear parameters: three offsets and 29 invariant
coefficients. In the saved row construction, energy features and labels are
divided by 3 in binary64, and force features and labels are multiplied by 0.1
in binary64. Sixty energy rows plus 1620 force rows give 1680 weighted rows.
With residual $r=A\beta-y$, the row data loss is
$\ell=\|r\|^2/60$. The inner refit instead solves a regularized problem:

$$Q_D(\beta)=\frac{\|A\beta-y\|^2+\beta^TD\beta}{60}.$$

The coefficient ridge in $Q_D$ is distinct from the radial penalty in J.
Improving one objective therefore need not improve the other. The native
assembly path for its captured normal equations also differs from forming
exact scalar products of the saved row matrix. These objects are kept separate
in the analysis, rather than replacing the native computation with a convenient
matrix formula. Source `theory.native_contracts` records the reviewed native
conventions; `theory.new_main4500` records the resulting diagnostics.

## One periodic interruption at main4500

The selected boundary belongs to the recovered Basin60 seed-3 C-long diagnostic:
session 2, cap 8000, iteration 4500, refit 244. Its native order is
S0 → S1 → S2 → S3 → S4. S1c branches from S1; S2q branches from S2. The two
copies are diagnostic questions, not additional steps taken by the optimizer.

| State | Meaning | Native J | Measurement scope |
|---|---|---:|---|
| S0 | Preceding accepted model, after main4499 | 3.96610868384983 × 10⁻⁵ | Detached physical replay agrees with saved live objective |
| S1 | Radial frame changed without coefficient compensation | 1.525074560560527 | Detached physical replay; no separate live S1 objective measurement |
| S1c | Compensated copy in the new frame | 3.966082338667537 × 10⁻⁵ | New derived state, physically replayed |
| S2 | Native ridge-refit coefficients | 7.3047233495542 × 10⁻⁴ | Detached replay agrees with saved live objective |
| S2q | High-precision fixed-D row solution | 7.304723334929808 × 10⁻⁴ | New derived state targeting `ROW_EXACT_FIXED_D`, physically replayed |
| S3 | Optimizer rebase | Not measured | Physical state identity does not create another J observation |
| S4 | Next accepted BFGS model, at main4500 | 6.970148587716144 × 10⁻⁴ | Detached replay agrees with the evaluated, accepted live model |

The post-refit S2 objective is **18.4178597508 times** S0. The next accepted
BFGS step reduces J by $3.3457476184\times10^{-5}$, but the complete S0-to-S4
change is still positive, $6.5735377193\times10^{-4}$. These are differences
between states; they are not a unique allocation of causal responsibility
between refitting and BFGS. S1's large temporary J is also distinct from the
printed S0-to-S4 increase. The page therefore declares its logarithmic axis and
retains the numerical table. S3 receives no plotted zero or interpolated value.

The native softened Gram–Schmidt changes the radial frame without transporting
the coefficients to compensate. `Set_x` resets line search and retains the
same-size inverse Hessian; a full restart is a different operation. S4 is the
evaluated, accepted model, not the next unassessed trial vector. Claims
`OPT_THEORY_STATE_*`, `OPT_THEORY_S3` and `OPT_THEORY_TELESCOPE` bind these meanings
to physical replay, captured events and source contracts.

This episode is not universal. The recovered historical IXA main50 reader gives
S0 = 0.0005931939787004071, S2 = 0.000538759477805523 and
S4 = 0.0005360530518194475: that boundary decreases J. Its exact original
reader/report was recovered, but these displayed numbers retain a rounded,
reported-summary tier; they are not a new main50 physical replay. Across ten
public 8000-main logs, 1163 positive adjacent printed changes occur at multiples
of 50. Ten cap2000 logs are exact prefixes and duplicate 60 of those changes.
Neither the count nor those prefixes are independent causal experiments.
See `OBS_IXA50_*`, `OBS_LONG_1163` and `OBS_PREFIX_60`.

## What coefficient transport establishes

For the specific finite L12 graph, the reviewed algebra verifies 29 polynomial
transport identities with 134 formal monomials, 43 nonzero transport entries and
841 composition-law entries. Under an invertible lower-triangular channel map,
the conventions are
$\Phi_1=T\Phi_0$, $A_1=A_0T^T$ and
$\beta_{1c}=T^{-T}\beta_0$. Force equality additionally requires a smooth
geometry region. The determinant of the invariant transport is
$a^{65}c^{10}f^2$ under the declared triangular-map notation.

The literal softened Gram–Schmidt reconstruction matches the captured S1 frame
bitwise. On the source-verified Train60 geometries, the new S1c replay satisfies
the preregistered component condition
$|v_{\mathrm{new}}-v_{\mathrm{old}}|\le10^{-12}\max(1,|v_{\mathrm{old}}|,|v_{\mathrm{new}}|)$
for every energy and force component. Maximum absolute differences are
$9.0949470\times10^{-13}$ eV and $7.9047879\times10^{-14}$ eV/Å.

This is not equality of full native J. The physical data-loss difference is
about $9.8933\times10^{-19}$, while the radial-penalty difference is
$-2.6345182383\times10^{-10}$. That penalty accounts for the corresponding
native-J change. Exact functional transport under the graph assumptions and
finite-precision parity on Train60 also do not establish unseen prediction
accuracy. See `OPT_THEORY_TRANSPORT_EXACT`, `OPT_THEORY_TRANSPORT_EF` and
`OPT_THEORY_TRANSPORT_J`.

## Stable algebra does not remove the refit tradeoff

Three systems are analyzed independently:

| System | Definition | Physical S2q target? |
|---|---|---|
| `ROW_EXACT_FIXED_D` | Exact dyadic products of recorded binary64 A and y, with reconstructed fixed native D | Yes |
| `CAPTURE_G_PLUS_EXACT_D` | Captured native G and b, with D added in high precision | No |
| `ACTUAL_K_CAPTURE` | Actual captured binary64 K after rounded native diagonal addition, with captured b | No |

The fixed diagonal is reconstructed from captured G with the reviewed operations
$D_i=\mathrm{fl}(\gamma\,\mathrm{fl}(1+G_{ii}))$, where
$\gamma=\mathrm{fl}(10^{-13})$. It was not separately captured as D. The actual
native K includes another rounded addition. Native Gaussian elimination uses
no pivoting. The captured K has a two-norm condition number about
$1.9336881\times10^{15}$, so high-precision cross-checks are useful.

The three systems pass independent 85/110-digit and LU/Cholesky solution
comparisons. Their normalized backward errors are very small, but this is
numerical resolution, **not an interval certificate**. The resolved Gaussian
solve gap on `ACTUAL_K_CAPTURE`, normalized by 60, is about
$1.5171793\times10^{-14}$. Computing a float64 residual first and then applying
a high-precision correction overestimates that gap by about 10.6672 times.
The total effective-coefficient gap on `ROW_EXACT_FIXED_D` is about
$3.4880691\times10^{-12}$. A difference between row-Q and captured-Q is a
difference between problems; it is not a solve gap or native J.

The physically replayed S2q changes native J from S2 by only
$-1.4624392\times10^{-12}$. More stable algebra therefore barely changes the
elevated objective in this case. The signed balance in one fixed-D row problem
is more informative. With $R(\beta)=\beta^TD\beta/60$ and its optimum
$\beta_*$:

$$
\ell(S2)-\ell(S1c)
=-[Q(S1c)-Q(\beta_*)]+[R(S1c)-R(S2)]+[Q(S2)-Q(\beta_*)].
$$

| Signed-balance quantity | Value, rounded |
|---|---:|
| Data-loss increase | 0.000690811511568680 |
| Regularized improvement from S1c, subtracted | 0.00100347907346903 |
| Ridge-penalty reduction traded against data fit | 0.00169429058154964 |
| Remaining row-system gap, added | 3.4880691011 × 10⁻¹² |

The high-precision closure residual is about $1.36\times10^{-106}$. This is an
algebraic identity within the named fixed system, not percentages of physical
causation. The public payload keeps its full-precision decimal strings. See
claims `OPT_THEORY_SYSTEMS` through `OPT_THEORY_RIDGE_BALANCE`.

## A constrained COV candidate and its actual limits

Let $\beta_c$ be the compensated incumbent and $r=A\beta_c-y$. A candidate
increment minimizes $\|r+A\delta\|^2+\delta^TM\delta$ over a fixed feasible
space. Here $\delta=T_gz$, with a 32 × 30 map: its offset direction is
$(3,4,2)/\sqrt{29}$ and the remaining 29 directions are invariant coefficients.
This is a constrained step, not the general unrestricted 32-variable minimizer.

The new proposed metric D₀ is formed from pre-radial A₀ column norms using
`math.fsum`; it is not a captured native D₀. Its transport is
$B=\sqrt{D_0}T^T$, $M=B^TB=TD_0T^T$. Covariance refers to transporting **one
already chosen metric**. Rebuilding a diagonal metric in any starting gauge
does not make the entire policy gauge invariant.

For fixed A, r, feasible space and positive M on that space, zero is feasible
and the penalty is nonnegative. The exact minimizer cannot increase data loss.
Projected stationarity gives the stronger identity

$$
T_g^T[A^Tr+(A^TA+M)\delta]=0,\qquad
\ell(\beta_c)-\ell(\beta_c+\delta)
=\delta^T(A^TA+2M)\delta/60\ge0.
$$

The saved-row example changes loss from 3.9660823386673726 × 10⁻⁵ to
3.926892714784233 × 10⁻⁵, a decrease of 3.918962388313964 × 10⁻⁷ or
**0.9881192707740806% of the total incumbent data loss**. The projected
stationarity residual is about 1.28 × 10⁻²²; the descent-identity residual is
about 3.65 × 10⁻²¹. Independent QR/SVD predictions differ by at most
8.54 × 10⁻¹⁶. The regularized 1712 × 30 stack has condition number about
8.12 × 10⁷, and the coefficient increment has norm about 12120.1.

Those checks concern saved rows. **The candidate was not exported as a model
or evaluated by native E/F/J/gradient in this recovery.** Off-training accuracy
is unqualified. A future live implementation must evaluate the original native
objective, accept under its fixed tolerance or completely restore the relevant
model and optimizer state. A conceptual accept/rollback diagram is not an
execution receipt. Source `theory.new_main4500` and claims `OPT_THEORY_COV_*`
record the numerical and theoretical scopes separately.

The prediction-proximal control is also saved-row arithmetic. At lambda 1 it
removes 75% of the **available projected least-squares gap**, about 1.337531% of
the whole data loss. It is not a 75% reduction of the original error. Numerical
rank selection and a large coefficient increment remain limitations. Neither
candidate establishes a better predictive potential.

## Finishing and choosing a checkpoint

The historical XI/XI-T saved pair gives END_MAIN J = 9.558201729682155 × 10⁻⁶
and TERMINAL J = 1.3512522319231626 × 10⁻⁴, a ratio of 14.1370968111. Both
Train60 values have saved physical replay verification. Terminal fitting and
rescaling therefore deserve an explicit checkpoint policy; the last serialized
model is not automatically the best evaluated state.

External PBE14 force errors answer a separate question:

| Model | Basin region, eV/Å | Transition region, eV/Å | Evidence tier |
|---|---:|---:|---|
| Historical H | 0.0418933466501 | 0.210993959948 | Public prediction vectors and labels |
| END_MAIN | 0.0526879322180 | 0.135505374418 | Saved prediction vectors checked; original P1 runtime gap preserved |
| TERMINAL | 0.0663734088843 | 0.184006965428 | Reaggregation of 14 saved error scores; original prediction vectors missing |

The metric computes a 27-component RMSE per geometry, averages existing members
within each physical block, then gives four blocks equal weight in each region.
END_MAIN is better than TERMINAL in 8/8 blocks and 12/14 geometries; L01m and
L03m are the two worse individual cases. Against H, END_MAIN improves transition
error but worsens basin error. PBE14 was already used in development. This is one
Basin60 seed-3 pair, with 6350 main steps for XI versus 8000 for H, not an
independent or cost-matched optimizer comparison.

The historical XI journal remains missing. The XI-T P1 prediction process
completed numerically, but its runtime snapshot was not captured before exit;
the original `FAIL_STOP_NO_RETRY` remains. New C-long recovery does not repair
those histories. Source IDs `OBS_XIT_TRAIN_CONTRAST`, `OBS_XIT_PBE14`,
`OBS_XIT_GATE` and `OBS_XI_PILOT_GATE` identify the limits.

An opposite example is placed beside this result: in the synthetic T1 pipelines,
TERMINAL has lower J than END_MAIN in both CONTROL_A and COV_A, and BEST selects
TERMINAL. The shared CHECKPOINT_A policy uses strict binary64 `<`; exact ties
keep the earliest sequence. These examples motivate a fixed policy, not an
always-END_MAIN rule or selection after examining PBE14.

## T0, T1 and T2 are different claims

**Engineered and checked on synthetic runs. Not yet demonstrated to be a better
real-data optimizer.**

Historical T1 has the following scope, from the `t1-*` claim-map entries:

| Item | Recorded result | What it establishes |
|---|---|---|
| Core assertions | 94 = 72 inherited + 22 additional | Source-reviewed engineering cases; repeated runs are not extra unique cases |
| Fixture and lifecycle | 60 synthetic configurations of 9 atoms; 75 + 150 = 225 accepted states per arm | A full synthetic training lifecycle |
| Control parity | FROZEN/OFF/CONTROL_A match all 225 accepted parameter/gradient/J payloads and saved BFGS snapshots | The control path preserves the qualified baseline |
| Candidate boundaries | ACCEPT at main50 and main100 with lower native synthetic J; first 125 accepted states match CONTROL_A | Two actual synthetic candidate transactions |
| Checkpoint captures | 228 per arm: 225 accepted states, two END_MAIN captures, one TERMINAL | Complete qualified capture lifecycle; BEST is TERMINAL in both arms |
| Reload | 12 separate processes; zero recorded J/gradient error | Reload for evaluation only; full BFGS resume is unqualified |
| Reload vector | Maximum difference 4.390932062392494 × 10⁻¹⁴ in `[E/3, F × 0.1]` | Weighted vector parity, not external force RMSE |
| Filesystem faults | 21 unique file-error points and 9 signal/crash cases; 144 children and 98 assertions per complete suite | Injected fault handling, not tested power-loss durability |
| Sanitizers | ASan, UBSan and LeakSanitizer pass their qualified scope | External BLAS/LAPACK/Fortran are not sanitizer-instrumented |

Two checkpoint copies on one filesystem are not independent hardware replicas.
SHA integrity does not authenticate ownership or prevent replay of a valid stale
history without an external sequence anchor. Earlier incomplete gates and unknown
prototype counters remain recorded. The final historical closure records 29
synthetic native process records, including a fixture-hash probe, and zero real
Train60 fits, real replays, DFT, MD or Blind12 reads for that closure.

The later necessary recovery is a separate ledger: **one real diagnostic training
with 75 + 8000 accepted printed rows, and six detached physical replays**, all
serial with no retry. Its explicit replay-wrapper counts are 360 CalcEFS,
360 CalcEFSComponents and 6 CalcObjectiveFunctionGrad; internal API work was not
separately instrumented. Four live-state results match historical indexed bytes;
S1c/S2q are newly derived. The original M01 archive and old journal remain absent.
There were no T2, DFT, MD, COV-candidate physical or protected-holdout model
evaluations in this recovery. These facts do not change T1's historical counts.

T2 is `T2_NOT_AUTHORIZED_NOT_EXECUTED`. Its future outline proposes CONTROL_A/COV_A
at matched cost on two fixed Train60 allocations and five fixed seeds, with one
checkpoint policy: 20 proposed trainings, not 20 completed experiments. PBE14
remains development evidence; an independent external physical validation would
still be required. Conditional mathematical descent, correct engineering and
predictive improvement cannot stand in for one another.

## Review preview and reproduction

Run these commands from the checked-out review branch. They process committed
public data and build the site; they do not invoke MLIP, QE or a native recovery.
Python 3.11 or later and the standard library are sufficient for the chapter
verification and site build.

```sh
python3 -B tools/build_optimizer_story.py --verify
python3 -O -B tools/build_optimizer_story.py --verify
python3 -B -m unittest discover -s tests -p test_optimization_story.py
python3 -O -B -m unittest discover -s tests -p test_optimization_story.py
python3 -B tools/build_research_site.py --out _site
python3 -m http.server 8000 --directory _site
```

Open `http://localhost:8000/#optimization`. Serve a downloaded preview artifact
over HTTP too; opening a file URL is not the supported JSON-fetch workflow.
After the branch's research-site workflow succeeds, its
`research-site-preview` artifact supplies the built exhibit for review. Download
it from that actual workflow run's Artifacts section, extract it and serve the
directory containing `index.html`. The
[workflow](../.github/workflows/research-site.yml) retains the preview for 14 days;
the artifact is a downloadable review build, not a hosted production URL.
The standalone optimizer builder also accepts `--data DIR` and `--out DIR`;
`--verify` and `--out` are mutually exclusive. A full exhibit preview uses the
full-site command above. The builder has no private-source fallback.
This v001 edition also pins all five reviewed file hashes after semantic checks;
editing a checksum manifest cannot approve a different dataset or evidence tier.
A future edition needs another reviewed bundle and an updated edition gate.

The existing scientific and site checks remain required:

```sh
python3 -B tools/run_public_selftests.py .
python3 -B tools/site/test_site.py
python3 -O -B tools/site/test_site.py
node --test tools/site/test_core.mjs
```

With an already installed compatible Chrome, install the locked browser-test
dependencies and run the optimization runner against the HTTP server:

```sh
npm ci --prefix tools/site --ignore-scripts
BROWSER_DEPS="$PWD/tools/site" SITE_URL=http://localhost:8000/ \
  QA_OUT=/path/to/new-empty-optimization-qa \
  node tools/site/browser_optimization_test.mjs
```

Set `CHROME_BIN` when Chrome is not at the runner's default `/usr/bin/google-chrome`.
The complete
review also runs the existing historical and off-path browser suites, including
actual English-film playback. Five widths × two themes × twelve routes means
120 distinct view combinations. Required optimization checks cover state/source
identity, explicit log scale and missing S3, native/counterfactual branching,
finite playback, keyboard/focus, reduced motion, no-JavaScript reading and failed
JSON loading. Existing Canvas and media fallbacks remain part of the full-site
acceptance. WCAG-tagged axe checks are useful evidence within the recorded scope,
not a complete accessibility certification.

For deterministic comparisons, hold `PROTON_SOURCE_REF` fixed: off-path metadata
otherwise follows the current git HEAD. Compare protected scientific arrays and
media separately from metadata that intentionally identifies a new review
revision. Two deterministic builds, source/payload hashes, browser screenshots,
normal and `-O` tests, and actual CI results must be recorded against the tested
revision. These instructions are not a claim that a future branch revision has
already passed them; the final review report supplies the execution evidence.

## Connections and publication boundary

The new chapter links back to five-seed sensitivity, the completed off-path
comparison, Train119's separate applicability verdict and reproduction evidence.
The original transition pool still contains exactly 24 candidates with K = 24;
it does not demonstrate competitive MaxVol selection from a larger pool.
Repeated optimizer seeds do not create new independent data allocations.
`SEED_SENSITIVE`, `STATIC_APPLICABILITY_FAIL`, historical release tags and
CITATION.cff retain their existing meanings.

The public payload supports its exported arithmetic. Restricted native code,
states, full journals, full replay arrays and source-dependent numerical
reconstruction need separately available material and appropriate software
rights. See [PUBLIC_PRIVATE_BOUNDARY.md](PUBLIC_PRIVATE_BOUNDARY.md). The review
prepares a concrete draft change for visual and scientific inspection; it does
not merge, release or deploy the chapter.

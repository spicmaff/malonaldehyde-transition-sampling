# Finite-budget moment tensor potentials for malonaldehyde proton transfer: paired-seed variability and local off-path force errors

**Editorial scaffold, not a submitted or complete manuscript.** Target length:
3000–4000 words, four figures, one main table plus supporting information. Journal
selection, authorship/affiliations and final declarations remain owner decisions.
No acceptance probability or current journal quartile is asserted here.

## Central research question

For two fixed equal-size MTP-L12 training allocations, how do initialization,
finite optimization cap and evaluation region affect local force-accuracy ranking?
The contribution is a transparent bounded case study, not a new sampling algorithm.

## 1. Introduction (450–600 words)

Explain rare-region coverage and why a path comparison is insufficient. Position
against Brezina–Beck–Marsalek transition tube sampling, Transition1x and Landscape17.
Explain why equal label counts do not guarantee equal optimization outcomes.
Do not imply that transition-focused data or malonaldehyde ML potentials are new.

## 2. Methods (900–1100 words)

Define the original common36+24 allocations and fixed L12 settings; cite original
public methods. Define five matched 64-bit optimizer seeds and cap2000/cap8000.
Describe the 75-step preliminary stage and terminal refitting. State STEP_LIMIT for
all twenty endpoints; no converged-potential claim.

Describe the already fixed fourteen local transverse geometries, two known NEB
anchors, displacement0.075 Å and four physical blocks. Distinguish three ± pairs
from the singleton out-of-plane block. Report nearest-neighbor dependencies.

Report actual frozen QE7.5/PBE/PAW inputs,16 Å cell,Gamma,80/960Ry, exact unit
conversions and QC. Include interrupted T02m/recovery without erasing the failure.
Define the per-geometry27-component RMSE, within-block mean, equal four-block region
mean and primary paired Targeted−Basin contrast at8000 in the transition region.
Five initializations are not five allocation-policy realizations. No geometry-level
pseudoreplicated significance test; all secondary results labeled descriptive.

## 3. Results (800–1000 words)

3.1 Data integrity:14 accepted raw references,20 frozen predictions,280 independently
recomputed comparisons; source/public digests and coordinate serialization guard.
3.2 Primary: show all five signed contrasts, mean, median, four negative and one
positive. Do not replace this with a selected favorable seed or average alone.
3.3 Both budgets and regions: emphasize increased Basin transition error at8000,
near-constant Targeted transition error and the adverse basin tradeoff.
3.4 Physical directions: O–O contribution to the signed mean; correlated pairs and
singleton weighting. Show unfavorable directions and closest geometry labels.

## 4. Discussion (650–900 words)

Interpret conditional on the two fixed allocations, model family, caps and local
geometry design. Distinguish optimization effects from sampling-policy inference.
The old successful NEB pair and its3/5 joint-metric audit differ from PBE14's4/5
single-force endpoint. Local agreement with PBE does not establish experimental
accuracy, PES topology, tunneling or reactive MD. Train119 remains a separate
adaptive program with STATIC_APPLICABILITY_FAIL, not a third equal-budget branch.
Optional Observer paragraph may motivate terminal-model verification, but must keep
its single-seed, event/runtime-provenance limits and cannot become a validated fix.

## 5. Conclusions (150–220 words)

State the bounded numerical contrast and region/cap/seed dependence. Preserve negative
results. Do not make a universal Targeted superiority claim. New physical studies
are future work, not a prerequisite for drafting this scoped manuscript.

## Figure plan

Figure1: fixed allocation and fourteen real local test geometries/direction blocks.
Figure2: both caps and both regions; paired-seed context and all STEP_LIMIT statuses.
Figure3: all five signed primary PBE14 contrasts with fixed zero and uncut seed2.
Figure4: four directional block contrasts plus disclosed local-dependence boundary.
Table1:2×2×2 region/cap/branch mean scores from BUDGET_REGION_MEANS.tsv.

Figures must use the same verifier and versioned result tables as the site.
See ABSTRACT_EN.md, SUPPLEMENTARY_PLAN.md and CLAIM_DATA_MAP.tsv.

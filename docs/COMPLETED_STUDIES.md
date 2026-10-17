# Completed studies: fixed data, finite optimization, local off-path forces

The original v028 demonstration, its five-seed Audit21 audit, this later PBE14 study,
and the adaptive Train119 program are **different experiments**. None replaces another.
The original `3/5` describes simultaneous wins on two original NEB metrics; the new
`4/5` describes Targeted's lower transition-region force error on PBE14 at cap8000.

## What was held fixed

Two predetermined Train60 allocations contain common36 plus 24 branch-specific
geometries. Five paired initialization seeds and two main optimizer caps give 20
saved model endpoints. These are repeated optimizations, not five new allocations.
All 20 logs terminate at STEP_LIMIT; a larger cap is not a convergence certificate.
The 75-step preliminary stages and the first 2000 main printed values match within
each cap pair. The printed BFGS objective precedes terminal fitting and saving.

## Local geometric design

PBE14 has fourteen nine-atom geometries around two known NEB anchors: seven near
image1 (BASIN_LEFT) and seven near image5 (TRANSITION_CENTER). Four predetermined
transverse directions are O–O breathing, carbon skeletal bending, lateral hydrogen
motion and out-of-plane hydrogen motion. Three directions have ± displacements;
out-of-plane has only the + member. The maximum individual-atom displacement is
0.075 Å. Frozen positions and design records are deposited, not newly generated.

Absence of exact duplicates does not confer broad independence. The deposited
nearest-neighbor table includes the L04p proximity to Basin60 and later Train119
neighbors. This was a prespecified local comparison of already fixed models; it is
not global out-of-distribution testing. Later Observer changes reused PBE14 for
**development**. Blind12 is not included or opened.

## Electronic reference and history

The stored Quantum ESPRESSO PWSCF 7.5 inputs use PBE, a 16 Å cubic cell, Gamma-only
sampling, PAW pseudopotentials, 80/960 Ry cutoffs and the frozen SCF settings.
The raw total atomic force block is distinguished from later partial force terms.
The checker uses 13.605693122994 eV/Ry and 0.529177210903 Å/bohr. All fourteen
accepted force blocks are compared with their CFG labels. Predictions serialize
coordinates to six decimals; the frozen 1.1e-6 Å coordinate and 2.1e-6 Å pair-distance
guards are retained rather than falsely claiming byte-identical coordinates.

The original T02m job was interrupted with an empty output during a storage incident.
A separately authorized recovery on the same input produced the accepted label.
Nine original accepted references were imported unchanged. The dataset contains
fourteen accepted outputs, **not only fourteen total historical QE process launches**.
The recovery addendum and source/public mapping preserve this distinction.

## Predeclared primary endpoint

For each model and geometry, take sqrt(mean squared Cartesian force error) across
27 components. Average the existing ± members within each physical block. Average
four block values with equal weights within each region. Do **not** substitute a
pooled component RMSE. A singleton block still has one quarter of region weight.
The primary signed contrast is Targeted minus Basin in TRANSITION_CENTER at8000,
paired within each seed. Its mean is −0.1461353992591766 eV/Å, median
−0.1408393764958256, with four negative and one positive contrast.

Both regions and both budgets are shown. The larger transition advantage at8000
coexists with degradation of Basin and with a basin-region disadvantage for Targeted.
O–O breathing contributes about70.19% to the signed mean contrast for this design;
that decomposition is not proof of a universal physical cause. Five seeds and
correlated geometry blocks do not support a calibrated win probability or component-
level pseudoreplicated significance tests.

## Reproduce without scientific programs

```sh
python3 -B tools/verify_pbe14_offpath.py --out /path/to/new-output/pbe14
python3 -B tools/verify_optimizer_budget.py --out /path/to/new-output/budget
python3 -B -m unittest discover -s tests -p test_completed_studies.py
python3 -O -B -m unittest discover -s tests -p test_completed_studies.py
```

The independent standard-library implementation reads 14 reference CFG entries,
14 physical QE blocks and 20 saved prediction files; it derives all 280 errors,
160 blocks, 40 region/model scores and five primary contrasts. It also checks the
20 raw training logs and model identifiers shared across both studies. No evaluator,
selector, training or DFT executable is invoked. Exact frozen result numbers are
regression checks, not the arithmetic source.

## Relation to the remaining research

`SEED_SENSITIVE` and `STATIC_APPLICABILITY_FAIL` remain. Observer IX–XI-T provides
separate local optimizer diagnostics. Guard and END_MAIN are not new primary models
in this dataset. The missing XI-T-R event journal and short-process runtime snapshot
limit that optional diagnostic; neither invalidates nor upgrades this study's data.
No general MTP improvement, PES topology, tunneling rate or reactive MD is established.

See [study index](../data/studies/STUDY_INDEX.json), [publication scope](PUBLICATION_SCOPE.md)
and [data mapping](../data/studies/pbe14_mtp20_v001/SOURCE_TO_PUBLIC_MANIFEST.tsv).

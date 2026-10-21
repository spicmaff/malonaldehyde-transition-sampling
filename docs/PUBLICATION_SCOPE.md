# Publication scope and fixed evidence boundary

This extension is a small-data computational case study, not a new active-learning
algorithm or a deployment-ready reactive potential. The manuscript backbone is the
fixed-allocation, paired-seed, finite-budget comparison and the local off-path PBE14
benchmark. Negative results and geometry dependencies are part of the contribution.

The published exhibit includes that completed-study chapter. The current review
adds a separate optimization chapter: conditional representation algebra, one
source-reviewed refit diagnostic, a saved checkpoint comparison and historical
synthetic engineering qualification. It does not replace the original models or
change `SEED_SENSITIVE` and `STATIC_APPLICABILITY_FAIL`.
[Optimization methods](OPTIMIZATION_STORY.md)
· [Canonical aggregate payload](../data/optimization_story/v001/OPTIMIZATION_STORY.json).

## Closest prior work

Brezina, Beck and Marsalek, *Reducing the Cost of Neural Network Potential Generation
for Reactive Molecular Systems* (JCTC2023), DOI10.1021/acs.jctc.3c00391, studies
transition tube sampling, including malonaldehyde. Path-adjacent training is not our
new method. Schreiner et al., *Transition1x* (Scientific Data2022),
DOI10.1038/s41597-022-01870-w, supplies a broad reactive on/near-path dataset.
Cărare et al., *Global properties of the energy landscape: a testing and training
arena for machine learned potentials* (npj Computational Materials2026, online2025),
DOI10.1038/s41524-025-01878-x, evaluates landscape/network properties and spurious
minima. Our static local force observations do not establish those properties.
Publisher/author abstracts, method overviews and bibliographic metadata were checked;
no claim is made that every full paper or supplement was read exhaustively.

The defensible distinction is a precisely matched, limited MTP-L12 setup with five
optimizer initializations, two endpoint caps and fully inspectable local transverse
force comparisons. PBE is a computational reference, not experimental ground truth.
Q3 is a submission target, not an acceptance prediction or an endorsed journal rank.

## Data and code availability

Project-owned generated numerical data and derivatives are published under the
repository's LICENSE-DATA. New original verifiers/exporter/tests use its MIT license.
Owner-specific path prefixes are replaced by stable aliases; numerical tokens are
preserved. Each exported source has original and public SHA-256 and size, plus a
transformation record. The exact source/private filesystem is not required for the
lightweight reproducer. The exporter takes explicit paths and has no private fallback.

No MLIP source, executable, pseudopotential binary, private state dump, Blind12 data,
credentials or heavy QE scratch is added. The 20 models' hashes are provided; new
physical evaluation still requires a separately available licensed model/executable
setup. Saved outputs enable independent arithmetic, not complete new DFT or fitting.
Legacy licensing statements are not broadened to cover external software.

For the optimization chapter, the public numerical boundary is
[the five-file allowlist](../data/optimization_story/v001/PUBLICATION_ALLOWLIST.json).
The [claim map](../data/optimization_story/v001/CLAIM_DATA_MAP.tsv) gives exact
reviewed source fields, units, evidence classes and access tiers. Public source
URLs are pinned to a verified commit. Restricted audit-relative locators and
checksums identify private evidence; they are neither public downloads nor a
claim that its native experiments can be reproduced from this repository alone.
The original/public transformation records above describe the completed-study
source exports; the optimization payload instead contains explicitly selected
aggregate derivatives and their source identities.

Public readers can repeat the exported table arithmetic, including END/TERMINAL
PBE14 block and region means. TERMINAL's original PBE14 prediction vectors remain
missing, so its scores have a saved-table reaggregation tier. The historical XI
training journal and XI-T P1 runtime-snapshot failure also remain limitations.
The new missing-input recovery performed one real diagnostic training and six
detached physical replays; it is separate from historical synthetic T1 and does
not establish a better real-data COV optimizer. T2, DFT, MD and independent external
validation were not performed by that recovery. See
[the public/restricted boundary](PUBLIC_PRIVATE_BOUNDARY.md) and source IDs
`OBS_RECOVERY_LEDGER`, `OBS_XIT_GATE`, `OBS_XIT_PBE14` and `t1-gate` in the claim map.

## Release boundary

The fixed-budget and off-path work is already public. The additive optimization
chapter is prepared on a separate review branch for a draft pull request and
owner visual review. Its local preview does not imply that `#optimization` is
available on the production site. Existing release tags and CITATION.cff remain
the unchanged records of their releases. No new DOI, merge, release or Pages
production deployment is part of this preparation.

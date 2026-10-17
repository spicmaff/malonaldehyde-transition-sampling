# Publication scope and fixed evidence boundary

This extension is a small-data computational case study, not a new active-learning
algorithm or a deployment-ready reactive potential. The manuscript backbone is the
fixed-allocation, paired-seed, finite-budget comparison and the local off-path PBE14
benchmark. Negative results and geometry dependencies are part of the contribution.

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

## Release boundary

This work is prepared on a review branch. Existing release tags and CITATION.cff
remain unchanged until the owner approves a release. No DOI is invented and no
merge, release or Pages production deployment is authorized by this preparation.

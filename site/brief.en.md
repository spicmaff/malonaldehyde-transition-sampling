# One proton. Several tests of trust.

A machine-learned potential can fit one energy barrier closely and still leave important questions unanswered. This project follows those questions through proton transfer in malonaldehyde, a nine-atom molecule with two oxygen centers and a hydrogen atom that changes sides.

## What moves?

Not just the hydrogen. On the nine saved PBE NEB structures, the oxygen–oxygen separation contracts by about 4.37% from the left minimum to the central image, while the molecular framework changes. The viewer links those structures to their distances and reference energies. Smooth connecting frames are visual interpolation: NEB images are not equally spaced moments in a reaction.

## Where should the model learn?

Two original L12 moment tensor potentials used the same 60-configuration DFT budget. Thirty-six structures were shared; each branch added 24 according to a basin-focused or transition-focused placement strategy. The transition pool contained exactly 24 candidates and K was 24, so this was not an experiment in ranking a subset of a larger pool.

The targeted member of the original locked model pair was much more accurate on the saved PBE path. Its barrier error was 4.10 meV, versus 35.25 meV for the basin model. The central force-component RMSE likewise fell from about 0.1761 to 0.0787 eV/Å. These numbers are reproducible, but they describe a specific pair of trained models.

## Does the result survive repeated training?

Five paired seeds produced different outcomes. Targeted won both primary metrics in three pairs, one pair reversed both and one was mixed. The finding is SEED_SENSITIVE. The exhibit leaves all five pairs visible; it does not select the best run or imply a reliable probability of winning.

The reference path is also not a wholly independent holdout. Its two endpoint geometries overlap the common training data. Independently computing a reference and keeping every reference geometry out of training are different requirements.

## Does a coverage warning imply inaccurate forces?

Later adaptive development produced Train119. Five recorded Replay228 configurations exceeded its frozen coverage stop. The historical outcome remains STATIC_APPLICABILITY_FAIL.

A separate diagnosis compared the unchanged model with PBE on seven neighboring Crossing7 frames and four Challenge4 frames. All eleven local force-component RMSE values were below the inherited A2 = 0.09 eV/Å criterion. A warning about coverage therefore coexisted with small measured force errors at these selected geometries. That does not calibrate the warning globally, justify relaxing its threshold or establish safe reactive dynamics.

Train119 also matched the development Audit21 barrier within about 0.123 meV, while its largest relative-profile residual was about 0.504 meV. The residual plot explains why one excellent summary is not a uniform error bound. The force viewer goes further: each scalar RMSE can be inspected as actual PBE/MTP vector differences on the nine atoms.

## What does agreement with PBE mean?

PBE is an internal electronic-structure reference. High-level potential surfaces, nuclear quantum calculations and spectroscopy address other layers of the physical problem. Their results cannot be transferred to this model simply because its PBE error is small.

The conclusion is not that a good fit is unimportant. It is that accuracy, repeatability, independent evaluation, coverage and physical validation are distinct tests of trust. The site makes those tests visible without rewriting their outcomes.

Explore the full story and source-backed controls at https://spicmaff.github.io/malonaldehyde-transition-sampling/ . The exact project evidence and literature references are available in the site's Evidence section. No new DFT, training, selector calculation or dynamics was performed to create this presentation. Blind12 remains unrevealed.

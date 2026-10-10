# One Proton. Several Tests of Trust.

## 1. A small molecule with a large question

A convincing machine-learned potential is easy to illustrate: draw its energy curve over a reference curve and show that the two nearly coincide. The harder story begins with what the picture leaves out. Which configurations were used for training? Would a different initialization produce the same result? Does the model remain useful when atoms move away from the plotted path? And how accurate was the reference calculation in the first place?

This project approaches those questions through malonaldehyde, C₃H₄O₂. The molecule has only nine atoms, but its compact structure connects several difficult ideas: an intramolecular hydrogen bond, proton transfer, a changing heavy-atom framework, and the approximation of a many-coordinate energy surface using a limited set of electronic-structure calculations. Its small size makes the geometry readable. It does not make the validation problem trivial.

The original experiment compared two ways to place the same number of DFT-labelled configurations. One added examples near the molecular minima; the other added examples near the proton-transfer region. The preserved transition-focused model reproduced the selected PBE-path metrics much better. Subsequent tests made that result more specific, not less worth studying. Repeated training changed the ordering, reused geometries limited independence, and a later model passed local force-error checks while still failing its frozen coverage criterion.

**The subject of this exhibit is not a model that passed every test. It is the information gained by keeping different tests separate.**

@sources: methods randomness diagnostic

## 2. The proton moves, and the scaffold moves with it

In the saved geometries, the transferred hydrogen is H2*, between O1 and O8. The signed coordinate qPT is the distance O1–H2* minus the distance O8–H2*. Negative values place the proton closer to O1, positive values closer to O8. Near the central image the two distances are almost equal. Atom names identify the same atoms throughout; rotating the viewer never changes their identity.

The oxygen atoms are not fixed supports. Their separation decreases from 2.499240 Å at the left endpoint to 2.390122 Å at the central image, a contraction of about 4.37%. The carbon framework changes at the same time. The viewer makes these simultaneous changes visible rather than moving a hydrogen sphere between an artificially rigid pair of oxygens. These distances are recomputed from the actual saved Cartesian coordinates.

That observation has a precise scope. It describes the geometry along this PBE path. It does not, by itself, establish how much the contraction changes a tunneling splitting or a reaction rate. Nor do two useful descriptors, qPT and O–O distance, describe the whole molecular state. A nonlinear nine-atom molecule has 21 internal coordinates after overall translation and rotation are removed. A two-coordinate projection is a readable window into that space, not the space itself.

The solid rods and dashed O–H guides in the display are visual conventions. They are not calculated bond orders, an electron-density map, or proof that a chemical bond changes at a particular animation frame. The scientific content is in the coordinates, distances and saved energies.

@sources: path methods

## 3. A path is not a clock

The nine images come from a nudged elastic band calculation. NEB is a way to locate a path through an energy surface; climbing-image refinements help target a saddle point. Its images are configurations used in an optimization, not snapshots separated by a common physical time interval. A minimum-energy path also need not be the trajectory that a thermally moving molecule follows.

The exhibit offers two modes. In saved-image mode, the viewer moves between the nine actual numerical supports. In smooth mode, coordinates and displayed energies are interpolated between neighboring supports. The intervening structures have not received new PBE labels and the potential has not been evaluated on them. Distances displayed during interpolation are calculated from the displayed coordinates; the energy is an interpolation of the two saved energy values. The distinction remains visible next to the controls.

This is why the animation has a playback position rather than a reaction time. Its purpose is to preserve correspondence: the same H2*, the same oxygen pair, the same moving marker on the energy plot. It cannot measure how long proton transfer takes. It cannot demonstrate a tunneling trajectory. Pausing on an actual image returns the reader to a genuine data point.

The same boundary matters for the barrier. Here the reported value is the maximum of the nine saved energies minus the lower of the two endpoint energies. It is a discrete fixed-path quantity. A denser path, a different electronic method, a relaxed model-specific path, a free-energy calculation and a quantum spectrum would answer different questions.

@sources: path methods
@papers: neb2000

## 4. Spend the labels differently

Electronic-structure labels are the expensive ingredient in a learned potential. The original design held their configuration count constant. Both L12 Moment Tensor Potentials received 60 configurations: the same 36 common configurations and 24 branch-specific additions. The architecture and training settings were matched. The principal change was where those additional configurations were placed.

The sampling view uses the original configuration identities and coordinates. Shared points and branch-specific points retain their actual positions in the qPT–O–O projection. Revealing points is only a way to explain the composition of the sets; it is not a record of molecular dynamics or a depiction of the optimizer learning in real time.

Moment Tensor Potentials provide a symmetry-respecting representation of local atomic environments. The representation can be expanded systematically, but the existence of a flexible representation does not settle which finite data are sufficient for a particular fitted model. Active-learning methods based on D-optimality address a related selection problem in the model's representation space.

There is a consequential detail in this experiment: the transition candidate pool contained exactly 24 candidates and the requested selection size was also 24. All candidates entered the training set. Therefore, the result cannot show that MaxVol found the best 24 examples among a larger pool. **The tested contrast is spatial placement under an equal configuration budget.** Even that budget should not be silently reinterpreted as identical total computational cost, because preparation and subsequent analysis also consume work.

@sources: train_basin train_targeted methods
@papers: mtp2016 maxvol2017

## 5. The original result is real—and specific

On the preserved PBE path, Basin60 has an absolute lower-endpoint barrier error of approximately 35.2457 meV. Targeted60 has an error of approximately 4.1004 meV. The corresponding transition-force errors are approximately 0.176083 and 0.078685 eV/Å. The force metric combines Cartesian components from the three central images satisfying |qPT| ≤ 0.15 Å.

These are not values reconstructed from a screenshot. They can be recomputed from the published reference and prediction CFG files. The original models have not been replaced with a later, more favorable pair. The source identities and numerical definitions remain part of the record.

An energy-profile comparison nevertheless needs more than a visually impressive overlap. Each plotted series is referenced to its own lower endpoint. The residual panel then shows the signed difference between the relative model profile and the relative PBE profile. A barrier error is one functional of those nine values; it is not a bound on the discrepancy at every image. That difference becomes especially clear in the later Train119 comparison, where a very small barrier error coexists with a larger maximum profile residual.

For this original pair, placing the extra data toward the transition was associated with a much better fixed-path result. The natural next question is not whether those saved numbers exist. It is whether the advantage survives another realization of the same training procedure.

@sources: path basin targeted randomness

## 6. Five seeds change the strength of the claim

The original stochastic training did not record an explicit initialization seed. The model files and their predictions are preserved, but obtaining those exact model bytes by retraining is therefore not guaranteed. A later audit fixed five pairs of seeds and trained both branches for each pair using the locked data and settings. It did not select a winning seed for presentation.

Targeted was better on the barrier metric in four pairs and on the central-force metric in three. It was better on both simultaneously in three of five pairs. One pair favored Basin on both metrics; another had mixed ordering. The classification is SEED_SENSITIVE.

The paired plots keep all five results visible. During the introductory sequence, each pair is added without moving the earlier pairs or changing the axes. Afterwards, the reader can inspect an individual seed while retaining the full comparison. The 64-bit seed identities are stored as text so a browser's ordinary numeric representation does not silently round them.

Three wins in five pairs is a description of five prescribed comparisons. It is not a calibrated 60% success probability for an arbitrary future training run. With this small audit, adding a smooth distribution or confident uncertainty band would suggest a statistical result that has not been established.

The audit also had a procedural defect: evaluation was originally interleaved with training instead of waiting for all trainings to finish. A later evaluation-only repair used the same ten already-trained models after training was complete. Its prediction files were byte-identical to the historical ones. The repair confirmed the numerical result but did not erase the historical nonconformance. Reproducible numbers and a conforming sequence of operations are related, but distinct, requirements.

@sources: seeds randomness

## 7. Independence is a property of the data

The PBE path was computed separately from the MTP evaluations. That does not mean that every path geometry was absent from training. The two NEB endpoints overlap the common training set. The seven interior images were absent from both Train60 sets within the preserved geometric comparison. Consequently the whole nine-image path and Audit21 cannot be described as wholly independent holdouts.

The central-force metric uses three interior images and is not directly affected by those endpoint overlaps. The barrier uses endpoint energies, so its interpretation carries a different dependence. Keeping that distinction beside the result is more informative than either calling the entire audit independent or dismissing every number as meaningless.

The later Train119 history makes the issue broader. Replay228 was repeatedly used to identify coverage deficiencies and choose development additions. Challenge4 comprises frames 93–96, next to later training additions 97–100. Crossing7 contains seven neighboring configurations from another saved segment. Even when two CFG files are not exact duplicates, neighboring frames can be strongly related. Absence of an exact match is not evidence of independent sampling.

A strict ordered-distance threshold of 10⁻¹² Å found one endpoint match in an old Train119 review. The previously established geometric screen of 2.1 × 10⁻⁶ Å identifies both known endpoint correspondences. Both statements have well-defined meanings, but the first is not a complete description of training dependence. The site retains the historical record while displaying the relevant two-endpoint boundary. It does not claim that this ordered-atom screen exhausts all equivalent-atom permutations or every statistical dependency.

@sources: geometry roles corrections diagnostic

## 8. Coverage is not force error

The applicability question asks whether a configuration is represented adequately under a particular model-space criterion. A direct force-error question asks how the model's force vector differs from an electronic reference on that configuration. The latter requires reference information; the former need not contain that information at all.

In the frozen Train119 check, five of 228 saved configurations exceeded the fresh numerical stop, 1.0000012996964838. The crossing frames were 143–147. The historical result was STATIC_APPLICABILITY_FAIL, not a completed deployment validation. A separate output-precision guard also recorded a narrowly nonconforming serialization result.

The later bounded diagnosis retained the learned model. Seven new PBE single points were computed for Crossing7, frames 142–148, and four existing PBE references were reused for Challenge4, frames 93–96. All eleven local force-component RMSE values were below the inherited A2 threshold of 0.09 eV/Å. Their maxima were about 0.027965 and 0.029823 eV/Å for the two sets.

Those observations coexist without contradiction. Five recorded coverage crossings remained, while direct force errors on these selected configurations were small relative to A2. The animated comparison therefore uses two panels and two units. Gamma is dimensionless; RMSE is in eV/Å. The gamma panel explicitly shows its difference from the frozen stop, multiplied by one thousand, rather than hiding that narrow scale behind a dramatic unlabeled axis.

The result does not justify raising the stop retrospectively. It does not establish a universal relation between gamma and force error. More generally, simulation benchmarks in the ML-force-field literature motivate examining stability and downstream observables separately from pointwise errors. They do not establish a new dynamics verdict for Train119, which was not given an independent deployment test here.

There are other ways to construct a warning signal. Bayesian force models and committee potentials estimate uncertainty using different assumptions, and resampling-based approaches explicitly consider calibration and correlations between models. The existence of those methods does not license adding uncertainty bands to the present plots. Our five paired seeds were a robustness audit, not a validated uncertainty model; our local diagnostic frames were adaptively selected, not a representative prospective test.

@sources: diagnostic train119 continuation
@papers: maxvol2017 fu2022 bayes2020 committee2020 musil2019

## 9. Look inside the scalar

Each nine-atom configuration has 27 Cartesian force components. The displayed RMSE is the square root of the mean of their squared errors. It is not the largest component error and not the error magnitude on one chosen atom. On Challenge4, some individual component errors slightly exceed 0.09 eV/Å without violating a 0.09 eV/Å RMSE criterion.

The force viewer makes that distinction inspectable. For every one of the eleven frames, it reads the PBE force from the official Quantum ESPRESSO output block, checks it against the XML result, and pairs it with the preserved MTP output on the matching geometry. The difference vector is MTP minus PBE. The selected atom's vector magnitude and the whole-frame RMSE are shown separately.

The camera rotates the atomic geometry and all force arrows together. The numeric component table remains in the original laboratory axes. A common declared arrow scale preserves relative magnitudes; normalizing each arrow independently would erase precisely the information the viewer is intended to explain. These arrows are not atomic displacements or a trajectory generated by integrating the forces.

Atom identity also matters. H2* is the transferred proton. C3/y is a different component involved in an old selector annotation. The original execution scalar was mislabeled, while a later correction separated the two quantities. That correction affects interpretation of the annotation, not the full force arrays or their primary RMSE.

@sources: geometry_crossing7 prediction_crossing7 geometry_challenge4 prediction_challenge4 corrections

## 10. A reference is another model

A small MTP-to-PBE error establishes agreement with the selected electronic approximation, not automatically with experiment. PBE is a defined density-functional approximation. A comparison with a different electronic method needs matched definitions and careful attention to geometries, basis or plane-wave settings, and whether relaxation and zero-point contributions are included.

For context, Wang and colleagues constructed a high-level malonaldehyde surface and reported an electronic barrier around 4.1 kcal/mol, alongside full-dimensional nuclear calculations. That barrier should not be subtracted from our discrete PBE result and presented as an exact error for our implementation: the calculations are not a controlled matched-geometry comparison. The literature nevertheless makes clear why the electronic-reference layer deserves its own scrutiny.

The placement of expensive labels is also important beyond this project. Käser, Richardson and Meuwly used selected CCSD(T) information near an instanton path to improve a surface already trained at MP2 level. The much-cited 25–50 additional high-level configurations are not a complete training-from-scratch budget. Their study illustrates a useful strategy, but it is not a direct contest against either Train60 or Train119.

@sources: methods diagnostic
The broader density-functional literature discusses delocalization and static-correlation errors. Those concepts motivate scrutiny of a reference approximation; they are not a diagnosis of the numerical origin of this particular barrier. Establishing that origin would require a controlled electronic-structure comparison rather than a visually persuasive juxtaposition of unrelated published numbers.

@papers: pbe1996 wang2008 kaser2022 dftlimits2008

## 11. Quantum motion needs its own evidence

A tunneling splitting is a property of a nuclear quantum problem on a specified potential surface. It is not the height of an electronic energy curve. Replacing H by D changes the nuclear mass, and therefore the nuclear calculation, even when the underlying electronic Born–Oppenheimer surface is kept fixed. A convincing spectral prediction requires more than animating a proton through the center of the path.

Recent work reinforces that distinction. Baumann, Trenins and Richardson used symmetrized path-integral molecular dynamics to isolate the ground rotational state on a specified surface, reporting 21.1 ± 0.1 cm⁻¹ and identifying contributions from higher rotational states in earlier comparisons. The observable and state projection matter alongside the potential.

At the same time, one dimension is not automatically disqualifying. Qu and colleagues tested a rectilinear Qim reaction-path Hamiltonian for H/D transfer and demonstrated useful accuracy in its stated domain. Their work emphasizes the coordinate and kinetic operator, and discusses limitations such as corner-cutting. It does not validate every one-dimensional interpolation of an energy curve.

The older H/D calculation in this repository is retained as a declared frozen-path spectral diagnostic. In its primary targeted-H case, the first excited level lies above that model's barrier; the gap is not a reproduced pair of two subbarrier levels. A stronger physical interpretation would require separate justification of the Hamiltonian and convergence, not a more cinematic picture. This exhibit deliberately does not draw a quantum wavepacket or probability current that was never calculated.

@sources: limits corrections
@papers: baumann2026 qu2026

## 12. What remains after the attractive plot

The outcome is not a single verdict on an entire class of machine-learned potentials. It is a set of preserved observations with explicit boundaries. The original frozen pair favors transition-focused placement on two fixed-path metrics. Repeated training qualifies that interpretation. Known overlaps qualify independence. The later Train119 diagnosis separates a failed coverage criterion from small force errors on selected local configurations.

Animation can help make those distinctions legible. It can hold the same atom in view while coordinates change, reveal paired results without changing their identity, or move a cursor across two different diagnostic panels. Visualization research also warns against treating motion as an automatic improvement to analytical comparison. Here every sequence can be stopped, every final plot remains available, and the numerical tables and essay remain readable without JavaScript.

The final test is whether the reader can follow a number backwards: from a claim to its definition, from the definition to a source file, from the file to a reconstruction, and from the reconstruction to the limit of the conclusion. Source hashes, immutable links and the unchanged scientific verifier make that route practical. They do not turn selected development data into an independent experiment.

**A small error can be an important result without being the final answer.** The next stronger claim—independent deployment, a calibrated warning rule, or quantitative experimental proton-transfer physics—would need its own study. Keeping that future work separate is part of what makes the present evidence useful.

@sources: science diagnostic randomness
@papers: animation2007 trends2008 molstories2026

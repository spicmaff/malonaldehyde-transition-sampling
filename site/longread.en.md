# One proton. Several tests of trust.

A potential can reproduce an energy barrier beautifully and still leave the most important question open: when should we trust it? In malonaldehyde, that question begins with nine atoms, two oxygen centers and a hydrogen atom that changes sides. It ends with a distinction between several kinds of evidence that are too easily compressed into a single error score.

This is the story of a small computational experiment with a limited first-principles data budget. Two original moment tensor potentials learned from different placements of the same number of labelled structures. One saved model was much better on the reference reaction path. Repeated training made that conclusion less universal. Later coverage tests stopped an adaptively developed model, even though direct PBE comparisons found small force errors on the selected local structures. None of these observations cancels the others.

The exhibit has two modes. The guided scenes introduce the questions through motion. The exact-image controls, numerical tables and source panels then let you stop the story and inspect the evidence. Animation time is never presented as chemical time.

## 1. The bridge moves with the hydrogen

The hydrogen-transfer geometry of malonaldehyde is not a particle traveling through a rigid molecular tunnel. Both oxygen centers and the carbon framework change as the transferred hydrogen moves. The difference between its two oxygen–hydrogen distances, qPT = r(O1–H2) − r(O8–H2), is a useful label for the two sides of the path. It is not a complete description of the molecule.

A nonlinear nine-atom molecule has 3 × 9 − 6 = 21 internal degrees of freedom. Many distinct structures can share one value of qPT. Oxygen separation, bending and out-of-plane motions can change while that coordinate stays similar. Full-dimensional studies of hydrogen transfer examine coupled vibrational motion explicitly; the present path inspection does not perform that mode analysis. [S06]

The nine stored PBE NEB images nevertheless reveal a clear geometric relationship. The O1–O8 distance falls from 2.499240 Å at the left endpoint to 2.390122 Å at the central image: a contraction of approximately 4.37%. It then increases toward 2.499058 Å at the right endpoint. These are distances reconstructed from the saved coordinates, not values chosen to make the animation more dramatic.

The molecular scene uses a uniform three-dimensional projection and keeps atom identity fixed as the camera turns. Optional ghost geometry shows the left-minimum framework for comparison. The camera and lighting explain spatial relationships; neither is part of the scientific model. Dashed oxygen–hydrogen contacts are distance guides, not a calculated bond-order field.

What does the contraction establish? That these geometric changes occur together along this saved PBE path. It does not quantify their influence on a tunneling splitting or prove a rate-enhancement mechanism. Those stronger questions require a nuclear-dynamics calculation and a suitable potential-energy surface.

@sources: path

## 2. A path is not a molecular movie

The nudged elastic band method constructs a path between specified configurations. Its climbing-image variant is designed to locate the saddle region of a minimum-energy path. The index of an image is not a time coordinate, and its spacing does not encode how long a molecule spends there. [S19]

That distinction matters most when the pictures look convincing. We have nine computed structures, not a validated real-time sequence of a reactive molecule. Between them, the scene can interpolate coordinates for display. The connected energy marker is interpolated from the stored energy samples. Neither the intermediate geometry nor its displayed energy is a new DFT calculation.

The interface therefore offers two complementary ways to look. The smooth scene shows the overall geometric change. The saved-image buttons return to the nine actual calculation anchors. Labels distinguish those states. No clock is labeled in femtoseconds, no kinetic rate is inferred from playback, and a smooth loop does not imply repeated physical reactions.

A tunneling pathway is another distinct concept. Semiclassical instanton theory searches for a path relevant to quantum transfer; it should not be identified automatically with our PBE NEB path. An example combining instantons and transfer learning illustrates how choosing structures around that path can be efficient for its particular quantum observable. [S07]

@sources: path methods

## 3. What the model is being asked to learn

A moment tensor potential represents atomic interactions through an invariant model family. Its systematic construction provides a way to approximate a chosen quantum interaction model; it does not promise that any finite training set produces an adequate potential everywhere. [S12]

For this project the electronic reference is PBE. The model learns labelled energies and forces associated with particular geometries. Forces are not decorative arrows added after fitting: for an energy-conserving potential, they describe derivatives of the energy with respect to atomic positions. A small energy error at a few geometries does not guarantee equally small derivative errors in every direction.

There are therefore two immediate questions. Where should the labelled configurations be placed? And how should the trained model be tested? The recent reactive-MLIP literature emphasizes both model architecture and data acquisition. Our experiment isolates a much narrower question inside that broad field: spatial allocation under the same configuration budget. [S21]

D-optimality-based active learning provides a principled method for selecting informative equations or configurations in model space. But the presence of an active-learning routine in a workflow does not by itself establish that competitive selection was the experimental variable. The candidate pool and selection budget determine what was actually tested. [S13]

@sources: methods train_basin train_targeted

## 4. Thirty-six shared. Twenty-four different.

Both original L12 MTPs used 60 DFT-labelled configurations. Thirty-six configurations were common to the two branches. The remaining 24 were placed according to the basin-focused or transition-focused strategy. Architecture, training settings and total configuration count were matched.

The learning visualization reconstructs the configuration identities and projects their actual coordinates into qPT and oxygen separation. Shared structures appear first; the two sets of additions then reveal where the branches differ. The projection is an inspection device. It is not the full descriptor space, a probability distribution or a trajectory through training examples.

One detail limits the claim. The transition candidate pool contained exactly 24 configurations, and the selection budget K was also 24. All candidates entered training. The comparison therefore cannot demonstrate that MaxVol found the best 24 structures out of a larger collection. It demonstrates the consequence of two different placements of a fixed number of labels in this particular experiment.

Equal data count also does not imply identical end-to-end computational expense. Subsequent debugging, repeat training and adaptive experiments consumed additional work. Train119 belongs to that later development history, not to a third arm of the original 60-configuration comparison.

@sources: train_basin train_targeted methods

## 5. The first result was real—and specific

For the original locked model pair, the difference was large. Basin60 predicted a nine-image barrier of about 0.826 meV against the saved PBE value of 36.072 meV. Targeted60 predicted approximately 31.972 meV. The resulting absolute barrier errors were 35.2457 and 4.1004 meV, respectively.

The central force-component RMSE told a similar story: approximately 0.176083 eV/Å for Basin60 and 0.078685 eV/Å for Targeted60. That metric pools the Cartesian force components of the three saved images satisfying |qPT| ≤ 0.15 Å. It is not the maximum force error on any one atom.

The energy comparison uses a precise convention. Each series is shifted by its own lower endpoint, and its discrete barrier is max(Ei) − min(E1,E9). This is an electronic-energy difference on nine images. It is not a free-energy barrier, a zero-point-corrected barrier or an experimentally determined activation energy.

The reference path was computed separately from MTP evaluation, but independent computation and independent holdout data are different ideas. Its two endpoint geometries overlap the common training set. The seven interior images were absent from the original training sets in the frozen geometry audit. Consequently, the central force metric is not affected by the endpoint overlaps, but the whole NEB9 path and Audit21 cannot be called fully independent holdouts.

Nothing in the later analysis replaces these original models. Their bytes, predictions and repaired v030r metric definitions remain available. The correct conclusion is strong but specific: the targeted member of this saved model pair better reproduces these selected PBE-path characteristics.

@sources: path basin targeted methods geometry

## 6. Repeating training changes the strength of the claim

The original training did not record an explicit random seed. Preserving its model bytes makes the prediction arithmetic reproducible; it does not make the exact original training reproducible from a seed that was never recorded.

A later audit fixed five paired 64-bit seeds and retrained both branches for each pair. The same architecture, datasets and prescribed settings were retained. There was no best-seed selection, additional DFT labeling or retry scheme designed to produce a favorable pair.

Targeted had the smaller barrier error in four pairs, the smaller central force RMSE in three, and both smaller errors together in three. One pair favored Basin on both metrics. Another produced a mixed ordering. The resulting classification is SEED_SENSITIVE.

Five outcomes are enough to show that the direction of the original comparison is not invariant across these tested training initializations. They are not enough to justify an empirical probability that a future targeted model will win, or an unqualified causal estimate of sampling advantage. The visualization accordingly reveals all five pairs and then leaves them visible for direct comparison. It does not invent posterior samples or confidence bands.

The audit also had a procedural nonconformance: evaluations were initially interleaved with training, rather than delayed until all trainings had finished. A later evaluation-only repair used the same ten already-trained models after all existed. The ten prediction files were byte-identical to the historical outputs. That repair confirms the saved arithmetic without pretending that the initial execution order was compliant.

@sources: seeds randomness

## 7. Coverage asks a different question

During molecular motion, the model can encounter directions that were barely tested by the static path. A coverage diagnostic is intended to flag this possibility. In the project, MaxVol gamma belongs to a particular active equation space and its specified numerical stopping rule. It is not a force error in disguise.

A gamma value has no eV/Å unit. A force error does. To know the latter at a particular configuration, one needs a reference force calculation and a verified mapping between the same atoms in the same geometry. No geometric warning can supply those reference numbers on its own.

Independent benchmark research likewise distinguishes force prediction error from simulation quality and stability. That broader result motivates testing more than one metric, but it does not itself prove that our particular model will fail or succeed in a future trajectory. [S18]

The original first-update diagnostic captured six attempted unconstrained updates across three temperatures and two minima. Later exact replay confirmed that the saved updated configurations exceeded the historical applicability threshold. That evidence did not contain a usable free trajectory or direct DFT force errors for those six original frames. It is important not to borrow force-error conclusions from later models and place them onto those early configurations.

The interface uses separate, consistently scaled panels for coverage and local force error. It also treats Replay228 as an archive assembled from development configurations, not one continuous physical clock. A line should not connect unrelated trajectory segments merely because they occupy adjacent rows in a file.

@sources: replay continuation science

## 8. Train119: two verdicts on selected configurations

The continuation program adaptively developed Train109, Train112, Train115 and Train119. Replay228 was repeatedly used to identify gaps and choose remediation configurations. It is a development benchmark, not an untouched final test.

The frozen Train119 check produced a fresh numerical stop of 1.0000012996964838. Five saved configurations, archive indices 143–147, exceeded it. A separate narrow serialization nonconformance was retained rather than repaired by weakening the tolerance. The historical outcome is STATIC_APPLICABILITY_FAIL.

The later local PBE diagnosis asked a different question using the unchanged model. Crossing7 comprised saved frames 142–148 from a right-minimum Train109 segment; it included the five coverage crossings and their neighbors. Seven PBE single points were calculated in the October 5 diagnostic. Challenge4 reused four existing PBE references at indices 93–96 from another saved segment, adjacent to the later training additions 97–100.

All eleven local configurations had a force-component RMSE below the inherited A2 = 0.09 eV/Å criterion. The maximum was approximately 0.027965 on Crossing7 and 0.029823 on Challenge4. These observations show that a recorded coverage rejection can coexist with a small local PBE force error. They do not calibrate gamma globally or authorize an increase in the frozen stop.

The same model was also examined on development Audit21. Its barrier error was approximately 0.122996 meV and its central force RMSE 0.013834 eV/Å. Yet the largest relative-profile residual was about 0.504 meV. Good agreement of the maximum is not a uniform error bound on every image, which is why the site exposes the residual plot beside the profile.

Both known endpoint geometries overlap Train119 under the established comparison tolerance. Neighboring trajectory frames remain correlated even without exact duplicates. No new Train119 Gate1, validated reactive MD or prospective independent generalization result follows from these local successes.

@sources: diagnostic train119_manifest corrections geometry roles

## 9. Look inside the force error

A scalar RMSE aggregates 27 Cartesian differences in a nine-atom configuration. It can be a useful summary without telling the entire local story. Which atom carries a difference? Does it point along the transferred hydrogen coordinate or another direction? How does the vector magnitude relate to a single Cartesian component?

The force inspector reconstructs PBE forces from the official total-force block of each saved Quantum ESPRESSO output, cross-checks the corresponding XML and compares them with the stored MTP predictions. It does not read a partial contribution block as a total force, and it does not calculate new model predictions.

The selected atom’s vectors and geometry undergo the same rigid camera transformation. Numerical components remain in the original source frame. Consequently, a projected arrow can shorten as the view rotates while the true three-dimensional magnitude stays unchanged. Arrow magnification is an explicit display setting, not a physical displacement.

The transferred proton is H2, zero-based atom index 1. C3 is zero-based index 2. An old scalar field confused these labels; the full saved force arrays did not become identical because of that annotation. The new inspector names both unambiguously.

Some individual Challenge4 component errors exceed 0.09 eV/Å while the configuration RMSE remains below that number. This does not violate the inherited A2 rule: that rule bounds the configuration-level RMSE, not every component. Understanding what a threshold actually constrains is part of understanding the result.

@sources: train119_manifest corrections

## 10. What is the reference a reference for?

PBE is a defined approximation to electronic exchange and correlation, not experimental ground truth. General analyses identify delocalization and static-correlation errors among important limits of density-functional approximations. Those mechanisms provide context; without controlled comparisons they do not diagnose the cause of this project’s particular barrier. [S10] [S11]

High-level malonaldehyde potential-energy surfaces supply a useful contrast. Wang and coauthors reported a 4.1 kcal/mol saddle barrier on a full-dimensional surface fitted to near-basis-limit CCSD(T) energies. That value belongs to their surface and protocol. It is not a matched-geometry measurement of the error of our approximately 0.832 kcal/mol discrete PBE barrier. [S04]

Even an excellent electronic surface does not finish the nuclear problem. A full-dimensional coupled-cluster-oriented surface and diffusion Monte Carlo calculations have been used to study both hydrogen and deuterium transfer. Their comparison with spectroscopy connects a specified potential, a nuclear solution and an observed splitting—not simply one point at the top of a curve. [S01] [S05]

A more recent symmetrized path-integral study isolates the ground rotational state and reports 21.1 ± 0.1 cm⁻¹ on its chosen surface. It resolves discrepancies associated with rotational contributions in earlier path-integral treatments. The precision of that nuclear calculation must not be transferred to an untested electronic surface. [S08]

Nor should every one-dimensional reduction be dismissed automatically. Tests of the Qim reaction-path Hamiltonian emphasize the coordinate and kinetic operator that define a reduced model. Our existing frozen-path H/D calculation is a distinct effective spectral diagnostic; it has not acquired validation merely because another reduced model performs well. In its primary targeted-H result the first excited level lies above that model’s barrier, so a level gap alone is not evidence of a reproduced subbarrier doublet. [S09]

This is where the different tests of trust come together. The fit to a reference, robustness to training, independence of evaluation, coverage during use, accuracy of the electronic approximation and treatment of nuclear motion each establish something different. A small error at one level cannot serve as a certificate for the others.

The point of this exhibit is not to rescue a universal success claim. It is to preserve a genuinely interesting original result, show how later tests changed its interpretation, and make every step inspectable. The scientific artifacts remain frozen. The animation is new; the evidence is not.

@sources: limits methods diagnostic science quantum

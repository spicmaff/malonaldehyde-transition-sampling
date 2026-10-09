# Where should twenty-four DFT points go?

## 1. A small molecule, a large question

A machine potential can produce a convincing energy curve and still leave an important question unanswered: can it be trusted away from the configurations that made that curve look good? Malonaldehyde makes that question unusually tangible. There are only nine atoms. One hydrogen can move from the vicinity of one oxygen to the other. The chemical event is small enough to inspect, but the demands it places on a learned potential are not confined to a single number.

This project began with a question about the placement of expensive reference data. Two Moment Tensor Potentials received the same number of DFT-labelled configurations. One received extra examples near the stable minima; the other received them in the transition region. The original saved pair gave a striking difference. Subsequent checks made the conclusion narrower, more complicated and more informative.

This is the story of that narrowing. It does not end with a universal claim that one sampling strategy works best, or with a model declared ready for reactive dynamics. It ends with a set of reproducible observations, a demonstrated sensitivity to training initialization, and a local diagnosis of an applicability failure. The distinction between these outcomes is the main result of the story.

The molecular viewer shows nine saved PBE nudged-elastic-band geometries. The proton-transfer coordinate qPT is the distance from the transferred hydrogen to O₁ minus its distance to O₂. Negative and positive values distinguish the two sides. Near zero, the two O–H distances are similar. The other atoms also move along the path: this is not a hydrogen sliding through an otherwise rigid drawing.

The maximum of the saved PBE energy profile is about 36.072 meV above its lower endpoint. Throughout this exhibit, PBE is an internal computational reference. Reproducing that particular electronic-structure approximation is not equivalent to reproducing the experimental barrier or all nuclear quantum effects. The smoothly moving molecule is a display of the saved path, not a molecular-dynamics trajectory. Its animation clock has no physical interpretation.

@sources: path methods limits

## 2. Equal budgets do not make every comparison equal

Each original model used 60 DFT configurations: 36 shared examples and 24 strategy-specific additions. The MTP architecture, L12, and the training settings were held fixed. The intended contrast was spatial: additional basin configurations versus additional transition-region configurations. The interactive projection displays actual training geometries through qPT and the O–O distance. It is a two-dimensional projection, not a statement that those two coordinates completely describe the molecule.

A consequential limitation appeared in the selection procedure. The transition candidate pool contained exactly 24 configurations, and the requested selection size K was also 24. Every candidate entered training. MaxVol was present in the workflow, but this experiment did not test its ability to choose a smaller, better subset from a larger pool. The supported comparison concerns where the extra examples were placed, not the superiority of a competitive ranking algorithm.

There is another boundary in the phrase “equal budget.” The comparison fixes the number of labelled configurations and the relevant model settings. It does not establish equality of every computational cost incurred in preparing geometries, training models, auditing results or pursuing the later development programme. Once the story reaches Train119, it has left the original 60-versus-60 experiment altogether.

@sources: train_basin train_targeted methods

## 3. The saved pair tells a striking story

The original MTPs were evaluated on the same saved nine-image PBE path. The repaired primary analysis uses a precise barrier definition: the maximum of the nine energies minus the lower of the two endpoint energies. Each model has its own endpoint reference. This matters when interpreting both the shape of the plotted curve and the reported error.

For the saved Basin60 model, the absolute barrier error is 35.245734 meV. For Targeted60 it is 4.100394 meV. Their central transition force-component RMSE values are approximately 0.176083 and 0.078685 eV/Å. The force metric combines the Cartesian components on the three images satisfying |qPT| ≤ 0.15 Å. It is not a maximum-component error and not an average over the entire Audit21 set.

In this fixed comparison, the transition-focused model is substantially closer to PBE on both selected transition metrics. The curves show why the result attracted attention: the basin model largely misses the reference barrier, whereas the targeted model follows its shape more closely. This is a useful observation about these two models, and their original coefficients and predictions remain available.

The saved numerical arrays make the observation reproducible without rerunning DFT or invoking a model. They do not, by themselves, make the training procedure reproducible down to the identical model. Those are different achievements. A later model with a better-looking curve was not substituted for the original pair; later evidence changes the strength of the interpretation, not the identity of the original result.

@sources: path basin targeted methods

## 4. “Independently calculated” is not “held out”

The PBE path was calculated separately from the MTP evaluations. That does not mean every geometry on that path was absent from training. The geometry audit identifies both NEB endpoints in the shared common36 set. Within the frozen geometry screen, the seven interior images were absent from both original Train60 sets.

The distinction is easy to lose in a figure caption. The reference calculation can be independent as a computational procedure while the test set still shares configurations with training. The whole NEB9 path and Audit21 as a whole should therefore not be described as fully independent holdouts. The central force metric uses interior images, so those two endpoint overlaps do not directly enter its force average. The barrier metric does use endpoint energies.

The appropriate response is neither to discard every number nor to ignore the overlap. It is to state the role of each subset and the scope of each metric. This becomes even more important later: a benchmark repeatedly consulted during adaptive development is no longer an untouched final test merely because the final evaluator has a new filename or a fresh model.

@sources: path methods limits geometry

## 5. Five initializations change the strength of the conclusion

The original stochastic training did not record an explicit random seed. The model bytes survived, but one realization per strategy cannot separate the influence of data placement from optimization sensitivity. A later audit therefore fixed five paired 64-bit seeds, then retrained the original basin and targeted datasets from the same locked untrained template under the prescribed settings.

There were ten trainings, with no extra attempts, warm starts, hyperparameter search or best-seed selection. Targeted performed better on the barrier in four of the five pairs, on transition forces in three, and on both metrics simultaneously in three. One pair reversed both comparisons; another split the result between the two metrics. The site shows every pair rather than selecting the most persuasive example.

The classification is SEED_SENSITIVE. Five pairs are enough to exhibit that sensitivity in these runs, but they are not a universal estimate of the chance that targeted sampling will win a future training. The original advantage remains a property of the saved model pair, not a seed-robust causal estimate of the sampling strategy.

This audit also had a procedural defect: evaluations were interleaved with training, although the protocol required all ten trainings to finish first. A later evaluation-only repair used the same ten already-trained models after all trainings existed. Every resulting prediction CFG was byte-identical to its historical counterpart, and the recomputed metrics agreed. The repair confirms the saved arithmetic; it does not erase the earlier order nonconformance or transform the small seed audit into a broader experiment.

@sources: seeds randomness science

## 6. A good path is not permission to run dynamics

The next question concerned attempted motion away from a minimum. Six first attempted unconstrained integration updates were captured for the original targeted model: 100, 300 and 500 K, from both minima. Later exact source-oracle replay established that all six updated geometries exceeded the historical MaxVol applicability threshold.

That is evidence of early applicability rejection. It is not a usable free trajectory, and those six original frames were not accompanied by a DFT force-error measurement in that diagnostic. The statements “the selector rejected this geometry” and “the forces are inaccurate here” require different evidence.

The distinction motivated a separate transition-tube development programme. Frozen protocols were followed by execution, review and interpretation, with failures generating new diagnostic questions. This history is adaptive development, not one uninterrupted confirmatory experiment. Changes in models, selector equations and test roles must remain visible rather than being compressed into “more data eventually solved it.”

A static path explores only a limited set of geometric changes. Dynamics can encounter other directions. Conversely, rejecting a direction in the selector's active-equation space need not imply a large force error at that exact point. Both observations can be true without establishing that the model is safe for arbitrary future motion.

@sources: continuation methods limits

## 7. What does gamma actually measure?

MaxVol gamma is an algebraic applicability diagnostic relative to a particular active basis and query construction. Its numerical value depends on that construction. A force RMSE, in contrast, compares reference and predicted Cartesian forces on a specified geometry. One is dimensionless; the other carries force units. Plotting both does not make them two interchangeable scales of confidence.

The later programme examined energy-only and force-aware selector behaviour and compared local force errors with saved grades. The repository records that a calibration over 22 labelled development frames did not support a universal scalar mapping from gamma to force error. This exhibit treats that as local descriptive evidence, not an inferred law across configurations and temperatures.

The frozen stopping rule remains a rule even when a subsequent local force check is reassuring. A defensible interpretation keeps three questions apart: was the prescribed criterion exceeded, were forces measured accurately in the selected neighborhood, and has safe deployment been established? A yes to the second question does not automatically reverse the first or answer the third.

The Replay228 view uses the already saved Train119 scores. No selector is reconstructed in the browser. Its horizontal coordinate is an archive index; the collection should not be mistaken for a single continuous physical time series. Zooming into five threshold crossings changes the view, not the threshold or the science.

@sources: continuation replay science

## 8. Train119: a failed gate and an informative local diagnosis

Train119 followed Train109, Train112 and Train115 in the adaptive programme. Replay228 had already been used to locate coverage deficiencies and choose remediation configurations. The final frozen Stage91J evaluation constructed a fresh force-aware selector, derived a numerical stop and graded that replay set. Five frames, indices 143–147, exceeded 1.0000012996964838.

The saved Validation11 force errors were below A2 = 0.09 eV/Å, but Validation11 had known training dependencies. An output-serialization guard also failed narrowly. These are distinct observations. The historical outcome remains STATIC_APPLICABILITY_FAIL; no Train119 Gate1 promotion, longer validated deployment run or Blind12 reveal followed.

A separate diagnostic completed on October 5 investigated the physical meaning of the local rejection without retraining Train119. Crossing7 contains replay frames 142–148: five saved crossings with one neighboring frame on either side. Seven PBE single-point calculations were made for these geometries. Challenge4 reuses four older PBE references for replay frames 93–96. The learned model was unchanged.

All eleven local configurations satisfy the inherited per-configuration 27-component force RMSE criterion. The largest error is about 0.027965 eV/Å for Crossing7 and 0.029823 eV/Å for Challenge4. Some individual Challenge4 force components have errors slightly above 0.09 eV/Å; that does not violate a criterion defined on RMSE. It does demonstrate why the metric must be named precisely.

These are not eleven independent trials. Crossing7 comprises neighboring configurations from one saved 100 K trajectory segment. Challenge4 is adjacent to replay frames 97–100 that later entered training. The results establish local PBE-relative accuracy on selected development geometries. They do not establish a universal gamma calibration or justify increasing the frozen stop.

A separate saved-data Audit21 evaluation is numerically even closer to PBE: the discrete lower-endpoint barrier error is about 0.123 meV and the central force RMSE about 0.013834 eV/Å. Yet both endpoints overlap training, and Train119 is an adaptively developed, larger model. This is not a third equal-budget branch. Nor does the barrier error bound the error everywhere on the profile: after each series is referenced to its own lower endpoint, the maximum profile error is about 0.504 meV.

@sources: diagnostic train119 train119_prediction roles geometry

## 9. Precision and provenance are part of the result

The late diagnostic required an output-only change in a separate MLIP executable: write the CFG using its lossless-output option. The purpose was to retain numerical precision in serialization, not to change model coefficients, descriptors or predicted forces. Its qualification evidence is preserved separately from the historical failure.

The reporting layer also needed correction. Zero-based atom index 2 is C3; the transferred proton H2 has index 1. An older scalar label confused these roles. Corrected tables distinguish proton H2/y from the historical C3/y crossing component. The raw force arrays and primary RMSE are not replaced by an annotation fix.

The endpoint audit illustrates another precision trap. A strict 10⁻¹² Å ordered-distance test reports one match, but the second known endpoint differs by only about 8.64 × 10⁻¹¹ Å in its pair distances and is included by the previously used 2.1 × 10⁻⁶ Å geometry screen. For the right endpoint, a small rigid rotation must also be applied to the forces before comparing components. A count tied to an extremely strict threshold is not a complete account of data dependence.

Historical training_eligible=false fields on some appended configurations describe an earlier role. Later stage-specific contracts determine their authorized training membership. The frozen bytes should not be silently cleaned up to tell a simpler story. An external provenance table explains the change of role while preserving the original input.

Hashes and tests help protect these distinctions, but a passing check is not a scientific conclusion by itself. The important chain is source, geometry and model identity, numerical operation, resulting quantity, and finally the limits of the claim made about it.

@sources: corrections roles geometry train119_manifest

## 10. What remains after the headline gets smaller

The original saved pair supports a clear numerical observation about transition-focused placement. The five-seed audit shows that the ordering is sensitive to initialization. The late Train119 study demonstrates small local force errors even in a selected neighborhood rejected by its frozen applicability rule. None of these findings needs to be hidden to preserve the others.

The one-dimensional H/D spectral appendix has a similarly bounded role. It is a calculation for a declared effective Hamiltonian along a frozen path, not a validated experimental reaction-rate model. In the primary targeted-H case the first excited level is above that model's barrier, so a numerically similar level gap is not automatically a reproduced subbarrier doublet. This additional limitation does not invalidate the separate classical saved-data comparisons.

The public repository now lets a reader inspect exact model files, label sets, predictions, corrected metric definitions and provenance. The compact verifier checks the saved PBE input geometries, official force blocks, XML unit consistency, stored predictions and overlaps without running new physical calculations. Rebuilding this website is another presentation-layer operation; it is not a new inference or simulation.

Further claims—independent generalization, broader-temperature coverage or reliable reactive dynamics—would require a new question and a new prospective protocol. They should not be smuggled into a caption by calling a local check a final validation. The useful ending is not that every warning disappeared. It is that we can now say, with much greater precision, which observations survived and which conclusions never followed from them.

@sources: methods limits diagnostic corrections science

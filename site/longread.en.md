# One Proton. Several Tests of Trust.

This essay connects five distinct studies of one molecule. Geometry and force comparisons use saved calculations; optimizer examples use published summary values. The goal is to understand what each test reveals about a model, rather than to claim experimental accuracy.

## 1. A small molecule with a large question

Malonaldehyde has only nine atoms: three carbons, four hydrogens and two oxygens. One hydrogen sits between the oxygen atoms and can change sides. This small rearrangement makes a useful test for a model of molecular energy. A model must describe both comfortable geometries near a minimum and less familiar geometries along the transfer.

A Moment Tensor Potential, or MTP, learns an energy function from reference calculations. Its forces come from derivatives of that function. The attraction is practical: once fitted, an interatomic potential can be evaluated much more cheaply than repeatedly solving the electronic problem. The challenge is deciding where that approximation works.

Here the question is concrete: if two models get the same number of training examples, can their placement change what the models learn?

@sources: methods randomness
@papers: mtp2016

## 2. The proton moves, and the scaffold moves with it

The highlighted H2* is the transferred proton. O1 and O8 are the two oxygen atoms. Move through the nine saved geometries and watch the frame around the proton: the oxygen atoms approach each other, and the carbon skeleton changes too.

The oxygen separation falls from about 2.499 Å at the left endpoint to 2.390 Å at the center, a contraction of about 4.37%. A useful position coordinate is qPT: the O1–H2* distance minus the O8–H2* distance. It changes sign as the proton changes sides. At zero, the two distances are equal.

That coordinate makes a readable graph, but a nine-atom nonlinear molecule has 21 internal degrees of freedom. The oxygen separation adds another useful view of the same geometry.

@sources: path methods

## 3. A path is not a clock

The reference path consists of nine saved PBE geometries, obtained with the nudged elastic band method. The method searches for a path through the energy landscape. It does not tell us how long the proton spends at each position.

The site's smooth animation joins the saved structures by coordinate interpolation. The motion helps us follow the rearrangement; its speed is a presentation choice. A point between two saved images is not a new electronic calculation.

The energy hill is also a specific quantity: the largest of the nine saved electronic energies, measured from the lower endpoint. This discrete barrier is about 36.07 meV. A converged saddle structure, a free-energy barrier and a reaction rate require further calculations and different definitions.

@sources: path methods
@papers: neb2000

## 4. Spend the labels differently

Both original training sets contain 60 geometries. They share 36 examples; the remaining 24 differ. Basin60 adds examples near the minima. Targeted60 adds examples from a tube around a straight connection between aligned endpoint geometries.

This is a transition-directed sampling design, but the straight connection differs from the relaxed path. The training geometries never bring the oxygen atoms closer than about 2.479 Å. All seven internal PBE path images lie below that separation, reaching 2.390 Å at the center. The targeted design moves the proton toward the middle while missing part of the scaffold contraction.

That observation matters when interpreting the result. It is a gap in a geometric projection. It does not, by itself, classify a configuration as extrapolation in the MTP's full feature space.

@sources: train_basin train_targeted methods
@papers: mtp2016 maxvol2017

## 5. The original result is real—and specific

For the original saved model pair, the targeted allocation gives a much closer energy profile. Its discrete barrier is about 31.97 meV, compared with the PBE reference of 36.07 meV. Basin60 gives only about 0.83 meV under the same barrier definition.

The curve shapes reveal more than that scalar comparison. Basin60 has a central dip along the nine saved supports, where PBE has a hill. Targeted60 follows the hill more closely. This is a statement about the sampled path, not a proof that the full molecular surface has a false minimum at that structure.

Forces give a second test. On the three central path images, the component RMSE falls from about 0.176 eV/Å for Basin60 to 0.079 eV/Å for Targeted60. These are comparisons with PBE. They concern one model pair and a reused reference path whose endpoints overlap the shared training set.

@sources: path basin targeted randomness

## 6. Five seeds change the strength of the claim

Repeat the fitting with five paired initializations while keeping the two training sets fixed. The result becomes more interesting: Targeted is better on both primary metrics in three pairs. One pair reverses both rankings, and another gives a mixed ordering.

All five pairs belong in the figure. Selecting the best fit would erase the part of the experiment that shows how sensitive the conclusion is to training.

These are repetitions of optimization, not five independently generated training datasets. Three wins in five pairs describe those pairs; they are not a measured 60% probability that targeted sampling will win in a new experiment.

@sources: seeds randomness

## 7. Independence is a property of the data

Different filenames do not necessarily mean independent evidence. Two models may share endpoint geometries. Neighboring trajectory frames may be strongly correlated. A benchmark used to choose or inspect a model becomes part of development.

The later Train119 study adaptively expands the training set to 119 configurations. That changes both the data budget and its selection history. It answers a useful development question, but it is not a third equal-budget competitor to the original Train60 pair.

Its small errors on the reused path are therefore best read as development diagnostics. A test designed and kept separate from model development would answer a stronger question about generalization.

@sources: geometry roles corrections diagnostic

## 8. Coverage is not force error

A model can raise an applicability warning and still give a small error on a particular configuration. The two measurements ask different questions.

The saved Train119 grading crosses its historical stop on five frames. Direct PBE comparisons on eleven selected local frames give force-component RMSE values below the study's 0.09 eV/Å threshold. The warning remains; the force comparison adds a narrower observation about those frames.

The applicability grade is dimensionless. It is neither an error in eV/Å nor a universal probability of correctness. The eleven frames come from two correlated development segments, so they cannot establish a general calibration from grade to physical error.

@sources: diagnostic train119 continuation
@papers: maxvol2017

## 9. Look inside the scalar

One nine-atom force comparison contains 27 Cartesian components. The RMSE squares their differences, averages over the 27 components and takes a square root. It summarizes the whole frame, while a selected atom's vector difference describes just that atom.

The force viewer lets you inspect both. PBE, MTP and difference arrows use one declared display scale and undergo the same rigid camera rotation. The table stays in the original laboratory axes. Its difference is always MTP minus PBE.

An arrow shows a force, not the atom's future displacement. The shape, the selected atom, the numerical components and the whole-frame score must all refer to the same saved configuration.

@sources: geometry_crossing7 prediction_crossing7 geometry_challenge4 prediction_challenge4 corrections

## 10. A reference is another model

PBE is a density-functional approximation used here to provide electronic energies and forces. Learning that reference accurately is a meaningful computational task. It is different from demonstrating agreement with a higher-level electronic calculation or experiment.

The reference settings include a 16 Å periodic cell, Γ-point sampling and 80/960 Ry wavefunction/charge-density cutoffs. Those settings define the calculation; a convergence study would establish how sensitive the answers are to changing them.

The saved endpoint energies differ by about 0.107 meV. Later sub-meV model errors measure agreement with that particular reference. Extra digits allow arithmetic to be checked, but they do not create additional physical accuracy.

@sources: methods diagnostic
@papers: pbe1996 dftlimits2008

## 11. Quantum motion needs its own evidence

Proton transfer makes malonaldehyde interesting beyond classical pictures of crossing a hill. Quantum nuclei can produce tunneling splittings between energy levels. Their calculation requires a nuclear Hamiltonian, specified masses and a method that resolves the relevant quantum states.

A spectral splitting is an energy difference, whereas a reaction rate describes change per unit time. Neither follows directly from an animated path or one electronic barrier. Comparing them requires matching the physical quantity and computational assumptions.

The present figures examine an electronic reference and its learned approximations. They do not predict a measured tunneling splitting or a reaction rate.

@sources: methods limits
@papers: wang2008 kaser2022

## 12. What remains after the attractive plot

The most useful result is a sharper set of questions. Does the model reproduce the reference hill? Does the ranking survive a different initialization? Does it survive leaving the path? Does a coverage warning agree with a direct force comparison?

An animation can connect those questions, but each still needs a defined metric and an appropriate test. The static figures, tables and downloadable values keep the answer available when the motion stops.

The studies do not establish experimental accuracy or safe reactive dynamics. They show how a persuasive local fit can be investigated rather than simply trusted.

@sources: science diagnostic randomness

## 13. Off the path, the budget remains part of the result

PBE14 tests fourteen perturbed geometries around a minimum and the transition center. Four directions probe oxygen breathing, carbon-skeleton bending, lateral proton motion and out-of-plane proton motion. Both models, five paired initializations and two optimizer step caps remain in the comparison.

The primary transition-region result uses the 8000-step cap. It gives equal weight to four physical direction blocks: paired positive/negative perturbations are averaged within a block, and the single out-of-plane geometry forms its own block. Targeted has lower error in four of the five seed pairs. The mean Targeted-minus-Basin difference is about −0.146 eV/Å.

The absolute values help explain the widening gap. From the 2000 to 8000 cap, mean Basin transition error rises from about 0.188 to 0.310 eV/Å. Targeted changes from about 0.168 to 0.164 eV/Å. Most of the gap growth is therefore an increase in Basin error, rather than a large Targeted improvement. This is arithmetic; it does not identify a learning mechanism.

Alternative weights and leave-one-direction-out summaries are exploratory checks. The primary four-block definition stays fixed. The perturbed geometries and reused models extend the development picture, rather than constituting a prospective independent holdout.

@study: offpath
@papers: brezina2023 transition1x2022

## 14. The fit is not the finish

A final complication lies inside training itself. A regularized fitting problem combines a data residual with a coefficient penalty. Improving their sum can trade a worse fit for a smaller penalty.

In the published optimizer example, the same fixed-row objective Q falls by about 29% between a compensated copy and a refitted state. The data-loss term rises; the coefficient penalty falls by more. The stacked bars show exactly that balance. They explain arithmetic from published summary values, rather than reporting a new native execution.

Native J, fixed-row data loss, regularized Q and external force RMSE remain separate quantities. A conditional incremental update can guarantee non-increasing loss on fixed saved rows when zero is feasible and the nonnegative penalty vanishes at zero. That guarantee does not automatically improve the original native objective or forces on new geometries.

The next useful experiment is a matched comparison of complete training with a fixed checkpoint policy, followed by independent physical tests. The story ends with a testable question: which changes make the model more useful, under the conditions where we actually want to use it?

@study: optimization

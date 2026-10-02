# Execution boundary

The repository distinguishes four levels of reproducibility.

## 1. Repository integrity

No external scientific software is needed. CI verifies required files, Python syntax, script manifests, the public-asset manifest, compact-data manifests, private-path hygiene and checksums.

## 2. Compact numerical reproduction

No MLIP or QE executable is needed. tools/recompute_primary_metrics.py reads saved v029 reference and prediction CFGs and recomputes the original v030r primary metrics and endpoint overlaps.

## 3. Publication rendering and quantum diagnostics

The declared Python dependencies are required. Final renderers use data/publication_source_v005 when no compatible external project root is supplied. Video rendering requires ffmpeg.

The one-dimensional quantum audit is a numerical post-processing calculation on the frozen path; it is not DFT or molecular dynamics.

## 4. Heavy scientific recomputation

Retraining the MTPs requires external MLIP. Recomputing DFT labels and NEB requires Quantum ESPRESSO plus the documented pseudopotentials. Deployment trajectories require the historical LAMMPS/MLIP interface.

The repository does not redistribute those executables, the pseudopotential binaries, or the approximately 80 GB raw project tree.

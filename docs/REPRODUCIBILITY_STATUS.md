# Reproducibility status

## Clean clone

A clean clone is sufficient to:
- validate repository and public-asset hashes;
- recompute original v030r primary barrier and transition-force metrics from frozen v029 CFG payloads;
- reproduce the two NEB endpoint geometry overlaps with Train60;
- validate final publication figure, table and video inputs from repo-local compact v005 data;
- inspect original v028 datasets, models and Audit21 predictions;
- inspect the fixed-seed robustness audit, its evaluation-order repair, and final Train119 status;
- run the frozen-path quantum diagnostic with the declared Python environment.

Publication figures and the supplementary table can be rerendered from the clean clone. The CI reproduction-smoke job now performs the figure/table/frozen-path quantum render chain rather than only validating inputs. Video rendering additionally requires ffmpeg and remains input-validated in CI; full video rendering was verified separately in clean-copy QA.

## External MLIP

Re-evaluating the included MTP models or retraining from the included Train60 CFGs requires a compatible MLIP-2 executable. The original and deterministic-patch executable hashes are documented, but binaries are not redistributed.

## External Quantum ESPRESSO

Recomputing PBE labels or NEB requires Quantum ESPRESSO and the documented pseudopotentials. QE and pseudopotential binaries are not included.

## Private project tree

The private approximately 80 GB project tree is no longer required for the compact numerical checks, primary metric recomputation, or final publication renderers. It remains the full provenance source for heavy raw outputs and historical failed attempts.

## Scope of CI

CI verifies the public package and compact reproduction boundary. It does not claim to rerun QE, MTP training, LAMMPS dynamics or the complete scientific project.

## Source resolution

Publication renderers use an explicit input order: `--source-root` when supplied, otherwise repo-local `data/publication_source_v005`. They do not silently fall back to a private project pointer. A compatible external project tree can be used only by passing it explicitly through `--source-root`.

## Current canonical ledger

V005 is the accepted source-bound authority. Historical V004 contains known semantic classification errors and is preserved for comparison. Public CI covers compact semantic regression; it does not reproduce all raw private source documents or the complete historical physics lineage.

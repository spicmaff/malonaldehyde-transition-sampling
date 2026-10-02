# Data provenance

The public repository contains compact derivatives of the local malonaldehyde project.

data/publication_source_v005 is a sanitized copy of the minimal v005 source package required by the publication renderers. Numerical fields are preserved; private absolute path strings are replaced by placeholders. PUBLICATION_SOURCE_MANIFEST.tsv records both original-source and repository SHA-256 values.

data/frozen_models_v028 contains the original Train60 CFGs, untrained L12 template, locked trained MTP files, frozen Audit21 labels and saved v029 model predictions. Where a training CFG contained a private absolute provenance path, only that path string was sanitized; numerical training data are unchanged.

data/robustness contains the post-publication fixed-seed audit protocol and summary outputs. It did not execute new DFT.

data/post_publication contains a compact machine-readable final scientific status.

The full historical project, including failed attempts and heavy QE scratch data, remains outside Git. No new DFT calculation is performed during public-repository preparation.

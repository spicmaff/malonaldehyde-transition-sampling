# CI scope

CI is intentionally narrower than full scientific recomputation.

It checks:
- Python compilation;
- core and complete script manifests;
- every row of PUBLIC_ASSET_MANIFEST.tsv;
- compact publication-source and frozen-model manifests;
- absence of private machine paths and common credential patterns;
- exact numerical recomputation of the original v030r primary metrics from included CFG payloads;
- expected endpoint-overlap count;
- renderer and quantum input validation in the reproduction smoke job.

CI does not run Quantum ESPRESSO, MTP training, LAMMPS, NEB or reactive molecular dynamics.

A green CI status therefore means that the published compact package is internally consistent and its supported lightweight reproductions pass. It is not an end-to-end reproduction of the heavy calculation.

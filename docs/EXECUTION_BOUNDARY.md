# Execution boundary

This document separates three different reproducibility claims.

## Clean-clone repository verification

A fresh clone is sufficient to compile public Python, verify manifests and
SHA-256 values, check dependency declarations, and run the public-release
audit. Run:

```bash
python3 tools/run_public_selftests.py .
python3 tools/audit_public_repo.py .
```

These checks do not execute Quantum ESPRESSO, MLIP, LAMMPS, NEB, MTP training,
or the full scientific calculation.

## Regeneration from a compatible project tree

The public renderers and late-stage audits require accepted input/output tables
under a compatible `malonaldehyde_mtp_al` project root.

## Heavy scientific recomputation

The versioned core scripts are public, but complete recomputation also requires
separately installed scientific software, pseudopotentials, and compatible
upstream project inputs. The repository is not a containerized redistribution
of all external software and scratch data.

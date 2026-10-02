# Software provenance

## Recorded scientific environment

The later Stage69 source audit captured exact executable identities from the same project environment used by the continuation:

| component | recorded version / identity | SHA-256 |
|---|---|---|
| Python | 3.11.15 | 2ec954d9a5b0e3976e27d12431bc7f5636276c110123439ee492e687c97f282e |
| Quantum ESPRESSO pw.x | PWSCF 7.5 | 1d66c7856f5d6b3cd9c66b8578e01512b16bbe907b4360e54234890712ccd6a1 |
| MLIP-2 mlp used by the original public lineage | local MLIP-2 build | e7ff9392c76b9642bc4a016115b7b3a7bf5bb80472f7ae46ce01ca171d558d72 |
| seeded MLIP training patch used for deterministic later training and the post-publication RNG audit | Stage71d seeded-random patch | fd6e96bdd5c070c4b3728768cc29338a0e7fd43a77ec0c18b292c0170ab386fe |
| LAMMPS/MLIP serial | LAMMPS stable 2 Aug 2023 | 539cf3b61b0b293c7bf19b4d6642877f2d56da44bc69cf7a9b3b5bfb4c211581 |

The original v024/v025 QE outputs explicitly report PWSCF 7.5.

## PBE reference settings

- functional: PBE;
- cell: 16 x 16 x 16 A;
- wavefunction cutoff: 80 Ry;
- charge-density cutoff: 960 Ry;
- occupations: fixed;
- spin: neutral singlet, nspin = 1;
- k points: Gamma.

## Pseudopotentials

PSlibrary scalar-relativistic PBE PAW files were used:

| file | SHA-256 |
|---|---|
| C.pbe-n-kjpaw_psl.1.0.0.UPF | 8a25fbf64c4fa257c68c01dc9a96e5b23c6a5ac0b09f45f271e1c946a65ed657 |
| H.pbe-kjpaw_psl.1.0.0.UPF | dd48be99c7a91c4163ed123cdac938af189a9f62f382c41e3f664d00a586839d |
| O.pbe-n-kjpaw_psl.1.0.0.UPF | 6d4f573d1f5d8fab1d334ed76fefbac21fdbb2c406af7f85ab8c6aab0e84ccc0 |

The UPF binaries are not redistributed here. The names and hashes are provided so a separately obtained copy can be authenticated.

## Public Python environment

environment.yml and requirements.txt describe the lightweight rendering and post-processing environment. They do not reproduce the external QE, MLIP or LAMMPS installations.

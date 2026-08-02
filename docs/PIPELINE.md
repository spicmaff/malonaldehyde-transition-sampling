# Reproducible pipeline included in this repository

The public repository now contains the accepted strict-comparison scripts from
the independent PBE NEB calculation through the final deployment diagnostics.

## Ordered pipeline

1. `step26_independent_neb_dft_v024.py`
2. `step27_independent_neb_single_points_v025.py`
3. `step28_fresh_tube_active_selection_v026.py`
4. `step29_equal_budget_dft_labels_v027.py`
5. `step30_train_equal_budget_l12_v028.py`
6. `step31_frozen_audit21_evaluation_v029.py`
7. `step32_final_primary_analysis_v030.py`
8. `step32b_primary_metric_protocol_recovery_v030r.py`
9. `step33_secondary_mtp_neb_v031.py`
10. `step34_targeted_md_diagnostics_v032.py`
11. `step34c_v032_selection_interface_diagnostic_v032d.py`
12. `step35_project_closeout_v033.py`

The repaired `step32b` metrics are authoritative for the final primary
barrier and transition-force comparison.

## Additional public code

The repository also includes final figure, table, and video renderers; the
frozen-path H/D quantum audit; and exact source-oracle/forensic diagnostics.

## Execution boundary

These scripts require a compatible project tree, Quantum ESPRESSO, MLIP, and
LAMMPS/MLIP installations. Heavy DFT working directories, pseudopotential
files, installed external binaries, and transient attempt directories are not
stored in ordinary Git.

The repository therefore supports audited reconstruction from the accepted
project inputs and compact tables. It is not a containerized redistribution of
all external scientific software or all raw scratch files.

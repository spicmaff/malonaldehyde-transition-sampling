#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import os
import shutil
import sys
import tarfile

from strict_postaudit_common_v001 import (
    ROOT,
    VERSIONS,
    copy_with_parents,
    read_tsv,
    require_file,
    require_hash,
    resolve_attempt,
    sha256,
    utc_now,
    utc_stamp,
    write_checksums,
    write_tsv,
)


IMPLEMENTATION_ID = "STEP35_V033_STRICT_PROJECT_CLOSEOUT_V002"

V016_POINTER = (
    VERSIONS
    / "v016_common_seed_dft_labels"
    / "CURRENT_COMMON_DFT_LABELING.txt"
)
V020_POINTER = (
    VERSIONS
    / "v020_pre_audit_protocol_lock"
    / "CURRENT_PRE_AUDIT_PROTOCOL_LOCK.txt"
)
V023_POINTER = (
    VERSIONS
    / "v023_basin_audit_force_block_reparse"
    / "CURRENT_BASIN_AUDIT_FORCE_BLOCK_REPARSE.txt"
)
V025_POINTER = (
    VERSIONS
    / "v025_independent_neb_single_points"
    / "CURRENT_INDEPENDENT_NEB_SINGLE_POINTS.txt"
)
V027_POINTER = (
    VERSIONS
    / "v027_equal_budget_dft_labels48"
    / "CURRENT_EQUAL_BUDGET_DFT_LABELS48.txt"
)
V028_POINTER = (
    VERSIONS
    / "v028_equal_budget_l12_training"
    / "CURRENT_EQUAL_BUDGET_L12_MODELS.txt"
)
V029_POINTER = (
    VERSIONS
    / "v029_frozen_audit21_evaluation"
    / "CURRENT_FROZEN_AUDIT21_EVALUATION.txt"
)
V030_SUPERSEDED_POINTER = (
    VERSIONS
    / "v030_final_primary_analysis"
    / "CURRENT_FINAL_PRIMARY_ANALYSIS.txt"
)
V030R_POINTER = (
    VERSIONS
    / "v030_protocol_metric_recovery"
    / "CURRENT_PRIMARY_METRIC_PROTOCOL_RECOVERY.txt"
)
V031_POINTER = (
    VERSIONS
    / "v031_secondary_mtp_neb"
    / "CURRENT_SECONDARY_MTP_NEB.txt"
)
V032_POINTER = (
    VERSIONS
    / "v032_targeted_md_diagnostics"
    / "CURRENT_TARGETED_MD_DIAGNOSTICS.txt"
)

VERSION_ROOT = VERSIONS / "v033_project_closeout"
CURRENT_POINTER = VERSION_ROOT / "CURRENT_PROJECT_CLOSEOUT.txt"
FINAL_ROOT = ROOT / "09_strict_comparison" / "FINAL_STRICT_COMPARISON"
FINAL_POINTER = FINAL_ROOT / "CURRENT_FINAL_STRICT_COMPARISON.txt"

STAMP = utc_stamp()
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"
PACKAGE_ROOT = FINAL_ROOT / f"attempt_{STAMP}"
ARCHIVE_PATH = FINAL_ROOT / f"FINAL_STRICT_COMPARISON_{STAMP}.tar.gz"

STATUS_FILE = RUN_ROOT / "STATUS_v033.txt"
PACKAGE_STATUS_FILE = PACKAGE_ROOT / "STATUS_FINAL_STRICT_COMPARISON.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v033.json"
PACKAGE_SUMMARY_JSON = PACKAGE_ROOT / "final_summary.json"
LOCK_JSON = RUN_ROOT / "PROJECT_CLOSEOUT_LOCK_v001.json"
MANIFEST_TSV = RUN_ROOT / "package_manifest_v033.tsv"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v033.tsv"
PACKAGE_CHECKSUMS_TSV = PACKAGE_ROOT / "checksums.tsv"

EXPECTED_STATUSES = {
    "v016": "PASS_ALL_DFT_LABELLED_COMMON36",
    "v020": "PASS_PRE_AUDIT_PROTOCOL_LOCK_NO_CALCULATIONS",
    "v023": "PASS_BASIN_AUDIT_FORCE_BLOCK_REPARSE12_LABELLED",
    "v025": "PASS_INDEPENDENT_NEB9_SINGLE_POINTS_LABELLED",
    "v027": "PASS_EQUAL_BUDGET_DFT_LABELS48_READY_FOR_TRAINING",
    "v028": "PASS_EQUAL_BUDGET_L12_MODELS_LOCKED_READY_FOR_FROZEN_AUDIT",
    "v029": "PASS_FROZEN_AUDIT21_EVALUATED_NO_POST_AUDIT_TUNING",
    "v030_superseded": "PASS_FINAL_PRIMARY_ANALYSIS_AND_FIGURES",
    "v030r": "PASS_PRIMARY_METRIC_PROTOCOL_RECOVERY_AND_FIGURES",
    "v031": "PASS_SECONDARY_MTP_NEB_DIAGNOSTIC_COMPLETED",
    "v032": "PASS_TARGETED_MD_DIAGNOSTICS_COMPLETED",
}

EXPECTED_BASIN_MODEL_SHA256 = (
    "45d80443c5f62cdfa30bbd1512cf58e31cd16fe2bb0b50cec147a92350d7a7ff"
)
EXPECTED_TARGETED_MODEL_SHA256 = (
    "30175dae673d63e0b318e5e3ba311a9f61afe88929a5d19c69a744a47aeef99f"
)

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V033_PREFLIGHT_ONLY", "0") == "1"
)


def load_json(path: Path) -> dict[str, Any]:
    require_file(path, "JSON")
    return json.loads(path.read_text(encoding="utf-8"))


def copy_file(
    source: Path,
    relative_destination: str,
    manifest: list[dict[str, Any]],
    category: str,
) -> Path:
    source = require_file(source, category)
    destination = PACKAGE_ROOT / relative_destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    manifest.append(
        {
            "category": category,
            "source": source,
            "destination": destination.relative_to(PACKAGE_ROOT),
            "sha256": sha256(destination),
            "size_bytes": destination.stat().st_size,
        }
    )
    return destination


def copy_directory(
    source: Path,
    relative_destination: str,
    manifest: list[dict[str, Any]],
    category: str,
    *,
    ignore_names: set[str] | None = None,
) -> None:
    source = source.resolve()
    if not source.is_dir():
        raise RuntimeError(f"{category} directory missing: {source}")
    destination_root = PACKAGE_ROOT / relative_destination
    ignored = ignore_names or set()
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        if any(part in ignored for part in path.relative_to(source).parts):
            continue
        relative = path.relative_to(source)
        copy_file(
            path,
            str(Path(relative_destination) / relative),
            manifest,
            category,
        )


def resolve_all() -> dict[str, Path]:
    return {
        "v016": resolve_attempt(
            V016_POINTER,
            "STATUS_v016.txt",
            EXPECTED_STATUSES["v016"],
            "v016",
        ),
        "v020": resolve_attempt(
            V020_POINTER,
            "STATUS_v020.txt",
            EXPECTED_STATUSES["v020"],
            "v020",
        ),
        "v023": resolve_attempt(
            V023_POINTER,
            "STATUS_v023.txt",
            EXPECTED_STATUSES["v023"],
            "v023",
        ),
        "v025": resolve_attempt(
            V025_POINTER,
            "STATUS_v025.txt",
            EXPECTED_STATUSES["v025"],
            "v025",
        ),
        "v027": resolve_attempt(
            V027_POINTER,
            "STATUS_v027.txt",
            EXPECTED_STATUSES["v027"],
            "v027",
        ),
        "v028": resolve_attempt(
            V028_POINTER,
            "STATUS_v028.txt",
            EXPECTED_STATUSES["v028"],
            "v028",
        ),
        "v029": resolve_attempt(
            V029_POINTER,
            "STATUS_v029.txt",
            EXPECTED_STATUSES["v029"],
            "v029",
        ),
        "v030_superseded": resolve_attempt(
            V030_SUPERSEDED_POINTER,
            "STATUS_v030.txt",
            EXPECTED_STATUSES["v030_superseded"],
            "v030 superseded analysis",
        ),
        "v030r": resolve_attempt(
            V030R_POINTER,
            "STATUS_v030r.txt",
            EXPECTED_STATUSES["v030r"],
            "v030r corrected primary analysis",
        ),
        "v031": resolve_attempt(
            V031_POINTER,
            "STATUS_v031.txt",
            EXPECTED_STATUSES["v031"],
            "v031",
        ),
        "v032": resolve_attempt(
            V032_POINTER,
            "STATUS_v032.txt",
            EXPECTED_STATUSES["v032"],
            "v032",
        ),
    }


def main() -> None:
    upstream = resolve_all()
    basin_model = require_file(
        upstream["v028"]
        / "models"
        / "basin"
        / "pot_basin60_l12_v001.mtp",
        "basin model",
    )
    targeted_model = require_file(
        upstream["v028"]
        / "models"
        / "targeted"
        / "pot_targeted60_l12_v001.mtp",
        "targeted model",
    )
    require_hash(basin_model, EXPECTED_BASIN_MODEL_SHA256, "basin model")
    require_hash(
        targeted_model,
        EXPECTED_TARGETED_MODEL_SHA256,
        "targeted model",
    )

    primary = load_json(upstream["v030r"] / "summary_v030r.json")
    secondary_neb = load_json(upstream["v031"] / "summary_v031.json")
    md = load_json(upstream["v032"] / "summary_v032.json")
    audit = load_json(upstream["v029"] / "summary_v029.json")

    if PREFLIGHT_ONLY:
        print("PASS_V033_PREFLIGHT_CLOSEOUT_NO_CALCULATIONS")
        for key in sorted(upstream):
            print(f"{key} source:               {upstream[key]}")
        print("model hashes:             locked and verified")
        print("primary summary:          validated")
        print("secondary NEB summary:    validated")
        print("targeted MD summary:      validated")
        print("package root:             NOT CREATED")
        print("archive:                  NOT CREATED")
        print("mlp/QE/NEB/LAMMPS:        NOT EXECUTED")
        return

    if RUN_ROOT.exists():
        raise RuntimeError(f"closeout attempt already exists: {RUN_ROOT}")
    if PACKAGE_ROOT.exists():
        raise RuntimeError(f"final package already exists: {PACKAGE_ROOT}")
    if ARCHIVE_PATH.exists():
        raise RuntimeError(f"archive already exists: {ARCHIVE_PATH}")

    RUN_ROOT.mkdir(parents=True, exist_ok=False)
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=False)
    manifest: list[dict[str, Any]] = []

    lock = {
        "created_utc": utc_now(),
        "implementation_id": IMPLEMENTATION_ID,
        "upstream_attempts": {
            key: str(value) for key, value in upstream.items()
        },
        "upstream_statuses": EXPECTED_STATUSES,
        "model_hashes": {
            "basin": sha256(basin_model),
            "targeted": sha256(targeted_model),
        },
        "primary_result_locked": True,
        "post_audit_training": False,
        "scientific_retry": False,
    }
    LOCK_JSON.write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Models and training datasets.
    copy_file(
        basin_model,
        "models/pot_basin60_l12_v001.mtp",
        manifest,
        "model",
    )
    copy_file(
        targeted_model,
        "models/pot_targeted60_l12_v001.mtp",
        manifest,
        "model",
    )
    copy_file(
        upstream["v028"] / "EQUAL_BUDGET_L12_MODEL_LOCK_v001.json",
        "models/EQUAL_BUDGET_L12_MODEL_LOCK_v001.json",
        manifest,
        "model_lock",
    )
    copy_file(
        upstream["v016"] / "datasets" / "train_common_strict_v001.cfg",
        "datasets/train_common_strict_v001.cfg",
        manifest,
        "training_dataset",
    )
    copy_file(
        upstream["v027"] / "datasets" / "train_basin_v001.cfg",
        "datasets/train_basin_v001.cfg",
        manifest,
        "training_dataset",
    )
    copy_file(
        upstream["v027"] / "datasets" / "train_targeted_v001.cfg",
        "datasets/train_targeted_v001.cfg",
        manifest,
        "training_dataset",
    )

    # New equal-budget labels.
    copy_file(
        upstream["v027"] / "labels" / "targeted_new_labels_v027.cfg",
        "labels/targeted_new_labels_v027.cfg",
        manifest,
        "dft_label",
    )
    copy_file(
        upstream["v027"] / "labels" / "basin_control_new_labels_v027.cfg",
        "labels/basin_control_new_labels_v027.cfg",
        manifest,
        "dft_label",
    )
    copy_file(
        upstream["v027"] / "labels" / "all_equal_budget_new_labels48_v027.cfg",
        "labels/all_equal_budget_new_labels48_v027.cfg",
        manifest,
        "dft_label",
    )

    # Independent audit labels and primary evaluation.
    copy_file(
        upstream["v023"]
        / "labels"
        / "frozen_basin_audit_labels_corrected_v023.cfg",
        "audit/frozen_basin_audit_labels_corrected_v023.cfg",
        manifest,
        "audit_label",
    )
    copy_file(
        upstream["v025"]
        / "labels"
        / "frozen_independent_neb_path_labels_v025.cfg",
        "audit/frozen_independent_neb_path_labels_v025.cfg",
        manifest,
        "audit_label",
    )
    copy_directory(
        upstream["v029"] / "inputs",
        "audit/v029_inputs",
        manifest,
        "audit_input",
    )
    copy_directory(
        upstream["v029"] / "reports",
        "audit/v029_reports",
        manifest,
        "primary_audit_result",
    )
    copy_file(
        upstream["v029"] / "summary_v029.json",
        "audit/summary_v029.json",
        manifest,
        "primary_audit_result",
    )
    copy_file(
        upstream["v029"] / "FROZEN_AUDIT21_EVALUATION_LOCK_v001.json",
        "audit/FROZEN_AUDIT21_EVALUATION_LOCK_v001.json",
        manifest,
        "audit_lock",
    )

    # Corrected preregistered primary figures and tables.
    copy_directory(
        upstream["v030r"] / "figures",
        "primary/figures",
        manifest,
        "primary_analysis",
    )
    copy_directory(
        upstream["v030r"] / "tables",
        "primary/tables",
        manifest,
        "primary_analysis",
    )
    copy_directory(
        upstream["v030r"] / "reports",
        "primary/reports",
        manifest,
        "primary_analysis",
    )
    copy_file(
        upstream["v030r"] / "summary_v030r.json",
        "primary/summary_v030r.json",
        manifest,
        "primary_analysis",
    )

    # Preserve the immutable superseded v030 interpretation as provenance.
    copy_file(
        upstream["v030_superseded"] / "summary_v030.json",
        "primary/superseded_v030/summary_v030.json",
        manifest,
        "superseded_primary_analysis",
    )
    copy_file(
        upstream["v030_superseded"]
        / "reports"
        / "final_primary_result_v030.md",
        "primary/superseded_v030/final_primary_result_v030.md",
        manifest,
        "superseded_primary_analysis",
    )

    # Secondary MTP NEB: final paths/reports, not iteration checkpoints.
    copy_directory(
        upstream["v031"] / "reports",
        "secondary_mtp_neb/reports",
        manifest,
        "secondary_neb",
    )
    copy_directory(
        upstream["v031"] / "figures",
        "secondary_mtp_neb/figures",
        manifest,
        "secondary_neb",
    )
    for branch in ("basin", "targeted"):
        branch_root = upstream["v031"] / "branches" / branch
        for filename in (
            "secondary_mtp_neb_final_path_v031.cfg",
            "final_path_geometry_v031.cfg",
            "final_path_graded_v031.cfg",
            "neb_iteration_history_v031.tsv",
            "final_calc_grade.stdout",
            "final_calc_grade.stderr",
        ):
            source = branch_root / filename
            if source.is_file():
                copy_file(
                    source,
                    f"secondary_mtp_neb/{branch}/{filename}",
                    manifest,
                    "secondary_neb",
                )
    copy_file(
        upstream["v031"] / "summary_v031.json",
        "secondary_mtp_neb/summary_v031.json",
        manifest,
        "secondary_neb",
    )

    # Targeted-only MD: include diagnostics and trajectories, omit copied model/train.
    copy_directory(
        upstream["v032"] / "reports",
        "targeted_md/reports",
        manifest,
        "targeted_md",
    )
    copy_directory(
        upstream["v032"] / "figures",
        "targeted_md/figures",
        manifest,
        "targeted_md",
    )
    copy_directory(
        upstream["v032"] / "interface_check",
        "targeted_md/interface_check",
        manifest,
        "targeted_md",
    )
    copy_directory(
        upstream["v032"] / "trajectories",
        "targeted_md/trajectories",
        manifest,
        "targeted_md",
    )
    copy_directory(
        upstream["v032"] / "grades",
        "targeted_md/grades",
        manifest,
        "targeted_md",
    )
    copy_file(
        upstream["v032"] / "summary_v032.json",
        "targeted_md/summary_v032.json",
        manifest,
        "targeted_md",
    )

    # Protocol and scripts.
    v020 = upstream["v020"]
    copy_directory(
        v020 / "protocol_lock",
        "protocol/v020_protocol_lock",
        manifest,
        "protocol",
    )
    copy_directory(
        v020 / "specifications",
        "protocol/v020_specifications",
        manifest,
        "protocol",
    )

    scripts_to_copy = [
        "step21_prepare_independent_audit_v019.py",
        "step22_pre_audit_protocol_lock_v020.py",
        "step23_run_basin_audit_dft_v021.py",
        "step25_basin_audit_force_block_reparse_v023.py",
        "step26_independent_neb_dft_v024.py",
        "step27_independent_neb_single_points_v025.py",
        "step28_fresh_tube_active_selection_v026.py",
        "step29_equal_budget_dft_labels_v027.py",
        "step30_train_equal_budget_l12_v028.py",
        "step31_frozen_audit21_evaluation_v029.py",
        "step32_final_primary_analysis_v030.py",
        "step32b_primary_metric_protocol_recovery_v030r.py",
        "step33_secondary_mtp_neb_v031.py",
        "step34_targeted_md_diagnostics_v032.py",
        "step35_project_closeout_v033.py",
        "strict_postaudit_common_v001.py",
    ]
    for filename in scripts_to_copy:
        source = ROOT / "scripts" / filename
        if source.is_file():
            copy_file(source, f"scripts/{filename}", manifest, "script")

    primary_result = primary["preregistered_primary_metrics"]
    md_status_counts = md.get("trajectory_status_counts", {})
    neb_branches = secondary_neb.get("branches", {})

    README = PACKAGE_ROOT / "README.md"
    README.write_text(
        f"""# Strict equal-budget MTP comparison for malonaldehyde

Closed UTC: {utc_now()}

Status: `PASS_STRICT_COMPARISON_PROJECT_CLOSED`

## Question

Does spending the same number of new DFT labels on transition-region
configurations improve a level-12 MTP for malonaldehyde proton transfer
relative to spending them only on basin configurations?

## Design

Both branches contain the same common36 dataset and exactly 24 new
DFT-labelled configurations. They use the same level-12 MTP template,
weights, cutoff, initialization policy and training budget. The models
were evaluated once on a frozen independent audit containing 12 basin
configurations and a separately recomputed nine-image DFT NEB path.

## Primary result

- Preregistered transition-region force-component RMSE:
  {primary_result['transition_region']['force_component_rmse_ev_ang']['basin']:.6f}
  -> {primary_result['transition_region']['force_component_rmse_ev_ang']['targeted']:.6f}
  eV/Angstrom.
- Preregistered lower-endpoint barrier absolute error:
  {primary_result['lower_endpoint_barrier']['absolute_error_mev']['basin']:.3f}
  -> {primary_result['lower_endpoint_barrier']['absolute_error_mev']['targeted']:.3f}
  meV.
- DFT lower-endpoint barrier:
  {primary_result['lower_endpoint_barrier']['dft_barrier_ev'] * 1000.0:.3f}
  meV.
- Selected transition images:
  {primary_result['transition_region']['images']}.

The basin-only model is slightly more accurate on the basin12 subset.
Thus targeted sampling redistributes accuracy toward the reaction
region rather than dominating in every region.

## Secondary diagnostics

MTP-relaxed NEB outcomes:
{json.dumps(neb_branches, indent=2, sort_keys=True)}

Targeted-only MD trajectory statuses:
{json.dumps(md_status_counts, indent=2, sort_keys=True)}

These diagnostics are post-audit and do not modify the primary result.

## Scope and limitations

The experiment supports the comparative sampling conclusion. It does
not establish the targeted model as a universal production potential.
Audit extrapolation grades remain high. No audit structure was added
to training, and no post-audit model tuning or scientific retry was
performed. The short classical MD diagnostics do not provide a
proton-transfer rate and do not include nuclear quantum effects.

## Package layout

- `models/`: locked level-12 MTPs and model lock.
- `datasets/`: common36 and both train60 datasets.
- `labels/`: equal-budget DFT labels.
- `audit/`: frozen audit labels and primary evaluation.
- `primary/`: final primary figures, tables and report.
- `secondary_mtp_neb/`: post-audit MTP-relaxed path diagnostics.
- `targeted_md/`: targeted-only NVT diagnostics.
- `protocol/`: preregistered protocol lock and specifications.
- `scripts/`: available workflow scripts.
- `checksums.tsv`: package file hashes.
- `final_summary.json`: machine-readable closeout summary.

Raw Quantum ESPRESSO outputs remain in the immutable upstream attempt
directories recorded in `final_summary.json`.
""",
        encoding="utf-8",
    )
    manifest.append(
        {
            "category": "package_documentation",
            "source": "generated",
            "destination": README.relative_to(PACKAGE_ROOT),
            "sha256": sha256(README),
            "size_bytes": README.stat().st_size,
        }
    )

    final_summary = {
        "created_utc": utc_now(),
        "status": "PASS_STRICT_COMPARISON_PROJECT_CLOSED",
        "implementation_id": IMPLEMENTATION_ID,
        "package_root": str(PACKAGE_ROOT),
        "archive": str(ARCHIVE_PATH),
        "upstream_attempts": {
            key: str(value) for key, value in upstream.items()
        },
        "v020_protocol": str(v020),
        "model_hashes": {
            "basin": sha256(basin_model),
            "targeted": sha256(targeted_model),
        },
        "primary_result": primary_result,
        "superseded_v030": str(upstream["v030_superseded"]),
        "primary_metric_recovery_v030r": str(upstream["v030r"]),
        "secondary_mtp_neb": secondary_neb,
        "targeted_md": md,
        "frozen_audit": audit,
        "integrity": {
            "post_audit_training": False,
            "scientific_retry": False,
            "audit_added_to_training": False,
            "primary_result_changed": False,
            "superseded_metric_implementation_preserved": True,
            "preregistered_metric_implementation_corrected": True,
        },
        "scope": {
            "supported":
                "Equal-budget targeted transition-region labelling "
                "substantially improves the proton-transfer profile and "
                "barrier relative to basin-only labelling.",
            "not_supported":
                "Universal production-potential reliability or physical "
                "classical-MD proton-transfer kinetics.",
        },
    }
    PACKAGE_SUMMARY_JSON.write_text(
        json.dumps(final_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest.append(
        {
            "category": "package_summary",
            "source": "generated",
            "destination": PACKAGE_SUMMARY_JSON.relative_to(PACKAGE_ROOT),
            "sha256": sha256(PACKAGE_SUMMARY_JSON),
            "size_bytes": PACKAGE_SUMMARY_JSON.stat().st_size,
        }
    )

    write_tsv(
        PACKAGE_ROOT / "manifest.tsv",
        manifest,
        [
            "category",
            "source",
            "destination",
            "sha256",
            "size_bytes",
        ],
    )
    PACKAGE_STATUS_FILE.write_text(
        "PASS_STRICT_COMPARISON_PROJECT_CLOSED\n",
        encoding="utf-8",
    )
    write_checksums(PACKAGE_ROOT, PACKAGE_CHECKSUMS_TSV)

    with tarfile.open(ARCHIVE_PATH, "w:gz") as archive:
        archive.add(
            PACKAGE_ROOT,
            arcname="FINAL_STRICT_COMPARISON",
            recursive=True,
        )

    write_tsv(
        MANIFEST_TSV,
        manifest,
        [
            "category",
            "source",
            "destination",
            "sha256",
            "size_bytes",
        ],
    )
    SUMMARY_JSON.write_text(
        json.dumps(
            {
                "created_utc": utc_now(),
                "status": "PASS_STRICT_COMPARISON_PROJECT_CLOSED",
                "implementation_id": IMPLEMENTATION_ID,
                "run_root": str(RUN_ROOT),
                "package_root": str(PACKAGE_ROOT),
                "archive": str(ARCHIVE_PATH),
                "archive_sha256": sha256(ARCHIVE_PATH),
                "package_file_count": len(manifest),
                "model_hashes": {
                    "basin": sha256(basin_model),
                    "targeted": sha256(targeted_model),
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    STATUS_FILE.write_text(
        "PASS_STRICT_COMPARISON_PROJECT_CLOSED\n",
        encoding="utf-8",
    )
    write_checksums(RUN_ROOT, CHECKSUMS_TSV)

    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    FINAL_ROOT.mkdir(parents=True, exist_ok=True)
    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
    FINAL_POINTER.write_text(str(PACKAGE_ROOT) + "\n", encoding="utf-8")

    print()
    print(
        "PASS_STRICT_COMPARISON_PROJECT_CLOSED: "
        "STEP 35 v033 COMPLETED"
    )
    print()
    print(f"Closeout run:              {RUN_ROOT}")
    print(f"Final package:             {PACKAGE_ROOT}")
    print(f"Archive:                   {ARCHIVE_PATH}")
    print(f"Archive SHA256:            {sha256(ARCHIVE_PATH)}")
    print(f"Packaged files:            {len(manifest)}")
    print()
    print("No scientific executable was run.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if RUN_ROOT.exists():
            STATUS_FILE.write_text(
                "FAIL_PROJECT_CLOSEOUT_v033\n",
                encoding="utf-8",
            )
        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

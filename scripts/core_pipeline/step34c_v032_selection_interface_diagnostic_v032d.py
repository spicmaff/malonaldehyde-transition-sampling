#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from strict_postaudit_common_v001 import (
    CFGBlock,
    EXPECTED_TYPES,
    NAT,
    ROOT,
    VERSIONS,
    cfg_from_positions,
    finite_float,
    geometry_metrics,
    mass_weighted_kabsch_align,
    parse_lammps_custom_dump,
    read_cfg,
    read_tsv,
    recover_blocks_by_feature_or_geometry,
    require_file,
    require_hash,
    resolve_attempt,
    sha256,
    utc_now,
    utc_stamp,
    write_cfg,
    write_checksums,
    write_lammps_data,
    write_tsv,
)


IMPLEMENTATION_ID = (
    "STEP34C_V032D_SELECTION_INTERFACE_DIAGNOSTIC_V002"
)

MLP = ROOT / "01_environment" / "v001" / "software" / "bin" / "mlp"
LAMMPS = (
    ROOT
    / "01_environment"
    / "v001"
    / "software"
    / "bin"
    / "lmp_mlip_serial"
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
V030R_POINTER = (
    VERSIONS
    / "v030_protocol_metric_recovery"
    / "CURRENT_PRIMARY_METRIC_PROTOCOL_RECOVERY.txt"
)
V031R_POINTER = (
    VERSIONS
    / "v031_secondary_mtp_neb_interpretation_recovery"
    / "CURRENT_SECONDARY_MTP_NEB_INTERPRETATION_RECOVERY.txt"
)
V032_POINTER = (
    VERSIONS
    / "v032_targeted_md_diagnostics"
    / "CURRENT_TARGETED_MD_DIAGNOSTICS.txt"
)
V032R_POINTER = (
    VERSIONS
    / "v032_targeted_md_interpretation_recovery"
    / "CURRENT_TARGETED_MD_INTERPRETATION_RECOVERY.txt"
)

VERSION_ROOT = VERSIONS / "v032_selection_interface_diagnostic"
CURRENT_POINTER = (
    VERSION_ROOT / "CURRENT_V032_SELECTION_INTERFACE_DIAGNOSTIC.txt"
)

STAMP = utc_stamp()
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"

INPUTS_DIR = RUN_ROOT / "inputs"
RUN0_DIR = RUN_ROOT / "run0_repeats"
OFFLINE_DIR = RUN_ROOT / "offline_exact_grades"
TABLES_DIR = RUN_ROOT / "tables"
FIGURES_DIR = RUN_ROOT / "figures"
REPORTS_DIR = RUN_ROOT / "reports"
PROVENANCE_DIR = RUN_ROOT / "provenance"

STATUS_FILE = RUN_ROOT / "STATUS_v032d.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v032d.json"
REPORT_MD = (
    REPORTS_DIR / "selection_interface_diagnostic_v032d.md"
)
BREAK_TABLE = TABLES_DIR / "captured_break_configurations_v032d.tsv"
RUN0_TABLE = TABLES_DIR / "selection_enabled_run0_repeats_v032d.tsv"
FIGURE_MANIFEST = FIGURES_DIR / "figure_manifest_v032d.tsv"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v032d.tsv"

EXPECTED_V028_STATUS = (
    "PASS_EQUAL_BUDGET_L12_MODELS_LOCKED_READY_FOR_FROZEN_AUDIT"
)
EXPECTED_V029_STATUS = (
    "PASS_FROZEN_AUDIT21_EVALUATED_NO_POST_AUDIT_TUNING"
)
EXPECTED_V030R_STATUS = (
    "PASS_PRIMARY_METRIC_PROTOCOL_RECOVERY_AND_FIGURES"
)
EXPECTED_V031R_STATUS = (
    "PASS_SECONDARY_MTP_NEB_INTERPRETATION_RECOVERY"
)
EXPECTED_V032_STATUS = "PASS_TARGETED_MD_DIAGNOSTICS_COMPLETED"
EXPECTED_V032R_STATUS = (
    "PASS_TARGETED_MD_INTERPRETATION_RECOVERY_NO_MD_DATA"
)

EXPECTED_TARGETED_MODEL_SHA256 = (
    "30175dae673d63e0b318e5e3ba311a9f61afe88929a5d19c69a744a47aeef99f"
)

SELECT_THRESHOLD = 2.0
BREAK_THRESHOLD = 10.0
RUN0_REPEATS_PER_SIDE = 3

TRAJECTORIES = [
    ("T100_left", 100.0, "left", 42101),
    ("T100_right", 100.0, "right", 42102),
    ("T300_left", 300.0, "left", 42301),
    ("T300_right", 300.0, "right", 42302),
    ("T500_left", 500.0, "left", 42501),
    ("T500_right", 500.0, "right", 42502),
]

BREAK_GRADE_PATTERN = re.compile(
    r"Breaking threshold exceeded\s*"
    r"\(MV-grade:\s*([0-9eE+\-.]+)\)"
)
ANY_GRADE_PATTERN = re.compile(
    r"MV-grade:\s*([0-9eE+\-.]+)"
)

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V032D_PREFLIGHT_ONLY", "0") == "1"
)


def maybe_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def extract_grade(text: str, *, break_only: bool) -> float:
    pattern = BREAK_GRADE_PATTERN if break_only else ANY_GRADE_PATTERN
    matches = pattern.findall(text)
    if not matches:
        return math.nan
    return finite_float(matches[-1], "parsed online grade")


def cfg_mv_grade(block: CFGBlock) -> float:
    for key in ("MV_grade", "mv_grade", "MV-Grade"):
        if key in block.features:
            return finite_float(
                block.features[key],
                f"preselected feature {key}",
            )
    return math.nan


def coordinate_delta(
    first: np.ndarray,
    second: np.ndarray,
) -> tuple[float, float]:
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    if first.shape != second.shape:
        raise RuntimeError(
            f"coordinate shape mismatch {first.shape} vs {second.shape}"
        )
    difference = first - second
    return (
        float(np.max(np.abs(difference))),
        float(np.sqrt(np.mean(difference ** 2))),
    )


def normalize_mlip_types(types: list[int]) -> list[int]:
    values = [int(value) for value in types]
    expected_multiset = sorted(EXPECTED_TYPES)
    if sorted(values) == expected_multiset:
        return values
    shifted = [value - 1 for value in values]
    if sorted(shifted) == expected_multiset:
        return shifted
    raise RuntimeError(
        f"cannot normalize CFG atom types {values}; "
        f"expected multiset {expected_multiset} or one-based equivalent"
    )


def pair_distance_matrix(positions: np.ndarray) -> np.ndarray:
    positions = np.asarray(positions, dtype=float)
    difference = positions[:, None, :] - positions[None, :, :]
    return np.sqrt(np.sum(difference ** 2, axis=2))


def minimum_image_to_reference(
    mobile: np.ndarray,
    reference: np.ndarray,
    box_length: float = 16.0,
) -> np.ndarray:
    mobile = np.asarray(mobile, dtype=float).copy()
    reference = np.asarray(reference, dtype=float)
    mobile += np.round((reference - mobile) / box_length) * box_length
    return mobile


def canonicalize_cfg_to_endpoint(
    block: CFGBlock,
    endpoint: CFGBlock,
    label: str,
) -> dict[str, Any]:
    if block.size != NAT:
        raise RuntimeError(f"{label}: Size={block.size}, expected {NAT}")
    normalized_types = normalize_mlip_types(block.types)
    endpoint_types = list(EXPECTED_TYPES)

    candidates: list[tuple[str, list[int]]] = []
    identity = list(range(NAT))
    if [normalized_types[index] for index in identity] == endpoint_types:
        candidates.append(("raw_order", identity))

    ids = [int(value) for value in block.ids]
    if len(set(ids)) == NAT and (
        set(ids) == set(range(1, NAT + 1))
        or set(ids) == set(range(NAT))
    ):
        by_id = sorted(range(NAT), key=lambda index: ids[index])
        if [normalized_types[index] for index in by_id] == endpoint_types:
            candidates.append(("sorted_by_atom_id", by_id))

    source_by_type = {
        atom_type: [
            index
            for index, value in enumerate(normalized_types)
            if value == atom_type
        ]
        for atom_type in sorted(set(EXPECTED_TYPES))
    }
    target_by_type = {
        atom_type: [
            index
            for index, value in enumerate(endpoint_types)
            if value == atom_type
        ]
        for atom_type in sorted(set(EXPECTED_TYPES))
    }

    per_type_permutations = []
    type_order = sorted(source_by_type)
    for atom_type in type_order:
        source = source_by_type[atom_type]
        target = target_by_type[atom_type]
        if len(source) != len(target):
            raise RuntimeError(
                f"{label}: type {atom_type} count mismatch "
                f"{len(source)} vs {len(target)}"
            )
        per_type_permutations.append(
            list(itertools.permutations(source, len(target)))
        )

    for combination in itertools.product(*per_type_permutations):
        order = [-1] * NAT
        for atom_type, chosen_sources in zip(type_order, combination):
            for target_index, source_index in zip(
                target_by_type[atom_type],
                chosen_sources,
            ):
                order[target_index] = source_index
        if any(index < 0 for index in order):
            raise RuntimeError(f"{label}: incomplete species assignment")
        candidates.append(("species_assignment", order))

    unique_candidates: dict[tuple[int, ...], str] = {}
    for mode, order in candidates:
        unique_candidates.setdefault(tuple(order), mode)

    reference = np.asarray(endpoint.positions, dtype=float)
    reference_pair = pair_distance_matrix(reference)
    ranked: list[dict[str, Any]] = []

    for order_tuple, mode in unique_candidates.items():
        order = list(order_tuple)
        mobile = np.asarray(block.positions, dtype=float)[order]
        mobile_unwrapped = minimum_image_to_reference(
            mobile,
            reference,
        )
        aligned, kabsch_rmsd = mass_weighted_kabsch_align(
            mobile_unwrapped,
            reference,
        )
        aligned_max, aligned_rms = coordinate_delta(aligned, reference)
        pair_delta = float(
            np.max(
                np.abs(
                    pair_distance_matrix(mobile_unwrapped)
                    - reference_pair
                )
            )
        )
        ranked.append(
            {
                "mode": mode,
                "order": order,
                "positions": mobile_unwrapped,
                "aligned_positions": aligned,
                "kabsch_rmsd_ang": kabsch_rmsd,
                "aligned_max_abs_ang": aligned_max,
                "aligned_rms_ang": aligned_rms,
                "pair_distance_max_abs_delta_ang": pair_delta,
            }
        )

    if not ranked:
        raise RuntimeError(f"{label}: no atom-order candidates")
    ranked.sort(
        key=lambda item: (
            item["pair_distance_max_abs_delta_ang"],
            item["kabsch_rmsd_ang"],
            item["aligned_max_abs_ang"],
        )
    )
    best = ranked[0]
    best["raw_ids"] = ids
    best["raw_types"] = list(block.types)
    best["normalized_raw_types"] = normalized_types
    best["candidate_count"] = len(ranked)
    return best


def load_upstream() -> dict[str, Any]:
    v028 = resolve_attempt(
        V028_POINTER,
        "STATUS_v028.txt",
        EXPECTED_V028_STATUS,
        "v028",
    )
    v029 = resolve_attempt(
        V029_POINTER,
        "STATUS_v029.txt",
        EXPECTED_V029_STATUS,
        "v029",
    )
    v030r = resolve_attempt(
        V030R_POINTER,
        "STATUS_v030r.txt",
        EXPECTED_V030R_STATUS,
        "v030r",
    )
    v031r = resolve_attempt(
        V031R_POINTER,
        "STATUS_v031r.txt",
        EXPECTED_V031R_STATUS,
        "v031r",
    )
    v032 = resolve_attempt(
        V032_POINTER,
        "STATUS_v032.txt",
        EXPECTED_V032_STATUS,
        "v032 immutable MD attempt",
    )
    v032r = resolve_attempt(
        V032R_POINTER,
        "STATUS_v032r.txt",
        EXPECTED_V032R_STATUS,
        "v032r superseded interpretation",
    )

    model = require_file(
        v028
        / "models"
        / "targeted"
        / "pot_targeted60_l12_v001.mtp",
        "targeted model",
    )
    require_hash(model, EXPECTED_TARGETED_MODEL_SHA256, "targeted model")

    train = require_file(
        v028 / "inputs" / "train_targeted_v001.cfg",
        "targeted train60",
    )
    original_state = require_file(
        v032 / "grades" / "state_targeted_v032.als",
        "original v032 active-learning state",
    )
    trajectory_summary = require_file(
        v032 / "reports" / "trajectory_summary_v032.tsv",
        "v032 trajectory summary",
    )

    audit_cfg = require_file(
        v029 / "inputs" / "frozen_audit21_labels_v029.cfg",
        "frozen audit labels",
    )
    audit_manifest = require_file(
        v029 / "inputs" / "frozen_audit21_manifest_v029.tsv",
        "frozen audit manifest",
    )

    blocks = read_cfg(audit_cfg)
    by_id = {
        block.features.get("audit_id", ""): block
        for block in blocks
        if block.features.get("audit_id", "")
    }
    manifest_rows = [
        row
        for row in read_tsv(audit_manifest)
        if row.get("subset", "") == "neb9"
    ]
    manifest_rows.sort(key=lambda row: int(row["subset_index"]))
    if len(manifest_rows) != 9:
        raise RuntimeError("cannot reconstruct NEB9 endpoints")
    left = by_id[manifest_rows[0]["audit_id"]]
    right = by_id[manifest_rows[-1]["audit_id"]]

    require_file(MLP, "mlp executable")
    require_file(LAMMPS, "LAMMPS executable")

    trajectory_rows = read_tsv(trajectory_summary)
    if len(trajectory_rows) != 6:
        raise RuntimeError(
            f"v032 trajectory count={len(trajectory_rows)}, expected 6"
        )
    trajectory_by_id = {
        row["trajectory_id"]: row for row in trajectory_rows
    }

    return {
        "v028": v028,
        "v029": v029,
        "v030r": v030r,
        "v031r": v031r,
        "v032": v032,
        "v032r": v032r,
        "model": model,
        "train": train,
        "original_state": original_state,
        "trajectory_summary": trajectory_summary,
        "left": left,
        "right": right,
        "trajectory_by_id": trajectory_by_id,
    }


def inspect_original_breaks(
    upstream: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for trajectory_id, temperature, side, seed in TRAJECTORIES:
        directory = (
            upstream["v032"] / "trajectories" / trajectory_id
        )
        preselected_path = require_file(
            directory / "preselected.cfg",
            f"{trajectory_id} preselected configuration",
        )
        stdout_path = require_file(
            directory / "lammps.stdout",
            f"{trajectory_id} stdout",
        )
        dump_path = require_file(
            directory / "trajectory.lammpstrj",
            f"{trajectory_id} dump",
        )

        preselected = read_cfg(preselected_path)
        if len(preselected) != 1:
            raise RuntimeError(
                f"{trajectory_id}: preselected count={len(preselected)}, "
                "expected 1"
            )
        break_block = preselected[0]

        frames = parse_lammps_custom_dump(dump_path)
        if len(frames) != 1:
            raise RuntimeError(
                f"{trajectory_id}: dump frame count={len(frames)}, "
                "expected 1"
            )
        step0 = frames[0]
        if int(step0["timestep"]) != 0:
            raise RuntimeError(
                f"{trajectory_id}: only captured frame is not step 0"
            )

        endpoint = (
            upstream["left"] if side == "left" else upstream["right"]
        )
        canonical = canonicalize_cfg_to_endpoint(
            break_block,
            endpoint,
            trajectory_id,
        )
        canonical_positions = canonical["positions"]
        aligned_break = canonical["aligned_positions"]

        endpoint_max, endpoint_rms = coordinate_delta(
            aligned_break,
            endpoint.positions,
        )

        aligned_to_dump, dump_kabsch_rms = mass_weighted_kabsch_align(
            minimum_image_to_reference(
                canonical_positions,
                step0["positions"],
            ),
            step0["positions"],
        )
        dump_max, dump_rms = coordinate_delta(
            aligned_to_dump,
            step0["positions"],
        )

        aligned_dump_endpoint, dump_endpoint_kabsch_rms = (
            mass_weighted_kabsch_align(
                minimum_image_to_reference(
                    step0["positions"],
                    endpoint.positions,
                ),
                endpoint.positions,
            )
        )
        dump_endpoint_max, dump_endpoint_rms = coordinate_delta(
            aligned_dump_endpoint,
            endpoint.positions,
        )

        stdout = stdout_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        original_online_grade = extract_grade(
            stdout,
            break_only=True,
        )
        if not math.isfinite(original_online_grade):
            raise RuntimeError(
                f"{trajectory_id}: online break grade missing"
            )

        metrics = geometry_metrics(canonical_positions)
        canonical_block = CFGBlock(
            order=break_block.order,
            size=NAT,
            cell=np.asarray(endpoint.cell, dtype=float).copy(),
            ids=list(range(1, NAT + 1)),
            types=list(EXPECTED_TYPES),
            positions=np.asarray(canonical_positions, dtype=float).copy(),
            forces=None,
            energy=None,
            features=dict(break_block.features),
            feature_rows=list(break_block.feature_rows),
            raw=break_block.raw,
        )
        result = {
            "trajectory_id": trajectory_id,
            "temperature_K": temperature,
            "side": side,
            "seed": seed,
            "original_online_break_grade": original_online_grade,
            "preselected_feature_mv_grade":
                cfg_mv_grade(break_block),
            "canonicalization_mode": canonical["mode"],
            "canonicalization_candidate_count":
                canonical["candidate_count"],
            "raw_atom_ids": ",".join(
                str(value) for value in canonical["raw_ids"]
            ),
            "raw_atom_types": ",".join(
                str(value) for value in canonical["raw_types"]
            ),
            "canonical_order_zero_based": ",".join(
                str(value) for value in canonical["order"]
            ),
            "break_vs_endpoint_max_abs_ang": endpoint_max,
            "break_vs_endpoint_rms_ang": endpoint_rms,
            "break_vs_endpoint_kabsch_rmsd_ang":
                canonical["kabsch_rmsd_ang"],
            "break_vs_endpoint_pair_distance_max_abs_delta_ang":
                canonical["pair_distance_max_abs_delta_ang"],
            "break_vs_dump0_max_abs_ang": dump_max,
            "break_vs_dump0_rms_ang": dump_rms,
            "break_vs_dump0_kabsch_rmsd_ang": dump_kabsch_rms,
            "dump0_vs_endpoint_max_abs_ang": dump_endpoint_max,
            "dump0_vs_endpoint_rms_ang": dump_endpoint_rms,
            "dump0_vs_endpoint_kabsch_rmsd_ang":
                dump_endpoint_kabsch_rms,
            "break_qpt_ang": metrics["qpt_ang"],
            "break_roo_ang": metrics["roo_ang"],
            "break_minimum_pair_ang": metrics[
                "minimum_pair_ang"
            ],
            "break_maximum_span_ang": metrics[
                "maximum_span_ang"
            ],
            "preselected_path": preselected_path,
            "break_block": canonical_block,
        }
        results.append(result)

    return results


def write_mlip_ini(
    path: Path,
    model: Path,
    state_path: Path,
    preselected_path: Path,
    selection_log: Path,
) -> None:
    path.write_text(
        "\n".join(
            [
                f"mtp-filename {model}",
                "calculate-efs TRUE",
                "select TRUE",
                f"select:threshold {SELECT_THRESHOLD:.8f}",
                f"select:threshold-break {BREAK_THRESHOLD:.8f}",
                f"select:save-selected {preselected_path}",
                f"select:load-state {state_path}",
                f"select:log {selection_log}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_selection_enabled_run0(
    upstream: dict[str, Any],
    side: str,
    repeat: int,
) -> dict[str, Any]:
    endpoint = (
        upstream["left"] if side == "left" else upstream["right"]
    )
    directory = RUN0_DIR / f"{side}_repeat_{repeat:02d}"
    directory.mkdir(parents=True, exist_ok=True)

    data_path = directory / "endpoint.data"
    state_path = directory / "state_fresh_copy.als"
    mlip_ini = directory / "mlip.ini"
    input_path = directory / "in.run0"
    log_path = directory / "log.run0"
    dump_path = directory / "run0.lammpstrj"
    preselected_path = directory / "preselected.cfg"
    selection_log = directory / "selection.log"

    write_lammps_data(data_path, endpoint.positions)
    shutil.copy2(upstream["original_state"], state_path)
    source_state_sha = sha256(upstream["original_state"])
    copied_state_sha_before = sha256(state_path)

    write_mlip_ini(
        mlip_ini,
        upstream["model"],
        state_path,
        preselected_path,
        selection_log,
    )
    input_path.write_text(
        f"""units metal
atom_style atomic
boundary p p p
read_data {data_path}
pair_style mlip {mlip_ini}
pair_coeff * *
neighbor 1.0 bin
neigh_modify every 1 delay 0 check yes
thermo_style custom step time temp pe ke etotal
thermo 1
thermo_modify format float %.16g flush yes
dump probe all custom 1 {dump_path} id type x y z fx fy fz
dump_modify probe sort id first yes format float %.16g
run 0
undump probe
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(LAMMPS), "-in", str(input_path), "-log", str(log_path)],
        cwd=directory,
        env={**os.environ, "OMP_NUM_THREADS": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (directory / "lammps.stdout").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (directory / "lammps.stderr").write_text(
        completed.stderr,
        encoding="utf-8",
    )

    combined = completed.stdout + "\n" + completed.stderr
    if log_path.is_file():
        combined += "\n" + log_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

    break_detected = (
        "Breaking threshold exceeded" in combined
    )
    online_break_grade = extract_grade(
        combined,
        break_only=True,
    )
    any_online_grade = extract_grade(
        combined,
        break_only=False,
    )

    frames = (
        parse_lammps_custom_dump(dump_path)
        if dump_path.is_file()
        else []
    )
    if frames:
        run0_positions = frames[-1]["positions"]
        run0_step = int(frames[-1]["timestep"])
        coordinate_max, coordinate_rms = coordinate_delta(
            run0_positions,
            endpoint.positions,
        )
    else:
        run0_step = -1
        coordinate_max = math.nan
        coordinate_rms = math.nan

    selected_blocks = (
        read_cfg(preselected_path)
        if preselected_path.is_file()
        else []
    )
    preselected_feature_grades = [
        cfg_mv_grade(block) for block in selected_blocks
    ]
    finite_feature_grades = [
        value
        for value in preselected_feature_grades
        if math.isfinite(value)
    ]

    copied_state_sha_after = (
        sha256(state_path) if state_path.is_file() else ""
    )

    return {
        "side": side,
        "repeat": repeat,
        "returncode": completed.returncode,
        "break_detected": break_detected,
        "online_break_grade": online_break_grade,
        "any_online_grade": any_online_grade,
        "preselected_count": len(selected_blocks),
        "preselected_feature_grade":
            finite_feature_grades[-1]
            if finite_feature_grades
            else math.nan,
        "dump_frame_count": len(frames),
        "dump_last_step": run0_step,
        "run0_vs_endpoint_max_abs_ang": coordinate_max,
        "run0_vs_endpoint_rms_ang": coordinate_rms,
        "source_state_sha256": source_state_sha,
        "copied_state_sha256_before": copied_state_sha_before,
        "copied_state_sha256_after": copied_state_sha_after,
        "state_file_changed":
            copied_state_sha_before != copied_state_sha_after,
        "directory": directory,
    }


def offline_grade_single(
    model: Path,
    train: Path,
    positions: np.ndarray,
    diagnostic_id: str,
) -> dict[str, Any]:
    directory = OFFLINE_DIR / diagnostic_id
    directory.mkdir(parents=True, exist_ok=True)

    input_cfg = directory / "geometry.cfg"
    output_cfg = directory / "graded.cfg"
    state_path = directory / "state.als"

    reference = cfg_from_positions(
        positions,
        key="diagnostic_id",
        value=diagnostic_id,
    )
    reference.features.update(
        {
            "technical_diagnostic": "true",
            "diagnostic_id": diagnostic_id,
        }
    )
    reference.feature_rows = list(reference.features.items())
    write_cfg(
        input_cfg,
        [reference],
        include_energy=False,
        include_forces=False,
    )

    completed = subprocess.run(
        [
            str(MLP),
            "calc-grade",
            str(model),
            str(train),
            str(input_cfg),
            str(output_cfg),
            f"--als-filename={state_path}",
        ],
        cwd=directory,
        env={**os.environ, "OMP_NUM_THREADS": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (directory / "calc_grade.stdout").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (directory / "calc_grade.stderr").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"offline calc-grade failed for {diagnostic_id}, "
            f"rc={completed.returncode}"
        )

    produced = read_cfg(output_cfg)
    recovered = recover_blocks_by_feature_or_geometry(
        produced,
        [reference],
        "diagnostic_id",
        f"v032d offline grade {diagnostic_id}",
    )
    block = recovered[diagnostic_id]
    grade = finite_float(
        block.features.get("MV_grade", ""),
        f"offline grade {diagnostic_id}",
    )
    return {
        "diagnostic_id": diagnostic_id,
        "offline_mv_grade": grade,
        "state_sha256": sha256(state_path),
        "graded_cfg_sha256": sha256(output_cfg),
        "directory": directory,
    }


def classify(
    break_rows: list[dict[str, Any]],
    run0_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    all_run0_no_break = all(
        not row["break_detected"] for row in run0_rows
    )
    all_run0_rc_zero = all(
        row["returncode"] == 0 for row in run0_rows
    )
    all_run0_exact_endpoint = all(
        math.isfinite(row["run0_vs_endpoint_max_abs_ang"])
        and row["run0_vs_endpoint_max_abs_ang"] <= 1.0e-12
        for row in run0_rows
    )

    all_break_configs_captured_after_coordinate_change = all(
        row["break_vs_dump0_max_abs_ang"] > 1.0e-12
        and row["break_vs_endpoint_max_abs_ang"] > 1.0e-12
        for row in break_rows
    )
    all_exact_break_offline_above_threshold = all(
        row["offline_exact_break_mv_grade"] > BREAK_THRESHOLD
        for row in break_rows
    )
    all_online_above_threshold = all(
        row["original_online_break_grade"] > BREAK_THRESHOLD
        for row in break_rows
    )
    threshold_class_agreement = all(
        (
            row["original_online_break_grade"] > BREAK_THRESHOLD
        )
        == (
            row["offline_exact_break_mv_grade"] > BREAK_THRESHOLD
        )
        for row in break_rows
    )

    if (
        all_run0_no_break
        and all_run0_rc_zero
        and all_run0_exact_endpoint
        and all_break_configs_captured_after_coordinate_change
        and all_exact_break_offline_above_threshold
        and all_online_above_threshold
        and threshold_class_agreement
    ):
        outcome = (
            "first_integrator_step_extrapolation_confirmed_"
            "selection_interface_consistent"
        )
        selection_interface_consistent = True
        first_step_extrapolation_confirmed = True
        unresolved = False
    elif (
        all_run0_no_break
        and all_run0_rc_zero
        and all_break_configs_captured_after_coordinate_change
        and not all_exact_break_offline_above_threshold
    ):
        outcome = (
            "captured_break_configuration_grade_inconsistency_confirmed"
        )
        selection_interface_consistent = False
        first_step_extrapolation_confirmed = False
        unresolved = False
    elif any(row["break_detected"] for row in run0_rows):
        run0_break_grades = [
            row["online_break_grade"]
            for row in run0_rows
            if math.isfinite(row["online_break_grade"])
        ]
        grade_spread = (
            max(run0_break_grades) - min(run0_break_grades)
            if run0_break_grades
            else math.nan
        )
        endpoint_offline = [
            row["offline_endpoint_mv_grade"]
            for row in break_rows
        ]
        if (
            run0_break_grades
            and all(value > BREAK_THRESHOLD for value in run0_break_grades)
            and all(value <= BREAK_THRESHOLD for value in endpoint_offline)
        ):
            outcome = "endpoint_run0_grade_inconsistency_confirmed"
            selection_interface_consistent = False
            first_step_extrapolation_confirmed = False
            unresolved = False
        else:
            outcome = "run0_endpoint_break_mixed_or_unresolved"
            selection_interface_consistent = False
            first_step_extrapolation_confirmed = False
            unresolved = True
    else:
        outcome = "mixed_or_unresolved_selection_diagnostic"
        selection_interface_consistent = False
        first_step_extrapolation_confirmed = False
        unresolved = True

    return {
        "outcome": outcome,
        "selection_interface_consistent":
            selection_interface_consistent,
        "first_step_extrapolation_confirmed":
            first_step_extrapolation_confirmed,
        "unresolved": unresolved,
        "all_run0_no_break": all_run0_no_break,
        "all_run0_rc_zero": all_run0_rc_zero,
        "all_run0_exact_endpoint": all_run0_exact_endpoint,
        "all_break_configs_captured_after_coordinate_change":
            all_break_configs_captured_after_coordinate_change,
        "all_exact_break_offline_above_threshold":
            all_exact_break_offline_above_threshold,
        "threshold_class_agreement":
            threshold_class_agreement,
    }


def save_figure(
    figure: plt.Figure,
    stem: str,
    description: str,
    manifest: list[dict[str, Any]],
) -> None:
    png = FIGURES_DIR / f"{stem}.png"
    pdf = FIGURES_DIR / f"{stem}.pdf"
    figure.tight_layout()
    figure.savefig(png, dpi=220, bbox_inches="tight")
    figure.savefig(pdf, bbox_inches="tight")
    plt.close(figure)
    manifest.append(
        {
            "figure": stem,
            "description": description,
            "png": png,
            "png_sha256": sha256(png),
            "pdf": pdf,
            "pdf_sha256": sha256(pdf),
        }
    )


def main() -> None:
    upstream = load_upstream()
    original_breaks = inspect_original_breaks(upstream)

    preflight_displacements = [
        row["break_vs_endpoint_max_abs_ang"]
        for row in original_breaks
    ]
    preflight_pair_deltas = [
        row["break_vs_endpoint_pair_distance_max_abs_delta_ang"]
        for row in original_breaks
    ]
    captured_all = len(original_breaks) == 6
    changed_all = all(value > 1.0e-12 for value in preflight_displacements)

    if PREFLIGHT_ONLY:
        print(
            "PASS_V032D_PREFLIGHT_SELECTION_DIAGNOSTIC_NO_CALCULATIONS"
        )
        print(f"source v028:              {upstream['v028']}")
        print(f"source v029:              {upstream['v029']}")
        print(f"source v030r:             {upstream['v030r']}")
        print(f"source v031r:             {upstream['v031r']}")
        print(f"immutable source v032:    {upstream['v032']}")
        print(f"superseded source v032r:  {upstream['v032r']}")
        print(
            "captured break configs:  "
            f"{len(original_breaks)}/6"
        )
        print(
            "break vs endpoint max:   "
            f"{min(preflight_displacements):.12e} to "
            f"{max(preflight_displacements):.12e} A "
            "(atom-ID/species canonicalized + Kabsch)"
        )
        print(
            "pair-distance delta max: "
            f"{min(preflight_pair_deltas):.12e} to "
            f"{max(preflight_pair_deltas):.12e} A"
        )
        print(
            "canonicalization modes:  "
            + ", ".join(
                f"{row['trajectory_id']}={row['canonicalization_mode']}"
                for row in original_breaks
            )
        )
        print(
            "all differ from step0:   "
            f"{all(row['break_vs_dump0_max_abs_ang'] > 1.0e-12 for row in original_breaks)}"
        )
        print(
            "original online grades:  "
            f"{min(row['original_online_break_grade'] for row in original_breaks):.6f} "
            f"to "
            f"{max(row['original_online_break_grade'] for row in original_breaks):.6f}"
        )
        print(
            "diagnostic plan:         "
            "6 selection-enabled run0 repeats + "
            "8 exact offline calc-grade evaluations"
        )
        print(
            "one-step rerun:          NOT NEEDED; "
            "all six breaking configurations are already captured"
        )
        print("scientific MD retry:      FORBIDDEN")
        print("attempt directory:        NOT CREATED")
        print("LAMMPS run0/MLP:          NOT EXECUTED")
        print("pw.x/neb.x/train:         NOT EXECUTED")
        if not captured_all:
            raise RuntimeError("not all break configurations captured")
        if max(preflight_pair_deltas) > 0.25:
            raise RuntimeError(
                "captured preselected.cfg cannot be mapped reliably to "
                "the endpoint: internal pair-distance change exceeds "
                "0.25 A after atom-order canonicalization"
            )
        if not changed_all:
            print(
                "WARNING: at least one captured break configuration "
                "equals its endpoint within 1e-12 A after alignment"
            )
        return

    if RUN_ROOT.exists():
        raise RuntimeError(f"attempt already exists: {RUN_ROOT}")

    for directory in (
        INPUTS_DIR,
        RUN0_DIR,
        OFFLINE_DIR,
        TABLES_DIR,
        FIGURES_DIR,
        REPORTS_DIR,
        PROVENANCE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    for path in (
        upstream["model"],
        upstream["train"],
        upstream["original_state"],
        upstream["trajectory_summary"],
    ):
        shutil.copy2(path, INPUTS_DIR / path.name)

    shutil.copy2(
        Path(__file__).resolve(),
        PROVENANCE_DIR / Path(__file__).name,
    )
    helper = Path(__file__).resolve().with_name(
        "strict_postaudit_common_v001.py"
    )
    if helper.is_file():
        shutil.copy2(helper, PROVENANCE_DIR / helper.name)

    print(
        f"[{utc_now()}] Running six selection-enabled run0 probes "
        "with fresh copies of the original ALS state."
    )
    run0_rows: list[dict[str, Any]] = []
    for side in ("left", "right"):
        for repeat in range(1, RUN0_REPEATS_PER_SIDE + 1):
            row = run_selection_enabled_run0(
                upstream,
                side,
                repeat,
            )
            run0_rows.append(row)
            print(
                f"[{utc_now()}] run0 {side} repeat {repeat}: "
                f"rc={row['returncode']}; "
                f"break={row['break_detected']}; "
                f"preselected={row['preselected_count']}; "
                f"coord_delta={row['run0_vs_endpoint_max_abs_ang']:.3e} A."
            )

    print(
        f"[{utc_now()}] Calculating independent offline grades for "
        "the two endpoints and six exact captured break configurations."
    )
    offline_by_id: dict[str, dict[str, Any]] = {}
    for side in ("left", "right"):
        endpoint = (
            upstream["left"] if side == "left" else upstream["right"]
        )
        diagnostic_id = f"endpoint_{side}"
        offline_by_id[diagnostic_id] = offline_grade_single(
            upstream["model"],
            upstream["train"],
            endpoint.positions,
            diagnostic_id,
        )
        print(
            f"[{utc_now()}] {diagnostic_id}: "
            f"offline grade="
            f"{offline_by_id[diagnostic_id]['offline_mv_grade']:.6f}."
        )

    for row in original_breaks:
        diagnostic_id = f"break_{row['trajectory_id']}"
        offline_by_id[diagnostic_id] = offline_grade_single(
            upstream["model"],
            upstream["train"],
            row["break_block"].positions,
            diagnostic_id,
        )
        row["offline_exact_break_mv_grade"] = offline_by_id[
            diagnostic_id
        ]["offline_mv_grade"]
        row["offline_endpoint_mv_grade"] = offline_by_id[
            f"endpoint_{row['side']}"
        ]["offline_mv_grade"]
        row["online_over_offline_exact"] = (
            row["original_online_break_grade"]
            / row["offline_exact_break_mv_grade"]
        )
        row["threshold_class_agreement"] = (
            row["original_online_break_grade"] > BREAK_THRESHOLD
        ) == (
            row["offline_exact_break_mv_grade"] > BREAK_THRESHOLD
        )
        print(
            f"[{utc_now()}] {diagnostic_id}: online="
            f"{row['original_online_break_grade']:.6f}; "
            f"offline exact="
            f"{row['offline_exact_break_mv_grade']:.6f}; "
            f"delta endpoint="
            f"{row['break_vs_endpoint_max_abs_ang']:.3e} A."
        )

    for row in original_breaks:
        row.pop("break_block", None)

    result = classify(original_breaks, run0_rows)

    write_tsv(BREAK_TABLE, original_breaks)
    write_tsv(RUN0_TABLE, run0_rows)

    manifest: list[dict[str, Any]] = []

    labels = [row["trajectory_id"] for row in original_breaks]
    x = np.arange(len(labels))
    online = [
        row["original_online_break_grade"] for row in original_breaks
    ]
    offline_exact = [
        row["offline_exact_break_mv_grade"] for row in original_breaks
    ]
    offline_endpoint = [
        row["offline_endpoint_mv_grade"] for row in original_breaks
    ]

    figure, axis = plt.subplots(figsize=(8.3, 5.0))
    width = 0.25
    axis.bar(
        x - width,
        online,
        width,
        label="original online break",
    )
    axis.bar(
        x,
        offline_exact,
        width,
        label="offline exact break config",
    )
    axis.bar(
        x + width,
        offline_endpoint,
        width,
        label="offline endpoint",
    )
    axis.axhline(
        BREAK_THRESHOLD,
        linewidth=1.0,
        linestyle="--",
        label="break threshold",
    )
    axis.set_yscale("log")
    axis.set_xticks(x, labels, rotation=30, ha="right")
    axis.set_ylabel("MaxVol grade (log scale)")
    axis.set_title(
        "Online break grades versus exact captured configurations"
    )
    axis.legend()
    axis.grid(True, axis="y", alpha=0.25)
    save_figure(
        figure,
        "figure_01_exact_break_grade_comparison",
        "Original LAMMPS break grades, offline grades of the exact "
        "preselected break configurations, and endpoint grades.",
        manifest,
    )

    figure, axis = plt.subplots(figsize=(7.5, 5.0))
    for side in ("left", "right"):
        selected = [
            row for row in original_breaks if row["side"] == side
        ]
        axis.scatter(
            [
                row["break_vs_endpoint_max_abs_ang"]
                for row in selected
            ],
            [
                row["offline_exact_break_mv_grade"]
                for row in selected
            ],
            label=side,
        )
    axis.axhline(
        BREAK_THRESHOLD,
        linewidth=1.0,
        linestyle="--",
        label="break threshold",
    )
    axis.set_xlabel(
        "Maximum coordinate displacement from endpoint (Å)"
    )
    axis.set_ylabel("Offline grade of exact break configuration")
    axis.set_yscale("log")
    axis.set_title(
        "Captured first-step displacement and extrapolation grade"
    )
    axis.legend()
    axis.grid(True, alpha=0.25)
    save_figure(
        figure,
        "figure_02_break_displacement_vs_exact_grade",
        "Displacement of each captured breaking configuration from its "
        "endpoint versus its independent offline grade.",
        manifest,
    )

    write_tsv(
        FIGURE_MANIFEST,
        manifest,
        [
            "figure",
            "description",
            "png",
            "png_sha256",
            "pdf",
            "pdf_sha256",
        ],
    )

    status = "PASS_V032_SELECTION_INTERFACE_DIAGNOSTIC_COMPLETED"
    STATUS_FILE.write_text(status + "\n", encoding="utf-8")

    summary = {
        "created_utc": utc_now(),
        "status": status,
        "implementation_id": IMPLEMENTATION_ID,
        "run_root": str(RUN_ROOT),
        "analysis_class":
            "post_audit_technical_selection_interface_diagnostic",
        "sources": {
            "v028": str(upstream["v028"]),
            "v029": str(upstream["v029"]),
            "v030r": str(upstream["v030r"]),
            "v031r": str(upstream["v031r"]),
            "v032_immutable": str(upstream["v032"]),
            "v032r_superseded_interpretation": str(upstream["v032r"]),
        },
        "protocol": {
            "selection_threshold": SELECT_THRESHOLD,
            "break_threshold": BREAK_THRESHOLD,
            "run0_repeats_per_side": RUN0_REPEATS_PER_SIDE,
            "fresh_als_copy_per_run0": True,
            "integrator_steps_executed": 0,
            "scientific_md_retry": False,
            "exact_original_break_configs_reused": 6,
        },
        "result": result,
        "ranges": {
            "original_online_break_grade": [
                min(
                    row["original_online_break_grade"]
                    for row in original_breaks
                ),
                max(
                    row["original_online_break_grade"]
                    for row in original_breaks
                ),
            ],
            "offline_exact_break_grade": [
                min(
                    row["offline_exact_break_mv_grade"]
                    for row in original_breaks
                ),
                max(
                    row["offline_exact_break_mv_grade"]
                    for row in original_breaks
                ),
            ],
            "offline_endpoint_grade": [
                min(
                    row["offline_endpoint_mv_grade"]
                    for row in original_breaks
                ),
                max(
                    row["offline_endpoint_mv_grade"]
                    for row in original_breaks
                ),
            ],
            "break_vs_endpoint_max_abs_ang": [
                min(
                    row["break_vs_endpoint_max_abs_ang"]
                    for row in original_breaks
                ),
                max(
                    row["break_vs_endpoint_max_abs_ang"]
                    for row in original_breaks
                ),
            ],
        },
        "scientific_interpretation": {
            "md_trajectory_available": False,
            "thermal_stability_assessed": False,
            "kinetics_assessed": False,
            "primary_result_changed": False,
            "v032_modified": False,
            "v032r_status":
                "preserved but superseded for causal interpretation",
        },
        "execution": {
            "lammps_run0_only": True,
            "lammps_integrator_steps": 0,
            "mlp_calc_grade": True,
            "mlp_calc_efs": False,
            "mlp_train": False,
            "pw_x": False,
            "neb_x": False,
        },
        "outputs": {
            "captured_break_table": str(BREAK_TABLE),
            "run0_table": str(RUN0_TABLE),
            "report": str(REPORT_MD),
            "figures": [
                {
                    key: str(value) if isinstance(value, Path) else value
                    for key, value in item.items()
                }
                for item in manifest
            ],
        },
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    break_lines = "\n".join(
        (
            f"- {row['trajectory_id']}: displacement "
            f"{row['break_vs_endpoint_max_abs_ang']:.9e} Å; "
            f"online {row['original_online_break_grade']:.6f}; "
            f"offline exact {row['offline_exact_break_mv_grade']:.6f}; "
            f"endpoint offline {row['offline_endpoint_mv_grade']:.6f}; "
            f"threshold agreement {row['threshold_class_agreement']}."
        )
        for row in original_breaks
    )
    run0_lines = "\n".join(
        (
            f"- {row['side']} repeat {row['repeat']}: "
            f"rc={row['returncode']}; break={row['break_detected']}; "
            f"selected={row['preselected_count']}; "
            f"coordinate delta="
            f"{row['run0_vs_endpoint_max_abs_ang']:.3e} Å."
        )
        for row in run0_rows
    )

    REPORT_MD.write_text(
        f"""# v032 selection-interface diagnostic

Created UTC: {utc_now()}

Status: `{status}`

## Scope

This is a technical post-audit diagnostic. It does not repeat the
six scientific MD trajectories. It executes only selection-enabled
LAMMPS `run 0` probes and independent `mlp calc-grade` evaluations.

The six configurations written by MLIP as `preselected.cfg` are first
canonicalized to the locked atom order using atom IDs where possible
and a species-constrained assignment otherwise. Rigid translation and
rotation are removed only for displacement diagnostics. The canonical
physical geometries are used for independent offline grading.

## Selection-enabled run 0

{run0_lines}

## Exact captured break configurations

{break_lines}

## Classification

`{result['outcome']}`

Selection interface consistent:
`{result['selection_interface_consistent']}`

First-integrator-step extrapolation confirmed:
`{result['first_step_extrapolation_confirmed']}`

Unresolved:
`{result['unresolved']}`

## Scientific scope

- no usable MD trajectory was produced;
- thermal stability was not assessed;
- kinetics was not assessed;
- v029/v030r remain the primary quantitative result;
- v031r remains a secondary relaxed-path diagnostic;
- immutable v032 is preserved;
- v032r is preserved but superseded for causal interpretation.

No DFT, NEB, model training, or LAMMPS integrator step was executed.
""",
        encoding="utf-8",
    )

    write_checksums(RUN_ROOT, CHECKSUMS_TSV)
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    print()
    print(
        "PASS_V032_SELECTION_INTERFACE_DIAGNOSTIC_COMPLETED: "
        "STEP 34C v032d COMPLETED"
    )
    print()
    print(f"Run root:                  {RUN_ROOT}")
    print(f"Classification:            {result['outcome']}")
    print(
        "Selection consistent:      "
        f"{result['selection_interface_consistent']}"
    )
    print(
        "First-step extrapolation:  "
        f"{result['first_step_extrapolation_confirmed']}"
    )
    print(
        "Run0 no-break/all exact:   "
        f"{result['all_run0_no_break']} / "
        f"{result['all_run0_exact_endpoint']}"
    )
    print(
        "Exact break grades > 10:   "
        f"{result['all_exact_break_offline_above_threshold']}"
    )
    print("Scientific MD retry:       NO")
    print("LAMMPS integrator steps:   0")
    print(f"Report:                    {REPORT_MD}")
    print(f"Summary:                   {SUMMARY_JSON}")
    print()
    print(
        "LAMMPS run0 and mlp calc-grade WERE executed. "
        "No DFT, NEB, training, or MD integration was executed."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import csv
import json
import math
import os
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
    MASSES,
    ROOT,
    VERSIONS,
    copy_block,
    finite_float,
    geometry_guard_reasons,
    geometry_metrics,
    mass_weighted_kabsch_align,
    read_cfg,
    read_tsv,
    recover_blocks_by_feature_or_geometry,
    remove_rigid_force_components,
    require_file,
    require_hash,
    resolve_attempt,
    sha256,
    utc_now,
    utc_stamp,
    write_cfg,
    write_checksums,
    write_tsv,
)


IMPLEMENTATION_ID = "STEP33_V031_SECONDARY_MTP_NEB_V002"

MLP = ROOT / "01_environment" / "v001" / "software" / "bin" / "mlp"

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

VERSION_ROOT = VERSIONS / "v031_secondary_mtp_neb"
CURRENT_POINTER = VERSION_ROOT / "CURRENT_SECONDARY_MTP_NEB.txt"

STAMP = utc_stamp()
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"
INPUTS_DIR = RUN_ROOT / "inputs"
BRANCHES_DIR = RUN_ROOT / "branches"
REPORTS_DIR = RUN_ROOT / "reports"
FIGURES_DIR = RUN_ROOT / "figures"
PROVENANCE_DIR = RUN_ROOT / "provenance"

STATUS_FILE = RUN_ROOT / "STATUS_v031.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v031.json"
REPORT_MD = REPORTS_DIR / "secondary_mtp_neb_report_v031.md"
COMPARISON_TSV = REPORTS_DIR / "secondary_mtp_neb_comparison_v031.tsv"
PROFILE_TSV = REPORTS_DIR / "secondary_mtp_neb_profiles_v031.tsv"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v031.tsv"

EXPECTED_V028_STATUS = (
    "PASS_EQUAL_BUDGET_L12_MODELS_LOCKED_READY_FOR_FROZEN_AUDIT"
)
EXPECTED_V029_STATUS = (
    "PASS_FROZEN_AUDIT21_EVALUATED_NO_POST_AUDIT_TUNING"
)
EXPECTED_V030R_STATUS = "PASS_PRIMARY_METRIC_PROTOCOL_RECOVERY_AND_FIGURES"

EXPECTED_BASIN_MODEL_SHA256 = (
    "45d80443c5f62cdfa30bbd1512cf58e31cd16fe2bb0b50cec147a92350d7a7ff"
)
EXPECTED_TARGETED_MODEL_SHA256 = (
    "30175dae673d63e0b318e5e3ba311a9f61afe88929a5d19c69a744a47aeef99f"
)

IMAGE_COUNT = 9
K_SPRING_EV_ANG2 = 0.10
FMAX_EV_ANG = 0.030
CONSECUTIVE_REQUIRED = 5
MAX_ITERATIONS = 1200
CLIMB_START_ITERATION = 20
CHECKPOINT_INTERVAL = 25

FIRE_DT_INITIAL = 0.010
FIRE_DT_MAX = 0.100
FIRE_ALPHA_INITIAL = 0.10
FIRE_FINC = 1.10
FIRE_FDEC = 0.50
FIRE_FALPHA = 0.99
FIRE_NMIN = 5
MAX_ATOM_DISPLACEMENT_ANG = 0.030

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V031_PREFLIGHT_ONLY", "0") == "1"
)


@dataclass
class BranchResult:
    branch: str
    status: str
    iterations: int
    converged: bool
    guard_reason: str
    maximum_neb_force_ev_ang: float
    climbing_image: int | None
    model_forward_barrier_ev: float
    model_backward_barrier_ev: float
    model_endpoint_difference_ev: float
    maximum_grade: float
    median_grade: float
    final_blocks: list[CFGBlock]
    profile_rows: list[dict[str, Any]]
    history_path: Path
    final_cfg: Path
    graded_cfg: Path


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
        "v030r corrected primary analysis",
    )

    basin_model = require_file(
        v028 / "models" / "basin" / "pot_basin60_l12_v001.mtp",
        "basin model",
    )
    targeted_model = require_file(
        v028
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

    basin_train = require_file(
        v028 / "inputs" / "train_basin_v001.cfg",
        "basin train60",
    )
    targeted_train = require_file(
        v028 / "inputs" / "train_targeted_v001.cfg",
        "targeted train60",
    )
    audit_cfg = require_file(
        v029 / "inputs" / "frozen_audit21_labels_v029.cfg",
        "frozen audit21 labels",
    )
    audit_manifest = require_file(
        v029 / "inputs" / "frozen_audit21_manifest_v029.tsv",
        "frozen audit manifest",
    )
    barrier_metrics = require_file(
        v029 / "reports" / "neb9_barrier_metrics_v029.tsv",
        "DFT barrier metrics",
    )
    require_file(MLP, "mlp executable")

    all_blocks = read_cfg(audit_cfg)
    manifest_rows = read_tsv(audit_manifest)
    neb_manifest = [
        row for row in manifest_rows
        if row.get("subset", row.get("audit_subset", "")) == "neb9"
    ]
    if len(neb_manifest) != IMAGE_COUNT:
        raise RuntimeError(
            f"manifest NEB count={len(neb_manifest)}, expected {IMAGE_COUNT}"
        )

    block_by_audit_id: dict[str, CFGBlock] = {}
    for block in all_blocks:
        audit_id = block.features.get("audit_id", "").strip()
        if audit_id:
            block_by_audit_id[audit_id] = block

    initial_blocks: list[CFGBlock] = []
    for row in sorted(
        neb_manifest,
        key=lambda item: int(
            item.get("subset_index", item.get("audit_subset_index", "0"))
        ),
    ):
        audit_id = row.get("audit_id", "").strip()
        if audit_id not in block_by_audit_id:
            raise RuntimeError(f"audit block missing for {audit_id}")
        block = block_by_audit_id[audit_id]
        if block.energy is None or block.forces is None:
            raise RuntimeError(f"audit labels incomplete for {audit_id}")
        initial_blocks.append(block)

    if len(initial_blocks) != IMAGE_COUNT:
        raise RuntimeError("failed to reconstruct frozen DFT NEB9")
    qpts = [geometry_metrics(block.positions)["qpt_ang"] for block in initial_blocks]
    if any(qpts[index + 1] <= qpts[index] for index in range(IMAGE_COUNT - 1)):
        raise RuntimeError(f"initial qPT path not strictly increasing: {qpts}")

    barrier_rows = read_tsv(barrier_metrics)
    if len(barrier_rows) != 2:
        raise RuntimeError("unexpected v029 barrier table")
    dft_forward = finite_float(
        barrier_rows[0]["dft_forward_barrier_ev"],
        "DFT forward barrier",
    )
    dft_backward = finite_float(
        barrier_rows[0]["dft_backward_barrier_ev"],
        "DFT backward barrier",
    )

    return {
        "v028": v028,
        "v029": v029,
        "v030r": v030r,
        "basin_model": basin_model,
        "targeted_model": targeted_model,
        "basin_train": basin_train,
        "targeted_train": targeted_train,
        "audit_cfg": audit_cfg,
        "audit_manifest": audit_manifest,
        "barrier_metrics": barrier_metrics,
        "initial_blocks": initial_blocks,
        "dft_forward": dft_forward,
        "dft_backward": dft_backward,
    }


def evaluate_images(
    branch: str,
    model: Path,
    positions: np.ndarray,
    template_blocks: list[CFGBlock],
    branch_dir: Path,
    iteration: int,
    log_handle: Any,
) -> tuple[np.ndarray, np.ndarray, list[CFGBlock]]:
    eval_dir = branch_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    input_cfg = eval_dir / "current_geometry.cfg"
    output_cfg = eval_dir / "current_predictions.cfg"

    references: list[CFGBlock] = []
    for image_index in range(IMAGE_COUNT):
        features = {
            "neb_eval_id": f"{branch}_image_{image_index + 1:02d}",
            "neb_image": str(image_index + 1),
            "secondary_analysis": "true",
        }
        references.append(
            copy_block(
                template_blocks[image_index],
                positions=positions[image_index],
                forces=None,
                energy=None,
                features=features,
            )
        )
    write_cfg(
        input_cfg,
        references,
        include_energy=False,
        include_forces=False,
    )

    command = [str(MLP), "calc-efs", str(model), str(input_cfg), str(output_cfg)]
    completed = subprocess.run(
        command,
        cwd=branch_dir,
        env={
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    log_handle.write(
        f"\n===== iteration {iteration} calc-efs stdout =====\n"
        + completed.stdout
        + f"\n===== iteration {iteration} calc-efs stderr =====\n"
        + completed.stderr
    )
    log_handle.flush()
    if completed.returncode != 0:
        raise RuntimeError(
            f"{branch} calc-efs failed at iteration {iteration}, "
            f"rc={completed.returncode}"
        )

    produced = read_cfg(output_cfg)
    recovered = recover_blocks_by_feature_or_geometry(
        produced,
        references,
        "neb_eval_id",
        f"{branch} iteration {iteration}",
    )
    ordered = [
        recovered[f"{branch}_image_{image_index + 1:02d}"]
        for image_index in range(IMAGE_COUNT)
    ]
    energies = np.asarray([block.energy for block in ordered], dtype=float)
    forces = np.asarray([block.forces for block in ordered], dtype=float)
    if energies.shape != (IMAGE_COUNT,) or not np.all(np.isfinite(energies)):
        raise RuntimeError(f"{branch}: invalid energy array")
    if forces.shape != (IMAGE_COUNT, 9, 3) or not np.all(np.isfinite(forces)):
        raise RuntimeError(f"{branch}: invalid force array")
    return energies, forces, ordered


def improved_tangent(
    positions: np.ndarray,
    energies: np.ndarray,
    image_index: int,
) -> np.ndarray:
    d_plus = (positions[image_index + 1] - positions[image_index]).reshape(-1)
    d_minus = (positions[image_index] - positions[image_index - 1]).reshape(-1)
    e_prev = energies[image_index - 1]
    e_curr = energies[image_index]
    e_next = energies[image_index + 1]

    if e_next > e_curr > e_prev:
        tangent = d_plus
    elif e_next < e_curr < e_prev:
        tangent = d_minus
    else:
        delta_plus = abs(e_next - e_curr)
        delta_minus = abs(e_prev - e_curr)
        delta_max = max(delta_plus, delta_minus)
        delta_min = min(delta_plus, delta_minus)
        if e_next > e_prev:
            tangent = d_plus * delta_max + d_minus * delta_min
        else:
            tangent = d_plus * delta_min + d_minus * delta_max

    norm = float(np.linalg.norm(tangent))
    if not math.isfinite(norm) or norm < 1.0e-14:
        tangent = d_plus + d_minus
        norm = float(np.linalg.norm(tangent))
    if not math.isfinite(norm) or norm < 1.0e-14:
        raise RuntimeError(f"degenerate NEB tangent at image {image_index + 1}")
    return tangent / norm


def calculate_neb_forces(
    positions: np.ndarray,
    energies: np.ndarray,
    physical_forces: np.ndarray,
    iteration: int,
) -> tuple[np.ndarray, float, int | None]:
    neb_forces = np.zeros_like(physical_forces)
    climbing_zero: int | None = None
    if iteration >= CLIMB_START_ITERATION:
        climbing_zero = int(np.argmax(energies[1:-1])) + 1

    maximum_force = 0.0
    for image_index in range(1, IMAGE_COUNT - 1):
        tangent = improved_tangent(positions, energies, image_index)
        physical = remove_rigid_force_components(
            positions[image_index],
            physical_forces[image_index],
        ).reshape(-1)
        parallel = float(np.dot(physical, tangent)) * tangent

        if climbing_zero == image_index:
            combined = physical - 2.0 * parallel
        else:
            d_plus = float(
                np.linalg.norm(
                    (positions[image_index + 1] - positions[image_index]).reshape(-1)
                )
            )
            d_minus = float(
                np.linalg.norm(
                    (positions[image_index] - positions[image_index - 1]).reshape(-1)
                )
            )
            spring = K_SPRING_EV_ANG2 * (d_plus - d_minus) * tangent
            combined = physical - parallel + spring

        combined_matrix = remove_rigid_force_components(
            positions[image_index],
            combined.reshape(9, 3),
        )
        neb_forces[image_index] = combined_matrix
        local_max = float(
            np.max(np.linalg.norm(combined_matrix, axis=1))
        )
        maximum_force = max(maximum_force, local_max)

    return (
        neb_forces,
        maximum_force,
        None if climbing_zero is None else climbing_zero + 1,
    )


def grades_for_final_path(
    branch: str,
    model: Path,
    train_cfg: Path,
    final_blocks: list[CFGBlock],
    branch_dir: Path,
) -> tuple[float, float, Path]:
    geometry_cfg = branch_dir / "final_path_geometry_v031.cfg"
    graded_cfg = branch_dir / "final_path_graded_v031.cfg"
    als_path = branch_dir / "final_path_state_v031.als"
    references = [
        copy_block(
            block,
            forces=None,
            energy=None,
            features={
                "neb_eval_id": f"{branch}_image_{index + 1:02d}",
                "neb_image": str(index + 1),
                "secondary_analysis": "true",
            },
        )
        for index, block in enumerate(final_blocks)
    ]
    write_cfg(
        geometry_cfg,
        references,
        include_energy=False,
        include_forces=False,
    )
    completed = subprocess.run(
        [
            str(MLP),
            "calc-grade",
            str(model),
            str(train_cfg),
            str(geometry_cfg),
            str(graded_cfg),
            f"--als-filename={als_path}",
        ],
        cwd=branch_dir,
        env={
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (branch_dir / "final_calc_grade.stdout").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (branch_dir / "final_calc_grade.stderr").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{branch}: final calc-grade failed")
    produced = read_cfg(graded_cfg)
    recovered = recover_blocks_by_feature_or_geometry(
        produced,
        references,
        "neb_eval_id",
        f"{branch} final grade",
    )
    values = []
    for index in range(IMAGE_COUNT):
        block = recovered[f"{branch}_image_{index + 1:02d}"]
        grade_text = block.features.get("MV_grade", "").strip()
        values.append(finite_float(grade_text, f"{branch} image grade"))
    array = np.asarray(values, dtype=float)
    return float(np.max(array)), float(np.median(array)), graded_cfg


def optimize_branch(
    branch: str,
    model: Path,
    train_cfg: Path,
    initial_blocks: list[CFGBlock],
) -> BranchResult:
    branch_dir = BRANCHES_DIR / branch
    branch_dir.mkdir(parents=True, exist_ok=True)
    history_path = branch_dir / "neb_iteration_history_v031.tsv"
    calc_log_path = branch_dir / "mlp_calc_efs_combined_v031.log"
    checkpoints_dir = branch_dir / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    initial_positions = np.asarray(
        [block.positions for block in initial_blocks],
        dtype=float,
    )
    positions = initial_positions.copy()
    velocities = np.zeros_like(positions)
    dt = np.full(IMAGE_COUNT, FIRE_DT_INITIAL, dtype=float)
    alpha = np.full(IMAGE_COUNT, FIRE_ALPHA_INITIAL, dtype=float)
    positive_steps = np.zeros(IMAGE_COUNT, dtype=int)

    history_rows: list[dict[str, Any]] = []
    consecutive = 0
    final_status = "max_iterations"
    guard_reason = ""
    last_maximum_force = math.inf
    last_climbing_image: int | None = None
    last_ordered: list[CFGBlock] = []
    last_energies = np.zeros(IMAGE_COUNT)
    last_forces = np.zeros((IMAGE_COUNT, 9, 3))

    with calc_log_path.open("w", encoding="utf-8") as calc_log:
        for iteration in range(MAX_ITERATIONS + 1):
            energies, physical_forces, ordered = evaluate_images(
                branch,
                model,
                positions,
                initial_blocks,
                branch_dir,
                iteration,
                calc_log,
            )
            neb_forces, maximum_force, climbing_image = calculate_neb_forces(
                positions,
                energies,
                physical_forces,
                iteration,
            )
            last_maximum_force = maximum_force
            last_climbing_image = climbing_image
            last_ordered = ordered
            last_energies = energies
            last_forces = physical_forces

            guards: list[str] = []
            for image_index in range(1, IMAGE_COUNT - 1):
                reasons = geometry_guard_reasons(positions[image_index])
                if reasons:
                    guards.append(
                        f"image{image_index + 1}:"
                        + ",".join(reasons)
                    )

            relative = energies - energies[0]
            history_rows.append(
                {
                    "iteration": iteration,
                    "maximum_neb_force_ev_ang": maximum_force,
                    "climbing_image":
                        "" if climbing_image is None else climbing_image,
                    "energy_span_ev": float(np.max(energies) - np.min(energies)),
                    "forward_barrier_current_ev": float(np.max(energies) - energies[0]),
                    "qpt_1_ang": geometry_metrics(positions[0])["qpt_ang"],
                    "qpt_5_ang": geometry_metrics(positions[4])["qpt_ang"],
                    "qpt_9_ang": geometry_metrics(positions[-1])["qpt_ang"],
                    "guard_reasons": ";".join(guards),
                }
            )
            if iteration % 10 == 0 or maximum_force <= FMAX_EV_ANG:
                print(
                    f"[{utc_now()}] {branch} NEB iter={iteration}; "
                    f"fmax={maximum_force:.6f} eV/A; "
                    f"barrier={float(np.max(relative)):.6f} eV; "
                    f"CI={climbing_image}; guards={len(guards)}"
                )

            if guards:
                final_status = "geometry_guard_stop"
                guard_reason = ";".join(guards)
                break

            if (
                iteration >= CLIMB_START_ITERATION
                and maximum_force <= FMAX_EV_ANG
            ):
                consecutive += 1
            else:
                consecutive = 0
            if consecutive >= CONSECUTIVE_REQUIRED:
                final_status = "converged"
                break

            if iteration >= MAX_ITERATIONS:
                final_status = "max_iterations"
                break

            for image_index in range(1, IMAGE_COUNT - 1):
                force = neb_forces[image_index]
                velocities[image_index] += dt[image_index] * force
                power = float(
                    np.sum(velocities[image_index] * force)
                )

                if power > 0.0:
                    positive_steps[image_index] += 1
                    if positive_steps[image_index] > FIRE_NMIN:
                        dt[image_index] = min(
                            dt[image_index] * FIRE_FINC,
                            FIRE_DT_MAX,
                        )
                        alpha[image_index] *= FIRE_FALPHA
                else:
                    velocities[image_index].fill(0.0)
                    dt[image_index] *= FIRE_FDEC
                    alpha[image_index] = FIRE_ALPHA_INITIAL
                    positive_steps[image_index] = 0

                velocity_norm = float(
                    np.linalg.norm(velocities[image_index])
                )
                force_norm = float(np.linalg.norm(force))
                if velocity_norm > 0.0 and force_norm > 0.0:
                    velocities[image_index] = (
                        (1.0 - alpha[image_index])
                        * velocities[image_index]
                        + alpha[image_index]
                        * velocity_norm
                        * force
                        / force_norm
                    )

                displacement = (
                    dt[image_index] * velocities[image_index]
                )
                maximum_atom_displacement = float(
                    np.max(np.linalg.norm(displacement, axis=1))
                )
                if maximum_atom_displacement > MAX_ATOM_DISPLACEMENT_ANG:
                    displacement *= (
                        MAX_ATOM_DISPLACEMENT_ANG
                        / maximum_atom_displacement
                    )
                    velocities[image_index] = (
                        displacement / dt[image_index]
                    )
                positions[image_index] += displacement
                positions[image_index], _ = mass_weighted_kabsch_align(
                    positions[image_index],
                    initial_positions[image_index],
                )

            if iteration % CHECKPOINT_INTERVAL == 0:
                checkpoint_blocks = [
                    copy_block(
                        initial_blocks[index],
                        positions=positions[index],
                        forces=None,
                        energy=None,
                        features={
                            "neb_image": str(index + 1),
                            "iteration": str(iteration),
                            "branch": branch,
                            "secondary_analysis": "true",
                        },
                    )
                    for index in range(IMAGE_COUNT)
                ]
                write_cfg(
                    checkpoints_dir / f"iteration_{iteration:04d}.cfg",
                    checkpoint_blocks,
                    include_energy=False,
                    include_forces=False,
                )

    write_tsv(history_path, history_rows)

    final_blocks: list[CFGBlock] = []
    profile_rows: list[dict[str, Any]] = []
    for image_index in range(IMAGE_COUNT):
        features = {
            "neb_image": str(image_index + 1),
            "branch": branch,
            "secondary_analysis": "true",
            "optimization_status": final_status,
        }
        final_block = copy_block(
            initial_blocks[image_index],
            positions=positions[image_index],
            forces=last_forces[image_index],
            energy=float(last_energies[image_index]),
            features=features,
        )
        final_blocks.append(final_block)
        metrics = geometry_metrics(positions[image_index])
        _, rmsd = mass_weighted_kabsch_align(
            positions[image_index],
            initial_positions[image_index],
        )
        profile_rows.append(
            {
                "branch": branch,
                "image": image_index + 1,
                "optimization_status": final_status,
                "energy_ev": float(last_energies[image_index]),
                "delta_e_from_left_ev":
                    float(last_energies[image_index] - last_energies[0]),
                "qpt_ang": metrics["qpt_ang"],
                "roo_ang": metrics["roo_ang"],
                "minimum_pair_ang": metrics["minimum_pair_ang"],
                "maximum_span_ang": metrics["maximum_span_ang"],
                "mass_weighted_rmsd_from_dft_image_ang": rmsd,
            }
        )

    final_cfg = branch_dir / "secondary_mtp_neb_final_path_v031.cfg"
    write_cfg(final_cfg, final_blocks)

    maximum_grade, median_grade, graded_cfg = grades_for_final_path(
        branch,
        model,
        train_cfg,
        final_blocks,
        branch_dir,
    )

    maximum_zero = int(np.argmax(last_energies))
    forward = float(last_energies[maximum_zero] - last_energies[0])
    backward = float(last_energies[maximum_zero] - last_energies[-1])
    endpoint_difference = float(last_energies[-1] - last_energies[0])

    return BranchResult(
        branch=branch,
        status=final_status,
        iterations=int(history_rows[-1]["iteration"]),
        converged=final_status == "converged",
        guard_reason=guard_reason,
        maximum_neb_force_ev_ang=last_maximum_force,
        climbing_image=last_climbing_image,
        model_forward_barrier_ev=forward,
        model_backward_barrier_ev=backward,
        model_endpoint_difference_ev=endpoint_difference,
        maximum_grade=maximum_grade,
        median_grade=median_grade,
        final_blocks=final_blocks,
        profile_rows=profile_rows,
        history_path=history_path,
        final_cfg=final_cfg,
        graded_cfg=graded_cfg,
    )


def main() -> None:
    upstream = load_upstream()
    initial_blocks: list[CFGBlock] = upstream["initial_blocks"]
    initial_qpts = [
        geometry_metrics(block.positions)["qpt_ang"]
        for block in initial_blocks
    ]

    if PREFLIGHT_ONLY:
        print("PASS_V031_PREFLIGHT_SECONDARY_NEB_NO_CALCULATIONS")
        print(f"source v028:             {upstream['v028']}")
        print(f"source v029:             {upstream['v029']}")
        print(f"source v030r:            {upstream['v030r']}")
        print("initial path:            frozen DFT NEB9 geometries")
        print(
            "initial qPT range:       "
            f"{initial_qpts[0]:.8f} to {initial_qpts[-1]:.8f} A"
        )
        print("models:                  basin then targeted")
        print(f"images:                  {IMAGE_COUNT}, endpoints fixed")
        print(
            "NEB spring/fmax:         "
            f"{K_SPRING_EV_ANG2:.3f} eV/A^2 / "
            f"{FMAX_EV_ANG:.3f} eV/A"
        )
        print(
            "optimizer:               "
            f"batch MLP calc-efs + FIRE, max {MAX_ITERATIONS} iterations"
        )
        print(
            "climbing image:          "
            f"enabled from iteration {CLIMB_START_ITERATION}"
        )
        print("classification:          converged / guard-stop / max-iterations")
        print("scientific retry:        FORBIDDEN")
        print("attempt directory:       NOT CREATED")
        print("mlp calc-efs/calc-grade: NOT EXECUTED")
        print("pw.x/neb.x/train/LAMMPS: NOT EXECUTED")
        return

    if RUN_ROOT.exists():
        raise RuntimeError(f"attempt already exists: {RUN_ROOT}")
    for directory in (
        INPUTS_DIR,
        BRANCHES_DIR,
        REPORTS_DIR,
        FIGURES_DIR,
        PROVENANCE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    for source in (
        upstream["audit_cfg"],
        upstream["audit_manifest"],
        upstream["barrier_metrics"],
    ):
        shutil.copy2(source, INPUTS_DIR / source.name)
    shutil.copy2(Path(__file__).resolve(), PROVENANCE_DIR / Path(__file__).name)
    helper_source = Path(__file__).resolve().with_name(
        "strict_postaudit_common_v001.py"
    )
    if helper_source.is_file():
        shutil.copy2(helper_source, PROVENANCE_DIR / helper_source.name)

    initial_cfg = INPUTS_DIR / "frozen_dft_neb9_initial_path_v031.cfg"
    write_cfg(initial_cfg, initial_blocks)

    print(
        f"[{utc_now()}] Starting secondary basin-model MTP NEB. "
        "This is post-audit and cannot alter the primary result."
    )
    basin_result = optimize_branch(
        "basin",
        upstream["basin_model"],
        upstream["basin_train"],
        initial_blocks,
    )
    print(
        f"[{utc_now()}] Basin secondary NEB completed with status "
        f"{basin_result.status}."
    )

    print(
        f"[{utc_now()}] Starting secondary targeted-model MTP NEB "
        "with identical settings."
    )
    targeted_result = optimize_branch(
        "targeted",
        upstream["targeted_model"],
        upstream["targeted_train"],
        initial_blocks,
    )
    print(
        f"[{utc_now()}] Targeted secondary NEB completed with status "
        f"{targeted_result.status}."
    )

    results = [basin_result, targeted_result]
    all_profile_rows = [
        row for result in results for row in result.profile_rows
    ]
    write_tsv(PROFILE_TSV, all_profile_rows)

    dft_forward = upstream["dft_forward"]
    dft_backward = upstream["dft_backward"]
    comparison_rows: list[dict[str, Any]] = []
    for result in results:
        comparison_rows.append(
            {
                "branch": result.branch,
                "optimization_status": result.status,
                "converged": result.converged,
                "iterations": result.iterations,
                "maximum_neb_force_ev_ang":
                    result.maximum_neb_force_ev_ang,
                "climbing_image": result.climbing_image,
                "dft_forward_barrier_ev": dft_forward,
                "model_forward_barrier_ev":
                    result.model_forward_barrier_ev,
                "forward_barrier_error_ev":
                    result.model_forward_barrier_ev - dft_forward,
                "forward_barrier_abs_error_mev":
                    abs(result.model_forward_barrier_ev - dft_forward)
                    * 1000.0,
                "dft_backward_barrier_ev": dft_backward,
                "model_backward_barrier_ev":
                    result.model_backward_barrier_ev,
                "backward_barrier_error_ev":
                    result.model_backward_barrier_ev - dft_backward,
                "endpoint_difference_ev":
                    result.model_endpoint_difference_ev,
                "grade_median": result.median_grade,
                "grade_max": result.maximum_grade,
                "guard_reason": result.guard_reason,
                "final_cfg": result.final_cfg,
            }
        )
    write_tsv(COMPARISON_TSV, comparison_rows)

    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    dft_energies = np.asarray(
        [block.energy for block in initial_blocks],
        dtype=float,
    )
    axis.plot(
        initial_qpts,
        1000.0 * (dft_energies - dft_energies[0]),
        marker="o",
        label="DFT frozen NEB9",
    )
    for result in results:
        axis.plot(
            [row["qpt_ang"] for row in result.profile_rows],
            [
                1000.0 * row["delta_e_from_left_ev"]
                for row in result.profile_rows
            ],
            marker="o",
            label=f"{result.branch} MTP-relaxed",
        )
    axis.set_xlabel(r"$q_{\mathrm{PT}}$ (Å)")
    axis.set_ylabel(r"$\Delta E$ from left endpoint (meV)")
    axis.set_title("Secondary post-audit MTP-relaxed NEB paths")
    axis.axvline(0.0, linewidth=0.8, linestyle="--")
    axis.legend()
    axis.grid(True, alpha=0.25)
    figure.tight_layout()
    figure_png = FIGURES_DIR / "secondary_mtp_neb_profiles_v031.png"
    figure_pdf = FIGURES_DIR / "secondary_mtp_neb_profiles_v031.pdf"
    figure.savefig(figure_png, dpi=220, bbox_inches="tight")
    figure.savefig(figure_pdf, bbox_inches="tight")
    plt.close(figure)

    overall_status = (
        "PASS_SECONDARY_MTP_NEB_DIAGNOSTIC_COMPLETED"
    )
    STATUS_FILE.write_text(overall_status + "\n", encoding="utf-8")

    summary = {
        "created_utc": utc_now(),
        "status": overall_status,
        "implementation_id": IMPLEMENTATION_ID,
        "run_root": str(RUN_ROOT),
        "analysis_class": "secondary_post_audit",
        "primary_metrics_changed": False,
        "post_audit_training": False,
        "settings": {
            "image_count": IMAGE_COUNT,
            "fixed_endpoints": True,
            "spring_ev_ang2": K_SPRING_EV_ANG2,
            "fmax_ev_ang": FMAX_EV_ANG,
            "consecutive_required": CONSECUTIVE_REQUIRED,
            "max_iterations": MAX_ITERATIONS,
            "climb_start_iteration": CLIMB_START_ITERATION,
            "optimizer": "per-image FIRE with capped displacement",
        },
        "dft_barriers_ev": {
            "forward": dft_forward,
            "backward": dft_backward,
        },
        "branches": {
            result.branch: {
                "status": result.status,
                "converged": result.converged,
                "iterations": result.iterations,
                "maximum_neb_force_ev_ang":
                    result.maximum_neb_force_ev_ang,
                "climbing_image": result.climbing_image,
                "forward_barrier_ev": result.model_forward_barrier_ev,
                "backward_barrier_ev": result.model_backward_barrier_ev,
                "grade_median": result.median_grade,
                "grade_max": result.maximum_grade,
                "guard_reason": result.guard_reason,
                "final_cfg": str(result.final_cfg),
            }
            for result in results
        },
        "execution": {
            "mlp_calc_efs": True,
            "mlp_calc_grade": True,
            "mlp_train": False,
            "pw_x": False,
            "neb_x": False,
            "lammps": False,
        },
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    REPORT_MD.write_text(
        f"""# Secondary post-audit MTP NEB v031

Created UTC: {utc_now()}

Status: `{overall_status}`

This calculation is a secondary diagnostic. The frozen-audit result
from v029 remains the primary result and was not changed.

## Shared protocol

- Initial path: the same nine frozen DFT NEB geometries.
- Endpoints: fixed.
- Spring constant: {K_SPRING_EV_ANG2:.3f} eV/Angstrom^2.
- Climbing image enabled from iteration {CLIMB_START_ITERATION}.
- Convergence target: maximum NEB force <= {FMAX_EV_ANG:.3f}
  eV/Angstrom for {CONSECUTIVE_REQUIRED} consecutive iterations.
- Model order: basin, then targeted.
- No parameter adjustment or scientific retry.

## Outcomes

Basin model:
- status: `{basin_result.status}`;
- iterations: {basin_result.iterations};
- forward barrier: {basin_result.model_forward_barrier_ev:.8f} eV;
- forward barrier error: {(basin_result.model_forward_barrier_ev - dft_forward) * 1000.0:.3f} meV;
- final maximum grade: {basin_result.maximum_grade:.6f}.

Targeted model:
- status: `{targeted_result.status}`;
- iterations: {targeted_result.iterations};
- forward barrier: {targeted_result.model_forward_barrier_ev:.8f} eV;
- forward barrier error: {(targeted_result.model_forward_barrier_ev - dft_forward) * 1000.0:.3f} meV;
- final maximum grade: {targeted_result.maximum_grade:.6f}.

A guard stop or max-iteration outcome is retained as a diagnostic result;
it is not followed by altered settings.

No DFT, Quantum ESPRESSO NEB, MTP training or LAMMPS execution occurred.
""",
        encoding="utf-8",
    )

    write_checksums(RUN_ROOT, CHECKSUMS_TSV)
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    print()
    print(
        "PASS_SECONDARY_MTP_NEB_DIAGNOSTIC_COMPLETED: "
        "STEP 33 v031 COMPLETED"
    )
    print()
    print(f"Run root:                  {RUN_ROOT}")
    for result in results:
        print(
            f"{result.branch:9s} status/barrier: "
            f"{result.status} / "
            f"{result.model_forward_barrier_ev:.8f} eV"
        )
    print(f"Comparison:                {COMPARISON_TSV}")
    print(f"Report:                    {REPORT_MD}")
    print()
    print("mlp calc-efs and calc-grade WERE executed.")
    print("pw.x, neb.x, mlp train and LAMMPS were NOT executed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if RUN_ROOT.exists():
            STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATUS_FILE.write_text(
                "FAIL_SECONDARY_MTP_NEB_v031\n",
                encoding="utf-8",
            )
        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    ROOT,
    VERSIONS,
    cfg_from_positions,
    copy_block,
    finite_float,
    geometry_guard_reasons,
    geometry_metrics,
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


IMPLEMENTATION_ID = "STEP34_V032_TARGETED_MD_DIAGNOSTICS_V003"

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

VERSION_ROOT = VERSIONS / "v032_targeted_md_diagnostics"
CURRENT_POINTER = VERSION_ROOT / "CURRENT_TARGETED_MD_DIAGNOSTICS.txt"

STAMP = utc_stamp()
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"
INPUTS_DIR = RUN_ROOT / "inputs"
INTERFACE_DIR = RUN_ROOT / "interface_check"
TRAJECTORIES_DIR = RUN_ROOT / "trajectories"
GRADES_DIR = RUN_ROOT / "grades"
REPORTS_DIR = RUN_ROOT / "reports"
FIGURES_DIR = RUN_ROOT / "figures"
PROVENANCE_DIR = RUN_ROOT / "provenance"

STATUS_FILE = RUN_ROOT / "STATUS_v032.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v032.json"
REPORT_MD = REPORTS_DIR / "targeted_md_diagnostics_report_v032.md"
TRAJECTORY_SUMMARY_TSV = REPORTS_DIR / "trajectory_summary_v032.tsv"
FRAME_METRICS_TSV = REPORTS_DIR / "sampled_frame_metrics_v032.tsv"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v032.tsv"

EXPECTED_V028_STATUS = (
    "PASS_EQUAL_BUDGET_L12_MODELS_LOCKED_READY_FOR_FROZEN_AUDIT"
)
EXPECTED_V029_STATUS = (
    "PASS_FROZEN_AUDIT21_EVALUATED_NO_POST_AUDIT_TUNING"
)
EXPECTED_V030R_STATUS = "PASS_PRIMARY_METRIC_PROTOCOL_RECOVERY_AND_FIGURES"
EXPECTED_V031R_STATUS = "PASS_SECONDARY_MTP_NEB_INTERPRETATION_RECOVERY"

EXPECTED_TARGETED_MODEL_SHA256 = (
    "30175dae673d63e0b318e5e3ba311a9f61afe88929a5d19c69a744a47aeef99f"
)

TIMESTEP_PS = 0.0001  # 0.1 fs in LAMMPS metal units
RUN_STEPS = 10000
RUN_LENGTH_PS = TIMESTEP_PS * RUN_STEPS
THERMOSTAT_DAMP_PS = 0.020
SAMPLE_EVERY_STEPS = 100
SELECT_THRESHOLD = 2.0
BREAK_THRESHOLD = 10.0

TRAJECTORY_PROTOCOL = [
    {"trajectory_id": "T100_left", "temperature_K": 100.0, "side": "left", "seed": 42101},
    {"trajectory_id": "T100_right", "temperature_K": 100.0, "side": "right", "seed": 42102},
    {"trajectory_id": "T300_left", "temperature_K": 300.0, "side": "left", "seed": 42301},
    {"trajectory_id": "T300_right", "temperature_K": 300.0, "side": "right", "seed": 42302},
    {"trajectory_id": "T500_left", "temperature_K": 500.0, "side": "left", "seed": 42501},
    {"trajectory_id": "T500_right", "temperature_K": 500.0, "side": "right", "seed": 42502},
]

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V032_PREFLIGHT_ONLY", "0") == "1"
)


@dataclass
class TrajectoryResult:
    trajectory_id: str
    temperature_K: float
    side: str
    seed: int
    returncode: int
    status: str
    completed_steps: int
    frame_count: int
    break_detected: bool
    geometry_guard_count: int
    maximum_temperature_K: float
    mean_temperature_K: float
    minimum_qpt_ang: float
    maximum_qpt_ang: float
    minimum_roo_ang: float
    maximum_roo_ang: float
    minimum_pair_ang: float
    maximum_span_ang: float
    preselected_count: int
    directory: Path


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
    v031r = resolve_attempt(
        V031R_POINTER,
        "STATUS_v031r.txt",
        EXPECTED_V031R_STATUS,
        "v031r secondary NEB interpretation recovery",
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
    audit_cfg = require_file(
        v029 / "inputs" / "frozen_audit21_labels_v029.cfg",
        "frozen audit labels",
    )
    audit_manifest = require_file(
        v029 / "inputs" / "frozen_audit21_manifest_v029.tsv",
        "frozen audit manifest",
    )
    require_file(MLP, "mlp executable")
    require_file(LAMMPS, "LAMMPS executable")

    blocks = read_cfg(audit_cfg)
    block_by_id = {
        block.features.get("audit_id", ""): block
        for block in blocks
        if block.features.get("audit_id", "")
    }
    manifest = [
        row for row in read_tsv(audit_manifest)
        if row.get("subset", "") == "neb9"
    ]
    manifest.sort(key=lambda row: int(row["subset_index"]))
    if len(manifest) != 9:
        raise RuntimeError("cannot reconstruct NEB9 endpoints")
    left_id = manifest[0]["audit_id"]
    right_id = manifest[-1]["audit_id"]
    if left_id not in block_by_id or right_id not in block_by_id:
        raise RuntimeError("endpoint blocks missing")
    left = block_by_id[left_id]
    right = block_by_id[right_id]
    if left.energy is None or right.energy is None:
        raise RuntimeError("endpoint labels incomplete")

    return {
        "v028": v028,
        "v029": v029,
        "v030r": v030r,
        "v031r": v031r,
        "model": model,
        "train": train,
        "audit_cfg": audit_cfg,
        "audit_manifest": audit_manifest,
        "left": left,
        "right": right,
    }


def mlp_calc_efs_single(
    model: Path,
    source_block: CFGBlock,
    directory: Path,
) -> CFGBlock:
    input_cfg = directory / "mlp_input.cfg"
    output_cfg = directory / "mlp_prediction.cfg"
    reference = copy_block(
        source_block,
        forces=None,
        energy=None,
        features={"interface_id": "endpoint_left"},
    )
    write_cfg(
        input_cfg,
        [reference],
        include_energy=False,
        include_forces=False,
    )
    completed = subprocess.run(
        [str(MLP), "calc-efs", str(model), str(input_cfg), str(output_cfg)],
        cwd=directory,
        env={**os.environ, "OMP_NUM_THREADS": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (directory / "mlp_calc_efs.stdout").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (directory / "mlp_calc_efs.stderr").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError("interface mlp calc-efs failed")
    produced = read_cfg(output_cfg)
    recovered = recover_blocks_by_feature_or_geometry(
        produced,
        [reference],
        "interface_id",
        "v032 interface MLP",
    )
    result = recovered["endpoint_left"]
    if result.energy is None or result.forces is None:
        raise RuntimeError("interface MLP prediction incomplete")
    return result


def write_mlip_ini(
    path: Path,
    model: Path,
    *,
    selection: bool,
    state_path: Path | None = None,
    preselected_path: Path | None = None,
    selection_log: Path | None = None,
) -> None:
    lines = [
        f"mtp-filename {model}",
        "calculate-efs TRUE",
        f"select {'TRUE' if selection else 'FALSE'}",
    ]
    if selection:
        if state_path is None or preselected_path is None:
            raise RuntimeError("selection paths missing")
        lines.extend(
            [
                f"select:threshold {SELECT_THRESHOLD:.8f}",
                f"select:threshold-break {BREAK_THRESHOLD:.8f}",
                f"select:save-selected {preselected_path}",
                f"select:load-state {state_path}",
            ]
        )
        if selection_log is not None:
            lines.append(f"select:log {selection_log}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_thermo_rows(log_path: Path) -> list[dict[str, float]]:
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[dict[str, float]] = []
    required = {"Step", "Time", "Temp", "PotEng", "KinEng", "TotEng"}
    index = 0
    while index < len(lines):
        columns = lines[index].split()
        if required.issubset(columns):
            index += 1
            while index < len(lines):
                values = lines[index].split()
                if len(values) != len(columns):
                    break
                try:
                    row = {
                        key: float(value)
                        for key, value in zip(columns, values)
                    }
                except ValueError:
                    break
                rows.append(row)
                index += 1
        index += 1
    unique: dict[int, dict[str, float]] = {}
    for row in rows:
        unique[int(round(row["Step"]))] = row
    return [unique[key] for key in sorted(unique)]


def run_interface_check(
    upstream: dict[str, Any],
) -> dict[str, float]:
    INTERFACE_DIR.mkdir(parents=True, exist_ok=True)
    source_block: CFGBlock = upstream["left"]
    mlp_prediction = mlp_calc_efs_single(
        upstream["model"],
        source_block,
        INTERFACE_DIR,
    )

    data_path = INTERFACE_DIR / "left_endpoint.data"
    mlip_ini = INTERFACE_DIR / "mlip_interface.ini"
    input_path = INTERFACE_DIR / "in.interface"
    log_path = INTERFACE_DIR / "log.interface"
    dump_path = INTERFACE_DIR / "interface.lammpstrj"
    stdout_path = INTERFACE_DIR / "lammps.stdout"
    stderr_path = INTERFACE_DIR / "lammps.stderr"

    write_lammps_data(data_path, source_block.positions)
    write_mlip_ini(mlip_ini, upstream["model"], selection=False)
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
dump intf all custom 1 {dump_path} id type x y z fx fy fz
dump_modify intf sort id first yes format float %.16g
run 0
undump intf
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [str(LAMMPS), "-in", str(input_path), "-log", str(log_path)],
        cwd=INTERFACE_DIR,
        env={**os.environ, "OMP_NUM_THREADS": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"LAMMPS interface run failed rc={completed.returncode}"
        )

    frames = parse_lammps_custom_dump(dump_path)
    if len(frames) < 1 or "forces" not in frames[-1]:
        raise RuntimeError("LAMMPS interface force dump missing")
    thermo = parse_thermo_rows(log_path)
    if not thermo:
        raise RuntimeError("LAMMPS interface thermo missing")
    lammps_energy = thermo[-1]["PotEng"]
    lammps_forces = np.asarray(frames[-1]["forces"], dtype=float)

    energy_delta = abs(lammps_energy - float(mlp_prediction.energy))
    force_delta = float(
        np.max(np.abs(lammps_forces - mlp_prediction.forces))
    )
    coordinate_delta = float(
        np.max(np.abs(frames[-1]["positions"] - source_block.positions))
    )
    if energy_delta > 1.0e-8:
        raise RuntimeError(
            f"MLP/LAMMPS interface energy delta={energy_delta:.3e} eV"
        )
    if force_delta > 2.0e-5:
        raise RuntimeError(
            f"MLP/LAMMPS interface force delta={force_delta:.3e} eV/A"
        )
    if coordinate_delta > 1.0e-6:
        raise RuntimeError(
            f"LAMMPS run0 coordinates changed by {coordinate_delta:.3e} A"
        )
    return {
        "energy_delta_ev": energy_delta,
        "force_max_abs_delta_ev_ang": force_delta,
        "coordinate_max_abs_delta_ang": coordinate_delta,
    }


def create_active_learning_state(
    model: Path,
    train: Path,
) -> Path:
    GRADES_DIR.mkdir(parents=True, exist_ok=True)
    graded_train = GRADES_DIR / "train_targeted_with_grades_v032.cfg"
    state = GRADES_DIR / "state_targeted_v032.als"
    completed = subprocess.run(
        [
            str(MLP),
            "calc-grade",
            str(model),
            str(train),
            str(train),
            str(graded_train),
            f"--als-filename={state}",
        ],
        cwd=GRADES_DIR,
        env={**os.environ, "OMP_NUM_THREADS": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (GRADES_DIR / "make_state.stdout").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (GRADES_DIR / "make_state.stderr").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0 or not state.is_file():
        raise RuntimeError("targeted active-learning state creation failed")
    return state


def write_md_input(
    path: Path,
    data_path: Path,
    mlip_ini: Path,
    dump_path: Path,
    temperature: float,
    seed: int,
) -> None:
    path.write_text(
        f"""units metal
atom_style atomic
boundary p p p
read_data {data_path}
pair_style mlip {mlip_ini}
pair_coeff * *
neighbor 1.0 bin
neigh_modify every 1 delay 0 check yes
timestep {TIMESTEP_PS:.8f}
velocity all create {temperature:.8f} {seed} mom yes rot yes dist gaussian
fix remove_momentum all momentum 1 linear 1 1 1 angular
fix thermostat all nvt temp {temperature:.8f} {temperature:.8f} {THERMOSTAT_DAMP_PS:.8f}
thermo_style custom step time temp pe ke etotal
thermo {SAMPLE_EVERY_STEPS}
thermo_modify format float %.16g flush yes
dump trajectory all custom {SAMPLE_EVERY_STEPS} {dump_path} id type x y z vx vy vz fx fy fz
dump_modify trajectory sort id first yes format float %.16g
run {RUN_STEPS}
""",
        encoding="utf-8",
    )


def run_trajectory(
    specification: dict[str, Any],
    start_block: CFGBlock,
    model: Path,
    state_path: Path,
) -> tuple[TrajectoryResult, list[dict[str, Any]]]:
    trajectory_id = specification["trajectory_id"]
    directory = TRAJECTORIES_DIR / trajectory_id
    directory.mkdir(parents=True, exist_ok=True)

    data_path = directory / "start.data"
    mlip_ini = directory / "mlip.ini"
    input_path = directory / "in.md"
    log_path = directory / "log.lammps"
    dump_path = directory / "trajectory.lammpstrj"
    preselected_path = directory / "preselected.cfg"
    selection_log = directory / "selection.log"

    write_lammps_data(data_path, start_block.positions)
    write_mlip_ini(
        mlip_ini,
        model,
        selection=True,
        state_path=state_path,
        preselected_path=preselected_path,
        selection_log=selection_log,
    )
    write_md_input(
        input_path,
        data_path,
        mlip_ini,
        dump_path,
        specification["temperature_K"],
        specification["seed"],
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

    combined_text = completed.stdout + "\n" + completed.stderr
    if log_path.is_file():
        combined_text += "\n" + log_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    break_detected = "Breaking threshold exceeded" in combined_text

    frames: list[dict[str, Any]] = []
    if dump_path.is_file():
        try:
            frames = parse_lammps_custom_dump(dump_path)
        except Exception as parse_error:
            (directory / "dump_parse_error.txt").write_text(
                str(parse_error) + "\n",
                encoding="utf-8",
            )
            if not break_detected:
                raise
    thermo_rows = parse_thermo_rows(log_path) if log_path.is_file() else []
    thermo_by_step = {
        int(round(row["Step"])): row for row in thermo_rows
    }

    frame_rows: list[dict[str, Any]] = []
    geometry_guard_count = 0
    qpts: list[float] = []
    roos: list[float] = []
    minimum_pairs: list[float] = []
    spans: list[float] = []
    temperatures: list[float] = []

    for frame_index, frame in enumerate(frames, start=1):
        metrics = geometry_metrics(frame["positions"])
        reasons = geometry_guard_reasons(frame["positions"])
        if reasons:
            geometry_guard_count += 1
        step = int(frame["timestep"])
        thermo = thermo_by_step.get(step, {})
        temperature = float(thermo.get("Temp", math.nan))
        if math.isfinite(temperature):
            temperatures.append(temperature)
        qpts.append(metrics["qpt_ang"])
        roos.append(metrics["roo_ang"])
        minimum_pairs.append(metrics["minimum_pair_ang"])
        spans.append(metrics["maximum_span_ang"])
        frame_rows.append(
            {
                "trajectory_id": trajectory_id,
                "frame_index": frame_index,
                "step": step,
                "time_ps": step * TIMESTEP_PS,
                "temperature_K": temperature,
                "potential_energy_ev": thermo.get("PotEng", math.nan),
                "kinetic_energy_ev": thermo.get("KinEng", math.nan),
                "total_energy_ev": thermo.get("TotEng", math.nan),
                "qpt_ang": metrics["qpt_ang"],
                "roo_ang": metrics["roo_ang"],
                "minimum_pair_ang": metrics["minimum_pair_ang"],
                "maximum_span_ang": metrics["maximum_span_ang"],
                "geometry_guard_reasons": ";".join(reasons),
                "positions": frame["positions"],
            }
        )

    completed_steps = max(
        [int(row["Step"]) for row in thermo_rows]
        + [int(frame["timestep"]) for frame in frames]
        + [0]
    )
    preselected_count = (
        preselected_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).count("BEGIN_CFG")
        if preselected_path.is_file()
        else 0
    )

    if break_detected:
        status = "mlip_threshold_break"
    elif completed.returncode != 0:
        status = "technical_failure"
    elif geometry_guard_count:
        status = "posthoc_geometry_guard"
    elif completed_steps < RUN_STEPS:
        status = "incomplete_without_break_marker"
    else:
        status = "completed"

    result = TrajectoryResult(
        trajectory_id=trajectory_id,
        temperature_K=float(specification["temperature_K"]),
        side=str(specification["side"]),
        seed=int(specification["seed"]),
        returncode=completed.returncode,
        status=status,
        completed_steps=completed_steps,
        frame_count=len(frames),
        break_detected=break_detected,
        geometry_guard_count=geometry_guard_count,
        maximum_temperature_K=max(temperatures) if temperatures else math.nan,
        mean_temperature_K=float(np.mean(temperatures)) if temperatures else math.nan,
        minimum_qpt_ang=min(qpts) if qpts else math.nan,
        maximum_qpt_ang=max(qpts) if qpts else math.nan,
        minimum_roo_ang=min(roos) if roos else math.nan,
        maximum_roo_ang=max(roos) if roos else math.nan,
        minimum_pair_ang=min(minimum_pairs) if minimum_pairs else math.nan,
        maximum_span_ang=max(spans) if spans else math.nan,
        preselected_count=preselected_count,
        directory=directory,
    )
    return result, frame_rows


def grade_sampled_frames(
    model: Path,
    train: Path,
    frame_rows: list[dict[str, Any]],
) -> dict[str, float]:
    if not frame_rows:
        return {}
    GRADES_DIR.mkdir(parents=True, exist_ok=True)
    geometry_cfg = GRADES_DIR / "sampled_md_frames_geometry_v032.cfg"
    graded_cfg = GRADES_DIR / "sampled_md_frames_graded_v032.cfg"
    state_path = GRADES_DIR / "sampled_md_frames_state_v032.als"

    references: list[CFGBlock] = []
    for row in frame_rows:
        frame_id = (
            f"{row['trajectory_id']}_step_{int(row['step']):06d}"
        )
        block = cfg_from_positions(
            row["positions"],
            key="md_frame_id",
            value=frame_id,
        )
        block.features.update(
            {
                "trajectory_id": row["trajectory_id"],
                "md_step": str(int(row["step"])),
                "targeted_only": "true",
            }
        )
        block.feature_rows = list(block.features.items())
        references.append(block)
        row["md_frame_id"] = frame_id

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
            str(train),
            str(geometry_cfg),
            str(graded_cfg),
            f"--als-filename={state_path}",
        ],
        cwd=GRADES_DIR,
        env={**os.environ, "OMP_NUM_THREADS": "1"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (GRADES_DIR / "sampled_calc_grade.stdout").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (GRADES_DIR / "sampled_calc_grade.stderr").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError("sampled MD calc-grade failed")
    produced = read_cfg(graded_cfg)
    recovered = recover_blocks_by_feature_or_geometry(
        produced,
        references,
        "md_frame_id",
        "v032 sampled MD grades",
    )
    grades: dict[str, float] = {}
    for frame_id, block in recovered.items():
        grades[frame_id] = finite_float(
            block.features.get("MV_grade", ""),
            f"grade {frame_id}",
        )
    return grades


def main() -> None:
    upstream = load_upstream()
    left_metrics = geometry_metrics(upstream["left"].positions)
    right_metrics = geometry_metrics(upstream["right"].positions)

    if PREFLIGHT_ONLY:
        print("PASS_V032_PREFLIGHT_TARGETED_MD_NO_CALCULATIONS")
        print(f"source v028:             {upstream['v028']}")
        print(f"source v029:             {upstream['v029']}")
        print(f"source v030r:            {upstream['v030r']}")
        print(f"source v031r:            {upstream['v031r']}")
        print("model:                   locked targeted60 level-12")
        print(
            "endpoint qPT:            "
            f"{left_metrics['qpt_ang']:.8f}, "
            f"{right_metrics['qpt_ang']:.8f} A"
        )
        print("trajectories:            6 NVT = 100/300/500 K x left/right")
        print(
            "timestep/run:            "
            f"{TIMESTEP_PS * 1000.0:.4f} fs / "
            f"{RUN_LENGTH_PS:.3f} ps"
        )
        print(
            "selection thresholds:    "
            f"{SELECT_THRESHOLD:.1f} / break {BREAK_THRESHOLD:.1f}"
        )
        print("velocity seeds:          42101,42102,42301,42302,42501,42502")
        print("scientific retry:        FORBIDDEN")
        print("attempt directory:       NOT CREATED")
        print("mlp/LAMMPS:              NOT EXECUTED")
        print("pw.x/neb.x/train:        NOT EXECUTED")
        return

    if RUN_ROOT.exists():
        raise RuntimeError(f"attempt already exists: {RUN_ROOT}")
    for directory in (
        INPUTS_DIR,
        INTERFACE_DIR,
        TRAJECTORIES_DIR,
        GRADES_DIR,
        REPORTS_DIR,
        FIGURES_DIR,
        PROVENANCE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copy2(upstream["model"], INPUTS_DIR / upstream["model"].name)
    shutil.copy2(upstream["train"], INPUTS_DIR / upstream["train"].name)
    shutil.copy2(Path(__file__).resolve(), PROVENANCE_DIR / Path(__file__).name)
    helper_source = Path(__file__).resolve().with_name(
        "strict_postaudit_common_v001.py"
    )
    if helper_source.is_file():
        shutil.copy2(helper_source, PROVENANCE_DIR / helper_source.name)

    protocol_path = INPUTS_DIR / "targeted_md_protocol_v032.json"
    protocol_path.write_text(
        json.dumps(
            {
                "created_utc": utc_now(),
                "model_sha256": sha256(upstream["model"]),
                "ensemble": "NVT",
                "temperatures_K": [100, 300, 500],
                "sides": ["left", "right"],
                "trajectory_count": 6,
                "timestep_ps": TIMESTEP_PS,
                "run_steps": RUN_STEPS,
                "run_length_ps": RUN_LENGTH_PS,
                "thermostat_damp_ps": THERMOSTAT_DAMP_PS,
                "sample_every_steps": SAMPLE_EVERY_STEPS,
                "select_threshold": SELECT_THRESHOLD,
                "break_threshold": BREAK_THRESHOLD,
                "trajectories": TRAJECTORY_PROTOCOL,
                "scientific_retry": False,
                "kinetics_claim": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"[{utc_now()}] Running one MLP/LAMMPS interface check.")
    interface_metrics = run_interface_check(upstream)
    print(
        f"[{utc_now()}] Interface PASS: "
        f"dE={interface_metrics['energy_delta_ev']:.3e} eV; "
        f"dFmax={interface_metrics['force_max_abs_delta_ev_ang']:.3e} eV/A."
    )

    print(f"[{utc_now()}] Creating targeted active-learning state.")
    state_path = create_active_learning_state(
        upstream["model"],
        upstream["train"],
    )

    trajectory_results: list[TrajectoryResult] = []
    all_frame_rows: list[dict[str, Any]] = []
    for specification in TRAJECTORY_PROTOCOL:
        start_block = (
            upstream["left"]
            if specification["side"] == "left"
            else upstream["right"]
        )
        print(
            f"[{utc_now()}] Starting {specification['trajectory_id']}: "
            f"T={specification['temperature_K']:.0f} K, "
            f"seed={specification['seed']}."
        )
        result, frame_rows = run_trajectory(
            specification,
            start_block,
            upstream["model"],
            state_path,
        )
        trajectory_results.append(result)
        all_frame_rows.extend(frame_rows)
        print(
            f"[{utc_now()}] {result.trajectory_id}: status={result.status}; "
            f"steps={result.completed_steps}/{RUN_STEPS}; "
            f"frames={result.frame_count}; "
            f"preselected={result.preselected_count}."
        )

    print(
        f"[{utc_now()}] Calculating offline grades for "
        f"{len(all_frame_rows)} sampled frames."
    )
    grade_by_frame = grade_sampled_frames(
        upstream["model"],
        upstream["train"],
        all_frame_rows,
    )
    for row in all_frame_rows:
        row["mv_grade"] = grade_by_frame.get(
            row.get("md_frame_id", ""),
            math.nan,
        )
        row.pop("positions", None)

    write_tsv(FRAME_METRICS_TSV, all_frame_rows)

    trajectory_rows: list[dict[str, Any]] = []
    for result in trajectory_results:
        trajectory_grades = [
            finite_float(row["mv_grade"], "trajectory grade")
            for row in all_frame_rows
            if row["trajectory_id"] == result.trajectory_id
            and math.isfinite(float(row["mv_grade"]))
        ]
        trajectory_rows.append(
            {
                "trajectory_id": result.trajectory_id,
                "temperature_K": result.temperature_K,
                "side": result.side,
                "seed": result.seed,
                "status": result.status,
                "returncode": result.returncode,
                "completed_steps": result.completed_steps,
                "planned_steps": RUN_STEPS,
                "completed_time_ps":
                    result.completed_steps * TIMESTEP_PS,
                "frame_count": result.frame_count,
                "break_detected": result.break_detected,
                "geometry_guard_count": result.geometry_guard_count,
                "mean_temperature_K": result.mean_temperature_K,
                "maximum_temperature_K": result.maximum_temperature_K,
                "minimum_qpt_ang": result.minimum_qpt_ang,
                "maximum_qpt_ang": result.maximum_qpt_ang,
                "minimum_roo_ang": result.minimum_roo_ang,
                "maximum_roo_ang": result.maximum_roo_ang,
                "minimum_pair_ang": result.minimum_pair_ang,
                "maximum_span_ang": result.maximum_span_ang,
                "preselected_count": result.preselected_count,
                "sampled_grade_median":
                    float(np.median(trajectory_grades))
                    if trajectory_grades else math.nan,
                "sampled_grade_max":
                    max(trajectory_grades)
                    if trajectory_grades else math.nan,
                "directory": result.directory,
            }
        )
    write_tsv(TRAJECTORY_SUMMARY_TSV, trajectory_rows)

    figure, axis = plt.subplots(figsize=(7.5, 4.8))
    for trajectory_id in [
        item["trajectory_id"] for item in TRAJECTORY_PROTOCOL
    ]:
        rows = [
            row for row in all_frame_rows
            if row["trajectory_id"] == trajectory_id
        ]
        axis.plot(
            [float(row["time_ps"]) for row in rows],
            [float(row["qpt_ang"]) for row in rows],
            label=trajectory_id,
        )
    axis.axhline(0.0, linewidth=0.8, linestyle="--")
    axis.set_xlabel("Time (ps)")
    axis.set_ylabel(r"$q_{\mathrm{PT}}$ (Å)")
    axis.set_title("Targeted-model NVT diagnostic trajectories")
    axis.legend(ncol=2)
    axis.grid(True, alpha=0.25)
    figure.tight_layout()
    qpt_png = FIGURES_DIR / "targeted_md_qpt_v032.png"
    qpt_pdf = FIGURES_DIR / "targeted_md_qpt_v032.pdf"
    figure.savefig(qpt_png, dpi=220, bbox_inches="tight")
    figure.savefig(qpt_pdf, bbox_inches="tight")
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(7.5, 4.8))
    for trajectory_id in [
        item["trajectory_id"] for item in TRAJECTORY_PROTOCOL
    ]:
        rows = [
            row for row in all_frame_rows
            if row["trajectory_id"] == trajectory_id
            and math.isfinite(float(row["mv_grade"]))
        ]
        if not rows:
            continue
        axis.plot(
            [float(row["time_ps"]) for row in rows],
            [float(row["mv_grade"]) for row in rows],
            label=trajectory_id,
        )
    axis.axhline(SELECT_THRESHOLD, linewidth=0.8, linestyle="--")
    axis.axhline(BREAK_THRESHOLD, linewidth=0.8, linestyle=":")
    axis.set_yscale("log")
    axis.set_xlabel("Time (ps)")
    axis.set_ylabel("MaxVol grade")
    axis.set_title("Offline grades of sampled MD frames")
    axis.legend(ncol=2)
    axis.grid(True, which="both", alpha=0.25)
    figure.tight_layout()
    grade_png = FIGURES_DIR / "targeted_md_grades_v032.png"
    grade_pdf = FIGURES_DIR / "targeted_md_grades_v032.pdf"
    figure.savefig(grade_png, dpi=220, bbox_inches="tight")
    figure.savefig(grade_pdf, bbox_inches="tight")
    plt.close(figure)

    status_counts: dict[str, int] = {}
    for result in trajectory_results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    overall_status = "PASS_TARGETED_MD_DIAGNOSTICS_COMPLETED"
    STATUS_FILE.write_text(overall_status + "\n", encoding="utf-8")

    finite_grades = [
        float(row["mv_grade"])
        for row in all_frame_rows
        if math.isfinite(float(row["mv_grade"]))
    ]
    summary = {
        "created_utc": utc_now(),
        "status": overall_status,
        "implementation_id": IMPLEMENTATION_ID,
        "run_root": str(RUN_ROOT),
        "analysis_class": "targeted_only_post_audit_diagnostic",
        "model_sha256": sha256(upstream["model"]),
        "interface": interface_metrics,
        "protocol": {
            "ensemble": "NVT",
            "trajectory_count": 6,
            "temperatures_K": [100, 300, 500],
            "timestep_fs": TIMESTEP_PS * 1000.0,
            "run_length_ps": RUN_LENGTH_PS,
            "select_threshold": SELECT_THRESHOLD,
            "break_threshold": BREAK_THRESHOLD,
        },
        "trajectory_status_counts": status_counts,
        "sampled_frame_count": len(all_frame_rows),
        "sampled_grade_max":
            max(finite_grades) if finite_grades else None,
        "sampled_grade_median":
            float(np.median(finite_grades)) if finite_grades else None,
        "scientific_scope": {
            "thermal_stability_diagnostic": True,
            "kinetics_claim": False,
            "quantum_nuclear_effects_included": False,
            "post_audit_training": False,
            "scientific_retry": False,
        },
        "execution": {
            "mlp_calc_efs": True,
            "mlp_calc_grade": True,
            "lammps": True,
            "mlp_train": False,
            "pw_x": False,
            "neb_x": False,
        },
        "trajectory_summary": str(TRAJECTORY_SUMMARY_TSV),
        "frame_metrics": str(FRAME_METRICS_TSV),
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    status_lines = "\n".join(
        f"- `{name}`: {count}" for name, count in sorted(status_counts.items())
    )
    REPORT_MD.write_text(
        f"""# Targeted-only MD diagnostics v032

Created UTC: {utc_now()}

Status: `{overall_status}`

This is a post-audit numerical and geometric diagnostic of the locked
targeted model. It is not a kinetic calculation.

## Protocol

- Six NVT trajectories: 100, 300 and 500 K, one left-start and one
  right-start trajectory at each temperature.
- Timestep: {TIMESTEP_PS * 1000.0:.4f} fs.
- Planned duration: {RUN_LENGTH_PS:.3f} ps per trajectory.
- MaxVol selection threshold: {SELECT_THRESHOLD:.1f}.
- MaxVol breaking threshold: {BREAK_THRESHOLD:.1f}.
- No retraining, DFT labelling or scientific retry.

## Interface

- Energy difference between direct MLP and LAMMPS: {interface_metrics['energy_delta_ev']:.3e} eV.
- Maximum force-component difference: {interface_metrics['force_max_abs_delta_ev_ang']:.3e} eV/Angstrom.

## Trajectory outcomes

{status_lines}

A threshold break or geometry guard is retained as a diagnostic
outcome. It does not trigger a modified rerun.

The trajectories cannot establish a physical proton-transfer rate:
the runs are short, classical, and omit nuclear quantum effects.
""",
        encoding="utf-8",
    )

    write_checksums(RUN_ROOT, CHECKSUMS_TSV)
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    print()
    print(
        "PASS_TARGETED_MD_DIAGNOSTICS_COMPLETED: "
        "STEP 34 v032 COMPLETED"
    )
    print()
    print(f"Run root:                  {RUN_ROOT}")
    print(f"Trajectory status counts: {status_counts}")
    print(f"Sampled frames:            {len(all_frame_rows)}")
    print(
        "Maximum sampled grade:    "
        f"{max(finite_grades):.6f}"
        if finite_grades
        else "Maximum sampled grade:    unavailable"
    )
    print(f"Summary:                   {TRAJECTORY_SUMMARY_TSV}")
    print(f"Report:                    {REPORT_MD}")
    print()
    print("LAMMPS, mlp calc-efs and mlp calc-grade WERE executed.")
    print("pw.x, neb.x and mlp train were NOT executed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if RUN_ROOT.exists():
            STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATUS_FILE.write_text(
                "FAIL_TARGETED_MD_DIAGNOSTICS_v032\n",
                encoding="utf-8",
            )
        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

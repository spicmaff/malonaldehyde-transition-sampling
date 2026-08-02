#!/usr/bin/env python3
"""STAGE62 frozen-path 1D tunneling audit v003.

Purpose
-------
Use only the checksum-locked v005 frozen-audit PBE NEB9 path from
source_data/neb9_energy_profiles_v005.tsv and the basin/targeted MTP energies
evaluated image-by-image on those same nine PBE geometries. Construct one-dimensional
Hamiltonians along q_PT and test whether equal-budget transition-focused
sampling reproduces a PBE-derived quantum nuclear observable better than
basin-focused sampling.

Scientific scope
----------------
This is a one-dimensional frozen-path quantum audit. It is not a prediction of
an experimental tunneling rate, not a full-dimensional instanton calculation,
not molecular dynamics, and not a new DFT calculation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import PchipInterpolator, CubicSpline
from scipy.linalg import eigh_tridiagonal

VERSION = "v039"
STAGE_ID = "STAGE62_FROZEN_PATH_1D_TUNNELING_AUDIT_V003"
STATUS_PASS = "PASS_STAGE62_FROZEN_PATH_1D_TUNNELING_AUDIT_V003"
VERSION_DIR = "v039_frozen_path_1d_tunneling_audit"
POINTER_FILE = "CURRENT_FROZEN_PATH_1D_TUNNELING_AUDIT_V039.txt"

INPUT_VERSION_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
INPUT_STATUS_FILE = "STATUS_v005.txt"
EXPECTED_INPUT_STATUS = "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"
PROFILE_REL = "source_data/neb9_energy_profiles_v005.tsv"
BARRIER_SUMMARY_REL = "source_data/neb9_barrier_summary_v005.tsv"
PRIMARY_METRIC_REL = "source_data/primary_metric_summary_v005.tsv"
XYZ_REL = "geometry/dft_independent_neb9_v005.xyz"
CHECKSUM_REL = "checksums_v005.tsv"

EXPECTED_SERIES = ("DFT", "basin", "targeted")
EXPECTED_IMAGES = tuple(range(1, 10))
EXPECTED_ATOMS = ("O", "H", "C", "H", "C", "H", "C", "O", "H")
HEAVY_INDICES = (0, 2, 4, 6, 7)
TRANSFER_H_INDEX = 1
LEFT_O_INDEX = 0
RIGHT_O_INDEX = 7

EXPECTED_PBE_BARRIER_EV = 0.036072093892926205
EXPECTED_BASIN_BARRIER_ERROR_MEV = 35.245734
EXPECTED_TARGETED_BARRIER_ERROR_MEV = 4.100394

# Fundamental coefficient hbar^2/(2 amu Angstrom^2), expressed in eV.
KINETIC_COEFF_EV_A2_PER_AMU = 0.0020900796402483607
EV_TO_WAVENUMBER_CM = 8065.544005
EV_TO_GHZ = 241798.924208

ATOMIC_MASS_AMU = {
    "H": 1.00784,
    "D": 2.01410177812,
    "C": 12.011,
    "O": 15.999,
}

PRIMARY_INTERPOLATION = "pchip"
PRIMARY_PROFILE_MODE = "symmetrized"
PRIMARY_MASS_MODEL = "path_metric"
DEFAULT_GRID = 1601
CONVERGENCE_GRIDS = (801, 1201, 1601)
DEFAULT_EXTENSION_FRACTION = 0.35
N_LEVELS = 4

COLORS = {"DFT": "#202020", "basin": "#D88928", "targeted": "#377EB8"}
LABELS = {"DFT": "PBE", "basin": "Basin-focused MTP", "targeted": "Transition-focused MTP"}


class AuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class XYZFrame:
    elements: tuple[str, ...]
    positions: np.ndarray
    comment: str


@dataclass(frozen=True)
class LockedSource:
    attempt: Path
    profile_rows: list[dict[str, str]]
    barrier_summary_rows: list[dict[str, str]]
    primary_metric_rows: list[dict[str, str]]
    xyz_frames: list[XYZFrame]
    source_hashes: dict[str, str]


@dataclass(frozen=True)
class PreparedInput:
    q_ang: np.ndarray
    energies_ev: dict[str, np.ndarray]
    aligned_xyz: np.ndarray
    elements: tuple[str, ...]
    barriers_ev: dict[str, float]
    endpoint_bias_ev: dict[str, float]
    pbe_wall_curvature_left: float
    pbe_wall_curvature_right: float
    q_source_policy: str
    qpt_series_diagnostics: dict[str, dict[str, Any]]
    qpt_xyz_max_abs_difference_ang: float


@dataclass(frozen=True)
class QuantumResult:
    series: str
    isotope: str
    interpolation: str
    profile_mode: str
    mass_model: str
    grid_points: int
    extension_fraction: float
    barrier_ev: float
    endpoint_bias_ev: float
    e0_ev: float
    e1_ev: float
    e2_ev: float
    e3_ev: float
    gap_ev: float
    gap_mev: float
    gap_cm1: float
    gap_ghz: float
    e1_below_barrier: bool
    e0_below_barrier: bool
    classification: str
    left_probability_e0: float
    right_probability_e0: float
    left_probability_e1: float
    right_probability_e1: float
    min_effective_mass_amu: float
    median_effective_mass_amu: float
    max_effective_mass_amu: float


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    if not path.is_file():
        raise AuditError(f"Missing file: {path}")
    return path.read_text(encoding="utf-8")


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise AuditError(f"Missing TSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle, delimiter="\t")]
    if not rows:
        raise AuditError(f"TSV is empty: {path}")
    return rows


def write_tsv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        if not rows:
            raise AuditError(f"Cannot infer field names for empty table: {path}")
        fieldnames = list(rows[0].keys())
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    os.replace(temporary, path)


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_float(value: Any, label: str) -> float:
    try:
        result = float(str(value).strip())
    except Exception as exc:
        raise AuditError(f"Invalid float for {label}: {value!r}") from exc
    if not math.isfinite(result):
        raise AuditError(f"Non-finite float for {label}: {value!r}")
    return result


def parse_int(value: Any, label: str) -> int:
    try:
        return int(str(value).strip())
    except Exception as exc:
        raise AuditError(f"Invalid integer for {label}: {value!r}") from exc


def parse_xyz(path: Path) -> list[XYZFrame]:
    lines = read_text(path).splitlines()
    frames: list[XYZFrame] = []
    cursor = 0
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        atom_count = parse_int(lines[cursor], f"atom count at line {cursor + 1}")
        if cursor + atom_count + 1 >= len(lines):
            raise AuditError(f"Truncated XYZ frame in {path}")
        comment = lines[cursor + 1]
        elements: list[str] = []
        positions: list[list[float]] = []
        for offset in range(atom_count):
            tokens = lines[cursor + 2 + offset].split()
            if len(tokens) < 4:
                raise AuditError(f"Invalid XYZ row: {lines[cursor + 2 + offset]!r}")
            elements.append(tokens[0])
            positions.append([parse_float(tokens[i], "XYZ coordinate") for i in (1, 2, 3)])
        frames.append(XYZFrame(tuple(elements), np.asarray(positions, dtype=float), comment))
        cursor += atom_count + 2
    return frames


def resolve_source_attempt(root: Path) -> Path:
    version_root = (root / INPUT_VERSION_ROOT).resolve()
    pointer = version_root / INPUT_POINTER
    if pointer.is_file():
        raw = pointer.read_text(encoding="utf-8").strip()
        if not raw:
            raise AuditError(f"Empty pointer: {pointer}")
        attempt = Path(raw).expanduser().resolve()
    else:
        candidates = sorted(path for path in version_root.glob("attempt_*") if path.is_dir())
        if not candidates:
            raise AuditError(f"No v005 source attempt found under {version_root}")
        attempt = candidates[-1].resolve()
    try:
        attempt.relative_to(version_root)
    except ValueError as exc:
        raise AuditError(f"Resolved attempt escapes expected v005 root: {attempt}") from exc
    observed_status = read_text(attempt / INPUT_STATUS_FILE).strip()
    if observed_status != EXPECTED_INPUT_STATUS:
        raise AuditError(f"Unexpected v005 status {observed_status!r}; expected {EXPECTED_INPUT_STATUS!r}")
    return attempt


def verify_checksum(attempt: Path, checksum_rows: Sequence[Mapping[str, str]], relative: str) -> str:
    matches = [row for row in checksum_rows if row.get("relative_path") == relative]
    if len(matches) != 1:
        raise AuditError(f"Expected one checksum row for {relative}; found {len(matches)}")
    row = matches[0]
    target = attempt / relative
    if not target.is_file():
        raise AuditError(f"Checksum target missing: {target}")
    expected_size = parse_int(row.get("size_bytes", ""), f"size for {relative}")
    expected_sha = str(row.get("sha256", "")).strip()
    observed_size = target.stat().st_size
    observed_sha = sha256_file(target)
    if observed_size != expected_size or observed_sha != expected_sha:
        raise AuditError(
            f"Checksum mismatch for {relative}: size {observed_size}/{expected_size}; "
            f"sha256 {observed_sha}/{expected_sha}"
        )
    return observed_sha


def load_locked_source(root: Path) -> LockedSource:
    attempt = resolve_source_attempt(root)
    checksum_rows = read_tsv(attempt / CHECKSUM_REL)
    source_hashes = {
        PROFILE_REL: verify_checksum(attempt, checksum_rows, PROFILE_REL),
        BARRIER_SUMMARY_REL: verify_checksum(attempt, checksum_rows, BARRIER_SUMMARY_REL),
        PRIMARY_METRIC_REL: verify_checksum(attempt, checksum_rows, PRIMARY_METRIC_REL),
        XYZ_REL: verify_checksum(attempt, checksum_rows, XYZ_REL),
    }
    profile_rows = read_tsv(attempt / PROFILE_REL)
    if not profile_rows:
        raise AuditError(f"Frozen audit profile is empty: {PROFILE_REL}")
    required_profile_columns = {
        "series", "image", "qpt_ang", "energy_ev",
        "delta_e_from_lower_endpoint_ev", "profile_error_ev",
    }
    missing = sorted(required_profile_columns - set(profile_rows[0]))
    if missing:
        raise AuditError(
            f"Wrong profile schema for frozen-path audit; missing {missing}. "
            f"Expected checksum-locked {PROFILE_REL}, not a relaxed MTP-NEB path table."
        )
    return LockedSource(
        attempt=attempt,
        profile_rows=profile_rows,
        barrier_summary_rows=read_tsv(attempt / BARRIER_SUMMARY_REL),
        primary_metric_rows=read_tsv(attempt / PRIMARY_METRIC_REL),
        xyz_frames=parse_xyz(attempt / XYZ_REL),
        source_hashes=source_hashes,
    )


def kabsch_align(mobile: np.ndarray, reference: np.ndarray, indices: Sequence[int]) -> np.ndarray:
    p = mobile[np.asarray(indices)]
    q = reference[np.asarray(indices)]
    pc = p.mean(axis=0)
    qc = q.mean(axis=0)
    p0 = p - pc
    q0 = q - qc
    covariance = p0.T @ q0
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    return (mobile - pc) @ rotation + qc


def qpt_from_xyz(xyz: np.ndarray) -> float:
    d_left = float(np.linalg.norm(xyz[TRANSFER_H_INDEX] - xyz[LEFT_O_INDEX]))
    d_right = float(np.linalg.norm(xyz[TRANSFER_H_INDEX] - xyz[RIGHT_O_INDEX]))
    return d_left - d_right


def endpoint_confinement_curvature(q: np.ndarray, v: np.ndarray, side: str) -> float:
    if side == "left":
        dx = q[1:3] - q[0]
        dv = v[1:3] - v[0]
    elif side == "right":
        dx = q[-3:-1] - q[-1]
        dv = v[-3:-1] - v[-1]
    else:
        raise AuditError(f"Unknown side: {side}")
    denominator = float(np.sum(dx ** 4))
    if denominator <= 0:
        raise AuditError("Degenerate endpoint coordinates")
    curvature = float(2.0 * np.sum((dx ** 2) * dv) / denominator)
    if not math.isfinite(curvature) or curvature <= 0:
        raise AuditError(f"Non-positive DFT-derived endpoint curvature on {side}: {curvature}")
    return curvature


def _optional_qpt_array(rows: Sequence[Mapping[str, str]], series: str) -> np.ndarray | None:
    values: list[float] = []
    for image, row in enumerate(rows, start=1):
        raw = str(row.get("qpt_ang", "")).strip()
        if not raw:
            return None
        values.append(parse_float(raw, f"{series} qpt image {image}"))
    return np.asarray(values, dtype=float)


def _qpt_diagnostic(canonical_q: np.ndarray, observed_q: np.ndarray | None, series: str) -> dict[str, Any]:
    if observed_q is None:
        return {
            "series": series,
            "status": "CANONICALIZED_FROM_DFT_QPT_METADATA_MISSING",
            "coordinate_used": "DFT.qpt_ang_by_image",
            "observed_complete": False,
            "max_abs_difference_ang": None,
            "rms_difference_ang": None,
            "strictly_increasing": None,
            "strictly_decreasing": None,
            "pearson_r": None,
        }
    diff = observed_q - canonical_q
    increasing = bool(np.all(np.diff(observed_q) > 0))
    decreasing = bool(np.all(np.diff(observed_q) < 0))
    if np.std(observed_q) > 0 and np.std(canonical_q) > 0:
        pearson = float(np.corrcoef(canonical_q, observed_q)[0, 1])
    else:
        pearson = float("nan")
    max_abs = float(np.max(np.abs(diff)))
    rms = float(np.sqrt(np.mean(diff ** 2)))
    if max_abs <= 1.0e-10:
        status = "IDENTICAL_TO_DFT_QPT"
    elif max_abs <= 5.0e-6:
        status = "ROUNDING_DIFFERENCE_CANONICALIZED_TO_DFT_QPT"
    else:
        status = "MODEL_QPT_METADATA_DIFFERS_CANONICALIZED_TO_DFT_QPT"
    return {
        "series": series,
        "status": status,
        "coordinate_used": "DFT.qpt_ang_by_image",
        "observed_complete": True,
        "max_abs_difference_ang": max_abs,
        "rms_difference_ang": rms,
        "strictly_increasing": increasing,
        "strictly_decreasing": decreasing,
        "pearson_r": pearson,
    }


def prepare_input(source: LockedSource) -> PreparedInput:
    """Prepare a common frozen-path coordinate and three image-indexed energy profiles.

    The frozen path is defined by the checksum-locked DFT NEB9 geometries and DFT
    qPT values. Non-DFT qPT columns are treated as descriptive metadata only.
    They are not allowed to redefine the coordinate because basin and targeted
    energies are compared image-by-image on the same frozen PBE path.
    """
    if len(source.xyz_frames) != 9:
        raise AuditError(f"Expected 9 XYZ frames; found {len(source.xyz_frames)}")
    for frame in source.xyz_frames:
        if frame.elements != EXPECTED_ATOMS:
            raise AuditError(f"Unexpected atom ordering: {frame.elements}")

    by_series: dict[str, list[dict[str, str]]] = {series: [] for series in EXPECTED_SERIES}
    for row in source.profile_rows:
        series = str(row.get("series", "")).strip()
        if series in by_series:
            by_series[series].append(dict(row))
    for series in EXPECTED_SERIES:
        by_series[series].sort(key=lambda row: parse_int(row.get("image", ""), f"{series} image"))
        images = tuple(parse_int(row.get("image", ""), f"{series} image") for row in by_series[series])
        if images != EXPECTED_IMAGES:
            raise AuditError(f"Unexpected image sequence for {series}: {images}")

    q_dft = _optional_qpt_array(by_series["DFT"], "DFT")
    if q_dft is None:
        raise AuditError("DFT qPT metadata is missing; a canonical frozen-path coordinate cannot be established")
    q = q_dft
    if not np.all(np.diff(q) > 0):
        raise AuditError(f"DFT qPT coordinates are not strictly increasing: {q}")

    q_metadata = {series: _optional_qpt_array(rows, series) for series, rows in by_series.items()}
    qpt_diagnostics = {
        series: _qpt_diagnostic(q, q_metadata[series], series)
        for series in EXPECTED_SERIES
    }
    qpt_diagnostics["DFT"]["status"] = "CANONICAL_DFT_QPT"
    qpt_diagnostics["DFT"]["coordinate_used"] = "DFT.qpt_ang_by_image"

    # The correct frozen-audit table evaluates all three energy series on the
    # same nine DFT geometries. Therefore non-DFT qPT metadata must agree with
    # DFT qPT to formatting precision. A large mismatch indicates that a
    # relaxed MTP-NEB path table was supplied and is a hard provenance error.
    for series in ("basin", "targeted"):
        observed = q_metadata[series]
        if observed is None:
            raise AuditError(f"Missing qPT metadata for frozen-path series {series}")
        max_abs = float(np.max(np.abs(observed - q)))
        if max_abs > 1.0e-8:
            raise AuditError(
                f"Frozen-path qPT mismatch for {series}: max abs {max_abs:.6e} Angstrom. "
                f"Expected image-indexed energies on identical DFT NEB9 geometries from {PROFILE_REL}."
            )
        qpt_diagnostics[series]["status"] = "IDENTICAL_FROZEN_DFT_PATH"
        qpt_diagnostics[series]["coordinate_used"] = "DFT.qpt_ang_by_image"

    energies = {
        series: np.asarray([parse_float(row.get("energy_ev", ""), f"{series} energy") for row in rows], dtype=float)
        for series, rows in by_series.items()
    }
    for series in EXPECTED_SERIES:
        if not np.all(np.isfinite(energies[series])):
            raise AuditError(f"Non-finite energies in {series}")
        energies[series] = energies[series] - float(np.min(energies[series][[0, -1]]))

    barriers = {series: float(np.max(v) - np.min(v[[0, -1]])) for series, v in energies.items()}
    endpoint_bias = {series: float(abs(v[-1] - v[0])) for series, v in energies.items()}
    if abs(barriers["DFT"] - EXPECTED_PBE_BARRIER_EV) > 2e-9:
        raise AuditError(
            f"Locked PBE barrier mismatch: {barriers['DFT']:.15f} eV; "
            f"expected {EXPECTED_PBE_BARRIER_EV:.15f} eV"
        )
    basin_error = 1000.0 * abs(barriers["basin"] - barriers["DFT"])
    targeted_error = 1000.0 * abs(barriers["targeted"] - barriers["DFT"])

    # Cross-check against the separately checksum-locked barrier summary. This
    # prevents accidental use of the relaxed MTP-NEB table, which has different
    # geometries and different barrier semantics.
    summary_by_series = {
        str(row.get("series", "")).strip(): row
        for row in source.barrier_summary_rows
        if str(row.get("series", "")).strip() in EXPECTED_SERIES
    }
    if set(summary_by_series) != set(EXPECTED_SERIES):
        raise AuditError(
            f"Unexpected barrier-summary series: {sorted(summary_by_series)}; "
            f"expected {list(EXPECTED_SERIES)}"
        )
    for series in EXPECTED_SERIES:
        row = summary_by_series[series]
        summary_barrier = parse_float(
            row.get("lower_endpoint_barrier_ev", ""),
            f"{series} barrier summary",
        )
        if abs(summary_barrier - barriers[series]) > 2.0e-9:
            raise AuditError(
                f"Profile/barrier-summary mismatch for {series}: "
                f"profile={barriers[series]:.15f} eV, summary={summary_barrier:.15f} eV"
            )
    summary_basin_error = parse_float(
        summary_by_series["basin"].get("absolute_error_mev", ""),
        "basin absolute barrier error summary",
    )
    summary_targeted_error = parse_float(
        summary_by_series["targeted"].get("absolute_error_mev", ""),
        "targeted absolute barrier error summary",
    )
    if abs(basin_error - summary_basin_error) > 2.0e-6:
        raise AuditError(
            f"Computed/summary basin barrier error mismatch: "
            f"{basin_error:.9f}/{summary_basin_error:.9f} meV"
        )
    if abs(targeted_error - summary_targeted_error) > 2.0e-6:
        raise AuditError(
            f"Computed/summary targeted barrier error mismatch: "
            f"{targeted_error:.9f}/{summary_targeted_error:.9f} meV"
        )
    if abs(basin_error - EXPECTED_BASIN_BARRIER_ERROR_MEV) > 0.05:
        raise AuditError(f"Locked basin barrier error mismatch: {basin_error:.6f} meV")
    if abs(targeted_error - EXPECTED_TARGETED_BARRIER_ERROR_MEV) > 0.05:
        raise AuditError(f"Locked targeted barrier error mismatch: {targeted_error:.6f} meV")

    # Independently verify the preregistered primary metric table.
    barrier_metric_rows = [
        row for row in source.primary_metric_rows
        if str(row.get("metric", "")).strip() == "lower_endpoint_barrier_abs_error_mev"
    ]
    if len(barrier_metric_rows) != 1:
        raise AuditError(
            f"Expected one lower_endpoint_barrier_abs_error_mev row; found {len(barrier_metric_rows)}"
        )
    metric_row = barrier_metric_rows[0]
    metric_basin = parse_float(metric_row.get("basin", ""), "primary metric basin barrier error")
    metric_targeted = parse_float(metric_row.get("targeted", ""), "primary metric targeted barrier error")
    if abs(metric_basin - basin_error) > 2.0e-6 or abs(metric_targeted - targeted_error) > 2.0e-6:
        raise AuditError(
            "Frozen profile does not reproduce preregistered primary barrier errors: "
            f"computed basin/targeted={basin_error:.9f}/{targeted_error:.9f} meV; "
            f"locked metric={metric_basin:.9f}/{metric_targeted:.9f} meV"
        )

    reference = source.xyz_frames[4].positions
    aligned = np.stack([
        kabsch_align(frame.positions, reference, HEAVY_INDICES)
        for frame in source.xyz_frames
    ])
    q_xyz = np.asarray([qpt_from_xyz(frame) for frame in aligned])
    max_q_difference = float(np.max(np.abs(q_xyz - q)))
    # This tolerance matches the already validated v005 visualization audit.
    # The TSV qPT is the canonical reaction coordinate; XYZ is an independent
    # geometry-consistency check and may differ slightly by formatting/convention.
    if max_q_difference > 3.0e-2:
        raise AuditError(
            f"qPT mismatch between DFT XYZ and DFT TSV: max abs {max_q_difference:.6e} Angstrom; "
            "expected <= 3.0e-2 Angstrom"
        )

    k_left = endpoint_confinement_curvature(q, energies["DFT"], "left")
    k_right = endpoint_confinement_curvature(q, energies["DFT"], "right")
    return PreparedInput(
        q_ang=q,
        energies_ev=energies,
        aligned_xyz=aligned,
        elements=EXPECTED_ATOMS,
        barriers_ev=barriers,
        endpoint_bias_ev=endpoint_bias,
        pbe_wall_curvature_left=k_left,
        pbe_wall_curvature_right=k_right,
        q_source_policy="DFT_QPT_CANONICAL_FOR_ALL_IMAGE_INDEXED_ENERGY_SERIES",
        qpt_series_diagnostics=qpt_diagnostics,
        qpt_xyz_max_abs_difference_ang=max_q_difference,
    )


def atomic_masses(elements: Sequence[str], isotope: str) -> np.ndarray:
    masses = np.asarray([ATOMIC_MASS_AMU[element] for element in elements], dtype=float)
    if isotope == "D":
        masses[TRANSFER_H_INDEX] = ATOMIC_MASS_AMU["D"]
    elif isotope != "H":
        raise AuditError(f"Unknown isotope: {isotope}")
    return masses


def path_metric_mass(prepared: PreparedInput, isotope: str, q_eval: np.ndarray) -> np.ndarray:
    masses = atomic_masses(prepared.elements, isotope)
    q = prepared.q_ang
    derivative_sq_sum = np.zeros_like(q_eval, dtype=float)
    for atom in range(prepared.aligned_xyz.shape[1]):
        atom_derivative_sq = np.zeros_like(q_eval, dtype=float)
        for component in range(3):
            spline = CubicSpline(q, prepared.aligned_xyz[:, atom, component], bc_type="natural")
            derivative = spline(q_eval, 1)
            atom_derivative_sq += derivative ** 2
        derivative_sq_sum += masses[atom] * atom_derivative_sq
    if not np.all(np.isfinite(derivative_sq_sum)) or float(np.min(derivative_sq_sum)) <= 0:
        raise AuditError("Invalid path-metric effective mass")
    return derivative_sq_sum


def transfer_particle_mass(isotope: str, q_eval: np.ndarray) -> np.ndarray:
    if isotope not in ("H", "D"):
        raise AuditError(f"Unknown isotope: {isotope}")
    return np.full_like(q_eval, ATOMIC_MASS_AMU[isotope], dtype=float)


def interpolate_inside(q: np.ndarray, values: np.ndarray, q_eval: np.ndarray, method: str) -> np.ndarray:
    if method == "pchip":
        return np.asarray(PchipInterpolator(q, values)(q_eval), dtype=float)
    if method == "linear":
        return np.interp(q_eval, q, values)
    raise AuditError(f"Unknown interpolation method: {method}")


def common_domain(prepared: PreparedInput, profile_mode: str, extension_fraction: float) -> tuple[float, float, float]:
    q = prepared.q_ang
    if profile_mode == "raw":
        left, right = float(q[0]), float(q[-1])
        span = right - left
        return left - extension_fraction * span, right + extension_fraction * span, 0.0
    if profile_mode == "symmetrized":
        center = float(q[4])
        half = min(center - float(q[0]), float(q[-1]) - center)
        span = 2.0 * half
        return -half - extension_fraction * span, half + extension_fraction * span, center
    raise AuditError(f"Unknown profile mode: {profile_mode}")


def build_grid_potential_and_mass(
    prepared: PreparedInput,
    series: str,
    isotope: str,
    interpolation: str,
    profile_mode: str,
    mass_model: str,
    grid_points: int,
    extension_fraction: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    if grid_points < 301 or grid_points % 2 == 0:
        raise AuditError("grid_points must be odd and at least 301")
    q = prepared.q_ang
    v = prepared.energies_ev[series]
    left_domain, right_domain, center = common_domain(prepared, profile_mode, extension_fraction)
    grid = np.linspace(left_domain, right_domain, grid_points)

    if profile_mode == "raw":
        inside_left, inside_right = float(q[0]), float(q[-1])
        inside_mask = (grid >= inside_left) & (grid <= inside_right)
        potential = np.empty_like(grid)
        potential[inside_mask] = interpolate_inside(q, v, grid[inside_mask], interpolation)
        potential[grid < inside_left] = v[0] + 0.5 * prepared.pbe_wall_curvature_left * (grid[grid < inside_left] - inside_left) ** 2
        potential[grid > inside_right] = v[-1] + 0.5 * prepared.pbe_wall_curvature_right * (grid[grid > inside_right] - inside_right) ** 2

        q_for_mass = np.clip(grid, q[0], q[-1])
        if mass_model == "path_metric":
            mass = path_metric_mass(prepared, isotope, q_for_mass)
        elif mass_model == "transfer_particle":
            mass = transfer_particle_mass(isotope, q_for_mass)
        else:
            raise AuditError(f"Unknown mass model: {mass_model}")
        endpoint_bias = prepared.endpoint_bias_ev[series]
        barrier = prepared.barriers_ev[series]
    else:
        shifted_q = q - center
        half = min(-float(shifted_q[0]), float(shifted_q[-1]))
        inside_mask = (grid >= -half) & (grid <= half)
        sample = grid[inside_mask]
        v_plus = interpolate_inside(shifted_q, v, sample, interpolation)
        v_minus = interpolate_inside(shifted_q, v, -sample, interpolation)
        potential = np.empty_like(grid)
        potential[inside_mask] = 0.5 * (v_plus + v_minus)
        endpoint_level = float(0.5 * (
            interpolate_inside(shifted_q, v, np.asarray([-half]), interpolation)[0]
            + interpolate_inside(shifted_q, v, np.asarray([half]), interpolation)[0]
        ))
        common_k = 0.5 * (prepared.pbe_wall_curvature_left + prepared.pbe_wall_curvature_right)
        potential[grid < -half] = endpoint_level + 0.5 * common_k * (grid[grid < -half] + half) ** 2
        potential[grid > half] = endpoint_level + 0.5 * common_k * (grid[grid > half] - half) ** 2

        q_plus = np.clip(sample + center, q[0], q[-1])
        q_minus = np.clip(-sample + center, q[0], q[-1])
        if mass_model == "path_metric":
            m_plus = path_metric_mass(prepared, isotope, q_plus)
            m_minus = path_metric_mass(prepared, isotope, q_minus)
            m_inside = 0.5 * (m_plus + m_minus)
            mass = np.empty_like(grid)
            mass[inside_mask] = m_inside
            mass[grid < -half] = m_inside[0]
            mass[grid > half] = m_inside[-1]
        elif mass_model == "transfer_particle":
            mass = transfer_particle_mass(isotope, grid)
        else:
            raise AuditError(f"Unknown mass model: {mass_model}")
        endpoint_bias = 0.0
        barrier = float(np.max(potential[inside_mask]) - np.min(potential[inside_mask]))

    potential = potential - float(np.min(potential))
    if not np.all(np.isfinite(potential)) or not np.all(np.isfinite(mass)):
        raise AuditError("Non-finite potential or mass")
    if float(np.min(mass)) <= 0:
        raise AuditError("Effective mass is non-positive")
    return grid, potential, mass, barrier, endpoint_bias


def solve_hamiltonian(grid: np.ndarray, potential: np.ndarray, mass: np.ndarray, n_levels: int = N_LEVELS) -> tuple[np.ndarray, np.ndarray]:
    h = float(grid[1] - grid[0])
    if not np.allclose(np.diff(grid), h, atol=1e-12, rtol=1e-10):
        raise AuditError("Hamiltonian grid is not uniform")
    inv_mass = 1.0 / mass
    inv_half = 0.5 * (inv_mass[:-1] + inv_mass[1:])
    # Dirichlet boundaries: solve only for interior points.
    diagonal = (
        KINETIC_COEFF_EV_A2_PER_AMU / (h * h)
        * (inv_half[:-1] + inv_half[1:])
        + potential[1:-1]
    )
    offdiag = -KINETIC_COEFF_EV_A2_PER_AMU / (h * h) * inv_half[1:-1]
    if diagonal.size <= n_levels + 2:
        raise AuditError("Hamiltonian grid too small")
    eigenvalues, eigenvectors = eigh_tridiagonal(
        diagonal,
        offdiag,
        select="i",
        select_range=(0, n_levels - 1),
        check_finite=True,
        lapack_driver="stebz",
    )
    # Normalize eigenvectors with the coordinate-space quadrature measure.
    norms = np.sqrt(np.sum(eigenvectors ** 2, axis=0) * h)
    eigenvectors = eigenvectors / norms
    return np.asarray(eigenvalues), np.asarray(eigenvectors)


def side_probability(grid: np.ndarray, wavefunction_interior: np.ndarray) -> tuple[float, float]:
    h = float(grid[1] - grid[0])
    interior = grid[1:-1]
    density = wavefunction_interior ** 2
    left = float(np.sum(density[interior < 0]) * h)
    right = float(np.sum(density[interior > 0]) * h)
    total = left + right
    if total > 0:
        left /= total
        right /= total
    return left, right


def classify_levels(eigenvalues: np.ndarray, barrier: float, profile_mode: str, endpoint_bias: float) -> str:
    e0, e1 = float(eigenvalues[0]), float(eigenvalues[1])
    if e1 < barrier:
        if profile_mode == "symmetrized":
            return "subbarrier_symmetric_doublet"
        if endpoint_bias <= max(1e-5, 0.1 * (e1 - e0)):
            return "subbarrier_nearly_symmetric_doublet"
        return "subbarrier_biased_low_level_pair"
    if e0 < barrier <= e1:
        return "only_ground_state_below_barrier"
    return "no_low_subbarrier_doublet"


def compute_result(
    prepared: PreparedInput,
    series: str,
    isotope: str,
    interpolation: str,
    profile_mode: str,
    mass_model: str,
    grid_points: int,
    extension_fraction: float,
) -> tuple[QuantumResult, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    grid, potential, mass, barrier, endpoint_bias = build_grid_potential_and_mass(
        prepared,
        series,
        isotope,
        interpolation,
        profile_mode,
        mass_model,
        grid_points,
        extension_fraction,
    )
    eigenvalues, eigenvectors = solve_hamiltonian(grid, potential, mass)
    gap = float(eigenvalues[1] - eigenvalues[0])
    l0, r0 = side_probability(grid, eigenvectors[:, 0])
    l1, r1 = side_probability(grid, eigenvectors[:, 1])
    classification = classify_levels(eigenvalues, barrier, profile_mode, endpoint_bias)
    result = QuantumResult(
        series=series,
        isotope=isotope,
        interpolation=interpolation,
        profile_mode=profile_mode,
        mass_model=mass_model,
        grid_points=grid_points,
        extension_fraction=extension_fraction,
        barrier_ev=barrier,
        endpoint_bias_ev=endpoint_bias,
        e0_ev=float(eigenvalues[0]),
        e1_ev=float(eigenvalues[1]),
        e2_ev=float(eigenvalues[2]),
        e3_ev=float(eigenvalues[3]),
        gap_ev=gap,
        gap_mev=1000.0 * gap,
        gap_cm1=EV_TO_WAVENUMBER_CM * gap,
        gap_ghz=EV_TO_GHZ * gap,
        e1_below_barrier=bool(eigenvalues[1] < barrier),
        e0_below_barrier=bool(eigenvalues[0] < barrier),
        classification=classification,
        left_probability_e0=l0,
        right_probability_e0=r0,
        left_probability_e1=l1,
        right_probability_e1=r1,
        min_effective_mass_amu=float(np.min(mass)),
        median_effective_mass_amu=float(np.median(mass)),
        max_effective_mass_amu=float(np.max(mass)),
    )
    return result, grid, potential, mass, eigenvalues, eigenvectors


def result_to_row(result: QuantumResult) -> dict[str, Any]:
    return {
        "series": result.series,
        "series_label": LABELS[result.series],
        "isotope": result.isotope,
        "interpolation": result.interpolation,
        "profile_mode": result.profile_mode,
        "mass_model": result.mass_model,
        "grid_points": result.grid_points,
        "extension_fraction": result.extension_fraction,
        "barrier_ev": result.barrier_ev,
        "barrier_mev": 1000.0 * result.barrier_ev,
        "endpoint_bias_ev": result.endpoint_bias_ev,
        "endpoint_bias_mev": 1000.0 * result.endpoint_bias_ev,
        "e0_ev": result.e0_ev,
        "e1_ev": result.e1_ev,
        "e2_ev": result.e2_ev,
        "e3_ev": result.e3_ev,
        "gap_ev": result.gap_ev,
        "gap_mev": result.gap_mev,
        "gap_cm1": result.gap_cm1,
        "gap_ghz": result.gap_ghz,
        "e0_below_barrier": result.e0_below_barrier,
        "e1_below_barrier": result.e1_below_barrier,
        "classification": result.classification,
        "left_probability_e0": result.left_probability_e0,
        "right_probability_e0": result.right_probability_e0,
        "left_probability_e1": result.left_probability_e1,
        "right_probability_e1": result.right_probability_e1,
        "min_effective_mass_amu": result.min_effective_mass_amu,
        "median_effective_mass_amu": result.median_effective_mass_amu,
        "max_effective_mass_amu": result.max_effective_mass_amu,
    }


def run_all_formulations(prepared: PreparedInput, grid_points: int, extension_fraction: float) -> tuple[list[QuantumResult], dict[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]]:
    results: list[QuantumResult] = []
    primary_payloads: dict[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    for profile_mode in ("symmetrized", "raw"):
        for interpolation in ("pchip", "linear"):
            for mass_model in ("path_metric", "transfer_particle"):
                for isotope in ("H", "D"):
                    for series in EXPECTED_SERIES:
                        result, grid, potential, mass, levels, vectors = compute_result(
                            prepared,
                            series,
                            isotope,
                            interpolation,
                            profile_mode,
                            mass_model,
                            grid_points,
                            extension_fraction,
                        )
                        results.append(result)
                        if (
                            profile_mode == PRIMARY_PROFILE_MODE
                            and interpolation == PRIMARY_INTERPOLATION
                            and mass_model == PRIMARY_MASS_MODEL
                        ):
                            primary_payloads[(series, isotope)] = (grid, potential, mass, levels, vectors)
    return results, primary_payloads


def primary_results(results: Sequence[QuantumResult]) -> list[QuantumResult]:
    selected = [
        row for row in results
        if row.profile_mode == PRIMARY_PROFILE_MODE
        and row.interpolation == PRIMARY_INTERPOLATION
        and row.mass_model == PRIMARY_MASS_MODEL
    ]
    selected.sort(key=lambda row: (row.isotope, EXPECTED_SERIES.index(row.series)))
    if len(selected) != 6:
        raise AuditError(f"Expected 6 primary results; found {len(selected)}")
    return selected


def robustness_rows(results: Sequence[QuantumResult]) -> list[dict[str, Any]]:
    lookup = {
        (row.profile_mode, row.interpolation, row.mass_model, row.isotope, row.series): row
        for row in results
    }
    rows: list[dict[str, Any]] = []
    for profile_mode in ("symmetrized", "raw"):
        for interpolation in ("pchip", "linear"):
            for mass_model in ("path_metric", "transfer_particle"):
                for isotope in ("H", "D"):
                    dft = lookup[(profile_mode, interpolation, mass_model, isotope, "DFT")]
                    basin = lookup[(profile_mode, interpolation, mass_model, isotope, "basin")]
                    targeted = lookup[(profile_mode, interpolation, mass_model, isotope, "targeted")]
                    basin_error = abs(basin.gap_mev - dft.gap_mev)
                    targeted_error = abs(targeted.gap_mev - dft.gap_mev)
                    rows.append({
                        "profile_mode": profile_mode,
                        "interpolation": interpolation,
                        "mass_model": mass_model,
                        "isotope": isotope,
                        "dft_gap_mev": dft.gap_mev,
                        "basin_gap_mev": basin.gap_mev,
                        "targeted_gap_mev": targeted.gap_mev,
                        "basin_abs_error_mev": basin_error,
                        "targeted_abs_error_mev": targeted_error,
                        "targeted_better": targeted_error < basin_error,
                        "basin_classification": basin.classification,
                        "targeted_classification": targeted.classification,
                        "dft_classification": dft.classification,
                    })
    return rows


def convergence_rows(prepared: PreparedInput, extension_fraction: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_case: dict[tuple[str, str], list[QuantumResult]] = {}
    for isotope in ("H", "D"):
        for series in EXPECTED_SERIES:
            case_results: list[QuantumResult] = []
            for grid in CONVERGENCE_GRIDS:
                result, *_ = compute_result(
                    prepared,
                    series,
                    isotope,
                    PRIMARY_INTERPOLATION,
                    PRIMARY_PROFILE_MODE,
                    PRIMARY_MASS_MODEL,
                    grid,
                    extension_fraction,
                )
                case_results.append(result)
            by_case[(series, isotope)] = case_results
            reference = case_results[-1].gap_mev
            for result in case_results:
                absolute = abs(result.gap_mev - reference)
                relative = absolute / max(abs(reference), 1e-12)
                rows.append({
                    "series": series,
                    "isotope": isotope,
                    "grid_points": result.grid_points,
                    "gap_mev": result.gap_mev,
                    "reference_grid_points": CONVERGENCE_GRIDS[-1],
                    "absolute_difference_from_finest_mev": absolute,
                    "relative_difference_from_finest": relative,
                    "converged": absolute <= 0.01 or relative <= 0.005,
                })
    return rows


def create_run_dir(root: Path) -> Path:
    version_root = root / "10_visualization" / "versions" / VERSION_DIR
    ensure_dir(version_root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = version_root / f"attempt_{stamp}"
    suffix = 1
    while run_dir.exists():
        run_dir = version_root / f"attempt_{stamp}_{suffix:02d}"
        suffix += 1
    ensure_dir(run_dir)
    return run_dir


def snapshot_source(source: LockedSource, destination: Path) -> None:
    for relative in (PROFILE_REL, BARRIER_SUMMARY_REL, PRIMARY_METRIC_REL, XYZ_REL, CHECKSUM_REL, INPUT_STATUS_FILE):
        src = source.attempt / relative
        dst = destination / relative
        ensure_dir(dst.parent)
        shutil.copy2(src, dst)


def render_figure(
    run_dir: Path,
    prepared: PreparedInput,
    primary: Sequence[QuantumResult],
    primary_payloads: Mapping[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    robustness: Sequence[Mapping[str, Any]],
) -> list[Path]:
    fig = plt.figure(figsize=(13.6, 6.8), facecolor="white")
    gs = fig.add_gridspec(1, 2, width_ratios=[1.32, 1.0], left=0.07, right=0.97, bottom=0.12, top=0.87, wspace=0.24)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])

    # Panel A: primary symmetrized potentials and H low levels.
    for series in EXPECTED_SERIES:
        grid, potential, _, levels, _ = primary_payloads[(series, "H")]
        ax_a.plot(grid, 1000.0 * potential, color=COLORS[series], lw=2.4, label=LABELS[series])
        x_fraction = {"DFT": 0.20, "basin": 0.50, "targeted": 0.80}[series]
        xmin = grid[0] + x_fraction * (grid[-1] - grid[0]) - 0.08 * (grid[-1] - grid[0])
        xmax = xmin + 0.16 * (grid[-1] - grid[0])
        ax_a.hlines(1000.0 * levels[0], xmin, xmax, color=COLORS[series], lw=1.4)
        ax_a.hlines(1000.0 * levels[1], xmin, xmax, color=COLORS[series], lw=1.4, ls="--")
    ax_a.set_xlabel(r"Symmetrized proton-transfer coordinate $q_{PT}$ (Å)")
    ax_a.set_ylabel("Relative potential / level energy (meV)")
    ax_a.set_title("a  Frozen-path 1D potentials and two lowest H levels", loc="left", fontweight="bold")
    ax_a.legend(frameon=False, fontsize=9.5)
    ax_a.spines[["top", "right"]].set_visible(False)
    ax_a.grid(axis="y", color="#E6E6E6", lw=0.8)
    ax_a.text(
        0.02,
        0.03,
        "Solid short line: E0   Dashed short line: E1\n"
        "Primary formulation: PCHIP + symmetrized profile + path-metric mass",
        transform=ax_a.transAxes,
        fontsize=8.7,
        color="#555555",
        va="bottom",
    )

    # Panel B: H/D gaps and error to PBE.
    primary_lookup = {(row.series, row.isotope): row for row in primary}
    x = np.arange(3)
    width = 0.34
    h_values = [primary_lookup[(series, "H")].gap_mev for series in EXPECTED_SERIES]
    d_values = [primary_lookup[(series, "D")].gap_mev for series in EXPECTED_SERIES]
    bars_h = ax_b.bar(x - width / 2, h_values, width, label="H", color=[COLORS[s] for s in EXPECTED_SERIES], alpha=0.95)
    bars_d = ax_b.bar(x + width / 2, d_values, width, label="D", color=[COLORS[s] for s in EXPECTED_SERIES], alpha=0.42, hatch="//")
    ax_b.set_xticks(x, ["PBE", "Basin", "Targeted"])
    ax_b.set_ylabel("Lowest-level gap (meV)")
    ax_b.set_title("b  PBE-derived H/D low-level gaps", loc="left", fontweight="bold")
    ax_b.spines[["top", "right"]].set_visible(False)
    ax_b.grid(axis="y", color="#E6E6E6", lw=0.8)
    ax_b.legend(frameon=False)
    for bar in [*bars_h, *bars_d]:
        height = bar.get_height()
        ax_b.text(bar.get_x() + bar.get_width() / 2, height, f"{height:.2f}", ha="center", va="bottom", fontsize=8)

    comparison_count = len(robustness)
    targeted_wins = sum(bool(row["targeted_better"]) for row in robustness)
    ax_b.text(
        0.02,
        0.98,
        f"Targeted closer to PBE in {targeted_wins}/{comparison_count} predeclared formulations",
        transform=ax_b.transAxes,
        fontsize=9.2,
        va="top",
        color="#2D5F8B",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#EEF5FB", edgecolor="#AFC7DD"),
    )

    fig.suptitle(
        "Frozen-path 1D quantum audit of proton transfer in malonaldehyde",
        fontsize=16.5,
        fontweight="bold",
        y=0.96,
    )
    fig.text(
        0.07,
        0.91,
        "Tests whether transition-focused equal-budget sampling improves a PBE-derived quantum nuclear observable; not an experimental rate prediction.",
        fontsize=10.4,
        color="#555555",
    )

    figures = run_dir / "figures"
    ensure_dir(figures)
    paths = [
        figures / "supplementary_figure_s3_frozen_path_tunneling_audit_v039.png",
        figures / "supplementary_figure_s3_frozen_path_tunneling_audit_v039.pdf",
        figures / "supplementary_figure_s3_frozen_path_tunneling_audit_v039.svg",
        figures / "supplementary_figure_s3_frozen_path_tunneling_audit_v039.tiff",
    ]
    fig.savefig(paths[0], dpi=220)
    fig.savefig(paths[1])
    fig.savefig(paths[2])
    fig.savefig(paths[3], dpi=300)
    plt.close(fig)

    # Effective-mass diagnostic.
    fig2, ax = plt.subplots(figsize=(7.2, 4.5), facecolor="white")
    for isotope, style in (("H", "-"), ("D", "--")):
        grid, _, mass, _, _ = primary_payloads[("DFT", isotope)]
        ax.plot(grid, mass, style, lw=2.0, label=isotope)
    ax.set_xlabel(r"Symmetrized $q_{PT}$ (Å)")
    ax.set_ylabel("Path-metric effective mass (amu)")
    ax.set_title("Frozen PBE-path effective-mass diagnostic")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#E6E6E6", lw=0.8)
    ax.legend(frameon=False)
    mass_path = figures / "supplementary_figure_s3_effective_mass_diagnostic_v039.png"
    fig2.savefig(mass_path, dpi=220, bbox_inches="tight")
    plt.close(fig2)
    paths.append(mass_path)
    return paths


def write_checksums(run_dir: Path) -> Path:
    output = run_dir / "checksums_v039.tsv"
    rows: list[dict[str, Any]] = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path != output:
            rows.append({
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "relative_path": str(path.relative_to(run_dir)),
            })
    write_tsv(output, rows, ["sha256", "size_bytes", "relative_path"])
    return output


def conclusion_from_robustness(robustness: Sequence[Mapping[str, Any]], primary: Sequence[QuantumResult]) -> tuple[str, dict[str, Any]]:
    wins = sum(bool(row["targeted_better"]) for row in robustness)
    total = len(robustness)
    fraction = wins / total if total else 0.0
    primary_lookup = {(row.series, row.isotope): row for row in primary}
    primary_h = abs(primary_lookup[("targeted", "H")].gap_mev - primary_lookup[("DFT", "H")].gap_mev) < abs(primary_lookup[("basin", "H")].gap_mev - primary_lookup[("DFT", "H")].gap_mev)
    primary_d = abs(primary_lookup[("targeted", "D")].gap_mev - primary_lookup[("DFT", "D")].gap_mev) < abs(primary_lookup[("basin", "D")].gap_mev - primary_lookup[("DFT", "D")].gap_mev)
    if primary_h and primary_d and fraction == 1.0:
        classification = "HYPOTHESIS_SUPPORTED_ACROSS_ALL_PREDECLARED_FORMULATIONS"
    elif primary_h and primary_d and fraction >= 0.75:
        classification = "HYPOTHESIS_SUPPORTED_WITH_SENSITIVITY_CAVEATS"
    else:
        classification = "HYPOTHESIS_NOT_ROBUSTLY_SUPPORTED"
    return classification, {
        "targeted_better_count": wins,
        "comparison_count": total,
        "targeted_better_fraction": fraction,
        "primary_H_targeted_better": primary_h,
        "primary_D_targeted_better": primary_d,
    }


def execute(root: Path, grid_points: int, extension_fraction: float, validate_only: bool = False) -> int:
    source = load_locked_source(root)
    prepared = prepare_input(source)
    if validate_only:
        print("VALIDATE_ONLY=PASS")
        print(f"INPUT_ATTEMPT={source.attempt}")
        print(f"PBE_BARRIER_MEV={1000.0 * prepared.barriers_ev['DFT']:.12f}")
        print(f"BASIN_BARRIER_MEV={1000.0 * prepared.barriers_ev['basin']:.12f}")
        print(f"TARGETED_BARRIER_MEV={1000.0 * prepared.barriers_ev['targeted']:.12f}")
        print(f"PBE_WALL_CURVATURE_LEFT_EV_A2={prepared.pbe_wall_curvature_left:.12f}")
        print(f"PBE_WALL_CURVATURE_RIGHT_EV_A2={prepared.pbe_wall_curvature_right:.12f}")
        print(f"QPT_COORDINATE_POLICY={prepared.q_source_policy}")
        print(f"QPT_XYZ_MAX_ABS_DIFFERENCE_ANG={prepared.qpt_xyz_max_abs_difference_ang:.12e}")
        for series in EXPECTED_SERIES:
            diagnostic = prepared.qpt_series_diagnostics[series]
            print(f"QPT_METADATA_{series.upper()}={diagnostic['status']}")
            if diagnostic.get('max_abs_difference_ang') is not None:
                print(f"QPT_METADATA_{series.upper()}_MAX_ABS_DIFFERENCE_ANG={diagnostic['max_abs_difference_ang']:.12e}")
        print("DFT_EXECUTION=NONE")
        print("MD_EXECUTION=NONE")
        return 0

    run_dir = create_run_dir(root)
    snapshot_source(source, run_dir / "source_snapshot")
    results, primary_payloads = run_all_formulations(prepared, grid_points, extension_fraction)
    primary = primary_results(results)
    robustness = robustness_rows(results)
    convergence = convergence_rows(prepared, extension_fraction)
    conclusion, conclusion_metrics = conclusion_from_robustness(robustness, primary)

    # Input profile table.
    profile_rows: list[dict[str, Any]] = []
    for series in EXPECTED_SERIES:
        for image, (q, energy) in enumerate(zip(prepared.q_ang, prepared.energies_ev[series]), start=1):
            profile_rows.append({
                "series": series,
                "image": image,
                "qpt_ang": q,
                "relative_energy_ev": energy,
                "relative_energy_mev": 1000.0 * energy,
            })
    write_tsv(run_dir / "tables" / "frozen_path_input_profiles_v039.tsv", profile_rows)

    qpt_provenance_rows: list[dict[str, Any]] = []
    by_series_rows: dict[str, list[dict[str, str]]] = {series: [] for series in EXPECTED_SERIES}
    for row in source.profile_rows:
        series = str(row.get("series", "")).strip()
        if series in by_series_rows:
            by_series_rows[series].append(dict(row))
    for series in EXPECTED_SERIES:
        by_series_rows[series].sort(key=lambda row: parse_int(row.get("image", ""), f"{series} image"))
        diagnostic = prepared.qpt_series_diagnostics[series]
        for image, (canonical_q, source_row) in enumerate(zip(prepared.q_ang, by_series_rows[series]), start=1):
            raw = str(source_row.get("qpt_ang", "")).strip()
            observed = parse_float(raw, f"{series} qpt") if raw else None
            qpt_provenance_rows.append({
                "series": series,
                "image": image,
                "canonical_dft_qpt_ang": canonical_q,
                "source_series_qpt_ang": "" if observed is None else observed,
                "source_minus_canonical_ang": "" if observed is None else observed - canonical_q,
                "coordinate_used_for_hamiltonian": canonical_q,
                "series_qpt_status": diagnostic["status"],
                "coordinate_policy": prepared.q_source_policy,
            })
    write_tsv(run_dir / "tables" / "qpt_coordinate_provenance_v039.tsv", qpt_provenance_rows)
    write_tsv(run_dir / "tables" / "quantum_results_all_formulations_v039.tsv", [result_to_row(row) for row in results])
    write_tsv(run_dir / "tables" / "quantum_results_primary_v039.tsv", [result_to_row(row) for row in primary])
    write_tsv(run_dir / "tables" / "robustness_comparisons_v039.tsv", robustness)
    write_tsv(run_dir / "tables" / "grid_convergence_v039.tsv", convergence)

    potential_rows: list[dict[str, Any]] = []
    mass_rows: list[dict[str, Any]] = []
    for isotope in ("H", "D"):
        for series in EXPECTED_SERIES:
            grid, potential, mass, levels, _ = primary_payloads[(series, isotope)]
            for index, (q, v, m) in enumerate(zip(grid, potential, mass)):
                potential_rows.append({
                    "series": series,
                    "isotope": isotope,
                    "grid_index": index,
                    "qpt_ang": q,
                    "potential_ev": v,
                    "potential_mev": 1000.0 * v,
                    "effective_mass_amu": m,
                    "e0_ev": levels[0],
                    "e1_ev": levels[1],
                })
            if series == "DFT":
                for index, (q, m) in enumerate(zip(grid, mass)):
                    mass_rows.append({
                        "isotope": isotope,
                        "grid_index": index,
                        "qpt_ang": q,
                        "effective_mass_amu": m,
                    })
    write_tsv(run_dir / "tables" / "primary_potential_and_mass_grid_v039.tsv", potential_rows)
    write_tsv(run_dir / "tables" / "effective_mass_profiles_v039.tsv", mass_rows)

    figure_paths = render_figure(run_dir, prepared, primary, primary_payloads, robustness)

    all_converged = all(bool(row["converged"]) for row in convergence if row["grid_points"] != CONVERGENCE_GRIDS[-1])
    primary_lookup = {(row.series, row.isotope): row for row in primary}
    isotope_checks = {
        series: primary_lookup[(series, "D")].gap_mev < primary_lookup[(series, "H")].gap_mev
        for series in EXPECTED_SERIES
    }

    validation_rows = [
        {"check": "locked_source_checksums", "status": "PASS", "detail": json.dumps(source.source_hashes, sort_keys=True)},
        {"check": "series_and_images", "status": "PASS", "detail": "DFT/basin/targeted; images 1..9"},
        {"check": "atom_order", "status": "PASS", "detail": ",".join(EXPECTED_ATOMS)},
        {"check": "canonical_qpt_coordinate_policy", "status": "PASS", "detail": prepared.q_source_policy},
        {"check": "dft_qpt_xyz_tsv_consistency", "status": "PASS", "detail": f"max abs difference {prepared.qpt_xyz_max_abs_difference_ang:.6e} Angstrom <= 3e-2"},
        {"check": "non_dft_qpt_metadata", "status": "PASS", "detail": json.dumps(prepared.qpt_series_diagnostics, sort_keys=True)},
        {"check": "locked_pbe_barrier", "status": "PASS", "detail": f"{1000.0 * prepared.barriers_ev['DFT']:.9f} meV"},
        {"check": "common_frozen_geometry_path", "status": "PASS", "detail": "same aligned PBE NEB9 geometry path for all three energy profiles"},
        {"check": "common_endpoint_confinement", "status": "PASS", "detail": "DFT-derived harmonic continuation used for all series"},
        {"check": "primary_formulation", "status": "PASS", "detail": f"{PRIMARY_PROFILE_MODE}/{PRIMARY_INTERPOLATION}/{PRIMARY_MASS_MODEL}"},
        {"check": "grid_convergence", "status": "PASS" if all_converged else "WARN", "detail": f"grids {CONVERGENCE_GRIDS}"},
        {"check": "H_to_D_isotope_direction_PBE", "status": "PASS" if isotope_checks["DFT"] else "WARN", "detail": str(isotope_checks["DFT"])},
        {"check": "H_to_D_isotope_direction_targeted", "status": "PASS" if isotope_checks["targeted"] else "WARN", "detail": str(isotope_checks["targeted"])},
        {"check": "scientific_scope", "status": "PASS", "detail": "1D frozen-path PBE-derived audit; no experimental-rate claim"},
    ]
    write_tsv(run_dir / "reports" / "validation_v039.tsv", validation_rows)

    report_lines = [
        "# Frozen-path 1D tunneling audit v039",
        "",
        f"- Input attempt: `{source.attempt}`",
        "- New DFT calculations: none",
        "- New training: none",
        "- Molecular dynamics: none",
        "- Geometry path: checksum-locked PBE NEB9",
        "- Energy profiles: PBE, basin-focused MTP, transition-focused MTP on the same frozen PBE images",
        f"- Reaction-coordinate policy: {prepared.q_source_policy}",
        f"- DFT XYZ-vs-TSV qPT maximum difference: {prepared.qpt_xyz_max_abs_difference_ang:.6e} Angstrom",
        f"- Basin qPT metadata status: {prepared.qpt_series_diagnostics['basin']['status']}",
        f"- Targeted qPT metadata status: {prepared.qpt_series_diagnostics['targeted']['status']}",
        f"- Primary formulation: {PRIMARY_PROFILE_MODE} profile, {PRIMARY_INTERPOLATION} interpolation, {PRIMARY_MASS_MODEL} mass",
        f"- Final grid: {grid_points} points",
        f"- Harmonic extension fraction: {extension_fraction}",
        f"- Robustness conclusion: **{conclusion}**",
        f"- Targeted closer to PBE: {conclusion_metrics['targeted_better_count']}/{conclusion_metrics['comparison_count']} predeclared comparisons",
        "",
        "## Primary results",
        "",
    ]
    for isotope in ("H", "D"):
        report_lines.append(f"### {isotope}")
        for series in EXPECTED_SERIES:
            row = primary_lookup[(series, isotope)]
            report_lines.append(
                f"- {LABELS[series]}: gap {row.gap_mev:.6f} meV ({row.gap_cm1:.4f} cm^-1); "
                f"classification `{row.classification}`"
            )
        report_lines.append("")
    report_lines.extend([
        "## Interpretation boundary",
        "",
        "The reported quantity is the gap between the two lowest eigenstates of a one-dimensional Hamiltonian constructed from a frozen PBE path. For a symmetric profile with both states below the barrier it can be interpreted as a frozen-path tunneling splitting. If a model does not support a sub-barrier doublet, the code reports a low-level gap and explicitly marks that classification.",
        "",
        "This audit does not include full-dimensional zero-point vibrational corrections, a full reaction-surface kinetic operator, instanton optimization, environmental reorganization, or comparison to an experimental rate.",
    ])
    write_text(run_dir / "reports" / "frozen_path_1d_tunneling_audit_report_v039.md", "\n".join(report_lines) + "\n")

    caption = (
        "**Supplementary Figure S3. Frozen-path one-dimensional quantum audit.** "
        "The checksum-locked PBE NEB9 geometries define a common proton-transfer path, while PBE, "
        "basin-focused MTP, and transition-focused MTP energies define three one-dimensional potentials. "
        "The primary analysis uses a symmetrized PCHIP profile and a coordinate-dependent path-metric mass. "
        "Panel a shows the H potentials and the two lowest levels; panel b compares the corresponding H and D "
        "low-level gaps. The result is a PBE-derived frozen-path audit, not an experimental tunneling-rate "
        "prediction or a full-dimensional quantum-dynamics calculation.\n"
    )
    write_text(run_dir / "reports" / "supplementary_figure_s3_caption_v039.md", caption)

    limitations = """# Limitations of the frozen-path 1D audit

1. The potential is based on only nine frozen PBE NEB images.
2. The endpoint wells are continued with a common PBE-derived harmonic confinement.
3. The primary potential is symmetrized to isolate barrier-shape fidelity from small endpoint asymmetry.
4. The path-metric mass is derived from the aligned frozen PBE geometries and is not a full reaction-surface kinetic operator.
5. No orthogonal-mode ZPVE correction is included.
6. No instanton, path-integral, ring-polymer, or full-dimensional wavepacket calculation is performed.
7. The result is relative to the PBE reference and is not an experimental prediction.
8. A low-level gap is called a tunneling splitting only when both lowest levels lie below the barrier and the profile is symmetric or nearly symmetric.
"""
    write_text(run_dir / "reports" / "limitations_v039.md", limitations)

    summary = {
        "stage_id": STAGE_ID,
        "version": VERSION,
        "status": STATUS_PASS,
        "input_attempt": str(source.attempt),
        "source_hashes": source.source_hashes,
        "scientific_execution": "FROZEN_PATH_1D_SCHRODINGER_AUDIT_ONLY",
        "dft_execution": "NONE",
        "training_execution": "NONE",
        "molecular_dynamics_execution": "NONE",
        "primary_formulation": {
            "profile_mode": PRIMARY_PROFILE_MODE,
            "interpolation": PRIMARY_INTERPOLATION,
            "mass_model": PRIMARY_MASS_MODEL,
            "grid_points": grid_points,
            "extension_fraction": extension_fraction,
        },
        "barriers_mev": {series: 1000.0 * prepared.barriers_ev[series] for series in EXPECTED_SERIES},
        "qpt_coordinate_policy": prepared.q_source_policy,
        "qpt_xyz_max_abs_difference_ang": prepared.qpt_xyz_max_abs_difference_ang,
        "qpt_series_diagnostics": prepared.qpt_series_diagnostics,
        "primary_results": [result_to_row(row) for row in primary],
        "robustness_conclusion": conclusion,
        "robustness_metrics": conclusion_metrics,
        "grid_convergence_pass": all_converged,
        "isotope_direction_checks": isotope_checks,
        "figure_paths": [str(path) for path in figure_paths],
    }
    write_json(run_dir / "summary_v039.json", summary)
    write_text(run_dir / "STATUS_v039.txt", STATUS_PASS + "\n")
    checksums = write_checksums(run_dir)

    pointer = root / "10_visualization" / "versions" / VERSION_DIR / POINTER_FILE
    write_text(pointer, str(run_dir) + "\n")

    print(STATUS_PASS)
    print(f"RUN_DIR={run_dir}")
    print(f"PRIMARY_TABLE={run_dir / 'tables' / 'quantum_results_primary_v039.tsv'}")
    print(f"ALL_RESULTS_TABLE={run_dir / 'tables' / 'quantum_results_all_formulations_v039.tsv'}")
    print(f"ROBUSTNESS_TABLE={run_dir / 'tables' / 'robustness_comparisons_v039.tsv'}")
    print(f"CONVERGENCE_TABLE={run_dir / 'tables' / 'grid_convergence_v039.tsv'}")
    print(f"QPT_PROVENANCE_TABLE={run_dir / 'tables' / 'qpt_coordinate_provenance_v039.tsv'}")
    print(f"FIGURE_PNG={figure_paths[0]}")
    print(f"FIGURE_PDF={figure_paths[1]}")
    print(f"REPORT={run_dir / 'reports' / 'frozen_path_1d_tunneling_audit_report_v039.md'}")
    print(f"SUMMARY={run_dir / 'summary_v039.json'}")
    print(f"CHECKSUMS={checksums}")
    print(f"CURRENT_POINTER={pointer}")
    print(f"ROBUSTNESS_CONCLUSION={conclusion}")
    print(f"TARGETED_BETTER={conclusion_metrics['targeted_better_count']}/{conclusion_metrics['comparison_count']}")
    print("DFT_EXECUTION=NONE")
    print("TRAINING_EXECUTION=NONE")
    print("MOLECULAR_DYNAMICS_EXECUTION=NONE")
    return 0


# ---------------------------- synthetic self-test ----------------------------
SYNTHETIC_DFT = np.asarray([0.0, 0.003833404038, 0.016756635594, 0.030538386386, 0.036072093893, 0.030526549434, 0.016756635594, 0.003833404038, 0.0])
SYNTHETIC_Q = np.asarray([-0.4837794558, -0.3879764216, -0.2598589815, -0.1278232809, -0.0001802773, 0.1275092943, 0.2598589815, 0.3879764216, 0.4837794558])


def synthetic_geometry(qpt: float, image: int) -> np.ndarray:
    roo = 2.3925 + 0.1067 * (abs(qpt) / max(abs(SYNTHETIC_Q[0]), abs(SYNTHETIC_Q[-1]))) ** 1.6
    left_o = np.asarray([-roo / 2.0, -0.72, 0.0])
    right_o = np.asarray([roo / 2.0, -0.72, 0.0])
    # Solve approximately for H x such that d_left - d_right = qpt on the O-O line.
    hx = 0.5 * qpt
    transfer_h = np.asarray([hx, -1.00, 0.0])
    coords = np.asarray([
        left_o,
        transfer_h,
        [-0.95, 0.10, 0.0],
        [-1.55, 0.45, 0.0],
        [0.00, 0.65 + 0.015 * math.cos(image), 0.0],
        [0.00, 1.35, 0.0],
        [0.95, 0.10, 0.0],
        right_o,
        [1.55, 0.45, 0.0],
    ], dtype=float)
    # Numerically adjust transfer H x to exact qPT.
    for _ in range(30):
        current = qpt_from_xyz(coords)
        derivative = (
            qpt_from_xyz(coords + np.eye(9, 3, k=0) * 0.0) if False else None
        )
        eps = 1e-6
        trial = coords.copy()
        trial[TRANSFER_H_INDEX, 0] += eps
        dqdx = (qpt_from_xyz(trial) - current) / eps
        coords[TRANSFER_H_INDEX, 0] += (qpt - current) / dqdx
    return coords


def make_synthetic_fixture(root: Path) -> Path:
    attempt = root / INPUT_VERSION_ROOT / "attempt_20990101T000000Z"
    ensure_dir(attempt / "source_data")
    ensure_dir(attempt / "geometry")
    base_energy = -1949.728489481261
    # Real-source-like frozen PBE-path profiles. The basin model is not a
    # conventional central barrier: its maximum occurs near image 2/8 and the
    # central image is below the endpoints. This deliberately exercises the
    # solver's non-double-well classification instead of hiding the pathology.
    profiles = {
        "DFT": np.asarray([
            0.000107348919073047, 0.003927011206087627, 0.01680616031694626,
            0.03053838638606976, 0.036072093892926205, 0.030526549433034234,
            0.01675663559399254, 0.0038334040380050283, 0.0,
        ]),
        "basin": np.asarray([
            4.802859621122479e-07, 0.0008263598228950286, 0.00014334236789181887,
            -0.0022549399491254007, -0.003500733987038984, -0.0022601370021675393,
            0.00013808102494294872, 0.0008249874870216445, 0.0,
        ]),
        "targeted": np.asarray([
            9.319589935330441e-07, 0.0036146989280041453, 0.016183980101004636,
            0.02777313018100358, 0.031971700288977445, 0.0277976119300547,
            0.01621172533805293, 0.0036227735340617073, 0.0,
        ]),
    }
    rows: list[dict[str, Any]] = []
    for series in EXPECTED_SERIES:
        for image, (q, delta) in enumerate(zip(SYNTHETIC_Q, profiles[series]), start=1):
            rows.append({
                "series": series,
                "image": image,
                "qpt_ang": q,
                "roo_ang": "",
                "energy_ev": base_energy + float(delta),
                "delta_e_from_lower_endpoint_ev": float(delta),
                "delta_e_from_lower_endpoint_mev": 1000.0 * float(delta),
                "profile_error_ev": float(delta - profiles["DFT"][image - 1]),
                "profile_error_mev": 1000.0 * float(delta - profiles["DFT"][image - 1]),
                "is_transition_region": abs(q) <= 0.15,
            })
    write_tsv(attempt / PROFILE_REL, rows)

    barrier_rows = []
    dft_barrier = float(np.max(profiles["DFT"]) - min(profiles["DFT"][0], profiles["DFT"][-1]))
    for series in EXPECTED_SERIES:
        values = profiles[series]
        barrier = float(np.max(values) - min(values[0], values[-1]))
        maximum_image = int(np.argmax(values)) + 1
        barrier_rows.append({
            "series": series,
            "lower_endpoint_barrier_ev": barrier,
            "lower_endpoint_barrier_mev": 1000.0 * barrier,
            "absolute_error_ev": 0.0 if series == "DFT" else abs(barrier - dft_barrier),
            "absolute_error_mev": 0.0 if series == "DFT" else 1000.0 * abs(barrier - dft_barrier),
            "maximum_image": maximum_image,
            "maximum_qpt_ang": SYNTHETIC_Q[maximum_image - 1],
            "lower_endpoint_image": 1 if values[0] <= values[-1] else 9,
        })
    write_tsv(attempt / BARRIER_SUMMARY_REL, barrier_rows)
    primary_rows = [
        {
            "metric": "lower_endpoint_barrier_abs_error_mev",
            "definition": "abs[(max E - min(endpoint E))_model - (max E - min(endpoint E))_DFT]",
            "unit": "meV",
            "basin": 1000.0 * abs((np.max(profiles["basin"]) - min(profiles["basin"][0], profiles["basin"][-1])) - dft_barrier),
            "targeted": 1000.0 * abs((np.max(profiles["targeted"]) - min(profiles["targeted"][0], profiles["targeted"][-1])) - dft_barrier),
            "targeted_minus_basin": "",
            "basin_over_targeted": "",
            "targeted_better": True,
            "authoritative_source": "synthetic frozen-path fixture",
        }
    ]
    write_tsv(attempt / PRIMARY_METRIC_REL, primary_rows)

    xyz_lines: list[str] = []
    for image, q in enumerate(SYNTHETIC_Q, start=1):
        coords = synthetic_geometry(float(q), image)
        xyz_lines.append(str(len(EXPECTED_ATOMS)))
        xyz_lines.append(f"synthetic image {image}")
        for element, xyz in zip(EXPECTED_ATOMS, coords):
            xyz_lines.append(f"{element} {xyz[0]:.16f} {xyz[1]:.16f} {xyz[2]:.16f}")
    write_text(attempt / XYZ_REL, "\n".join(xyz_lines) + "\n")
    write_text(attempt / INPUT_STATUS_FILE, EXPECTED_INPUT_STATUS + "\n")

    checksum_rows = []
    for relative in (PROFILE_REL, BARRIER_SUMMARY_REL, PRIMARY_METRIC_REL, XYZ_REL):
        path = attempt / relative
        checksum_rows.append({
            "relative_path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    write_tsv(attempt / CHECKSUM_REL, checksum_rows, ["relative_path", "size_bytes", "sha256"])
    version_root = root / INPUT_VERSION_ROOT
    write_text(version_root / INPUT_POINTER, str(attempt) + "\n")
    return attempt


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="stage62_tunneling_selftest_") as temporary:
        root = Path(temporary) / "project"
        make_synthetic_fixture(root)
        source = load_locked_source(root)
        prepared = prepare_input(source)
        if prepared.qpt_series_diagnostics["basin"]["status"] != "IDENTICAL_FROZEN_DFT_PATH":
            raise AuditError(f"SELF_TEST unexpected basin qPT status: {prepared.qpt_series_diagnostics['basin']}")
        if prepared.qpt_series_diagnostics["targeted"]["status"] != "IDENTICAL_FROZEN_DFT_PATH":
            raise AuditError(f"SELF_TEST unexpected targeted qPT status: {prepared.qpt_series_diagnostics['targeted']}")
        if not np.allclose(prepared.q_ang, SYNTHETIC_Q, atol=0.0, rtol=0.0):
            raise AuditError("SELF_TEST canonical qPT coordinate changed")
        execute(root, grid_points=801, extension_fraction=DEFAULT_EXTENSION_FRACTION, validate_only=True)
        execute(root, grid_points=801, extension_fraction=DEFAULT_EXTENSION_FRACTION, validate_only=False)
        pointer = root / "10_visualization" / "versions" / VERSION_DIR / POINTER_FILE
        run_dir = Path(read_text(pointer).strip())
        required = [
            run_dir / "STATUS_v039.txt",
            run_dir / "summary_v039.json",
            run_dir / "tables" / "quantum_results_primary_v039.tsv",
            run_dir / "tables" / "quantum_results_all_formulations_v039.tsv",
            run_dir / "tables" / "robustness_comparisons_v039.tsv",
            run_dir / "tables" / "qpt_coordinate_provenance_v039.tsv",
            run_dir / "figures" / "supplementary_figure_s3_frozen_path_tunneling_audit_v039.png",
            run_dir / "figures" / "supplementary_figure_s3_frozen_path_tunneling_audit_v039.pdf",
        ]
        for path in required:
            if not path.is_file() or path.stat().st_size == 0:
                raise AuditError(f"SELF_TEST missing output: {path}")
        summary = json.loads(read_text(run_dir / "summary_v039.json"))
        if not summary["robustness_metrics"]["primary_H_targeted_better"]:
            raise AuditError("SELF_TEST expected targeted to beat basin for primary H")
        if not summary["robustness_metrics"]["primary_D_targeted_better"]:
            raise AuditError("SELF_TEST expected targeted to beat basin for primary D")
        print("SELF_TEST=PASS")
        print("LOCKED_SOURCE_VALIDATION=PASS")
        print("FROZEN_PATH_SOURCE_IDENTITY=PASS")
        print("VARIABLE_MASS_SOLVER=PASS")
        print("H_D_ISOTOPE_AUDIT=PASS")
        print("ROBUSTNESS_MATRIX=PASS")
        print("FIGURE_RENDER=PASS")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("${PROJECT_ROOT}"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--grid-points", type=int, default=DEFAULT_GRID)
    parser.add_argument("--extension-fraction", type=float, default=DEFAULT_EXTENSION_FRACTION)
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (0.15 <= args.extension_fraction <= 0.75):
        raise AuditError("extension-fraction must lie between 0.15 and 0.75")
    return execute(args.root.resolve(), args.grid_points, args.extension_fraction, args.validate_only)


if __name__ == "__main__":
    raise SystemExit(main())
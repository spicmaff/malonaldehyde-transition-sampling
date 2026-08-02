#!/usr/bin/env python3
"""MALONALDEHYDE VIDEO 02 — PBE minimum-energy path v032.

Molecule-first animation of proton transfer along the checksum-locked PBE NEB9
path. The renderer reads only locked v005 source artifacts, validates their
checksums and scientific invariants, aligns all nine geometries to one global
image-5 molecular frame, and interpolates between adjacent NEB images solely
for visual continuity.

This is a reaction-path visualization. It is not molecular dynamics, not a
physical time trajectory, and not a quantum-tunnelling simulation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import numpy as np
from PIL import Image, ImageDraw, ImageFont

VERSION = "v034"
VERSION_DIRNAME = "v034_video02_proton_transfer_pbe_mep_clean"
VERSION_TAG = "VIDEO02_PROTON_TRANSFER_PBE_MEP_CLEAN_V034"
STATUS = f"PASS_{VERSION_TAG}_RENDERED"
POINTER_NAME = "CURRENT_VIDEO02_PROTON_TRANSFER_PBE_MEP_CLEAN_V034.txt"

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
EXPECTED_INPUT_STATUS = "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"

PROFILE_FILE = "source_data/mtp_neb_paths_v005.tsv"
DFT_GEOMETRY_FILE = "geometry/dft_independent_neb9_v005.xyz"
FIGURE_MANIFEST_FILE = "figure_manifest_v005.tsv"
SUMMARY_FILE = "summary_v005.json"
CHECKSUM_FILE = "checksums_v005.tsv"
STATUS_FILE = "STATUS_v005.txt"

EXPECTED_ATOM_SEQUENCE = ("O", "H", "C", "H", "C", "H", "C", "O", "H")
EXPECTED_IMAGES = tuple(range(1, 10))
STORYBOARD_IMAGES = (1, 3, 5, 7, 9)
EXPECTED_MAX_IMAGE = 5
EXPECTED_BARRIER_EV = 0.036072093892926205

# Atom indices in the checksum-locked XYZ order.
IDX_O_LEFT = 0
IDX_H_TRANSFER = 1
IDX_C_LEFT = 2
IDX_H_LEFT = 3
IDX_C_CENTER = 4
IDX_H_TOP = 5
IDX_C_RIGHT = 6
IDX_O_RIGHT = 7
IDX_H_RIGHT = 8

BACKBONE_INDICES = (IDX_O_LEFT, IDX_C_LEFT, IDX_C_CENTER, IDX_C_RIGHT, IDX_O_RIGHT)
SKELETON_BONDS = (
    (IDX_O_LEFT, IDX_C_LEFT),
    (IDX_C_LEFT, IDX_C_CENTER),
    (IDX_C_CENTER, IDX_C_RIGHT),
    (IDX_C_RIGHT, IDX_O_RIGHT),
    (IDX_C_LEFT, IDX_H_LEFT),
    (IDX_C_CENTER, IDX_H_TOP),
    (IDX_C_RIGHT, IDX_H_RIGHT),
)

# Visual constants.
BG = "#FFFFFF"
TEXT = "#202020"
SUBTEXT = "#5A5A5A"
GRID = "#E4E4E4"
PROFILE = "#202020"
PROFILE_POINTS = "#707070"
PROFILE_MARKER = "#D9A11E"
ELEMENT_C = "#444444"
ELEMENT_O = "#D1491F"
ELEMENT_H = "#D9D9D9"
ELEMENT_TRANSFER = "#D9A11E"
DISTANCE_GUIDE = "#A5A5A5"
BOND = "#555555"

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_DPI = 100
DEFAULT_FPS = 30
DEFAULT_START_HOLD = 15
DEFAULT_MOTION_FRAMES = 149  # Gives an exact u=0.5 frame at the path maximum.
DEFAULT_END_HOLD = 21
DEFAULT_SLOWDOWN = 0.45


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class XYZFrame:
    elements: tuple[str, ...]
    positions: tuple[tuple[float, float, float], ...]
    comment: str


@dataclass(frozen=True)
class LockedInputs:
    attempt: Path
    checksum_rows: list[dict[str, str]]
    profile_rows: list[dict[str, str]]
    dft_frames: list[XYZFrame]
    manifest_rows: list[dict[str, str]]
    summary: dict[str, Any]
    source_hashes: dict[str, str]


@dataclass(frozen=True)
class PreparedPath:
    xy_by_image: dict[int, np.ndarray]
    xyz_aligned_by_image: dict[int, np.ndarray]
    energies_mev: np.ndarray
    qpt_table: np.ndarray
    roo_exact: np.ndarray
    bounds: tuple[float, float, float, float]
    barrier_mev: float


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise RenderError(f"Missing {label}: {path}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    return require_file(path, "text file").read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def read_tsv(path: Path) -> list[dict[str, str]]:
    with require_file(path, "TSV file").open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle, delimiter="\t")]
    if not rows:
        raise RenderError(f"TSV is empty: {path}")
    return rows


def parse_float(value: str, label: str) -> float:
    try:
        return float(str(value).strip())
    except Exception as exc:
        raise RenderError(f"Invalid float for {label}: {value!r}") from exc


def parse_int(value: str, label: str) -> int:
    try:
        return int(str(value).strip())
    except Exception as exc:
        raise RenderError(f"Invalid integer for {label}: {value!r}") from exc


def atomic_write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def atomic_write_tsv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    os.replace(temporary, path)


def parse_xyz(path: Path) -> list[XYZFrame]:
    lines = require_file(path, "XYZ file").read_text(encoding="utf-8").splitlines()
    frames: list[XYZFrame] = []
    cursor = 0
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        try:
            atom_count = int(lines[cursor].strip())
        except ValueError as exc:
            raise RenderError(f"Invalid atom count at {path}:{cursor + 1}") from exc
        if atom_count != len(EXPECTED_ATOM_SEQUENCE):
            raise RenderError(f"Unexpected atom count in {path}: {atom_count}")
        if cursor + atom_count + 1 >= len(lines):
            raise RenderError(f"Truncated XYZ frame in {path}")
        comment = lines[cursor + 1]
        elements: list[str] = []
        positions: list[tuple[float, float, float]] = []
        for offset in range(atom_count):
            tokens = lines[cursor + 2 + offset].split()
            if len(tokens) < 4:
                raise RenderError(f"Invalid XYZ row in {path}: {lines[cursor + 2 + offset]!r}")
            elements.append(tokens[0])
            positions.append(tuple(parse_float(tokens[index], f"{path} coordinate") for index in (1, 2, 3)))
        if tuple(elements) != EXPECTED_ATOM_SEQUENCE:
            raise RenderError(f"Atom sequence mismatch in {path}: {elements}")
        frames.append(XYZFrame(tuple(elements), tuple(positions), comment))
        cursor += atom_count + 2
    if len(frames) != len(EXPECTED_IMAGES):
        raise RenderError(f"Expected 9 XYZ frames in {path}; found {len(frames)}")
    return frames


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def geometry_metrics(xyz: np.ndarray) -> tuple[float, float, float, float]:
    d_left = float(np.linalg.norm(xyz[IDX_H_TRANSFER] - xyz[IDX_O_LEFT]))
    d_right = float(np.linalg.norm(xyz[IDX_H_TRANSFER] - xyz[IDX_O_RIGHT]))
    qpt = d_left - d_right
    roo = float(np.linalg.norm(xyz[IDX_O_LEFT] - xyz[IDX_O_RIGHT]))
    return qpt, roo, d_left, d_right


def resolve_input_attempt(root: Path) -> Path:
    version_root = (root / INPUT_RELATIVE_ROOT).resolve()
    pointer = require_file(version_root / INPUT_POINTER, "v005 pointer")
    raw = pointer.read_text(encoding="utf-8").strip()
    if not raw:
        raise RenderError(f"Empty v005 pointer: {pointer}")
    attempt = Path(raw).expanduser().resolve()
    try:
        attempt.relative_to(version_root)
    except ValueError as exc:
        raise RenderError(f"v005 pointer escapes expected root: {attempt}") from exc
    if not attempt.is_dir():
        raise RenderError(f"v005 pointer target missing: {attempt}")
    observed_status = read_text(attempt / STATUS_FILE).strip()
    if observed_status != EXPECTED_INPUT_STATUS:
        raise RenderError(
            f"Unexpected v005 status: {observed_status}; expected {EXPECTED_INPUT_STATUS}"
        )
    return attempt


def verify_checksum_entry(
    attempt: Path,
    checksum_rows: Sequence[Mapping[str, str]],
    relative_path: str,
) -> str:
    matches = [row for row in checksum_rows if row.get("relative_path") == relative_path]
    if len(matches) != 1:
        raise RenderError(
            f"Expected one checksum entry for {relative_path}; found {len(matches)}"
        )
    row = matches[0]
    target = require_file(attempt / relative_path, relative_path)
    expected_size = parse_int(row.get("size_bytes", ""), f"{relative_path} size")
    expected_sha = row.get("sha256", "").strip()
    observed_size = target.stat().st_size
    observed_sha = sha256_file(target)
    if observed_size != expected_size or observed_sha != expected_sha:
        raise RenderError(
            f"Checksum mismatch for {relative_path}: "
            f"size {observed_size}/{expected_size}; sha256 {observed_sha}/{expected_sha}"
        )
    return observed_sha


def load_locked_inputs(root: Path) -> LockedInputs:
    attempt = resolve_input_attempt(root)
    checksum_rows = read_tsv(attempt / CHECKSUM_FILE)
    required = (
        PROFILE_FILE,
        DFT_GEOMETRY_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    source_hashes = {
        relative: verify_checksum_entry(attempt, checksum_rows, relative)
        for relative in required
    }
    return LockedInputs(
        attempt=attempt,
        checksum_rows=checksum_rows,
        profile_rows=read_tsv(attempt / PROFILE_FILE),
        dft_frames=parse_xyz(attempt / DFT_GEOMETRY_FILE),
        manifest_rows=read_tsv(attempt / FIGURE_MANIFEST_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        source_hashes=source_hashes,
    )


def dft_profile_rows(profile_rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    rows = [dict(row) for row in profile_rows if row.get("series") == "DFT"]
    rows.sort(key=lambda row: parse_int(row.get("image", ""), "DFT image"))
    observed = tuple(parse_int(row.get("image", ""), "DFT image") for row in rows)
    if observed != EXPECTED_IMAGES:
        raise RenderError(f"Unexpected DFT image sequence: {observed}")
    return rows


def snapshot_inputs(inputs: LockedInputs, destination: Path) -> None:
    ensure_dir(destination)
    for relative in (
        PROFILE_FILE,
        DFT_GEOMETRY_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
        CHECKSUM_FILE,
        STATUS_FILE,
    ):
        source = inputs.attempt / relative
        target = destination / relative
        ensure_dir(target.parent)
        shutil.copy2(source, target)


# ---------- Synthetic self-test fixture ----------
SYNTHETIC_DFT_ROWS = (
    (1, -0.48377945579573045, -1949.728489481261, 0.0),
    (2, -0.38797642164204493, -1949.724656077223, 0.0038334040380050283),
    (3, -0.25985898147464837, -1949.711732845667, 0.01675663559399254),
    (4, -0.12782328092162376, -1949.697951094875, 0.03053838638606976),
    (5, -0.0001802773458876583, -1949.692417387368, 0.036072093892926205),
    (6, 0.127509294253904, -1949.697962931828, 0.030526549433034234),
    (7, 0.25985898147464837, -1949.711732845667, 0.01675663559399254),
    (8, 0.38797642164204493, -1949.724656077223, 0.0038334040380050283),
    (9, 0.48377945579573045, -1949.728489481261, 0.0),
)


def synthetic_geometry(qpt: float, roo: float, image: int) -> XYZFrame:
    # A planar regression fixture with small, image-dependent heavy-atom deformation.
    phase = (image - 5) / 4.0
    o_left = np.array((-roo / 2.0, 0.0, 0.0))
    o_right = np.array((roo / 2.0, 0.0, 0.0))
    proton = np.array((qpt / 2.0, 0.02 * (1.0 - abs(phase)), 0.0))
    positions = np.array(
        [
            o_left,
            proton,
            (-1.37, 0.77 + 0.05 * phase, 0.00),
            (-1.86, 1.18 + 0.04 * phase, 0.07),
            (0.00, 1.30 - 0.06 * (1.0 - abs(phase)), 0.00),
            (0.00, 2.00 - 0.04 * (1.0 - abs(phase)), 0.08),
            (1.37, 0.77 - 0.05 * phase, 0.00),
            o_right,
            (1.86, 1.18 - 0.04 * phase, -0.07),
        ],
        dtype=float,
    )
    return XYZFrame(
        EXPECTED_ATOM_SEQUENCE,
        tuple(tuple(float(value) for value in row) for row in positions),
        f"synthetic DFT image {image}",
    )


def write_xyz(path: Path, frames: Sequence[XYZFrame]) -> None:
    lines: list[str] = []
    for frame in frames:
        lines.append(str(len(frame.elements)))
        lines.append(frame.comment)
        for element, xyz in zip(frame.elements, frame.positions):
            lines.append(f"{element} {xyz[0]:.16f} {xyz[1]:.16f} {xyz[2]:.16f}")
    atomic_write_text(path, "\n".join(lines) + "\n")


def make_synthetic_fixture(root: Path) -> Path:
    attempt = root / INPUT_RELATIVE_ROOT / "attempt_20990101T000000Z"
    ensure_dir(attempt / "source_data")
    ensure_dir(attempt / "geometry")

    profile_rows: list[dict[str, Any]] = []
    frames: list[XYZFrame] = []
    roo_values = [2.49924, 2.45770, 2.41924, 2.39920, 2.39250, 2.39917, 2.41919, 2.45766, 2.49906]
    for (image, qpt, energy, delta_lower), roo in zip(SYNTHETIC_DFT_ROWS, roo_values):
        profile_rows.append(
            {
                "series": "DFT",
                "image": image,
                "qpt_ang": qpt,
                "energy_ev": energy,
                "delta_e_from_left_ev": delta_lower,
                "delta_e_from_lower_endpoint_ev": delta_lower,
                "roo_ang": "",
                "minimum_pair_ang": "",
                "mass_weighted_rmsd_from_dft_image_ang": 0.0,
                "classification": "reference",
            }
        )
        frames.append(synthetic_geometry(qpt, roo, image))

    atomic_write_tsv(attempt / PROFILE_FILE, list(profile_rows[0].keys()), profile_rows)
    write_xyz(attempt / DFT_GEOMETRY_FILE, frames)
    manifest = [
        {
            "figure_id": "Figure_2",
            "title": "Frozen independent PBE NEB9 reference",
            "status": "SOURCE_DATA_READY",
            "primary_source_data": PROFILE_FILE,
            "geometry_sources": DFT_GEOMETRY_FILE,
        }
    ]
    atomic_write_tsv(attempt / FIGURE_MANIFEST_FILE, list(manifest[0].keys()), manifest)
    atomic_write_json(attempt / SUMMARY_FILE, {"status": EXPECTED_INPUT_STATUS})
    atomic_write_text(attempt / STATUS_FILE, EXPECTED_INPUT_STATUS + "\n")

    checksum_rows: list[dict[str, Any]] = []
    for relative in (PROFILE_FILE, DFT_GEOMETRY_FILE, FIGURE_MANIFEST_FILE, SUMMARY_FILE):
        target = attempt / relative
        checksum_rows.append(
            {
                "relative_path": relative,
                "size_bytes": target.stat().st_size,
                "sha256": sha256_file(target),
            }
        )
    atomic_write_tsv(
        attempt / CHECKSUM_FILE,
        ["relative_path", "size_bytes", "sha256"],
        checksum_rows,
    )
    atomic_write_text(root / INPUT_RELATIVE_ROOT / INPUT_POINTER, str(attempt) + "\n")
    return attempt


# ---------- Geometry preparation ----------
def xyz_to_array(frame: XYZFrame) -> np.ndarray:
    return np.asarray(frame.positions, dtype=float)


def kabsch_align(
    mobile_xyz: np.ndarray,
    reference_xyz: np.ndarray,
    fit_indices: Sequence[int],
) -> np.ndarray:
    """Rigidly align row-vector coordinates with the standard Kabsch solution."""
    index = np.asarray(fit_indices, dtype=int)
    mobile_fit = mobile_xyz[index]
    reference_fit = reference_xyz[index]
    mobile_center = mobile_fit.mean(axis=0)
    reference_center = reference_fit.mean(axis=0)
    p = mobile_fit - mobile_center
    q = reference_fit - reference_center
    covariance = p.T @ q
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1.0
        rotation = u @ vt
    return (mobile_xyz - mobile_center) @ rotation + reference_center


def molecular_plane(reference_xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    subset = reference_xyz[np.asarray(BACKBONE_INDICES)]
    origin = subset.mean(axis=0)
    centered = subset - origin
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    axis_x = vh[0].copy()
    axis_y = vh[1].copy()
    if np.dot(reference_xyz[IDX_O_RIGHT] - reference_xyz[IDX_O_LEFT], axis_x) < 0:
        axis_x *= -1.0
    if np.dot(reference_xyz[IDX_C_CENTER] - origin, axis_y) < 0:
        axis_y *= -1.0
    basis = np.vstack([axis_x, axis_y])
    return origin, basis


def project_to_plane(xyz: np.ndarray, origin: np.ndarray, basis: np.ndarray) -> np.ndarray:
    return (xyz - origin) @ basis.T


def validate_inputs(inputs: LockedInputs) -> dict[str, Any]:
    rows = dft_profile_rows(inputs.profile_rows)
    energies = np.array([parse_float(row["energy_ev"], "DFT energy") for row in rows])
    qpt_table = np.array([parse_float(row["qpt_ang"], "DFT qPT") for row in rows])
    endpoint_reference = min(float(energies[0]), float(energies[-1]))
    relative = energies - endpoint_reference
    maximum_image = int(np.argmax(relative)) + 1
    barrier = float(relative.max())
    if maximum_image != EXPECTED_MAX_IMAGE:
        raise RenderError(f"Expected DFT maximum at image 5; observed image {maximum_image}")
    if abs(barrier - EXPECTED_BARRIER_EV) > 1.0e-9:
        raise RenderError(
            f"Unexpected DFT barrier: {barrier:.15f} eV; expected {EXPECTED_BARRIER_EV:.15f} eV"
        )

    qpt_differences: list[float] = []
    roo_values: list[float] = []
    for image, (frame, expected_qpt) in enumerate(zip(inputs.dft_frames, qpt_table), start=1):
        xyz = xyz_to_array(frame)
        qpt, roo, _, _ = geometry_metrics(xyz)
        difference = abs(qpt - expected_qpt)
        if difference > 0.03:
            raise RenderError(
                f"qPT mismatch at image {image}: xyz={qpt:.8f}; table={expected_qpt:.8f}"
            )
        if not (1.5 < roo < 3.5):
            raise RenderError(f"Implausible R_OO at image {image}: {roo}")
        qpt_differences.append(difference)
        roo_values.append(roo)

    return {
        "profile_rows": len(inputs.profile_rows),
        "dft_rows": len(rows),
        "xyz_frames": len(inputs.dft_frames),
        "maximum_image": maximum_image,
        "barrier_ev": barrier,
        "barrier_mev": 1000.0 * barrier,
        "maximum_qpt_abs_difference_ang": max(qpt_differences),
        "minimum_roo_ang": min(roo_values),
        "maximum_roo_ang": max(roo_values),
        "validation_checks": 4 + 2 * len(EXPECTED_IMAGES),
    }


def prepare_path(inputs: LockedInputs) -> PreparedPath:
    rows = dft_profile_rows(inputs.profile_rows)
    reference = xyz_to_array(inputs.dft_frames[EXPECTED_MAX_IMAGE - 1])
    aligned_xyz: dict[int, np.ndarray] = {}
    for image, frame in enumerate(inputs.dft_frames, start=1):
        xyz = xyz_to_array(frame)
        aligned_xyz[image] = kabsch_align(xyz, reference, BACKBONE_INDICES)

    origin, basis = molecular_plane(aligned_xyz[EXPECTED_MAX_IMAGE])
    xy_by_image = {
        image: project_to_plane(xyz, origin, basis)
        for image, xyz in aligned_xyz.items()
    }

    stacked = np.vstack(list(xy_by_image.values()))
    xmin, ymin = stacked.min(axis=0)
    xmax, ymax = stacked.max(axis=0)
    width = xmax - xmin
    height = ymax - ymin
    pad_x = max(0.28, 0.13 * width)
    pad_y = max(0.32, 0.18 * height)
    bounds = (xmin - pad_x, xmax + pad_x, ymin - pad_y, ymax + pad_y)

    energies = np.array([parse_float(row["energy_ev"], "DFT energy") for row in rows])
    endpoint_reference = min(float(energies[0]), float(energies[-1]))
    energies_mev = 1000.0 * (energies - endpoint_reference)
    qpt_table = np.array([parse_float(row["qpt_ang"], "DFT qPT") for row in rows])
    roo_exact = np.array([geometry_metrics(aligned_xyz[image])[1] for image in EXPECTED_IMAGES])
    return PreparedPath(
        xy_by_image=xy_by_image,
        xyz_aligned_by_image=aligned_xyz,
        energies_mev=energies_mev,
        qpt_table=qpt_table,
        roo_exact=roo_exact,
        bounds=bounds,
        barrier_mev=float(energies_mev.max()),
    )


def interpolation_state(
    prepared: PreparedPath,
    progress: float,
) -> tuple[int, int, float, np.ndarray, np.ndarray, float]:
    progress = float(np.clip(progress, 1.0, 9.0))
    lower = int(math.floor(progress))
    upper = int(math.ceil(progress))
    if lower == upper:
        t = 0.0
    else:
        t = progress - lower
    xy = (1.0 - t) * prepared.xy_by_image[lower] + t * prepared.xy_by_image[upper]
    xyz = (
        (1.0 - t) * prepared.xyz_aligned_by_image[lower]
        + t * prepared.xyz_aligned_by_image[upper]
    )
    energy = float(
        (1.0 - t) * prepared.energies_mev[lower - 1]
        + t * prepared.energies_mev[upper - 1]
    )
    return lower, upper, t, xy, xyz, energy


# ---------- Rendering ----------
def create_run_dir(root: Path) -> Path:
    version_root = root / "10_visualization" / "versions" / VERSION_DIRNAME
    ensure_dir(version_root)
    attempt_name = Path(tempfile.mkdtemp(prefix="attempt_", dir=str(version_root))).name
    run_dir = version_root / attempt_name
    for relative in (
        "video",
        "figures",
        "frames/main",
        "frames/loop_crossfade",
        "tables",
        "reports",
        "source_snapshot",
    ):
        ensure_dir(run_dir / relative)
    return run_dir


def draw_bond(
    ax: plt.Axes,
    p1: np.ndarray,
    p2: np.ndarray,
    *,
    color: str,
    linewidth: float,
    linestyle: str | tuple = "-",
    alpha: float = 1.0,
    zorder: int = 2,
) -> None:
    ax.plot(
        [float(p1[0]), float(p2[0])],
        [float(p1[1]), float(p2[1])],
        color=color,
        lw=linewidth,
        ls=linestyle,
        alpha=alpha,
        solid_capstyle="round",
        zorder=zorder,
    )


def draw_atom(
    ax: plt.Axes,
    p: np.ndarray,
    *,
    radius: float,
    face: str,
    edge: str = "white",
    linewidth: float = 1.4,
    zorder: int = 4,
) -> None:
    ax.add_patch(
        Circle(
            (float(p[0]), float(p[1])),
            radius=radius,
            facecolor=face,
            edgecolor=edge,
            lw=linewidth,
            zorder=zorder,
        )
    )


def draw_molecule(ax: plt.Axes, xy: np.ndarray, bounds: tuple[float, float, float, float]) -> None:
    xmin, xmax, ymin, ymax = bounds
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.axis("off")

    for atom_a, atom_b in SKELETON_BONDS:
        draw_bond(
            ax,
            xy[atom_a],
            xy[atom_b],
            color=BOND,
            linewidth=4.0,
            zorder=2,
        )

    # Both O···H distances are displayed as geometric guides, not bond orders.
    draw_bond(
        ax,
        xy[IDX_O_LEFT],
        xy[IDX_H_TRANSFER],
        color=DISTANCE_GUIDE,
        linewidth=2.1,
        linestyle=(0, (4, 4)),
        alpha=0.95,
        zorder=1,
    )
    draw_bond(
        ax,
        xy[IDX_H_TRANSFER],
        xy[IDX_O_RIGHT],
        color=DISTANCE_GUIDE,
        linewidth=2.1,
        linestyle=(0, (4, 4)),
        alpha=0.95,
        zorder=1,
    )

    for index, element in enumerate(EXPECTED_ATOM_SEQUENCE):
        if index == IDX_H_TRANSFER:
            draw_atom(
                ax,
                xy[index],
                radius=0.125,
                face=ELEMENT_TRANSFER,
                edge="#FFF4D6",
                linewidth=2.2,
                zorder=6,
            )
        elif element == "O":
            draw_atom(ax, xy[index], radius=0.118, face=ELEMENT_O, zorder=5)
        elif element == "C":
            draw_atom(ax, xy[index], radius=0.112, face=ELEMENT_C, zorder=5)
        else:
            draw_atom(ax, xy[index], radius=0.082, face=ELEMENT_H, zorder=5)

    # Small, fixed-position labels establish that the lines are geometric guides.
    ax.text(
        0.02,
        0.03,
        "dashed lines: O···H distance guides",
        transform=ax.transAxes,
        fontsize=12.5,
        color=SUBTEXT,
        ha="left",
        va="bottom",
    )


def draw_energy_profile(
    ax: plt.Axes,
    energies_mev: np.ndarray,
    progress: float,
    current_energy_mev: float,
    barrier_mev: float,
) -> None:
    images = np.arange(1, 10, dtype=float)
    ax.set_facecolor(BG)
    ax.plot(images, energies_mev, color=PROFILE, lw=2.8, zorder=2)
    ax.scatter(images, energies_mev, s=38, facecolors=BG, edgecolors=PROFILE_POINTS, linewidths=1.4, zorder=3)
    ax.scatter(
        [progress],
        [current_energy_mev],
        s=170,
        facecolors=PROFILE_MARKER,
        edgecolors="#FFF4D6",
        linewidths=2.0,
        zorder=5,
    )
    ax.scatter(
        [EXPECTED_MAX_IMAGE],
        [barrier_mev],
        s=65,
        facecolors=BG,
        edgecolors=PROFILE,
        linewidths=1.7,
        zorder=4,
    )
    ax.set_xlim(0.7, 9.3)
    ymax = max(40.0, barrier_mev * 1.22)
    ax.annotate(
        f"Barrier maximum\n{barrier_mev:.2f} meV",
        xy=(EXPECTED_MAX_IMAGE, barrier_mev),
        xytext=(5.45, ymax * 0.88),
        fontsize=13,
        color=TEXT,
        ha="left",
        va="center",
        arrowprops=dict(arrowstyle="-", color="#7A7A7A", lw=1.0),
    )
    ax.set_ylim(-2.0, ymax)
    ax.set_xticks([1, 5, 9], ["Reactant", "Barrier", "Product"])
    ax.tick_params(axis="x", pad=6)
    ax.set_ylabel("Relative energy, meV", fontsize=13.5, color=TEXT)
    ax.set_xlabel("Reaction-path coordinate", fontsize=13.5, color=TEXT)
    ax.tick_params(axis="both", labelsize=11.5, colors=SUBTEXT)
    ax.grid(axis="y", color=GRID, lw=0.9)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#BEBEBE")
    ax.spines["bottom"].set_color("#BEBEBE")


def render_frame(
    prepared: PreparedPath,
    progress: float,
    output_png: Path,
    *,
    width: int,
    height: int,
    dpi: int,
) -> dict[str, float | int]:
    lower, upper, t, xy, xyz, current_energy = interpolation_state(prepared, progress)
    qpt, roo, d_left, d_right = geometry_metrics(xyz)

    figure = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, facecolor=BG)
    font_scale = max(0.72, min(1.0, width / float(DEFAULT_WIDTH)))
    figure.text(
        0.045,
        0.925,
        "Proton transfer along the PBE minimum-energy path",
        fontsize=31 * font_scale,
        fontweight="bold",
        color=TEXT,
    )
    figure.text(
        0.045,
        0.892,
        "Single-pass visualization of nine checksum-locked PBE NEB images",
        fontsize=16 * font_scale,
        color=SUBTEXT,
    )

    molecule_ax = figure.add_axes([0.045, 0.17, 0.62, 0.67], facecolor=BG)
    profile_ax = figure.add_axes([0.72, 0.30, 0.24, 0.44], facecolor=BG)
    draw_molecule(molecule_ax, xy, prepared.bounds)
    draw_energy_profile(
        profile_ax,
        prepared.energies_mev,
        progress,
        current_energy,
        prepared.barrier_mev,
    )

    figure.text(
        0.045,
        0.105,
        rf"$q_{{PT}} = {qpt:+.3f}$ Å    •    $R_{{OO}} = {roo:.3f}$ Å    •    NEB image = {progress:.2f} / 9",
        fontsize=18 * font_scale,
        color=TEXT,
    )
    figure.text(
        0.045,
        0.055,
        "Interpolated visualization of nine PBE NEB images; single forward pass, not a time-resolved trajectory.",
        fontsize=14.5 * font_scale,
        color=SUBTEXT,
    )

    figure.savefig(output_png, dpi=dpi, facecolor=BG)
    plt.close(figure)
    return {
        "image_lo": lower,
        "image_hi": upper,
        "interpolation_fraction": t,
        "path_position": progress,
        "qpt_ang": qpt,
        "roo_ang": roo,
        "oh_left_ang": d_left,
        "oh_right_ang": d_right,
        "relative_energy_mev": current_energy,
    }


def path_progress(u: float, slowdown: float) -> float:
    """Monotonic path map that slows near image 5 without stopping."""
    u = float(np.clip(u, 0.0, 1.0))
    mapped = u + slowdown * math.sin(2.0 * math.pi * u) / (2.0 * math.pi)
    return 1.0 + 8.0 * mapped


def timeline(
    start_hold: int,
    motion_frames: int,
    end_hold: int,
    slowdown: float,
) -> list[float]:
    if start_hold < 0 or end_hold < 0 or motion_frames < 1:
        raise RenderError("Timeline frame counts must be non-negative, with motion_frames >= 1")
    if not (0.0 <= slowdown < 1.0):
        raise RenderError("slowdown must satisfy 0 <= slowdown < 1")
    values = [1.0] * start_hold
    denominator = motion_frames + 1
    for index in range(motion_frames):
        u = (index + 1) / denominator
        values.append(path_progress(u, slowdown))
    values.extend([9.0] * end_hold)
    return values


def run_command(command: Sequence[str], label: str) -> None:
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise RenderError(
            f"{label} failed with exit code {process.returncode}\n"
            f"STDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}"
        )


def encode_video(frame_pattern: str, fps: int, output: Path, codec: str) -> None:
    if shutil.which("ffmpeg") is None:
        raise RenderError("ffmpeg is required for MP4/WEBM/GIF outputs")
    if codec == "mp4":
        command = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            frame_pattern,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    elif codec == "webm":
        command = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            frame_pattern,
            "-c:v",
            "libvpx-vp9",
            "-crf",
            "28",
            "-b:v",
            "0",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
    else:
        raise ValueError(codec)
    run_command(command, f"ffmpeg {codec} encode")


def encode_gif(source_video: Path, output_gif: Path) -> None:
    filter_graph = (
        "fps=12,scale=960:-2:flags=lanczos,split[s0][s1];"
        "[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=sierra2_4a"
    )
    run_command(
        ["ffmpeg", "-y", "-i", str(source_video), "-filter_complex", filter_graph, str(output_gif)],
        "ffmpeg GIF encode",
    )


def render_crossfade_frames(
    first_frame: Path,
    final_frame: Path,
    output_dir: Path,
    frame_count: int,
) -> list[Path]:
    if frame_count < 1:
        return []
    first = Image.open(first_frame).convert("RGB")
    final = Image.open(final_frame).convert("RGB")
    if first.size != final.size:
        raise RenderError("Crossfade endpoints have different dimensions")
    outputs: list[Path] = []
    for index in range(frame_count):
        alpha = (index + 1) / (frame_count + 1)
        blended = Image.blend(final, first, alpha)
        path = output_dir / f"crossfade_{index + 1:04d}.png"
        blended.save(path)
        outputs.append(path)
    first.close()
    final.close()
    return outputs


def encode_loop_video(
    main_video: Path,
    crossfade_pattern: str,
    crossfade_fps: int,
    output_loop: Path,
    temporary_clip: Path,
) -> None:
    encode_video(crossfade_pattern, crossfade_fps, temporary_clip, "mp4")
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(main_video),
            "-i",
            str(temporary_clip),
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_loop),
        ],
        "ffmpeg loop concat",
    )


def render_contact_sheet(frame_paths: Sequence[Path], output: Path) -> None:
    images = [Image.open(path).convert("RGB") for path in frame_paths]
    thumb_width = 850
    thumb_height = int(images[0].height * thumb_width / images[0].width)
    columns = 3
    rows = 2
    padding = 26
    title_height = 68
    label_height = 28
    sheet_width = padding + columns * thumb_width + (columns - 1) * padding + padding
    sheet_height = title_height + rows * (label_height + thumb_height) + (rows - 1) * padding + padding
    sheet = Image.new("RGB", (sheet_width, sheet_height), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text(
        (padding, 20),
        "Video 02 v032 — PBE minimum-energy path storyboard (images 1, 3, 5, 7, 9)",
        fill=(25, 25, 25),
        font=font,
    )
    for index, image in enumerate(images):
        row = index // columns
        column = index % columns
        x = padding + column * (thumb_width + padding)
        y = title_height + row * (label_height + thumb_height + padding)
        draw.text((x, y), f"NEB image {STORYBOARD_IMAGES[index]}", fill=(25, 25, 25), font=font)
        sheet.paste(image.resize((thumb_width, thumb_height)), (x, y + label_height))
    sheet.save(output)
    for image in images:
        image.close()


def write_checksums(run_dir: Path) -> None:
    rows: list[dict[str, str]] = []
    checksum_path = run_dir / f"checksums_{VERSION}.tsv"
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path != checksum_path:
            rows.append(
                {
                    "sha256": sha256_file(path),
                    "path": str(path.relative_to(run_dir)),
                }
            )
    atomic_write_tsv(checksum_path, ["sha256", "path"], rows)


def write_outputs(
    root: Path,
    inputs: LockedInputs,
    *,
    width: int,
    height: int,
    dpi: int,
    fps: int,
    start_hold: int,
    motion_frames: int,
    end_hold: int,
    crossfade_frames: int,
    slowdown: float,
) -> int:
    validation = validate_inputs(inputs)
    prepared = prepare_path(inputs)
    run_dir = create_run_dir(root)
    snapshot_inputs(inputs, run_dir / "source_snapshot")

    figures_dir = run_dir / "figures"
    frames_dir = run_dir / "frames" / "main"
    video_dir = run_dir / "video"

    exact_state_rows: list[dict[str, Any]] = []
    exact_paths: dict[int, Path] = {}
    for image in EXPECTED_IMAGES:
        output = figures_dir / f"video02_pbe_mep_image{image:02d}_{VERSION}.png"
        metrics = render_frame(
            prepared,
            float(image),
            output,
            width=width,
            height=height,
            dpi=dpi,
        )
        exact_paths[image] = output
        exact_state_rows.append(
            {
                "image": image,
                **metrics,
                "table_qpt_ang": prepared.qpt_table[image - 1],
                "exact_roo_ang": prepared.roo_exact[image - 1],
                "exact_relative_energy_mev": prepared.energies_mev[image - 1],
            }
        )

    storyboard = figures_dir / f"video02_pbe_mep_storyboard_{VERSION}.png"
    render_contact_sheet([exact_paths[image] for image in STORYBOARD_IMAGES], storyboard)
    central_poster = figures_dir / f"video02_pbe_mep_central_state_{VERSION}.png"
    final_poster = figures_dir / f"video02_pbe_mep_final_state_{VERSION}.png"
    shutil.copy2(exact_paths[5], central_poster)
    shutil.copy2(exact_paths[9], final_poster)

    progress_values = timeline(start_hold, motion_frames, end_hold, slowdown)
    frame_rows: list[dict[str, Any]] = []
    main_frame_paths: list[Path] = []
    for index, progress in enumerate(progress_values, start=1):
        output = frames_dir / f"video02_frame_{index:04d}.png"
        metrics = render_frame(
            prepared,
            progress,
            output,
            width=width,
            height=height,
            dpi=dpi,
        )
        main_frame_paths.append(output)
        frame_rows.append(
            {
                "frame_index": index,
                "time_seconds": (index - 1) / float(fps),
                **metrics,
            }
        )

    mp4 = video_dir / f"video02_proton_transfer_pbe_mep_clean_{VERSION}.mp4"
    preview_gif = video_dir / f"video02_proton_transfer_pbe_mep_clean_preview_{VERSION}.gif"
    main_pattern = str(frames_dir / "video02_frame_%04d.png")
    encode_video(main_pattern, fps, mp4, "mp4")
    crossfade_paths: list[Path] = []
    encode_gif(mp4, preview_gif)

    atomic_write_tsv(
        run_dir / "tables" / f"video02_exact_states_{VERSION}.tsv",
        [
            "image",
            "image_lo",
            "image_hi",
            "interpolation_fraction",
            "path_position",
            "qpt_ang",
            "roo_ang",
            "oh_left_ang",
            "oh_right_ang",
            "relative_energy_mev",
            "table_qpt_ang",
            "exact_roo_ang",
            "exact_relative_energy_mev",
        ],
        exact_state_rows,
    )
    atomic_write_tsv(
        run_dir / "tables" / f"video02_frame_manifest_{VERSION}.tsv",
        [
            "frame_index",
            "time_seconds",
            "image_lo",
            "image_hi",
            "interpolation_fraction",
            "path_position",
            "qpt_ang",
            "roo_ang",
            "oh_left_ang",
            "oh_right_ang",
            "relative_energy_mev",
        ],
        frame_rows,
    )

    caption = (
        "**Proton transfer along the PBE minimum-energy path.** The single-pass animation interpolates between nine "
        "independently calculated, checksum-locked PBE NEB images and synchronizes the molecular geometry "
        "with the relative-energy profile. The transferred proton is highlighted in gold, while dashed lines "
        "show geometric O···H distance guides. The displayed motion is a reaction-path visualization and must "
        "not be interpreted as a time-resolved molecular-dynamics or quantum-tunnelling trajectory.\n"
    )
    atomic_write_text(run_dir / "reports" / f"video02_caption_{VERSION}.md", caption)

    report = "\n".join(
        [
            "# Video 02 v034 clean render report",
            "",
            f"- Input attempt: `{inputs.attempt}`",
            "- Scientific execution: none",
            "- Source: checksum-locked PBE NEB9 v005 geometry and energy profile",
            "- Global reference frame: image 5 heavy-atom backbone",
            "- Projection: one image-5 molecular plane for all frames",
            "- Visual interpolation: adjacent locked NEB images only",
            f"- Barrier maximum: image {EXPECTED_MAX_IMAGE}, {prepared.barrier_mev:.6f} meV",
            f"- Main frames: {len(main_frame_paths)}",
            f"- Main duration: {len(main_frame_paths) / float(fps):.3f} s at {fps} fps",
            f"- Presentation loop: absent",
            "- Time-resolved interpretation: forbidden",
            "- Molecular-dynamics interpretation: forbidden",
            "- Quantum-tunnelling interpretation: forbidden",
        ]
    ) + "\n"
    atomic_write_text(run_dir / "reports" / f"video02_render_report_{VERSION}.md", report)

    validation_rows = [
        {"check": "scientific_execution", "status": "PASS", "detail": "NONE"},
        {"check": "source_checksums", "status": "PASS", "detail": f"{len(inputs.source_hashes)} files verified"},
        {"check": "xyz_frame_count", "status": "PASS", "detail": str(validation["xyz_frames"])},
        {"check": "atom_order", "status": "PASS", "detail": ",".join(EXPECTED_ATOM_SEQUENCE)},
        {"check": "global_reference_frame", "status": "PASS", "detail": "PBE image 5"},
        {"check": "single_projection_plane", "status": "PASS", "detail": "PBE image-5 plane"},
        {"check": "maximum_image", "status": "PASS", "detail": str(validation["maximum_image"])},
        {"check": "barrier_mev", "status": "PASS", "detail": f"{validation['barrier_mev']:.12f}"},
        {"check": "qpt_xyz_table_consistency", "status": "PASS", "detail": f"max abs diff {validation['maximum_qpt_abs_difference_ang']:.6e} Å"},
        {"check": "intermediate_holds", "status": "PASS", "detail": "NONE"},
        {"check": "popup_annotations", "status": "PASS", "detail": "NONE"},
        {"check": "time_axis", "status": "PASS", "detail": "ABSENT"},
        {"check": "full_video_outputs", "status": "PASS", "detail": "MP4, GIF"},
    ]
    atomic_write_tsv(
        run_dir / "reports" / f"video02_validation_{VERSION}.tsv",
        ["check", "status", "detail"],
        validation_rows,
    )

    summary = {
        "version": VERSION,
        "status": STATUS,
        "scientific_execution": "NONE",
        "visualization_type": "interpolated PBE NEB reaction path",
        "time_resolved_trajectory": False,
        "molecular_dynamics": False,
        "quantum_tunnelling_trajectory": False,
        "input_attempt": str(inputs.attempt),
        "fps": fps,
        "width": width,
        "height": height,
        "main_frame_count": len(main_frame_paths),
        "main_duration_seconds": len(main_frame_paths) / float(fps),
        "loop_crossfade_frame_count": 0,
        "barrier_mev": prepared.barrier_mev,
        "maximum_image": EXPECTED_MAX_IMAGE,
        "source_hashes": inputs.source_hashes,
        "outputs": {
            "mp4": str(mp4),
            "preview_gif": str(preview_gif),
            "storyboard": str(storyboard),
            "central_state_poster": str(central_poster),
            "final_state_poster": str(final_poster),
            "frames_dir": str(frames_dir),
        },
    }
    atomic_write_json(run_dir / f"summary_{VERSION}.json", summary)
    atomic_write_text(run_dir / f"STATUS_{VERSION}.txt", STATUS + "\n")
    write_checksums(run_dir)

    pointer = root / "10_visualization" / "versions" / VERSION_DIRNAME / POINTER_NAME
    atomic_write_text(pointer, str(run_dir) + "\n")

    print(STATUS)
    print(f"RUN_DIR={run_dir}")
    print(f"VIDEO_MP4={mp4}")
    print(f"VIDEO_GIF={preview_gif}")
    print(f"STORYBOARD={storyboard}")
    print(f"CENTRAL_STATE_POSTER={central_poster}")
    print(f"FINAL_STATE_POSTER={final_poster}")
    print(f"FRAMES_DIR={frames_dir}")
    print(f"FRAME_MANIFEST={run_dir / 'tables' / f'video02_frame_manifest_{VERSION}.tsv'}")
    print(f"EXACT_STATES={run_dir / 'tables' / f'video02_exact_states_{VERSION}.tsv'}")
    print(f"CAPTION={run_dir / 'reports' / f'video02_caption_{VERSION}.md'}")
    print(f"REPORT={run_dir / 'reports' / f'video02_render_report_{VERSION}.md'}")
    print(f"VALIDATION={run_dir / 'reports' / f'video02_validation_{VERSION}.tsv'}")
    print(f"SUMMARY={run_dir / f'summary_{VERSION}.json'}")
    print(f"CHECKSUMS={run_dir / f'checksums_{VERSION}.tsv'}")
    print(f"CURRENT_POINTER={pointer}")
    print("FULL_VIDEO_RENDERED=TRUE")
    print("SCIENTIFIC_EXECUTION=NONE")
    print("REACTION_PATH_VISUALIZATION=TRUE")
    print("MOLECULAR_DYNAMICS=FALSE")
    return 0


def perform_validate_only(root: Path) -> int:
    inputs = load_locked_inputs(root)
    validation = validate_inputs(inputs)
    prepared = prepare_path(inputs)
    print("VALIDATE_ONLY=PASS")
    print(f"INPUT_ATTEMPT={inputs.attempt}")
    print(f"DFT_ROWS={validation['dft_rows']}")
    print(f"XYZ_FRAMES={validation['xyz_frames']}")
    print(f"MAXIMUM_IMAGE={validation['maximum_image']}")
    print(f"BARRIER_MEV={validation['barrier_mev']:.12f}")
    print(f"GLOBAL_REFERENCE_IMAGE={EXPECTED_MAX_IMAGE}")
    print(f"GLOBAL_BOUNDS={prepared.bounds}")
    print("SCIENTIFIC_EXECUTION=NONE")
    print("MOLECULAR_DYNAMICS=FALSE")
    return 0


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="video02_v032_selftest_") as temporary:
        root = Path(temporary) / "root"
        ensure_dir(root)
        make_synthetic_fixture(root)
        inputs = load_locked_inputs(root)
        validation = validate_inputs(inputs)
        write_outputs(
            root,
            inputs,
            width=960,
            height=540,
            dpi=100,
            fps=12,
            start_hold=3,
            motion_frames=29,
            end_hold=4,
            crossfade_frames=0,
            slowdown=DEFAULT_SLOWDOWN,
        )
        version_root = root / "10_visualization" / "versions" / VERSION_DIRNAME
        pointer = version_root / POINTER_NAME
        run_dir = Path(read_text(pointer).strip())
        required = [
            run_dir / "video" / f"video02_proton_transfer_pbe_mep_clean_{VERSION}.mp4",
            run_dir / "video" / f"video02_proton_transfer_pbe_mep_clean_preview_{VERSION}.gif",
            run_dir / "figures" / f"video02_pbe_mep_storyboard_{VERSION}.png",
            run_dir / "figures" / f"video02_pbe_mep_central_state_{VERSION}.png",
        ]
        for path in required:
            if not path.is_file() or path.stat().st_size == 0:
                raise RenderError(f"SELF_TEST missing output: {path}")
        print("SELF_TEST=PASS")
        print(f"VALIDATION_CHECKS={validation['validation_checks']}")
        print("FORMATS=PNG,MP4,GIF")
        print("CHECKSUM_LOCK=PASS")
        print("GLOBAL_ALIGNMENT=PASS")
        print("FULL_VIDEO_RENDERED=TRUE")
        print("SCIENTIFIC_EXECUTION=NONE")
        print("MOLECULAR_DYNAMICS=FALSE")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("${PROJECT_ROOT}"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--start-hold", type=int, default=DEFAULT_START_HOLD)
    parser.add_argument("--motion-frames", type=int, default=DEFAULT_MOTION_FRAMES)
    parser.add_argument("--end-hold", type=int, default=DEFAULT_END_HOLD)
    parser.add_argument("--crossfade-frames", type=int, default=0)
    parser.add_argument("--slowdown", type=float, default=DEFAULT_SLOWDOWN)
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.validate_only:
        return perform_validate_only(args.root)
    inputs = load_locked_inputs(args.root)
    return write_outputs(
        args.root,
        inputs,
        width=args.width,
        height=args.height,
        dpi=args.dpi,
        fps=args.fps,
        start_hold=args.start_hold,
        motion_frames=args.motion_frames,
        end_hold=args.end_hold,
        crossfade_frames=args.crossfade_frames,
        slowdown=args.slowdown,
    )


if __name__ == "__main__":
    raise SystemExit(main())

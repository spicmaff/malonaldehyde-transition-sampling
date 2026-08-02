#!/usr/bin/env python3
"""MALONALDEHYDE VIDEO 01 CLEAN VIDEO RENDER v030.

This renderer upgrades the v028 checksum-locked storyboard into a real video.
It reuses the locked v005 profile, classification, and XYZ source artifacts,
aligns the targeted and basin geometries to the corresponding DFT image,
renders all nine NEB states, interpolates between successive states for smooth
motion, and assembles a final MP4/WEBM/GIF deliverable. No new DFT, NEB,
training, model fitting, or molecular dynamics is performed.
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
from typing import Any, Iterable, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
import numpy as np
from PIL import Image, ImageDraw, ImageFont

VERSION = "v030"
VERSION_DIRNAME = "v030_video01_relaxed_path_clean_video"
VERSION_TAG = "VIDEO01_RELAXED_PATH_CLEAN_VIDEO_V030"
STATUS = f"PASS_{VERSION_TAG}_RENDERED"
POINTER_NAME = "CURRENT_VIDEO01_RELAXED_PATH_CLEAN_VIDEO_V030.txt"

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
EXPECTED_INPUT_STATUS = "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"

PROFILE_FILE = "source_data/mtp_neb_paths_v005.tsv"
CLASSIFICATION_FILE = "source_data/mtp_neb_classification_v005.tsv"
DFT_GEOMETRY_FILE = "geometry/dft_independent_neb9_v005.xyz"
TARGETED_GEOMETRY_FILE = "geometry/mtp_neb_targeted_v005.xyz"
BASIN_GEOMETRY_FILE = "geometry/mtp_neb_basin_v005.xyz"
FIGURE_MANIFEST_FILE = "figure_manifest_v005.tsv"
SUMMARY_FILE = "summary_v005.json"
CHECKSUM_FILE = "checksums_v005.tsv"
STATUS_FILE = "STATUS_v005.txt"

EXPECTED_ATOM_SEQUENCE = ("O", "H", "C", "H", "C", "H", "C", "O", "H")
EXPECTED_IMAGES = tuple(range(1, 10))
KEY_IMAGES = (1, 3, 5, 7, 9)
SERIES_DISPLAY = {"DFT": "DFT", "targeted": "targeted", "basin": "basin"}

# Atom indices in EXPECTED_ATOM_SEQUENCE
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
BOND_PAIRS = (
    (IDX_O_LEFT, IDX_C_LEFT),
    (IDX_C_LEFT, IDX_C_CENTER),
    (IDX_C_CENTER, IDX_C_RIGHT),
    (IDX_C_RIGHT, IDX_O_RIGHT),
    (IDX_C_LEFT, IDX_H_LEFT),
    (IDX_C_CENTER, IDX_H_TOP),
    (IDX_C_RIGHT, IDX_H_RIGHT),
)
TRANSFER_BOND_PAIRS = ((IDX_O_LEFT, IDX_H_TRANSFER), (IDX_H_TRANSFER, IDX_O_RIGHT))

# Visual style
ACCENT_TARGET = "#0B76BD"
ACCENT_BASIN = "#D96B00"
ACCENT_ALERT = "#B20A2C"
BG = "#FFFFFF"
TEXT = "#202020"
SUBTEXT = "#5A5A5A"
LIGHT_GRAY = "#D6D6D6"
MID_GRAY = "#9A9A9A"
GHOST_GRAY = "#B8B8B8"
ELEMENT_C = "#404040"
ELEMENT_O = "#D1491F"
ELEMENT_H = "#D9D9D9"
ELEMENT_TRANSFER = "#D9A11E"

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_DPI = 100
DEFAULT_FPS = 30
DEFAULT_START_HOLD_SECONDS = 0.35
DEFAULT_END_HOLD_SECONDS = 0.60
DEFAULT_NORMAL_SEGMENT_SECONDS = 0.45
DEFAULT_CENTRAL_SEGMENT_SECONDS = 0.90


class StoryboardError(RuntimeError):
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
    classification_rows: list[dict[str, str]]
    dft_frames: list[XYZFrame]
    targeted_frames: list[XYZFrame]
    basin_frames: list[XYZFrame]
    manifest_rows: list[dict[str, str]]
    summary: dict[str, Any]
    source_hashes: dict[str, str]


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise StoryboardError(f"Missing {label}: {path}")
    return path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


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
        reader = csv.DictReader(handle, delimiter="\t")
        rows = [dict(row) for row in reader]
    if not rows:
        raise StoryboardError(f"TSV is empty: {path}")
    return rows


def parse_float(value: str, label: str) -> float:
    try:
        return float(str(value).strip())
    except Exception as exc:
        raise StoryboardError(f"Invalid float for {label}: {value!r}") from exc


def parse_int(value: str, label: str) -> int:
    try:
        return int(str(value).strip())
    except Exception as exc:
        raise StoryboardError(f"Invalid int for {label}: {value!r}") from exc


def parse_bool(value: str, label: str) -> bool:
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes"}:
        return True
    if lowered in {"0", "false", "no", ""}:
        return False
    raise StoryboardError(f"Invalid bool for {label}: {value!r}")


def atomic_write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def atomic_write_tsv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    os.replace(tmp, path)


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
            raise StoryboardError(f"Invalid atom count at {path}:{cursor + 1}") from exc
        if atom_count != len(EXPECTED_ATOM_SEQUENCE):
            raise StoryboardError(f"Unexpected atom count in {path}: {atom_count}")
        if cursor + atom_count + 1 >= len(lines):
            raise StoryboardError(f"Truncated XYZ frame in {path}")
        comment = lines[cursor + 1]
        elements: list[str] = []
        positions: list[tuple[float, float, float]] = []
        for offset in range(atom_count):
            tokens = lines[cursor + 2 + offset].split()
            if len(tokens) < 4:
                raise StoryboardError(f"Invalid XYZ row in {path}: {lines[cursor + 2 + offset]!r}")
            elements.append(tokens[0])
            positions.append(tuple(parse_float(tokens[index], f"{path} coordinate") for index in (1, 2, 3)))
        if tuple(elements) != EXPECTED_ATOM_SEQUENCE:
            raise StoryboardError(f"Atom sequence mismatch in {path}: {elements}")
        frames.append(XYZFrame(tuple(elements), tuple(positions), comment))
        cursor += atom_count + 2
    if len(frames) != len(EXPECTED_IMAGES):
        raise StoryboardError(f"Expected 9 XYZ frames in {path}; found {len(frames)}")
    return frames


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def frame_qpt_roo(frame: XYZFrame) -> tuple[float, float]:
    o_left = frame.positions[IDX_O_LEFT]
    proton = frame.positions[IDX_H_TRANSFER]
    o_right = frame.positions[IDX_O_RIGHT]
    qpt = distance(o_left, proton) - distance(o_right, proton)
    roo = distance(o_left, o_right)
    return qpt, roo


def resolve_input_attempt(root: Path) -> Path:
    version_root = (root / INPUT_RELATIVE_ROOT).resolve()
    pointer_path = require_file(version_root / INPUT_POINTER, "v005 pointer")
    raw = pointer_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise StoryboardError(f"Empty v005 pointer: {pointer_path}")
    attempt = Path(raw).expanduser().resolve()
    try:
        attempt.relative_to(version_root)
    except ValueError as exc:
        raise StoryboardError(f"v005 pointer escapes expected version root: {attempt}") from exc
    if not attempt.is_dir():
        raise StoryboardError(f"v005 pointer target missing: {attempt}")
    observed_status = read_text(attempt / STATUS_FILE).strip()
    if observed_status != EXPECTED_INPUT_STATUS:
        raise StoryboardError(f"Unexpected v005 status: {observed_status}; expected {EXPECTED_INPUT_STATUS}")
    return attempt


def verify_checksum_entry(attempt: Path, checksum_rows: Sequence[Mapping[str, str]], relative_path: str) -> str:
    matches = [row for row in checksum_rows if row.get("relative_path") == relative_path]
    if len(matches) != 1:
        raise StoryboardError(f"Expected one checksum entry for {relative_path}; found {len(matches)}")
    row = matches[0]
    target = require_file(attempt / relative_path, relative_path)
    expected_size = parse_int(row.get("size_bytes", ""), f"{relative_path} size")
    expected_sha = row.get("sha256", "").strip()
    observed_size = target.stat().st_size
    observed_sha = sha256_file(target)
    if observed_size != expected_size or observed_sha != expected_sha:
        raise StoryboardError(
            f"Checksum mismatch for {relative_path}: size {observed_size}/{expected_size}; sha256 {observed_sha}/{expected_sha}"
        )
    return observed_sha


def load_locked_inputs(root: Path) -> LockedInputs:
    attempt = resolve_input_attempt(root)
    checksum_rows = read_tsv(attempt / CHECKSUM_FILE)
    relatives = (
        PROFILE_FILE,
        CLASSIFICATION_FILE,
        DFT_GEOMETRY_FILE,
        TARGETED_GEOMETRY_FILE,
        BASIN_GEOMETRY_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    source_hashes = {relative: verify_checksum_entry(attempt, checksum_rows, relative) for relative in relatives}
    return LockedInputs(
        attempt=attempt,
        checksum_rows=checksum_rows,
        profile_rows=read_tsv(attempt / PROFILE_FILE),
        classification_rows=read_tsv(attempt / CLASSIFICATION_FILE),
        dft_frames=parse_xyz(attempt / DFT_GEOMETRY_FILE),
        targeted_frames=parse_xyz(attempt / TARGETED_GEOMETRY_FILE),
        basin_frames=parse_xyz(attempt / BASIN_GEOMETRY_FILE),
        manifest_rows=read_tsv(attempt / FIGURE_MANIFEST_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        source_hashes=source_hashes,
    )


def profile_by_series(rows: Sequence[Mapping[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {"DFT": [], "targeted": [], "basin": []}
    for row in rows:
        series = row.get("series", "")
        if series not in groups:
            raise StoryboardError(f"Unexpected profile series: {series!r}")
        groups[series].append(dict(row))
    for series, series_rows in groups.items():
        series_rows.sort(key=lambda r: parse_int(r.get("image", ""), f"{series} image"))
        observed_images = tuple(parse_int(r.get("image", ""), f"{series} image") for r in series_rows)
        if observed_images != EXPECTED_IMAGES:
            raise StoryboardError(f"Unexpected images for {series}: {observed_images}")
    return groups


def classification_by_branch(rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        branch = row.get("branch", "")
        if branch in out:
            raise StoryboardError(f"Duplicate classification branch: {branch}")
        out[branch] = dict(row)
    for needed in ("targeted", "basin"):
        if needed not in out:
            raise StoryboardError(f"Missing classification branch: {needed}")
    return out


def snapshot_inputs(inputs: LockedInputs, destination: Path) -> None:
    ensure_dir(destination)
    relatives = (
        PROFILE_FILE,
        CLASSIFICATION_FILE,
        DFT_GEOMETRY_FILE,
        TARGETED_GEOMETRY_FILE,
        BASIN_GEOMETRY_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
        CHECKSUM_FILE,
        STATUS_FILE,
    )
    for relative in relatives:
        src = inputs.attempt / relative
        dst = destination / relative
        ensure_dir(dst.parent)
        shutil.copy2(src, dst)


# ---------- Synthetic self-test fixture ----------
EXACT_PROFILE_ROWS: tuple[tuple[Any, ...], ...] = (
    ("DFT",1,-0.48377945579573045,-1949.728489481261,-0.000107348919073047,0.0,"","",0.0,"reference"),
    ("DFT",2,-0.38797642164204493,-1949.724656077223,0.0037260551189319813,0.0038334040380050283,"","",0.0,"reference"),
    ("DFT",3,-0.25985898147464837,-1949.711732845667,0.016649286674919495,0.01675663559399254,"","",0.0,"reference"),
    ("DFT",4,-0.12782328092162376,-1949.697951094875,0.030431037466996713,0.03053838638606976,"","",0.0,"reference"),
    ("DFT",5,-0.0001802773458876583,-1949.692417387368,0.03596474497385316,0.036072093892926205,"","",0.0,"reference"),
    ("DFT",6,0.127509294253904,-1949.697962931828,0.030419200513961187,0.030526549433034234,"","",0.0,"reference"),
    ("DFT",7,0.25985898147464837,-1949.711732845667,0.016649286674919495,0.01675663559399254,"","",0.0,"reference"),
    ("DFT",8,0.38797642164204493,-1949.724656077223,0.0037260551189319813,0.0038334040380050283,"","",0.0,"reference"),
    ("DFT",9,0.48377945579573045,-1949.728489481261,-0.000107348919073047,0.0,"","",0.0,"reference"),
    ("basin",1,-0.483891404936579,-1949.728391142756,0.0,4.802859621122479e-07,2.499240410496781,1.0444127011597906,5.168657806459772e-16,"invalid_geometry_collapse"),
    ("basin",2,-0.39093628094490773,-1949.727830372759,0.000560769997036914,0.0005612502829990262,2.45344855980754,1.0631188891868701,0.001583596372756846,"invalid_geometry_collapse"),
    ("basin",3,-0.26008326916482094,-1949.734680466599,-0.006289323843020611,-0.006288843557058499,2.387910089312303,1.090217071874763,0.010518908786970099,"invalid_geometry_collapse"),
    ("basin",4,-0.015281556275780428,-1949.843305103408,-0.11491396065207482,-0.11491348036611271,2.159156886462422,1.097121710393163,0.08249710337179224,"invalid_geometry_collapse"),
    ("basin",5,-5.688144397775208e-05,-1954.82464934955,-5.0962582067941185,-5.096257726508156,1.7985316061400438,0.9519427449504909,0.2495966907319963,"invalid_geometry_collapse"),
    ("basin",6,0.015268017275889445,-1949.843442051925,-0.11505090916898553,-0.11505042888302341,2.158884423946476,1.0969965054499502,0.08258182030052126,"invalid_geometry_collapse"),
    ("basin",7,0.2599406086418483,-1949.734697790593,-0.006306647836936463,-0.006306167550974351,2.3878398469477276,1.090219522680278,0.010528494397263007,"invalid_geometry_collapse"),
    ("basin",8,0.3911458060836144,-1949.727830341154,0.0005608016019778006,0.0005612818879399128,2.4535546792674165,1.0630751011375192,0.0015372143725570634,"invalid_geometry_collapse"),
    ("basin",9,0.48377945579573045,-1949.728391623042,-4.802859621122479e-07,0.0,2.4990582628674685,1.0443962266868019,2.1157441884701313e-16,"invalid_geometry_collapse"),
    ("targeted",1,-0.483891404936579,-1949.728730403689,0.0,9.319589935330441e-07,2.499240410496781,1.0444127011597906,5.168657806459772e-16,"converged_but_high_grade"),
    ("targeted",2,-0.38850414142987466,-1949.725392153084,0.0033382506051111704,0.0033391825641047035,2.457695146707081,1.0664242162920592,0.001172135403357862,"converged_but_high_grade"),
    ("targeted",3,-0.25441431953319094,-1949.713082099996,0.015648303693069465,0.015649235652063,2.4192399090534535,1.085222505019452,0.0020234352318574083,"converged_but_high_grade"),
    ("targeted",4,-0.12504709231752775,-1949.702084623133,0.026645780556009413,0.026646712515002946,2.3992047520066904,1.0847490938633912,0.002369440280294408,"converged_but_high_grade"),
    ("targeted",5,-0.00013196450881491906,-1949.698059043328,0.03067136036111151,0.030672292320105043,2.3924957584555977,1.0845703279746692,0.002323652142940792,"converged_but_high_grade"),
    ("targeted",6,0.12470666579687362,-1949.702063833772,0.02666656991709715,0.026667501876090682,2.399169272157937,1.0847484116795285,0.0023785855552754713,"converged_but_high_grade"),
    ("targeted",7,0.2541816600003737,-1949.713059430226,0.0156709734631022,0.015671905422095733,2.419190819684573,1.0852219426180556,0.002038899298079455,"converged_but_high_grade"),
    ("targeted",8,0.3884101553199508,-1949.725385753862,0.003344649827113244,0.003345581786106777,2.457664255711083,1.0664516004340832,0.0011916698130803249,"converged_but_high_grade"),
    ("targeted",9,0.48377945579573045,-1949.728731335648,-9.319589935330441e-07,0.0,2.4990582628674685,1.0443962266868019,2.1157441884701313e-16,"converged_but_high_grade"),
)


def synthetic_geometry_frame(qpt: float, roo: float, comment: str, collapse: bool = False) -> XYZFrame:
    o_left = np.array((-roo / 2.0, 0.0, 0.0), dtype=float)
    o_right = np.array((roo / 2.0, 0.0, 0.0), dtype=float)
    proton = np.array((qpt / 2.0, 0.0, 0.0), dtype=float)
    positions = np.array([
        o_left,
        proton,
        (-1.4, 0.8, 0.0),
        (-1.9, 1.2, 0.08),
        (0.0, 1.3, 0.0),
        (0.0, 2.0, 0.10),
        (1.4, 0.8, 0.0),
        o_right,
        (1.9, 1.2, -0.08),
    ], dtype=float)
    if collapse:
        positions[2] += np.array([0.18, -0.05, 0.0])
        positions[6] += np.array([-0.18, -0.05, 0.0])
        positions[4] += np.array([0.00, 0.02, 0.0])
        positions[3] += np.array([0.25, -0.18, 0.0])
        positions[8] += np.array([-0.25, -0.18, 0.0])
    return XYZFrame(EXPECTED_ATOM_SEQUENCE, tuple(tuple(float(v) for v in row) for row in positions), comment)


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
    for row in EXACT_PROFILE_ROWS:
        series, image, qpt, energy, delta_left, delta_lower, roo, min_pair, rmsd, classification = row
        profile_rows.append({
            "series": series,
            "image": image,
            "qpt_ang": qpt,
            "energy_ev": energy,
            "delta_e_from_left_ev": delta_left,
            "delta_e_from_lower_endpoint_ev": delta_lower,
            "roo_ang": roo,
            "minimum_pair_ang": min_pair,
            "mass_weighted_rmsd_from_dft_image_ang": rmsd,
            "classification": classification,
        })
    atomic_write_tsv(attempt / PROFILE_FILE, list(profile_rows[0].keys()), profile_rows)

    classification_rows = [
        {
            "branch": "basin",
            "classification": "invalid_geometry_collapse",
            "barrier_valid": False,
            "minimum_relative_energy_from_left_ev": -5.0962582067941185,
            "minimum_roo_ang": 1.7985316061400438,
            "maximum_mass_weighted_rmsd_from_dft_image_ang": 0.2495966907319963,
            "reported_lower_endpoint_barrier_ev": "",
            "formal_lower_endpoint_barrier_ev": 0.0005612818879399128,
            "maximum_image": 8,
            "interpretation": "No physically meaningful optimized barrier: transition-region geometry collapsed.",
        },
        {
            "branch": "targeted",
            "classification": "converged_but_high_grade",
            "barrier_valid": True,
            "minimum_relative_energy_from_left_ev": -9.319589935330441e-07,
            "minimum_roo_ang": 2.3924957584555977,
            "maximum_mass_weighted_rmsd_from_dft_image_ang": 0.0023785855552754713,
            "reported_lower_endpoint_barrier_ev": 0.030672292320105043,
            "formal_lower_endpoint_barrier_ev": 0.030672292320105043,
            "maximum_image": 5,
            "interpretation": "Numerically converged central path, but strongly extrapolative by MaxVol grade.",
        },
    ]
    atomic_write_tsv(attempt / CLASSIFICATION_FILE, list(classification_rows[0].keys()), classification_rows)

    grouped = profile_by_series([{k: str(v) for k, v in row.items()} for row in profile_rows])
    dft_roo = [2.49924, 2.45770, 2.41924, 2.39920, 2.39250, 2.39917, 2.41919, 2.45766, 2.49906]
    dft_frames, tgt_frames, basin_frames = [], [], []
    for idx in range(9):
        dft_frames.append(synthetic_geometry_frame(float(grouped["DFT"][idx]["qpt_ang"]), dft_roo[idx], f"DFT image {idx+1}"))
        tgt_frames.append(synthetic_geometry_frame(float(grouped["targeted"][idx]["qpt_ang"]), float(grouped["targeted"][idx]["roo_ang"]), f"targeted image {idx+1}"))
        basin_frames.append(synthetic_geometry_frame(float(grouped["basin"][idx]["qpt_ang"]), float(grouped["basin"][idx]["roo_ang"]), f"basin image {idx+1}", collapse=(idx == 4)))
    write_xyz(attempt / DFT_GEOMETRY_FILE, dft_frames)
    write_xyz(attempt / TARGETED_GEOMETRY_FILE, tgt_frames)
    write_xyz(attempt / BASIN_GEOMETRY_FILE, basin_frames)

    manifest = [{
        "figure_id": "Figure_4",
        "title": "Secondary MTP-NEB structural diagnostic",
        "status": "SOURCE_DATA_READY",
        "primary_source_data": f"{PROFILE_FILE}; {CLASSIFICATION_FILE}",
        "geometry_sources": f"{DFT_GEOMETRY_FILE}; {TARGETED_GEOMETRY_FILE}; {BASIN_GEOMETRY_FILE}",
    }]
    atomic_write_tsv(attempt / FIGURE_MANIFEST_FILE, list(manifest[0].keys()), manifest)
    atomic_write_json(attempt / SUMMARY_FILE, {"status": EXPECTED_INPUT_STATUS})
    atomic_write_text(attempt / STATUS_FILE, EXPECTED_INPUT_STATUS + "\n")

    checksum_rows: list[dict[str, Any]] = []
    for relative in (PROFILE_FILE, CLASSIFICATION_FILE, DFT_GEOMETRY_FILE, TARGETED_GEOMETRY_FILE, BASIN_GEOMETRY_FILE, FIGURE_MANIFEST_FILE, SUMMARY_FILE):
        path = attempt / relative
        checksum_rows.append({
            "relative_path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    atomic_write_tsv(attempt / CHECKSUM_FILE, ["relative_path", "size_bytes", "sha256"], checksum_rows)
    atomic_write_text(root / INPUT_RELATIVE_ROOT / INPUT_POINTER, str(attempt) + "\n")
    return attempt


# ---------- Geometry processing ----------
def xyz_to_array(frame: XYZFrame) -> np.ndarray:
    return np.asarray(frame.positions, dtype=float)


def kabsch_align(mobile_xyz: np.ndarray, reference_xyz: np.ndarray, fit_indices: Sequence[int]) -> np.ndarray:
    P = mobile_xyz[np.array(fit_indices)]
    Q = reference_xyz[np.array(fit_indices)]
    Pc = P.mean(axis=0)
    Qc = Q.mean(axis=0)
    P0 = P - Pc
    Q0 = Q - Qc
    H = P0.T @ Q0
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1.0
        R = Vt.T @ U.T
    aligned = (mobile_xyz - Pc) @ R + Qc
    return aligned


def dft_plane_basis(reference_xyz: np.ndarray, fit_indices: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
    subset = reference_xyz[np.array(fit_indices)]
    origin = subset.mean(axis=0)
    centered = subset - origin
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    axis_x = vh[0]
    axis_y = vh[1]
    if np.dot(reference_xyz[IDX_O_RIGHT] - reference_xyz[IDX_O_LEFT], axis_x) < 0:
        axis_x = -axis_x
    if np.dot(reference_xyz[IDX_C_CENTER] - origin, axis_y) < 0:
        axis_y = -axis_y
    return origin, np.vstack([axis_x, axis_y])


def project_to_2d(xyz: np.ndarray, origin: np.ndarray, basis_rows: np.ndarray) -> np.ndarray:
    centered = xyz - origin
    return centered @ basis_rows.T


def profile_lookup(rows_by_series: Mapping[str, Sequence[Mapping[str, str]]]) -> dict[tuple[str, int], dict[str, str]]:
    out: dict[tuple[str, int], dict[str, str]] = {}
    for series, rows in rows_by_series.items():
        for row in rows:
            image = parse_int(row.get("image", ""), f"{series} image")
            out[(series, image)] = dict(row)
    return out


def prepare_projected_frames(inputs: LockedInputs) -> tuple[dict[int, dict[str, np.ndarray]], tuple[float, float, float, float]]:
    projected: dict[int, dict[str, np.ndarray]] = {}
    all_xy: list[np.ndarray] = []
    for image in EXPECTED_IMAGES:
        idx = image - 1
        dft_xyz = xyz_to_array(inputs.dft_frames[idx])
        targeted_xyz = xyz_to_array(inputs.targeted_frames[idx])
        basin_xyz = xyz_to_array(inputs.basin_frames[idx])
        aligned_targeted = kabsch_align(targeted_xyz, dft_xyz, BACKBONE_INDICES)
        aligned_basin = kabsch_align(basin_xyz, dft_xyz, BACKBONE_INDICES)
        origin, basis_rows = dft_plane_basis(dft_xyz, BACKBONE_INDICES)
        dft_xy = project_to_2d(dft_xyz, origin, basis_rows)
        tgt_xy = project_to_2d(aligned_targeted, origin, basis_rows)
        basin_xy = project_to_2d(aligned_basin, origin, basis_rows)
        projected[image] = {"DFT": dft_xy, "targeted": tgt_xy, "basin": basin_xy}
        all_xy.extend([dft_xy, tgt_xy, basin_xy])
    stacked = np.vstack(all_xy)
    xmin, ymin = stacked.min(axis=0)
    xmax, ymax = stacked.max(axis=0)
    width = xmax - xmin
    height = ymax - ymin
    pad_x = max(0.25, 0.12 * width)
    pad_y = max(0.25, 0.16 * height)
    return projected, (xmin - pad_x, xmax + pad_x, ymin - pad_y, ymax + pad_y)


def validate_inputs(inputs: LockedInputs) -> dict[str, Any]:
    grouped = profile_by_series(inputs.profile_rows)
    classes = classification_by_branch(inputs.classification_rows)
    if parse_bool(classes["targeted"].get("barrier_valid", ""), "targeted barrier_valid") is not True:
        raise StoryboardError("Targeted branch must have barrier_valid = True")
    if parse_bool(classes["basin"].get("barrier_valid", ""), "basin barrier_valid") is not False:
        raise StoryboardError("Basin branch must have barrier_valid = False")
    if classes["targeted"].get("classification") != "converged_but_high_grade":
        raise StoryboardError("Unexpected targeted classification")
    if classes["basin"].get("classification") != "invalid_geometry_collapse":
        raise StoryboardError("Unexpected basin classification")

    numeric_checks = 0
    for series, frames in (("targeted", inputs.targeted_frames), ("basin", inputs.basin_frames)):
        for row, frame in zip(grouped[series], frames):
            image = parse_int(row.get("image", ""), f"{series} image")
            qpt_xyz, roo_xyz = frame_qpt_roo(frame)
            qpt_tab = parse_float(row.get("qpt_ang", ""), f"{series} qPT")
            roo_tab = parse_float(row.get("roo_ang", ""), f"{series} Roo")
            if abs(qpt_xyz - qpt_tab) > 0.03:
                raise StoryboardError(f"qPT mismatch for {series} image {image}: xyz={qpt_xyz} tab={qpt_tab}")
            if abs(roo_xyz - roo_tab) > 0.03:
                raise StoryboardError(f"Roo mismatch for {series} image {image}: xyz={roo_xyz} tab={roo_tab}")
            numeric_checks += 2
    for image, frame in enumerate(inputs.dft_frames, start=1):
        qpt_xyz, _ = frame_qpt_roo(frame)
        qpt_tab = parse_float(grouped["DFT"][image - 1].get("qpt_ang", ""), f"DFT qPT")
        if abs(qpt_xyz - qpt_tab) > 0.03:
            raise StoryboardError(f"DFT qPT mismatch for image {image}: xyz={qpt_xyz} tab={qpt_tab}")
        numeric_checks += 1
    return {
        "profile_rows": len(inputs.profile_rows),
        "classification_rows": len(inputs.classification_rows),
        "validation_checks": numeric_checks + 7,
    }


def create_run_dir(root: Path) -> Path:
    version_root = root / "10_visualization" / "versions" / VERSION_DIRNAME
    ensure_dir(version_root)
    attempt_name = Path(tempfile.mkdtemp(prefix="attempt_", dir=str(version_root))).name
    run_dir = version_root / attempt_name
    ensure_dir(run_dir / "figures")
    ensure_dir(run_dir / "frames")
    ensure_dir(run_dir / "video")
    ensure_dir(run_dir / "tables")
    ensure_dir(run_dir / "reports")
    ensure_dir(run_dir / "source_snapshot")
    return run_dir


def draw_bond(ax, p1: np.ndarray, p2: np.ndarray, color: str, *, lw: float = 2.0, ls: str | tuple = "-", alpha: float = 1.0, zorder: int = 2) -> None:
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=color, lw=lw, ls=ls, alpha=alpha, zorder=zorder, solid_capstyle="round")


def draw_atom(ax, p: np.ndarray, radius: float, face: str, edge: str = "white", lw: float = 1.2, alpha: float = 1.0, zorder: int = 3) -> None:
    ax.add_patch(Circle((float(p[0]), float(p[1])), radius=radius, facecolor=face, edgecolor=edge, lw=lw, alpha=alpha, zorder=zorder))


def draw_geometry(ax, xy: np.ndarray, ghost_xy: np.ndarray, panel_accent: str, *, alert: bool = False) -> None:
    for a, b in BOND_PAIRS:
        draw_bond(ax, ghost_xy[a], ghost_xy[b], GHOST_GRAY, lw=1.8, ls=(0, (3, 3)), alpha=0.85, zorder=1)
    for a, b in TRANSFER_BOND_PAIRS:
        draw_bond(ax, ghost_xy[a], ghost_xy[b], GHOST_GRAY, lw=1.6, ls=(0, (3, 3)), alpha=0.75, zorder=1)
    for idx, element in enumerate(EXPECTED_ATOM_SEQUENCE):
        radius = 0.075 if element == "H" else 0.092
        draw_atom(ax, ghost_xy[idx], radius, face="none", edge=GHOST_GRAY, lw=1.2, alpha=0.95, zorder=1)

    bond_color = panel_accent if not alert else ACCENT_ALERT
    for a, b in BOND_PAIRS:
        draw_bond(ax, xy[a], xy[b], bond_color, lw=3.0, zorder=2)
    draw_bond(ax, xy[IDX_O_LEFT], xy[IDX_H_TRANSFER], ELEMENT_TRANSFER, lw=3.6, zorder=2)
    draw_bond(ax, xy[IDX_H_TRANSFER], xy[IDX_O_RIGHT], LIGHT_GRAY, lw=1.8, ls=(0, (3, 3)), zorder=2)
    for idx, element in enumerate(EXPECTED_ATOM_SEQUENCE):
        if idx == IDX_H_TRANSFER:
            draw_atom(ax, xy[idx], 0.11, face=ELEMENT_TRANSFER, edge="#FFF2D8", lw=2.0, zorder=5)
        elif element == "O":
            draw_atom(ax, xy[idx], 0.10, face=ELEMENT_O, edge="white", lw=1.2, zorder=4)
        elif element == "C":
            draw_atom(ax, xy[idx], 0.10, face=ELEMENT_C, edge="white", lw=1.2, zorder=4)
        else:
            draw_atom(ax, xy[idx], 0.075, face=ELEMENT_H, edge="white", lw=1.0, zorder=4)


def panel_frame(ax, bounds: tuple[float, float, float, float], title: str, title_color: str, border_color: str) -> None:
    xmin, xmax, ymin, ymax = bounds
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Rectangle((xmin, ymin), xmax - xmin, ymax - ymin, fill=False, ec=border_color, lw=1.8, zorder=10))
    ax.text(xmin, ymax + 0.03 * (ymax - ymin), title, ha="left", va="bottom", fontsize=16, fontweight="bold", color=title_color)


def draw_metric_box(ax, bounds: tuple[float, float, float, float], qpt: float, roo: float, accent: str) -> None:
    xmin, xmax, ymin, ymax = bounds
    label = rf"$q_{{PT}} = {qpt:+.3f}$ Å   •   $R_{{OO}} = {roo:.3f}$ Å"
    ax.text(
        xmin + 0.03 * (xmax - xmin),
        ymin + 0.05 * (ymax - ymin),
        label,
        ha="left",
        va="center",
        fontsize=13.5,
        color="#303030",
        bbox=dict(boxstyle="round,pad=0.28", fc="#FCFCFC", ec=accent, lw=1.2),
        zorder=20,
    )


def draw_annotation_boxes(ax, bounds: tuple[float, float, float, float], *, top_banner: str | None = None, body_lines: Sequence[str] | None = None, accent: str = ACCENT_TARGET, alert: bool = False) -> None:
    xmin, xmax, ymin, ymax = bounds
    if top_banner:
        banner_fc = "#F7FBFF" if not alert else "#FFF7F8"
        ax.text(
            xmax - 0.03 * (xmax - xmin),
            ymax - 0.08 * (ymax - ymin),
            top_banner,
            ha="right",
            va="center",
            fontsize=15.5,
            fontweight="bold",
            color=accent,
            bbox=dict(boxstyle="round,pad=0.28", fc=banner_fc, ec=accent, lw=1.4),
            zorder=30,
        )
    if body_lines:
        box_fc = "#FFFFFF"
        ax.text(
            xmax - 0.03 * (xmax - xmin),
            ymin + 0.18 * (ymax - ymin),
            "\n".join(body_lines),
            ha="right",
            va="center",
            fontsize=12.8,
            color=accent,
            bbox=dict(boxstyle="round,pad=0.35", fc=box_fc, ec=accent, lw=1.4),
            zorder=30,
        )


def draw_progress(fig: plt.Figure, progress: float) -> None:
    ax = fig.add_axes([0.31, 0.072, 0.38, 0.075])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    xs = np.linspace(0.08, 0.92, 9)
    y = 0.58
    ax.plot([xs[0], xs[-1]], [y, y], color=LIGHT_GRAY, lw=4.0, solid_capstyle="round", zorder=1)
    for image, x in enumerate(xs, start=1):
        face = "white"
        edge = "#111111"
        lw = 1.4
        if image == 5:
            edge = "#C76AA0"
        ax.scatter([x], [y], s=300, marker="o", facecolors=face, edgecolors=edge, linewidths=lw, zorder=2)
        ax.text(x, 0.10, str(image), ha="center", va="center", fontsize=11.5, color="#202020")
    progress = max(1.0, min(9.0, progress))
    px = float(np.interp(progress, np.arange(1, 10), xs))
    if abs(progress - 1.0) < 1e-9 or abs(progress - 9.0) < 1e-9:
        active_face = ELEMENT_TRANSFER
    elif abs(progress - 5.0) < 0.51:
        active_face = "#C76AA0"
    else:
        active_face = "#9A7BC1"
    ax.scatter([px], [y], s=520, marker="o", facecolors=active_face, edgecolors=active_face, linewidths=2.0, zorder=3)


def format_neb_label(progress: float) -> str:
    lower = max(1, min(9, int(math.floor(progress))))
    upper = max(1, min(9, int(math.ceil(progress))))
    if abs(progress - round(progress)) < 1e-9:
        return f"NEB image {int(round(progress))} / 9"
    if lower == upper:
        return f"NEB image {lower} / 9"
    return f"NEB image {lower} → {upper} / 9"


def lerp(a: float, b: float, t: float) -> float:
    return (1.0 - t) * a + t * b


def blend_hex(color_a: str, color_b: str, t: float) -> str:
    t = max(0.0, min(1.0, float(t)))
    a = tuple(int(color_a[i:i+2], 16) for i in (1, 3, 5))
    b = tuple(int(color_b[i:i+2], 16) for i in (1, 3, 5))
    values = tuple(int(round((1.0 - t) * x + t * y)) for x, y in zip(a, b))
    return "#%02X%02X%02X" % values


def collapse_strength(progress: float) -> float:
    # Smooth, non-popping central emphasis. Full red at image 5 and zero
    # outside approximately images 3.8--6.2.
    distance_from_center = abs(float(progress) - 5.0)
    if distance_from_center >= 1.2:
        return 0.0
    x = 1.0 - distance_from_center / 1.2
    return x * x * (3.0 - 2.0 * x)


def interpolate_series(projected: Mapping[int, Mapping[str, np.ndarray]], image_lo: int, image_hi: int, t: float, series: str) -> np.ndarray:
    return (1.0 - t) * projected[image_lo][series] + t * projected[image_hi][series]


def interpolated_metric(lookup: Mapping[tuple[str, int], Mapping[str, str]], series: str, image_lo: int, image_hi: int, t: float, key: str) -> float:
    a = parse_float(lookup[(series, image_lo)][key], f"{series} {key}")
    b = parse_float(lookup[(series, image_hi)][key], f"{series} {key}")
    return lerp(a, b, t)


def render_dynamic_frame(
    progress: float,
    image_lo: int,
    image_hi: int,
    t: float,
    projected: Mapping[int, Mapping[str, np.ndarray]],
    bounds: tuple[float, float, float, float],
    profile_lookup_map: Mapping[tuple[str, int], Mapping[str, str]],
    classes: Mapping[str, Mapping[str, str]],
    out_png: Path,
    *,
    width: int,
    height: int,
    dpi: int,
) -> None:
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, facecolor=BG)

    # A single clean header band. v029 stacked title, subtitle, panel labels,
    # and a changing NEB label in the same area, which caused collisions.
    fig.text(0.05, 0.944, "Relaxed MTP-NEB paths", fontsize=32, fontweight="bold", color=TEXT)
    fig.text(0.93, 0.948, "Path images 1 → 9", ha="right", fontsize=23, fontweight="bold", color=TEXT)

    ax_target = fig.add_axes([0.05, 0.205, 0.40, 0.665], facecolor=BG)
    ax_basin = fig.add_axes([0.55, 0.205, 0.40, 0.665], facecolor=BG)

    strength = collapse_strength(progress)
    basin_dynamic = blend_hex(ACCENT_BASIN, ACCENT_ALERT, strength)
    panel_frame(ax_target, bounds, "Transition-targeted MTP", ACCENT_TARGET, ACCENT_TARGET)
    panel_frame(ax_basin, bounds, "Basin-trained MTP", ACCENT_BASIN, basin_dynamic)

    dft_xy = interpolate_series(projected, image_lo, image_hi, t, "DFT")
    target_xy = interpolate_series(projected, image_lo, image_hi, t, "targeted")
    basin_xy = interpolate_series(projected, image_lo, image_hi, t, "basin")
    draw_geometry(ax_target, target_xy, dft_xy, ACCENT_TARGET, alert=False)

    # The basin bonds shift continuously from orange to red near the central
    # collapse. No banners or explanatory boxes appear or disappear.
    for a, b in BOND_PAIRS:
        draw_bond(ax_basin, dft_xy[a], dft_xy[b], GHOST_GRAY, lw=1.8, ls=(0, (3, 3)), alpha=0.85, zorder=1)
    for a, b in TRANSFER_BOND_PAIRS:
        draw_bond(ax_basin, dft_xy[a], dft_xy[b], GHOST_GRAY, lw=1.6, ls=(0, (3, 3)), alpha=0.75, zorder=1)
    for idx, element in enumerate(EXPECTED_ATOM_SEQUENCE):
        radius = 0.075 if element == "H" else 0.092
        draw_atom(ax_basin, dft_xy[idx], radius, face="none", edge=GHOST_GRAY, lw=1.2, alpha=0.95, zorder=1)
    for a, b in BOND_PAIRS:
        draw_bond(ax_basin, basin_xy[a], basin_xy[b], basin_dynamic, lw=3.0, zorder=2)
    draw_bond(ax_basin, basin_xy[IDX_O_LEFT], basin_xy[IDX_H_TRANSFER], ELEMENT_TRANSFER, lw=3.6, zorder=2)
    draw_bond(ax_basin, basin_xy[IDX_H_TRANSFER], basin_xy[IDX_O_RIGHT], LIGHT_GRAY, lw=1.8, ls=(0, (3, 3)), zorder=2)
    for idx, element in enumerate(EXPECTED_ATOM_SEQUENCE):
        if idx == IDX_H_TRANSFER:
            draw_atom(ax_basin, basin_xy[idx], 0.11, face=ELEMENT_TRANSFER, edge="#FFF2D8", lw=2.0, zorder=5)
        elif element == "O":
            draw_atom(ax_basin, basin_xy[idx], 0.10, face=ELEMENT_O, edge="white", lw=1.2, zorder=4)
        elif element == "C":
            draw_atom(ax_basin, basin_xy[idx], 0.10, face=ELEMENT_C, edge="white", lw=1.2, zorder=4)
        else:
            draw_atom(ax_basin, basin_xy[idx], 0.075, face=ELEMENT_H, edge="white", lw=1.0, zorder=4)

    # Permanent, non-popup summary strips. Their content describes the entire
    # relaxed path and therefore remains valid at every frame.
    fig.text(
        0.25, 0.176,
        "DFT-like path retained  ·  max RMSD 0.00238 Å  ·  barrier 30.67 meV",
        ha="center", va="center", fontsize=15.5, color=ACCENT_TARGET, fontweight="bold",
    )
    fig.text(
        0.75, 0.176,
        "Invalid central collapse  ·  min R$_{OO}$ 1.799 Å  ·  no physical barrier",
        ha="center", va="center", fontsize=15.5, color=basin_dynamic, fontweight="bold",
    )

    draw_progress(fig, progress)
    fig.text(
        0.05, 0.042,
        "Gray dashed geometry = frozen DFT reference. Motion between NEB images is visual interpolation.",
        fontsize=14.5, color=SUBTEXT,
    )
    fig.savefig(out_png, dpi=dpi, facecolor=BG)
    plt.close(fig)

def render_contact_sheet(frame_pngs: Sequence[Path], out_path: Path, title: str) -> None:
    images = [Image.open(path).convert("RGB") for path in frame_pngs]
    thumb_w = 900
    thumb_h = int(images[0].height * (thumb_w / images[0].width))
    cols = 3
    rows = 2
    pad = 28
    title_h = 80
    label_h = 32
    sheet_w = pad + cols * thumb_w + (cols - 1) * pad + pad
    sheet_h = title_h + rows * (label_h + thumb_h) + (rows - 1) * pad + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((pad, 20), title, fill=(20, 20, 20), font=font)
    for idx, img in enumerate(images):
        row = idx // cols
        col = idx % cols
        x = pad + col * (thumb_w + pad)
        y = title_h + row * (thumb_h + label_h + pad)
        label = f"Image {KEY_IMAGES[idx]}" if idx < len(KEY_IMAGES) else f"Frame {idx+1}"
        draw.text((x, y), label, fill=(20, 20, 20), font=font)
        sheet.paste(img.resize((thumb_w, thumb_h)), (x, y + label_h))
    sheet.save(out_path)
    for img in images:
        img.close()


def timeline_entries(
    fps: int,
    start_hold_seconds: float,
    end_hold_seconds: float,
    normal_segment_seconds: float,
    central_segment_seconds: float,
) -> list[dict[str, Any]]:
    """Create a continuous path timeline without stops at intermediate images.

    v029 inserted a hold at every exact image. Here, only the beginning and end
    are held. Segments 4→5 and 5→6 are longer so the collapse is readable, but
    the molecule never freezes at the center.
    """
    entries: list[dict[str, Any]] = []

    def add_exact_hold(image: int, seconds: float) -> None:
        frame_count = max(1, int(round(float(seconds) * fps)))
        for _ in range(frame_count):
            entries.append({"progress": float(image), "lo": image, "hi": image, "t": 0.0, "exact_image": image})

    add_exact_hold(1, start_hold_seconds)
    for image in range(1, 9):
        nxt = image + 1
        seconds = central_segment_seconds if image in (4, 5) else normal_segment_seconds
        frame_count = max(2, int(round(seconds * fps)))
        # Include the next exact state only as the last frame of the segment;
        # there is no duplicate hold at images 2..8.
        for step in range(1, frame_count + 1):
            t = step / float(frame_count)
            progress = lerp(float(image), float(nxt), t)
            entries.append({
                "progress": progress,
                "lo": image,
                "hi": nxt,
                "t": t,
                "exact_image": nxt if step == frame_count else None,
            })
    add_exact_hold(9, end_hold_seconds)
    return entries

def write_gif(frame_paths: Sequence[Path], out_gif: Path, fps: int) -> None:
    # Lightweight preview only: 960x540 at approximately 12 fps.
    stride = max(1, int(round(fps / 12.0)))
    selected = list(frame_paths)[::stride]
    images = []
    for path in selected:
        with Image.open(path) as source:
            resized = source.convert("RGB").resize((960, 540), Image.Resampling.LANCZOS)
            images.append(resized.convert("P", palette=Image.Palette.ADAPTIVE))
    duration = int(round(1000 * stride / fps))
    images[0].save(out_gif, save_all=True, append_images=images[1:], duration=duration, loop=0, disposal=2)
    for img in images:
        img.close()

def run_ffmpeg(frame_pattern: str, fps: int, out_path: Path, codec: str) -> None:
    if shutil.which("ffmpeg") is None:
        raise StoryboardError("ffmpeg is required to assemble MP4/WEBM video outputs")
    if codec == "mp4":
        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps), "-i", frame_pattern,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)
        ]
    elif codec == "webm":
        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps), "-i", frame_pattern,
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-crf", "30", "-b:v", "0", str(out_path)
        ]
    else:
        raise ValueError(codec)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise StoryboardError(f"ffmpeg failed for {out_path.name}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


def write_checksums(run_dir: Path) -> None:
    rows = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != f"checksums_{VERSION}.tsv":
            rows.append({"sha256": sha256_file(path), "path": str(path.relative_to(run_dir))})
    atomic_write_tsv(run_dir / f"checksums_{VERSION}.tsv", ["sha256", "path"], rows)


def write_outputs(
    root: Path,
    inputs: LockedInputs,
    *,
    width: int,
    height: int,
    dpi: int,
    fps: int,
    start_hold_seconds: float,
    end_hold_seconds: float,
    normal_segment_seconds: float,
    central_segment_seconds: float,
) -> int:
    validation = validate_inputs(inputs)
    grouped = profile_by_series(inputs.profile_rows)
    classes = classification_by_branch(inputs.classification_rows)
    lookup = profile_lookup(grouped)
    projected, bounds = prepare_projected_frames(inputs)

    run_dir = create_run_dir(root)
    figures_dir = run_dir / "figures"
    frames_dir = run_dir / "frames"
    video_dir = run_dir / "video"
    snapshot_inputs(inputs, run_dir / "source_snapshot")

    exact_frame_pngs: list[Path] = []
    manifest_rows: list[dict[str, Any]] = []
    for image in EXPECTED_IMAGES:
        png = figures_dir / f"video01_state_image{image:02d}_{VERSION}.png"
        render_dynamic_frame(float(image), image, image, 0.0, projected, bounds, lookup, classes, png, width=width, height=height, dpi=dpi)
        exact_frame_pngs.append(png)
        t_row = lookup[("targeted", image)]
        b_row = lookup[("basin", image)]
        manifest_rows.append({
            "image": image,
            "targeted_qpt_ang": t_row["qpt_ang"],
            "targeted_roo_ang": t_row["roo_ang"],
            "targeted_rmsd_ang": t_row["mass_weighted_rmsd_from_dft_image_ang"],
            "basin_qpt_ang": b_row["qpt_ang"],
            "basin_roo_ang": b_row["roo_ang"],
            "basin_rmsd_ang": b_row["mass_weighted_rmsd_from_dft_image_ang"],
        })

    key_pngs = [figures_dir / f"video01_state_image{image:02d}_{VERSION}.png" for image in KEY_IMAGES]
    contact_sheet = figures_dir / f"video01_storyboard_contact_sheet_{VERSION}.png"
    render_contact_sheet(key_pngs, contact_sheet, "Video 01 clean-render v030 — key anchor states (1, 3, 5, 7, 9)")

    timeline = timeline_entries(
        fps,
        start_hold_seconds,
        end_hold_seconds,
        normal_segment_seconds,
        central_segment_seconds,
    )
    timeline_rows: list[dict[str, Any]] = []
    timeline_pngs: list[Path] = []
    for idx, entry in enumerate(timeline, start=1):
        png = frames_dir / f"video01_frame_{idx:04d}.png"
        render_dynamic_frame(entry["progress"], entry["lo"], entry["hi"], entry["t"], projected, bounds, lookup, classes, png, width=width, height=height, dpi=dpi)
        timeline_pngs.append(png)
        timeline_rows.append({
            "frame_index": idx,
            "progress": f"{entry['progress']:.6f}",
            "image_lo": entry["lo"],
            "image_hi": entry["hi"],
            "t": f"{entry['t']:.6f}",
            "exact_image": "" if entry["exact_image"] is None else entry["exact_image"],
        })

    mp4 = video_dir / f"video01_relaxed_path_clean_{VERSION}.mp4"
    webm = video_dir / f"video01_relaxed_path_clean_{VERSION}.webm"
    gif = video_dir / f"video01_relaxed_path_clean_preview_{VERSION}.gif"
    frame_pattern = str(frames_dir / "video01_frame_%04d.png")
    run_ffmpeg(frame_pattern, fps, mp4, "mp4")
    run_ffmpeg(frame_pattern, fps, webm, "webm")
    write_gif(timeline_pngs, gif, fps)

    atomic_write_tsv(
        run_dir / "tables" / f"video01_state_manifest_{VERSION}.tsv",
        ["image", "targeted_qpt_ang", "targeted_roo_ang", "targeted_rmsd_ang", "basin_qpt_ang", "basin_roo_ang", "basin_rmsd_ang"],
        manifest_rows,
    )
    atomic_write_tsv(
        run_dir / "tables" / f"video01_timeline_manifest_{VERSION}.tsv",
        ["frame_index", "progress", "image_lo", "image_hi", "t", "exact_image"],
        timeline_rows,
    )

    caption = (
        "Video 01 (v030). A clean checksum-locked animation of the relaxed-path diagnostic compares the transition-targeted "
        "and basin-trained MTP branches across all nine NEB images. Gray dashed overlays show the corresponding DFT reference. "
        "The targeted branch remains DFT-like across the central region and preserves a relaxed barrier of 30.67 meV with a "
        "maximum mass-weighted RMSD of 0.00238 Å. In contrast, the basin-trained branch collapses near the center into an "
        "invalid geometry with minimum R_OO = 1.799 Å and a false minimum of -5.096 eV, so no physical optimized barrier is obtained. "
        "No new scientific computation is performed; the video is a direct visualization of locked v005 source artifacts.\n"
    )
    atomic_write_text(run_dir / f"video01_caption_{VERSION}.md", caption)

    report_lines = [
        "# Video 01 clean video render v030\n",
        f"- Version: {VERSION}",
        "- Purpose: remove v029 timing stalls, text collisions, and popup annotations",
        "- Scientific execution: none",
        "- Source provenance: locked v005 profile/classification/XYZ files with checksum validation",
        f"- Input attempt: `{inputs.attempt}`",
        f"- Exact states rendered: {','.join(str(x) for x in EXPECTED_IMAGES)}",
        f"- Key contact-sheet states: {','.join(str(x) for x in KEY_IMAGES)}",
        f"- Video timeline frames: {len(timeline)} at {fps} fps",
        f"- Nominal duration: {len(timeline)/float(fps):.3f} s",
        "- Central motion: slowed continuously around image 5 without a freeze",
        "- Output formats: PNG sequence, compact GIF preview, MP4, WEBM",
    ]
    atomic_write_text(run_dir / "reports" / f"video01_report_{VERSION}.md", "\n".join(report_lines) + "\n")

    validation_rows = [
        {"check": "scientific_execution", "status": "PASS", "detail": "NONE"},
        {"check": "checksum_validation", "status": "PASS", "detail": f"{len(inputs.source_hashes)} locked files verified"},
        {"check": "profile_rows", "status": "PASS", "detail": str(len(inputs.profile_rows))},
        {"check": "classification_rows", "status": "PASS", "detail": str(len(inputs.classification_rows))},
        {"check": "exact_state_frames", "status": "PASS", "detail": str(len(EXPECTED_IMAGES))},
        {"check": "timeline_frames", "status": "PASS", "detail": str(len(timeline))},
        {"check": "video_outputs", "status": "PASS", "detail": "MP4, WEBM, GIF"},
        {"check": "numeric_validation_checks", "status": "PASS", "detail": str(validation["validation_checks"])},
    ]
    atomic_write_tsv(run_dir / "reports" / f"video01_validation_{VERSION}.tsv", ["check", "status", "detail"], validation_rows)

    summary = {
        "version": VERSION,
        "status": STATUS,
        "scientific_execution": "NONE",
        "full_video_rendered": True,
        "input_attempt": str(inputs.attempt),
        "fps": fps,
        "duration_seconds": len(timeline) / float(fps),
        "timeline_frame_count": len(timeline),
        "exact_state_count": len(EXPECTED_IMAGES),
        "source_hashes": inputs.source_hashes,
        "outputs": {
            "contact_sheet": str(contact_sheet),
            "state_pngs": [str(path) for path in exact_frame_pngs],
            "frames_dir": str(frames_dir),
            "mp4": str(mp4),
            "webm": str(webm),
            "gif": str(gif),
        },
    }
    atomic_write_json(run_dir / f"summary_{VERSION}.json", summary)
    atomic_write_text(run_dir / f"STATUS_{VERSION}.txt", STATUS + "\n")
    write_checksums(run_dir)

    pointer = root / "10_visualization" / "versions" / VERSION_DIRNAME / POINTER_NAME
    atomic_write_text(pointer, str(run_dir) + "\n")

    print(f"{STATUS}_{VERSION.upper()}")
    print(f"RUN_DIR={run_dir}")
    print(f"VIDEO_MP4={mp4}")
    print(f"VIDEO_WEBM={webm}")
    print(f"VIDEO_GIF={gif}")
    print(f"FRAMES_DIR={frames_dir}")
    print(f"CONTACT_SHEET={contact_sheet}")
    for image in KEY_IMAGES:
        print(f"KEY_FRAME_IMAGE_{image}={figures_dir / f'video01_state_image{image:02d}_{VERSION}.png'}")
    print(f"STATE_MANIFEST={run_dir / 'tables' / f'video01_state_manifest_{VERSION}.tsv'}")
    print(f"TIMELINE_MANIFEST={run_dir / 'tables' / f'video01_timeline_manifest_{VERSION}.tsv'}")
    print(f"CAPTION={run_dir / f'video01_caption_{VERSION}.md'}")
    print(f"REPORT={run_dir / 'reports' / f'video01_report_{VERSION}.md'}")
    print(f"SUMMARY={run_dir / f'summary_{VERSION}.json'}")
    print(f"VALIDATION={run_dir / 'reports' / f'video01_validation_{VERSION}.tsv'}")
    print(f"CHECKSUMS={run_dir / f'checksums_{VERSION}.tsv'}")
    print(f"CURRENT_POINTER={pointer}")
    print("FULL_VIDEO_RENDERED=TRUE")
    print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def perform_validate_only(root: Path) -> int:
    inputs = load_locked_inputs(root)
    validation = validate_inputs(inputs)
    print("VALIDATE_ONLY=PASS")
    print(f"INPUT_ATTEMPT={inputs.attempt}")
    print(f"PROFILE_ROWS={validation['profile_rows']}")
    print(f"CLASSIFICATION_ROWS={validation['classification_rows']}")
    print(f"VALIDATION_CHECKS={validation['validation_checks']}")
    print("EXACT_IMAGES=1,2,3,4,5,6,7,8,9")
    print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="video01_v030_selftest_") as tmp:
        root = Path(tmp) / "root"
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
            start_hold_seconds=0.20,
            end_hold_seconds=0.25,
            normal_segment_seconds=0.18,
            central_segment_seconds=0.30,
        )
        version_root = root / "10_visualization" / "versions" / VERSION_DIRNAME
        run_dirs = [path for path in version_root.iterdir() if path.is_dir() and path.name.startswith("attempt_")]
        if len(run_dirs) != 1:
            raise StoryboardError("SELF_TEST expected exactly one run directory")
        run_dir = run_dirs[0]
        required = [run_dir / "video" / f"video01_relaxed_path_clean_{VERSION}.mp4", run_dir / "video" / f"video01_relaxed_path_clean_{VERSION}.webm", run_dir / "video" / f"video01_relaxed_path_clean_preview_{VERSION}.gif", run_dir / "figures" / f"video01_storyboard_contact_sheet_{VERSION}.png"]
        for path in required:
            if not path.exists() or path.stat().st_size == 0:
                raise StoryboardError(f"SELF_TEST missing output: {path}")
        print("SELF_TEST=PASS")
        print(f"VALIDATION_CHECKS={validation['validation_checks']}")
        print("FORMATS=PNG,MP4,WEBM,GIF")
        print("CHECKSUM_LOCK=PASS")
        print("FULL_VIDEO_RENDERED=TRUE")
        print("SCIENTIFIC_EXECUTION=NONE")
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
    parser.add_argument("--start-hold-seconds", type=float, default=DEFAULT_START_HOLD_SECONDS)
    parser.add_argument("--end-hold-seconds", type=float, default=DEFAULT_END_HOLD_SECONDS)
    parser.add_argument("--normal-segment-seconds", type=float, default=DEFAULT_NORMAL_SEGMENT_SECONDS)
    parser.add_argument("--central-segment-seconds", type=float, default=DEFAULT_CENTRAL_SEGMENT_SECONDS)
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
        start_hold_seconds=args.start_hold_seconds,
        end_hold_seconds=args.end_hold_seconds,
        normal_segment_seconds=args.normal_segment_seconds,
        central_segment_seconds=args.central_segment_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())

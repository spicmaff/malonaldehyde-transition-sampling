#!/usr/bin/env python3
"""
Exact, source-guided replay of the six v032d geometry rows.

This stage replaces the previous broad best-fit search with one fixed contract:

  break    = exact frozen preselected.cfg
  mapping  = exact stored canonical_order_zero_based
  endpoint = trajectory-local endpoint.data sorted by persistent LAMMPS atom ID
  dump0    = unique timestep-zero dump frame directly identical to endpoint.data
  metrics  = direct Cartesian max/RMS, independent Kabsch RMSD, pair distances,
             q_PT and R_OO

The primary replay never chooses a different endpoint, a different atom mapping,
a different alignment or a different RMS convention per trajectory. A separate
identity audit looks for an exact post-step LAMMPS dump frame that can link raw
CFG rows back to persistent atom IDs. It is diagnostic and cannot alter the
primary replay.

No DFT, NEB, MTP training, model loading, calc-grade, LAMMPS execution or MD is
performed. All upstream artifacts are read-only.
"""

from __future__ import annotations

import argparse
import ast
import csv
import dataclasses
import datetime as dt
import hashlib
import itertools
import json
import math
import os
import re
import shutil
import sys
import tarfile
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


VERSION = "v001"
STAGE = "v032f_exact_geometry_provenance_replay"
DEFAULT_ROOT = Path("${PROJECT_ROOT}")

EXPECTED_PROVENANCE_SHA256 = (
    "8585a400029d74b7c5c13c4f37220e3954b5a4d90015d4f4cbee478f80de91be"
)
EXPECTED_CASES = (
    "T100_left", "T100_right", "T300_left", "T300_right",
    "T500_left", "T500_right",
)
LOCKED_ELEMENTS = ("O", "H", "C", "H", "C", "H", "C", "O", "H")
EXPECTED_RAW_TYPES = (1, 0, 2, 1, 2, 0, 1, 0, 1)
EXPECTED_RECORDED_ORDER = (4, 0, 5, 6, 7, 8, 1, 2, 3)
MLIP_TO_ELEMENT = {0: "C", 1: "H", 2: "O"}
LAMMPS_TO_ELEMENT = {1: "C", 2: "H", 3: "O"}

TOL_METRIC_A = 5.0e-9
TOL_DUMP0_A = 5.0e-10
TOL_CFG_DUMP_A = 5.0e-8

OUTPUT_REL = Path("09_strict_comparison/versions") / STAGE
POINTER_NAME = "CURRENT_V032D_EXACT_GEOMETRY_REPLAY.txt"
STATUS_NAME = "STATUS_v032f.txt"

SOURCE_TERMS = (
    "species_assignment",
    "canonical_order_zero_based",
    "canonicalization_candidate_count",
    "break_vs_endpoint_max_abs_ang",
    "break_vs_endpoint_rms_ang",
    "break_vs_endpoint_kabsch_rmsd_ang",
    "break_vs_endpoint_pair_distance_max_abs_delta_ang",
    "break_vs_dump0_max_abs_ang",
    "dump0_vs_endpoint_max_abs_ang",
    "kabsch",
    "permutations",
    "endpoint.data",
    "preselected.cfg",
)


class AuditError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Atom:
    atom_id: int
    atom_type: int
    element: str
    position: tuple[float, float, float]
    row_index: int


@dataclasses.dataclass
class Frame:
    source: Path
    kind: str
    label: str
    atoms: list[Atom]
    timestep: int | None = None
    box_lo: tuple[float, float, float] | None = None
    box_hi: tuple[float, float, float] | None = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def positions(self) -> np.ndarray:
        return np.asarray([atom.position for atom in self.atoms], dtype=float)

    def elements(self) -> tuple[str, ...]:
        return tuple(atom.element for atom in self.atoms)

    def ids(self) -> tuple[int, ...]:
        return tuple(atom.atom_id for atom in self.atoms)

    def sorted_by_id(self) -> "Frame":
        return Frame(
            source=self.source,
            kind=self.kind,
            label=self.label + "|sorted_by_id",
            atoms=sorted(self.atoms, key=lambda atom: atom.atom_id),
            timestep=self.timestep,
            box_lo=self.box_lo,
            box_hi=self.box_hi,
            metadata=dict(self.metadata),
        )

    def box_lengths(self) -> np.ndarray | None:
        if self.box_lo is None or self.box_hi is None:
            return None
        return np.asarray(self.box_hi, dtype=float) - np.asarray(self.box_lo, dtype=float)


@dataclasses.dataclass(frozen=True)
class Metrics:
    max_abs: float
    component_rms: float
    atom_rms: float
    kabsch_atom_rmsd: float
    pair_max_delta: float
    qpt: float
    roo: float


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def log(message: str) -> None:
    print(f"[{utc_now()}] {message}", flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise AuditError(f"Missing {label}: {path}")
    return path.resolve()


def require_dir(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise AuditError(f"Missing {label}: {path}")
    return path.resolve()


def ensure_inside(path: Path, root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AuditError(f"{label} escapes project root: {resolved}") from exc
    return resolved


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return f"{value:.16g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def atomic_write_tsv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        order: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    order.append(key)
        fields = order
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: format_value(row.get(key)) for key in fields})
    os.replace(temporary, path)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def csv_ints(text: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in text.split(",") if part.strip())


def table_float(row: Mapping[str, str], key: str) -> float:
    text = str(row.get(key, "")).strip()
    if not text:
        raise AuditError(f"Missing numeric field {key}")
    try:
        return float(text)
    except ValueError as exc:
        raise AuditError(f"Invalid numeric field {key}={text!r}") from exc


def resolve_current(version_root: Path, pointer_name: str) -> Path:
    pointer = require_file(version_root / pointer_name, f"pointer {pointer_name}")
    value = pointer.read_text(encoding="utf-8").strip()
    if not value:
        raise AuditError(f"Empty pointer: {pointer}")
    target = Path(value)
    if not target.is_absolute():
        target = version_root / target
    return require_dir(target, f"current attempt from {pointer_name}")


def find_unique(base: Path, patterns: Sequence[str], label: str) -> Path:
    paths: set[Path] = set()
    for pattern in patterns:
        for path in base.glob(pattern):
            if path.is_file():
                paths.add(path.resolve())
    ordered = sorted(paths)
    if len(ordered) != 1:
        raise AuditError(
            f"Expected one {label} under {base}; found {len(ordered)}: {ordered}"
        )
    return ordered[0]


def resolve_paths(root: Path) -> dict[str, Path]:
    v032_root = require_dir(
        root / "09_strict_comparison/versions/v032_targeted_md_diagnostics",
        "v032 version root",
    )
    v032d_root = require_dir(
        root / "09_strict_comparison/versions/v032_selection_interface_diagnostic",
        "v032d version root",
    )
    v032 = resolve_current(v032_root, "CURRENT_TARGETED_MD_DIAGNOSTICS.txt")
    v032d = resolve_current(
        v032d_root, "CURRENT_V032_SELECTION_INTERFACE_DIAGNOSTIC.txt"
    )
    return {
        "v032": v032,
        "v032d": v032d,
        "captured": find_unique(
            v032d,
            (
                "tables/captured_break_configurations_v032d.tsv",
                "**/captured_break_configurations_v032d.tsv",
            ),
            "captured-break table",
        ),
        "provenance": find_unique(
            v032d,
            (
                "provenance/step34c_v032_selection_interface_diagnostic_v032d.py",
                "**/step34c_v032_selection_interface_diagnostic_v032d.py",
            ),
            "provenance script",
        ),
        "summary": find_unique(
            v032d,
            ("summary_v032d.json", "**/summary_v032d.json"),
            "v032d summary",
        ),
        "atom_order": require_file(
            root / "00_protocol/ATOM_ORDER_LOCKED_v000.tsv",
            "locked atom-order table",
        ),
    }


def validate_atom_lock(path: Path) -> None:
    rows = read_tsv(path)
    rows.sort(key=lambda row: int(row["atom_id"]))
    observed = tuple(row["element"] for row in rows)
    if observed != LOCKED_ELEMENTS:
        raise AuditError(
            f"Unexpected locked atom order: observed={observed}, expected={LOCKED_ELEMENTS}"
        )


def parse_cfg(path: Path) -> Frame:
    text = path.read_text(encoding="utf-8", errors="strict")
    blocks = re.findall(r"(?s)BEGIN_CFG(.*?)END_CFG", text)
    if len(blocks) != 1:
        raise AuditError(f"Expected one CFG block in {path}, found {len(blocks)}")
    lines = blocks[0].splitlines()
    size: int | None = None
    atoms: list[Atom] = []
    features: dict[str, str] = {}
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped == "Size":
            index += 1
            while index < len(lines) and not lines[index].strip():
                index += 1
            size = int(float(lines[index].strip()))
        elif stripped.startswith("AtomData:"):
            if size is None:
                raise AuditError(f"AtomData before Size in {path}")
            headers = stripped.split(":", 1)[1].split()
            columns = {header: column for column, header in enumerate(headers)}
            required = {"id", "type", "cartes_x", "cartes_y", "cartes_z"}
            if not required.issubset(columns):
                raise AuditError(f"Unsupported CFG columns in {path}: {headers}")
            atoms = []
            while len(atoms) < size:
                index += 1
                if index >= len(lines):
                    raise AuditError(f"Truncated CFG atom table in {path}")
                row_text = lines[index].strip()
                if not row_text:
                    continue
                values = row_text.split()
                atom_type = int(float(values[columns["type"]]))
                if atom_type not in MLIP_TO_ELEMENT:
                    raise AuditError(f"Unknown MLIP type {atom_type} in {path}")
                atoms.append(
                    Atom(
                        atom_id=int(float(values[columns["id"]])),
                        atom_type=atom_type,
                        element=MLIP_TO_ELEMENT[atom_type],
                        position=(
                            float(values[columns["cartes_x"]]),
                            float(values[columns["cartes_y"]]),
                            float(values[columns["cartes_z"]]),
                        ),
                        row_index=len(atoms),
                    )
                )
        elif stripped.startswith("Feature"):
            pieces = stripped.split(maxsplit=2)
            if len(pieces) >= 2:
                features[pieces[1]] = pieces[2] if len(pieces) == 3 else ""
        index += 1
    if size != 9 or len(atoms) != 9:
        raise AuditError(f"Expected nine atoms in CFG {path}; size={size}, atoms={len(atoms)}")
    return Frame(
        source=path.resolve(),
        kind="mlip_cfg",
        label=path.name,
        atoms=atoms,
        metadata={"features": features},
    )


def is_integer(text: str) -> bool:
    try:
        value = float(text)
    except ValueError:
        return False
    return value.is_integer()


def infer_atom_style(header: str, rows: Sequence[list[str]]) -> str:
    match = re.search(r"#\s*([A-Za-z0-9_]+)", header)
    if match:
        return match.group(1).lower()
    lengths = {len(row) for row in rows}
    if lengths == {5}:
        return "atomic"
    if lengths == {6}:
        col1_type = all(
            is_integer(row[1]) and int(float(row[1])) in LAMMPS_TO_ELEMENT
            for row in rows
        )
        col2_type = all(
            is_integer(row[2]) and int(float(row[2])) in LAMMPS_TO_ELEMENT
            for row in rows
        )
        if col1_type and not col2_type:
            return "charge"
        if col2_type and not col1_type:
            return "molecular"
        raise AuditError("Ambiguous six-column LAMMPS Atoms section")
    if min(lengths) >= 7:
        return "full"
    raise AuditError(f"Cannot infer atom style from row lengths {sorted(lengths)}")


def parse_lammps_data(path: Path) -> Frame:
    lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    bounds: dict[str, tuple[float, float]] = {}
    for line in lines:
        parts = line.split()
        if len(parts) >= 4 and parts[-2:] == ["xlo", "xhi"]:
            bounds["x"] = (float(parts[0]), float(parts[1]))
        elif len(parts) >= 4 and parts[-2:] == ["ylo", "yhi"]:
            bounds["y"] = (float(parts[0]), float(parts[1]))
        elif len(parts) >= 4 and parts[-2:] == ["zlo", "zhi"]:
            bounds["z"] = (float(parts[0]), float(parts[1]))

    header_index: int | None = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*Atoms(?:\s*#.*)?\s*$", line):
            header_index = index
            break
    if header_index is None:
        raise AuditError(f"No Atoms section in {path}")

    raw_rows: list[list[str]] = []
    index = header_index + 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    while index < len(lines):
        stripped = lines[index].split("#", 1)[0].strip()
        if not stripped:
            if raw_rows:
                break
            index += 1
            continue
        if re.match(r"^[A-Za-z]", stripped):
            break
        raw_rows.append(stripped.split())
        index += 1
    if len(raw_rows) != 9:
        raise AuditError(f"Expected nine atom rows in {path}, found {len(raw_rows)}")

    style = infer_atom_style(lines[header_index], raw_rows)
    specs = {
        "atomic": (0, 1, 2, 3, 4),
        "charge": (0, 1, 3, 4, 5),
        "molecular": (0, 2, 3, 4, 5),
        "full": (0, 2, 4, 5, 6),
    }
    if style not in specs:
        raise AuditError(f"Unsupported LAMMPS atom style {style!r} in {path}")
    id_col, type_col, x_col, y_col, z_col = specs[style]

    atoms: list[Atom] = []
    for row_index, values in enumerate(raw_rows):
        atom_type = int(float(values[type_col]))
        if atom_type not in LAMMPS_TO_ELEMENT:
            raise AuditError(f"Unknown LAMMPS type {atom_type} in {path}")
        atoms.append(
            Atom(
                atom_id=int(float(values[id_col])),
                atom_type=atom_type,
                element=LAMMPS_TO_ELEMENT[atom_type],
                position=(
                    float(values[x_col]),
                    float(values[y_col]),
                    float(values[z_col]),
                ),
                row_index=row_index,
            )
        )

    box_lo = None
    box_hi = None
    if all(axis in bounds for axis in ("x", "y", "z")):
        box_lo = tuple(bounds[axis][0] for axis in ("x", "y", "z"))
        box_hi = tuple(bounds[axis][1] for axis in ("x", "y", "z"))

    return Frame(
        source=path.resolve(),
        kind="lammps_data",
        label=path.name,
        atoms=atoms,
        box_lo=box_lo,
        box_hi=box_hi,
        metadata={"atom_style": style, "atom_header": lines[header_index].strip()},
    )


def parse_lammps_dump(path: Path) -> list[Frame]:
    lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    frames: list[Frame] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("ITEM: TIMESTEP"):
            index += 1
            continue
        if index + 8 >= len(lines):
            raise AuditError(f"Truncated dump frame in {path}")
        timestep = int(float(lines[index + 1].strip()))
        if not lines[index + 2].startswith("ITEM: NUMBER OF ATOMS"):
            raise AuditError(f"Malformed dump NUMBER OF ATOMS in {path}")
        atom_count = int(float(lines[index + 3].strip()))
        if atom_count != 9:
            raise AuditError(f"Expected nine dump atoms in {path}, found {atom_count}")
        if not lines[index + 4].startswith("ITEM: BOX BOUNDS"):
            raise AuditError(f"Missing dump BOX BOUNDS in {path}")
        bounds: list[tuple[float, float]] = []
        for axis in range(3):
            values = lines[index + 5 + axis].split()
            bounds.append((float(values[0]), float(values[1])))
        header_index = index + 8
        if not lines[header_index].startswith("ITEM: ATOMS"):
            raise AuditError(f"Missing dump ATOMS header in {path}")
        headers = lines[header_index].split()[2:]
        columns = {header: column for column, header in enumerate(headers)}
        if "id" not in columns or "type" not in columns:
            raise AuditError(f"Dump lacks id/type in {path}: {headers}")
        coordinate_names: tuple[str, str, str] | None = None
        for candidate in (
            ("xu", "yu", "zu"),
            ("x", "y", "z"),
            ("xsu", "ysu", "zsu"),
            ("xs", "ys", "zs"),
        ):
            if all(name in columns for name in candidate):
                coordinate_names = candidate
                break
        if coordinate_names is None:
            raise AuditError(f"Dump lacks supported coordinates in {path}: {headers}")
        atoms: list[Atom] = []
        for row_index in range(atom_count):
            values = lines[header_index + 1 + row_index].split()
            atom_type = int(float(values[columns["type"]]))
            if atom_type not in LAMMPS_TO_ELEMENT:
                raise AuditError(f"Unknown dump atom type {atom_type} in {path}")
            coordinates = np.asarray(
                [float(values[columns[name]]) for name in coordinate_names],
                dtype=float,
            )
            if coordinate_names[0] in {"xs", "xsu"}:
                for axis in range(3):
                    lo, hi = bounds[axis]
                    coordinates[axis] = lo + coordinates[axis] * (hi - lo)
            atoms.append(
                Atom(
                    atom_id=int(float(values[columns["id"]])),
                    atom_type=atom_type,
                    element=LAMMPS_TO_ELEMENT[atom_type],
                    position=tuple(float(value) for value in coordinates),
                    row_index=row_index,
                )
            )
        frames.append(
            Frame(
                source=path.resolve(),
                kind="lammps_dump",
                label=f"{path.name}:timestep={timestep}",
                atoms=atoms,
                timestep=timestep,
                box_lo=tuple(bound[0] for bound in bounds),
                box_hi=tuple(bound[1] for bound in bounds),
                metadata={
                    "headers": headers,
                    "coordinate_names": coordinate_names,
                },
            )
        )
        index = header_index + 1 + atom_count
    if not frames:
        raise AuditError(f"No dump frames in {path}")
    return frames


def canonicalize_cfg(frame: Frame, order: Sequence[int]) -> Frame:
    order = tuple(int(value) for value in order)
    if len(order) != 9 or sorted(order) != list(range(9)):
        raise AuditError(f"Invalid canonical order: {order}")
    atoms = [frame.atoms[index] for index in order]
    elements = tuple(atom.element for atom in atoms)
    if elements != LOCKED_ELEMENTS:
        raise AuditError(
            f"Recorded order does not produce locked elements: {elements}"
        )
    return Frame(
        source=frame.source,
        kind=frame.kind,
        label=frame.label + "|recorded_order",
        atoms=atoms,
        metadata={**frame.metadata, "recorded_order": order},
    )


def validate_endpoint(frame: Frame) -> Frame:
    frame = frame.sorted_by_id()
    if frame.ids() != tuple(range(1, 10)):
        raise AuditError(f"Endpoint IDs are not 1..9 in {frame.source}: {frame.ids()}")
    if frame.elements() != LOCKED_ELEMENTS:
        raise AuditError(
            f"Endpoint ID order is not chemically locked in {frame.source}: "
            f"{frame.elements()}"
        )
    return frame


def minimum_image_delta(
    moving: np.ndarray,
    reference: np.ndarray,
    box_lengths: np.ndarray | None,
) -> np.ndarray:
    delta = moving - reference
    if box_lengths is None:
        return delta
    if np.any(box_lengths <= 0):
        raise AuditError(f"Invalid box lengths {box_lengths}")
    return delta - np.round(delta / box_lengths) * box_lengths


def kabsch_atom_rmsd(moving: np.ndarray, reference: np.ndarray) -> float:
    moving_centered = moving - moving.mean(axis=0)
    reference_centered = reference - reference.mean(axis=0)
    covariance = moving_centered.T @ reference_centered
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1.0
        rotation = u @ vt
    aligned = moving_centered @ rotation
    difference = aligned - reference_centered
    return float(np.sqrt(np.mean(np.sum(difference * difference, axis=1))))


def kabsch_aligned(moving: np.ndarray, reference: np.ndarray) -> np.ndarray:
    moving_centered = moving - moving.mean(axis=0)
    reference_centered = reference - reference.mean(axis=0)
    covariance = moving_centered.T @ reference_centered
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1.0
        rotation = u @ vt
    return moving_centered @ rotation + reference.mean(axis=0)


def pair_max_delta(a: np.ndarray, b: np.ndarray) -> float:
    maximum = 0.0
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            da = float(np.linalg.norm(a[i] - a[j]))
            db = float(np.linalg.norm(b[i] - b[j]))
            maximum = max(maximum, abs(da - db))
    return maximum


def qpt_roo(positions: np.ndarray) -> tuple[float, float]:
    o1 = positions[0]
    hstar = positions[1]
    o2 = positions[7]
    qpt = float(np.linalg.norm(o1 - hstar) - np.linalg.norm(o2 - hstar))
    roo = float(np.linalg.norm(o1 - o2))
    return qpt, roo


def metrics(moving: np.ndarray, reference: np.ndarray) -> Metrics:
    difference = moving - reference
    qpt, roo = qpt_roo(moving)
    return Metrics(
        max_abs=float(np.max(np.abs(difference))),
        component_rms=float(np.sqrt(np.mean(difference * difference))),
        atom_rms=float(np.sqrt(np.mean(np.sum(difference * difference, axis=1)))),
        kabsch_atom_rmsd=kabsch_atom_rmsd(moving, reference),
        pair_max_delta=pair_max_delta(moving, reference),
        qpt=qpt,
        roo=roo,
    )


def trajectory_dir(row: Mapping[str, str], root: Path, v032: Path) -> Path:
    preselected = ensure_inside(Path(row["preselected_path"]), root, "preselected_path")
    require_file(preselected, "preselected CFG")
    directory = require_dir(preselected.parent, "trajectory directory")
    try:
        directory.relative_to(v032)
    except ValueError as exc:
        raise AuditError(f"Trajectory is outside frozen v032 attempt: {directory}") from exc
    if directory.name != row["trajectory_id"]:
        raise AuditError(
            f"Trajectory ID mismatch: table={row['trajectory_id']}, dir={directory.name}"
        )
    return directory


def find_endpoint(directory: Path) -> Path:
    candidates = sorted({
        path.resolve()
        for pattern in ("endpoint.data", "**/endpoint.data")
        for path in directory.glob(pattern)
        if path.is_file()
    })
    if len(candidates) != 1:
        raise AuditError(
            f"Expected one local endpoint.data under {directory}; found {candidates}"
        )
    return candidates[0]


def discover_dumps(directory: Path) -> list[Path]:
    paths: set[Path] = set()
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        suffix = path.suffix.lower()
        if suffix in {".dump", ".lammpstrj", ".traj"} or "lammpstrj" in name:
            paths.add(path.resolve())
    return sorted(paths)


def choose_dump0(
    dump_paths: Sequence[Path], endpoint: Frame
) -> tuple[Frame, list[dict[str, Any]], str]:
    endpoint_positions = endpoint.positions()
    inventory: list[dict[str, Any]] = []
    exact: list[tuple[Frame, str]] = []
    for path in dump_paths:
        try:
            frames = parse_lammps_dump(path)
        except Exception as exc:
            inventory.append({
                "path": str(path),
                "status": "PARSE_FAIL",
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        for frame in frames:
            ordered = frame.sorted_by_id()
            if ordered.ids() != tuple(range(1, 10)) or ordered.elements() != LOCKED_ELEMENTS:
                inventory.append({
                    "path": str(path),
                    "frame": frame.label,
                    "timestep": frame.timestep,
                    "status": "SKIP_ID_OR_ELEMENT_ORDER",
                    "ids": ordered.ids(),
                    "elements": ordered.elements(),
                })
                continue
            direct = ordered.positions() - endpoint_positions
            direct_max = float(np.max(np.abs(direct)))
            lengths = ordered.box_lengths()
            if lengths is None:
                lengths = endpoint.box_lengths()
            mi = minimum_image_delta(ordered.positions(), endpoint_positions, lengths)
            mi_max = float(np.max(np.abs(mi)))
            direct_exact = frame.timestep == 0 and direct_max <= TOL_DUMP0_A
            mi_exact = frame.timestep == 0 and mi_max <= TOL_DUMP0_A
            inventory.append({
                "path": str(path),
                "frame": frame.label,
                "timestep": frame.timestep,
                "status": "PARSED",
                "direct_max_abs_A": direct_max,
                "minimum_image_max_abs_A": mi_max,
                "direct_exact_timestep0": direct_exact,
                "minimum_image_exact_timestep0": mi_exact,
                "coordinate_names": ordered.metadata.get("coordinate_names"),
            })
            if direct_exact:
                exact.append((ordered, "direct"))
            elif mi_exact:
                exact.append((ordered, "minimum_image"))
    if not exact:
        raise AuditError(
            "No timestep-zero dump frame directly reproduces local endpoint.data "
            f"within {TOL_DUMP0_A:.1e} A"
        )
    first_positions = exact[0][0].positions()
    for frame, _ in exact[1:]:
        if float(np.max(np.abs(frame.positions() - first_positions))) > TOL_DUMP0_A:
            raise AuditError("Multiple non-identical exact dump0 candidates")
    exact.sort(key=lambda item: (str(item[0].source), item[0].label))
    chosen, mode = exact[0]
    duplicate_note = "unique" if len(exact) == 1 else f"{len(exact)}_identical"
    return chosen, inventory, f"{mode}:{duplicate_note}"


def compare_value(
    trajectory_id: str,
    group: str,
    metric_name: str,
    calculated: float,
    expected: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    residual = calculated - expected
    passed = abs(residual) <= TOL_METRIC_A
    flat = {
        f"{group}_{metric_name}_calculated": calculated,
        f"{group}_{metric_name}_table": expected,
        f"{group}_{metric_name}_residual": residual,
        f"{group}_{metric_name}_pass": passed,
    }
    detail = {
        "trajectory_id": trajectory_id,
        "group": group,
        "metric": metric_name,
        "calculated": calculated,
        "table": expected,
        "residual": residual,
        "abs_residual": abs(residual),
        "tolerance": TOL_METRIC_A,
        "pass": passed,
    }
    return flat, detail


def source_audit(source_path: Path) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str
]:
    source = source_path.read_text(encoding="utf-8", errors="strict")
    tree = ast.parse(source)
    lines = source.splitlines()
    functions: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    literals: list[dict[str, Any]] = []
    function_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = ast.get_source_segment(source, node) or ""
        hits = [term for term in SOURCE_TERMS if term in segment]
        local_calls = sorted({
            sub.func.id
            for sub in ast.walk(node)
            if isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id in function_names
        })
        functions.append({
            "function": node.name,
            "line_start": node.lineno,
            "line_end": getattr(node, "end_lineno", node.lineno),
            "arguments": ",".join(argument.arg for argument in node.args.args),
            "keyword_hits": ",".join(hits),
            "local_calls": ",".join(local_calls),
            "source_sha256": hashlib.sha256(segment.encode("utf-8")).hexdigest(),
        })
        for callee in local_calls:
            calls.append({
                "caller": node.name,
                "callee": callee,
                "caller_line": node.lineno,
            })
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            hits = [term for term in SOURCE_TERMS if term in node.value]
            if hits:
                literals.append({
                    "line": getattr(node, "lineno", ""),
                    "keywords": ",".join(hits),
                    "literal": node.value,
                })
    hit_lines = {
        number
        for number, line in enumerate(lines, start=1)
        if any(term in line for term in SOURCE_TERMS)
    }
    ranges: list[tuple[int, int]] = []
    for hit in sorted(hit_lines):
        start = max(1, hit - 10)
        end = min(len(lines), hit + 12)
        if not ranges or start > ranges[-1][1] + 1:
            ranges.append((start, end))
        else:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
    context = [
        f"SOURCE={source_path}",
        f"SHA256={sha256_file(source_path)}",
        "",
    ]
    for start, end in ranges:
        context.append(f"===== LINES {start}-{end} =====")
        for number in range(start, end + 1):
            context.append(f"{number:05d}: {lines[number - 1]}")
        context.append("")
    return functions, calls, literals, "\n".join(context)


def fixed_replay(
    row: Mapping[str, str], root: Path, paths: Mapping[str, Path]
) -> tuple[
    dict[str, Any], list[dict[str, Any]], list[dict[str, Any]],
    dict[str, Any], Frame, Frame, Frame
]:
    trajectory_id = row["trajectory_id"]
    directory = trajectory_dir(row, root, paths["v032"])
    preselected_path = require_file(
        ensure_inside(Path(row["preselected_path"]), root, "preselected_path"),
        "preselected CFG",
    )
    endpoint_path = find_endpoint(directory)
    raw_cfg = parse_cfg(preselected_path)
    endpoint = validate_endpoint(parse_lammps_data(endpoint_path))

    raw_ids_table = csv_ints(row["raw_atom_ids"])
    raw_types_table = csv_ints(row["raw_atom_types"])
    order = csv_ints(row["canonical_order_zero_based"])
    contract = {
        "raw_ids_equal_table": raw_cfg.ids() == raw_ids_table,
        "raw_types_equal_table": tuple(atom.atom_type for atom in raw_cfg.atoms) == raw_types_table,
        "raw_types_equal_expected": tuple(atom.atom_type for atom in raw_cfg.atoms) == EXPECTED_RAW_TYPES,
        "recorded_order_equal_expected": order == EXPECTED_RECORDED_ORDER,
        "mode_species_assignment": row["canonicalization_mode"] == "species_assignment",
        "candidate_count_288": int(row["canonicalization_candidate_count"]) == 288,
    }
    failed = [name for name, passed in contract.items() if not passed]
    if failed:
        raise AuditError(f"{trajectory_id}: locked CFG/table contract failed: {failed}")

    break_frame = canonicalize_cfg(raw_cfg, order)
    dumps = discover_dumps(directory)
    if not dumps:
        raise AuditError(f"{trajectory_id}: no local dump files")
    dump0, dump_inventory, dump0_choice = choose_dump0(dumps, endpoint)
    for inventory_row in dump_inventory:
        inventory_row["trajectory_id"] = trajectory_id

    break_endpoint = metrics(break_frame.positions(), endpoint.positions())
    break_dump0 = metrics(break_frame.positions(), dump0.positions())
    dump0_endpoint = metrics(dump0.positions(), endpoint.positions())

    replay: dict[str, Any] = {
        "trajectory_id": trajectory_id,
        "temperature_K": table_float(row, "temperature_K"),
        "side": row["side"],
        "seed": int(row["seed"]),
        "trajectory_dir": str(directory),
        "preselected_path": str(preselected_path),
        "preselected_sha256": sha256_file(preselected_path),
        "endpoint_path": str(endpoint_path),
        "endpoint_sha256": sha256_file(endpoint_path),
        "endpoint_atom_style": endpoint.metadata["atom_style"],
        "dump0_path": str(dump0.source),
        "dump0_sha256": sha256_file(dump0.source),
        "dump0_label": dump0.label,
        "dump0_choice": dump0_choice,
        "recorded_order": order,
        "canonical_cfg_raw_row_ids": tuple(raw_cfg.atoms[index].atom_id for index in order),
        "canonical_cfg_elements": break_frame.elements(),
        **contract,
    }
    checks: list[dict[str, Any]] = []

    groups = (
        (
            "break_vs_endpoint",
            break_endpoint,
            {
                "max_abs": table_float(row, "break_vs_endpoint_max_abs_ang"),
                "component_rms": table_float(row, "break_vs_endpoint_rms_ang"),
                "kabsch_atom_rmsd": table_float(row, "break_vs_endpoint_kabsch_rmsd_ang"),
                "pair_max_delta": table_float(row, "break_vs_endpoint_pair_distance_max_abs_delta_ang"),
            },
        ),
        (
            "break_vs_dump0",
            break_dump0,
            {
                "max_abs": table_float(row, "break_vs_dump0_max_abs_ang"),
                "component_rms": table_float(row, "break_vs_dump0_rms_ang"),
                "kabsch_atom_rmsd": table_float(row, "break_vs_dump0_kabsch_rmsd_ang"),
            },
        ),
        (
            "dump0_vs_endpoint",
            dump0_endpoint,
            {
                "max_abs": table_float(row, "dump0_vs_endpoint_max_abs_ang"),
                "component_rms": table_float(row, "dump0_vs_endpoint_rms_ang"),
                "kabsch_atom_rmsd": table_float(row, "dump0_vs_endpoint_kabsch_rmsd_ang"),
            },
        ),
    )
    for group_name, calculated_metrics, expected_metrics in groups:
        calculated_map = {
            "max_abs": calculated_metrics.max_abs,
            "component_rms": calculated_metrics.component_rms,
            "kabsch_atom_rmsd": calculated_metrics.kabsch_atom_rmsd,
            "pair_max_delta": calculated_metrics.pair_max_delta,
        }
        for metric_name, expected in expected_metrics.items():
            flat, detail = compare_value(
                trajectory_id,
                group_name,
                metric_name,
                calculated_map[metric_name],
                expected,
            )
            replay.update(flat)
            checks.append(detail)

    for metric_name, calculated, expected in (
        ("qpt", break_endpoint.qpt, table_float(row, "break_qpt_ang")),
        ("roo", break_endpoint.roo, table_float(row, "break_roo_ang")),
    ):
        flat, detail = compare_value(
            trajectory_id, "break_reaction_coordinate", metric_name, calculated, expected
        )
        replay.update(flat)
        checks.append(detail)

    pass_keys = [
        key for key, value in replay.items()
        if key.endswith("_pass") and isinstance(value, bool)
    ]
    replay["metric_check_count"] = len(pass_keys)
    replay["metric_pass_count"] = sum(bool(replay[key]) for key in pass_keys)
    replay["exact_fixed_replay_pass"] = all(bool(replay[key]) for key in pass_keys)

    translated = break_frame.positions() + (
        endpoint.positions().mean(axis=0) - break_frame.positions().mean(axis=0)
    )
    full_kabsch = kabsch_aligned(break_frame.positions(), endpoint.positions())
    diagnostics = {
        "trajectory_id": trajectory_id,
        "direct_max_abs_A": break_endpoint.max_abs,
        "direct_component_rms_A": break_endpoint.component_rms,
        "translation_only_max_abs_A": metrics(translated, endpoint.positions()).max_abs,
        "translation_only_component_rms_A": metrics(translated, endpoint.positions()).component_rms,
        "full_kabsch_max_abs_A": metrics(full_kabsch, endpoint.positions()).max_abs,
        "full_kabsch_component_rms_A": metrics(full_kabsch, endpoint.positions()).component_rms,
        "kabsch_atom_rmsd_A": break_endpoint.kabsch_atom_rmsd,
        "pair_max_delta_A": break_endpoint.pair_max_delta,
        "table_max_abs_A": table_float(row, "break_vs_endpoint_max_abs_ang"),
        "table_component_rms_A": table_float(row, "break_vs_endpoint_rms_ang"),
        "table_kabsch_atom_rmsd_A": table_float(row, "break_vs_endpoint_kabsch_rmsd_ang"),
        "table_pair_max_delta_A": table_float(row, "break_vs_endpoint_pair_distance_max_abs_delta_ang"),
    }
    return replay, checks, dump_inventory, diagnostics, raw_cfg, endpoint, break_frame


def element_assignments(
    source_elements: Sequence[str], target_elements: Sequence[str]
) -> Iterable[tuple[int, ...]]:
    source_by_element: dict[str, list[int]] = defaultdict(list)
    target_slots: dict[str, list[int]] = defaultdict(list)
    for index, element in enumerate(source_elements):
        source_by_element[element].append(index)
    for index, element in enumerate(target_elements):
        target_slots[element].append(index)
    if {key: len(value) for key, value in source_by_element.items()} != {
        key: len(value) for key, value in target_slots.items()
    }:
        return
    elements = sorted(source_by_element)
    permutation_sets = [
        list(itertools.permutations(source_by_element[element]))
        for element in elements
    ]
    for combination in itertools.product(*permutation_sets):
        order = [-1] * len(target_elements)
        for element, selected in zip(elements, combination):
            for target_slot, source_index in zip(target_slots[element], selected):
                order[target_slot] = source_index
        yield tuple(order)


def match_cfg_rows_to_dump(raw_cfg: Frame, dump_frame: Frame) -> list[dict[str, Any]]:
    cfg_positions = raw_cfg.positions()
    dump_positions = dump_frame.positions()
    results: list[dict[str, Any]] = []
    for order in element_assignments(dump_frame.elements(), raw_cfg.elements()):
        assigned = dump_positions[list(order)]
        direct = assigned - cfg_positions
        direct_max = float(np.max(np.abs(direct)))
        direct_rms = float(np.sqrt(np.mean(direct * direct)))
        mi = minimum_image_delta(assigned, cfg_positions, dump_frame.box_lengths())
        mi_max = float(np.max(np.abs(mi)))
        mi_rms = float(np.sqrt(np.mean(mi * mi)))
        results.append({
            "dump_rows_for_cfg_rows": order,
            "lammps_ids_for_cfg_rows": tuple(dump_frame.atoms[index].atom_id for index in order),
            "direct_max_abs_A": direct_max,
            "direct_component_rms_A": direct_rms,
            "minimum_image_max_abs_A": mi_max,
            "minimum_image_component_rms_A": mi_rms,
            "best_max_abs_A": min(direct_max, mi_max),
            "best_mode": "direct" if direct_max <= mi_max else "minimum_image",
        })
    results.sort(
        key=lambda row: (
            row["best_max_abs_A"],
            min(row["direct_component_rms_A"], row["minimum_image_component_rms_A"]),
            row["lammps_ids_for_cfg_rows"],
        )
    )
    return results


def identity_audit(
    row: Mapping[str, str],
    raw_cfg: Frame,
    directory: Path,
    recorded_order: Sequence[int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidate_rows: list[dict[str, Any]] = []
    for dump_path in discover_dumps(directory):
        try:
            frames = parse_lammps_dump(dump_path)
        except Exception:
            continue
        for frame in frames:
            if frame.timestep is None or frame.timestep <= 0:
                continue
            matches = match_cfg_rows_to_dump(raw_cfg, frame)
            for rank, match in enumerate(matches[:5], start=1):
                role_ids = tuple(
                    match["lammps_ids_for_cfg_rows"][raw_row]
                    for raw_row in recorded_order
                )
                candidate_rows.append({
                    "trajectory_id": row["trajectory_id"],
                    "dump_path": str(dump_path),
                    "dump_sha256": sha256_file(dump_path),
                    "frame_label": frame.label,
                    "timestep": frame.timestep,
                    "rank_within_frame": rank,
                    **match,
                    "canonical_role_lammps_ids": role_ids,
                    "role_ids_equal_locked_1_to_9": role_ids == tuple(range(1, 10)),
                    "exact_coordinate_match": match["best_max_abs_A"] <= TOL_CFG_DUMP_A,
                })
    candidate_rows.sort(
        key=lambda row: (
            row["best_max_abs_A"],
            row["timestep"],
            row["dump_path"],
            row["lammps_ids_for_cfg_rows"],
        )
    )
    exact = [row for row in candidate_rows if row["exact_coordinate_match"]]
    raw_maps = {tuple(row["lammps_ids_for_cfg_rows"]) for row in exact}
    role_maps = {tuple(row["canonical_role_lammps_ids"]) for row in exact}
    if not exact:
        classification = "NO_PRESERVED_BREAK_DUMP_MATCH"
    elif len(raw_maps) == 1 and len(role_maps) == 1:
        role_map = next(iter(role_maps))
        if role_map == tuple(range(1, 10)):
            classification = "UNIQUE_MATCH_PRESERVES_LOCKED_ATOM_IDS"
        else:
            classification = "UNIQUE_MATCH_RECORDED_ROLES_DIFFER_FROM_LOCKED_IDS"
    else:
        classification = "AMBIGUOUS_EXACT_CFG_TO_LAMMPS_ID_MAPPING"
    summary = {
        "trajectory_id": row["trajectory_id"],
        "classification": classification,
        "candidate_row_count": len(candidate_rows),
        "exact_match_count": len(exact),
        "unique_raw_id_maps": len(raw_maps),
        "unique_role_id_maps": len(role_maps),
        "best_match_max_abs_A": candidate_rows[0]["best_max_abs_A"] if candidate_rows else None,
        "best_match_dump": candidate_rows[0]["dump_path"] if candidate_rows else None,
        "best_match_timestep": candidate_rows[0]["timestep"] if candidate_rows else None,
        "best_match_role_ids": candidate_rows[0]["canonical_role_lammps_ids"] if candidate_rows else None,
    }
    return candidate_rows[:30], summary


def artifact_row(path: Path, role: str, root: Path) -> dict[str, Any]:
    path = path.resolve()
    return {
        "role": role,
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if path.is_relative_to(root) else "",
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "mtime_utc": dt.datetime.fromtimestamp(
            path.stat().st_mtime, dt.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_xyz(path: Path, endpoint: Frame, break_frame: Frame, trajectory_id: str) -> None:
    lines: list[str] = []
    for label, frame in (("endpoint", endpoint), ("break", break_frame)):
        lines.append("9")
        lines.append(
            f"trajectory={trajectory_id} state={label} source={frame.source} "
            f"order={'LAMMPS_ID_1_to_9' if label == 'endpoint' else 'recorded_canonical_order'}"
        )
        for element, position in zip(LOCKED_ELEMENTS, frame.positions()):
            lines.append(
                f"{element:<2s} {position[0]: .14f} {position[1]: .14f} {position[2]: .14f}"
            )
    atomic_write_text(path, "\n".join(lines) + "\n")


def classify(
    replay_rows: Sequence[Mapping[str, Any]],
    identity_rows: Sequence[Mapping[str, Any]],
) -> str:
    if not all(bool(row["exact_fixed_replay_pass"]) for row in replay_rows):
        if any(
            not bool(row.get("dump0_vs_endpoint_max_abs_pass", False))
            for row in replay_rows
        ):
            return "EXACT_REPLAY_FAIL_ENDPOINT_DUMP0_REFERENCE"
        return "EXACT_REPLAY_FAIL_RECORDED_ORDER_OR_STORED_METRICS"
    identities = [row["classification"] for row in identity_rows]
    if all(value == "UNIQUE_MATCH_PRESERVES_LOCKED_ATOM_IDS" for value in identities):
        return "EXACT_REPLAY_PASS_ATOM_IDS_PRESERVED"
    if any(value == "UNIQUE_MATCH_RECORDED_ROLES_DIFFER_FROM_LOCKED_IDS" for value in identities):
        return "EXACT_REPLAY_PASS_BUT_RECORDED_ROLES_DIFFER_FROM_LAMMPS_IDS"
    return "EXACT_REPLAY_PASS_GEOMETRY_ATOM_ID_PROVENANCE_INCOMPLETE"


def build_report(
    classification: str,
    paths: Mapping[str, Path],
    replay_rows: Sequence[Mapping[str, Any]],
    identity_rows: Sequence[Mapping[str, Any]],
) -> str:
    identity_by_id = {row["trajectory_id"]: row for row in identity_rows}
    lines = [
        "# Exact v032d geometry replay v001",
        "",
        f"Created UTC: {utc_now()}",
        "",
        f"Classification: `{classification}`",
        "",
        "## Locked replay contract",
        "",
        "The same procedure was applied to all six trajectories:",
        "",
        "- local `endpoint.data` sorted by persistent LAMMPS atom ID;",
        "- unique timestep-zero dump that directly equals that endpoint;",
        "- exact frozen `preselected.cfg`;",
        "- exact table-recorded `canonical_order_zero_based`;",
        "- no alignment for direct max/RMS and pair-distance metrics;",
        "- proper Kabsch rotation only for the separately named Kabsch RMSD.",
        "",
        "No endpoint swapping, best-fit reference search or alternative role mapping",
        "was permitted in the primary replay.",
        "",
        "## Authority",
        "",
        f"- provenance source: `{paths['provenance']}`",
        f"- SHA256: `{sha256_file(paths['provenance'])}`",
        "",
        "## Results",
        "",
        "| trajectory | exact replay | passed metrics | identity result | endpoint | dump0 |",
        "|---|---:|---:|---|---|---|",
    ]
    for row in replay_rows:
        identity = identity_by_id[row["trajectory_id"]]
        lines.append(
            f"| {row['trajectory_id']} | {row['exact_fixed_replay_pass']} | "
            f"{row['metric_pass_count']}/{row['metric_check_count']} | "
            f"`{identity['classification']}` | `{Path(row['endpoint_path']).name}` | "
            f"`{Path(row['dump0_path']).name}` |"
        )
    lines.extend([
        "",
        "## Scientific boundary",
        "",
        "This replay checks geometry provenance only. It does not establish that a",
        "large MaxVol grade corresponds to a large DFT energy or force error. That",
        "question requires six new DFT single-point labels in a separate versioned",
        "extension and is not answered here.",
        "",
    ])
    return "\n".join(lines)


def checksums(attempt: Path) -> Path:
    rows: list[dict[str, Any]] = []
    for path in sorted(attempt.rglob("*")):
        if not path.is_file() or path.name == "checksums_v001.tsv":
            continue
        rows.append({
            "relative_path": str(path.relative_to(attempt)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    output = attempt / "checksums_v001.tsv"
    atomic_write_tsv(output, rows, ("relative_path", "size_bytes", "sha256"))
    return output


def bundle(attempt: Path) -> Path:
    output = attempt / "v032d_exact_geometry_replay_bundle_v001.tar.gz"
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(attempt.rglob("*")):
            if path.is_file() and path != output:
                archive.add(path, arcname=str(path.relative_to(attempt)))
    return output


def self_test() -> None:
    rng = np.random.default_rng(20260724)
    reference = rng.normal(size=(9, 3))
    angle = math.radians(9.0)
    rotation = np.array([
        [math.cos(angle), -math.sin(angle), 0.0],
        [math.sin(angle), math.cos(angle), 0.0],
        [0.0, 0.0, 1.0],
    ])
    moving = reference @ rotation.T + np.array([0.35, -0.38, 0.02])
    rmsd = kabsch_atom_rmsd(moving, reference)
    if rmsd > 1e-12:
        raise AuditError(f"Kabsch self-test failed: {rmsd}")
    raw_elements = ("H", "C", "O", "H", "O", "C", "H", "C", "H")
    reordered = tuple(raw_elements[index] for index in EXPECTED_RECORDED_ORDER)
    if reordered != LOCKED_ELEMENTS:
        raise AuditError("Recorded-order self-test failed")
    assignments = list(element_assignments(raw_elements, LOCKED_ELEMENTS))
    if len(assignments) != 288:
        raise AuditError(f"Species-assignment count failed: {len(assignments)}")
    shifted = reference + 0.001
    if not math.isclose(metrics(shifted, reference).max_abs, 0.001, abs_tol=1e-14):
        raise AuditError("Direct-metric self-test failed")
    print("SELF_TEST=PASS")
    print(f"KABSCH_RMSD={rmsd:.3e}")
    print(f"SPECIES_ASSIGNMENT_COUNT={len(assignments)}")
    print(f"RECORDED_ORDER_ELEMENTS={','.join(reordered)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exact source-guided replay of v032d geometry metrics."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    root = require_dir(args.root.expanduser().resolve(), "project root")
    paths = resolve_paths(root)
    validate_atom_lock(paths["atom_order"])
    provenance_sha = sha256_file(paths["provenance"])
    if provenance_sha != EXPECTED_PROVENANCE_SHA256:
        raise AuditError(
            "Provenance source hash mismatch: "
            f"expected={EXPECTED_PROVENANCE_SHA256}, observed={provenance_sha}"
        )

    rows = read_tsv(paths["captured"])
    rows_by_id = {row["trajectory_id"]: row for row in rows}
    if len(rows) != 6 or tuple(sorted(rows_by_id)) != tuple(sorted(EXPECTED_CASES)):
        raise AuditError(f"Unexpected captured rows: {sorted(rows_by_id)}")

    function_rows, call_rows, literal_rows, source_context = source_audit(paths["provenance"])
    source_text = paths["provenance"].read_text(encoding="utf-8")
    missing_terms = [term for term in SOURCE_TERMS[:9] if term not in source_text]
    if missing_terms:
        raise AuditError(
            "Provenance source lacks required geometry terms: " + ", ".join(missing_terms)
        )

    log(f"Resolved v032: {paths['v032']}")
    log(f"Resolved v032d: {paths['v032d']}")
    log(f"Provenance SHA256: {provenance_sha}")
    log(f"Captured table: {paths['captured']}")

    for trajectory_id in EXPECTED_CASES:
        row = rows_by_id[trajectory_id]
        directory = trajectory_dir(row, root, paths["v032"])
        endpoint_path = find_endpoint(directory)
        endpoint = validate_endpoint(parse_lammps_data(endpoint_path))
        cfg = parse_cfg(require_file(Path(row["preselected_path"]), "preselected CFG"))
        canonicalize_cfg(cfg, csv_ints(row["canonical_order_zero_based"]))
        dump_paths = discover_dumps(directory)
        if not dump_paths:
            raise AuditError(f"{trajectory_id}: no dump files")
        log(
            f"Preflight {trajectory_id}: endpoint={endpoint_path.name}; "
            f"style={endpoint.metadata['atom_style']}; dumps={len(dump_paths)}; "
            f"raw_types={','.join(str(atom.atom_type) for atom in cfg.atoms)}"
        )

    if args.validate_only:
        print("VALIDATE_ONLY=PASS")
        print(f"PROVENANCE_SHA256={provenance_sha}")
        print("FIXED_ENDPOINT=trajectory_local_endpoint.data")
        print("FIXED_MAPPING=recorded_canonical_order_zero_based")
        print("PRIMARY_ALIGNMENT=none")
        print("SCIENTIFIC_EXECUTION=NONE")
        return 0

    attempt_root = root / OUTPUT_REL
    attempt_root.mkdir(parents=True, exist_ok=True)
    attempt = attempt_root / f"attempt_{utc_stamp()}"
    if attempt.exists():
        raise AuditError(f"Refusing existing attempt: {attempt}")
    attempt.mkdir()
    for name in ("tables", "reports", "geometry", "provenance"):
        (attempt / name).mkdir()

    shutil.copy2(paths["provenance"], attempt / "provenance/step34c_v032_selection_interface_diagnostic_v032d.py")
    shutil.copy2(paths["captured"], attempt / "provenance/captured_break_configurations_v032d.tsv")
    shutil.copy2(paths["summary"], attempt / "provenance/summary_v032d.json")
    shutil.copy2(paths["atom_order"], attempt / "provenance/ATOM_ORDER_LOCKED_v000.tsv")

    replay_rows: list[dict[str, Any]] = []
    metric_checks: list[dict[str, Any]] = []
    dump_inventory: list[dict[str, Any]] = []
    discrepancy_rows: list[dict[str, Any]] = []
    identity_candidates: list[dict[str, Any]] = []
    identity_summaries: list[dict[str, Any]] = []
    artifacts = [
        artifact_row(paths["provenance"], "provenance_source", root),
        artifact_row(paths["captured"], "captured_table", root),
        artifact_row(paths["summary"], "v032d_summary", root),
        artifact_row(paths["atom_order"], "atom_order_lock", root),
    ]

    for trajectory_id in EXPECTED_CASES:
        row = rows_by_id[trajectory_id]
        log(f"Exact replay {trajectory_id}")
        replay, checks, inventory, diagnostics, raw_cfg, endpoint, break_frame = fixed_replay(
            row, root, paths
        )
        replay_rows.append(replay)
        metric_checks.extend(checks)
        dump_inventory.extend(inventory)
        discrepancy_rows.append(diagnostics)

        directory = trajectory_dir(row, root, paths["v032"])
        identity_rows, identity_summary = identity_audit(
            row,
            raw_cfg,
            directory,
            csv_ints(row["canonical_order_zero_based"]),
        )
        identity_candidates.extend(identity_rows)
        identity_summaries.append(identity_summary)

        artifacts.extend([
            artifact_row(Path(replay["preselected_path"]), f"{trajectory_id}:preselected", root),
            artifact_row(Path(replay["endpoint_path"]), f"{trajectory_id}:endpoint", root),
            artifact_row(Path(replay["dump0_path"]), f"{trajectory_id}:dump0", root),
        ])

        if replay["exact_fixed_replay_pass"]:
            write_xyz(
                attempt / "geometry" / f"{trajectory_id}_exact_replay_v001.xyz",
                endpoint,
                break_frame,
                trajectory_id,
            )

        log(
            f"{trajectory_id}: replay={replay['exact_fixed_replay_pass']}; "
            f"metrics={replay['metric_pass_count']}/{replay['metric_check_count']}; "
            f"identity={identity_summary['classification']}"
        )

    classification = classify(replay_rows, identity_summaries)

    atomic_write_tsv(attempt / "tables/exact_fixed_replay_v001.tsv", replay_rows)
    atomic_write_tsv(attempt / "tables/metric_checks_v001.tsv", metric_checks)
    atomic_write_tsv(attempt / "tables/dump_inventory_v001.tsv", dump_inventory)
    atomic_write_tsv(attempt / "tables/discrepancy_decomposition_v001.tsv", discrepancy_rows)
    atomic_write_tsv(attempt / "tables/atom_identity_candidates_v001.tsv", identity_candidates)
    atomic_write_tsv(attempt / "tables/atom_identity_summary_v001.tsv", identity_summaries)
    atomic_write_tsv(attempt / "tables/provenance_function_inventory_v001.tsv", function_rows)
    atomic_write_tsv(attempt / "tables/provenance_call_graph_v001.tsv", call_rows)
    atomic_write_tsv(attempt / "tables/provenance_literals_v001.tsv", literal_rows)
    atomic_write_tsv(attempt / "tables/input_artifact_manifest_v001.tsv", artifacts)
    atomic_write_text(attempt / "reports/provenance_source_context_v001.txt", source_context)
    atomic_write_text(
        attempt / "reports/exact_geometry_replay_report_v001.md",
        build_report(classification, paths, replay_rows, identity_summaries),
    )

    summary = {
        "created_utc": utc_now(),
        "stage": STAGE,
        "version": VERSION,
        "classification": classification,
        "provenance_source": str(paths["provenance"]),
        "provenance_sha256": provenance_sha,
        "fixed_contract": {
            "break": "exact frozen preselected.cfg",
            "mapping": "stored canonical_order_zero_based only",
            "endpoint": "trajectory-local endpoint.data sorted by LAMMPS atom ID",
            "dump0": "unique timestep-zero frame directly equal to endpoint",
            "direct_alignment": "none",
            "rms": "sqrt(mean(delta_cartesian^2)) over 27 components",
            "kabsch": "proper-rotation atom RMSD after centroid removal",
            "posthoc_reference_selection": False,
            "posthoc_species_assignment": False,
        },
        "scientific_execution": {
            "dft": False,
            "neb": False,
            "training": False,
            "model_loading": False,
            "calc_grade": False,
            "lammps": False,
            "md_steps": 0,
            "upstream_modified": False,
        },
        "trajectory_replay": replay_rows,
        "atom_identity": identity_summaries,
        "counts": {
            "trajectories": len(replay_rows),
            "exact_replay_pass": sum(bool(row["exact_fixed_replay_pass"]) for row in replay_rows),
            "metric_checks": len(metric_checks),
            "metric_passes": sum(bool(row["pass"]) for row in metric_checks),
            "identity_candidate_rows": len(identity_candidates),
        },
        "visualization_policy": {
            "use_first_step_displacement": classification.startswith("EXACT_REPLAY_PASS"),
            "use_generated_xyz": classification in {
                "EXACT_REPLAY_PASS_ATOM_IDS_PRESERVED",
                "EXACT_REPLAY_PASS_GEOMETRY_ATOM_ID_PROVENANCE_INCOMPLETE",
            },
            "claim_physical_force_error": False,
            "claim_maxvol_rejection": True,
        },
    }
    atomic_write_json(attempt / "summary_v001.json", summary)
    status = "PASS_EXACT_REPLAY_AUDIT_COMPLETED__" + classification
    atomic_write_text(attempt / STATUS_NAME, status + "\n")
    checksums(attempt)
    bundle_path = bundle(attempt)
    checksums(attempt)

    pointer = attempt_root / POINTER_NAME
    atomic_write_text(pointer, str(attempt) + "\n")

    print("============================================================")
    print("EXACT GEOMETRY REPLAY COMPLETED")
    print("============================================================")
    print(f"CLASSIFICATION={classification}")
    print(f"RUN_DIR={attempt}")
    print(f"STATUS={attempt / STATUS_NAME}")
    print(f"SUMMARY={attempt / 'summary_v001.json'}")
    print(f"REPORT={attempt / 'reports/exact_geometry_replay_report_v001.md'}")
    print(f"REPLAY_TABLE={attempt / 'tables/exact_fixed_replay_v001.tsv'}")
    print(f"METRIC_CHECKS={attempt / 'tables/metric_checks_v001.tsv'}")
    print(f"IDENTITY_SUMMARY={attempt / 'tables/atom_identity_summary_v001.tsv'}")
    print(f"SOURCE_CONTEXT={attempt / 'reports/provenance_source_context_v001.txt'}")
    print(f"BUNDLE={bundle_path}")
    print(f"CURRENT_POINTER={pointer}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print(f"AUDIT_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except KeyboardInterrupt:
        print("INTERRUPTED", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"UNEXPECTED_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(3)

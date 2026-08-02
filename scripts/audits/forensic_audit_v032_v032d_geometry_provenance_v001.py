#!/usr/bin/env python3
"""
Read-only forensic audit of v032/v032d geometry provenance.

Purpose
-------
Determine exactly how the six MLIP preselected.cfg configurations were mapped
to chemical atom identities and compared with endpoint/dump0 geometries in
v032d. The audit does not run DFT, MD, LAMMPS integration, model training, or
modify any upstream artifact.

The script deliberately tests multiple hypotheses instead of assuming one:
- raw CFG row order versus atom-ID-sorted order;
- the recorded permutation and its inverse;
- all 288 species-constrained atom assignments;
- global DFT endpoints, trajectory-local endpoint.data files, trajectory dumps,
  and v032d run-0 endpoint/dump files;
- no alignment, translation-only alignment, proper Kabsch alignment,
  mass-weighted Kabsch alignment, and reflection-allowing alignment;
- component RMS versus atom-vector RMS conventions;
- optional minimum-image reconciliation when box data are available.

A completed audit exits successfully even when the scientific result is
unresolved. Structural/integrity errors exit non-zero. The scientific
classification is written into summary_v001.json and STATUS_v032e.txt.
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
from typing import Any, Iterable, Iterator, Mapping, Sequence

try:
    import numpy as np
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "NumPy is required for the forensic geometry audit. "
        f"Import failed: {type(exc).__name__}: {exc}"
    )

SCRIPT_VERSION = "v001"
STAGE_NAME = "v032e_geometry_provenance_forensic_audit"
OUTPUT_REL = Path("09_strict_comparison/versions") / STAGE_NAME
CURRENT_POINTER_NAME = "CURRENT_V032D_GEOMETRY_FORENSIC_AUDIT.txt"
STATUS_NAME = "STATUS_v032e.txt"

DEFAULT_ROOT = Path("${PROJECT_ROOT}")
V032_REL = Path("09_strict_comparison/versions/v032_targeted_md_diagnostics")
V032D_REL = Path("09_strict_comparison/versions/v032_selection_interface_diagnostic")

EXPECTED_CASES = {
    "T100_left", "T100_right",
    "T300_left", "T300_right",
    "T500_left", "T500_right",
}

MLIP_TYPE_TO_ELEMENT = {0: "C", 1: "H", 2: "O"}
LAMMPS_TYPE_TO_ELEMENT = {1: "C", 2: "H", 3: "O"}
ATOMIC_MASS = {"H": 1.008, "C": 12.011, "O": 15.999}

GEOMETRY_SUFFIXES = {".cfg", ".xyz", ".data", ".dump", ".lammpstrj", ".traj"}
GEOMETRY_NAME_HINTS = (
    "endpoint", "dump", "traj", "frame", "initial", "start",
    "preselected", "selected", "run0", "break",
)

KEYWORDS = (
    "kabsch", "canonical", "species_assignment", "permutation", "assignment",
    "break_vs_endpoint", "break_vs_dump0", "dump0_vs_endpoint",
    "max_abs", "pair_distance", "rms", "preselected", "endpoint.data",
    "lammpstrj", "calc-grade",
)


class AuditError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Atom:
    atom_id: int
    atom_type: int | None
    element: str
    position: tuple[float, float, float]
    row_index: int


@dataclasses.dataclass
class GeometryFrame:
    source_path: Path
    source_kind: str
    frame_index: int
    label: str
    atoms: list[Atom]
    box_lengths: tuple[float, float, float] | None = None
    timestep: int | None = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def positions_row(self) -> np.ndarray:
        return np.asarray([atom.position for atom in self.atoms], dtype=float)

    def elements_row(self) -> list[str]:
        return [atom.element for atom in self.atoms]

    def ids_row(self) -> list[int]:
        return [atom.atom_id for atom in self.atoms]


@dataclasses.dataclass(frozen=True)
class MappingCandidate:
    name: str
    indices: tuple[int, ...]
    origin: str


@dataclasses.dataclass
class AlignmentResult:
    method: str
    aligned: np.ndarray
    translation: np.ndarray
    rotation: np.ndarray
    determinant: float
    rotation_angle_deg: float
    max_abs: float
    component_rms: float
    atom_rms: float
    pair_max_delta: float
    raw_max_abs: float
    qpt: float
    roo: float


@dataclasses.dataclass
class ReconstructionCandidate:
    trajectory_id: str
    reference_label: str
    reference_path: str
    reference_kind: str
    reference_frame_index: int
    reference_mapping: str
    break_mapping: str
    break_mapping_origin: str
    alignment_method: str
    rms_definition: str
    metric_prefix: str
    score: float
    max_normalized_residual: float
    exact: bool
    near: bool
    computed_max_abs: float
    table_max_abs: float | None
    computed_rms: float
    table_rms: float | None
    computed_pair_delta: float
    table_pair_delta: float | None
    computed_kabsch_rms: float | None
    table_kabsch_rms: float | None
    qpt: float
    table_qpt: float | None
    roo: float
    table_roo: float | None
    raw_max_abs: float
    atom_rms: float
    component_rms: float
    rotation_angle_deg: float
    rotation_det: float
    break_mapping_indices: str
    reference_mapping_indices: str
    notes: str


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def log(message: str) -> None:
    print(f"[{utc_now()}] {message}", flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def atomic_write_tsv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        fields = ordered
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: format_tsv_value(row.get(key, "")) for key in fields})
    os.replace(tmp, path)


def format_tsv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return f"{value:.15g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise AuditError(f"Missing required {label}: {path}")
    return path.resolve()


def require_dir(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise AuditError(f"Missing required {label}: {path}")
    return path.resolve()


def ensure_under_root(path: Path, root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AuditError(f"{label} escapes project root: {resolved}") from exc
    return resolved


def resolve_current(version_root: Path, pointer_name: str) -> Path:
    pointer = require_file(version_root / pointer_name, f"current pointer {pointer_name}")
    target_text = pointer.read_text(encoding="utf-8").strip()
    if not target_text:
        raise AuditError(f"Empty current pointer: {pointer}")
    target = Path(target_text)
    if not target.is_absolute():
        target = version_root / target
    return require_dir(target, f"current attempt from {pointer_name}")


def find_single(base: Path, patterns: Sequence[str], label: str) -> Path:
    found: list[Path] = []
    for pattern in patterns:
        found.extend(base.glob(pattern))
    unique = sorted({p.resolve() for p in found if p.is_file()})
    if len(unique) != 1:
        raise AuditError(f"Expected exactly one {label} under {base}; found {len(unique)}: {unique}")
    return unique[0]


def load_atom_order(root: Path) -> tuple[list[str], dict[int, str], dict[int, str]]:
    path = require_file(root / "00_protocol/ATOM_ORDER_LOCKED_v000.tsv", "atom-order lock")
    rows = read_tsv(path)
    rows.sort(key=lambda row: int(row["atom_id"]))
    expected = [row["element"] for row in rows]
    mlip = {int(row["mlip_type"]): row["element"] for row in rows}
    lammps = {int(row["lammps_type"]): row["element"] for row in rows}
    if len(expected) != 9:
        raise AuditError(f"Expected 9 locked atoms, found {len(expected)}")
    return expected, mlip, lammps


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in str(value).split(",") if part.strip()]


def parse_float(value: Any) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_cfg(path: Path, mlip_map: Mapping[int, str]) -> list[GeometryFrame]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.findall(r"(?s)BEGIN_CFG(.*?)END_CFG", text)
    if not blocks:
        raise AuditError(f"No CFG blocks: {path}")
    frames: list[GeometryFrame] = []
    for frame_index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        size: int | None = None
        atoms: list[Atom] = []
        metadata: dict[str, Any] = {}
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if s == "Size":
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                size = int(float(lines[i].strip()))
            elif s.startswith("AtomData:"):
                if size is None:
                    raise AuditError(f"CFG AtomData before Size: {path}")
                header = s.split(":", 1)[1].split()
                idx = {name: j for j, name in enumerate(header)}
                required = {"id", "type", "cartes_x", "cartes_y", "cartes_z"}
                if not required.issubset(idx):
                    raise AuditError(f"Unsupported CFG columns in {path}: {header}")
                atoms = []
                while len(atoms) < size:
                    i += 1
                    if i >= len(lines):
                        raise AuditError(f"Truncated CFG AtomData: {path}")
                    row = lines[i].strip()
                    if not row:
                        continue
                    values = row.split()
                    atom_id = int(float(values[idx["id"]]))
                    atom_type = int(float(values[idx["type"]]))
                    if atom_type not in mlip_map:
                        raise AuditError(f"Unknown MLIP type {atom_type} in {path}")
                    atoms.append(Atom(
                        atom_id=atom_id,
                        atom_type=atom_type,
                        element=mlip_map[atom_type],
                        position=(
                            float(values[idx["cartes_x"]]),
                            float(values[idx["cartes_y"]]),
                            float(values[idx["cartes_z"]]),
                        ),
                        row_index=len(atoms),
                    ))
            elif s.startswith("Feature"):
                parts = s.split(maxsplit=2)
                if len(parts) >= 2:
                    metadata[parts[1]] = parts[2] if len(parts) == 3 else ""
            i += 1
        if size != len(atoms):
            raise AuditError(f"CFG atom count mismatch in {path}: size={size}, atoms={len(atoms)}")
        frames.append(GeometryFrame(
            source_path=path.resolve(),
            source_kind="cfg",
            frame_index=frame_index,
            label=f"{path.name}#cfg{frame_index}",
            atoms=atoms,
            metadata=metadata,
        ))
    return frames


def parse_xyz(path: Path) -> list[GeometryFrame]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    frames: list[GeometryFrame] = []
    i = 0
    frame_index = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        try:
            n = int(lines[i].strip())
        except ValueError as exc:
            raise AuditError(f"Invalid XYZ atom count in {path} line {i+1}") from exc
        if i + 1 + n >= len(lines) + 1:
            raise AuditError(f"Truncated XYZ frame in {path}")
        comment = lines[i + 1] if i + 1 < len(lines) else ""
        atoms: list[Atom] = []
        for row_index, line in enumerate(lines[i + 2:i + 2 + n]):
            parts = line.split()
            if len(parts) < 4:
                raise AuditError(f"Short XYZ row in {path}: {line!r}")
            element = parts[0]
            atoms.append(Atom(
                atom_id=row_index + 1,
                atom_type=None,
                element=element,
                position=(float(parts[1]), float(parts[2]), float(parts[3])),
                row_index=row_index,
            ))
        frame_index += 1
        frames.append(GeometryFrame(
            source_path=path.resolve(),
            source_kind="xyz",
            frame_index=frame_index,
            label=f"{path.name}#xyz{frame_index}",
            atoms=atoms,
            metadata={"comment": comment},
        ))
        i += n + 2
    if not frames:
        raise AuditError(f"No XYZ frames: {path}")
    return frames


def parse_lammps_data(path: Path, lammps_map: Mapping[int, str]) -> list[GeometryFrame]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    box: dict[str, float] = {}
    for line in lines:
        parts = line.split()
        if len(parts) >= 4 and parts[-2:] == ["xlo", "xhi"]:
            box["xlo"], box["xhi"] = float(parts[0]), float(parts[1])
        elif len(parts) >= 4 and parts[-2:] == ["ylo", "yhi"]:
            box["ylo"], box["yhi"] = float(parts[0]), float(parts[1])
        elif len(parts) >= 4 and parts[-2:] == ["zlo", "zhi"]:
            box["zlo"], box["zhi"] = float(parts[0]), float(parts[1])

    atoms_header = None
    for idx, line in enumerate(lines):
        if re.match(r"^\s*Atoms(?:\s*#.*)?\s*$", line):
            atoms_header = idx
            break
    if atoms_header is None:
        raise AuditError(f"No Atoms section in LAMMPS data file: {path}")

    style = ""
    match = re.search(r"#\s*(\w+)", lines[atoms_header])
    if match:
        style = match.group(1).lower()

    raw_rows: list[list[str]] = []
    i = atoms_header + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines):
        stripped = lines[i].split("#", 1)[0].strip()
        if not stripped:
            if raw_rows:
                break
            i += 1
            continue
        if re.match(r"^[A-Za-z]", stripped):
            break
        raw_rows.append(stripped.split())
        i += 1
    if not raw_rows:
        raise AuditError(f"Empty Atoms section in {path}")

    def decode(parts: list[str]) -> tuple[int, int, float, float, float] | None:
        candidates: list[tuple[int, int, int, int, int]] = []
        # id, type, x, y, z
        if style == "atomic":
            candidates.append((0, 1, 2, 3, 4))
        elif style == "charge":
            candidates.append((0, 1, 3, 4, 5))
        elif style == "molecular":
            candidates.append((0, 2, 3, 4, 5))
        elif style == "full":
            candidates.append((0, 2, 4, 5, 6))
        candidates.extend([
            (0, 1, 2, 3, 4),  # atomic
            (0, 1, 3, 4, 5),  # charge
            (0, 2, 3, 4, 5),  # molecular
            (0, 2, 4, 5, 6),  # full
        ])
        seen = set()
        for spec in candidates:
            if spec in seen or max(spec) >= len(parts):
                continue
            seen.add(spec)
            try:
                atom_id = int(float(parts[spec[0]]))
                atom_type = int(float(parts[spec[1]]))
                x, y, z = (float(parts[spec[2]]), float(parts[spec[3]]), float(parts[spec[4]]))
            except ValueError:
                continue
            if atom_type in lammps_map:
                return atom_id, atom_type, x, y, z
        return None

    atoms: list[Atom] = []
    for row_index, parts in enumerate(raw_rows):
        decoded = decode(parts)
        if decoded is None:
            raise AuditError(f"Cannot decode LAMMPS atom row in {path}: {' '.join(parts)}")
        atom_id, atom_type, x, y, z = decoded
        atoms.append(Atom(
            atom_id=atom_id,
            atom_type=atom_type,
            element=lammps_map[atom_type],
            position=(x, y, z),
            row_index=row_index,
        ))
    lengths = None
    if all(key in box for key in ("xlo", "xhi", "ylo", "yhi", "zlo", "zhi")):
        lengths = (
            box["xhi"] - box["xlo"],
            box["yhi"] - box["ylo"],
            box["zhi"] - box["zlo"],
        )
    return [GeometryFrame(
        source_path=path.resolve(),
        source_kind="lammps_data",
        frame_index=1,
        label=f"{path.name}#data",
        atoms=atoms,
        box_lengths=lengths,
        metadata={"atom_style": style},
    )]


def parse_lammps_dump(path: Path, lammps_map: Mapping[int, str]) -> list[GeometryFrame]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    frames: list[GeometryFrame] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("ITEM: TIMESTEP"):
            i += 1
            continue
        timestep = int(float(lines[i + 1].strip()))
        if not lines[i + 2].startswith("ITEM: NUMBER OF ATOMS"):
            raise AuditError(f"Malformed dump near timestep {timestep}: {path}")
        n = int(float(lines[i + 3].strip()))
        if not lines[i + 4].startswith("ITEM: BOX BOUNDS"):
            raise AuditError(f"Missing BOX BOUNDS in dump: {path}")
        bounds = []
        for j in range(3):
            parts = lines[i + 5 + j].split()
            bounds.append((float(parts[0]), float(parts[1])))
        header_index = i + 8
        if not lines[header_index].startswith("ITEM: ATOMS"):
            raise AuditError(f"Missing ATOMS header in dump: {path}")
        columns = lines[header_index].split()[2:]
        col = {name: idx for idx, name in enumerate(columns)}
        if "id" not in col or "type" not in col:
            raise AuditError(f"Dump lacks id/type in {path}: {columns}")

        coord_mode = None
        for triplet in (("xu", "yu", "zu"), ("x", "y", "z"), ("xs", "ys", "zs"), ("xsu", "ysu", "zsu")):
            if all(name in col for name in triplet):
                coord_mode = triplet
                break
        if coord_mode is None:
            raise AuditError(f"Dump lacks supported coordinates in {path}: {columns}")

        atoms: list[Atom] = []
        for row_index in range(n):
            parts = lines[header_index + 1 + row_index].split()
            atom_id = int(float(parts[col["id"]]))
            atom_type = int(float(parts[col["type"]]))
            if atom_type not in lammps_map:
                raise AuditError(f"Unknown LAMMPS type {atom_type} in {path}")
            coords = [float(parts[col[name]]) for name in coord_mode]
            if coord_mode[0] in {"xs", "xsu"}:
                coords = [
                    bounds[axis][0] + coords[axis] * (bounds[axis][1] - bounds[axis][0])
                    for axis in range(3)
                ]
            atoms.append(Atom(
                atom_id=atom_id,
                atom_type=atom_type,
                element=lammps_map[atom_type],
                position=tuple(coords),
                row_index=row_index,
            ))
        frames.append(GeometryFrame(
            source_path=path.resolve(),
            source_kind="lammps_dump",
            frame_index=len(frames) + 1,
            label=f"{path.name}#t{timestep}",
            atoms=atoms,
            box_lengths=tuple(hi - lo for lo, hi in bounds),
            timestep=timestep,
            metadata={"columns": columns, "coord_mode": coord_mode},
        ))
        i = header_index + 1 + n
    if not frames:
        raise AuditError(f"No frames in LAMMPS dump: {path}")
    return frames


def parse_geometry(path: Path, mlip_map: Mapping[int, str], lammps_map: Mapping[int, str]) -> list[GeometryFrame]:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix == ".cfg":
        return parse_cfg(path, mlip_map)
    if suffix == ".xyz":
        return parse_xyz(path)
    if suffix == ".data" or name.endswith(".lammps.data"):
        return parse_lammps_data(path, lammps_map)
    if suffix in {".dump", ".lammpstrj", ".traj"} or "lammpstrj" in name or "dump" in name:
        return parse_lammps_dump(path, lammps_map)
    raise AuditError(f"Unsupported geometry format: {path}")


def species_mapping_candidates(frame: GeometryFrame, expected: Sequence[str]) -> list[MappingCandidate]:
    raw_elements = frame.elements_row()
    if sorted(raw_elements) != sorted(expected):
        return []
    raw_by_element: dict[str, list[int]] = defaultdict(list)
    canonical_slots: dict[str, list[int]] = defaultdict(list)
    for idx, element in enumerate(raw_elements):
        raw_by_element[element].append(idx)
    for idx, element in enumerate(expected):
        canonical_slots[element].append(idx)

    element_permutations: list[list[tuple[int, ...]]] = []
    ordered_elements = sorted(raw_by_element)
    for element in ordered_elements:
        element_permutations.append(list(itertools.permutations(raw_by_element[element])))

    output: list[MappingCandidate] = []
    for combo in itertools.product(*element_permutations):
        indices = [-1] * len(expected)
        for element, permuted_raw in zip(ordered_elements, combo):
            for slot, raw_idx in zip(canonical_slots[element], permuted_raw):
                indices[slot] = raw_idx
        output.append(MappingCandidate(
            name="species_" + "_".join(str(i) for i in indices),
            indices=tuple(indices),
            origin="species_enumeration",
        ))
    return output


def simple_mapping_candidates(frame: GeometryFrame, expected: Sequence[str]) -> list[MappingCandidate]:
    candidates: list[MappingCandidate] = []
    row_indices = tuple(range(len(frame.atoms)))
    if frame.elements_row() == list(expected):
        candidates.append(MappingCandidate("row_order", row_indices, "simple"))

    id_sorted_indices = tuple(sorted(range(len(frame.atoms)), key=lambda idx: frame.atoms[idx].atom_id))
    if [frame.atoms[idx].element for idx in id_sorted_indices] == list(expected):
        candidates.append(MappingCandidate("id_sorted", id_sorted_indices, "simple"))
    return candidates


def recorded_mapping_candidates(frame: GeometryFrame, row: Mapping[str, str], expected: Sequence[str]) -> list[MappingCandidate]:
    output: list[MappingCandidate] = []
    order = parse_int_list(row.get("canonical_order_zero_based", ""))
    if len(order) != len(frame.atoms) or sorted(order) != list(range(len(frame.atoms))):
        return output

    bases = {
        "row": list(range(len(frame.atoms))),
        "id_sorted": sorted(range(len(frame.atoms)), key=lambda idx: frame.atoms[idx].atom_id),
    }
    for base_name, base in bases.items():
        direct = tuple(base[idx] for idx in order)
        if [frame.atoms[idx].element for idx in direct] == list(expected):
            output.append(MappingCandidate(
                f"recorded_direct_on_{base_name}", direct, "recorded",
            ))
        inverse_order = [0] * len(order)
        for canonical_idx, raw_idx in enumerate(order):
            inverse_order[raw_idx] = canonical_idx
        inverse = tuple(base[idx] for idx in inverse_order)
        if [frame.atoms[idx].element for idx in inverse] == list(expected):
            output.append(MappingCandidate(
                f"recorded_inverse_on_{base_name}", inverse, "recorded_inverse",
            ))
    return output


def unique_mappings(candidates: Iterable[MappingCandidate]) -> list[MappingCandidate]:
    seen: set[tuple[int, ...]] = set()
    result: list[MappingCandidate] = []
    for candidate in candidates:
        if candidate.indices in seen:
            continue
        seen.add(candidate.indices)
        result.append(candidate)
    return result


def mapped_positions(frame: GeometryFrame, mapping: MappingCandidate) -> np.ndarray:
    return np.asarray([frame.atoms[idx].position for idx in mapping.indices], dtype=float)


def mapped_elements(frame: GeometryFrame, mapping: MappingCandidate) -> list[str]:
    return [frame.atoms[idx].element for idx in mapping.indices]


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def reaction_coordinates(positions: np.ndarray) -> tuple[float, float]:
    if positions.shape != (9, 3):
        raise AuditError(f"Expected positions shape (9,3), found {positions.shape}")
    o1, hstar, o2 = positions[0], positions[1], positions[7]
    return distance(o1, hstar) - distance(o2, hstar), distance(o1, o2)


def pair_distance_max_delta(a: np.ndarray, b: np.ndarray) -> float:
    maximum = 0.0
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            maximum = max(maximum, abs(distance(a[i], a[j]) - distance(b[i], b[j])))
    return maximum


def weighted_centroid(points: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    if weights is None:
        return points.mean(axis=0)
    return np.average(points, axis=0, weights=weights)


def kabsch_rotation(
    moving_centered: np.ndarray,
    reference_centered: np.ndarray,
    weights: np.ndarray | None,
    allow_reflection: bool,
) -> np.ndarray:
    if weights is None:
        covariance = moving_centered.T @ reference_centered
    else:
        covariance = (moving_centered * weights[:, None]).T @ reference_centered
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if not allow_reflection and np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    return rotation


def rotation_angle_deg(rotation: np.ndarray) -> float:
    determinant = np.linalg.det(rotation)
    if determinant < 0:
        return float("nan")
    cosine = max(-1.0, min(1.0, (np.trace(rotation) - 1.0) / 2.0))
    return math.degrees(math.acos(cosine))


def minimum_image_to_reference(moving: np.ndarray, reference: np.ndarray, box: Sequence[float]) -> np.ndarray:
    output = moving.copy()
    lengths = np.asarray(box, dtype=float)
    if np.any(lengths <= 0):
        return output
    delta = reference - output
    output += np.round(delta / lengths) * lengths
    return output


def align_and_measure(
    moving: np.ndarray,
    reference: np.ndarray,
    expected: Sequence[str],
    method: str,
    box_lengths: tuple[float, float, float] | None = None,
) -> AlignmentResult:
    if moving.shape != reference.shape:
        raise AuditError(f"Shape mismatch: moving={moving.shape}, reference={reference.shape}")
    weights = np.asarray([ATOMIC_MASS[element] for element in expected], dtype=float)
    raw_diff = moving - reference
    raw_max = float(np.max(np.abs(raw_diff)))

    work = moving.copy()
    if method.startswith("pbc_"):
        if box_lengths is None:
            raise AuditError("PBC alignment requested without box lengths")
        shift0 = reference.mean(axis=0) - work.mean(axis=0)
        work = minimum_image_to_reference(work + shift0, reference, box_lengths)
        method_core = method[4:]
    else:
        method_core = method

    if method_core == "none":
        aligned = work.copy()
        translation = np.zeros(3)
        rotation = np.eye(3)
    elif method_core in {"translation_arithmetic", "translation_com"}:
        use_weights = weights if method_core.endswith("_com") else None
        cm = weighted_centroid(work, use_weights)
        cr = weighted_centroid(reference, use_weights)
        translation = cr - cm
        aligned = work + translation
        rotation = np.eye(3)
    elif method_core in {
        "kabsch_arithmetic", "kabsch_com",
        "reflection_arithmetic", "reflection_com",
    }:
        use_weights = weights if method_core.endswith("_com") else None
        cm = weighted_centroid(work, use_weights)
        cr = weighted_centroid(reference, use_weights)
        p = work - cm
        q = reference - cr
        allow_reflection = method_core.startswith("reflection")
        rotation = kabsch_rotation(p, q, use_weights, allow_reflection)
        aligned = p @ rotation + cr
        translation = cr - cm @ rotation
    else:
        raise AuditError(f"Unknown alignment method: {method}")

    diff = aligned - reference
    component_rms = float(np.sqrt(np.mean(diff * diff)))
    atom_rms = float(np.sqrt(np.mean(np.sum(diff * diff, axis=1))))
    qpt, roo = reaction_coordinates(aligned)
    return AlignmentResult(
        method=method,
        aligned=aligned,
        translation=translation,
        rotation=rotation,
        determinant=float(np.linalg.det(rotation)),
        rotation_angle_deg=rotation_angle_deg(rotation),
        max_abs=float(np.max(np.abs(diff))),
        component_rms=component_rms,
        atom_rms=atom_rms,
        pair_max_delta=pair_distance_max_delta(aligned, reference),
        raw_max_abs=raw_max,
        qpt=qpt,
        roo=roo,
    )


def self_test() -> None:
    expected = ["O", "H", "C", "H", "C", "H", "C", "O", "H"]
    rng = np.random.default_rng(42)
    reference = rng.normal(size=(9, 3))
    angle = math.radians(7.0)
    rot = np.array([
        [math.cos(angle), -math.sin(angle), 0.0],
        [math.sin(angle), math.cos(angle), 0.0],
        [0.0, 0.0, 1.0],
    ])
    moving = reference @ rot.T + np.array([0.35, -0.38, 0.02])
    result = align_and_measure(moving, reference, expected, "kabsch_arithmetic")
    if result.atom_rms > 1e-10 or result.max_abs > 1e-10:
        raise AuditError(
            f"Synthetic Kabsch regression failed: atom_rms={result.atom_rms}, max={result.max_abs}"
        )
    translated = align_and_measure(moving, reference, expected, "translation_arithmetic")
    if translated.atom_rms < 1e-3:
        raise AuditError("Synthetic translation-only control unexpectedly removed rotation")
    print("SELF_TEST=PASS")
    print(f"KABSCH_ATOM_RMS={result.atom_rms:.3e}")
    print(f"TRANSLATION_ONLY_ATOM_RMS={translated.atom_rms:.6g}")


def discover_required_paths(root: Path) -> dict[str, Path]:
    v032_root = require_dir(root / V032_REL, "v032 version root")
    v032d_root = require_dir(root / V032D_REL, "v032d version root")
    v032 = resolve_current(v032_root, "CURRENT_TARGETED_MD_DIAGNOSTICS.txt")
    v032d = resolve_current(v032d_root, "CURRENT_V032_SELECTION_INTERFACE_DIAGNOSTIC.txt")
    captured = find_single(v032d, [
        "tables/captured_break_configurations_v032d.tsv",
        "**/captured_break_configurations_v032d.tsv",
    ], "captured break table")
    summary = find_single(v032d, ["summary_v032d.json", "**/summary_v032d.json"], "v032d summary")
    provenance_script = find_single(v032d, [
        "provenance/step34c_v032_selection_interface_diagnostic_v032d.py",
        "**/step34c_v032_selection_interface_diagnostic_v032d.py",
    ], "v032d provenance script")
    live_script = root / "scripts/step34c_v032_selection_interface_diagnostic_v032d.py"
    return {
        "v032": v032,
        "v032d": v032d,
        "captured": captured,
        "summary": summary,
        "provenance_script": provenance_script,
        "live_script": live_script.resolve() if live_script.is_file() else live_script,
        "left_endpoint": require_file(root / "03_endpoints/left_relaxed.xyz", "left relaxed endpoint"),
        "right_endpoint": require_file(root / "03_endpoints/right_relaxed.xyz", "right relaxed endpoint"),
        "atom_order": require_file(root / "00_protocol/ATOM_ORDER_LOCKED_v000.tsv", "atom-order lock"),
    }


def artifact_record(path: Path, role: str, root: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "role": role,
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if path.is_relative_to(root) else "",
        "size_bytes": stat.st_size,
        "mtime_utc": dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha256": sha256_file(path),
    }


def source_code_audit(root: Path, paths: Mapping[str, Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    candidates: list[tuple[str, Path]] = []
    for role in ("provenance_script", "live_script"):
        path = paths[role]
        if path.is_file():
            candidates.append((role, path))
    for pattern in (
        "scripts/step34c_v032_selection_interface_diagnostic_v032d.py.previous_*",
        "stages/**/step34c_v032_selection_interface_diagnostic_v032d*.py",
    ):
        for path in root.glob(pattern):
            if path.is_file():
                candidates.append(("historical_or_staged_script", path.resolve()))

    dedup: dict[Path, str] = {}
    for role, path in candidates:
        dedup.setdefault(path, role)

    script_rows: list[dict[str, Any]] = []
    keyword_rows: list[dict[str, Any]] = []
    context_parts: list[str] = []
    provenance_sha = sha256_file(paths["provenance_script"])

    for path, role in sorted(dedup.items(), key=lambda item: str(item[0])):
        sha = sha256_file(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        parse_status = "PASS"
        functions: list[tuple[str, int, int]] = []
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append((node.name, node.lineno, getattr(node, "end_lineno", node.lineno)))
        except SyntaxError as exc:
            parse_status = f"FAIL:{exc}"
        script_rows.append({
            "role": role,
            "path": str(path),
            "sha256": sha,
            "size_bytes": path.stat().st_size,
            "identical_to_provenance": sha == provenance_sha,
            "ast_parse": parse_status,
            "function_count": len(functions),
            "functions_of_interest": ",".join(
                name for name, _, _ in functions
                if any(token in name.lower() for token in ("kabsch", "align", "canon", "assign", "displace", "cfg"))
            ),
        })

        hits: set[int] = set()
        for line_no, line in enumerate(lines, start=1):
            lower = line.lower()
            matched = [keyword for keyword in KEYWORDS if keyword.lower() in lower]
            if matched:
                hits.add(line_no)
                keyword_rows.append({
                    "script_path": str(path),
                    "script_sha256": sha,
                    "line": line_no,
                    "keywords": ",".join(matched),
                    "text": line.strip(),
                })
        if role == "provenance_script":
            context_parts.append(f"===== PROVENANCE SCRIPT: {path} =====")
            selected_ranges: list[tuple[int, int]] = []
            for hit in sorted(hits):
                selected_ranges.append((max(1, hit - 8), min(len(lines), hit + 8)))
            merged: list[tuple[int, int]] = []
            for start, end in selected_ranges:
                if not merged or start > merged[-1][1] + 1:
                    merged.append((start, end))
                else:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            for start, end in merged:
                context_parts.append(f"\n--- lines {start}-{end} ---")
                for line_no in range(start, end + 1):
                    context_parts.append(f"{line_no:05d}: {lines[line_no - 1]}")
    return script_rows, keyword_rows, "\n".join(context_parts) + "\n"


def discover_geometry_files(
    root: Path,
    row: Mapping[str, str],
    paths: Mapping[str, Path],
) -> tuple[Path, list[tuple[str, Path]]]:
    preselected = ensure_under_root(Path(row["preselected_path"]), root, "preselected_path")
    require_file(preselected, "preselected CFG")
    trajectory_dir = preselected.parent

    candidates: list[tuple[str, Path]] = [
        ("global_left_endpoint", paths["left_endpoint"]),
        ("global_right_endpoint", paths["right_endpoint"]),
    ]
    for key, value in row.items():
        if "path" in key.lower() and str(value).strip():
            candidate = Path(value)
            if candidate.is_absolute() and candidate.exists() and candidate.is_file():
                try:
                    candidate = ensure_under_root(candidate, root, key)
                except AuditError:
                    continue
                if candidate.suffix.lower() in GEOMETRY_SUFFIXES:
                    candidates.append((f"table_column:{key}", candidate))

    for path in trajectory_dir.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if path.suffix.lower() in GEOMETRY_SUFFIXES and (
            any(hint in lower for hint in GEOMETRY_NAME_HINTS) or path == preselected
        ):
            candidates.append(("trajectory_local", path.resolve()))

    side = str(row.get("side", "")).strip()
    run0_root = paths["v032d"] / "run0_repeats"
    if run0_root.is_dir() and side:
        for path in run0_root.glob(f"{side}_repeat_*/*"):
            if path.is_file() and path.suffix.lower() in GEOMETRY_SUFFIXES:
                candidates.append(("v032d_run0", path.resolve()))

    unique: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for role, path in candidates:
        resolved = path.resolve()
        if resolved == preselected.resolve():
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append((role, resolved))
    return preselected, unique


def metric_targets(row: Mapping[str, str], prefix: str) -> dict[str, float | None]:
    return {
        "max_abs": parse_float(row.get(f"{prefix}_max_abs_ang", "")),
        "rms": parse_float(row.get(f"{prefix}_rms_ang", "")),
        "pair": parse_float(row.get(f"{prefix}_pair_distance_max_abs_delta_ang", "")),
        "kabsch_rms": parse_float(row.get(f"{prefix}_kabsch_rms_ang", "")),
    }


def normalize_residual(computed: float, target: float | None, tolerance: float) -> tuple[float, float | None]:
    if target is None:
        return 0.0, None
    residual = abs(computed - target)
    return residual / tolerance, residual


def score_reconstruction(
    row: Mapping[str, str],
    trajectory_id: str,
    reference: GeometryFrame,
    reference_role: str,
    reference_mapping: MappingCandidate,
    break_frame: GeometryFrame,
    break_mapping: MappingCandidate,
    expected: Sequence[str],
    alignment_method: str,
    rms_definition: str,
) -> ReconstructionCandidate:
    moving = mapped_positions(break_frame, break_mapping)
    reference_positions = mapped_positions(reference, reference_mapping)

    label_lower = (reference.label + " " + reference.source_path.name).lower()
    if "dump0" in label_lower or (reference.timestep == 0 and "dump" in reference.source_kind):
        prefix = "break_vs_dump0"
    else:
        prefix = "break_vs_endpoint"
    targets = metric_targets(row, prefix)
    qpt_target = parse_float(row.get("break_qpt_ang", ""))
    roo_target = parse_float(row.get("break_roo_ang", ""))

    box = reference.box_lengths or break_frame.box_lengths
    result = align_and_measure(moving, reference_positions, expected, alignment_method, box)
    computed_rms = result.component_rms if rms_definition == "component" else result.atom_rms

    # Independently calculate proper Kabsch RMSD for a table column that may coexist
    # with max/RMS values generated by another alignment convention.
    kabsch = align_and_measure(moving, reference_positions, expected, "kabsch_arithmetic", box)

    normalized: list[float] = []
    residual_notes: list[str] = []
    for name, computed, target, tol in (
        ("max", result.max_abs, targets["max_abs"], 5e-7),
        ("rms", computed_rms, targets["rms"], 5e-7),
        ("pair", result.pair_max_delta, targets["pair"], 5e-7),
        ("kabsch", kabsch.atom_rms, targets["kabsch_rms"], 5e-7),
        ("qpt", result.qpt, qpt_target, 5e-5),
        ("roo", result.roo, roo_target, 5e-5),
    ):
        nres, residual = normalize_residual(computed, target, tol)
        if target is not None:
            normalized.append(nres)
            residual_notes.append(f"{name}_res={residual:.3g}")
    if not normalized:
        normalized = [math.inf]
    score = float(math.sqrt(sum(value * value for value in normalized) / len(normalized)))
    max_norm = float(max(normalized))
    exact = max_norm <= 1.0
    near = max_norm <= 200.0  # <=1e-4 A for 5e-7-normalized geometry metrics

    return ReconstructionCandidate(
        trajectory_id=trajectory_id,
        reference_label=reference.label,
        reference_path=str(reference.source_path),
        reference_kind=f"{reference_role}:{reference.source_kind}",
        reference_frame_index=reference.frame_index,
        reference_mapping=reference_mapping.name,
        break_mapping=break_mapping.name,
        break_mapping_origin=break_mapping.origin,
        alignment_method=alignment_method,
        rms_definition=rms_definition,
        metric_prefix=prefix,
        score=score,
        max_normalized_residual=max_norm,
        exact=exact,
        near=near,
        computed_max_abs=result.max_abs,
        table_max_abs=targets["max_abs"],
        computed_rms=computed_rms,
        table_rms=targets["rms"],
        computed_pair_delta=result.pair_max_delta,
        table_pair_delta=targets["pair"],
        computed_kabsch_rms=kabsch.atom_rms,
        table_kabsch_rms=targets["kabsch_rms"],
        qpt=result.qpt,
        table_qpt=qpt_target,
        roo=result.roo,
        table_roo=roo_target,
        raw_max_abs=result.raw_max_abs,
        atom_rms=result.atom_rms,
        component_rms=result.component_rms,
        rotation_angle_deg=result.rotation_angle_deg,
        rotation_det=result.determinant,
        break_mapping_indices=",".join(map(str, break_mapping.indices)),
        reference_mapping_indices=",".join(map(str, reference_mapping.indices)),
        notes=";".join(residual_notes),
    )


def reference_mapping_shortlist(
    reference: GeometryFrame,
    expected: Sequence[str],
    global_endpoint: GeometryFrame,
    max_count: int = 8,
) -> list[MappingCandidate]:
    candidates = unique_mappings(
        simple_mapping_candidates(reference, expected)
        + species_mapping_candidates(reference, expected)
    )
    if not candidates:
        return []
    global_mapping = simple_mapping_candidates(global_endpoint, expected)
    if not global_mapping:
        raise AuditError(f"Global endpoint is not in locked atom order: {global_endpoint.source_path}")
    global_positions = mapped_positions(global_endpoint, global_mapping[0])

    ranked: list[tuple[float, MappingCandidate]] = []
    for mapping in candidates:
        positions = mapped_positions(reference, mapping)
        result = align_and_measure(positions, global_positions, expected, "kabsch_arithmetic")
        score = result.atom_rms + 10.0 * result.pair_max_delta
        bonus = -1e-9 if mapping.origin == "simple" else 0.0
        ranked.append((score + bonus, mapping))
    ranked.sort(key=lambda item: (item[0], item[1].name))
    selected = [mapping for _, mapping in ranked[:max_count]]
    # Preserve all simple mappings even if they fall outside the numerical top-N.
    selected.extend(simple_mapping_candidates(reference, expected))
    return unique_mappings(selected)


def inventory_files(paths: Iterable[tuple[str, Path]], root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for role, path in paths:
        path = path.resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            record = artifact_record(path, role, root)
        except OSError as exc:
            record = {
                "role": role,
                "path": str(path),
                "relative_path": "",
                "size_bytes": "",
                "mtime_utc": "",
                "sha256": "",
                "error": f"{type(exc).__name__}: {exc}",
            }
        rows.append(record)
    return rows


def audit_trajectory(
    root: Path,
    row: Mapping[str, str],
    paths: Mapping[str, Path],
    expected: Sequence[str],
    mlip_map: Mapping[int, str],
    lammps_map: Mapping[int, str],
    top_n: int,
) -> tuple[
    list[ReconstructionCandidate],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    trajectory_id = row["trajectory_id"]
    preselected_path, reference_files = discover_geometry_files(root, row, paths)
    break_frames = parse_cfg(preselected_path, mlip_map)
    if len(break_frames) != 1:
        raise AuditError(f"{trajectory_id}: expected one preselected CFG frame, found {len(break_frames)}")
    break_frame = break_frames[0]

    recorded = recorded_mapping_candidates(break_frame, row, expected)
    break_mappings = unique_mappings(
        recorded
        + simple_mapping_candidates(break_frame, expected)
        + species_mapping_candidates(break_frame, expected)
    )
    if not break_mappings:
        raise AuditError(f"{trajectory_id}: no species-compatible break mapping")

    side = row["side"]
    global_path = paths["left_endpoint"] if side == "left" else paths["right_endpoint"]
    global_endpoint = parse_xyz(global_path)[0]

    parsed_references: list[tuple[str, GeometryFrame]] = []
    parse_rows: list[dict[str, Any]] = []
    artifact_inputs: list[tuple[str, Path]] = [("preselected", preselected_path)]
    artifact_inputs.extend(reference_files)

    for role, path in reference_files:
        try:
            frames = parse_geometry(path, mlip_map, lammps_map)
            for frame in frames:
                if len(frame.atoms) != 9:
                    parse_rows.append({
                        "trajectory_id": trajectory_id,
                        "role": role,
                        "path": str(path),
                        "status": "SKIP",
                        "reason": f"atom_count={len(frame.atoms)}",
                        "frame": frame.label,
                    })
                    continue
                if sorted(frame.elements_row()) != sorted(expected):
                    parse_rows.append({
                        "trajectory_id": trajectory_id,
                        "role": role,
                        "path": str(path),
                        "status": "SKIP",
                        "reason": f"composition={frame.elements_row()}",
                        "frame": frame.label,
                    })
                    continue
                parsed_references.append((role, frame))
                parse_rows.append({
                    "trajectory_id": trajectory_id,
                    "role": role,
                    "path": str(path),
                    "status": "PARSED",
                    "reason": "",
                    "frame": frame.label,
                    "timestep": frame.timestep,
                    "row_elements": ",".join(frame.elements_row()),
                    "row_ids": ",".join(map(str, frame.ids_row())),
                    "box_lengths": frame.box_lengths,
                })
        except Exception as exc:
            parse_rows.append({
                "trajectory_id": trajectory_id,
                "role": role,
                "path": str(path),
                "status": "UNPARSED",
                "reason": f"{type(exc).__name__}: {exc}",
                "frame": "",
            })

    # Ensure the side-matched global endpoint is present even if discovery logic changes.
    if not any(frame.source_path == global_path.resolve() for _, frame in parsed_references):
        parsed_references.append(("global_side_endpoint", global_endpoint))

    alignments = [
        "none",
        "translation_arithmetic",
        "translation_com",
        "kabsch_arithmetic",
        "kabsch_com",
        "reflection_arithmetic",
        "reflection_com",
    ]
    candidates: list[ReconstructionCandidate] = []

    for reference_role, reference in parsed_references:
        reference_mappings = reference_mapping_shortlist(
            reference, expected, global_endpoint, max_count=8
        )
        if not reference_mappings:
            continue
        methods = list(alignments)
        if reference.box_lengths or break_frame.box_lengths:
            methods.extend([
                "pbc_translation_arithmetic",
                "pbc_kabsch_arithmetic",
            ])
        for break_mapping in break_mappings:
            for reference_mapping in reference_mappings:
                for method in methods:
                    for rms_definition in ("component", "atom"):
                        try:
                            candidate = score_reconstruction(
                                row=row,
                                trajectory_id=trajectory_id,
                                reference=reference,
                                reference_role=reference_role,
                                reference_mapping=reference_mapping,
                                break_frame=break_frame,
                                break_mapping=break_mapping,
                                expected=expected,
                                alignment_method=method,
                                rms_definition=rms_definition,
                            )
                        except Exception:
                            continue
                        candidates.append(candidate)

    if not candidates:
        raise AuditError(f"{trajectory_id}: no reconstruction candidate could be evaluated")
    candidates.sort(key=lambda item: (
        item.score,
        item.max_normalized_residual,
        0 if item.break_mapping_origin == "recorded" else 1,
        item.reference_path,
        item.reference_frame_index,
        item.alignment_method,
    ))
    top = candidates[:top_n]
    best = top[0]
    second = top[1] if len(top) > 1 else None

    ambiguity = False
    if second is not None and second.score <= best.score * 1.05 + 1e-12:
        identity_a = (
            best.reference_path, best.reference_frame_index,
            best.break_mapping_indices, best.reference_mapping_indices,
            best.alignment_method, best.rms_definition,
        )
        identity_b = (
            second.reference_path, second.reference_frame_index,
            second.break_mapping_indices, second.reference_mapping_indices,
            second.alignment_method, second.rms_definition,
        )
        ambiguity = identity_a != identity_b

    recorded_best = best.break_mapping_origin == "recorded"
    if best.exact and recorded_best and not ambiguity:
        classification = "EXACT_REPRODUCTION_RECORDED_MAPPING"
    elif best.exact and ambiguity:
        classification = "EXACT_BUT_AMBIGUOUS"
    elif best.exact:
        classification = "EXACT_REPRODUCTION_DIFFERENT_MAPPING"
    elif best.near:
        classification = "NEAR_REPRODUCTION"
    else:
        classification = "NOT_REPRODUCED"

    summary = {
        "trajectory_id": trajectory_id,
        "classification": classification,
        "best_score": best.score,
        "best_max_normalized_residual": best.max_normalized_residual,
        "best_reference": best.reference_path,
        "best_reference_label": best.reference_label,
        "best_reference_kind": best.reference_kind,
        "best_reference_mapping": best.reference_mapping,
        "best_break_mapping": best.break_mapping,
        "best_break_mapping_origin": best.break_mapping_origin,
        "best_alignment": best.alignment_method,
        "best_rms_definition": best.rms_definition,
        "best_exact": best.exact,
        "best_near": best.near,
        "ambiguous_top_solution": ambiguity,
        "recorded_mapping_candidate_count": len(recorded),
        "break_mapping_candidate_count": len(break_mappings),
        "reference_frame_count": len(parsed_references),
        "table_columns": list(row.keys()),
    }
    return top, parse_rows, inventory_files(artifact_inputs, root), summary


def candidate_to_row(candidate: ReconstructionCandidate, rank: int) -> dict[str, Any]:
    row = dataclasses.asdict(candidate)
    row["rank"] = rank
    return row


def write_xyz(path: Path, elements: Sequence[str], frames: Sequence[tuple[np.ndarray, str]]) -> None:
    lines: list[str] = []
    for positions, comment in frames:
        lines.append(str(len(elements)))
        lines.append(comment)
        for element, position in zip(elements, positions):
            lines.append(f"{element:<2s} {position[0]: .12f} {position[1]: .12f} {position[2]: .12f}")
    atomic_write_text(path, "\n".join(lines) + "\n")


def reconstruct_best_xyz(
    output_dir: Path,
    trajectory_id: str,
    best: ReconstructionCandidate,
    row: Mapping[str, str],
    root: Path,
    paths: Mapping[str, Path],
    expected: Sequence[str],
    mlip_map: Mapping[int, str],
    lammps_map: Mapping[int, str],
) -> str:
    preselected = ensure_under_root(Path(row["preselected_path"]), root, "preselected_path")
    break_frame = parse_cfg(preselected, mlip_map)[0]
    all_break = unique_mappings(
        recorded_mapping_candidates(break_frame, row, expected)
        + simple_mapping_candidates(break_frame, expected)
        + species_mapping_candidates(break_frame, expected)
    )
    break_mapping = next(m for m in all_break if m.name == best.break_mapping)

    reference_frames = parse_geometry(Path(best.reference_path), mlip_map, lammps_map)
    reference = next(
        frame for frame in reference_frames
        if frame.frame_index == best.reference_frame_index and frame.label == best.reference_label
    )
    side_global = parse_xyz(paths["left_endpoint"] if row["side"] == "left" else paths["right_endpoint"])[0]
    ref_maps = reference_mapping_shortlist(reference, expected, side_global, max_count=288)
    reference_mapping = next(m for m in ref_maps if m.name == best.reference_mapping)

    moving = mapped_positions(break_frame, break_mapping)
    reference_positions = mapped_positions(reference, reference_mapping)
    box = reference.box_lengths or break_frame.box_lengths
    result = align_and_measure(moving, reference_positions, expected, best.alignment_method, box)
    path = output_dir / f"{trajectory_id}_best_reconstruction_v001.xyz"
    write_xyz(path, expected, [
        (reference_positions, (
            f"trajectory={trajectory_id} state=reference source={best.reference_path} "
            f"frame={best.reference_label} mapping={best.reference_mapping}"
        )),
        (result.aligned, (
            f"trajectory={trajectory_id} state=aligned_break source={preselected} "
            f"break_mapping={best.break_mapping} alignment={best.alignment_method} "
            f"max_abs_A={result.max_abs:.12g} component_rms_A={result.component_rms:.12g} "
            f"atom_rms_A={result.atom_rms:.12g} pair_delta_A={result.pair_max_delta:.12g}"
        )),
    ])
    return str(path)


def derive_global_classification(trajectory_summaries: Sequence[Mapping[str, Any]]) -> str:
    classes = [row["classification"] for row in trajectory_summaries]
    if all(value == "EXACT_REPRODUCTION_RECORDED_MAPPING" for value in classes):
        return "A_EXACT_REPRODUCTION_RECORDED_MAPPING"
    if all(value.startswith("EXACT") for value in classes):
        return "B_EXACT_REPRODUCTION_WITH_MAPPING_OR_REFERENCE_AMBIGUITY"
    if all(value in {"EXACT_REPRODUCTION_RECORDED_MAPPING", "EXACT_BUT_AMBIGUOUS",
                     "EXACT_REPRODUCTION_DIFFERENT_MAPPING", "NEAR_REPRODUCTION"} for value in classes):
        return "C_PARTIAL_OR_NEAR_GEOMETRY_REPRODUCTION"
    return "D_GEOMETRY_PROVENANCE_NOT_REPRODUCED"


def build_report(
    classification: str,
    paths: Mapping[str, Path],
    script_rows: Sequence[Mapping[str, Any]],
    trajectory_summaries: Sequence[Mapping[str, Any]],
    table_columns: Sequence[str],
) -> str:
    provenance_sha = sha256_file(paths["provenance_script"])
    live_same = any(
        row.get("role") == "live_script" and row.get("identical_to_provenance")
        for row in script_rows
    )
    lines = [
        "# v032/v032d geometry-provenance forensic audit v001",
        "",
        f"Created UTC: {utc_now()}",
        "",
        f"Overall classification: `{classification}`",
        "",
        "## Scope",
        "",
        "This audit is read-only with respect to all v032/v032d inputs. It does not",
        "execute DFT, molecular dynamics, LAMMPS integration, MTP training, or modify",
        "the frozen scientific results. It tests the exact geometry reconstruction",
        "rather than assuming a particular atom ordering or alignment convention.",
        "",
        "## Authoritative implementation",
        "",
        f"- provenance script: `{paths['provenance_script']}`",
        f"- provenance SHA256: `{provenance_sha}`",
        f"- live script identical to provenance: `{live_same}`",
        "",
        "The files `source_logic_context_v001.txt`, `script_hashes_v001.tsv`, and",
        "`source_keyword_hits_v001.tsv` contain the exact code context responsible",
        "for canonicalization and displacement metrics.",
        "",
        "## Captured table columns",
        "",
        "`" + "`, `".join(table_columns) + "`",
        "",
        "## Per-trajectory result",
        "",
        "| trajectory | classification | reference | break mapping | alignment | RMS convention | exact | ambiguous |",
        "|---|---|---|---|---|---|---:|---:|",
    ]
    for row in trajectory_summaries:
        lines.append(
            f"| {row['trajectory_id']} | {row['classification']} | "
            f"`{Path(row['best_reference']).name}` / `{row['best_reference_label']}` | "
            f"`{row['best_break_mapping']}` | `{row['best_alignment']}` | "
            f"`{row['best_rms_definition']}` | {row['best_exact']} | "
            f"{row['ambiguous_top_solution']} |"
        )
    lines.extend([
        "",
        "## Interpretation rules",
        "",
        "- `A`: all six rows reproduce the stored metrics using the recorded mapping.",
        "- `B`: the stored numbers reproduce, but more than one mapping/reference is",
        "  equally compatible or a different mapping is required.",
        "- `C`: only near reproduction is obtained; exact provenance remains incomplete.",
        "- `D`: one or more stored geometry metrics cannot be reconstructed from the",
        "  preserved artifacts under the tested conventions.",
        "",
        "A completed `D` audit is not a software crash. It is a scientific finding that",
        "the stored geometry provenance is insufficient or internally inconsistent.",
        "",
        "## Important limitation",
        "",
        "This audit checks geometry provenance. It does not establish that high MaxVol",
        "grade implies a large physical energy or force error. That requires new DFT",
        "single-point labels for the six captured first-step configurations.",
        "",
    ])
    return "\n".join(lines)


def create_bundle(attempt_dir: Path) -> Path:
    bundle = attempt_dir / "v032d_geometry_forensic_audit_v001.tar.gz"
    include = [
        "STATUS_v032e.txt",
        "summary_v001.json",
        "reports/forensic_report_v001.md",
        "reports/source_logic_context_v001.txt",
        "tables/trajectory_summary_v001.tsv",
        "tables/reconstruction_candidates_top_v001.tsv",
        "tables/reference_parse_inventory_v001.tsv",
        "tables/artifact_inventory_v001.tsv",
        "tables/script_hashes_v001.tsv",
        "tables/source_keyword_hits_v001.tsv",
        "checksums_v001.tsv",
    ]
    with tarfile.open(bundle, "w:gz") as archive:
        for rel in include:
            path = attempt_dir / rel
            if path.is_file():
                archive.add(path, arcname=rel)
        geometry_dir = attempt_dir / "geometry"
        if geometry_dir.is_dir():
            for path in sorted(geometry_dir.glob("*.xyz")):
                archive.add(path, arcname=str(path.relative_to(attempt_dir)))
    return bundle


def generate_checksums(attempt_dir: Path) -> Path:
    rows: list[dict[str, Any]] = []
    for path in sorted(attempt_dir.rglob("*")):
        if not path.is_file() or path.name == "checksums_v001.tsv":
            continue
        rows.append({
            "relative_path": str(path.relative_to(attempt_dir)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    output = attempt_dir / "checksums_v001.tsv"
    atomic_write_tsv(output, rows, ["relative_path", "size_bytes", "sha256"])
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only forensic audit of v032/v032d geometry provenance."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--top-n", type=int, default=40)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    root = require_dir(args.root.expanduser().resolve(), "project root")
    expected, mlip_map, lammps_map = load_atom_order(root)
    paths = discover_required_paths(root)
    rows = read_tsv(paths["captured"])
    ids = {row.get("trajectory_id", "") for row in rows}
    if ids != EXPECTED_CASES:
        raise AuditError(f"Unexpected trajectory IDs: observed={sorted(ids)}, expected={sorted(EXPECTED_CASES)}")
    if len(rows) != 6:
        raise AuditError(f"Expected six captured rows, found {len(rows)}")

    script_rows, keyword_rows, source_context = source_code_audit(root, paths)
    log(f"Resolved v032: {paths['v032']}")
    log(f"Resolved v032d: {paths['v032d']}")
    log(f"Captured table: {paths['captured']}")
    log(f"Provenance script SHA256: {sha256_file(paths['provenance_script'])}")
    log(f"Locked atom order: {','.join(expected)}")

    # Validate that every preselected file is present and parseable before creating output.
    for row in rows:
        preselected = ensure_under_root(Path(row["preselected_path"]), root, "preselected_path")
        frames = parse_cfg(require_file(preselected, "preselected CFG"), mlip_map)
        if len(frames) != 1 or len(frames[0].atoms) != 9:
            raise AuditError(f"{row['trajectory_id']}: invalid preselected CFG")
        log(
            f"Preflight {row['trajectory_id']}: raw IDs={frames[0].ids_row()} "
            f"raw elements={frames[0].elements_row()}"
        )

    if args.validate_only:
        print("VALIDATE_ONLY=PASS")
        print(f"V032={paths['v032']}")
        print(f"V032D={paths['v032d']}")
        print(f"CAPTURED_ROWS={len(rows)}")
        print(f"PROVENANCE_SCRIPT_SHA256={sha256_file(paths['provenance_script'])}")
        return 0

    attempt_root = root / OUTPUT_REL
    attempt_root.mkdir(parents=True, exist_ok=True)
    attempt_dir = attempt_root / f"attempt_{utc_stamp()}"
    if attempt_dir.exists():
        raise AuditError(f"Refusing existing attempt directory: {attempt_dir}")
    attempt_dir.mkdir(parents=False)
    (attempt_dir / "tables").mkdir()
    (attempt_dir / "reports").mkdir()
    (attempt_dir / "geometry").mkdir()
    (attempt_dir / "provenance").mkdir()

    # Snapshot exact authoritative inputs used for this audit.
    shutil.copy2(paths["captured"], attempt_dir / "provenance/captured_break_configurations_v032d.tsv")
    shutil.copy2(paths["summary"], attempt_dir / "provenance/summary_v032d.json")
    shutil.copy2(paths["provenance_script"], attempt_dir / "provenance/step34c_v032_selection_interface_diagnostic_v032d.py")
    shutil.copy2(paths["atom_order"], attempt_dir / "provenance/ATOM_ORDER_LOCKED_v000.tsv")

    all_candidates: list[dict[str, Any]] = []
    all_parse_rows: list[dict[str, Any]] = []
    all_artifacts: list[dict[str, Any]] = []
    trajectory_summaries: list[dict[str, Any]] = []

    for row in sorted(rows, key=lambda item: item["trajectory_id"]):
        trajectory_id = row["trajectory_id"]
        log(f"Auditing {trajectory_id}")
        top, parse_rows, artifacts, summary = audit_trajectory(
            root=root,
            row=row,
            paths=paths,
            expected=expected,
            mlip_map=mlip_map,
            lammps_map=lammps_map,
            top_n=args.top_n,
        )
        all_candidates.extend(candidate_to_row(candidate, rank) for rank, candidate in enumerate(top, start=1))
        all_parse_rows.extend(parse_rows)
        for artifact in artifacts:
            artifact["trajectory_id"] = trajectory_id
            all_artifacts.append(artifact)
        trajectory_summaries.append(summary)

        best = top[0]
        try:
            xyz_path = reconstruct_best_xyz(
                attempt_dir / "geometry", trajectory_id, best, row, root, paths,
                expected, mlip_map, lammps_map,
            )
            summary["best_reconstruction_xyz"] = xyz_path
        except Exception as exc:
            summary["best_reconstruction_xyz"] = ""
            summary["xyz_error"] = f"{type(exc).__name__}: {exc}"

        log(
            f"{trajectory_id}: {summary['classification']}; "
            f"reference={Path(summary['best_reference']).name}; "
            f"mapping={summary['best_break_mapping']}; "
            f"alignment={summary['best_alignment']}; score={summary['best_score']:.6g}"
        )

    classification = derive_global_classification(trajectory_summaries)
    table_columns = list(rows[0].keys())

    atomic_write_tsv(attempt_dir / "tables/reconstruction_candidates_top_v001.tsv", all_candidates)
    atomic_write_tsv(attempt_dir / "tables/reference_parse_inventory_v001.tsv", all_parse_rows)
    atomic_write_tsv(attempt_dir / "tables/artifact_inventory_v001.tsv", all_artifacts)
    atomic_write_tsv(attempt_dir / "tables/trajectory_summary_v001.tsv", trajectory_summaries)
    atomic_write_tsv(attempt_dir / "tables/script_hashes_v001.tsv", script_rows)
    atomic_write_tsv(attempt_dir / "tables/source_keyword_hits_v001.tsv", keyword_rows)
    atomic_write_text(attempt_dir / "reports/source_logic_context_v001.txt", source_context)

    report = build_report(
        classification, paths, script_rows, trajectory_summaries, table_columns
    )
    atomic_write_text(attempt_dir / "reports/forensic_report_v001.md", report)

    summary_payload = {
        "created_utc": utc_now(),
        "stage": STAGE_NAME,
        "version": SCRIPT_VERSION,
        "classification": classification,
        "scientific_scope": {
            "geometry_provenance_checked": True,
            "offline_grade_recomputed": False,
            "dft_executed": False,
            "md_executed": False,
            "lammps_integrator_steps": 0,
            "mtp_training_executed": False,
            "upstream_modified": False,
        },
        "authoritative_inputs": {
            key: str(value) for key, value in paths.items()
        },
        "provenance_script_sha256": sha256_file(paths["provenance_script"]),
        "trajectory_results": trajectory_summaries,
        "counts": {
            "captured_rows": len(rows),
            "top_candidate_rows": len(all_candidates),
            "reference_parse_rows": len(all_parse_rows),
            "artifact_rows": len(all_artifacts),
            "script_rows": len(script_rows),
            "keyword_hits": len(keyword_rows),
        },
        "limitations": [
            "This audit does not calibrate MaxVol grade against DFT energy or force error.",
            "Exact geometry reconstruction does not by itself prove production MD readiness.",
            "A non-exact result can indicate missing provenance, an inconsistent stored metric, or an untested transformation convention.",
        ],
    }
    atomic_write_json(attempt_dir / "summary_v001.json", summary_payload)

    status = f"PASS_FORENSIC_AUDIT_COMPLETED__{classification}"
    atomic_write_text(attempt_dir / STATUS_NAME, status + "\n")
    generate_checksums(attempt_dir)
    bundle = create_bundle(attempt_dir)
    # Regenerate checksums so the bundle itself is registered.
    generate_checksums(attempt_dir)

    pointer = attempt_root / CURRENT_POINTER_NAME
    atomic_write_text(pointer, str(attempt_dir) + "\n")

    print("============================================================")
    print("FORENSIC AUDIT COMPLETED")
    print("============================================================")
    print(f"CLASSIFICATION={classification}")
    print(f"RUN_DIR={attempt_dir}")
    print(f"STATUS={attempt_dir / STATUS_NAME}")
    print(f"SUMMARY={attempt_dir / 'summary_v001.json'}")
    print(f"REPORT={attempt_dir / 'reports/forensic_report_v001.md'}")
    print(f"TOP_CANDIDATES={attempt_dir / 'tables/reconstruction_candidates_top_v001.tsv'}")
    print(f"SOURCE_CONTEXT={attempt_dir / 'reports/source_logic_context_v001.txt'}")
    print(f"BUNDLE={bundle}")
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

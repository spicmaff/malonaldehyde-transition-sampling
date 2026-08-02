#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import csv
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time

import numpy as np


# =============================================================================
# STEP 29 / v027
#
# Equal-budget DFT labelling:
#   - K selected transition-tube configurations
#   - K matched basin-control configurations
#
# For the current frozen upstream v026 attempt, K = 24, therefore 48
# independent Quantum ESPRESSO pw.x single-point calculations are expected.
#
# Execution:
#   pw.x:       YES in a real run
#   neb.x:      NO
#   mlp:        NO
#   mlp train:  NO
#   LAMMPS:     NO
#
# Every case is calculated from scratch in a unique directory. Cases are run
# sequentially in paired order:
#   targeted_001, basin_001, targeted_002, basin_002, ...
#
# This paired order does not alter either final training-set order. Final
# branch-specific datasets are written according to the pre-registered rule:
#   common36 in frozen existing order, followed by new labels sorted by
#   candidate ID.
# =============================================================================


IMPLEMENTATION_ID = "STEP29_V027_EQUAL_BUDGET_DFT_LABELS_V003"

ROOT = Path.home() / "malonaldehyde_mtp_al"
VERSIONS = ROOT / "09_strict_comparison" / "versions"

ENV_PREFIX = Path.home() / "miniforge3" / "envs" / "malon_mtp"
PW_X = ENV_PREFIX / "bin" / "pw.x"
MPIRUN = ENV_PREFIX / "bin" / "mpirun"
CONDA_LIB = ENV_PREFIX / "lib"

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
V026_POINTER = (
    VERSIONS
    / "v026_fresh_tube_active_selection"
    / "CURRENT_FRESH_TUBE_ACTIVE_SELECTION.txt"
)

VERSION_ROOT = VERSIONS / "v027_equal_budget_dft_labels48"
CURRENT_POINTER = VERSION_ROOT / "CURRENT_EQUAL_BUDGET_DFT_LABELS48.txt"
RUNNING_POINTER = VERSION_ROOT / "CURRENT_RUNNING_EQUAL_BUDGET_DFT_LABELS48.txt"
FAILED_POINTER = VERSION_ROOT / "LAST_FAILED_EQUAL_BUDGET_DFT_LABELS48.txt"
INTERRUPTED_POINTER = VERSION_ROOT / "LAST_INTERRUPTED_EQUAL_BUDGET_DFT_LABELS48.txt"

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"

CASES_DIR = RUN_ROOT / "cases"
INPUTS_DIR = RUN_ROOT / "inputs"
LABELS_DIR = RUN_ROOT / "labels"
DATASETS_DIR = RUN_ROOT / "datasets"
REPORTS_DIR = RUN_ROOT / "reports"
PROVENANCE_DIR = RUN_ROOT / "provenance"
EXTRACTED_DIR = RUN_ROOT / "extracted_force_blocks"

STATUS_FILE = RUN_ROOT / "STATUS_v027.txt"
RUN_LOG = RUN_ROOT / "run_log_v027.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v027.json"
PROGRESS_JSON = RUN_ROOT / "progress_v027.json"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v027.tsv"

CASE_REPORT_TSV = REPORTS_DIR / "equal_budget_dft_cases_v027.tsv"
FORCE_COMPONENTS_TSV = REPORTS_DIR / "equal_budget_force_components_v027.tsv"
SCHEDULE_TSV = REPORTS_DIR / "paired_execution_schedule_v027.tsv"
TARGETED_REPORT_TSV = REPORTS_DIR / "targeted_labels_report_v027.tsv"
BASIN_REPORT_TSV = REPORTS_DIR / "basin_control_labels_report_v027.tsv"
REPORT_MD = REPORTS_DIR / "equal_budget_dft_labels_report_v027.md"

TARGETED_LABELS_CFG = LABELS_DIR / "targeted_new_labels_v027.cfg"
BASIN_LABELS_CFG = LABELS_DIR / "basin_control_new_labels_v027.cfg"
ALL_NEW_LABELS_CFG = LABELS_DIR / "all_equal_budget_new_labels48_v027.cfg"

TRAIN_TARGETED_CFG = DATASETS_DIR / "train_targeted_v001.cfg"
TRAIN_BASIN_CFG = DATASETS_DIR / "train_basin_v001.cfg"


# =============================================================================
# Frozen upstream identifiers and scientific constants
# =============================================================================

EXPECTED_V016_STATUS = "PASS_ALL_DFT_LABELLED_COMMON36"
EXPECTED_V020_STATUS = "PASS_PRE_AUDIT_PROTOCOL_LOCK_NO_CALCULATIONS"
EXPECTED_V026_STATUS = "PASS_FRESH_TUBE_SELECTION_K_FIXED_BASIN_QUEUE_READY"

EXPECTED_COMMON36_SHA256 = (
    "49c8331a88546d964fb9c0fe97bac65729fed228351e7ebee3524d59d7b93cce"
)
EXPECTED_PROTOCOL_SHA256 = (
    "0309ca4ca419458a847f1606759c792f0dfc4019108343e3d5a9721f5704d3b8"
)
EXPECTED_V026_SCRIPT_SHA256 = (
    "67a20a7be46d45f27f505fa230ea30454c42248f2a0791cbb502c3e92095c7f5"
)

NAT = 9
COMMON_COUNT = 36
MAX_K = 24

EXPECTED_SYMBOLS = ["O", "H", "C", "H", "C", "H", "C", "O", "H"]
EXPECTED_MLIP_TYPES = [2, 1, 0, 1, 0, 1, 0, 2, 1]
EXPECTED_QE_TYPES = [3, 2, 1, 2, 1, 2, 1, 3, 2]
EXPECTED_COMPOSITION = Counter({"C": 3, "H": 4, "O": 2})

SYMBOL_TO_MLIP_TYPE = {"C": 0, "H": 1, "O": 2}

RY_TO_EV = 13.605693122994
BOHR_TO_ANG = 0.529177210903
RY_BOHR_TO_EV_ANG = RY_TO_EV / BOHR_TO_ANG

MIN_PAIR_HARD_ANG = 0.65
ROO_MIN_ANG = 2.20
ROO_MAX_ANG = 2.80
MAX_SPAN_HARD_ANG = 5.50
BASIN_QPT_MIN_ABS_ANG = 0.30

CFG_COORDINATE_TOL_ANG = 1.0e-6
CELL_TOL_ANG = 1.0e-8

TOTAL_FORCE_ABS_TOL_RY_BOHR = 2.0e-5
TOTAL_FORCE_REL_TOL = 2.0e-3
NET_FORCE_WARNING_EV_ANG = 1.0e-5
NET_FORCE_HARD_EV_ANG = 1.0e-4
MAX_ATOMIC_FORCE_HARD_EV_ANG = 25.0

MPI_RANKS = 3
OMP_THREADS = 1
MPI_BINDING_ARGS = ["--map-by", "core", "--bind-to", "core"]
PER_CASE_TIMEOUT_SECONDS = 12 * 3600
POLL_INTERVAL_SECONDS = 5.0

RUN_PW = True
RUN_NEB = False
RUN_MLP = False
RUN_MLP_TRAIN = False
RUN_LAMMPS = False

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V027_PREFLIGHT_ONLY", "0") == "1"
)

NUMBER = (
    r"[-+]?"
    r"(?:\d+(?:\.\d*)?|\.\d+)"
    r"(?:[EeDd][-+]?\d+)?"
)

MAIN_FORCE_HEADER_RE = re.compile(
    r"Forces\s+acting\s+on\s+atoms"
    r"\s*\(cartesian\s+axes,\s*Ry/au\)\s*:",
    flags=re.IGNORECASE,
)
ATOM_FORCE_RE = re.compile(
    rf"^\s*atom\s+(\d+)\s+type\s+(\d+)\s+"
    rf"force\s*=\s*"
    rf"({NUMBER})\s+"
    rf"({NUMBER})\s+"
    rf"({NUMBER})\s*$",
    flags=re.IGNORECASE,
)
TOTAL_FORCE_RE = re.compile(
    rf"Total\s+force\s*=\s*({NUMBER})",
    flags=re.IGNORECASE,
)
ENERGY_RE = re.compile(
    rf"!\s+total\s+energy\s*=\s*({NUMBER})\s+Ry",
    flags=re.IGNORECASE,
)
CONTRIBUTION_HEADER_RE = re.compile(
    r"^\s*The\s+.+contrib\.\s+to\s+forces",
    flags=re.IGNORECASE,
)


_ATTEMPT_CREATED = False
_CURRENT_CASE: dict[str, Any] | None = None


@dataclass
class CFGBlock:
    raw: str
    order: int
    size: int
    types: list[int]
    positions: np.ndarray
    cell: np.ndarray | None
    features: dict[str, str]
    atom_columns: list[str]
    energy: float | None


@dataclass
class QueueItem:
    branch: str
    queue_index: int
    candidate_id: str
    source_cfg: Path
    block: CFGBlock
    qpt_ang: float
    roo_ang: float
    minimum_pair_ang: float
    maximum_span_ang: float
    side: str


class SinglePointInterrupted(BaseException):
    def __init__(
        self,
        reason: str,
        global_case_index: int | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.global_case_index = global_case_index
        self.elapsed_seconds = elapsed_seconds


# =============================================================================
# Generic utilities
# =============================================================================


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fatal(message: str) -> None:
    raise RuntimeError(message)


def log(message: str) -> None:
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    if _ATTEMPT_CREATED:
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with RUN_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def parse_number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


def parse_bool_text(text: str) -> bool:
    value = text.strip().strip("'\"").lower()
    if value in {"true", ".true.", "yes", "1"}:
        return True
    if value in {"false", ".false.", "no", "0"}:
        return False
    fatal(f"cannot parse boolean value: {text!r}")


def norm3(vector: Iterable[float]) -> float:
    return math.sqrt(sum(float(component) ** 2 for component in vector))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return value


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        fatal(f"{label} missing: {path}")
    return path


def require_hash(path: Path, expected: str, label: str) -> None:
    actual = sha256(path)
    if actual != expected:
        fatal(
            f"{label} SHA256 mismatch:\n"
            f"expected={expected}\n"
            f"actual={actual}\n"
            f"path={path}"
        )


def resolve_success_attempt(
    pointer: Path,
    status_filename: str,
    expected_status: str,
    label: str,
) -> Path:
    require_file(pointer, f"{label} pointer")
    text = pointer.read_text(encoding="utf-8").strip()
    if not text:
        fatal(f"{label} pointer is empty: {pointer}")
    attempt = Path(text)
    if not attempt.is_dir():
        fatal(f"{label} attempt directory missing: {attempt}")
    status_path = require_file(attempt / status_filename, f"{label} status")
    status = status_path.read_text(encoding="utf-8").strip()
    if status != expected_status:
        fatal(
            f"{label} status mismatch: expected {expected_status!r}, "
            f"found {status!r}"
        )
    return attempt


def read_tsv(path: Path) -> list[dict[str, str]]:
    require_file(path, "TSV")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def cleanup_running_pointer_for_this_attempt() -> None:
    if not RUNNING_POINTER.is_file():
        return
    try:
        pointed = RUNNING_POINTER.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if pointed == str(RUN_ROOT):
        try:
            RUNNING_POINTER.unlink()
        except FileNotFoundError:
            pass


def safe_candidate_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        fatal(f"unsafe candidate ID: {value!r}")
    return value


# =============================================================================
# CFG parsing and writing
# =============================================================================


def split_cfg_text(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None

    for line in text.splitlines(keepends=True):
        stripped = line.strip()

        if stripped == "BEGIN_CFG":
            if current is not None:
                fatal("nested BEGIN_CFG")
            current = [line]
            continue

        if current is not None:
            current.append(line)
            if stripped == "END_CFG":
                raw = "".join(current).rstrip() + "\n"
                blocks.append(raw)
                current = None

    if current is not None:
        fatal("unterminated CFG block")

    return blocks


def parse_cfg_features(raw: str) -> dict[str, str]:
    """
    Parse MLIP Feature metadata with one narrowly defined provenance upgrade.

    The successful v026 queue writer first materialized candidates with

        Feature version v026_corrected

    and later appended queue metadata containing

        Feature version v026

    without deleting the earlier provenance tag. This exact ordered transition
    is therefore a known upstream serialization artefact, not an ambiguous
    scientific conflict. It is canonicalized to ``version = v026``.

    Accepted duplicate cases:
      1. byte-equivalent repeated values for any key;
      2. only for key ``version``: v026_corrected -> v026.

    Every other conflicting duplicate remains a hard failure.
    """
    features: dict[str, str] = {}
    pattern = re.compile(r"^\s*Feature\s+(\S+)\s+(.*?)\s*$")

    for line_number, line in enumerate(raw.splitlines(), start=1):
        match = pattern.match(line)
        if not match:
            continue

        key = match.group(1)
        value = match.group(2).strip()

        if key not in features:
            features[key] = value
            continue

        previous = features[key]

        if value == previous:
            # Identical duplicate: retain the canonical value.
            continue

        if (
            key == "version"
            and previous == "v026_corrected"
            and value == "v026"
        ):
            # Known v026 materialization -> DFT-queue provenance upgrade.
            features[key] = "v026"
            continue

        fatal(
            f"conflicting duplicate CFG Feature {key}: "
            f"first={previous!r}, repeated={value!r}, "
            f"line={line_number}"
        )

    return features


def parse_cfg_block(raw: str, order: int) -> CFGBlock:
    lines = raw.splitlines()
    features = parse_cfg_features(raw)

    size: int | None = None
    types: list[int] | None = None
    positions: np.ndarray | None = None
    cell: np.ndarray | None = None
    atom_columns: list[str] = []
    energy: float | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped == "Size":
            if index + 1 >= len(lines):
                fatal("CFG Size value missing")
            size = int(lines[index + 1].strip())

        elif stripped == "Supercell":
            if index + 3 >= len(lines):
                fatal("CFG Supercell rows missing")
            cell = np.asarray(
                [
                    [parse_number(value) for value in lines[index + offset].split()[:3]]
                    for offset in (1, 2, 3)
                ],
                dtype=float,
            )

        elif stripped.startswith("AtomData:"):
            if size is None:
                fatal("CFG AtomData appears before Size")
            atom_columns = stripped.split(":", 1)[1].split()
            required = {"id", "type", "cartes_x", "cartes_y", "cartes_z"}
            if not required.issubset(atom_columns):
                fatal(f"CFG AtomData columns missing: {atom_columns}")

            lookup = {name: atom_columns.index(name) for name in atom_columns}
            parsed_types: list[int] = []
            parsed_positions: list[list[float]] = []
            parsed_ids: list[int] = []

            for atom_offset in range(size):
                row_index = index + 1 + atom_offset
                if row_index >= len(lines):
                    fatal("CFG AtomData truncated")
                fields = lines[row_index].split()
                if len(fields) < len(atom_columns):
                    fatal(f"CFG AtomData row too short: {lines[row_index]!r}")
                parsed_ids.append(int(fields[lookup["id"]]))
                parsed_types.append(int(fields[lookup["type"]]))
                parsed_positions.append(
                    [
                        parse_number(fields[lookup["cartes_x"]]),
                        parse_number(fields[lookup["cartes_y"]]),
                        parse_number(fields[lookup["cartes_z"]]),
                    ]
                )

            if parsed_ids != list(range(1, size + 1)):
                fatal(f"CFG atom IDs are not 1..N: {parsed_ids}")

            types = parsed_types
            positions = np.asarray(parsed_positions, dtype=float)

        elif stripped == "Energy":
            if index + 1 >= len(lines):
                fatal("CFG Energy value missing")
            energy = parse_number(lines[index + 1].strip())

    if size != NAT:
        fatal(f"CFG size={size}, expected {NAT}")
    if types is None or positions is None:
        fatal("CFG AtomData missing")
    if positions.shape != (NAT, 3):
        fatal(f"CFG coordinate shape mismatch: {positions.shape}")
    if not np.all(np.isfinite(positions)):
        fatal("CFG contains nonfinite positions")
    if cell is None:
        fatal("CFG Supercell missing")
    if cell.shape != (3, 3) or not np.all(np.isfinite(cell)):
        fatal("CFG Supercell invalid")

    return CFGBlock(
        raw=raw,
        order=order,
        size=size,
        types=types,
        positions=positions,
        cell=cell,
        features=features,
        atom_columns=atom_columns,
        energy=energy,
    )


def read_cfg(path: Path) -> list[CFGBlock]:
    require_file(path, "CFG")
    raw_blocks = split_cfg_text(path.read_text(encoding="utf-8"))
    return [
        parse_cfg_block(raw, order=index)
        for index, raw in enumerate(raw_blocks, start=1)
    ]


def write_raw_cfg(path: Path, raw_blocks: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for raw in raw_blocks:
            handle.write(raw.rstrip() + "\n\n")


def candidate_id_from_block(block: CFGBlock) -> str:
    candidate_id = block.features.get("candidate_id", "").strip()
    if not candidate_id:
        fatal(f"CFG block {block.order} lacks candidate_id")
    return safe_candidate_id(candidate_id)


def geometry_metrics(coordinates: np.ndarray) -> dict[str, Any]:
    distances: dict[tuple[int, int], float] = {}
    for first in range(NAT):
        for second in range(first + 1, NAT):
            distances[(first + 1, second + 1)] = float(
                np.linalg.norm(coordinates[first] - coordinates[second])
            )

    minimum_pair, minimum_distance = min(
        distances.items(),
        key=lambda item: item[1],
    )

    r_o1_h = distances[(1, 2)]
    r_h_o2 = distances[(2, 8)]
    roo = distances[(1, 8)]

    return {
        "qpt_ang": r_o1_h - r_h_o2,
        "roo_ang": roo,
        "minimum_pair": minimum_pair,
        "minimum_pair_ang": minimum_distance,
        "maximum_span_ang": max(distances.values()),
        "fingerprint": np.asarray(
            [distances[pair] for pair in sorted(distances)],
            dtype=float,
        ),
    }


def validate_cell(cell: np.ndarray, role: str) -> None:
    expected = np.diag([16.0, 16.0, 16.0])
    maximum_difference = float(np.max(np.abs(cell - expected)))
    if maximum_difference > CELL_TOL_ANG:
        fatal(
            f"{role}: cell differs from 16 A cube by "
            f"{maximum_difference:.3e} A"
        )


def validate_queue_block(
    block: CFGBlock,
    branch: str,
    expected_index: int,
    expected_k: int,
    source_path: Path,
) -> QueueItem:
    candidate_id = candidate_id_from_block(block)

    if block.types != EXPECTED_MLIP_TYPES:
        fatal(
            f"{branch} {candidate_id}: MLIP atom types changed: {block.types}"
        )

    validate_cell(block.cell, f"{branch} {candidate_id}")

    if block.energy is not None:
        fatal(f"{branch} {candidate_id}: queue CFG unexpectedly already has Energy")

    if any(column in block.atom_columns for column in ("fx", "fy", "fz")):
        fatal(f"{branch} {candidate_id}: queue CFG unexpectedly already has forces")

    feature_index = int(block.features.get("dft_queue_index", "0"))
    if feature_index != expected_index:
        fatal(
            f"{branch} {candidate_id}: dft_queue_index={feature_index}, "
            f"expected {expected_index}"
        )

    feature_k = int(block.features.get("equal_budget_K", "0"))
    if feature_k != expected_k:
        fatal(
            f"{branch} {candidate_id}: equal_budget_K={feature_k}, "
            f"expected {expected_k}"
        )

    if not parse_bool_text(block.features.get("selected_for_dft", "false")):
        fatal(f"{branch} {candidate_id}: selected_for_dft is not true")

    if not parse_bool_text(
        block.features.get("training_eligible_after_dft", "false")
    ):
        fatal(
            f"{branch} {candidate_id}: training_eligible_after_dft is not true"
        )

    canonical_version = block.features.get("version", "").strip()
    if canonical_version != "v026":
        fatal(
            f"{branch} {candidate_id}: canonical Feature version="
            f"{canonical_version!r}, expected 'v026'"
        )

    role = block.features.get("dft_queue_role", "").strip()
    expected_role = (
        "targeted_tube"
        if branch == "targeted"
        else "equal_budget_basin_control"
    )
    if role != expected_role:
        fatal(
            f"{branch} {candidate_id}: dft_queue_role={role!r}, "
            f"expected {expected_role!r}"
        )

    if branch == "targeted":
        if not candidate_id.startswith("tube_"):
            fatal(f"targeted candidate ID is not a tube ID: {candidate_id}")
        side = "transition"
    else:
        expected_prefix = "basin_control_"
        if not candidate_id.startswith(expected_prefix):
            fatal(f"basin candidate ID has wrong prefix: {candidate_id}")
        side = block.features.get("side", "").strip().lower()
        if side not in {"left", "right"}:
            match = re.match(r"basin_control_(left|right)_", candidate_id)
            if not match:
                fatal(f"cannot determine basin side for {candidate_id}")
            side = match.group(1)

    current_metrics = geometry_metrics(block.positions)

    reasons: list[str] = []
    if current_metrics["minimum_pair_ang"] <= MIN_PAIR_HARD_ANG:
        reasons.append(
            f"minimum_pair={current_metrics['minimum_pair_ang']:.8f}"
        )
    if not ROO_MIN_ANG < current_metrics["roo_ang"] < ROO_MAX_ANG:
        reasons.append(f"R_OO={current_metrics['roo_ang']:.8f}")
    if current_metrics["maximum_span_ang"] >= MAX_SPAN_HARD_ANG:
        reasons.append(
            f"maximum_span={current_metrics['maximum_span_ang']:.8f}"
        )

    if branch == "basin":
        if side == "left" and current_metrics["qpt_ang"] >= -BASIN_QPT_MIN_ABS_ANG:
            reasons.append(f"left_qPT={current_metrics['qpt_ang']:.8f}")
        if side == "right" and current_metrics["qpt_ang"] <= BASIN_QPT_MIN_ABS_ANG:
            reasons.append(f"right_qPT={current_metrics['qpt_ang']:.8f}")

    if reasons:
        fatal(
            f"{branch} {candidate_id} failed geometry validation: "
            + "; ".join(reasons)
        )

    return QueueItem(
        branch=branch,
        queue_index=expected_index,
        candidate_id=candidate_id,
        source_cfg=source_path,
        block=block,
        qpt_ang=current_metrics["qpt_ang"],
        roo_ang=current_metrics["roo_ang"],
        minimum_pair_ang=current_metrics["minimum_pair_ang"],
        maximum_span_ang=current_metrics["maximum_span_ang"],
        side=side,
    )


def read_queue_directory(
    directory: Path,
    branch: str,
    k: int,
) -> list[QueueItem]:
    if not directory.is_dir():
        fatal(f"{branch} queue directory missing: {directory}")

    files = sorted(directory.glob("*.cfg"))
    if len(files) != k:
        fatal(
            f"{branch} queue contains {len(files)} CFG files, expected {k}"
        )

    items: list[QueueItem] = []

    for expected_index, path in enumerate(files, start=1):
        blocks = read_cfg(path)
        if len(blocks) != 1:
            fatal(f"{path}: expected one CFG block, found {len(blocks)}")

        filename_match = re.match(r"^(\d{3})_(.+)\.cfg$", path.name)
        if not filename_match:
            fatal(f"unexpected queue filename: {path.name}")

        filename_index = int(filename_match.group(1))
        if filename_index != expected_index:
            fatal(
                f"{path.name}: filename queue index {filename_index}, "
                f"expected {expected_index}"
            )

        item = validate_queue_block(
            blocks[0],
            branch=branch,
            expected_index=expected_index,
            expected_k=k,
            source_path=path,
        )

        if filename_match.group(2) != item.candidate_id:
            fatal(
                f"{path.name}: filename candidate ID differs from CFG "
                f"{item.candidate_id}"
            )

        items.append(item)

    candidate_ids = [item.candidate_id for item in items]
    if candidate_ids != sorted(candidate_ids):
        fatal(f"{branch} queue is not sorted by candidate ID")
    if len(set(candidate_ids)) != k:
        fatal(f"{branch} queue has duplicate candidate IDs")

    return items


def compare_queue_to_combined(
    items: list[QueueItem],
    combined_cfg: Path,
    branch: str,
) -> None:
    combined_blocks = read_cfg(combined_cfg)
    if len(combined_blocks) != len(items):
        fatal(
            f"{branch} combined CFG has {len(combined_blocks)} blocks, "
            f"queue has {len(items)}"
        )

    by_id = {candidate_id_from_block(block): block for block in combined_blocks}
    if len(by_id) != len(combined_blocks):
        fatal(f"{branch} combined CFG has duplicate candidate IDs")

    if set(by_id) != {item.candidate_id for item in items}:
        fatal(f"{branch} combined CFG candidate set differs from queue")

    for item in items:
        reference = by_id[item.candidate_id]
        if reference.types != item.block.types:
            fatal(f"{branch} {item.candidate_id}: type mismatch with combined CFG")
        maximum_difference = float(
            np.max(np.abs(reference.positions - item.block.positions))
        )
        if maximum_difference > CFG_COORDINATE_TOL_ANG:
            fatal(
                f"{branch} {item.candidate_id}: queue/combined geometry "
                f"difference={maximum_difference:.3e} A"
            )


def geometry_fingerprint_rms(first: np.ndarray, second: np.ndarray) -> float:
    first_fp = geometry_metrics(first)["fingerprint"]
    second_fp = geometry_metrics(second)["fingerprint"]
    return float(np.sqrt(np.mean((first_fp - second_fp) ** 2)))


def write_label_cfg(
    path: Path,
    records: list[dict[str, Any]],
    cell: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write("BEGIN_CFG\n")
            handle.write(" Size\n")
            handle.write(f"    {NAT}\n")
            handle.write(" Supercell\n")
            for vector in cell:
                handle.write(
                    f"    {vector[0]:.16g} "
                    f"{vector[1]:.16g} "
                    f"{vector[2]:.16g}\n"
                )

            handle.write(
                " AtomData:  id type cartes_x cartes_y cartes_z fx fy fz\n"
            )

            for atom_index, (
                symbol,
                coordinate,
                force,
            ) in enumerate(
                zip(
                    EXPECTED_SYMBOLS,
                    record["coordinates_ang"],
                    record["forces_ev_ang"],
                ),
                start=1,
            ):
                handle.write(
                    f"    {atom_index:4d} "
                    f"{SYMBOL_TO_MLIP_TYPE[symbol]:2d} "
                    f"{coordinate[0]:.16g} "
                    f"{coordinate[1]:.16g} "
                    f"{coordinate[2]:.16g} "
                    f"{force[0]:.16g} "
                    f"{force[1]:.16g} "
                    f"{force[2]:.16g}\n"
                )

            handle.write(" Energy\n")
            handle.write(f"    {record['energy_ev']:.16g}\n")

            features = {
                "branch": record["branch"],
                "candidate_id": record["candidate_id"],
                "dft_case_index": record["branch_case_index"],
                "dft_global_case_index": record["global_case_index"],
                "dft_protocol_version": "v005",
                "dft_status": "PASS_INDEPENDENT_SINGLE_POINT",
                "equal_budget_K": record["equal_budget_k"],
                "force_parser_version": "v023_main_complete_force_block",
                "max_atomic_force_eV_A":
                    f"{record['maximum_atomic_force_ev_ang']:.12f}",
                "q_pt_A": f"{record['qpt_ang']:.12f}",
                "r_oo_A": f"{record['roo_ang']:.12f}",
                "single_point_version": "v027",
                "source_selection_version": "v026",
                "training_eligible": "true",
                "true_net_force_norm_eV_A":
                    f"{record['net_force_norm_ev_ang']:.12e}",
            }

            if record["branch"] == "basin":
                features["side"] = record["side"]

            for key in sorted(features):
                handle.write(f" Feature   {key} {features[key]}\n")

            handle.write("END_CFG\n\n")


def label_records_to_raw(
    records: list[dict[str, Any]],
    cell: np.ndarray,
) -> list[str]:
    temporary = RUN_ROOT / "_temporary_label_serialization.cfg"
    write_label_cfg(temporary, records, cell)
    raw = split_cfg_text(temporary.read_text(encoding="utf-8"))
    temporary.unlink()
    return raw


# =============================================================================
# QE input validation and rendering
# =============================================================================


def locate_namelist(lines: list[str], name: str) -> tuple[int, int]:
    wanted = f"&{name.upper()}"
    starts = [
        index
        for index, line in enumerate(lines)
        if line.strip().upper() == wanted
    ]
    if len(starts) != 1:
        fatal(f"expected exactly one {wanted}, found {len(starts)}")
    start = starts[0]
    for index in range(start + 1, len(lines)):
        if lines[index].strip() == "/":
            return start, index
    fatal(f"unterminated {wanted}")


def parse_namelist_assignments(
    lines: list[str],
    name: str,
) -> dict[str, str]:
    start, end = locate_namelist(lines, name)
    assignments: dict[str, str] = {}
    pattern = re.compile(
        r"^\s*([A-Za-z_][A-Za-z0-9_]*(?:\([^)]*\))?)"
        r"\s*=\s*(.*?)\s*,?\s*$"
    )

    for line in lines[start + 1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("!"):
            continue
        match = pattern.match(line)
        if not match:
            fatal(f"unsupported line in &{name.upper()}: {line!r}")
        key = match.group(1).lower()
        if key in assignments:
            fatal(f"duplicate {key} in &{name.upper()}")
        assignments[key] = match.group(2).strip()

    return assignments


def unquote(value: str) -> str:
    stripped = value.strip()
    if (
        len(stripped) >= 2
        and stripped[0] in {"'", '"'}
        and stripped[-1] == stripped[0]
    ):
        return stripped[1:-1]
    return stripped


def parse_fortran_bool(value: str) -> bool:
    normalized = unquote(value).strip().lower()
    if normalized in {".true.", "true", "t", "1"}:
        return True
    if normalized in {".false.", "false", "f", "0"}:
        return False
    fatal(f"invalid Fortran logical value: {value!r}")


def parse_card_unit(header: str, default: str = "alat") -> str:
    parenthesized = re.search(r"\(([^)]+)\)", header)
    if parenthesized:
        return parenthesized.group(1).strip()
    fields = header.split()
    if len(fields) >= 2:
        return fields[1].strip().strip("{}()")
    return default


def parse_cell_matrix_angstrom(lines: list[str]) -> np.ndarray:
    starts = [
        index
        for index, line in enumerate(lines)
        if line.strip().upper().startswith("CELL_PARAMETERS")
    ]
    if len(starts) != 1:
        fatal(
            "canonical PW input must contain exactly one CELL_PARAMETERS card"
        )

    start = starts[0]
    header = lines[start].lower()
    raw = np.asarray(
        [
            [parse_number(value) for value in lines[start + offset].split()[:3]]
            for offset in (1, 2, 3)
        ],
        dtype=float,
    )

    if "angstrom" in header:
        factor = 1.0
    elif "bohr" in header:
        factor = BOHR_TO_ANG
    elif "alat" in header:
        system = parse_namelist_assignments(lines, "SYSTEM")
        if "celldm(1)" not in system:
            fatal("CELL_PARAMETERS alat requires celldm(1)")
        factor = parse_number(system["celldm(1)"]) * BOHR_TO_ANG
    else:
        fatal(f"unsupported CELL_PARAMETERS unit: {lines[start]!r}")

    return raw * factor


def locate_atomic_positions_card(
    lines: list[str],
) -> tuple[int, int, str]:
    starts = [
        index
        for index, line in enumerate(lines)
        if line.strip().upper().startswith("ATOMIC_POSITIONS")
    ]
    if len(starts) != 1:
        fatal(
            "canonical PW input must contain exactly one ATOMIC_POSITIONS card"
        )
    start = starts[0]
    end = start + 1 + NAT
    if end > len(lines):
        fatal("truncated ATOMIC_POSITIONS card")
    return start, end, lines[start].strip()


def validate_canonical_pw_source(path: Path) -> dict[str, Any]:
    lines = require_file(path, "canonical PW input").read_text(
        encoding="utf-8"
    ).splitlines()

    control = parse_namelist_assignments(lines, "CONTROL")
    system = parse_namelist_assignments(lines, "SYSTEM")
    electrons = parse_namelist_assignments(lines, "ELECTRONS")

    if unquote(control.get("calculation", "")).lower() != "scf":
        fatal("canonical calculation is not scf")
    if "pseudo_dir" not in control:
        fatal("canonical CONTROL lacks pseudo_dir")

    pseudo_dir = Path(unquote(control["pseudo_dir"])).expanduser()
    if not pseudo_dir.is_dir():
        fatal(f"canonical pseudo_dir missing: {pseudo_dir}")

    integer_expectations = {
        "ibrav": 0,
        "nat": NAT,
        "ntyp": 3,
        "nspin": 1,
    }
    for key, expected in integer_expectations.items():
        if key not in system:
            fatal(f"canonical SYSTEM lacks {key}")
        actual = int(round(parse_number(system[key])))
        if actual != expected:
            fatal(f"canonical {key}={actual}, expected {expected}")

    numeric_expectations = {
        "ecutwfc": 80.0,
        "ecutrho": 960.0,
        "tot_charge": 0.0,
    }
    for key, expected in numeric_expectations.items():
        if key not in system:
            fatal(f"canonical SYSTEM lacks {key}")
        actual = parse_number(system[key])
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-10):
            fatal(f"canonical {key}={actual}, expected {expected}")

    if unquote(system.get("occupations", "")).lower() != "fixed":
        fatal("canonical occupations is not fixed")
    if unquote(system.get("input_dft", "")).upper() != "PBE":
        fatal("canonical input_dft is not PBE")
    if not parse_fortran_bool(system.get("nosym", "")):
        fatal("canonical nosym is not true")
    if not parse_fortran_bool(system.get("noinv", "")):
        fatal("canonical noinv is not true")

    if not math.isclose(
        parse_number(electrons.get("conv_thr", "nan")),
        1.0e-10,
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        fatal("canonical conv_thr is not 1.0e-10")
    if int(round(parse_number(electrons.get("electron_maxstep", "0")))) != 200:
        fatal("canonical electron_maxstep is not 200")
    if unquote(electrons.get("mixing_mode", "")).lower() != "plain":
        fatal("canonical mixing_mode is not plain")
    if not math.isclose(
        parse_number(electrons.get("mixing_beta", "nan")),
        0.30,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        fatal("canonical mixing_beta is not 0.30")
    if unquote(electrons.get("diagonalization", "")).lower() != "david":
        fatal("canonical diagonalization is not david")

    for key in ("startingpot", "startingwfc"):
        if key in electrons and unquote(electrons[key]).lower() == "file":
            fatal(f"canonical {key}='file' violates from-scratch SP")

    species_starts = [
        index
        for index, line in enumerate(lines)
        if line.strip().upper() == "ATOMIC_SPECIES"
    ]
    if len(species_starts) != 1:
        fatal("canonical input must contain one ATOMIC_SPECIES card")

    species_lines = lines[species_starts[0] + 1:species_starts[0] + 4]
    species_symbols: list[str] = []
    for line in species_lines:
        fields = line.split()
        if len(fields) < 3:
            fatal(f"invalid ATOMIC_SPECIES row: {line!r}")
        species_symbols.append(fields[0])
        pseudo_path = pseudo_dir / fields[2]
        if not pseudo_path.is_file():
            fatal(f"pseudopotential missing: {pseudo_path}")

    if species_symbols != ["C", "H", "O"]:
        fatal(f"unexpected ATOMIC_SPECIES order: {species_symbols}")

    k_points = [
        line
        for line in lines
        if re.match(r"^\s*K_POINTS\s+gamma\s*$", line, re.IGNORECASE)
    ]
    if len(k_points) != 1:
        fatal("canonical input does not have exactly one K_POINTS gamma")

    cell = parse_cell_matrix_angstrom(lines)
    validate_cell(cell, "canonical PW input")

    _, _, position_header = locate_atomic_positions_card(lines)
    position_unit = parse_card_unit(position_header)
    if position_unit.lower() not in {
        "angstrom", "ang", "bohr", "au", "a.u.", "alat", "crystal"
    }:
        fatal(f"unsupported canonical coordinate unit: {position_unit}")

    return {
        "pseudo_dir": pseudo_dir,
        "cell_ang": cell,
        "source_sha256": sha256(path),
        "system": system,
        "electrons": electrons,
    }


def render_control_block(pseudo_dir: str, prefix: str) -> list[str]:
    escaped_pseudo = pseudo_dir.replace("'", "''")
    escaped_prefix = prefix.replace("'", "''")
    return [
        "&CONTROL",
        "  calculation = 'scf',",
        "  restart_mode = 'from_scratch',",
        f"  prefix = '{escaped_prefix}',",
        f"  pseudo_dir = '{escaped_pseudo}',",
        "  outdir = './tmp',",
        "  tprnfor = .true.,",
        "  tstress = .false.,",
        "  disk_io = 'low',",
        "  verbosity = 'high',",
        "/",
    ]


def render_single_point_input(
    canonical_input: Path,
    coordinates_ang: np.ndarray,
    prefix: str,
) -> str:
    lines = canonical_input.read_text(encoding="utf-8").splitlines()

    control = parse_namelist_assignments(lines, "CONTROL")
    pseudo_dir = unquote(control["pseudo_dir"])

    control_start, control_end = locate_namelist(lines, "CONTROL")
    positions_start, positions_end, _ = locate_atomic_positions_card(lines)

    if control_start > positions_start:
        fatal("unexpected canonical PW card order")

    new_lines: list[str] = []
    new_lines.extend(lines[:control_start])
    new_lines.extend(render_control_block(pseudo_dir, prefix))
    new_lines.extend(lines[control_end + 1:positions_start])
    new_lines.append("ATOMIC_POSITIONS (angstrom)")

    for symbol, coordinate in zip(EXPECTED_SYMBOLS, coordinates_ang):
        new_lines.append(
            f"{symbol:<2s} "
            f"{coordinate[0]: .14f} "
            f"{coordinate[1]: .14f} "
            f"{coordinate[2]: .14f}"
        )

    new_lines.extend(lines[positions_end:])
    text = "\n".join(new_lines).rstrip() + "\n"

    validate_rendered_single_point_input(
        text,
        expected_prefix=prefix,
        expected_coordinates_ang=coordinates_ang,
    )
    return text


def validate_rendered_single_point_input(
    text: str,
    expected_prefix: str,
    expected_coordinates_ang: np.ndarray,
) -> None:
    lines = text.splitlines()
    control = parse_namelist_assignments(lines, "CONTROL")

    expected_text = {
        "calculation": "scf",
        "restart_mode": "from_scratch",
        "prefix": expected_prefix,
        "outdir": "./tmp",
        "disk_io": "low",
        "verbosity": "high",
    }

    for key, expected in expected_text.items():
        if key not in control:
            fatal(f"rendered CONTROL lacks {key}")
        actual = unquote(control[key])
        if actual.lower() != expected.lower():
            fatal(
                f"rendered CONTROL {key}={actual!r}, expected {expected!r}"
            )

    if not parse_fortran_bool(control.get("tprnfor", "")):
        fatal("rendered CONTROL tprnfor is not true")
    if parse_fortran_bool(control.get("tstress", "")):
        fatal("rendered CONTROL tstress is not false")

    if re.search(r"outdir\s*=\s*['\"]\./tmp['\"]\s*/", text):
        fatal("rendered input contains malformed outdir syntax")

    start, end, header = locate_atomic_positions_card(lines)
    if "angstrom" not in header.lower():
        fatal("rendered positions are not angstrom")

    symbols: list[str] = []
    parsed_coordinates: list[list[float]] = []

    for line in lines[start + 1:end]:
        fields = line.split()
        if len(fields) < 4:
            fatal(f"invalid rendered coordinate row: {line!r}")
        symbols.append(fields[0])
        parsed_coordinates.append(
            [
                parse_number(fields[1]),
                parse_number(fields[2]),
                parse_number(fields[3]),
            ]
        )

    if symbols != EXPECTED_SYMBOLS:
        fatal(f"rendered atom order mismatch: {symbols}")

    parsed = np.asarray(parsed_coordinates, dtype=float)
    maximum_difference = float(
        np.max(np.abs(parsed - expected_coordinates_ang))
    )
    if maximum_difference > 1.0e-10:
        fatal(
            f"rendered coordinates changed by {maximum_difference:.3e} A"
        )


# =============================================================================
# MPI environment and pw.x execution
# =============================================================================


def build_qe_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["OMP_NUM_THREADS"] = str(OMP_THREADS)
    environment["OPENBLAS_NUM_THREADS"] = "1"
    environment["MKL_NUM_THREADS"] = "1"
    environment["BLIS_NUM_THREADS"] = "1"
    environment["VECLIB_MAXIMUM_THREADS"] = "1"
    environment["NUMEXPR_NUM_THREADS"] = "1"
    environment["LD_LIBRARY_PATH"] = str(CONDA_LIB)
    return environment


def validate_mpi_stack() -> dict[str, Any]:
    for executable in (PW_X, MPIRUN):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            fatal(f"required executable missing: {executable}")

    ldd_result = subprocess.run(
        ["ldd", str(PW_X)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        env=build_qe_environment(),
    )
    if ldd_result.returncode != 0:
        fatal(f"ldd failed for pw.x: {ldd_result.stderr.strip()}")

    conda_lib_resolved = CONDA_LIB.resolve()
    mpi_lines = [
        line.strip()
        for line in ldd_result.stdout.splitlines()
        if re.search(r"libmpi(?:_|\.)|libopen-pal|libpmix", line)
    ]
    if not mpi_lines:
        fatal("pw.x ldd output contains no MPI libraries")

    wrong_linkages: list[str] = []
    resolved_linkages: list[tuple[str, Path]] = []

    for line in mpi_lines:
        match = re.search(r"=>\s+(\S+)", line)
        if match is None or match.group(1) == "not":
            fatal(f"unable to resolve MPI linkage: {line}")
        linked_path = Path(match.group(1)).resolve()
        resolved_linkages.append((line, linked_path))
        if not (
            linked_path == conda_lib_resolved
            or conda_lib_resolved in linked_path.parents
        ):
            wrong_linkages.append(f"{line}\n  resolved={linked_path}")

    if wrong_linkages:
        fatal(
            "pw.x is linked outside conda MPI:\n"
            + "\n".join(wrong_linkages)
        )

    if not any(
        "libmpi.so" in line
        and (
            linked_path == conda_lib_resolved
            or conda_lib_resolved in linked_path.parents
        )
        for line, linked_path in resolved_linkages
    ):
        fatal("conda libmpi.so not found in pw.x linkage")

    version_result = subprocess.run(
        [str(MPIRUN), "--version"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        env=build_qe_environment(),
    )
    if version_result.returncode != 0:
        fatal("conda mpirun --version failed")

    version_text = (
        version_result.stdout + "\n" + version_result.stderr
    ).strip()
    if "Open MPI" not in version_text:
        fatal(f"unexpected MPI launcher: {version_text}")

    smoke_command = [
        str(MPIRUN),
        "-np", str(MPI_RANKS),
        *MPI_BINDING_ARGS,
        "/bin/bash", "-lc",
        "printf '%s\\n' \"${OMPI_COMM_WORLD_RANK:?}\"",
    ]
    smoke_result = subprocess.run(
        smoke_command,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
        env=build_qe_environment(),
    )
    if smoke_result.returncode != 0:
        fatal(
            "MPI smoke test failed:\n"
            f"stdout:\n{smoke_result.stdout}\n"
            f"stderr:\n{smoke_result.stderr}"
        )

    ranks = sorted(
        int(line.strip())
        for line in smoke_result.stdout.splitlines()
        if line.strip().isdigit()
    )
    if ranks != list(range(MPI_RANKS)):
        fatal(f"MPI smoke test returned ranks {ranks}")

    return {
        "pw_x": PW_X,
        "mpirun": MPIRUN,
        "mpi_version": version_text.splitlines()[0],
        "mpi_ranks": MPI_RANKS,
        "omp_threads": OMP_THREADS,
        "binding_args": MPI_BINDING_ARGS,
        "smoke_test_ranks": ranks,
        "ld_library_path": str(CONDA_LIB),
    }


def terminate_process_group(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return

    for sig, timeout in (
        (signal.SIGINT, 20),
        (signal.SIGTERM, 20),
        (signal.SIGKILL, 20),
    ):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            continue


def run_single_point(
    case_dir: Path,
    global_case_index: int,
) -> tuple[int, float, list[str]]:
    input_path = case_dir / "pw_v027.in"
    output_path = case_dir / "pw_v027.out"
    error_path = case_dir / "pw_v027.err"

    command = [
        str(MPIRUN),
        "-np", str(MPI_RANKS),
        *MPI_BINDING_ARGS,
        str(PW_X),
        "-in", input_path.name,
    ]

    start = time.monotonic()

    with output_path.open("w", encoding="utf-8") as stdout_handle, \
         error_path.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            command,
            cwd=case_dir,
            stdout=stdout_handle,
            stderr=stderr_handle,
            env=build_qe_environment(),
            text=True,
            start_new_session=True,
        )

        try:
            while True:
                returncode = process.poll()
                if returncode is not None:
                    return (
                        returncode,
                        time.monotonic() - start,
                        command,
                    )

                elapsed = time.monotonic() - start
                if elapsed > PER_CASE_TIMEOUT_SECONDS:
                    terminate_process_group(process)
                    fatal(
                        f"global case {global_case_index}: pw.x timeout "
                        f"after {elapsed / 3600:.3f} h"
                    )

                time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt as error:
            terminate_process_group(process)
            elapsed = time.monotonic() - start
            raise SinglePointInterrupted(
                reason="SIGINT",
                global_case_index=global_case_index,
                elapsed_seconds=elapsed,
            ) from error


# =============================================================================
# Main complete-force-block parser inherited from corrected v023 logic
# =============================================================================


def find_main_force_blocks(lines: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    for header_index, line in enumerate(lines):
        if not MAIN_FORCE_HEADER_RE.search(line):
            continue

        forces: list[dict[str, Any]] = []
        end_index: int | None = None

        for index in range(header_index + 1, len(lines)):
            candidate = lines[index]

            if (
                index > header_index + 1
                and MAIN_FORCE_HEADER_RE.search(candidate)
            ):
                break

            if CONTRIBUTION_HEADER_RE.match(candidate):
                end_index = index
                break

            match = ATOM_FORCE_RE.match(candidate)
            if not match:
                continue

            forces.append(
                {
                    "atom_index": int(match.group(1)),
                    "qe_type": int(match.group(2)),
                    "force_ry_bohr": [
                        parse_number(match.group(3)),
                        parse_number(match.group(4)),
                        parse_number(match.group(5)),
                    ],
                    "source_line_number": index + 1,
                    "source_line": candidate,
                }
            )

            if len(forces) == NAT:
                end_index = index + 1
                break

        if len(forces) != NAT:
            fatal(
                f"force block at line {header_index + 1} contains "
                f"{len(forces)} atomic force rows"
            )

        atom_indices = [item["atom_index"] for item in forces]
        qe_types = [item["qe_type"] for item in forces]

        if atom_indices != list(range(1, NAT + 1)):
            fatal(f"force-block atom order mismatch: {atom_indices}")
        if qe_types != EXPECTED_QE_TYPES:
            fatal(f"force-block QE type mismatch: {qe_types}")

        blocks.append(
            {
                "header_line_index": header_index,
                "header_line_number": header_index + 1,
                "end_line_index": end_index,
                "forces": forces,
            }
        )

    return blocks


def find_reported_total_force(
    lines: list[str],
    block: dict[str, Any],
) -> tuple[float, int]:
    start = int(
        block["end_line_index"]
        or block["header_line_index"] + NAT + 1
    )

    for index in range(start, len(lines)):
        line = lines[index]
        if index > start and MAIN_FORCE_HEADER_RE.search(line):
            break
        match = TOTAL_FORCE_RE.search(line)
        if match:
            return parse_number(match.group(1)), index + 1

    fatal(
        "QE Total force line missing after main force block at "
        f"line {block['header_line_number']}"
    )


def parse_pw_output(output_path: Path) -> dict[str, Any]:
    if not output_path.is_file():
        fatal(f"PW output missing: {output_path}")

    text = output_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    if "JOB DONE." not in text:
        fatal(f"{output_path}: JOB DONE missing")

    if re.search(
        r"convergence\s+NOT\s+achieved",
        text,
        flags=re.IGNORECASE,
    ):
        fatal(f"{output_path}: SCF convergence NOT achieved")

    if not (
        re.search(
            r"convergence\s+has\s+been\s+achieved",
            text,
            flags=re.IGNORECASE,
        )
        or re.search(
            r"End\s+of\s+self-consistent\s+calculation",
            text,
            flags=re.IGNORECASE,
        )
    ):
        fatal(f"{output_path}: SCF completion marker missing")

    energy_matches = ENERGY_RE.findall(text)
    if not energy_matches:
        fatal(f"{output_path}: total energy missing")

    energy_ry = parse_number(energy_matches[-1])
    energy_ev = energy_ry * RY_TO_EV

    blocks = find_main_force_blocks(lines)
    if not blocks:
        fatal(f"{output_path}: main force block missing")

    block = blocks[-1]
    reported_total_force, total_force_line = find_reported_total_force(
        lines,
        block,
    )

    forces_ry_bohr = [
        item["force_ry_bohr"] for item in block["forces"]
    ]
    forces_ev_ang = [
        [component * RY_BOHR_TO_EV_ANG for component in force]
        for force in forces_ry_bohr
    ]

    calculated_total_force = math.sqrt(
        sum(
            component * component
            for force in forces_ry_bohr
            for component in force
        )
    )
    total_force_difference = calculated_total_force - reported_total_force
    total_force_tolerance = max(
        TOTAL_FORCE_ABS_TOL_RY_BOHR,
        TOTAL_FORCE_REL_TOL * abs(reported_total_force),
    )

    if abs(total_force_difference) > total_force_tolerance:
        fatal(
            f"{output_path}: QE Total force mismatch: "
            f"calculated={calculated_total_force:.9f}, "
            f"reported={reported_total_force:.9f}, "
            f"difference={total_force_difference:.3e}, "
            f"tolerance={total_force_tolerance:.3e} Ry/bohr"
        )

    net_force_vector = [
        sum(force[axis] for force in forces_ev_ang)
        for axis in range(3)
    ]
    net_force_norm = norm3(net_force_vector)

    if net_force_norm > NET_FORCE_HARD_EV_ANG:
        fatal(
            f"{output_path}: true |sum_i F_i|="
            f"{net_force_norm:.8e} eV/A"
        )

    maximum_atomic_force = max(norm3(force) for force in forces_ev_ang)
    if maximum_atomic_force > MAX_ATOMIC_FORCE_HARD_EV_ANG:
        fatal(
            f"{output_path}: maximum atomic force "
            f"{maximum_atomic_force:.8f} eV/A"
        )

    force_block_lines = [lines[block["header_line_index"]]]
    force_block_lines.extend(
        item["source_line"] for item in block["forces"]
    )
    force_block_lines.append(lines[total_force_line - 1])

    scf_iterations = len(
        re.findall(
            r"^\s*iteration\s+#",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    )

    return {
        "energy_ry": energy_ry,
        "energy_ev": energy_ev,
        "forces_ry_bohr": forces_ry_bohr,
        "forces_ev_ang": forces_ev_ang,
        "maximum_atomic_force_ev_ang": maximum_atomic_force,
        "net_force_vector_ev_ang": net_force_vector,
        "net_force_norm_ev_ang": net_force_norm,
        "net_force_warning": net_force_norm > NET_FORCE_WARNING_EV_ANG,
        "reported_total_force_ry_bohr": reported_total_force,
        "calculated_total_force_ry_bohr": calculated_total_force,
        "total_force_difference_ry_bohr": total_force_difference,
        "main_force_block_count": len(blocks),
        "selected_force_block_header_line": block["header_line_number"],
        "scf_iterations": scf_iterations,
        "force_block_text": "\n".join(force_block_lines) + "\n",
        "output_sha256": sha256(output_path),
    }


# =============================================================================
# Progress, failure handling, and finalization
# =============================================================================


CASE_REPORT_FIELDS = [
    "global_case_index",
    "branch",
    "branch_case_index",
    "candidate_id",
    "side",
    "qpt_ang",
    "roo_ang",
    "energy_ev",
    "maximum_atomic_force_ev_ang",
    "true_net_force_x_ev_ang",
    "true_net_force_y_ev_ang",
    "true_net_force_z_ev_ang",
    "true_net_force_norm_ev_ang",
    "net_force_warning",
    "reported_total_force_ry_bohr",
    "calculated_total_force_ry_bohr",
    "total_force_difference_ry_bohr",
    "main_force_block_count",
    "selected_force_block_header_line",
    "force_line_count",
    "scf_iterations",
    "elapsed_seconds",
    "returncode",
    "output_sha256",
    "status",
]

FORCE_COMPONENT_FIELDS = [
    "global_case_index",
    "branch",
    "branch_case_index",
    "candidate_id",
    "atom_index",
    "symbol",
    "qe_type",
    "fx_ry_bohr",
    "fy_ry_bohr",
    "fz_ry_bohr",
    "fx_ev_ang",
    "fy_ev_ang",
    "fz_ev_ang",
    "force_norm_ev_ang",
]


def sorted_branch_records(
    records: list[dict[str, Any]],
    branch: str,
) -> list[dict[str, Any]]:
    selected = [record for record in records if record["branch"] == branch]
    return sorted(selected, key=lambda record: record["candidate_id"])


def write_progress_artifacts(
    records: list[dict[str, Any]],
    case_rows: list[dict[str, Any]],
    component_rows: list[dict[str, Any]],
    cell: np.ndarray,
    total_expected: int,
    k: int,
    current_case: dict[str, Any] | None,
) -> None:
    targeted = sorted_branch_records(records, "targeted")
    basin = sorted_branch_records(records, "basin")

    write_tsv(CASE_REPORT_TSV, case_rows, CASE_REPORT_FIELDS)
    write_tsv(FORCE_COMPONENTS_TSV, component_rows, FORCE_COMPONENT_FIELDS)

    write_label_cfg(
        LABELS_DIR / "partial_targeted_labels_v027.cfg",
        targeted,
        cell,
    )
    write_label_cfg(
        LABELS_DIR / "partial_basin_control_labels_v027.cfg",
        basin,
        cell,
    )

    progress = {
        "updated_utc": utc_now(),
        "status": (
            STATUS_FILE.read_text(encoding="utf-8").strip()
            if STATUS_FILE.is_file()
            else "UNKNOWN"
        ),
        "run_root": RUN_ROOT,
        "K": k,
        "total_expected": total_expected,
        "completed_total": len(records),
        "completed_targeted": len(targeted),
        "completed_basin": len(basin),
        "current_case": current_case,
        "execution": {
            "pw_x": True,
            "neb_x": False,
            "mlp": False,
            "mlp_train": False,
            "lammps": False,
        },
    }
    PROGRESS_JSON.write_text(
        json.dumps(json_safe(progress), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def mark_failure(status: str, details: dict[str, Any]) -> None:
    if not _ATTEMPT_CREATED:
        return
    STATUS_FILE.write_text(status + "\n", encoding="utf-8")
    FAILED_POINTER.parent.mkdir(parents=True, exist_ok=True)
    FAILED_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
    (RUN_ROOT / "failure_v027.json").write_text(
        json.dumps(
            json_safe(
                {
                    "created_utc": utc_now(),
                    "status": status,
                    "run_root": RUN_ROOT,
                    "details": details,
                }
            ),
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    cleanup_running_pointer_for_this_attempt()


def write_checksums() -> None:
    rows: list[dict[str, str]] = []
    for path in sorted(RUN_ROOT.rglob("*"), key=lambda item: str(item)):
        if path.is_file() and path != CHECKSUMS_TSV:
            rows.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": sha256(path),
                }
            )
    write_tsv(CHECKSUMS_TSV, rows, ["path", "sha256"])


# =============================================================================
# Upstream validation
# =============================================================================


def verify_v026_checksums(v026: Path, required_paths: list[Path]) -> None:
    checksum_file = require_file(v026 / "checksums_v026.tsv", "v026 checksums")
    rows = read_tsv(checksum_file)
    lookup = {row["path"]: row["sha256"] for row in rows}

    for path in required_paths:
        relative = path.relative_to(ROOT).as_posix()
        if relative not in lookup:
            fatal(f"v026 checksum entry missing for {relative}")
        require_hash(path, lookup[relative], f"v026 locked file {path.name}")


def load_and_validate_upstream() -> dict[str, Any]:
    v016 = resolve_success_attempt(
        V016_POINTER,
        "STATUS_v016.txt",
        EXPECTED_V016_STATUS,
        "v016",
    )
    v020 = resolve_success_attempt(
        V020_POINTER,
        "STATUS_v020.txt",
        EXPECTED_V020_STATUS,
        "v020",
    )
    v026 = resolve_success_attempt(
        V026_POINTER,
        "STATUS_v026.txt",
        EXPECTED_V026_STATUS,
        "v026",
    )

    common36 = require_file(
        v016 / "datasets" / "train_common_strict_v001.cfg",
        "common36",
    )
    require_hash(common36, EXPECTED_COMMON36_SHA256, "common36")

    common_blocks = read_cfg(common36)
    if len(common_blocks) != COMMON_COUNT:
        fatal(
            f"common36 contains {len(common_blocks)} blocks, "
            f"expected {COMMON_COUNT}"
        )

    lock_md = require_file(
        v020 / "protocol_lock" / "PRE_AUDIT_STRICT_PROTOCOL_LOCK_v001.md",
        "v020 protocol lock",
    )
    lock_json = require_file(
        v020 / "protocol_lock" / "PRE_AUDIT_STRICT_PROTOCOL_LOCK_v001.json",
        "v020 protocol lock JSON",
    )
    lock_text = (
        lock_md.read_text(encoding="utf-8")
        + "\n"
        + lock_json.read_text(encoding="utf-8")
    )
    if EXPECTED_PROTOCOL_SHA256 not in lock_text:
        fatal("canonical protocol hash not found in v020 lock")

    final_training_lock = require_file(
        v020
        / "specifications"
        / "final_equal_budget_training_protocol_v001.md",
        "v020 final training protocol",
    )
    final_training_text = final_training_lock.read_text(encoding="utf-8")
    required_phrases = [
        "train_basin_v001 = common36 + K basin-control labels",
        "train_targeted_v001 = common36 + K selected tube labels",
        "common36 in its frozen existing order",
        "branch-specific K structures sorted by candidate ID",
    ]
    for phrase in required_phrases:
        if phrase not in final_training_text:
            fatal(f"v020 final training lock lacks phrase: {phrase!r}")

    summary_path = require_file(v026 / "summary_v026.json", "v026 summary")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    if summary.get("status") != EXPECTED_V026_STATUS:
        fatal(f"v026 summary status mismatch: {summary.get('status')!r}")

    k = int(summary.get("K", 0))
    if not 1 <= k <= MAX_K:
        fatal(f"v026 K={k}, expected 1..{MAX_K}")

    targeted_queue_dir = v026 / "dft_queues" / "targeted_tube"
    basin_queue_dir = v026 / "dft_queues" / "basin_control"

    targeted_combined = require_file(
        v026 / "selection" / "tube_maxvol_selected_K_v026.cfg",
        "v026 selected tube CFG",
    )
    basin_combined = require_file(
        v026
        / "basin_control"
        / "basin_control_selected_exact_K_v026.cfg",
        "v026 selected basin CFG",
    )

    targeted_files = sorted(targeted_queue_dir.glob("*.cfg"))
    basin_files = sorted(basin_queue_dir.glob("*.cfg"))

    required_v026_paths = [
        summary_path,
        targeted_combined,
        basin_combined,
        *targeted_files,
        *basin_files,
    ]

    provenance_scripts = sorted(
        path
        for path in (v026 / "provenance").glob("step28*.py")
        if path.is_file()
    )
    if len(provenance_scripts) != 1:
        fatal(
            f"expected one v026 provenance script, found "
            f"{len(provenance_scripts)}"
        )
    v026_script = provenance_scripts[0]
    require_hash(
        v026_script,
        EXPECTED_V026_SCRIPT_SHA256,
        "successful v026 implementation",
    )
    if IMPLEMENTATION_ID in v026_script.read_text(
        encoding="utf-8", errors="replace"
    ):
        fatal("v027 implementation unexpectedly found inside v026 source")

    required_v026_paths.append(v026_script)
    verify_v026_checksums(v026, required_v026_paths)

    targeted_items = read_queue_directory(targeted_queue_dir, "targeted", k)
    basin_items = read_queue_directory(basin_queue_dir, "basin", k)

    compare_queue_to_combined(
        targeted_items,
        targeted_combined,
        "targeted",
    )
    compare_queue_to_combined(
        basin_items,
        basin_combined,
        "basin",
    )

    if {item.candidate_id for item in targeted_items} & {
        item.candidate_id for item in basin_items
    }:
        fatal("targeted and basin queues have overlapping candidate IDs")

    left_count = sum(item.side == "left" for item in basin_items)
    right_count = sum(item.side == "right" for item in basin_items)
    if left_count != (k + 1) // 2 or right_count != k // 2:
        fatal(
            f"basin side allocation mismatch: left={left_count}, "
            f"right={right_count}, K={k}"
        )

    # This check is diagnostic and does not modify either queue.
    minimum_cross_branch_fingerprint_rms = min(
        geometry_fingerprint_rms(target.positions, basin.positions)
        for target in (item.block for item in targeted_items)
        for basin in (item.block for item in basin_items)
    )
    if minimum_cross_branch_fingerprint_rms <= 5.0e-5:
        fatal(
            "targeted and basin queues contain a pair-distance duplicate: "
            f"minimum fingerprint RMS="
            f"{minimum_cross_branch_fingerprint_rms:.8e} A"
        )

    canonical_input = require_file(
        v016
        / "source_dft_inputs"
        / "strict_common_dft_v015_001"
        / "pw.in",
        "canonical v016 PW input",
    )
    canonical_metadata = validate_canonical_pw_source(canonical_input)

    cell = canonical_metadata["cell_ang"]
    for item in [*targeted_items, *basin_items]:
        maximum_cell_difference = float(
            np.max(np.abs(item.block.cell - cell))
        )
        if maximum_cell_difference > CELL_TOL_ANG:
            fatal(
                f"{item.branch} {item.candidate_id}: queue/canonical cell "
                f"difference={maximum_cell_difference:.3e} A"
            )

    mpi_info = validate_mpi_stack()

    return {
        "v016": v016,
        "v020": v020,
        "v026": v026,
        "common36": common36,
        "common_blocks": common_blocks,
        "canonical_input": canonical_input,
        "canonical_metadata": canonical_metadata,
        "cell": cell,
        "k": k,
        "targeted_items": targeted_items,
        "basin_items": basin_items,
        "targeted_combined": targeted_combined,
        "basin_combined": basin_combined,
        "v026_script": v026_script,
        "mpi_info": mpi_info,
        "left_count": left_count,
        "right_count": right_count,
        "minimum_cross_branch_fingerprint_rms":
            minimum_cross_branch_fingerprint_rms,
    }


# =============================================================================
# Main execution
# =============================================================================


def main() -> None:
    global _ATTEMPT_CREATED, _CURRENT_CASE

    if not RUN_PW or any([RUN_NEB, RUN_MLP, RUN_MLP_TRAIN, RUN_LAMMPS]):
        fatal("v027 execution guards were modified")

    upstream = load_and_validate_upstream()

    k = upstream["k"]
    total_cases = 2 * k
    targeted_items: list[QueueItem] = upstream["targeted_items"]
    basin_items: list[QueueItem] = upstream["basin_items"]
    cell: np.ndarray = upstream["cell"]

    schedule: list[QueueItem] = []
    for index in range(k):
        schedule.append(targeted_items[index])
        schedule.append(basin_items[index])

    command_template = [
        str(MPIRUN),
        "-np", str(MPI_RANKS),
        *MPI_BINDING_ARGS,
        str(PW_X),
        "-in", "pw_v027.in",
    ]

    if PREFLIGHT_ONLY:
        print("PASS_V027_PREFLIGHT_NO_DFT")
        print(f"source v026:             {upstream['v026']}")
        print(f"K:                       {k}")
        print(f"targeted queue:          {len(targeted_items)}")
        print(
            f"basin queue:             {len(basin_items)} "
            f"({upstream['left_count']} left + "
            f"{upstream['right_count']} right)"
        )
        print(f"total pw.x cases:        {total_cases}")
        print("execution order:         paired and sequential")
        print("final dataset order:     common36 + candidate-ID-sorted K")
        print(
            "minimum cross-branch "
            f"fingerprint RMS: {upstream['minimum_cross_branch_fingerprint_rms']:.8e} A"
        )
        print(f"canonical PW input:      {upstream['canonical_input']}")
        print(f"pw.x:                    {PW_X}")
        print(f"mpirun:                  {MPIRUN}")
        print(f"MPI ranks/case:          {MPI_RANKS}")
        print(f"OMP threads/rank:        {OMP_THREADS}")
        print(f"binding:                 {' '.join(MPI_BINDING_ARGS)}")
        print(f"command:                 {' '.join(command_template)}")
        print("restart_mode:            from_scratch for every case")
        print("unique prefix/tmp:       YES")
        print("duplicate Feature policy: identical repeats plus exact v026_corrected->v026 accepted")
        print("audit files:             NOT OPENED")
        print("attempt directory:       NOT CREATED")
        print("pw.x:                    NOT EXECUTED")
        print("neb.x/mlp/train/LAMMPS:  NOT EXECUTED")
        return

    if RUN_ROOT.exists():
        fatal(f"attempt already exists: {RUN_ROOT}")

    for directory in (
        RUN_ROOT,
        CASES_DIR / "targeted",
        CASES_DIR / "basin",
        INPUTS_DIR / "targeted",
        INPUTS_DIR / "basin",
        LABELS_DIR,
        DATASETS_DIR,
        REPORTS_DIR,
        PROVENANCE_DIR,
        EXTRACTED_DIR / "targeted",
        EXTRACTED_DIR / "basin",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    _ATTEMPT_CREATED = True
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)

    STATUS_FILE.write_text(
        "RUNNING_EQUAL_BUDGET_DFT_LABELS48_v027\n",
        encoding="utf-8",
    )
    RUNNING_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    provenance_sources = [
        upstream["common36"],
        upstream["canonical_input"],
        upstream["targeted_combined"],
        upstream["basin_combined"],
        upstream["v026_script"],
        Path(__file__).resolve(),
    ]
    for source in provenance_sources:
        destination = PROVENANCE_DIR / source.name
        if destination.exists():
            destination = PROVENANCE_DIR / (
                source.stem + "_copy" + source.suffix
            )
        shutil.copy2(source, destination)

    schedule_rows: list[dict[str, Any]] = []
    for global_index, item in enumerate(schedule, start=1):
        schedule_rows.append(
            {
                "global_case_index": global_index,
                "branch": item.branch,
                "branch_case_index": item.queue_index,
                "candidate_id": item.candidate_id,
                "side": item.side,
                "qpt_ang": item.qpt_ang,
                "roo_ang": item.roo_ang,
                "source_cfg": item.source_cfg,
            }
        )

    write_tsv(
        SCHEDULE_TSV,
        schedule_rows,
        [
            "global_case_index",
            "branch",
            "branch_case_index",
            "candidate_id",
            "side",
            "qpt_ang",
            "roo_ang",
            "source_cfg",
        ],
    )

    log(
        "Validated v016/v020/v026, exact equal-budget queues, canonical "
        "DFT protocol, and conda MPI stack."
    )
    log(
        f"Frozen execution schedule: {k} targeted + {k} basin = "
        f"{total_cases} sequential from-scratch pw.x cases."
    )

    print()
    print("STEP 29 / EQUAL-BUDGET DFT LABELLING v027")
    print()
    print(f"Run root:          {RUN_ROOT}")
    print(f"Source v026:       {upstream['v026']}")
    print(f"K:                 {k}")
    print(f"Total cases:       {total_cases}")
    print(f"MPI ranks/case:    {MPI_RANKS}")
    print(f"OMP threads/rank:  {OMP_THREADS}")
    print("Execution:         paired, sequential, from scratch")
    print("pw.x execution:    YES")
    print("neb.x execution:   NO")
    print("mlp execution:     NO")
    print("mlp train:         NO")
    print("LAMMPS execution:  NO")
    print()

    records: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []

    try:
        for global_case_index, item in enumerate(schedule, start=1):
            _CURRENT_CASE = {
                "global_case_index": global_case_index,
                "branch": item.branch,
                "branch_case_index": item.queue_index,
                "candidate_id": item.candidate_id,
            }

            branch_dir_name = item.branch
            case_name = (
                f"{item.branch}_{item.queue_index:03d}_"
                f"{item.candidate_id}_v027"
            )
            case_dir = CASES_DIR / branch_dir_name / case_name
            case_dir.mkdir(parents=True, exist_ok=False)
            (case_dir / "tmp").mkdir(parents=True, exist_ok=False)

            prefix = (
                f"v027_{'t' if item.branch == 'targeted' else 'b'}_"
                f"{item.queue_index:03d}"
            )

            input_text = render_single_point_input(
                upstream["canonical_input"],
                item.block.positions,
                prefix,
            )

            case_input = case_dir / "pw_v027.in"
            case_input.write_text(input_text, encoding="utf-8")

            copied_input = (
                INPUTS_DIR
                / branch_dir_name
                / f"{item.queue_index:03d}_{item.candidate_id}_v027.in"
            )
            shutil.copy2(case_input, copied_input)

            metadata = {
                "implementation_id": IMPLEMENTATION_ID,
                "global_case_index": global_case_index,
                "branch": item.branch,
                "branch_case_index": item.queue_index,
                "candidate_id": item.candidate_id,
                "side": item.side,
                "source_cfg": item.source_cfg,
                "source_cfg_sha256": sha256(item.source_cfg),
                "qpt_ang": item.qpt_ang,
                "roo_ang": item.roo_ang,
                "minimum_pair_ang": item.minimum_pair_ang,
                "maximum_span_ang": item.maximum_span_ang,
                "prefix": prefix,
                "restart_mode": "from_scratch",
                "training_eligible_after_success": True,
                "equal_budget_K": k,
            }
            (case_dir / "metadata_v027.json").write_text(
                json.dumps(
                    json_safe(metadata),
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )

            log(
                f"[{global_case_index:02d}/{total_cases:02d}] "
                f"Starting {item.branch} {item.queue_index:03d} "
                f"{item.candidate_id}; qPT={item.qpt_ang:.8f} A; "
                f"R_OO={item.roo_ang:.8f} A."
            )

            returncode, elapsed, command = run_single_point(
                case_dir,
                global_case_index,
            )

            if returncode != 0:
                status = (
                    f"FAIL_PW_CASE_{global_case_index:02d}_"
                    f"{item.branch.upper()}_v027"
                )
                mark_failure(
                    status,
                    {
                        "global_case_index": global_case_index,
                        "branch": item.branch,
                        "candidate_id": item.candidate_id,
                        "returncode": returncode,
                    },
                )
                fatal(
                    f"case {global_case_index}: pw.x return code {returncode}"
                )

            parsed = parse_pw_output(case_dir / "pw_v027.out")

            extracted_path = (
                EXTRACTED_DIR
                / branch_dir_name
                / f"{item.queue_index:03d}_{item.candidate_id}_"
                f"main_force_block_v027.txt"
            )
            extracted_path.write_text(
                parsed["force_block_text"],
                encoding="utf-8",
            )

            record = {
                "global_case_index": global_case_index,
                "branch": item.branch,
                "branch_case_index": item.queue_index,
                "candidate_id": item.candidate_id,
                "side": item.side,
                "coordinates_ang": item.block.positions.tolist(),
                "qpt_ang": item.qpt_ang,
                "roo_ang": item.roo_ang,
                "equal_budget_k": k,
                "elapsed_seconds": elapsed,
                "command": command,
                **parsed,
            }
            records.append(record)

            case_rows.append(
                {
                    "global_case_index": global_case_index,
                    "branch": item.branch,
                    "branch_case_index": item.queue_index,
                    "candidate_id": item.candidate_id,
                    "side": item.side,
                    "qpt_ang": item.qpt_ang,
                    "roo_ang": item.roo_ang,
                    "energy_ev": parsed["energy_ev"],
                    "maximum_atomic_force_ev_ang":
                        parsed["maximum_atomic_force_ev_ang"],
                    "true_net_force_x_ev_ang":
                        parsed["net_force_vector_ev_ang"][0],
                    "true_net_force_y_ev_ang":
                        parsed["net_force_vector_ev_ang"][1],
                    "true_net_force_z_ev_ang":
                        parsed["net_force_vector_ev_ang"][2],
                    "true_net_force_norm_ev_ang":
                        parsed["net_force_norm_ev_ang"],
                    "net_force_warning": parsed["net_force_warning"],
                    "reported_total_force_ry_bohr":
                        parsed["reported_total_force_ry_bohr"],
                    "calculated_total_force_ry_bohr":
                        parsed["calculated_total_force_ry_bohr"],
                    "total_force_difference_ry_bohr":
                        parsed["total_force_difference_ry_bohr"],
                    "main_force_block_count":
                        parsed["main_force_block_count"],
                    "selected_force_block_header_line":
                        parsed["selected_force_block_header_line"],
                    "force_line_count": len(parsed["forces_ev_ang"]),
                    "scf_iterations": parsed["scf_iterations"],
                    "elapsed_seconds": elapsed,
                    "returncode": returncode,
                    "output_sha256": parsed["output_sha256"],
                    "status": "PASS",
                }
            )

            for atom_index, (
                symbol,
                force_ry,
                force_ev,
            ) in enumerate(
                zip(
                    EXPECTED_SYMBOLS,
                    parsed["forces_ry_bohr"],
                    parsed["forces_ev_ang"],
                ),
                start=1,
            ):
                component_rows.append(
                    {
                        "global_case_index": global_case_index,
                        "branch": item.branch,
                        "branch_case_index": item.queue_index,
                        "candidate_id": item.candidate_id,
                        "atom_index": atom_index,
                        "symbol": symbol,
                        "qe_type": EXPECTED_QE_TYPES[atom_index - 1],
                        "fx_ry_bohr": force_ry[0],
                        "fy_ry_bohr": force_ry[1],
                        "fz_ry_bohr": force_ry[2],
                        "fx_ev_ang": force_ev[0],
                        "fy_ev_ang": force_ev[1],
                        "fz_ev_ang": force_ev[2],
                        "force_norm_ev_ang": norm3(force_ev),
                    }
                )

            write_progress_artifacts(
                records,
                case_rows,
                component_rows,
                cell,
                total_cases,
                k,
                _CURRENT_CASE,
            )

            log(
                f"[{global_case_index:02d}/{total_cases:02d}] PASS: "
                f"E={parsed['energy_ev']:.9f} eV; "
                f"maxF={parsed['maximum_atomic_force_ev_ang']:.6f} eV/A; "
                f"|sumF|={parsed['net_force_norm_ev_ang']:.3e} eV/A; "
                f"time={elapsed / 60:.2f} min."
            )

            _CURRENT_CASE = None

    except SinglePointInterrupted:
        raise
    except Exception:
        cleanup_running_pointer_for_this_attempt()
        raise

    if len(records) != total_cases:
        fatal(
            f"completed {len(records)} cases, expected {total_cases}"
        )

    targeted_records = sorted_branch_records(records, "targeted")
    basin_records = sorted_branch_records(records, "basin")

    if len(targeted_records) != k or len(basin_records) != k:
        fatal(
            f"final branch counts mismatch: targeted={len(targeted_records)}, "
            f"basin={len(basin_records)}, K={k}"
        )

    if [record["candidate_id"] for record in targeted_records] != sorted(
        record["candidate_id"] for record in targeted_records
    ):
        fatal("targeted final labels are not candidate-ID sorted")
    if [record["candidate_id"] for record in basin_records] != sorted(
        record["candidate_id"] for record in basin_records
    ):
        fatal("basin final labels are not candidate-ID sorted")

    write_label_cfg(TARGETED_LABELS_CFG, targeted_records, cell)
    write_label_cfg(BASIN_LABELS_CFG, basin_records, cell)
    write_label_cfg(
        ALL_NEW_LABELS_CFG,
        targeted_records + basin_records,
        cell,
    )

    targeted_label_blocks = split_cfg_text(
        TARGETED_LABELS_CFG.read_text(encoding="utf-8")
    )
    basin_label_blocks = split_cfg_text(
        BASIN_LABELS_CFG.read_text(encoding="utf-8")
    )

    if len(targeted_label_blocks) != k or len(basin_label_blocks) != k:
        fatal("final label CFG block count mismatch")

    common_raw = [block.raw for block in upstream["common_blocks"]]

    write_raw_cfg(
        TRAIN_TARGETED_CFG,
        common_raw + targeted_label_blocks,
    )
    write_raw_cfg(
        TRAIN_BASIN_CFG,
        common_raw + basin_label_blocks,
    )

    if len(split_cfg_text(TRAIN_TARGETED_CFG.read_text(encoding="utf-8"))) != COMMON_COUNT + k:
        fatal("targeted training dataset count mismatch")
    if len(split_cfg_text(TRAIN_BASIN_CFG.read_text(encoding="utf-8"))) != COMMON_COUNT + k:
        fatal("basin training dataset count mismatch")

    targeted_report_rows = [
        {
            "candidate_id": record["candidate_id"],
            "qpt_ang": record["qpt_ang"],
            "roo_ang": record["roo_ang"],
            "energy_ev": record["energy_ev"],
            "maximum_atomic_force_ev_ang":
                record["maximum_atomic_force_ev_ang"],
            "true_net_force_norm_ev_ang":
                record["net_force_norm_ev_ang"],
            "elapsed_seconds": record["elapsed_seconds"],
        }
        for record in targeted_records
    ]
    basin_report_rows = [
        {
            "candidate_id": record["candidate_id"],
            "side": record["side"],
            "qpt_ang": record["qpt_ang"],
            "roo_ang": record["roo_ang"],
            "energy_ev": record["energy_ev"],
            "maximum_atomic_force_ev_ang":
                record["maximum_atomic_force_ev_ang"],
            "true_net_force_norm_ev_ang":
                record["net_force_norm_ev_ang"],
            "elapsed_seconds": record["elapsed_seconds"],
        }
        for record in basin_records
    ]

    write_tsv(
        TARGETED_REPORT_TSV,
        targeted_report_rows,
        list(targeted_report_rows[0]),
    )
    write_tsv(
        BASIN_REPORT_TSV,
        basin_report_rows,
        list(basin_report_rows[0]),
    )

    total_elapsed = sum(record["elapsed_seconds"] for record in records)
    maximum_force = max(
        record["maximum_atomic_force_ev_ang"] for record in records
    )
    maximum_net_force = max(
        record["net_force_norm_ev_ang"] for record in records
    )

    targeted_energy_range = (
        min(record["energy_ev"] for record in targeted_records),
        max(record["energy_ev"] for record in targeted_records),
    )
    basin_energy_range = (
        min(record["energy_ev"] for record in basin_records),
        max(record["energy_ev"] for record in basin_records),
    )

    final_status = "PASS_EQUAL_BUDGET_DFT_LABELS48_READY_FOR_TRAINING"
    STATUS_FILE.write_text(final_status + "\n", encoding="utf-8")

    report_lines = [
        "# Equal-budget DFT labelling report v027",
        "",
        f"Created UTC: {utc_now()}",
        "",
        f"Status: `{final_status}`",
        "",
        "## Frozen upstream",
        "",
        f"- v016 common36: `{upstream['common36']}`",
        f"- v020 protocol lock: `{upstream['v020']}`",
        f"- v026 equal-budget queues: `{upstream['v026']}`",
        f"- K: {k}",
        "",
        "## DFT execution",
        "",
        f"- independent pw.x single points: {total_cases}",
        f"- targeted labels: {len(targeted_records)}",
        f"- basin-control labels: {len(basin_records)}",
        f"- basin allocation: {upstream['left_count']} left + "
        f"{upstream['right_count']} right",
        "- restart_mode: from_scratch for every case",
        f"- MPI ranks per case: {MPI_RANKS}",
        f"- OMP threads per rank: {OMP_THREADS}",
        "- execution order: paired, sequential",
        "- pw.x executed: yes",
        "- neb.x executed: no",
        "- mlp executed: no",
        "- mlp train executed: no",
        "- LAMMPS executed: no",
        "",
        "## Label validation",
        "",
        f"- maximum atomic force: {maximum_force:.12f} eV/Angstrom",
        f"- maximum true net force: {maximum_net_force:.12e} eV/Angstrom",
        f"- targeted energy range: {targeted_energy_range[0]:.12f} to "
        f"{targeted_energy_range[1]:.12f} eV",
        f"- basin energy range: {basin_energy_range[0]:.12f} to "
        f"{basin_energy_range[1]:.12f} eV",
        f"- total accumulated case wall time: {total_elapsed / 3600:.6f} h",
        "",
        "## Frozen training datasets",
        "",
        f"- targeted: common36 + {k} targeted = {COMMON_COUNT + k}",
        f"- basin: common36 + {k} basin-control = {COMMON_COUNT + k}",
        "- common36 order preserved",
        "- branch-specific new labels sorted by candidate ID",
        "",
        "No MTP was trained in this stage. Both datasets must be locked before",
        "the two level-12 models are trained independently from byte-identical",
        "copies of the same untrained template.",
    ]
    REPORT_MD.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    summary = {
        "created_utc": utc_now(),
        "status": final_status,
        "implementation_id": IMPLEMENTATION_ID,
        "run_root": RUN_ROOT,
        "K": k,
        "counts": {
            "common": COMMON_COUNT,
            "targeted_new": len(targeted_records),
            "basin_new": len(basin_records),
            "total_pw_cases": total_cases,
            "train_targeted": COMMON_COUNT + k,
            "train_basin": COMMON_COUNT + k,
        },
        "execution": {
            "pw_x": True,
            "neb_x": False,
            "mlp": False,
            "mlp_train": False,
            "lammps": False,
            "mpi_ranks_per_case": MPI_RANKS,
            "omp_threads_per_rank": OMP_THREADS,
            "paired_sequential_order": True,
            "total_case_wall_seconds": total_elapsed,
        },
        "validation": {
            "maximum_atomic_force_ev_ang": maximum_force,
            "maximum_true_net_force_ev_ang": maximum_net_force,
            "targeted_energy_range_ev": targeted_energy_range,
            "basin_energy_range_ev": basin_energy_range,
        },
        "upstream": {
            "v016": upstream["v016"],
            "v020": upstream["v020"],
            "v026": upstream["v026"],
            "common36_sha256": sha256(upstream["common36"]),
            "v026_script_sha256": sha256(upstream["v026_script"]),
            "canonical_pw_sha256":
                sha256(upstream["canonical_input"]),
            "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        },
        "outputs": {
            "targeted_labels": TARGETED_LABELS_CFG,
            "basin_labels": BASIN_LABELS_CFG,
            "all_new_labels": ALL_NEW_LABELS_CFG,
            "train_targeted": TRAIN_TARGETED_CFG,
            "train_basin": TRAIN_BASIN_CFG,
            "case_report": CASE_REPORT_TSV,
            "force_components": FORCE_COMPONENTS_TSV,
            "report": REPORT_MD,
        },
    }
    SUMMARY_JSON.write_text(
        json.dumps(json_safe(summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    write_checksums()

    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
    cleanup_running_pointer_for_this_attempt()

    print()
    print(
        "PASS_EQUAL_BUDGET_DFT_LABELS48_READY_FOR_TRAINING: "
        "STEP 29 v027 COMPLETED"
    )
    print()
    print(f"Run root:                  {RUN_ROOT}")
    print(f"Independent pw.x cases:    {total_cases}/{total_cases}")
    print(f"Targeted labels:           {len(targeted_records)}")
    print(f"Basin-control labels:      {len(basin_records)}")
    print(
        f"Basin allocation:          {upstream['left_count']} left + "
        f"{upstream['right_count']} right"
    )
    print(f"Maximum atomic force:      {maximum_force:.8f} eV/A")
    print(f"Maximum true |sum F|:      {maximum_net_force:.3e} eV/A")
    print(f"Total case wall time:      {total_elapsed / 3600:.3f} h")
    print()
    print(f"Targeted labels CFG:       {TARGETED_LABELS_CFG}")
    print(f"Basin labels CFG:          {BASIN_LABELS_CFG}")
    print(f"Targeted train60:          {TRAIN_TARGETED_CFG}")
    print(f"Basin train60:             {TRAIN_BASIN_CFG}")
    print(f"Report:                    {REPORT_MD}")
    print()
    print("pw.x WAS executed for all equal-budget cases.")
    print("neb.x was NOT executed.")
    print("mlp was NOT executed.")
    print("mlp train was NOT executed.")
    print("LAMMPS was NOT executed.")
    print()
    print("Next stage: lock both train60 datasets and train two level-12 MTPs.")


if __name__ == "__main__":
    try:
        main()

    except SinglePointInterrupted as interruption:
        if _ATTEMPT_CREATED:
            status = "INTERRUPTED_EQUAL_BUDGET_DFT_LABELS48_v027"
            STATUS_FILE.write_text(status + "\n", encoding="utf-8")
            INTERRUPTED_POINTER.parent.mkdir(parents=True, exist_ok=True)
            INTERRUPTED_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
            (RUN_ROOT / "interruption_v027.json").write_text(
                json.dumps(
                    json_safe(
                        {
                            "created_utc": utc_now(),
                            "status": status,
                            "reason": interruption.reason,
                            "global_case_index":
                                interruption.global_case_index,
                            "elapsed_seconds":
                                interruption.elapsed_seconds,
                            "current_case": _CURRENT_CASE,
                        }
                    ),
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )
            cleanup_running_pointer_for_this_attempt()

        print(
            f"\nINTERRUPTED: {interruption.reason}; "
            f"case={interruption.global_case_index}",
            file=sys.stderr,
        )
        raise SystemExit(130)

    except Exception as error:
        if _ATTEMPT_CREATED:
            current_status = (
                STATUS_FILE.read_text(encoding="utf-8").strip()
                if STATUS_FILE.is_file()
                else ""
            )
            if not current_status.startswith("FAIL_"):
                mark_failure(
                    "FAIL_RUNTIME_v027",
                    {
                        "error": repr(error),
                        "current_case": _CURRENT_CASE,
                    },
                )

        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

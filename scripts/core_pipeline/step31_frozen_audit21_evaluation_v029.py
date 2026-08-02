#!/usr/bin/env python3
from __future__ import annotations

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
# STEP 31 / v029
#
# One frozen audit21 evaluation of the two locked equal-budget level-12 MTPs.
#
# Frozen audit:
#   - 12 independent basin structures with DFT energies and corrected forces
#     from v023
#   - 9 independent DFT single points on the converged NEB path from v025
#
# Locked models:
#   - basin60 level-12 MTP from v028
#   - targeted60 level-12 MTP from v028
#
# Executed:
#   - mlp calc-efs once per model on the same frozen audit21
#   - mlp calc-grade once per model, using that model's own train60 as the
#     MaxVol reference set
#
# Forbidden:
#   - pw.x, neb.x, mlp train, select-add, LAMMPS
#   - changing either model, either dataset, or any metric after audit exposure
#   - retries for scientific quality
# =============================================================================


IMPLEMENTATION_ID = "STEP31_V029_FROZEN_AUDIT21_EVALUATION_V001"

ROOT = Path.home() / "malonaldehyde_mtp_al"
VERSIONS = ROOT / "09_strict_comparison" / "versions"
MLP = (
    ROOT
    / "01_environment"
    / "v001"
    / "software"
    / "bin"
    / "mlp"
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
V028_POINTER = (
    VERSIONS
    / "v028_equal_budget_l12_training"
    / "CURRENT_EQUAL_BUDGET_L12_MODELS.txt"
)

VERSION_ROOT = VERSIONS / "v029_frozen_audit21_evaluation"
CURRENT_POINTER = VERSION_ROOT / "CURRENT_FROZEN_AUDIT21_EVALUATION.txt"
RUNNING_POINTER = VERSION_ROOT / "CURRENT_RUNNING_FROZEN_AUDIT21_EVALUATION.txt"
FAILED_POINTER = VERSION_ROOT / "LAST_FAILED_FROZEN_AUDIT21_EVALUATION.txt"
INTERRUPTED_POINTER = (
    VERSION_ROOT / "LAST_INTERRUPTED_FROZEN_AUDIT21_EVALUATION.txt"
)

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"

INPUTS_DIR = RUN_ROOT / "inputs"
PREDICTIONS_DIR = RUN_ROOT / "predictions"
GRADES_DIR = RUN_ROOT / "grades"
REPORTS_DIR = RUN_ROOT / "reports"
PROVENANCE_DIR = RUN_ROOT / "provenance"

STATUS_FILE = RUN_ROOT / "STATUS_v029.txt"
RUN_LOG = RUN_ROOT / "run_log_v029.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v029.json"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v029.tsv"
COMMANDS_TSV = RUN_ROOT / "commands_v029.tsv"
AUDIT_LOCK_JSON = RUN_ROOT / "FROZEN_AUDIT21_EVALUATION_LOCK_v001.json"
REPORT_MD = REPORTS_DIR / "frozen_audit21_comparison_report_v029.md"

AUDIT_LABELS_CFG = INPUTS_DIR / "frozen_audit21_labels_v029.cfg"
AUDIT_GEOMETRY_CFG = INPUTS_DIR / "frozen_audit21_geometry_only_v029.cfg"
AUDIT_MANIFEST_TSV = INPUTS_DIR / "frozen_audit21_manifest_v029.tsv"

PER_CONFIGURATION_TSV = REPORTS_DIR / "per_configuration_errors_v029.tsv"
SUBSET_METRICS_TSV = REPORTS_DIR / "subset_metrics_v029.tsv"
GRADE_METRICS_TSV = REPORTS_DIR / "grade_metrics_v029.tsv"
NEB_PROFILE_TSV = REPORTS_DIR / "neb9_energy_profile_v029.tsv"
BARRIER_METRICS_TSV = REPORTS_DIR / "neb9_barrier_metrics_v029.tsv"
MODEL_COMPARISON_TSV = REPORTS_DIR / "model_comparison_v029.tsv"

EXPECTED_V020_STATUS = "PASS_PRE_AUDIT_PROTOCOL_LOCK_NO_CALCULATIONS"
EXPECTED_V023_STATUS = "PASS_BASIN_AUDIT_FORCE_BLOCK_REPARSE12_LABELLED"
EXPECTED_V025_STATUS = "PASS_INDEPENDENT_NEB9_SINGLE_POINTS_LABELLED"
EXPECTED_V028_STATUS = (
    "PASS_EQUAL_BUDGET_L12_MODELS_LOCKED_READY_FOR_FROZEN_AUDIT"
)

EXPECTED_PROTOCOL_SHA256 = (
    "0309ca4ca419458a847f1606759c792f0dfc4019108343e3d5a9721f5704d3b8"
)
EXPECTED_V028_SCRIPT_SHA256 = (
    "182558ec08f3daa0f0fa27e45083f2c8d0d858c50fbc1895b8f875a967aca972"
)
EXPECTED_BASIN_MODEL_SHA256 = (
    "45d80443c5f62cdfa30bbd1512cf58e31cd16fe2bb0b50cec147a92350d7a7ff"
)
EXPECTED_TARGETED_MODEL_SHA256 = (
    "30175dae673d63e0b318e5e3ba311a9f61afe88929a5d19c69a744a47aeef99f"
)
EXPECTED_TEMPLATE_SHA256 = (
    "84937b7176b87004a55296f2ba908386aaaa7095df1b73e5e6c2288d119d7db1"
)

NAT = 9
BASIN_AUDIT_COUNT = 12
NEB_AUDIT_COUNT = 9
AUDIT_COUNT = BASIN_AUDIT_COUNT + NEB_AUDIT_COUNT
TRAIN_COUNT = 60

EXPECTED_TYPES = [2, 1, 0, 1, 0, 1, 0, 2, 1]
EXPECTED_CELL = np.diag([16.0, 16.0, 16.0])

COORDINATE_TOL_ANG = 1.0e-6
CELL_TOL_ANG = 1.0e-8
FINGERPRINT_MATCH_TOL_ANG = 5.0e-5

AUX_TIMEOUT_SECONDS = 30 * 60
POLL_SECONDS = 1.0

THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}

RUN_CALC_EFS = True
RUN_CALC_GRADE = True
RUN_DFT = False
RUN_NEB = False
RUN_TRAIN = False
RUN_SELECT_ADD = False
RUN_LAMMPS = False
ALLOW_MODEL_CHANGES = False
ALLOW_DATASET_CHANGES = False
ALLOW_METRIC_CHANGES = False
ALLOW_SCIENTIFIC_RETRY = False

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V029_PREFLIGHT_ONLY", "0") == "1"
)

_ATTEMPT_CREATED = False
_CURRENT_OPERATION: dict[str, Any] | None = None


@dataclass
class CFGBlock:
    raw: str
    order: int
    size: int
    types: list[int]
    positions: np.ndarray
    forces: np.ndarray | None
    energy: float | None
    cell: np.ndarray
    features: dict[str, str]


@dataclass
class AuditItem:
    audit_index: int
    audit_id: str
    subset: str
    subset_index: int
    source_path: Path
    source_block_order: int
    block: CFGBlock
    qpt_ang: float
    roo_ang: float


class InterruptedRun(BaseException):
    def __init__(self, operation: str, elapsed_seconds: float) -> None:
        super().__init__(operation)
        self.operation = operation
        self.elapsed_seconds = elapsed_seconds


# =============================================================================
# Utilities
# =============================================================================


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fatal(message: str) -> None:
    raise RuntimeError(message)


def log(message: str) -> None:
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    if _ATTEMPT_CREATED:
        with RUN_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def parse_number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


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


def read_tsv(path: Path) -> list[dict[str, str]]:
    require_file(path, "TSV")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def cleanup_running_pointer() -> None:
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


def mlp_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(THREAD_ENV)
    return environment


def terminate_group(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    for sig, timeout in (
        (signal.SIGINT, 10),
        (signal.SIGTERM, 10),
        (signal.SIGKILL, 10),
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


def run_command(
    command: list[str],
    stdout_path: Path,
    stderr_path: Path,
    operation: str,
) -> tuple[int, float]:
    global _CURRENT_OPERATION

    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    _CURRENT_OPERATION = {
        "operation": operation,
        "command": command,
        "stdout": stdout_path,
        "stderr": stderr_path,
    }

    start = time.monotonic()

    with stdout_path.open("w", encoding="utf-8") as stdout_handle, \
         stderr_path.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            command,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            env=mlp_environment(),
            start_new_session=True,
        )

        try:
            while True:
                returncode = process.poll()
                if returncode is not None:
                    elapsed = time.monotonic() - start
                    _CURRENT_OPERATION = None
                    return returncode, elapsed

                elapsed = time.monotonic() - start
                if elapsed > AUX_TIMEOUT_SECONDS:
                    terminate_group(process)
                    fatal(
                        f"{operation}: timeout after "
                        f"{elapsed / 60:.2f} min"
                    )
                time.sleep(POLL_SECONDS)

        except KeyboardInterrupt as error:
            terminate_group(process)
            elapsed = time.monotonic() - start
            raise InterruptedRun(operation, elapsed) from error


# =============================================================================
# CFG parsing and serialization
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
                blocks.append("".join(current).rstrip() + "\n")
                current = None

    if current is not None:
        fatal("unterminated CFG block")

    return blocks


def parse_features(raw: str) -> dict[str, str]:
    features: dict[str, str] = {}
    pattern = re.compile(r"^\s*Feature\s+(\S+)\s+(.*?)\s*$")

    for line in raw.splitlines():
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
            continue

        # Known queue provenance transition inherited from v026/v027. It is
        # irrelevant to audit labels but accepted if encountered in copied
        # metadata.
        if (
            key == "version"
            and previous == "v026_corrected"
            and value == "v026"
        ):
            features[key] = "v026"
            continue

        fatal(
            f"conflicting duplicate CFG Feature {key}: "
            f"{previous!r} versus {value!r}"
        )

    return features


def parse_cfg_block(raw: str, order: int) -> CFGBlock:
    lines = raw.splitlines()
    features = parse_features(raw)

    size: int | None = None
    types: list[int] | None = None
    positions: np.ndarray | None = None
    forces: np.ndarray | None = None
    energy: float | None = None
    cell: np.ndarray | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped == "Size":
            if index + 1 >= len(lines):
                fatal("CFG Size value missing")
            size = int(lines[index + 1].strip())

        elif stripped == "Supercell":
            if index + 3 >= len(lines):
                fatal("CFG Supercell truncated")
            cell = np.asarray(
                [
                    [
                        parse_number(value)
                        for value in lines[index + offset].split()[:3]
                    ]
                    for offset in (1, 2, 3)
                ],
                dtype=float,
            )

        elif stripped.startswith("AtomData:"):
            if size is None:
                fatal("CFG AtomData appears before Size")

            columns = stripped.split(":", 1)[1].split()
            lookup = {name: columns.index(name) for name in columns}

            required = {"id", "type", "cartes_x", "cartes_y", "cartes_z"}
            if not required.issubset(lookup):
                fatal(f"CFG AtomData columns missing: {columns}")

            has_forces = {"fx", "fy", "fz"}.issubset(lookup)
            parsed_ids: list[int] = []
            parsed_types: list[int] = []
            parsed_positions: list[list[float]] = []
            parsed_forces: list[list[float]] = []

            for atom_offset in range(size):
                row = lines[index + 1 + atom_offset].split()
                if len(row) < len(columns):
                    fatal("CFG AtomData row too short")

                parsed_ids.append(int(row[lookup["id"]]))
                parsed_types.append(int(row[lookup["type"]]))
                parsed_positions.append(
                    [
                        parse_number(row[lookup["cartes_x"]]),
                        parse_number(row[lookup["cartes_y"]]),
                        parse_number(row[lookup["cartes_z"]]),
                    ]
                )
                if has_forces:
                    parsed_forces.append(
                        [
                            parse_number(row[lookup["fx"]]),
                            parse_number(row[lookup["fy"]]),
                            parse_number(row[lookup["fz"]]),
                        ]
                    )

            if parsed_ids != list(range(1, size + 1)):
                fatal(f"CFG atom IDs are not 1..N: {parsed_ids}")

            types = parsed_types
            positions = np.asarray(parsed_positions, dtype=float)
            if has_forces:
                forces = np.asarray(parsed_forces, dtype=float)

        elif stripped == "Energy":
            if index + 1 >= len(lines):
                fatal("CFG Energy value missing")
            energy = parse_number(lines[index + 1].strip())

    if size != NAT:
        fatal(f"CFG size={size}, expected {NAT}")
    if types is None or positions is None:
        fatal("CFG AtomData missing")
    if cell is None or cell.shape != (3, 3):
        fatal("CFG Supercell missing or malformed")
    if positions.shape != (NAT, 3):
        fatal(f"CFG coordinate shape={positions.shape}")
    if forces is not None and forces.shape != (NAT, 3):
        fatal(f"CFG force shape={forces.shape}")

    arrays = [cell, positions]
    if forces is not None:
        arrays.append(forces)
    if not all(np.all(np.isfinite(array)) for array in arrays):
        fatal("CFG contains nonfinite array values")
    if energy is not None and not math.isfinite(energy):
        fatal("CFG contains nonfinite energy")

    return CFGBlock(
        raw=raw,
        order=order,
        size=size,
        types=types,
        positions=positions,
        forces=forces,
        energy=energy,
        cell=cell,
        features=features,
    )


def read_cfg(path: Path) -> list[CFGBlock]:
    require_file(path, "CFG")
    return [
        parse_cfg_block(raw, index)
        for index, raw in enumerate(
            split_cfg_text(path.read_text(encoding="utf-8")),
            start=1,
        )
    ]


def geometry_metrics(positions: np.ndarray) -> dict[str, Any]:
    distances: dict[tuple[int, int], float] = {}

    for first in range(NAT):
        for second in range(first + 1, NAT):
            distances[(first + 1, second + 1)] = float(
                np.linalg.norm(positions[first] - positions[second])
            )

    return {
        "qpt_ang": distances[(1, 2)] - distances[(2, 8)],
        "roo_ang": distances[(1, 8)],
        "fingerprint": np.asarray(
            [distances[key] for key in sorted(distances)],
            dtype=float,
        ),
    }


def validate_labelled_blocks(
    path: Path,
    expected_count: int,
    label: str,
) -> list[CFGBlock]:
    blocks = read_cfg(path)

    if len(blocks) != expected_count:
        fatal(
            f"{label}: {len(blocks)} CFG blocks, expected {expected_count}"
        )

    for block in blocks:
        if block.types != EXPECTED_TYPES:
            fatal(
                f"{label} block {block.order}: atom types changed: "
                f"{block.types}"
            )

        cell_error = float(np.max(np.abs(block.cell - EXPECTED_CELL)))
        if cell_error > CELL_TOL_ANG:
            fatal(
                f"{label} block {block.order}: cell error="
                f"{cell_error:.3e} A"
            )

        if block.energy is None:
            fatal(f"{label} block {block.order}: Energy missing")
        if block.forces is None:
            fatal(f"{label} block {block.order}: forces missing")

    return blocks


def write_audit_label_cfg(
    path: Path,
    items: list[AuditItem],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            block = item.block
            assert block.energy is not None
            assert block.forces is not None

            handle.write("BEGIN_CFG\n")
            handle.write(" Size\n")
            handle.write(f"    {NAT}\n")
            handle.write(" Supercell\n")
            for vector in block.cell:
                handle.write(
                    f"    {vector[0]:.16g} "
                    f"{vector[1]:.16g} "
                    f"{vector[2]:.16g}\n"
                )

            handle.write(
                " AtomData:  id type cartes_x cartes_y cartes_z fx fy fz\n"
            )
            for atom_index, (
                atom_type,
                coordinate,
                force,
            ) in enumerate(
                zip(block.types, block.positions, block.forces),
                start=1,
            ):
                handle.write(
                    f"    {atom_index:4d} {atom_type:2d} "
                    f"{coordinate[0]:.16g} "
                    f"{coordinate[1]:.16g} "
                    f"{coordinate[2]:.16g} "
                    f"{force[0]:.16g} "
                    f"{force[1]:.16g} "
                    f"{force[2]:.16g}\n"
                )

            handle.write(" Energy\n")
            handle.write(f"    {block.energy:.16g}\n")
            handle.write(f" Feature   audit_id {item.audit_id}\n")
            handle.write(f" Feature   audit_index {item.audit_index}\n")
            handle.write(f" Feature   audit_subset {item.subset}\n")
            handle.write(
                f" Feature   audit_subset_index {item.subset_index}\n"
            )
            handle.write(f" Feature   q_pt_A {item.qpt_ang:.12f}\n")
            handle.write(f" Feature   r_oo_A {item.roo_ang:.12f}\n")
            handle.write(" Feature   frozen_audit true\n")
            handle.write(" Feature   training_eligible false\n")
            handle.write(" Feature   version v029\n")
            handle.write("END_CFG\n\n")


def write_audit_geometry_cfg(
    path: Path,
    items: list[AuditItem],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            block = item.block

            handle.write("BEGIN_CFG\n")
            handle.write(" Size\n")
            handle.write(f"    {NAT}\n")
            handle.write(" Supercell\n")
            for vector in block.cell:
                handle.write(
                    f"    {vector[0]:.16g} "
                    f"{vector[1]:.16g} "
                    f"{vector[2]:.16g}\n"
                )

            handle.write(" AtomData:  id type cartes_x cartes_y cartes_z\n")
            for atom_index, (
                atom_type,
                coordinate,
            ) in enumerate(
                zip(block.types, block.positions),
                start=1,
            ):
                handle.write(
                    f"    {atom_index:4d} {atom_type:2d} "
                    f"{coordinate[0]:.16g} "
                    f"{coordinate[1]:.16g} "
                    f"{coordinate[2]:.16g}\n"
                )

            handle.write(f" Feature   audit_id {item.audit_id}\n")
            handle.write(f" Feature   audit_index {item.audit_index}\n")
            handle.write(f" Feature   audit_subset {item.subset}\n")
            handle.write(
                f" Feature   audit_subset_index {item.subset_index}\n"
            )
            handle.write(f" Feature   q_pt_A {item.qpt_ang:.12f}\n")
            handle.write(f" Feature   r_oo_A {item.roo_ang:.12f}\n")
            handle.write(" Feature   frozen_audit true\n")
            handle.write(" Feature   training_eligible false\n")
            handle.write(" Feature   version v029\n")
            handle.write("END_CFG\n\n")


def recover_blocks_by_geometry(
    produced: list[CFGBlock],
    reference_items: list[AuditItem],
    stage: str,
) -> dict[str, CFGBlock]:
    if len(produced) != len(reference_items):
        fatal(
            f"{stage}: output count {len(produced)}, "
            f"expected {len(reference_items)}"
        )

    unmatched = {item.audit_id: item for item in reference_items}
    recovered: dict[str, CFGBlock] = {}

    for block in produced:
        explicit_id = block.features.get("audit_id", "").strip()

        if explicit_id:
            if explicit_id not in unmatched:
                fatal(f"{stage}: unknown or duplicate audit_id {explicit_id}")
            item = unmatched[explicit_id]

            if block.types != item.block.types:
                fatal(f"{stage} {explicit_id}: atom types changed")

            coordinate_error = float(
                np.max(np.abs(block.positions - item.block.positions))
            )
            if coordinate_error > COORDINATE_TOL_ANG:
                fatal(
                    f"{stage} {explicit_id}: coordinates changed by "
                    f"{coordinate_error:.3e} A"
                )

            recovered[explicit_id] = block
            del unmatched[explicit_id]
            continue

        matches: list[str] = []
        for audit_id, item in unmatched.items():
            if block.types != item.block.types:
                continue
            coordinate_error = float(
                np.max(np.abs(block.positions - item.block.positions))
            )
            if coordinate_error <= COORDINATE_TOL_ANG:
                matches.append(audit_id)

        if len(matches) != 1:
            # Secondary diagnostic using pair-distance fingerprints.
            produced_fp = geometry_metrics(block.positions)["fingerprint"]
            fingerprint_matches: list[str] = []
            for audit_id, item in unmatched.items():
                reference_fp = geometry_metrics(
                    item.block.positions
                )["fingerprint"]
                rms = float(
                    np.sqrt(np.mean((produced_fp - reference_fp) ** 2))
                )
                if rms <= FINGERPRINT_MATCH_TOL_ANG:
                    fingerprint_matches.append(audit_id)

            fatal(
                f"{stage}: cannot uniquely recover audit ID; "
                f"coordinate_matches={matches}; "
                f"fingerprint_matches={fingerprint_matches}"
            )

        audit_id = matches[0]
        recovered[audit_id] = block
        del unmatched[audit_id]

    if unmatched:
        fatal(f"{stage}: missing audit items {sorted(unmatched)}")

    return recovered


# =============================================================================
# Upstream validation
# =============================================================================


def optional_checksum_verify(
    attempt: Path,
    version: str,
    paths: list[Path],
) -> dict[str, Any]:
    checksum_file = attempt / f"checksums_{version}.tsv"

    if not checksum_file.is_file():
        return {
            "checksum_manifest_present": False,
            "checksum_manifest": None,
            "verified_paths": [],
        }

    rows = read_tsv(checksum_file)
    lookup = {row["path"]: row["sha256"] for row in rows}
    verified: list[str] = []

    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if relative not in lookup:
            fatal(
                f"{version}: checksum entry missing for {relative}"
            )
        require_hash(path, lookup[relative], f"{version} locked file")
        verified.append(relative)

    return {
        "checksum_manifest_present": True,
        "checksum_manifest": checksum_file,
        "verified_paths": verified,
    }


def validate_mlp_cli() -> dict[str, Any]:
    if not MLP.is_file() or not os.access(MLP, os.X_OK):
        fatal(f"mlp missing or not executable: {MLP}")

    help_outputs: dict[str, str] = {}

    for command_name in ("calc-efs", "calc-grade"):
        attempts = [
            [str(MLP), "help", command_name],
            [str(MLP), command_name, "--help"],
        ]
        successful: str | None = None

        for command in attempts:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
                env=mlp_environment(),
            )
            output = result.stdout + "\n" + result.stderr
            if result.returncode == 0 and output.strip():
                successful = output
                break

        if successful is None:
            fatal(f"unable to obtain mlp help for {command_name}")

        help_outputs[command_name] = successful

    if "--als-filename" not in help_outputs["calc-grade"]:
        fatal("local calc-grade help lacks --als-filename")

    return {
        "mlp": MLP,
        "calc_efs_help_sha256": hashlib.sha256(
            help_outputs["calc-efs"].encode("utf-8")
        ).hexdigest(),
        "calc_grade_help_sha256": hashlib.sha256(
            help_outputs["calc-grade"].encode("utf-8")
        ).hexdigest(),
    }


def load_upstream() -> dict[str, Any]:
    v020 = resolve_success_attempt(
        V020_POINTER,
        "STATUS_v020.txt",
        EXPECTED_V020_STATUS,
        "v020",
    )
    v023 = resolve_success_attempt(
        V023_POINTER,
        "STATUS_v023.txt",
        EXPECTED_V023_STATUS,
        "v023",
    )
    v025 = resolve_success_attempt(
        V025_POINTER,
        "STATUS_v025.txt",
        EXPECTED_V025_STATUS,
        "v025",
    )
    v028 = resolve_success_attempt(
        V028_POINTER,
        "STATUS_v028.txt",
        EXPECTED_V028_STATUS,
        "v028",
    )

    audit_metrics_spec = require_file(
        v020
        / "specifications"
        / "frozen_audit_metrics_v001.tsv",
        "v020 frozen audit metric specification",
    )
    audit_protocol = require_file(
        v020
        / "specifications"
        / "frozen_audit_evaluation_protocol_v001.md",
        "v020 frozen audit evaluation protocol",
    )
    protocol_json = require_file(
        v020
        / "protocol_lock"
        / "PRE_AUDIT_STRICT_PROTOCOL_LOCK_v001.json",
        "v020 protocol JSON",
    )
    protocol_md = require_file(
        v020
        / "protocol_lock"
        / "PRE_AUDIT_STRICT_PROTOCOL_LOCK_v001.md",
        "v020 protocol Markdown",
    )

    protocol_text = (
        protocol_json.read_text(encoding="utf-8")
        + "\n"
        + protocol_md.read_text(encoding="utf-8")
    )
    if EXPECTED_PROTOCOL_SHA256 not in protocol_text:
        fatal("expected v020 protocol SHA256 absent from protocol lock")

    audit_lock_text = (
        audit_metrics_spec.read_text(encoding="utf-8")
        + "\n"
        + audit_protocol.read_text(encoding="utf-8")
    ).lower()

    for required_term in (
        "energy",
        "force",
        "barrier",
        "grade",
        "qpt",
    ):
        if required_term not in audit_lock_text:
            fatal(
                f"v020 frozen audit specifications lack term "
                f"{required_term!r}"
            )

    basin_labels = require_file(
        v023
        / "labels"
        / "frozen_basin_audit_labels_corrected_v023.cfg",
        "v023 corrected basin audit labels",
    )
    neb_labels = require_file(
        v025
        / "labels"
        / "frozen_independent_neb_path_labels_v025.cfg",
        "v025 frozen NEB9 labels",
    )

    basin_blocks = validate_labelled_blocks(
        basin_labels,
        BASIN_AUDIT_COUNT,
        "v023 basin audit",
    )
    neb_blocks = validate_labelled_blocks(
        neb_labels,
        NEB_AUDIT_COUNT,
        "v025 NEB9 audit",
    )

    basin_items: list[AuditItem] = []
    neb_items: list[AuditItem] = []

    for subset_index, block in enumerate(basin_blocks, start=1):
        metrics = geometry_metrics(block.positions)
        basin_items.append(
            AuditItem(
                audit_index=subset_index,
                audit_id=f"audit_basin_{subset_index:02d}",
                subset="basin12",
                subset_index=subset_index,
                source_path=basin_labels,
                source_block_order=block.order,
                block=block,
                qpt_ang=metrics["qpt_ang"],
                roo_ang=metrics["roo_ang"],
            )
        )

    for subset_index, block in enumerate(neb_blocks, start=1):
        metrics = geometry_metrics(block.positions)
        neb_items.append(
            AuditItem(
                audit_index=BASIN_AUDIT_COUNT + subset_index,
                audit_id=f"audit_neb_{subset_index:02d}",
                subset="neb9",
                subset_index=subset_index,
                source_path=neb_labels,
                source_block_order=block.order,
                block=block,
                qpt_ang=metrics["qpt_ang"],
                roo_ang=metrics["roo_ang"],
            )
        )

    qpt_values = [item.qpt_ang for item in neb_items]
    if any(
        qpt_values[index] >= qpt_values[index + 1]
        for index in range(len(qpt_values) - 1)
    ):
        fatal(f"v025 NEB9 qPT is not strictly increasing: {qpt_values}")

    if abs(qpt_values[0] + 0.48389140) > 5.0e-6:
        fatal(f"unexpected NEB9 left endpoint qPT={qpt_values[0]:.8f}")
    if abs(qpt_values[-1] - 0.48377946) > 5.0e-6:
        fatal(f"unexpected NEB9 right endpoint qPT={qpt_values[-1]:.8f}")

    audit_items = basin_items + neb_items

    fingerprints = [
        geometry_metrics(item.block.positions)["fingerprint"]
        for item in audit_items
    ]
    for first in range(len(fingerprints)):
        for second in range(first + 1, len(fingerprints)):
            rms = float(
                np.sqrt(
                    np.mean(
                        (fingerprints[first] - fingerprints[second]) ** 2
                    )
                )
            )
            if rms <= FINGERPRINT_MATCH_TOL_ANG:
                fatal(
                    f"frozen audit contains duplicate-like geometries: "
                    f"{audit_items[first].audit_id}, "
                    f"{audit_items[second].audit_id}, rms={rms:.3e} A"
                )

    model_lock = require_file(
        v028 / "EQUAL_BUDGET_L12_MODEL_LOCK_v001.json",
        "v028 model lock",
    )
    model_lock_data = json.loads(model_lock.read_text(encoding="utf-8"))

    if model_lock_data.get("status") != EXPECTED_V028_STATUS:
        fatal("v028 model-lock status mismatch")

    if (
        model_lock_data.get("execution", {})
        .get("audit_opened_or_evaluated") is not False
    ):
        fatal("v028 model lock does not confirm audit was unopened")

    basin_model = require_file(
        v028 / "models" / "basin" / "pot_basin60_l12_v001.mtp",
        "v028 basin model",
    )
    targeted_model = require_file(
        v028 / "models" / "targeted" / "pot_targeted60_l12_v001.mtp",
        "v028 targeted model",
    )
    basin_train = require_file(
        v028 / "inputs" / "train_basin_v001.cfg",
        "v028 basin train60",
    )
    targeted_train = require_file(
        v028 / "inputs" / "train_targeted_v001.cfg",
        "v028 targeted train60",
    )
    locked_template = require_file(
        v028 / "templates" / "locked_untrained_l12_v028.mtp",
        "v028 locked template",
    )
    basin_init = require_file(
        v028 / "templates" / "init_basin_l12_v028.mtp",
        "v028 basin initialization",
    )
    targeted_init = require_file(
        v028 / "templates" / "init_targeted_l12_v028.mtp",
        "v028 targeted initialization",
    )

    require_hash(
        basin_model,
        EXPECTED_BASIN_MODEL_SHA256,
        "v028 basin model",
    )
    require_hash(
        targeted_model,
        EXPECTED_TARGETED_MODEL_SHA256,
        "v028 targeted model",
    )
    for path in (locked_template, basin_init, targeted_init):
        require_hash(path, EXPECTED_TEMPLATE_SHA256, path.name)

    if sha256(basin_model) == sha256(targeted_model):
        fatal("v028 trained model hashes are identical")

    basin_train_blocks = read_cfg(basin_train)
    targeted_train_blocks = read_cfg(targeted_train)
    if len(basin_train_blocks) != TRAIN_COUNT:
        fatal("v028 basin train set count mismatch")
    if len(targeted_train_blocks) != TRAIN_COUNT:
        fatal("v028 targeted train set count mismatch")

    provenance_scripts = sorted(
        path
        for path in (v028 / "provenance").glob("step30*.py")
        if path.is_file()
    )
    if len(provenance_scripts) != 1:
        fatal(
            f"v028 expected one step30 provenance script, "
            f"found {len(provenance_scripts)}"
        )
    v028_script = provenance_scripts[0]
    require_hash(
        v028_script,
        EXPECTED_V028_SCRIPT_SHA256,
        "successful v028 implementation",
    )

    v028_checks = optional_checksum_verify(
        v028,
        "v028",
        [
            model_lock,
            basin_model,
            targeted_model,
            basin_train,
            targeted_train,
            locked_template,
            basin_init,
            targeted_init,
            v028_script,
        ],
    )
    v023_checks = optional_checksum_verify(
        v023,
        "v023",
        [basin_labels],
    )
    v025_checks = optional_checksum_verify(
        v025,
        "v025",
        [neb_labels],
    )

    cli = validate_mlp_cli()

    dft_neb_energies = np.asarray(
        [item.block.energy for item in neb_items],
        dtype=float,
    )
    assert np.all(np.isfinite(dft_neb_energies))

    dft_max_index = int(np.argmax(dft_neb_energies))
    if dft_max_index != 4:
        fatal(
            f"DFT NEB9 maximum is image {dft_max_index + 1}, expected 5"
        )

    dft_forward_barrier = float(
        dft_neb_energies[dft_max_index] - dft_neb_energies[0]
    )
    dft_backward_barrier = float(
        dft_neb_energies[dft_max_index] - dft_neb_energies[-1]
    )

    if abs(dft_forward_barrier - 0.03596474) > 2.0e-7:
        fatal(
            f"DFT forward barrier={dft_forward_barrier:.9f} eV"
        )
    if abs(dft_backward_barrier - 0.03607209) > 2.0e-7:
        fatal(
            f"DFT backward barrier={dft_backward_barrier:.9f} eV"
        )

    return {
        "v020": v020,
        "v023": v023,
        "v025": v025,
        "v028": v028,
        "audit_metrics_spec": audit_metrics_spec,
        "audit_protocol": audit_protocol,
        "protocol_json": protocol_json,
        "protocol_md": protocol_md,
        "basin_labels": basin_labels,
        "neb_labels": neb_labels,
        "audit_items": audit_items,
        "basin_items": basin_items,
        "neb_items": neb_items,
        "basin_model": basin_model,
        "targeted_model": targeted_model,
        "basin_train": basin_train,
        "targeted_train": targeted_train,
        "model_lock": model_lock,
        "v028_script": v028_script,
        "cli": cli,
        "v028_checks": v028_checks,
        "v023_checks": v023_checks,
        "v025_checks": v025_checks,
        "dft_forward_barrier_ev": dft_forward_barrier,
        "dft_backward_barrier_ev": dft_backward_barrier,
        "dft_max_image": dft_max_index + 1,
    }


# =============================================================================
# Prediction, grade parsing, and metrics
# =============================================================================


def grade_from_block(block: CFGBlock) -> float:
    candidates = [
        key
        for key in block.features
        if key.lower() == "mv_grade"
    ]
    if len(candidates) != 1:
        fatal(
            f"graded CFG block {block.order}: expected one MV_grade, "
            f"found keys={candidates}"
        )
    value = parse_number(block.features[candidates[0]])
    if not math.isfinite(value) or value < 0.0:
        fatal(f"invalid MV_grade={value}")
    return value


def subset_metrics(
    reference_items: list[AuditItem],
    predictions: dict[str, CFGBlock],
    grades: dict[str, float],
) -> dict[str, Any]:
    energy_errors: list[float] = []
    force_component_errors: list[float] = []
    force_vector_errors: list[float] = []
    subset_grades: list[float] = []

    for item in reference_items:
        predicted = predictions[item.audit_id]
        reference = item.block

        assert reference.energy is not None
        assert reference.forces is not None
        assert predicted.energy is not None
        assert predicted.forces is not None

        energy_errors.append(predicted.energy - reference.energy)

        force_delta = predicted.forces - reference.forces
        force_component_errors.extend(force_delta.reshape(-1).tolist())
        force_vector_errors.extend(
            np.linalg.norm(force_delta, axis=1).tolist()
        )
        subset_grades.append(grades[item.audit_id])

    energy_array = np.asarray(energy_errors, dtype=float)
    force_component_array = np.asarray(
        force_component_errors,
        dtype=float,
    )
    force_vector_array = np.asarray(force_vector_errors, dtype=float)
    grade_array = np.asarray(subset_grades, dtype=float)

    if not all(
        np.all(np.isfinite(array))
        for array in (
            energy_array,
            force_component_array,
            force_vector_array,
            grade_array,
        )
    ):
        fatal("nonfinite audit metrics")

    centered_energy = energy_array - float(np.mean(energy_array))

    return {
        "configuration_count": len(reference_items),
        "energy_rmse_ev":
            float(np.sqrt(np.mean(energy_array ** 2))),
        "energy_mae_ev":
            float(np.mean(np.abs(energy_array))),
        "energy_max_abs_ev":
            float(np.max(np.abs(energy_array))),
        "energy_mean_error_ev":
            float(np.mean(energy_array)),
        "energy_centered_rmse_ev":
            float(np.sqrt(np.mean(centered_energy ** 2))),
        "force_component_rmse_ev_ang":
            float(np.sqrt(np.mean(force_component_array ** 2))),
        "force_component_mae_ev_ang":
            float(np.mean(np.abs(force_component_array))),
        "force_component_max_abs_ev_ang":
            float(np.max(np.abs(force_component_array))),
        "force_vector_rmse_ev_ang":
            float(np.sqrt(np.mean(force_vector_array ** 2))),
        "force_vector_max_ev_ang":
            float(np.max(force_vector_array)),
        "grade_min": float(np.min(grade_array)),
        "grade_median": float(np.median(grade_array)),
        "grade_mean": float(np.mean(grade_array)),
        "grade_max": float(np.max(grade_array)),
        "grade_gt_2_count": int(np.sum(grade_array > 2.0)),
        "grade_gt_10_count": int(np.sum(grade_array > 10.0)),
    }


def neb_metrics(
    neb_items: list[AuditItem],
    predictions: dict[str, CFGBlock],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dft_energies = np.asarray(
        [item.block.energy for item in neb_items],
        dtype=float,
    )
    model_energies = np.asarray(
        [predictions[item.audit_id].energy for item in neb_items],
        dtype=float,
    )

    if not np.all(np.isfinite(dft_energies)):
        fatal("nonfinite DFT NEB energies")
    if not np.all(np.isfinite(model_energies)):
        fatal("nonfinite model NEB energies")

    dft_relative = dft_energies - dft_energies[0]
    model_relative = model_energies - model_energies[0]
    profile_error = model_relative - dft_relative

    dft_max_zero = int(np.argmax(dft_energies))
    model_max_zero = int(np.argmax(model_energies))

    dft_forward = float(
        dft_energies[dft_max_zero] - dft_energies[0]
    )
    dft_backward = float(
        dft_energies[dft_max_zero] - dft_energies[-1]
    )
    model_forward = float(
        model_energies[model_max_zero] - model_energies[0]
    )
    model_backward = float(
        model_energies[model_max_zero] - model_energies[-1]
    )

    rows: list[dict[str, Any]] = []
    for item, dft_energy, model_energy, dft_delta, model_delta, error in zip(
        neb_items,
        dft_energies,
        model_energies,
        dft_relative,
        model_relative,
        profile_error,
    ):
        rows.append(
            {
                "audit_id": item.audit_id,
                "image": item.subset_index,
                "qpt_ang": item.qpt_ang,
                "roo_ang": item.roo_ang,
                "dft_energy_ev": dft_energy,
                "model_energy_ev": model_energy,
                "raw_energy_error_ev": model_energy - dft_energy,
                "dft_delta_e_from_left_ev": dft_delta,
                "model_delta_e_from_left_ev": model_delta,
                "profile_error_ev": error,
            }
        )

    metrics = {
        "profile_rmse_ev":
            float(np.sqrt(np.mean(profile_error ** 2))),
        "profile_mae_ev":
            float(np.mean(np.abs(profile_error))),
        "profile_max_abs_ev":
            float(np.max(np.abs(profile_error))),
        "dft_max_image": dft_max_zero + 1,
        "model_max_image": model_max_zero + 1,
        "dft_max_qpt_ang": neb_items[dft_max_zero].qpt_ang,
        "model_max_qpt_ang": neb_items[model_max_zero].qpt_ang,
        "dft_forward_barrier_ev": dft_forward,
        "model_forward_barrier_ev": model_forward,
        "forward_barrier_error_ev": model_forward - dft_forward,
        "forward_barrier_abs_error_mev":
            abs(model_forward - dft_forward) * 1000.0,
        "dft_backward_barrier_ev": dft_backward,
        "model_backward_barrier_ev": model_backward,
        "backward_barrier_error_ev": model_backward - dft_backward,
        "backward_barrier_abs_error_mev":
            abs(model_backward - dft_backward) * 1000.0,
        "dft_endpoint_difference_ev":
            float(dft_energies[-1] - dft_energies[0]),
        "model_endpoint_difference_ev":
            float(model_energies[-1] - model_energies[0]),
        "endpoint_difference_error_ev":
            float(
                (model_energies[-1] - model_energies[0])
                - (dft_energies[-1] - dft_energies[0])
            ),
    }

    return metrics, rows


def evaluate_model(
    branch: str,
    model: Path,
    train_set: Path,
    audit_items: list[AuditItem],
) -> dict[str, Any]:
    prediction_path = (
        PREDICTIONS_DIR / branch / f"audit21_predictions_{branch}_v029.cfg"
    )
    calc_efs_stdout = (
        PREDICTIONS_DIR / branch / "calc_efs_stdout_v029.txt"
    )
    calc_efs_stderr = (
        PREDICTIONS_DIR / branch / "calc_efs_stderr_v029.txt"
    )

    grade_output = (
        GRADES_DIR / branch / f"audit21_grades_{branch}_v029.cfg"
    )
    grade_als = GRADES_DIR / branch / f"audit21_{branch}_v029.als"
    calc_grade_stdout = (
        GRADES_DIR / branch / "calc_grade_stdout_v029.txt"
    )
    calc_grade_stderr = (
        GRADES_DIR / branch / "calc_grade_stderr_v029.txt"
    )

    calc_efs_command = [
        str(MLP),
        "calc-efs",
        str(model),
        str(AUDIT_LABELS_CFG),
        str(prediction_path),
    ]

    log(
        f"Starting frozen audit calc-efs for locked {branch} model "
        f"on audit21."
    )
    calc_efs_code, calc_efs_elapsed = run_command(
        calc_efs_command,
        calc_efs_stdout,
        calc_efs_stderr,
        f"mlp calc-efs frozen audit {branch}",
    )
    if calc_efs_code != 0:
        fatal(f"{branch} calc-efs return code {calc_efs_code}")

    prediction_blocks = read_cfg(prediction_path)
    prediction_map = recover_blocks_by_geometry(
        prediction_blocks,
        audit_items,
        f"{branch} calc-efs",
    )

    for audit_id, block in prediction_map.items():
        if block.energy is None:
            fatal(f"{branch} prediction {audit_id}: Energy missing")
        if block.forces is None:
            fatal(f"{branch} prediction {audit_id}: forces missing")

    calc_grade_command = [
        str(MLP),
        "calc-grade",
        str(model),
        str(train_set),
        str(AUDIT_GEOMETRY_CFG),
        str(grade_output),
        f"--als-filename={grade_als}",
    ]

    log(
        f"Starting frozen audit calc-grade for locked {branch} model "
        f"using its own train60 reference."
    )
    calc_grade_code, calc_grade_elapsed = run_command(
        calc_grade_command,
        calc_grade_stdout,
        calc_grade_stderr,
        f"mlp calc-grade frozen audit {branch}",
    )
    if calc_grade_code != 0:
        fatal(f"{branch} calc-grade return code {calc_grade_code}")

    require_file(grade_als, f"{branch} calc-grade ALS")
    grade_blocks = read_cfg(grade_output)
    grade_map = recover_blocks_by_geometry(
        grade_blocks,
        audit_items,
        f"{branch} calc-grade",
    )
    grades = {
        audit_id: grade_from_block(block)
        for audit_id, block in grade_map.items()
    }

    all_metrics = subset_metrics(
        audit_items,
        prediction_map,
        grades,
    )
    basin_items = [
        item for item in audit_items if item.subset == "basin12"
    ]
    neb_items = [
        item for item in audit_items if item.subset == "neb9"
    ]
    basin_metrics = subset_metrics(
        basin_items,
        prediction_map,
        grades,
    )
    neb_subset_metrics = subset_metrics(
        neb_items,
        prediction_map,
        grades,
    )
    barrier_metrics, neb_rows = neb_metrics(
        neb_items,
        prediction_map,
    )

    log(
        f"{branch} frozen audit PASS: "
        f"all21 E_RMSE={all_metrics['energy_rmse_ev']:.8f} eV; "
        f"F_component_RMSE="
        f"{all_metrics['force_component_rmse_ev_ang']:.8f} eV/A; "
        f"NEB profile_RMSE={barrier_metrics['profile_rmse_ev']:.8f} eV; "
        f"forward barrier error="
        f"{barrier_metrics['forward_barrier_error_ev'] * 1000.0:.3f} meV; "
        f"grade_max={all_metrics['grade_max']:.6f}."
    )

    return {
        "branch": branch,
        "model": model,
        "model_sha256": sha256(model),
        "train_set": train_set,
        "train_set_sha256": sha256(train_set),
        "prediction_path": prediction_path,
        "prediction_sha256": sha256(prediction_path),
        "grade_output": grade_output,
        "grade_output_sha256": sha256(grade_output),
        "grade_als": grade_als,
        "calc_efs_command": calc_efs_command,
        "calc_efs_returncode": calc_efs_code,
        "calc_efs_elapsed_seconds": calc_efs_elapsed,
        "calc_grade_command": calc_grade_command,
        "calc_grade_returncode": calc_grade_code,
        "calc_grade_elapsed_seconds": calc_grade_elapsed,
        "predictions": prediction_map,
        "grades": grades,
        "metrics": {
            "all21": all_metrics,
            "basin12": basin_metrics,
            "neb9": neb_subset_metrics,
        },
        "barrier_metrics": barrier_metrics,
        "neb_rows": neb_rows,
    }


# =============================================================================
# Failure and finalization
# =============================================================================


def mark_failure(status: str, error: BaseException) -> None:
    if not _ATTEMPT_CREATED:
        return

    STATUS_FILE.write_text(status + "\n", encoding="utf-8")
    FAILED_POINTER.parent.mkdir(parents=True, exist_ok=True)
    FAILED_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    (RUN_ROOT / "failure_v029.json").write_text(
        json.dumps(
            json_safe(
                {
                    "created_utc": utc_now(),
                    "status": status,
                    "error": repr(error),
                    "current_operation": _CURRENT_OPERATION,
                    "run_root": RUN_ROOT,
                }
            ),
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    cleanup_running_pointer()


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


def main() -> None:
    global _ATTEMPT_CREATED

    if not RUN_CALC_EFS or not RUN_CALC_GRADE:
        fatal("v029 required audit execution guards were modified")

    if any(
        [
            RUN_DFT,
            RUN_NEB,
            RUN_TRAIN,
            RUN_SELECT_ADD,
            RUN_LAMMPS,
            ALLOW_MODEL_CHANGES,
            ALLOW_DATASET_CHANGES,
            ALLOW_METRIC_CHANGES,
            ALLOW_SCIENTIFIC_RETRY,
        ]
    ):
        fatal("v029 scientific guards were modified")

    upstream = load_upstream()
    audit_items: list[AuditItem] = upstream["audit_items"]

    if PREFLIGHT_ONLY:
        print("PASS_V029_PREFLIGHT_AUDIT_OPENED_NO_MLP_NO_DFT")
        print(f"source v023 basin12:     {upstream['v023']}")
        print(f"source v025 NEB9:        {upstream['v025']}")
        print(f"source v028 models:      {upstream['v028']}")
        print(f"audit count:             {len(audit_items)}")
        print(f"basin audit count:       {len(upstream['basin_items'])}")
        print(f"NEB audit count:         {len(upstream['neb_items'])}")
        print(
            f"NEB qPT range:           "
            f"{upstream['neb_items'][0].qpt_ang:.8f} to "
            f"{upstream['neb_items'][-1].qpt_ang:.8f} A"
        )
        print(
            f"DFT forward barrier:     "
            f"{upstream['dft_forward_barrier_ev']:.8f} eV"
        )
        print(
            f"DFT backward barrier:    "
            f"{upstream['dft_backward_barrier_ev']:.8f} eV"
        )
        print(
            f"basin model SHA256:      "
            f"{sha256(upstream['basin_model'])}"
        )
        print(
            f"targeted model SHA256:   "
            f"{sha256(upstream['targeted_model'])}"
        )
        print("model/dataset changes:   FORBIDDEN")
        print("metric changes:          FORBIDDEN")
        print("scientific retries:      FORBIDDEN")
        print("model order:             basin, then targeted")
        print("audit files:             OPENED FOR VALIDATION")
        print("attempt directory:       NOT CREATED")
        print("mlp calc-efs:            NOT EXECUTED")
        print("mlp calc-grade:          NOT EXECUTED")
        print("pw.x/neb.x/train/select-add/LAMMPS: NOT EXECUTED")
        return

    if RUN_ROOT.exists():
        fatal(f"attempt already exists: {RUN_ROOT}")

    for directory in (
        RUN_ROOT,
        INPUTS_DIR,
        PREDICTIONS_DIR / "basin",
        PREDICTIONS_DIR / "targeted",
        GRADES_DIR / "basin",
        GRADES_DIR / "targeted",
        REPORTS_DIR,
        PROVENANCE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    _ATTEMPT_CREATED = True
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(
        "RUNNING_FROZEN_AUDIT21_EVALUATION_v029\n",
        encoding="utf-8",
    )
    RUNNING_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    # Freeze exactly what is about to be evaluated before the first MLP call.
    write_audit_label_cfg(AUDIT_LABELS_CFG, audit_items)
    write_audit_geometry_cfg(AUDIT_GEOMETRY_CFG, audit_items)

    manifest_rows = [
        {
            "audit_index": item.audit_index,
            "audit_id": item.audit_id,
            "subset": item.subset,
            "subset_index": item.subset_index,
            "source_path": item.source_path,
            "source_block_order": item.source_block_order,
            "qpt_ang": item.qpt_ang,
            "roo_ang": item.roo_ang,
            "dft_energy_ev": item.block.energy,
        }
        for item in audit_items
    ]
    write_tsv(
        AUDIT_MANIFEST_TSV,
        manifest_rows,
        list(manifest_rows[0]),
    )

    input_label_blocks = validate_labelled_blocks(
        AUDIT_LABELS_CFG,
        AUDIT_COUNT,
        "materialized frozen audit21",
    )
    if len(input_label_blocks) != AUDIT_COUNT:
        fatal("materialized audit21 count mismatch")

    provenance_sources = [
        upstream["audit_metrics_spec"],
        upstream["audit_protocol"],
        upstream["protocol_json"],
        upstream["protocol_md"],
        upstream["model_lock"],
        upstream["v028_script"],
        upstream["basin_labels"],
        upstream["neb_labels"],
        Path(__file__).resolve(),
    ]

    for source in provenance_sources:
        destination = PROVENANCE_DIR / source.name
        if destination.exists():
            destination = (
                PROVENANCE_DIR
                / f"{source.stem}_copy{source.suffix}"
            )
        shutil.copy2(source, destination)

    audit_lock = {
        "created_utc": utc_now(),
        "status": "LOCKED_BEFORE_FIRST_AUDIT_MLP_CALL",
        "implementation_id": IMPLEMENTATION_ID,
        "run_root": RUN_ROOT,
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "audit": {
            "count": AUDIT_COUNT,
            "basin12_source": upstream["basin_labels"],
            "basin12_source_sha256": sha256(upstream["basin_labels"]),
            "neb9_source": upstream["neb_labels"],
            "neb9_source_sha256": sha256(upstream["neb_labels"]),
            "materialized_labels": AUDIT_LABELS_CFG,
            "materialized_labels_sha256": sha256(AUDIT_LABELS_CFG),
            "materialized_geometry": AUDIT_GEOMETRY_CFG,
            "materialized_geometry_sha256": sha256(AUDIT_GEOMETRY_CFG),
            "manifest": AUDIT_MANIFEST_TSV,
            "manifest_sha256": sha256(AUDIT_MANIFEST_TSV),
        },
        "models": {
            "basin": {
                "path": upstream["basin_model"],
                "sha256": sha256(upstream["basin_model"]),
                "train60": upstream["basin_train"],
                "train60_sha256": sha256(upstream["basin_train"]),
            },
            "targeted": {
                "path": upstream["targeted_model"],
                "sha256": sha256(upstream["targeted_model"]),
                "train60": upstream["targeted_train"],
                "train60_sha256": sha256(upstream["targeted_train"]),
            },
        },
        "fixed_metrics": [
            "raw energy RMSE/MAE/max error on all21, basin12, neb9",
            "force-component RMSE/MAE/max on all21, basin12, neb9",
            "force-vector RMSE/max on all21, basin12, neb9",
            "MaxVol grade distribution on all21, basin12, neb9",
            "NEB9 relative-energy profile RMSE/MAE/max",
            "forward and backward barrier errors",
            "barrier maximum image and qPT",
            "endpoint energy-difference error",
        ],
        "evaluation_order": ["basin", "targeted"],
        "guards": {
            "model_changes": False,
            "dataset_changes": False,
            "metric_changes": False,
            "scientific_retries": False,
            "pw_x": False,
            "neb_x": False,
            "mlp_train": False,
            "select_add": False,
            "lammps": False,
        },
    }
    AUDIT_LOCK_JSON.write_text(
        json.dumps(json_safe(audit_lock), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    log(
        "Frozen audit21, both locked models, both train60 references, "
        "evaluation order and metrics were locked before the first MLP call."
    )
    log(
        "Audit evaluation order is basin first, targeted second. "
        "No model or metric changes are permitted."
    )

    basin_result = evaluate_model(
        branch="basin",
        model=upstream["basin_model"],
        train_set=upstream["basin_train"],
        audit_items=audit_items,
    )
    targeted_result = evaluate_model(
        branch="targeted",
        model=upstream["targeted_model"],
        train_set=upstream["targeted_train"],
        audit_items=audit_items,
    )
    results = [basin_result, targeted_result]

    # -------------------------------------------------------------------------
    # Per-configuration report
    # -------------------------------------------------------------------------
    per_configuration_rows: list[dict[str, Any]] = []

    for result in results:
        branch = result["branch"]
        predictions: dict[str, CFGBlock] = result["predictions"]
        grades: dict[str, float] = result["grades"]

        for item in audit_items:
            reference = item.block
            prediction = predictions[item.audit_id]

            assert reference.energy is not None
            assert reference.forces is not None
            assert prediction.energy is not None
            assert prediction.forces is not None

            force_delta = prediction.forces - reference.forces
            force_component_abs = np.abs(force_delta.reshape(-1))
            force_vector_norms = np.linalg.norm(force_delta, axis=1)

            per_configuration_rows.append(
                {
                    "model": branch,
                    "audit_index": item.audit_index,
                    "audit_id": item.audit_id,
                    "subset": item.subset,
                    "subset_index": item.subset_index,
                    "qpt_ang": item.qpt_ang,
                    "roo_ang": item.roo_ang,
                    "dft_energy_ev": reference.energy,
                    "model_energy_ev": prediction.energy,
                    "energy_error_ev":
                        prediction.energy - reference.energy,
                    "energy_abs_error_ev":
                        abs(prediction.energy - reference.energy),
                    "force_component_rmse_ev_ang":
                        float(np.sqrt(np.mean(force_delta ** 2))),
                    "force_component_mae_ev_ang":
                        float(np.mean(force_component_abs)),
                    "force_component_max_abs_ev_ang":
                        float(np.max(force_component_abs)),
                    "force_vector_rmse_ev_ang":
                        float(np.sqrt(np.mean(force_vector_norms ** 2))),
                    "force_vector_max_ev_ang":
                        float(np.max(force_vector_norms)),
                    "mv_grade": grades[item.audit_id],
                }
            )

    write_tsv(
        PER_CONFIGURATION_TSV,
        per_configuration_rows,
        list(per_configuration_rows[0]),
    )

    # -------------------------------------------------------------------------
    # Subset and grade metrics
    # -------------------------------------------------------------------------
    subset_rows: list[dict[str, Any]] = []
    grade_rows: list[dict[str, Any]] = []

    for result in results:
        for subset_name in ("all21", "basin12", "neb9"):
            metrics = result["metrics"][subset_name]
            subset_rows.append(
                {
                    "model": result["branch"],
                    "subset": subset_name,
                    "configuration_count":
                        metrics["configuration_count"],
                    "energy_rmse_ev": metrics["energy_rmse_ev"],
                    "energy_mae_ev": metrics["energy_mae_ev"],
                    "energy_max_abs_ev": metrics["energy_max_abs_ev"],
                    "energy_mean_error_ev":
                        metrics["energy_mean_error_ev"],
                    "energy_centered_rmse_ev":
                        metrics["energy_centered_rmse_ev"],
                    "force_component_rmse_ev_ang":
                        metrics["force_component_rmse_ev_ang"],
                    "force_component_mae_ev_ang":
                        metrics["force_component_mae_ev_ang"],
                    "force_component_max_abs_ev_ang":
                        metrics["force_component_max_abs_ev_ang"],
                    "force_vector_rmse_ev_ang":
                        metrics["force_vector_rmse_ev_ang"],
                    "force_vector_max_ev_ang":
                        metrics["force_vector_max_ev_ang"],
                }
            )
            grade_rows.append(
                {
                    "model": result["branch"],
                    "subset": subset_name,
                    "configuration_count":
                        metrics["configuration_count"],
                    "grade_min": metrics["grade_min"],
                    "grade_median": metrics["grade_median"],
                    "grade_mean": metrics["grade_mean"],
                    "grade_max": metrics["grade_max"],
                    "grade_gt_2_count":
                        metrics["grade_gt_2_count"],
                    "grade_gt_10_count":
                        metrics["grade_gt_10_count"],
                }
            )

    write_tsv(SUBSET_METRICS_TSV, subset_rows, list(subset_rows[0]))
    write_tsv(GRADE_METRICS_TSV, grade_rows, list(grade_rows[0]))

    # -------------------------------------------------------------------------
    # NEB profile and barrier reports
    # -------------------------------------------------------------------------
    neb_profile_rows: list[dict[str, Any]] = []

    for result in results:
        for row in result["neb_rows"]:
            neb_profile_rows.append(
                {"model": result["branch"], **row}
            )

    write_tsv(
        NEB_PROFILE_TSV,
        neb_profile_rows,
        list(neb_profile_rows[0]),
    )

    barrier_rows = [
        {
            "model": result["branch"],
            **result["barrier_metrics"],
        }
        for result in results
    ]
    write_tsv(
        BARRIER_METRICS_TSV,
        barrier_rows,
        list(barrier_rows[0]),
    )

    # -------------------------------------------------------------------------
    # Direct paired comparison. Positive delta means targeted metric is larger.
    # No winner is selected and no tuning follows.
    # -------------------------------------------------------------------------
    basin_all = basin_result["metrics"]["all21"]
    targeted_all = targeted_result["metrics"]["all21"]
    basin_basin = basin_result["metrics"]["basin12"]
    targeted_basin = targeted_result["metrics"]["basin12"]
    basin_neb = basin_result["metrics"]["neb9"]
    targeted_neb = targeted_result["metrics"]["neb9"]
    basin_barrier = basin_result["barrier_metrics"]
    targeted_barrier = targeted_result["barrier_metrics"]

    comparison_rows = [
        {
            "metric": "all21_energy_rmse_ev",
            "basin": basin_all["energy_rmse_ev"],
            "targeted": targeted_all["energy_rmse_ev"],
            "targeted_minus_basin":
                targeted_all["energy_rmse_ev"]
                - basin_all["energy_rmse_ev"],
        },
        {
            "metric": "all21_force_component_rmse_ev_ang",
            "basin": basin_all["force_component_rmse_ev_ang"],
            "targeted": targeted_all["force_component_rmse_ev_ang"],
            "targeted_minus_basin":
                targeted_all["force_component_rmse_ev_ang"]
                - basin_all["force_component_rmse_ev_ang"],
        },
        {
            "metric": "basin12_energy_rmse_ev",
            "basin": basin_basin["energy_rmse_ev"],
            "targeted": targeted_basin["energy_rmse_ev"],
            "targeted_minus_basin":
                targeted_basin["energy_rmse_ev"]
                - basin_basin["energy_rmse_ev"],
        },
        {
            "metric": "basin12_force_component_rmse_ev_ang",
            "basin": basin_basin["force_component_rmse_ev_ang"],
            "targeted": targeted_basin["force_component_rmse_ev_ang"],
            "targeted_minus_basin":
                targeted_basin["force_component_rmse_ev_ang"]
                - basin_basin["force_component_rmse_ev_ang"],
        },
        {
            "metric": "neb9_energy_rmse_ev",
            "basin": basin_neb["energy_rmse_ev"],
            "targeted": targeted_neb["energy_rmse_ev"],
            "targeted_minus_basin":
                targeted_neb["energy_rmse_ev"]
                - basin_neb["energy_rmse_ev"],
        },
        {
            "metric": "neb9_force_component_rmse_ev_ang",
            "basin": basin_neb["force_component_rmse_ev_ang"],
            "targeted": targeted_neb["force_component_rmse_ev_ang"],
            "targeted_minus_basin":
                targeted_neb["force_component_rmse_ev_ang"]
                - basin_neb["force_component_rmse_ev_ang"],
        },
        {
            "metric": "neb9_profile_rmse_ev",
            "basin": basin_barrier["profile_rmse_ev"],
            "targeted": targeted_barrier["profile_rmse_ev"],
            "targeted_minus_basin":
                targeted_barrier["profile_rmse_ev"]
                - basin_barrier["profile_rmse_ev"],
        },
        {
            "metric": "forward_barrier_abs_error_mev",
            "basin":
                basin_barrier["forward_barrier_abs_error_mev"],
            "targeted":
                targeted_barrier["forward_barrier_abs_error_mev"],
            "targeted_minus_basin":
                targeted_barrier["forward_barrier_abs_error_mev"]
                - basin_barrier["forward_barrier_abs_error_mev"],
        },
        {
            "metric": "backward_barrier_abs_error_mev",
            "basin":
                basin_barrier["backward_barrier_abs_error_mev"],
            "targeted":
                targeted_barrier["backward_barrier_abs_error_mev"],
            "targeted_minus_basin":
                targeted_barrier["backward_barrier_abs_error_mev"]
                - basin_barrier["backward_barrier_abs_error_mev"],
        },
        {
            "metric": "all21_grade_max",
            "basin": basin_all["grade_max"],
            "targeted": targeted_all["grade_max"],
            "targeted_minus_basin":
                targeted_all["grade_max"] - basin_all["grade_max"],
        },
    ]
    write_tsv(
        MODEL_COMPARISON_TSV,
        comparison_rows,
        list(comparison_rows[0]),
    )

    command_rows: list[dict[str, Any]] = []
    for result in results:
        command_rows.extend(
            [
                {
                    "model": result["branch"],
                    "operation": "mlp_calc_efs_frozen_audit21",
                    "command": " ".join(result["calc_efs_command"]),
                    "returncode": result["calc_efs_returncode"],
                    "elapsed_seconds":
                        result["calc_efs_elapsed_seconds"],
                },
                {
                    "model": result["branch"],
                    "operation": "mlp_calc_grade_frozen_audit21",
                    "command": " ".join(result["calc_grade_command"]),
                    "returncode": result["calc_grade_returncode"],
                    "elapsed_seconds":
                        result["calc_grade_elapsed_seconds"],
                },
            ]
        )
    write_tsv(
        COMMANDS_TSV,
        command_rows,
        [
            "model",
            "operation",
            "command",
            "returncode",
            "elapsed_seconds",
        ],
    )

    final_status = "PASS_FROZEN_AUDIT21_EVALUATED_NO_POST_AUDIT_TUNING"

    summary = {
        "created_utc": utc_now(),
        "status": final_status,
        "implementation_id": IMPLEMENTATION_ID,
        "run_root": RUN_ROOT,
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "audit": {
            "count": AUDIT_COUNT,
            "basin12": BASIN_AUDIT_COUNT,
            "neb9": NEB_AUDIT_COUNT,
            "labels_sha256": sha256(AUDIT_LABELS_CFG),
            "geometry_sha256": sha256(AUDIT_GEOMETRY_CFG),
            "dft_forward_barrier_ev":
                upstream["dft_forward_barrier_ev"],
            "dft_backward_barrier_ev":
                upstream["dft_backward_barrier_ev"],
        },
        "models": {
            result["branch"]: {
                "model": result["model"],
                "model_sha256": result["model_sha256"],
                "train_set": result["train_set"],
                "train_set_sha256": result["train_set_sha256"],
                "metrics": result["metrics"],
                "barrier_metrics": result["barrier_metrics"],
                "prediction_cfg": result["prediction_path"],
                "prediction_sha256": result["prediction_sha256"],
                "grade_cfg": result["grade_output"],
                "grade_sha256": result["grade_output_sha256"],
            }
            for result in results
        },
        "outputs": {
            "audit_lock": AUDIT_LOCK_JSON,
            "per_configuration": PER_CONFIGURATION_TSV,
            "subset_metrics": SUBSET_METRICS_TSV,
            "grade_metrics": GRADE_METRICS_TSV,
            "neb_profile": NEB_PROFILE_TSV,
            "barrier_metrics": BARRIER_METRICS_TSV,
            "model_comparison": MODEL_COMPARISON_TSV,
            "report": REPORT_MD,
        },
        "execution": {
            "mlp_calc_efs": True,
            "mlp_calc_grade": True,
            "pw_x": False,
            "neb_x": False,
            "mlp_train": False,
            "select_add": False,
            "lammps": False,
            "post_audit_tuning": False,
        },
    }

    summary_text = json.dumps(
        json_safe(summary),
        indent=2,
        sort_keys=True,
    ) + "\n"
    SUMMARY_JSON.write_text(summary_text, encoding="utf-8")

    report_lines = [
        "# Frozen audit21 comparison report v029",
        "",
        f"Created UTC: {utc_now()}",
        "",
        f"Status: `{final_status}`",
        "",
        "## Frozen inputs",
        "",
        f"- basin audit12: `{upstream['basin_labels']}`",
        f"- NEB audit9: `{upstream['neb_labels']}`",
        f"- basin model: `{upstream['basin_model']}`",
        f"- targeted model: `{upstream['targeted_model']}`",
        "",
        "## Audit metrics",
        "",
    ]

    for result in results:
        all_metrics = result["metrics"]["all21"]
        basin_metrics = result["metrics"]["basin12"]
        neb_metrics_subset = result["metrics"]["neb9"]
        barrier = result["barrier_metrics"]

        report_lines.extend(
            [
                f"### {result['branch']}",
                "",
                f"- all21 energy RMSE: "
                f"{all_metrics['energy_rmse_ev']:.12f} eV",
                f"- all21 force-component RMSE: "
                f"{all_metrics['force_component_rmse_ev_ang']:.12f} eV/Angstrom",
                f"- basin12 energy RMSE: "
                f"{basin_metrics['energy_rmse_ev']:.12f} eV",
                f"- basin12 force-component RMSE: "
                f"{basin_metrics['force_component_rmse_ev_ang']:.12f} eV/Angstrom",
                f"- NEB9 energy RMSE: "
                f"{neb_metrics_subset['energy_rmse_ev']:.12f} eV",
                f"- NEB9 force-component RMSE: "
                f"{neb_metrics_subset['force_component_rmse_ev_ang']:.12f} eV/Angstrom",
                f"- NEB9 profile RMSE: "
                f"{barrier['profile_rmse_ev']:.12f} eV",
                f"- predicted forward barrier: "
                f"{barrier['model_forward_barrier_ev']:.12f} eV",
                f"- forward barrier error: "
                f"{barrier['forward_barrier_error_ev'] * 1000.0:.6f} meV",
                f"- predicted backward barrier: "
                f"{barrier['model_backward_barrier_ev']:.12f} eV",
                f"- backward barrier error: "
                f"{barrier['backward_barrier_error_ev'] * 1000.0:.6f} meV",
                f"- predicted maximum image: "
                f"{barrier['model_max_image']}",
                f"- all21 maximum MaxVol grade: "
                f"{all_metrics['grade_max']:.12f}",
                "",
            ]
        )

    report_lines.extend(
        [
            "## Interpretation guard",
            "",
            "The audit was evaluated only after both models and datasets were",
            "locked. No setting, model, training set or metric was changed after",
            "audit exposure. This stage performs no retraining and no model",
            "selection for downstream tuning.",
            "",
        ]
    )
    REPORT_MD.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    STATUS_FILE.write_text(final_status + "\n", encoding="utf-8")
    write_checksums()

    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
    cleanup_running_pointer()

    basin_all = basin_result["metrics"]["all21"]
    targeted_all = targeted_result["metrics"]["all21"]
    basin_barrier = basin_result["barrier_metrics"]
    targeted_barrier = targeted_result["barrier_metrics"]

    print()
    print(
        "PASS_FROZEN_AUDIT21_EVALUATED_NO_POST_AUDIT_TUNING: "
        "STEP 31 v029 COMPLETED"
    )
    print()
    print(f"Run root:                  {RUN_ROOT}")
    print(f"Frozen audit:              {AUDIT_COUNT} = 12 basin + 9 NEB")
    print(
        f"DFT forward/back barrier: "
        f"{upstream['dft_forward_barrier_ev']:.8f} / "
        f"{upstream['dft_backward_barrier_ev']:.8f} eV"
    )
    print()
    print("Basin model:")
    print(
        f"  all21 E/F RMSE:          "
        f"{basin_all['energy_rmse_ev']:.8f} eV / "
        f"{basin_all['force_component_rmse_ev_ang']:.8f} eV/A"
    )
    print(
        f"  NEB profile RMSE:        "
        f"{basin_barrier['profile_rmse_ev']:.8f} eV"
    )
    print(
        f"  forward barrier error:   "
        f"{basin_barrier['forward_barrier_error_ev'] * 1000.0:.3f} meV"
    )
    print(
        f"  maximum grade:           {basin_all['grade_max']:.6f}"
    )
    print()
    print("Targeted model:")
    print(
        f"  all21 E/F RMSE:          "
        f"{targeted_all['energy_rmse_ev']:.8f} eV / "
        f"{targeted_all['force_component_rmse_ev_ang']:.8f} eV/A"
    )
    print(
        f"  NEB profile RMSE:        "
        f"{targeted_barrier['profile_rmse_ev']:.8f} eV"
    )
    print(
        f"  forward barrier error:   "
        f"{targeted_barrier['forward_barrier_error_ev'] * 1000.0:.3f} meV"
    )
    print(
        f"  maximum grade:           {targeted_all['grade_max']:.6f}"
    )
    print()
    print(f"Audit lock:                {AUDIT_LOCK_JSON}")
    print(f"Report:                    {REPORT_MD}")
    print(f"Summary:                   {SUMMARY_JSON}")
    print()
    print("mlp calc-efs and calc-grade WERE executed for both locked models.")
    print("pw.x, neb.x, mlp train, select-add and LAMMPS were NOT executed.")
    print("No post-audit tuning or scientific retry was performed.")


if __name__ == "__main__":
    try:
        main()

    except InterruptedRun as interruption:
        if _ATTEMPT_CREATED:
            status = "INTERRUPTED_FROZEN_AUDIT21_EVALUATION_v029"
            STATUS_FILE.write_text(status + "\n", encoding="utf-8")
            INTERRUPTED_POINTER.parent.mkdir(parents=True, exist_ok=True)
            INTERRUPTED_POINTER.write_text(
                str(RUN_ROOT) + "\n",
                encoding="utf-8",
            )
            (RUN_ROOT / "interruption_v029.json").write_text(
                json.dumps(
                    json_safe(
                        {
                            "created_utc": utc_now(),
                            "status": status,
                            "operation": interruption.operation,
                            "elapsed_seconds":
                                interruption.elapsed_seconds,
                            "current_operation": _CURRENT_OPERATION,
                        }
                    ),
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )
            cleanup_running_pointer()

        print(
            f"\nINTERRUPTED: {interruption.operation}",
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
                mark_failure("FAIL_RUNTIME_v029", error)

        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

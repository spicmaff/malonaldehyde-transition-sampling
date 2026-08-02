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
# STEP 30 / v028
#
# Equal-budget final model training:
#
#   basin model:
#       common36 + K basin-control DFT labels
#
#   targeted model:
#       common36 + K selected transition-tube DFT labels
#
# Both models are trained exactly once from byte-identical copies of the same
# locked, untrained level-12 MTP template. Shared settings are taken from the
# pre-audit v020 protocol lock.
#
# This stage may execute:
#   mlp train:       YES
#   mlp calc-errors: YES, training set only
#   mlp calc-efs:    YES, training set only
#
# This stage must not execute:
#   pw.x / neb.x / LAMMPS
#   any evaluation on frozen audit21
#   any hyperparameter search or model selection
# =============================================================================


IMPLEMENTATION_ID = "STEP30_V028_EQUAL_BUDGET_L12_TRAINING_V001"

ROOT = Path.home() / "malonaldehyde_mtp_al"
VERSIONS = ROOT / "09_strict_comparison" / "versions"
SOFTWARE = ROOT / "01_environment" / "v001" / "software"

MLP = SOFTWARE / "bin" / "mlp"
STANDARD_L12_TEMPLATE = SOFTWARE / "src" / "mlip-2" / "untrained_mtps" / "12.mtp"

V016_POINTER = (
    VERSIONS
    / "v016_common_seed_dft_labels"
    / "CURRENT_COMMON_DFT_LABELING.txt"
)
V018_POINTER = (
    VERSIONS
    / "v018_common36_l12_protocol_recovery"
    / "CURRENT_COMMON36_L12_MODEL.txt"
)
V020_POINTER = (
    VERSIONS
    / "v020_pre_audit_protocol_lock"
    / "CURRENT_PRE_AUDIT_PROTOCOL_LOCK.txt"
)
V027_POINTER = (
    VERSIONS
    / "v027_equal_budget_dft_labels48"
    / "CURRENT_EQUAL_BUDGET_DFT_LABELS48.txt"
)

VERSION_ROOT = VERSIONS / "v028_equal_budget_l12_training"
CURRENT_POINTER = VERSION_ROOT / "CURRENT_EQUAL_BUDGET_L12_MODELS.txt"
RUNNING_POINTER = VERSION_ROOT / "CURRENT_RUNNING_EQUAL_BUDGET_L12_MODELS.txt"
FAILED_POINTER = VERSION_ROOT / "LAST_FAILED_EQUAL_BUDGET_L12_MODELS.txt"
INTERRUPTED_POINTER = VERSION_ROOT / "LAST_INTERRUPTED_EQUAL_BUDGET_L12_MODELS.txt"

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"

INPUTS_DIR = RUN_ROOT / "inputs"
TEMPLATES_DIR = RUN_ROOT / "templates"
MODELS_DIR = RUN_ROOT / "models"
TRAIN_DIR = RUN_ROOT / "training"
EVALUATION_DIR = RUN_ROOT / "training_set_evaluation"
REPORTS_DIR = RUN_ROOT / "reports"
PROVENANCE_DIR = RUN_ROOT / "provenance"

STATUS_FILE = RUN_ROOT / "STATUS_v028.txt"
RUN_LOG = RUN_ROOT / "run_log_v028.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v028.json"
COMMANDS_TSV = RUN_ROOT / "commands_v028.tsv"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v028.tsv"
MODEL_LOCK_JSON = RUN_ROOT / "EQUAL_BUDGET_L12_MODEL_LOCK_v001.json"
MODEL_LOCK_MD = RUN_ROOT / "EQUAL_BUDGET_L12_MODEL_LOCK_v001.md"
REPORT_MD = REPORTS_DIR / "equal_budget_l12_training_report_v028.md"
METRICS_TSV = REPORTS_DIR / "training_set_metrics_v028.tsv"

LOCKED_TEMPLATE = TEMPLATES_DIR / "locked_untrained_l12_v028.mtp"
BASIN_INIT = TEMPLATES_DIR / "init_basin_l12_v028.mtp"
TARGETED_INIT = TEMPLATES_DIR / "init_targeted_l12_v028.mtp"

BASIN_MODEL = MODELS_DIR / "basin" / "pot_basin60_l12_v001.mtp"
TARGETED_MODEL = MODELS_DIR / "targeted" / "pot_targeted60_l12_v001.mtp"

BASIN_TRAIN_COPY = INPUTS_DIR / "train_basin_v001.cfg"
TARGETED_TRAIN_COPY = INPUTS_DIR / "train_targeted_v001.cfg"
COMMON36_COPY = INPUTS_DIR / "train_common_strict_v001.cfg"

BASIN_STDOUT = TRAIN_DIR / "basin" / "mlp_train_stdout_v028.txt"
BASIN_STDERR = TRAIN_DIR / "basin" / "mlp_train_stderr_v028.txt"
TARGETED_STDOUT = TRAIN_DIR / "targeted" / "mlp_train_stdout_v028.txt"
TARGETED_STDERR = TRAIN_DIR / "targeted" / "mlp_train_stderr_v028.txt"

BASIN_ERRORS = EVALUATION_DIR / "basin" / "calc_errors_train60_v028.txt"
TARGETED_ERRORS = EVALUATION_DIR / "targeted" / "calc_errors_train60_v028.txt"
BASIN_PREDICTIONS = EVALUATION_DIR / "basin" / "train60_predictions_v028.cfg"
TARGETED_PREDICTIONS = EVALUATION_DIR / "targeted" / "train60_predictions_v028.cfg"


EXPECTED_V016_STATUS = "PASS_ALL_DFT_LABELLED_COMMON36"
EXPECTED_V018_STATUS = "PASS_COMMON36_L12_READY_FOR_FRESH_TUBE"
EXPECTED_V020_STATUS = "PASS_PRE_AUDIT_PROTOCOL_LOCK_NO_CALCULATIONS"
EXPECTED_V027_STATUS = "PASS_EQUAL_BUDGET_DFT_LABELS48_READY_FOR_TRAINING"

EXPECTED_COMMON36_SHA256 = (
    "49c8331a88546d964fb9c0fe97bac65729fed228351e7ebee3524d59d7b93cce"
)
EXPECTED_PROTOCOL_SHA256 = (
    "0309ca4ca419458a847f1606759c792f0dfc4019108343e3d5a9721f5704d3b8"
)
EXPECTED_V027_SCRIPT_SHA256 = (
    "b74fcc1ba3877300595d9ffe939f4913a68d1adb3a04a55c647e8aa804cd1259"
)

NAT = 9
COMMON_COUNT = 36
EXPECTED_K = 24
EXPECTED_TRAIN_COUNT = COMMON_COUNT + EXPECTED_K

EXPECTED_TYPES = [2, 1, 0, 1, 0, 1, 0, 2, 1]

MTP_LEVEL = 12
SPECIES_COUNT = 3
MIN_DIST_ANG = 0.65
MAX_DIST_ANG = 6.0
ALPHA_MOMENTS_COUNT = 84
ALPHA_INDEX_TIMES_COUNT = 117

ENERGY_WEIGHT = 1.0
FORCE_WEIGHT = 0.01
STRESS_WEIGHT = 0.0
MAX_ITERATIONS = 2000

THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}

COORDINATE_TOL_ANG = 1.0e-6
CELL_TOL_ANG = 1.0e-8

TRAIN_TIMEOUT_SECONDS = 4 * 3600
AUX_TIMEOUT_SECONDS = 30 * 60
POLL_SECONDS = 1.0

RUN_MLP_TRAIN = True
RUN_MLP_CALC_ERRORS = True
RUN_MLP_CALC_EFS = True
RUN_DFT = False
RUN_NEB = False
RUN_LAMMPS = False
USE_AUDIT = False
ALLOW_HYPERPARAMETER_CHANGES = False
ALLOW_MODEL_SELECTION = False
ALLOW_WARM_START = False
UPDATE_MINDIST = False

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V028_PREFLIGHT_ONLY", "0") == "1"
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
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
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
    target_text = pointer.read_text(encoding="utf-8").strip()
    if not target_text:
        fatal(f"{label} pointer is empty: {pointer}")

    target = Path(target_text)
    if not target.is_dir():
        fatal(f"{label} attempt directory missing: {target}")

    status_path = require_file(target / status_filename, f"{label} status")
    status = status_path.read_text(encoding="utf-8").strip()
    if status != expected_status:
        fatal(
            f"{label} status mismatch: expected {expected_status!r}, "
            f"found {status!r}"
        )
    return target


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


def cleanup_running_pointer() -> None:
    if not RUNNING_POINTER.is_file():
        return
    try:
        target = RUNNING_POINTER.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if target == str(RUN_ROOT):
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
    timeout_seconds: int,
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
                if elapsed > timeout_seconds:
                    terminate_group(process)
                    fatal(
                        f"{operation}: timeout after "
                        f"{elapsed / 3600:.3f} h"
                    )

                time.sleep(POLL_SECONDS)

        except KeyboardInterrupt as error:
            terminate_group(process)
            elapsed = time.monotonic() - start
            raise InterruptedRun(operation, elapsed) from error


# =============================================================================
# CFG validation
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
    cell: np.ndarray | None = None
    types: list[int] | None = None
    positions: np.ndarray | None = None
    forces: np.ndarray | None = None
    energy: float | None = None

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
                fatal("CFG AtomData before Size")

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
                fields = lines[index + 1 + atom_offset].split()
                if len(fields) < len(columns):
                    fatal("CFG AtomData row too short")

                parsed_ids.append(int(fields[lookup["id"]]))
                parsed_types.append(int(fields[lookup["type"]]))
                parsed_positions.append(
                    [
                        parse_number(fields[lookup["cartes_x"]]),
                        parse_number(fields[lookup["cartes_y"]]),
                        parse_number(fields[lookup["cartes_z"]]),
                    ]
                )

                if has_forces:
                    parsed_forces.append(
                        [
                            parse_number(fields[lookup["fx"]]),
                            parse_number(fields[lookup["fy"]]),
                            parse_number(fields[lookup["fz"]]),
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
    if cell is None or cell.shape != (3, 3):
        fatal("CFG cell missing or malformed")
    if types is None or positions is None:
        fatal("CFG AtomData missing")
    if positions.shape != (NAT, 3):
        fatal(f"CFG coordinate shape={positions.shape}")
    if forces is not None and forces.shape != (NAT, 3):
        fatal(f"CFG force shape={forces.shape}")

    numeric_arrays = [cell, positions]
    if forces is not None:
        numeric_arrays.append(forces)

    if not all(np.all(np.isfinite(array)) for array in numeric_arrays):
        fatal("CFG contains nonfinite values")
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


def validate_labelled_dataset(
    path: Path,
    expected_count: int,
    label: str,
    *,
    allow_stress: bool = False,
) -> list[CFGBlock]:
    blocks = read_cfg(path)

    if len(blocks) != expected_count:
        fatal(
            f"{label}: {len(blocks)} configurations, "
            f"expected {expected_count}"
        )

    expected_cell = np.diag([16.0, 16.0, 16.0])

    for block in blocks:
        if block.types != EXPECTED_TYPES:
            fatal(
                f"{label} block {block.order}: atom types changed: "
                f"{block.types}"
            )

        cell_error = float(np.max(np.abs(block.cell - expected_cell)))
        if cell_error > CELL_TOL_ANG:
            fatal(
                f"{label} block {block.order}: cell error "
                f"{cell_error:.3e} A"
            )

        if block.energy is None:
            fatal(f"{label} block {block.order}: Energy missing")
        if block.forces is None:
            fatal(f"{label} block {block.order}: forces missing")

        if (
            not allow_stress
            and (
                "PlusStress" in block.raw
                or re.search(
                    r"^\s*Stress:",
                    block.raw,
                    flags=re.MULTILINE,
                )
            )
        ):
            fatal(f"{label} block {block.order}: stress labels present")

    return blocks


def candidate_id(block: CFGBlock) -> str:
    value = block.features.get("candidate_id", "").strip()
    if not value:
        fatal(f"CFG block {block.order}: candidate_id missing")
    return value


def validate_dataset_architecture(
    common_path: Path,
    basin_path: Path,
    targeted_path: Path,
) -> dict[str, Any]:
    common = validate_labelled_dataset(
        common_path,
        COMMON_COUNT,
        "common36",
    )
    basin = validate_labelled_dataset(
        basin_path,
        EXPECTED_TRAIN_COUNT,
        "train_basin",
    )
    targeted = validate_labelled_dataset(
        targeted_path,
        EXPECTED_TRAIN_COUNT,
        "train_targeted",
    )

    common_raw = [block.raw for block in common]

    if [block.raw for block in basin[:COMMON_COUNT]] != common_raw:
        fatal("train_basin first 36 blocks are not byte-identical common36")
    if [block.raw for block in targeted[:COMMON_COUNT]] != common_raw:
        fatal("train_targeted first 36 blocks are not byte-identical common36")

    basin_ids = [candidate_id(block) for block in basin[COMMON_COUNT:]]
    targeted_ids = [
        candidate_id(block) for block in targeted[COMMON_COUNT:]
    ]

    if basin_ids != sorted(basin_ids):
        fatal("basin new labels are not candidate-ID sorted")
    if targeted_ids != sorted(targeted_ids):
        fatal("targeted new labels are not candidate-ID sorted")

    if len(set(basin_ids)) != EXPECTED_K:
        fatal("basin new labels contain duplicate IDs")
    if len(set(targeted_ids)) != EXPECTED_K:
        fatal("targeted new labels contain duplicate IDs")
    if set(basin_ids) & set(targeted_ids):
        fatal("basin and targeted new labels overlap")

    if not all(value.startswith("basin_control_") for value in basin_ids):
        fatal("basin dataset contains a non-basin candidate ID")
    if not all(value.startswith("tube_") for value in targeted_ids):
        fatal("targeted dataset contains a non-tube candidate ID")

    left = sum("_left_" in value for value in basin_ids)
    right = sum("_right_" in value for value in basin_ids)
    if (left, right) != (12, 12):
        fatal(
            f"basin side balance is {left} left + {right} right, "
            "expected 12 + 12"
        )

    return {
        "common_blocks": common,
        "basin_blocks": basin,
        "targeted_blocks": targeted,
        "basin_ids": basin_ids,
        "targeted_ids": targeted_ids,
        "basin_left": left,
        "basin_right": right,
    }


# =============================================================================
# MTP template and model validation
# =============================================================================


def mtp_scalar(text: str, key: str) -> str:
    pattern = re.compile(
        rf"^\s*{re.escape(key)}\s*=\s*(.*?)\s*$",
        flags=re.MULTILINE,
    )
    matches = pattern.findall(text)
    if len(matches) != 1:
        fatal(f"MTP expected one {key}, found {len(matches)}")
    return matches[0].strip()


def mtp_integer(text: str, key: str) -> int:
    return int(parse_number(mtp_scalar(text, key)))


def mtp_float(text: str, key: str) -> float:
    return parse_number(mtp_scalar(text, key))


def replace_mtp_scalar(text: str, key: str, value: str) -> str:
    pattern = re.compile(
        rf"^(\s*{re.escape(key)}\s*=\s*).*?$",
        flags=re.MULTILINE,
    )
    result, count = pattern.subn(rf"\g<1>{value}", text)
    if count != 1:
        fatal(f"MTP could not uniquely replace {key}; count={count}")
    return result


def validate_l12_mtp_text(
    text: str,
    label: str,
    require_finite_parameters: bool,
) -> dict[str, Any]:
    potential_name = mtp_scalar(text, "potential_name")
    canonical_potential_name = potential_name.strip("'\"").upper()
    if canonical_potential_name not in {"MTP", "MTP1M"}:
        fatal(f"{label}: potential_name={potential_name!r}")

    species_count = mtp_integer(text, "species_count")
    min_dist = mtp_float(text, "min_dist")
    max_dist = mtp_float(text, "max_dist")
    alpha_moments_count = mtp_integer(text, "alpha_moments_count")
    alpha_index_times_count = mtp_integer(
        text,
        "alpha_index_times_count",
    )

    expected = {
        "species_count": (species_count, SPECIES_COUNT),
        "alpha_moments_count": (
            alpha_moments_count,
            ALPHA_MOMENTS_COUNT,
        ),
        "alpha_index_times_count": (
            alpha_index_times_count,
            ALPHA_INDEX_TIMES_COUNT,
        ),
    }

    for key, (actual, wanted) in expected.items():
        if actual != wanted:
            fatal(f"{label}: {key}={actual}, expected {wanted}")

    if not math.isclose(
        min_dist, MIN_DIST_ANG, rel_tol=0.0, abs_tol=1.0e-12
    ):
        fatal(f"{label}: min_dist={min_dist}, expected {MIN_DIST_ANG}")
    if not math.isclose(
        max_dist, MAX_DIST_ANG, rel_tol=0.0, abs_tol=1.0e-12
    ):
        fatal(f"{label}: max_dist={max_dist}, expected {MAX_DIST_ANG}")

    if require_finite_parameters and re.search(
        r"(?i)(?<![A-Za-z])(?:nan|[-+]?inf(?:inity)?)(?![A-Za-z])",
        text,
    ):
        fatal(f"{label}: nonfinite parameter token found")

    return {
        "potential_name": potential_name,
        "level": MTP_LEVEL,
        "species_count": species_count,
        "min_dist_ang": min_dist,
        "max_dist_ang": max_dist,
        "alpha_moments_count": alpha_moments_count,
        "alpha_index_times_count": alpha_index_times_count,
    }


def materialize_locked_template(source: Path) -> tuple[str, dict[str, Any]]:
    require_file(source, "standard untrained level-12 template")
    original = source.read_text(encoding="utf-8")

    source_moments = mtp_integer(original, "alpha_moments_count")
    source_index_times = mtp_integer(
        original,
        "alpha_index_times_count",
    )

    if source_moments != ALPHA_MOMENTS_COUNT:
        fatal(
            f"standard 12.mtp alpha_moments_count={source_moments}, "
            f"expected {ALPHA_MOMENTS_COUNT}"
        )
    if source_index_times != ALPHA_INDEX_TIMES_COUNT:
        fatal(
            f"standard 12.mtp alpha_index_times_count={source_index_times}, "
            f"expected {ALPHA_INDEX_TIMES_COUNT}"
        )

    patched = original
    patched = replace_mtp_scalar(
        patched,
        "species_count",
        str(SPECIES_COUNT),
    )
    patched = replace_mtp_scalar(
        patched,
        "min_dist",
        f"{MIN_DIST_ANG:.16g}",
    )
    patched = replace_mtp_scalar(
        patched,
        "max_dist",
        f"{MAX_DIST_ANG:.16g}",
    )

    metadata = validate_l12_mtp_text(
        patched,
        "locked untrained level-12 template",
        require_finite_parameters=True,
    )

    return patched.rstrip() + "\n", metadata


def validate_trained_model(
    path: Path,
    template_hash: str,
    label: str,
) -> dict[str, Any]:
    require_file(path, f"{label} trained model")
    text = path.read_text(encoding="utf-8", errors="strict")
    metadata = validate_l12_mtp_text(
        text,
        label,
        require_finite_parameters=True,
    )

    model_hash = sha256(path)
    if model_hash == template_hash:
        fatal(f"{label}: trained model is byte-identical to template")

    if path.stat().st_size <= LOCKED_TEMPLATE.stat().st_size:
        fatal(
            f"{label}: trained model is not larger than untrained template"
        )

    metadata.update(
        {
            "path": path,
            "sha256": model_hash,
            "size_bytes": path.stat().st_size,
        }
    )
    return metadata


# =============================================================================
# Upstream and CLI validation
# =============================================================================


def verify_checksum_entries(
    checksum_file: Path,
    required_paths: list[Path],
    label: str,
) -> None:
    rows = read_tsv(checksum_file)
    lookup = {row["path"]: row["sha256"] for row in rows}

    for path in required_paths:
        relative = path.relative_to(ROOT).as_posix()
        if relative not in lookup:
            fatal(f"{label}: checksum entry missing for {relative}")
        require_hash(path, lookup[relative], f"{label} locked file")


def get_mlp_help(topic: str) -> str:
    attempts = [
        [str(MLP), "help", topic],
        [str(MLP), topic, "--help"],
    ]

    outputs: list[str] = []

    for command in attempts:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
            env=mlp_environment(),
        )
        combined = result.stdout + "\n" + result.stderr
        outputs.append(
            f"$ {' '.join(command)}\n"
            f"returncode={result.returncode}\n"
            f"{combined}"
        )
        if result.returncode == 0 and combined.strip():
            return combined

    fatal(
        f"unable to obtain mlp help for {topic}:\n"
        + "\n".join(outputs)
    )


def validate_mlp_cli() -> dict[str, Any]:
    if not MLP.is_file() or not os.access(MLP, os.X_OK):
        fatal(f"mlp executable missing: {MLP}")

    train_help = get_mlp_help("train")
    calc_errors_help = get_mlp_help("calc-errors")
    calc_efs_help = get_mlp_help("calc-efs")

    required_train_options = [
        "trained-pot-name",
        "max-iter",
        "energy-weight",
        "force-weight",
        "stress-weight",
    ]
    for option in required_train_options:
        if option not in train_help:
            fatal(f"mlp train help lacks --{option}")

    if "update-mindist" not in train_help:
        fatal("mlp train help lacks update-mindist option")
    # A successful topic-specific help call is sufficient for the auxiliary
    # commands. Their help banners differ slightly among MLIP-2 builds and do
    # not always repeat the command name verbatim.

    return {
        "mlp": MLP,
        "train_help_sha256": hashlib.sha256(
            train_help.encode("utf-8")
        ).hexdigest(),
        "calc_errors_help_sha256": hashlib.sha256(
            calc_errors_help.encode("utf-8")
        ).hexdigest(),
        "calc_efs_help_sha256": hashlib.sha256(
            calc_efs_help.encode("utf-8")
        ).hexdigest(),
        "required_train_options": required_train_options,
    }


def load_upstream() -> dict[str, Any]:
    v016 = resolve_success_attempt(
        V016_POINTER,
        "STATUS_v016.txt",
        EXPECTED_V016_STATUS,
        "v016",
    )
    v018 = resolve_success_attempt(
        V018_POINTER,
        "STATUS_v018.txt",
        EXPECTED_V018_STATUS,
        "v018",
    )
    v020 = resolve_success_attempt(
        V020_POINTER,
        "STATUS_v020.txt",
        EXPECTED_V020_STATUS,
        "v020",
    )
    v027 = resolve_success_attempt(
        V027_POINTER,
        "STATUS_v027.txt",
        EXPECTED_V027_STATUS,
        "v027",
    )

    common36 = require_file(
        v016 / "datasets" / "train_common_strict_v001.cfg",
        "common36",
    )
    require_hash(common36, EXPECTED_COMMON36_SHA256, "common36")

    protocol_json = require_file(
        v020
        / "protocol_lock"
        / "PRE_AUDIT_STRICT_PROTOCOL_LOCK_v001.json",
        "v020 master protocol JSON",
    )
    protocol_text = protocol_json.read_text(encoding="utf-8")
    protocol = json.loads(protocol_text)

    protocol_md = require_file(
        v020
        / "protocol_lock"
        / "PRE_AUDIT_STRICT_PROTOCOL_LOCK_v001.md",
        "v020 master protocol Markdown",
    )
    protocol_lock_text = (
        protocol_text
        + "\n"
        + protocol_md.read_text(encoding="utf-8")
    )
    if EXPECTED_PROTOCOL_SHA256 not in protocol_lock_text:
        fatal(
            "v020 expected protocol SHA256 is absent from the locked "
            "JSON/Markdown payload"
        )

    mtp_lock = protocol["protocol"]["mtp"]
    expected_mtp_lock = {
        "level": MTP_LEVEL,
        "species_count": SPECIES_COUNT,
        "min_dist_ang": MIN_DIST_ANG,
        "max_dist_ang": MAX_DIST_ANG,
        "alpha_moments_count": ALPHA_MOMENTS_COUNT,
        "alpha_index_times_count": ALPHA_INDEX_TIMES_COUNT,
        "energy_weight": ENERGY_WEIGHT,
        "force_weight": FORCE_WEIGHT,
        "max_iterations": MAX_ITERATIONS,
        "update_mindist": False,
    }
    for key, expected in expected_mtp_lock.items():
        actual = mtp_lock.get(key)
        if actual != expected:
            fatal(
                f"v020 MTP lock {key}={actual!r}, expected {expected!r}"
            )

    final_training_protocol = require_file(
        v020
        / "specifications"
        / "final_equal_budget_training_protocol_v001.md",
        "v020 final training protocol",
    )

    verify_checksum_entries(
        require_file(v020 / "checksums_v020.tsv", "v020 checksums"),
        [
            protocol_json,
            protocol_md,
            final_training_protocol,
        ],
        "v020",
    )

    final_text = final_training_protocol.read_text(encoding="utf-8")

    required_phrases = [
        "MTP level: 12",
        "species_count: 3",
        "min_dist: 0.65 Angstrom",
        "max_dist: 6.00 Angstrom",
        "energy weight: 1.0",
        "force weight: 0.01",
        "maximum iterations: 2000",
        "stress weight: zero / no PlusStress",
        "one computational thread",
        "omit --update-mindist completely",
        "byte-identical",
        "same locked untrained level-12 template",
        "No warm start",
        "common36 in its frozen existing order",
        "branch-specific K structures sorted by candidate ID",
        "Train exactly one basin model and one targeted model",
        "may not trigger",
        "hyperparameter changes",
        "Neither model may be evaluated on the frozen audit until",
        "both models, datasets, commands and checksums are locked",
    ]
    for phrase in required_phrases:
        if phrase not in final_text:
            fatal(f"v020 final training protocol lacks {phrase!r}")

    summary_path = require_file(v027 / "summary_v027.json", "v027 summary")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    if summary.get("status") != EXPECTED_V027_STATUS:
        fatal("v027 summary status mismatch")
    if int(summary.get("K", 0)) != EXPECTED_K:
        fatal(f"v027 K={summary.get('K')}, expected {EXPECTED_K}")

    counts = summary.get("counts", {})
    expected_counts = {
        "common": COMMON_COUNT,
        "targeted_new": EXPECTED_K,
        "basin_new": EXPECTED_K,
        "train_targeted": EXPECTED_TRAIN_COUNT,
        "train_basin": EXPECTED_TRAIN_COUNT,
    }
    for key, expected in expected_counts.items():
        if int(counts.get(key, -1)) != expected:
            fatal(
                f"v027 count {key}={counts.get(key)}, expected {expected}"
            )

    basin_train = require_file(
        v027 / "datasets" / "train_basin_v001.cfg",
        "v027 basin train60",
    )
    targeted_train = require_file(
        v027 / "datasets" / "train_targeted_v001.cfg",
        "v027 targeted train60",
    )
    basin_labels = require_file(
        v027 / "labels" / "basin_control_new_labels_v027.cfg",
        "v027 basin labels",
    )
    targeted_labels = require_file(
        v027 / "labels" / "targeted_new_labels_v027.cfg",
        "v027 targeted labels",
    )

    provenance_scripts = sorted(
        path
        for path in (v027 / "provenance").glob("step29*.py")
        if path.is_file()
    )
    if len(provenance_scripts) != 1:
        fatal(
            f"v027 expected one provenance script, "
            f"found {len(provenance_scripts)}"
        )
    v027_script = provenance_scripts[0]
    require_hash(
        v027_script,
        EXPECTED_V027_SCRIPT_SHA256,
        "successful v027 implementation",
    )

    verify_checksum_entries(
        require_file(v027 / "checksums_v027.tsv", "v027 checksums"),
        [
            summary_path,
            basin_train,
            targeted_train,
            basin_labels,
            targeted_labels,
            v027_script,
        ],
        "v027",
    )

    architecture = validate_dataset_architecture(
        common36,
        basin_train,
        targeted_train,
    )

    # v018 is resolved only through its successful status pointer as
    # historical protocol-recovery provenance. Its trained model and ALS state
    # are deliberately not opened, copied or used for initialization.
    cli = validate_mlp_cli()
    template_text, template_metadata = materialize_locked_template(
        STANDARD_L12_TEMPLATE
    )

    basin_command_preview = build_train_command(
        Path("init_basin_l12_v028.mtp"),
        Path("train_basin_v001.cfg"),
        Path("pot_basin60_l12_v001.mtp"),
    )
    targeted_command_preview = build_train_command(
        Path("init_targeted_l12_v028.mtp"),
        Path("train_targeted_v001.cfg"),
        Path("pot_targeted60_l12_v001.mtp"),
    )

    return {
        "v016": v016,
        "v018": v018,
        "v020": v020,
        "v027": v027,
        "common36": common36,
        "basin_train": basin_train,
        "targeted_train": targeted_train,
        "basin_labels": basin_labels,
        "targeted_labels": targeted_labels,
        "v027_script": v027_script,
        "protocol_json": protocol_json,
        "final_training_protocol": final_training_protocol,
        "architecture": architecture,
        "cli": cli,
        "template_text": template_text,
        "template_metadata": template_metadata,
        "template_source": STANDARD_L12_TEMPLATE,
        "template_source_sha256": sha256(STANDARD_L12_TEMPLATE),
        "basin_command_preview": basin_command_preview,
        "targeted_command_preview": targeted_command_preview,
    }


# =============================================================================
# Training and own-training-set evaluation
# =============================================================================


def build_train_command(
    init_model: Path,
    dataset: Path,
    output_model: Path,
) -> list[str]:
    command = [
        str(MLP),
        "train",
        str(init_model),
        str(dataset),
        f"--trained-pot-name={output_model}",
        f"--max-iter={MAX_ITERATIONS}",
        f"--energy-weight={ENERGY_WEIGHT:g}",
        f"--force-weight={FORCE_WEIGHT:g}",
        f"--stress-weight={STRESS_WEIGHT:g}",
    ]

    if any("update-mindist" in token for token in command):
        fatal("internal error: train command contains update-mindist")
    if any("valid-cfgs" in token for token in command):
        fatal("internal error: train command contains validation set")
    if any("init-params" in token for token in command):
        fatal("internal error: unregistered initialization option present")

    return command


def parse_calc_errors(path: Path) -> dict[str, Any]:
    text = require_file(path, "calc-errors output").read_text(
        encoding="utf-8",
        errors="replace",
    )

    if re.search(
        r"(?i)(?<![A-Za-z])(?:nan|[-+]?inf(?:inity)?)(?![A-Za-z])",
        text,
    ):
        fatal(f"{path}: nonfinite calc-errors output")

    def section(name: str, next_name: str) -> str:
        pattern = re.compile(
            rf"(?ms)^{re.escape(name)}:\s*(.*?)"
            rf"(?=^{re.escape(next_name)}:)",
        )
        match = pattern.search(text)
        if not match:
            fatal(f"{path}: {name} section missing")
        return match.group(1)

    energy_section = section("Energy", "Energy per atom")
    force_section = section("Forces", "Stresses (in eV)")

    rms_pattern = re.compile(
        r"RMS\s+absolute\s+difference\s*=\s*"
        r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?)"
    )

    energy_match = rms_pattern.search(energy_section)
    force_match = rms_pattern.search(force_section)

    if not energy_match or not force_match:
        fatal(f"{path}: RMS values missing")

    return {
        "reported_energy_rms_ev":
            parse_number(energy_match.group(1)),
        "reported_force_rms_ev_ang":
            parse_number(force_match.group(1)),
        "output_sha256": sha256(path),
    }


def evaluate_predictions(
    reference_path: Path,
    prediction_path: Path,
    label: str,
) -> dict[str, Any]:
    reference = validate_labelled_dataset(
        reference_path,
        EXPECTED_TRAIN_COUNT,
        f"{label} reference",
    )
    predictions = validate_labelled_dataset(
        prediction_path,
        EXPECTED_TRAIN_COUNT,
        f"{label} predictions",
        allow_stress=True,
    )

    energy_errors: list[float] = []
    force_component_errors: list[float] = []
    force_vector_errors: list[float] = []

    for ref, pred in zip(reference, predictions):
        if ref.types != pred.types:
            fatal(f"{label} block {ref.order}: prediction types changed")

        coordinate_error = float(
            np.max(np.abs(ref.positions - pred.positions))
        )
        if coordinate_error > COORDINATE_TOL_ANG:
            fatal(
                f"{label} block {ref.order}: prediction coordinates "
                f"changed by {coordinate_error:.3e} A"
            )

        cell_error = float(np.max(np.abs(ref.cell - pred.cell)))
        if cell_error > CELL_TOL_ANG:
            fatal(
                f"{label} block {ref.order}: prediction cell changed "
                f"by {cell_error:.3e} A"
            )

        assert ref.energy is not None
        assert pred.energy is not None
        assert ref.forces is not None
        assert pred.forces is not None

        energy_errors.append(pred.energy - ref.energy)

        force_delta = pred.forces - ref.forces
        force_component_errors.extend(force_delta.reshape(-1).tolist())
        force_vector_errors.extend(
            np.linalg.norm(force_delta, axis=1).tolist()
        )

    energy_array = np.asarray(energy_errors, dtype=float)
    component_array = np.asarray(force_component_errors, dtype=float)
    vector_array = np.asarray(force_vector_errors, dtype=float)

    if not all(
        np.all(np.isfinite(array))
        for array in (energy_array, component_array, vector_array)
    ):
        fatal(f"{label}: nonfinite training prediction error")

    return {
        "configuration_count": len(reference),
        "force_component_count": int(component_array.size),
        "energy_rmse_ev":
            float(np.sqrt(np.mean(energy_array ** 2))),
        "energy_mae_ev":
            float(np.mean(np.abs(energy_array))),
        "energy_max_abs_ev":
            float(np.max(np.abs(energy_array))),
        "force_component_rmse_ev_ang":
            float(np.sqrt(np.mean(component_array ** 2))),
        "force_component_mae_ev_ang":
            float(np.mean(np.abs(component_array))),
        "force_component_max_abs_ev_ang":
            float(np.max(np.abs(component_array))),
        "force_vector_rmse_ev_ang":
            float(np.sqrt(np.mean(vector_array ** 2))),
        "force_vector_max_ev_ang":
            float(np.max(vector_array)),
        "prediction_sha256": sha256(prediction_path),
    }


def train_branch(
    branch: str,
    init_model: Path,
    dataset: Path,
    output_model: Path,
    stdout_path: Path,
    stderr_path: Path,
    errors_path: Path,
    prediction_path: Path,
    template_hash: str,
) -> dict[str, Any]:
    command = build_train_command(init_model, dataset, output_model)

    log(
        f"Starting {branch} level-12 training from locked untrained "
        f"template; configs={EXPECTED_TRAIN_COUNT}."
    )

    returncode, elapsed = run_command(
        command,
        stdout_path,
        stderr_path,
        TRAIN_TIMEOUT_SECONDS,
        f"mlp train {branch}",
    )

    if returncode != 0:
        fatal(f"{branch} mlp train return code {returncode}")

    model_metadata = validate_trained_model(
        output_model,
        template_hash,
        f"{branch} model",
    )

    calc_errors_command = [
        str(MLP),
        "calc-errors",
        str(output_model),
        str(dataset),
    ]
    calc_errors_stderr = errors_path.with_suffix(".stderr.txt")
    errors_code, errors_elapsed = run_command(
        calc_errors_command,
        errors_path,
        calc_errors_stderr,
        AUX_TIMEOUT_SECONDS,
        f"mlp calc-errors {branch}",
    )
    if errors_code != 0:
        fatal(f"{branch} calc-errors return code {errors_code}")

    reported_errors = parse_calc_errors(errors_path)

    calc_efs_command = [
        str(MLP),
        "calc-efs",
        str(output_model),
        str(dataset),
        str(prediction_path),
    ]
    calc_efs_stdout = prediction_path.with_suffix(".calc_efs_stdout.txt")
    calc_efs_stderr = prediction_path.with_suffix(".calc_efs_stderr.txt")
    calc_efs_code, calc_efs_elapsed = run_command(
        calc_efs_command,
        calc_efs_stdout,
        calc_efs_stderr,
        AUX_TIMEOUT_SECONDS,
        f"mlp calc-efs {branch}",
    )
    if calc_efs_code != 0:
        fatal(f"{branch} calc-efs return code {calc_efs_code}")

    independent_metrics = evaluate_predictions(
        dataset,
        prediction_path,
        branch,
    )

    # MLIP's force RMS convention may be vector-based rather than component-
    # based, so it is recorded but not forced to equal the independently
    # calculated force-component RMSE.
    if not math.isclose(
        reported_errors["reported_energy_rms_ev"],
        independent_metrics["energy_rmse_ev"],
        rel_tol=2.0e-4,
        abs_tol=2.0e-7,
    ):
        fatal(
            f"{branch}: calc-errors energy RMS "
            f"{reported_errors['reported_energy_rms_ev']:.12g} differs "
            f"from independent energy RMSE "
            f"{independent_metrics['energy_rmse_ev']:.12g}"
        )

    log(
        f"{branch} PASS: train time={elapsed:.2f} s; "
        f"E_RMSE={independent_metrics['energy_rmse_ev']:.8f} eV; "
        f"F_component_RMSE="
        f"{independent_metrics['force_component_rmse_ev_ang']:.8f} eV/A; "
        f"max vector error="
        f"{independent_metrics['force_vector_max_ev_ang']:.8f} eV/A."
    )

    return {
        "branch": branch,
        "train_command": command,
        "train_returncode": returncode,
        "train_elapsed_seconds": elapsed,
        "train_stdout": stdout_path,
        "train_stderr": stderr_path,
        "init_model": init_model,
        "init_model_sha256": sha256(init_model),
        "dataset": dataset,
        "dataset_sha256": sha256(dataset),
        "model": output_model,
        "model_metadata": model_metadata,
        "calc_errors_command": calc_errors_command,
        "calc_errors_returncode": errors_code,
        "calc_errors_elapsed_seconds": errors_elapsed,
        "calc_errors_output": errors_path,
        "reported_errors": reported_errors,
        "calc_efs_command": calc_efs_command,
        "calc_efs_returncode": calc_efs_code,
        "calc_efs_elapsed_seconds": calc_efs_elapsed,
        "prediction_cfg": prediction_path,
        "independent_metrics": independent_metrics,
    }


# =============================================================================
# Failure and final lock
# =============================================================================


def mark_failure(status: str, error: BaseException) -> None:
    if not _ATTEMPT_CREATED:
        return

    STATUS_FILE.write_text(status + "\n", encoding="utf-8")
    FAILED_POINTER.parent.mkdir(parents=True, exist_ok=True)
    FAILED_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    (RUN_ROOT / "failure_v028.json").write_text(
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


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    global _ATTEMPT_CREATED

    if not all(
        [RUN_MLP_TRAIN, RUN_MLP_CALC_ERRORS, RUN_MLP_CALC_EFS]
    ):
        fatal("v028 required MLP execution guards were modified")

    if any(
        [
            RUN_DFT,
            RUN_NEB,
            RUN_LAMMPS,
            USE_AUDIT,
            ALLOW_HYPERPARAMETER_CHANGES,
            ALLOW_MODEL_SELECTION,
            ALLOW_WARM_START,
            UPDATE_MINDIST,
        ]
    ):
        fatal("v028 scientific guards were modified")

    upstream = load_upstream()

    template_bytes = upstream["template_text"].encode("utf-8")
    template_hash = hashlib.sha256(template_bytes).hexdigest()

    if PREFLIGHT_ONLY:
        print("PASS_V028_PREFLIGHT_NO_TRAINING_NO_AUDIT")
        print(f"source v027:             {upstream['v027']}")
        print(f"train_basin count:       {EXPECTED_TRAIN_COUNT}")
        print(f"train_targeted count:    {EXPECTED_TRAIN_COUNT}")
        print(
            f"basin allocation:        "
            f"{upstream['architecture']['basin_left']} left + "
            f"{upstream['architecture']['basin_right']} right"
        )
        print("dataset architecture:    common36 + candidate-ID-sorted K")
        print(f"MTP level:               {MTP_LEVEL}")
        print(f"species_count:           {SPECIES_COUNT}")
        print(f"min_dist/max_dist:       {MIN_DIST_ANG:.2f} / {MAX_DIST_ANG:.2f} A")
        print(
            f"alpha counts:            "
            f"{ALPHA_MOMENTS_COUNT} moments / "
            f"{ALPHA_INDEX_TIMES_COUNT} index-times"
        )
        print(
            f"weights E/F/stress:      "
            f"{ENERGY_WEIGHT:g} / {FORCE_WEIGHT:g} / "
            f"{STRESS_WEIGHT:g}"
        )
        print(f"maximum iterations:      {MAX_ITERATIONS}")
        print("computational threads:   1")
        print(f"template source:         {upstream['template_source']}")
        print(f"template source SHA256:  {upstream['template_source_sha256']}")
        print(f"locked template SHA256:  {template_hash}")
        print("initialization:          byte-identical independent copies")
        print("warm start:              FORBIDDEN")
        print("--update-mindist:        OMITTED")
        print("training order:          basin, then targeted")
        print(
            "basin train command:     "
            + " ".join(str(token) for token in upstream["basin_command_preview"])
        )
        print(
            "targeted train command:  "
            + " ".join(str(token) for token in upstream["targeted_command_preview"])
        )
        print("audit files:             NOT OPENED")
        print("attempt directory:       NOT CREATED")
        print("mlp train:               NOT EXECUTED")
        print("mlp calc-errors/efs:     NOT EXECUTED")
        print("pw.x/neb.x/LAMMPS:       NOT EXECUTED")
        return

    if RUN_ROOT.exists():
        fatal(f"attempt already exists: {RUN_ROOT}")

    for directory in (
        RUN_ROOT,
        INPUTS_DIR,
        TEMPLATES_DIR,
        MODELS_DIR / "basin",
        MODELS_DIR / "targeted",
        TRAIN_DIR / "basin",
        TRAIN_DIR / "targeted",
        EVALUATION_DIR / "basin",
        EVALUATION_DIR / "targeted",
        REPORTS_DIR,
        PROVENANCE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    _ATTEMPT_CREATED = True
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(
        "RUNNING_EQUAL_BUDGET_L12_TRAINING_v028\n",
        encoding="utf-8",
    )
    RUNNING_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    shutil.copy2(upstream["common36"], COMMON36_COPY)
    shutil.copy2(upstream["basin_train"], BASIN_TRAIN_COPY)
    shutil.copy2(upstream["targeted_train"], TARGETED_TRAIN_COPY)

    LOCKED_TEMPLATE.write_bytes(template_bytes)
    shutil.copy2(LOCKED_TEMPLATE, BASIN_INIT)
    shutil.copy2(LOCKED_TEMPLATE, TARGETED_INIT)

    if not (
        sha256(LOCKED_TEMPLATE)
        == sha256(BASIN_INIT)
        == sha256(TARGETED_INIT)
        == template_hash
    ):
        fatal("untrained level-12 template copies are not byte-identical")

    provenance_sources = [
        upstream["protocol_json"],
        upstream["final_training_protocol"],
        upstream["v027_script"],
        Path(__file__).resolve(),
        upstream["template_source"],
    ]
    for source in provenance_sources:
        destination = PROVENANCE_DIR / source.name
        if destination.exists():
            destination = (
                PROVENANCE_DIR
                / f"{source.stem}_copy{source.suffix}"
            )
        shutil.copy2(source, destination)

    log(
        "Validated frozen train60 datasets, v020 shared level-12 settings, "
        "MLIP CLI, and byte-identical untrained template copies."
    )
    log(
        "No audit geometry or audit label was opened. Training order is "
        "basin first, targeted second."
    )

    results: list[dict[str, Any]] = []

    basin_result = train_branch(
        branch="basin",
        init_model=BASIN_INIT,
        dataset=BASIN_TRAIN_COPY,
        output_model=BASIN_MODEL,
        stdout_path=BASIN_STDOUT,
        stderr_path=BASIN_STDERR,
        errors_path=BASIN_ERRORS,
        prediction_path=BASIN_PREDICTIONS,
        template_hash=template_hash,
    )
    results.append(basin_result)

    targeted_result = train_branch(
        branch="targeted",
        init_model=TARGETED_INIT,
        dataset=TARGETED_TRAIN_COPY,
        output_model=TARGETED_MODEL,
        stdout_path=TARGETED_STDOUT,
        stderr_path=TARGETED_STDERR,
        errors_path=TARGETED_ERRORS,
        prediction_path=TARGETED_PREDICTIONS,
        template_hash=template_hash,
    )
    results.append(targeted_result)

    # Reconfirm that neither initialization file was modified in-place.
    if sha256(BASIN_INIT) != template_hash:
        fatal("basin initialization template was modified in-place")
    if sha256(TARGETED_INIT) != template_hash:
        fatal("targeted initialization template was modified in-place")

    command_rows: list[dict[str, Any]] = []
    for result in results:
        command_rows.extend(
            [
                {
                    "branch": result["branch"],
                    "operation": "mlp_train",
                    "command": " ".join(result["train_command"]),
                    "returncode": result["train_returncode"],
                    "elapsed_seconds": result["train_elapsed_seconds"],
                },
                {
                    "branch": result["branch"],
                    "operation": "mlp_calc_errors_own_train60",
                    "command": " ".join(result["calc_errors_command"]),
                    "returncode": result["calc_errors_returncode"],
                    "elapsed_seconds": result["calc_errors_elapsed_seconds"],
                },
                {
                    "branch": result["branch"],
                    "operation": "mlp_calc_efs_own_train60",
                    "command": " ".join(result["calc_efs_command"]),
                    "returncode": result["calc_efs_returncode"],
                    "elapsed_seconds": result["calc_efs_elapsed_seconds"],
                },
            ]
        )

    write_tsv(
        COMMANDS_TSV,
        command_rows,
        [
            "branch",
            "operation",
            "command",
            "returncode",
            "elapsed_seconds",
        ],
    )

    metrics_rows: list[dict[str, Any]] = []
    for result in results:
        metrics = result["independent_metrics"]
        metrics_rows.append(
            {
                "branch": result["branch"],
                "configurations": metrics["configuration_count"],
                "energy_rmse_ev": metrics["energy_rmse_ev"],
                "energy_mae_ev": metrics["energy_mae_ev"],
                "energy_max_abs_ev": metrics["energy_max_abs_ev"],
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
                "mlip_reported_energy_rms_ev":
                    result["reported_errors"]["reported_energy_rms_ev"],
                "mlip_reported_force_rms_ev_ang":
                    result["reported_errors"]["reported_force_rms_ev_ang"],
            }
        )

    write_tsv(
        METRICS_TSV,
        metrics_rows,
        list(metrics_rows[0]),
    )

    final_status = (
        "PASS_EQUAL_BUDGET_L12_MODELS_LOCKED_READY_FOR_FROZEN_AUDIT"
    )

    model_lock = {
        "created_utc": utc_now(),
        "status": final_status,
        "implementation_id": IMPLEMENTATION_ID,
        "run_root": RUN_ROOT,
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "upstream": {
            "v016": upstream["v016"],
            "v018_protocol_recovery_only": upstream["v018"],
            "v020": upstream["v020"],
            "v027": upstream["v027"],
        },
        "datasets": {
            "basin": {
                "path": BASIN_TRAIN_COPY,
                "sha256": sha256(BASIN_TRAIN_COPY),
                "count": EXPECTED_TRAIN_COUNT,
                "architecture": "common36 + basin24",
            },
            "targeted": {
                "path": TARGETED_TRAIN_COPY,
                "sha256": sha256(TARGETED_TRAIN_COPY),
                "count": EXPECTED_TRAIN_COUNT,
                "architecture": "common36 + targeted24",
            },
        },
        "template": {
            "source": upstream["template_source"],
            "source_sha256": upstream["template_source_sha256"],
            "locked_path": LOCKED_TEMPLATE,
            "locked_sha256": template_hash,
            "basin_init_sha256": sha256(BASIN_INIT),
            "targeted_init_sha256": sha256(TARGETED_INIT),
            "byte_identical": True,
            "metadata": upstream["template_metadata"],
        },
        "shared_training_settings": {
            "level": MTP_LEVEL,
            "species_count": SPECIES_COUNT,
            "min_dist_ang": MIN_DIST_ANG,
            "max_dist_ang": MAX_DIST_ANG,
            "alpha_moments_count": ALPHA_MOMENTS_COUNT,
            "alpha_index_times_count": ALPHA_INDEX_TIMES_COUNT,
            "energy_weight": ENERGY_WEIGHT,
            "force_weight": FORCE_WEIGHT,
            "stress_weight": STRESS_WEIGHT,
            "max_iterations": MAX_ITERATIONS,
            "threads": 1,
            "update_mindist": False,
            "warm_start": False,
            "hyperparameter_search": False,
            "model_selection": False,
        },
        "training_order": ["basin", "targeted"],
        "branches": {
            result["branch"]: {
                "model": result["model"],
                "model_sha256":
                    result["model_metadata"]["sha256"],
                "command": result["train_command"],
                "training_set_metrics":
                    result["independent_metrics"],
                "own_training_set_only": True,
            }
            for result in results
        },
        "execution": {
            "mlp_train": True,
            "mlp_calc_errors": True,
            "mlp_calc_efs": True,
            "pw_x": False,
            "neb_x": False,
            "lammps": False,
            "audit_opened_or_evaluated": False,
        },
    }

    MODEL_LOCK_JSON.write_text(
        json.dumps(json_safe(model_lock), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    MODEL_LOCK_MD.write_text(
        "\n".join(
            [
                "# Equal-budget level-12 model lock v001",
                "",
                f"Created UTC: {utc_now()}",
                "",
                f"Status: `{final_status}`",
                "",
                "## Frozen models",
                "",
                f"- basin: `{BASIN_MODEL}`",
                f"- basin SHA256: `{sha256(BASIN_MODEL)}`",
                f"- targeted: `{TARGETED_MODEL}`",
                f"- targeted SHA256: `{sha256(TARGETED_MODEL)}`",
                "",
                "## Equal initialization",
                "",
                f"- locked untrained template: `{LOCKED_TEMPLATE}`",
                f"- template SHA256: `{template_hash}`",
                "- basin and targeted initialization copies are byte-identical;",
                "- no warm start;",
                "- no pilot model;",
                "- no model selection.",
                "",
                "## Shared settings",
                "",
                f"- MTP level: {MTP_LEVEL}",
                f"- species_count: {SPECIES_COUNT}",
                f"- min_dist: {MIN_DIST_ANG:.2f} Angstrom",
                f"- max_dist: {MAX_DIST_ANG:.2f} Angstrom",
                f"- energy weight: {ENERGY_WEIGHT:g}",
                f"- force weight: {FORCE_WEIGHT:g}",
                f"- stress weight: {STRESS_WEIGHT:g}",
                f"- maximum iterations: {MAX_ITERATIONS}",
                "- computational threads: 1",
                "- --update-mindist omitted",
                "",
                "## Audit guard",
                "",
                "No audit geometry or label was opened or evaluated in v028.",
                "Both models, datasets, commands and checksums are now locked.",
                "The next stage may evaluate both models once on frozen audit21.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    report_lines = [
        "# Equal-budget level-12 training report v028",
        "",
        f"Created UTC: {utc_now()}",
        "",
        f"Status: `{final_status}`",
        "",
        "## Inputs",
        "",
        f"- train_basin: `{BASIN_TRAIN_COPY}`",
        f"- train_targeted: `{TARGETED_TRAIN_COPY}`",
        f"- configurations per branch: {EXPECTED_TRAIN_COUNT}",
        f"- common prefix: {COMMON_COUNT}",
        f"- branch-specific additions: {EXPECTED_K}",
        "",
        "## Models",
        "",
    ]

    for result in results:
        metrics = result["independent_metrics"]
        report_lines.extend(
            [
                f"### {result['branch']}",
                "",
                f"- model: `{result['model']}`",
                f"- model SHA256: `{result['model_metadata']['sha256']}`",
                f"- training time: {result['train_elapsed_seconds']:.6f} s",
                f"- own-train energy RMSE: "
                f"{metrics['energy_rmse_ev']:.12f} eV/configuration",
                f"- own-train force-component RMSE: "
                f"{metrics['force_component_rmse_ev_ang']:.12f} eV/Angstrom",
                f"- own-train maximum force-vector error: "
                f"{metrics['force_vector_max_ev_ang']:.12f} eV/Angstrom",
                "",
            ]
        )

    report_lines.extend(
        [
            "## Scientific guards",
            "",
            "- no hyperparameter changes;",
            "- no retries for scientific quality;",
            "- no cross-branch model selection;",
            "- no frozen-audit evaluation;",
            "- no DFT, NEB or LAMMPS execution.",
            "",
            "Training errors are descriptive only and did not affect settings.",
            "",
        ]
    )

    REPORT_MD.write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    summary = {
        "created_utc": utc_now(),
        "status": final_status,
        "run_root": RUN_ROOT,
        "counts": {
            "common": COMMON_COUNT,
            "K": EXPECTED_K,
            "train_basin": EXPECTED_TRAIN_COUNT,
            "train_targeted": EXPECTED_TRAIN_COUNT,
            "models": 2,
        },
        "models": {
            result["branch"]: {
                "path": result["model"],
                "sha256": result["model_metadata"]["sha256"],
                "metrics": result["independent_metrics"],
                "train_elapsed_seconds":
                    result["train_elapsed_seconds"],
            }
            for result in results
        },
        "template_sha256": template_hash,
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "model_lock": MODEL_LOCK_JSON,
        "report": REPORT_MD,
        "execution": {
            "mlp_train": True,
            "mlp_calc_errors": True,
            "mlp_calc_efs": True,
            "pw_x": False,
            "neb_x": False,
            "lammps": False,
            "audit_evaluation": False,
        },
    }

    SUMMARY_JSON.write_text(
        json.dumps(json_safe(summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    STATUS_FILE.write_text(final_status + "\n", encoding="utf-8")
    write_checksums()

    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
    cleanup_running_pointer()

    basin_metrics = basin_result["independent_metrics"]
    targeted_metrics = targeted_result["independent_metrics"]

    print()
    print(
        "PASS_EQUAL_BUDGET_L12_MODELS_LOCKED_READY_FOR_FROZEN_AUDIT: "
        "STEP 30 v028 COMPLETED"
    )
    print()
    print(f"Run root:                  {RUN_ROOT}")
    print(f"Configurations/model:      {EXPECTED_TRAIN_COUNT}")
    print(f"Locked template SHA256:    {template_hash}")
    print()
    print(f"Basin model:               {BASIN_MODEL}")
    print(
        f"Basin E/F RMSE:            "
        f"{basin_metrics['energy_rmse_ev']:.8f} eV / "
        f"{basin_metrics['force_component_rmse_ev_ang']:.8f} eV/A"
    )
    print()
    print(f"Targeted model:            {TARGETED_MODEL}")
    print(
        f"Targeted E/F RMSE:         "
        f"{targeted_metrics['energy_rmse_ev']:.8f} eV / "
        f"{targeted_metrics['force_component_rmse_ev_ang']:.8f} eV/A"
    )
    print()
    print(f"Model lock:                {MODEL_LOCK_JSON}")
    print(f"Report:                    {REPORT_MD}")
    print()
    print("mlp train WAS executed exactly once per branch.")
    print("mlp calc-errors and calc-efs used only each model's own train60.")
    print("pw.x, neb.x and LAMMPS were NOT executed.")
    print("Frozen audit21 was NOT opened or evaluated.")
    print()
    print("Next stage: one frozen audit21 evaluation of both locked models.")


if __name__ == "__main__":
    try:
        main()

    except InterruptedRun as interruption:
        if _ATTEMPT_CREATED:
            status = "INTERRUPTED_EQUAL_BUDGET_L12_TRAINING_v028"
            STATUS_FILE.write_text(status + "\n", encoding="utf-8")
            INTERRUPTED_POINTER.parent.mkdir(parents=True, exist_ok=True)
            INTERRUPTED_POINTER.write_text(
                str(RUN_ROOT) + "\n",
                encoding="utf-8",
            )
            (RUN_ROOT / "interruption_v028.json").write_text(
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
                mark_failure("FAIL_RUNTIME_v028", error)

        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

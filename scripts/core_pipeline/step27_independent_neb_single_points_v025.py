from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


# ======================================================================
# Project paths
# ======================================================================

ROOT = Path.home() / "malonaldehyde_mtp_al"
ENV_PREFIX = Path.home() / "miniforge3" / "envs" / "malon_mtp"
PW_X = ENV_PREFIX / "bin" / "pw.x"
MPIRUN = ENV_PREFIX / "bin" / "mpirun"
CONDA_LIB = ENV_PREFIX / "lib"

V020_POINTER = (
    ROOT
    / "09_strict_comparison"
    / "versions"
    / "v020_pre_audit_protocol_lock"
    / "CURRENT_PRE_AUDIT_PROTOCOL_LOCK.txt"
)

V023_POINTER = (
    ROOT
    / "09_strict_comparison"
    / "versions"
    / "v023_basin_audit_force_block_reparse"
    / "CURRENT_BASIN_AUDIT_FORCE_BLOCK_REPARSE.txt"
)

V024_POINTER = (
    ROOT
    / "09_strict_comparison"
    / "versions"
    / "v024_independent_neb_dft"
    / "CURRENT_INDEPENDENT_NEB_DFT.txt"
)

VERSION_ROOT = (
    ROOT
    / "09_strict_comparison"
    / "versions"
    / "v025_independent_neb_single_points"
)

CURRENT_POINTER = (
    VERSION_ROOT
    / "CURRENT_INDEPENDENT_NEB_SINGLE_POINTS.txt"
)

RUNNING_POINTER = (
    VERSION_ROOT
    / "CURRENT_RUNNING_INDEPENDENT_NEB_SINGLE_POINTS.txt"
)

FAILED_POINTER = (
    VERSION_ROOT
    / "LAST_FAILED_INDEPENDENT_NEB_SINGLE_POINTS.txt"
)

INTERRUPTED_POINTER = (
    VERSION_ROOT
    / "LAST_INTERRUPTED_INDEPENDENT_NEB_SINGLE_POINTS.txt"
)

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"

CASES_DIR = RUN_ROOT / "cases"
INPUTS_DIR = RUN_ROOT / "inputs"
LABELS_DIR = RUN_ROOT / "labels"
REPORTS_DIR = RUN_ROOT / "reports"
PROVENANCE_DIR = RUN_ROOT / "provenance"
EXTRACTED_DIR = RUN_ROOT / "extracted_force_blocks"

STATUS_FILE = RUN_ROOT / "STATUS_v025.txt"
RUN_LOG = RUN_ROOT / "run_log_v025.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v025.json"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v025.tsv"

GEOMETRY_MANIFEST_TSV = (
    REPORTS_DIR / "final_neb_geometry_manifest_v025.tsv"
)
CASE_REPORT_TSV = (
    REPORTS_DIR / "independent_neb_single_point_cases_v025.tsv"
)
FORCE_COMPONENTS_TSV = (
    REPORTS_DIR / "independent_neb_force_components_v025.tsv"
)
ENERGY_PROFILE_TSV = (
    REPORTS_DIR / "independent_neb_energy_profile_v025.tsv"
)
REPORT_MD = (
    REPORTS_DIR / "independent_neb_single_points_report_v025.md"
)
LABELS_CFG = (
    LABELS_DIR / "frozen_independent_neb_path_labels_v025.cfg"
)


# ======================================================================
# Locked scientific and execution parameters
# ======================================================================

EXPECTED_IMAGES = 9
NAT = 9

EXPECTED_SYMBOLS = [
    "O", "H", "C", "H", "C", "H", "C", "O", "H"
]
EXPECTED_QE_TYPES = [3, 2, 1, 2, 1, 2, 1, 3, 2]
EXPECTED_COMPOSITION = Counter({"C": 3, "H": 4, "O": 2})

SYMBOL_TO_MLIP_TYPE = {
    "C": 0,
    "H": 1,
    "O": 2,
}

RY_TO_EV = 13.605693122994
BOHR_TO_ANG = 0.529177210903
RY_BOHR_TO_EV_ANG = RY_TO_EV / BOHR_TO_ANG

MIN_PAIR_HARD_ANG = 0.65
MAX_SPAN_HARD_ANG = 5.50
ENDPOINT_QPT_MIN_ABS_ANG = 0.30
CENTRAL_QPT_MAX_ABS_ANG = 0.08
ENDPOINT_COORD_TOL_ANG = 2.0e-6

TOTAL_FORCE_ABS_TOL_RY_BOHR = 2.0e-5
TOTAL_FORCE_REL_TOL = 2.0e-3
NET_FORCE_WARNING_EV_ANG = 1.0e-5
NET_FORCE_HARD_EV_ANG = 1.0e-4
MAX_ATOMIC_FORCE_HARD_EV_ANG = 20.0

NEB_ENERGY_WARNING_TOL_EV = 2.0e-5
NEB_ENERGY_HARD_TOL_EV = 2.0e-4
NEB_BARRIER_HARD_TOL_EV = 2.0e-4

MPI_RANKS = 3
OMP_THREADS = 1
MPI_BINDING_ARGS = [
    "--map-by", "core",
    "--bind-to", "core",
]
PER_CASE_TIMEOUT_SECONDS = 12 * 3600
POLL_INTERVAL_SECONDS = 5.0

RUN_PW = True
RUN_NEB = False
RUN_MLP = False
RUN_LAMMPS = False
USE_AUDIT_FOR_TRAINING = False

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V025_PREFLIGHT_ONLY", "0") == "1"
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


class SinglePointInterrupted(BaseException):
    def __init__(
        self,
        reason: str,
        image_index: int | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.image_index = image_index
        self.elapsed_seconds = elapsed_seconds


# ======================================================================
# Generic utilities
# ======================================================================


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fatal(message: str) -> None:
    raise RuntimeError(message)


def log(message: str) -> None:
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)

    if RUN_ROOT.exists():
        RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with RUN_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def parse_number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


def norm3(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return value


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
    if not path.is_file():
        fatal(f"TSV file missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def resolve_success_attempt(
    pointer: Path,
    status_filename: str,
    expected_status: str,
) -> Path:
    if not pointer.is_file():
        fatal(f"success pointer missing: {pointer}")

    attempt = Path(pointer.read_text(encoding="utf-8").strip())
    if not attempt.is_dir():
        fatal(f"pointed attempt directory missing: {attempt}")

    status_path = attempt / status_filename
    if not status_path.is_file():
        fatal(f"status file missing: {status_path}")

    status = status_path.read_text(encoding="utf-8").strip()
    if status != expected_status:
        fatal(
            f"unexpected status in {status_path}: "
            f"{status!r}; expected {expected_status!r}"
        )

    return attempt


def cleanup_running_pointer_for_this_attempt() -> None:
    if not RUNNING_POINTER.is_file():
        return

    try:
        value = RUNNING_POINTER.read_text(encoding="utf-8").strip()
    except OSError:
        return

    if value == str(RUN_ROOT):
        RUNNING_POINTER.unlink(missing_ok=True)


# ======================================================================
# QE input parsing and rendering
# ======================================================================


def locate_namelist(
    lines: list[str],
    name: str,
) -> tuple[int, int]:
    wanted = f"&{name.upper()}"
    starts = [
        index
        for index, line in enumerate(lines)
        if line.strip().upper() == wanted
    ]

    if len(starts) != 1:
        fatal(
            f"expected exactly one {wanted} namelist, "
            f"found {len(starts)}"
        )

    start = starts[0]
    for index in range(start + 1, len(lines)):
        if lines[index].strip() == "/":
            return start, index

    fatal(f"unterminated {wanted} namelist")


def parse_namelist_assignments(
    lines: list[str],
    name: str,
) -> dict[str, str]:
    start, end = locate_namelist(lines, name)
    assignments: dict[str, str] = {}

    assignment_re = re.compile(
        r"^\s*([A-Za-z_][A-Za-z0-9_]*(?:\([^)]*\))?)"
        r"\s*=\s*(.*?)\s*,?\s*$"
    )

    for line in lines[start + 1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("!"):
            continue

        match = assignment_re.match(line)
        if not match:
            fatal(
                f"unsupported line in &{name.upper()}: {line!r}"
            )

        key = match.group(1).lower()
        value = match.group(2).strip()
        if key in assignments:
            fatal(f"duplicate {key} in &{name.upper()}")
        assignments[key] = value

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


def parse_card_unit(header: str, default: str = "alat") -> str:
    parenthesized = re.search(r"\(([^)]+)\)", header)
    if parenthesized:
        return parenthesized.group(1).strip()

    fields = header.split()
    if len(fields) >= 2:
        return fields[1].strip().strip("{}()")

    return default


def parse_bool_value(value: str) -> bool:
    normalized = unquote(value).strip().lower()
    if normalized in {".true.", "true", "t", "1"}:
        return True
    if normalized in {".false.", "false", "f", "0"}:
        return False
    fatal(f"invalid Fortran logical value: {value!r}")


def validate_canonical_pw_source(
    path: Path,
    cell_ang: list[list[float]],
) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    control = parse_namelist_assignments(lines, "CONTROL")
    system = parse_namelist_assignments(lines, "SYSTEM")
    electrons = parse_namelist_assignments(lines, "ELECTRONS")

    if "pseudo_dir" not in control:
        fatal("canonical PW input lacks pseudo_dir")
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
            fatal(f"canonical &SYSTEM lacks {key}")
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
            fatal(f"canonical &SYSTEM lacks {key}")
        actual = parse_number(system[key])
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-10):
            fatal(f"canonical {key}={actual}, expected {expected}")

    if unquote(system.get("occupations", "")).lower() != "fixed":
        fatal("canonical occupations is not fixed")
    if unquote(system.get("input_dft", "")).upper() != "PBE":
        fatal("canonical input_dft is not PBE")
    if not parse_bool_value(system.get("nosym", "")):
        fatal("canonical nosym is not true")
    if not parse_bool_value(system.get("noinv", "")):
        fatal("canonical noinv is not true")

    if "conv_thr" not in electrons:
        fatal("canonical &ELECTRONS lacks conv_thr")
    if not math.isclose(
        parse_number(electrons["conv_thr"]),
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

    for key in ["startingpot", "startingwfc"]:
        if key in electrons and unquote(electrons[key]).lower() == "file":
            fatal(f"canonical {key}='file' would violate independent from-scratch SP")

    species_starts = [
        index
        for index, line in enumerate(lines)
        if line.strip().upper() == "ATOMIC_SPECIES"
    ]
    if len(species_starts) != 1:
        fatal("canonical input must contain exactly one ATOMIC_SPECIES card")

    species_lines = lines[species_starts[0] + 1:species_starts[0] + 4]
    species_symbols: list[str] = []
    for line in species_lines:
        fields = line.split()
        if len(fields) < 3:
            fatal(f"invalid ATOMIC_SPECIES line: {line!r}")
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
        fatal(f"expected exactly one K_POINTS gamma card, found {len(k_points)}")

    expected_cell = [
        [16.0, 0.0, 0.0],
        [0.0, 16.0, 0.0],
        [0.0, 0.0, 16.0],
    ]
    for actual_vector, expected_vector in zip(cell_ang, expected_cell):
        for actual, expected in zip(actual_vector, expected_vector):
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-8):
                fatal(f"unexpected canonical cell vector: {actual_vector}")

    return {
        "pseudo_dir": pseudo_dir,
        "system": system,
        "electrons": electrons,
        "source_sha256": sha256(path),
    }


def render_control_block(
    pseudo_dir: str,
    prefix: str,
) -> list[str]:
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
            "canonical PW input must contain exactly one "
            f"ATOMIC_POSITIONS card; found {len(starts)}"
        )

    start = starts[0]
    end = start + 1 + NAT
    if end > len(lines):
        fatal("truncated ATOMIC_POSITIONS card")

    header = lines[start].strip()
    return start, end, header


def parse_cell_matrix_angstrom(
    lines: list[str],
) -> list[list[float]]:
    starts = [
        index
        for index, line in enumerate(lines)
        if line.strip().upper().startswith("CELL_PARAMETERS")
    ]

    if len(starts) != 1:
        fatal(
            "canonical PW input must contain exactly one "
            f"CELL_PARAMETERS card; found {len(starts)}"
        )

    start = starts[0]
    header = lines[start].lower()
    raw: list[list[float]] = []

    for offset in range(1, 4):
        fields = lines[start + offset].split()
        if len(fields) < 3:
            fatal("invalid CELL_PARAMETERS row")
        raw.append([
            parse_number(fields[0]),
            parse_number(fields[1]),
            parse_number(fields[2]),
        ])

    if "angstrom" in header:
        factor = 1.0
    elif "bohr" in header:
        factor = BOHR_TO_ANG
    elif "alat" in header:
        system = parse_namelist_assignments(lines, "SYSTEM")
        if "celldm(1)" not in system:
            fatal(
                "CELL_PARAMETERS alat requires celldm(1) "
                "in &SYSTEM"
            )
        factor = parse_number(system["celldm(1)"]) * BOHR_TO_ANG
    else:
        fatal(
            "CELL_PARAMETERS unit is not explicitly supported: "
            f"{lines[start]!r}"
        )

    return [
        [component * factor for component in vector]
        for vector in raw
    ]


def convert_positions_to_angstrom(
    coordinates: list[list[float]],
    unit: str,
    cell_ang: list[list[float]],
    alat_bohr: float | None,
) -> list[list[float]]:
    normalized = unit.strip().lower()

    if normalized in {"angstrom", "ang"}:
        return [list(vector) for vector in coordinates]

    if normalized in {"bohr", "au", "a.u."}:
        return [
            [component * BOHR_TO_ANG for component in vector]
            for vector in coordinates
        ]

    if normalized == "alat":
        if alat_bohr is None:
            fatal("ATOMIC_POSITIONS alat requires celldm(1)")
        factor = alat_bohr * BOHR_TO_ANG
        return [
            [component * factor for component in vector]
            for vector in coordinates
        ]

    if normalized == "crystal":
        converted: list[list[float]] = []
        for fractional in coordinates:
            converted.append([
                sum(
                    fractional[row] * cell_ang[row][axis]
                    for row in range(3)
                )
                for axis in range(3)
            ])
        return converted

    fatal(f"unsupported coordinate unit: {unit!r}")


def parse_atomic_positions_from_pw(
    path: Path,
    cell_ang: list[list[float]],
) -> tuple[list[str], list[list[float]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start, end, header = locate_atomic_positions_card(lines)

    unit = parse_card_unit(header, default="alat")

    system = parse_namelist_assignments(lines, "SYSTEM")
    alat_bohr = (
        parse_number(system["celldm(1)"])
        if "celldm(1)" in system
        else None
    )

    symbols: list[str] = []
    coordinates: list[list[float]] = []

    for line in lines[start + 1:end]:
        fields = line.split()
        if len(fields) < 4:
            fatal(f"invalid PW coordinate line: {line!r}")
        symbols.append(fields[0])
        coordinates.append([
            parse_number(fields[1]),
            parse_number(fields[2]),
            parse_number(fields[3]),
        ])

    if symbols != EXPECTED_SYMBOLS:
        fatal(f"PW atom order mismatch in {path}: {symbols}")

    return (
        symbols,
        convert_positions_to_angstrom(
            coordinates,
            unit,
            cell_ang,
            alat_bohr,
        ),
    )


def render_single_point_input(
    canonical_input: Path,
    coordinates_ang: list[list[float]],
    prefix: str,
) -> str:
    lines = canonical_input.read_text(encoding="utf-8").splitlines()

    control = parse_namelist_assignments(lines, "CONTROL")
    if "pseudo_dir" not in control:
        fatal("canonical input lacks pseudo_dir in &CONTROL")
    pseudo_dir = unquote(control["pseudo_dir"])

    control_start, control_end = locate_namelist(lines, "CONTROL")
    pos_start, pos_end, _ = locate_atomic_positions_card(lines)

    if control_start > pos_start:
        fatal("unexpected PW input order: CONTROL follows positions")

    new_lines: list[str] = []
    new_lines.extend(lines[:control_start])
    new_lines.extend(render_control_block(pseudo_dir, prefix))
    new_lines.extend(lines[control_end + 1:pos_start])
    new_lines.append("ATOMIC_POSITIONS (angstrom)")

    for symbol, coordinate in zip(EXPECTED_SYMBOLS, coordinates_ang):
        new_lines.append(
            f"{symbol:<2s} "
            f"{coordinate[0]: .14f} "
            f"{coordinate[1]: .14f} "
            f"{coordinate[2]: .14f}"
        )

    new_lines.extend(lines[pos_end:])
    text = "\n".join(new_lines).rstrip() + "\n"

    validate_rendered_single_point_input(
        text,
        prefix,
        coordinates_ang,
    )

    return text


def validate_rendered_single_point_input(
    text: str,
    expected_prefix: str,
    expected_coordinates_ang: list[list[float]],
) -> None:
    lines = text.splitlines()
    control = parse_namelist_assignments(lines, "CONTROL")

    expected = {
        "calculation": "scf",
        "restart_mode": "from_scratch",
        "prefix": expected_prefix,
        "outdir": "./tmp",
        "disk_io": "low",
        "verbosity": "high",
    }

    for key, wanted in expected.items():
        if key not in control:
            fatal(f"rendered CONTROL lacks {key}")
        actual = unquote(control[key]).lower()
        if actual != wanted.lower():
            fatal(
                f"rendered CONTROL {key}={actual!r}, "
                f"expected {wanted!r}"
            )

    for key, wanted in {
        "tprnfor": ".true.",
        "tstress": ".false.",
    }.items():
        if control.get(key, "").strip().lower() != wanted:
            fatal(f"rendered CONTROL has invalid {key}")

    if re.search(r"outdir\s*=\s*['\"]\./tmp['\"]\s*/", text):
        fatal("rendered input contains malformed outdir syntax")

    pos_start, pos_end, header = locate_atomic_positions_card(lines)
    if "angstrom" not in header.lower():
        fatal("rendered positions are not in angstrom")

    parsed: list[list[float]] = []
    symbols: list[str] = []
    for line in lines[pos_start + 1:pos_end]:
        fields = line.split()
        symbols.append(fields[0])
        parsed.append([
            parse_number(fields[1]),
            parse_number(fields[2]),
            parse_number(fields[3]),
        ])

    if symbols != EXPECTED_SYMBOLS:
        fatal("rendered atom order mismatch")

    maximum_difference = max(
        abs(parsed[atom][axis] - expected_coordinates_ang[atom][axis])
        for atom in range(NAT)
        for axis in range(3)
    )
    if maximum_difference > 1.0e-10:
        fatal(
            "rendered coordinates changed by "
            f"{maximum_difference:.3e} A"
        )


# ======================================================================
# CRD extraction and geometry validation
# ======================================================================


def parse_crd_images(
    crd_path: Path,
    cell_ang: list[list[float]],
    alat_bohr: float | None,
) -> list[dict[str, Any]]:
    if not crd_path.is_file():
        fatal(f"CRD file missing: {crd_path}")

    lines = crd_path.read_text(
        encoding="utf-8",
        errors="strict",
    ).splitlines()

    images: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        token = lines[index].strip().upper()
        if not token:
            index += 1
            continue

        if token not in {
            "FIRST_IMAGE",
            "INTERMEDIATE_IMAGE",
            "LAST_IMAGE",
        }:
            fatal(
                f"unexpected CRD line {index + 1}: "
                f"{lines[index]!r}"
            )

        role = token
        index += 1

        while index < len(lines) and not lines[index].strip():
            index += 1

        if index >= len(lines):
            fatal(f"missing ATOMIC_POSITIONS after {role}")

        header = lines[index].strip()
        if not header.upper().startswith("ATOMIC_POSITIONS"):
            fatal(
                f"expected ATOMIC_POSITIONS after {role}; "
                f"found {header!r}"
            )

        unit = parse_card_unit(header, default="alat")
        index += 1

        symbols: list[str] = []
        raw_coordinates: list[list[float]] = []

        for _ in range(NAT):
            if index >= len(lines):
                fatal(f"truncated CRD coordinates after {role}")

            fields = lines[index].split()
            if len(fields) < 4:
                fatal(
                    f"invalid CRD coordinate line {index + 1}: "
                    f"{lines[index]!r}"
                )

            symbols.append(fields[0])
            raw_coordinates.append([
                parse_number(fields[1]),
                parse_number(fields[2]),
                parse_number(fields[3]),
            ])
            index += 1

        if symbols != EXPECTED_SYMBOLS:
            fatal(f"CRD atom order mismatch in {role}: {symbols}")

        if Counter(symbols) != EXPECTED_COMPOSITION:
            fatal(f"CRD composition mismatch in {role}")

        coordinates_ang = convert_positions_to_angstrom(
            raw_coordinates,
            unit,
            cell_ang,
            alat_bohr,
        )

        images.append({
            "role": role,
            "source_unit": unit,
            "symbols": symbols,
            "coordinates_ang": coordinates_ang,
        })

    expected_roles = (
        ["FIRST_IMAGE"]
        + ["INTERMEDIATE_IMAGE"] * (EXPECTED_IMAGES - 2)
        + ["LAST_IMAGE"]
    )

    roles = [image["role"] for image in images]
    if roles != expected_roles:
        fatal(
            f"unexpected CRD image sequence: {roles}; "
            f"expected {expected_roles}"
        )

    return images


def geometry_metrics(
    coordinates: list[list[float]],
) -> dict[str, Any]:
    distances: dict[tuple[int, int], float] = {}

    for first in range(NAT):
        for second in range(first + 1, NAT):
            distance = norm3([
                coordinates[first][axis]
                - coordinates[second][axis]
                for axis in range(3)
            ])
            distances[(first + 1, second + 1)] = distance

    minimum_pair, minimum_pair_ang = min(
        distances.items(),
        key=lambda item: item[1],
    )

    r_o1_h = distances[(1, 2)]
    r_h_o2 = distances[(2, 8)]
    r_oo = distances[(1, 8)]

    return {
        "qpt_ang": r_o1_h - r_h_o2,
        "roo_ang": r_oo,
        "minimum_pair": minimum_pair,
        "minimum_pair_ang": minimum_pair_ang,
        "maximum_span_ang": max(distances.values()),
    }


def maximum_coordinate_difference(
    first: list[list[float]],
    second: list[list[float]],
) -> float:
    return max(
        abs(first[atom][axis] - second[atom][axis])
        for atom in range(NAT)
        for axis in range(3)
    )


def validate_final_images(
    images: list[dict[str, Any]],
    left_endpoint_ang: list[list[float]],
    right_endpoint_ang: list[list[float]],
    climbing_image: int,
) -> list[dict[str, Any]]:
    if len(images) != EXPECTED_IMAGES:
        fatal(
            f"CRD contains {len(images)} images, "
            f"expected {EXPECTED_IMAGES}"
        )

    rows: list[dict[str, Any]] = []
    qpts: list[float] = []

    for image_index, image in enumerate(images, start=1):
        metrics = geometry_metrics(image["coordinates_ang"])

        if metrics["minimum_pair_ang"] <= MIN_PAIR_HARD_ANG:
            fatal(
                f"image {image_index}: minimum pair "
                f"{metrics['minimum_pair_ang']:.8f} A"
            )

        if metrics["maximum_span_ang"] >= MAX_SPAN_HARD_ANG:
            fatal(
                f"image {image_index}: molecular span "
                f"{metrics['maximum_span_ang']:.8f} A"
            )

        qpts.append(metrics["qpt_ang"])
        rows.append({
            "image_index": image_index,
            "role": image["role"],
            "source_unit": image["source_unit"],
            "qpt_ang": metrics["qpt_ang"],
            "roo_ang": metrics["roo_ang"],
            "minimum_pair_atoms": (
                f"{metrics['minimum_pair'][0]}-"
                f"{metrics['minimum_pair'][1]}"
            ),
            "minimum_pair_ang": metrics["minimum_pair_ang"],
            "maximum_span_ang": metrics["maximum_span_ang"],
            "is_climbing_image": image_index == climbing_image,
        })

    for first, second in zip(qpts, qpts[1:]):
        if not second > first:
            fatal(
                "final CRD qPT is not strictly increasing: "
                f"{qpts}"
            )

    if qpts[0] >= -ENDPOINT_QPT_MIN_ABS_ANG:
        fatal(f"left endpoint qPT is invalid: {qpts[0]:.8f} A")

    if qpts[-1] <= ENDPOINT_QPT_MIN_ABS_ANG:
        fatal(f"right endpoint qPT is invalid: {qpts[-1]:.8f} A")

    central_index = (EXPECTED_IMAGES + 1) // 2
    if abs(qpts[central_index - 1]) > CENTRAL_QPT_MAX_ABS_ANG:
        fatal(
            f"central image qPT={qpts[central_index - 1]:.8f} A"
        )

    if climbing_image != central_index:
        fatal(
            f"v024 climbing image is {climbing_image}, "
            f"expected central image {central_index}"
        )

    left_difference = maximum_coordinate_difference(
        images[0]["coordinates_ang"],
        left_endpoint_ang,
    )
    right_difference = maximum_coordinate_difference(
        images[-1]["coordinates_ang"],
        right_endpoint_ang,
    )

    if left_difference > ENDPOINT_COORD_TOL_ANG:
        fatal(
            "left CRD endpoint differs from fixed v024 endpoint by "
            f"{left_difference:.3e} A"
        )

    if right_difference > ENDPOINT_COORD_TOL_ANG:
        fatal(
            "right CRD endpoint differs from fixed v024 endpoint by "
            f"{right_difference:.3e} A"
        )

    rows[0]["endpoint_coordinate_difference_ang"] = left_difference
    rows[-1]["endpoint_coordinate_difference_ang"] = right_difference
    for row in rows[1:-1]:
        row["endpoint_coordinate_difference_ang"] = ""

    return rows


# ======================================================================
# v024 result parsing
# ======================================================================


def parse_v024_neb_results(
    v024_attempt: Path,
) -> dict[str, Any]:
    final_table_path = (
        v024_attempt
        / "reports"
        / "final_neb_energy_error_table_v024.tsv"
    )
    rows = read_tsv(final_table_path)

    if len(rows) != EXPECTED_IMAGES:
        fatal(
            f"v024 final table contains {len(rows)} rows, "
            f"expected {EXPECTED_IMAGES}"
        )

    normalized_rows: list[dict[str, Any]] = []
    for expected_index, row in enumerate(rows, start=1):
        image_index = int(row["image_index"])
        if image_index != expected_index:
            fatal("v024 final table image order mismatch")
        normalized_rows.append({
            "image_index": image_index,
            "energy_ev": parse_number(row["energy_ev"]),
            "error_ev_ang": parse_number(row["error_ev_ang"]),
            "frozen": row["frozen"],
        })

    output_path = v024_attempt / "neb_v024.out"
    if not output_path.is_file():
        fatal(f"v024 NEB output missing: {output_path}")

    text = output_path.read_text(encoding="utf-8", errors="replace")
    if "JOB DONE." not in text:
        fatal("v024 NEB output lacks JOB DONE")
    if not re.search(
        r"neb:\s+convergence\s+achieved\s+in\s+\d+\s+iterations",
        text,
        flags=re.IGNORECASE,
    ):
        fatal("v024 NEB convergence marker missing")

    forward_matches = re.findall(
        rf"activation\s+energy\s*\(->\)\s*=\s*({NUMBER})\s*eV",
        text,
        flags=re.IGNORECASE,
    )
    backward_matches = re.findall(
        rf"activation\s+energy\s*\(<-\)\s*=\s*({NUMBER})\s*eV",
        text,
        flags=re.IGNORECASE,
    )
    climbing_matches = re.findall(
        r"climbing\s+image\s*=\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    )

    if not forward_matches or not backward_matches or not climbing_matches:
        fatal("unable to parse final v024 barrier information")

    return {
        "final_table_path": final_table_path,
        "final_table": normalized_rows,
        "forward_barrier_ev": parse_number(forward_matches[-1]),
        "backward_barrier_ev": parse_number(backward_matches[-1]),
        "climbing_image": int(climbing_matches[-1]),
        "neb_output": output_path,
    }


# ======================================================================
# MPI validation and PW execution
# ======================================================================


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
    for executable in [PW_X, MPIRUN]:
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

    resolved_linkages: list[tuple[str, Path]] = []
    wrong_linkages: list[str] = []

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
            wrong_linkages.append(
                f"{line}\n  resolved={linked_path}"
            )

    if wrong_linkages:
        fatal(
            "pw.x is linked to MPI libraries outside conda:\n"
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
        fatal("conda libmpi.so was not found in pw.x linkage")

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
            "3-rank MPI smoke test failed:\n"
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


def terminate_process_group(
    process: subprocess.Popen[Any],
) -> None:
    if process.poll() is not None:
        return

    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=20)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=20)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        pass


def run_single_point(
    case_dir: Path,
    image_index: int,
) -> tuple[int, float, list[str]]:
    input_path = case_dir / "pw_v025.in"
    output_path = case_dir / "pw_v025.out"
    error_path = case_dir / "pw_v025.err"

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
                    elapsed = time.monotonic() - start
                    return returncode, elapsed, command

                elapsed = time.monotonic() - start
                if elapsed > PER_CASE_TIMEOUT_SECONDS:
                    terminate_process_group(process)
                    fatal(
                        f"image {image_index}: pw.x timeout after "
                        f"{elapsed / 3600:.3f} h"
                    )

                time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt as exc:
            terminate_process_group(process)
            elapsed = time.monotonic() - start
            raise SinglePointInterrupted(
                reason="SIGINT",
                image_index=image_index,
                elapsed_seconds=elapsed,
            ) from exc


# ======================================================================
# Correct main-force-block parser inherited from v023 logic
# ======================================================================


def find_main_force_blocks(
    lines: list[str],
) -> list[dict[str, Any]]:
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

            forces.append({
                "atom_index": int(match.group(1)),
                "qe_type": int(match.group(2)),
                "force_ry_bohr": [
                    parse_number(match.group(3)),
                    parse_number(match.group(4)),
                    parse_number(match.group(5)),
                ],
                "source_line_number": index + 1,
                "source_line": candidate,
            })

            if len(forces) == NAT:
                end_index = index + 1
                break

        if len(forces) != NAT:
            fatal(
                f"force block at line {header_index + 1} contains "
                f"{len(forces)} atomic force lines"
            )

        atom_indices = [item["atom_index"] for item in forces]
        qe_types = [item["qe_type"] for item in forces]

        if atom_indices != list(range(1, NAT + 1)):
            fatal(
                f"force-block atom order mismatch: {atom_indices}"
            )

        if qe_types != EXPECTED_QE_TYPES:
            fatal(f"force-block QE type mismatch: {qe_types}")

        blocks.append({
            "header_line_index": header_index,
            "header_line_number": header_index + 1,
            "end_line_index": end_index,
            "forces": forces,
        })

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


def parse_pw_output(
    output_path: Path,
) -> dict[str, Any]:
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
        item["force_ry_bohr"]
        for item in block["forces"]
    ]
    forces_ev_ang = [
        [component * RY_BOHR_TO_EV_ANG for component in force]
        for force in forces_ry_bohr
    ]

    calculated_total_force = math.sqrt(sum(
        component * component
        for force in forces_ry_bohr
        for component in force
    ))

    total_force_difference = (
        calculated_total_force - reported_total_force
    )
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

    scf_iterations = len(re.findall(
        r"^\s*iteration\s+#",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    ))

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


# ======================================================================
# CFG writer
# ======================================================================


def write_labels_cfg(
    path: Path,
    records: list[dict[str, Any]],
    cell_ang: list[list[float]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write("BEGIN_CFG\n")
            handle.write(" Size\n")
            handle.write(f"    {NAT}\n")
            handle.write(" Supercell\n")

            for vector in cell_ang:
                handle.write(
                    "    "
                    f"{vector[0]:.16g} "
                    f"{vector[1]:.16g} "
                    f"{vector[2]:.16g}\n"
                )

            handle.write(
                " AtomData:  id type cartes_x cartes_y cartes_z "
                "fx fy fz\n"
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
                "audit_role": "frozen_independent_transition_path_audit",
                "audit_design_version": "v019",
                "neb_geometry_version": "v024",
                "single_point_version": "v025",
                "force_parser_version": "v023_main_block",
                "image_index": str(record["image_index"]),
                "image_role": record["role"].lower(),
                "is_climbing_image": str(
                    bool(record["is_climbing_image"])
                ).lower(),
                "q_pt_A": f"{record['qpt_ang']:.12f}",
                "r_oo_A": f"{record['roo_ang']:.12f}",
                "neb_energy_eV": f"{record['neb_energy_ev']:.12f}",
                "single_point_minus_neb_eV": (
                    f"{record['energy_difference_from_neb_ev']:.12e}"
                ),
                "max_atomic_force_eV_A": (
                    f"{record['maximum_atomic_force_ev_ang']:.12f}"
                ),
                "true_net_force_norm_eV_A": (
                    f"{record['net_force_norm_ev_ang']:.12e}"
                ),
                "audit_locked": "true",
                "training_eligible": "false",
                "dft_status": "PASS_INDEPENDENT_SINGLE_POINT",
            }

            for key in sorted(features):
                handle.write(f" Feature   {key} {features[key]}\n")

            handle.write("END_CFG\n\n")


# ======================================================================
# Result finalization
# ======================================================================


def write_partial_failure_summary(
    status: str,
    source_v024: Path,
    completed_records: list[dict[str, Any]],
    failed_image_index: int | None,
    reason: str,
) -> None:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(status + "\n", encoding="utf-8")
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    FAILED_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    summary = {
        "created_utc": utc_now(),
        "status": status,
        "run_root": RUN_ROOT,
        "source_v024": source_v024,
        "completed_images": [
            record["image_index"] for record in completed_records
        ],
        "failed_image_index": failed_image_index,
        "reason": reason,
    }

    SUMMARY_JSON.write_text(
        json.dumps(
            json_safe(summary),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def record_interruption(
    interruption: SinglePointInterrupted,
    source_v024: Path | None,
) -> None:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    status = "INTERRUPTED_DURING_NEB_SINGLE_POINTS_v025"
    STATUS_FILE.write_text(status + "\n", encoding="utf-8")
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    INTERRUPTED_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    summary = {
        "created_utc": utc_now(),
        "status": status,
        "run_root": RUN_ROOT,
        "source_v024": source_v024,
        "reason": interruption.reason,
        "image_index": interruption.image_index,
        "elapsed_seconds": interruption.elapsed_seconds,
    }

    SUMMARY_JSON.write_text(
        json.dumps(
            json_safe(summary),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    cleanup_running_pointer_for_this_attempt()


# ======================================================================
# Main
# ======================================================================


def main() -> None:
    if not RUN_PW or any([RUN_NEB, RUN_MLP, RUN_LAMMPS]):
        fatal("v025 execution guards were modified")

    if USE_AUDIT_FOR_TRAINING:
        fatal("audit structures must remain training-ineligible")

    source_v020 = resolve_success_attempt(
        V020_POINTER,
        "STATUS_v020.txt",
        "PASS_PRE_AUDIT_PROTOCOL_LOCK_NO_CALCULATIONS",
    )
    source_v023 = resolve_success_attempt(
        V023_POINTER,
        "STATUS_v023.txt",
        "PASS_BASIN_AUDIT_FORCE_BLOCK_REPARSE12_LABELLED",
    )
    source_v024 = resolve_success_attempt(
        V024_POINTER,
        "STATUS_v024.txt",
        "PASS_INDEPENDENT_NEB9_DFT_CONVERGED",
    )

    corrected_basin_cfg = (
        source_v023
        / "labels"
        / "frozen_basin_audit_labels_corrected_v023.cfg"
    )
    if not corrected_basin_cfg.is_file():
        fatal(f"v023 corrected basin CFG missing: {corrected_basin_cfg}")

    v024_results = parse_v024_neb_results(source_v024)
    climbing_image = v024_results["climbing_image"]

    crd_files = sorted(source_v024.glob("*.crd"))
    if len(crd_files) != 1:
        fatal(
            f"expected exactly one v024 .crd file, found {len(crd_files)}"
        )
    crd_path = crd_files[0]

    canonical_input = source_v024 / "pw_1.in"
    right_input = source_v024 / "pw_9.in"
    if not canonical_input.is_file() or not right_input.is_file():
        fatal("v024 generated endpoint PW inputs are missing")

    canonical_lines = canonical_input.read_text(
        encoding="utf-8"
    ).splitlines()
    cell_ang = parse_cell_matrix_angstrom(canonical_lines)
    canonical_validation = validate_canonical_pw_source(
        canonical_input,
        cell_ang,
    )
    system = parse_namelist_assignments(canonical_lines, "SYSTEM")
    alat_bohr = (
        parse_number(system["celldm(1)"])
        if "celldm(1)" in system
        else None
    )

    _, left_endpoint_ang = parse_atomic_positions_from_pw(
        canonical_input,
        cell_ang,
    )
    _, right_endpoint_ang = parse_atomic_positions_from_pw(
        right_input,
        cell_ang,
    )

    images = parse_crd_images(crd_path, cell_ang, alat_bohr)
    geometry_rows = validate_final_images(
        images,
        left_endpoint_ang,
        right_endpoint_ang,
        climbing_image,
    )

    mpi_info = validate_mpi_stack()

    command_template = [
        str(MPIRUN),
        "-np", str(MPI_RANKS),
        *MPI_BINDING_ARGS,
        str(PW_X),
        "-in", "pw_v025.in",
    ]

    if PREFLIGHT_ONLY:
        print("PASS_V025_PREFLIGHT_NO_DFT")
        print(f"source v024:    {source_v024}")
        print(f"CRD:            {crd_path}")
        print(f"images:         {len(images)}")
        print(f"climbing image: {climbing_image}")
        print(f"pw.x:           {PW_X}")
        print(f"mpirun:         {MPIRUN}")
        print(f"MPI ranks:      {MPI_RANKS}")
        print(f"OMP threads:    {OMP_THREADS}")
        print(f"binding:        {' '.join(MPI_BINDING_ARGS)}")
        print(f"command:        {' '.join(command_template)}")
        print("execution:      sequential, one image at a time")
        print("No attempt directory was created.")
        print("pw.x was NOT executed.")
        print("neb.x was NOT executed.")
        return

    if RUN_ROOT.exists():
        fatal(f"attempt already exists: {RUN_ROOT}")

    for directory in [
        RUN_ROOT,
        CASES_DIR,
        INPUTS_DIR,
        LABELS_DIR,
        REPORTS_DIR,
        PROVENANCE_DIR,
        EXTRACTED_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(
        "RUNNING_INDEPENDENT_NEB_SINGLE_POINTS_v025\n",
        encoding="utf-8",
    )
    RUNNING_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    shutil.copy2(crd_path, PROVENANCE_DIR / crd_path.name)
    shutil.copy2(
        v024_results["final_table_path"],
        PROVENANCE_DIR / "final_neb_energy_error_table_v024.tsv",
    )
    shutil.copy2(
        v024_results["neb_output"],
        PROVENANCE_DIR / "neb_v024.out",
    )
    shutil.copy2(
        canonical_input,
        PROVENANCE_DIR / "canonical_pw_1_v024.in",
    )
    shutil.copy2(
        right_input,
        PROVENANCE_DIR / "endpoint_pw_9_v024.in",
    )

    write_tsv(
        GEOMETRY_MANIFEST_TSV,
        geometry_rows,
        fieldnames=[
            "image_index",
            "role",
            "source_unit",
            "qpt_ang",
            "roo_ang",
            "minimum_pair_atoms",
            "minimum_pair_ang",
            "maximum_span_ang",
            "is_climbing_image",
            "endpoint_coordinate_difference_ang",
        ],
    )

    provenance = {
        "created_utc": utc_now(),
        "run_root": RUN_ROOT,
        "source_v020": source_v020,
        "source_v023": source_v023,
        "source_v024": source_v024,
        "source_crd": crd_path,
        "source_crd_sha256": sha256(crd_path),
        "source_v024_final_table": v024_results["final_table_path"],
        "source_v024_forward_barrier_ev": v024_results[
            "forward_barrier_ev"
        ],
        "source_v024_backward_barrier_ev": v024_results[
            "backward_barrier_ev"
        ],
        "source_v024_climbing_image": climbing_image,
        "v023_corrected_basin_cfg": corrected_basin_cfg,
        "v023_corrected_basin_cfg_sha256": sha256(corrected_basin_cfg),
        "execution": {
            "pw_x": PW_X,
            "mpirun": MPIRUN,
            "mpi_ranks": MPI_RANKS,
            "omp_threads": OMP_THREADS,
            "binding_args": MPI_BINDING_ARGS,
            "sequential_images": True,
            "restart_mode": "from_scratch",
            "unique_prefix_per_image": True,
            "timeout_per_case_seconds": PER_CASE_TIMEOUT_SECONDS,
            "neb_x_executed": False,
            "mlp_executed": False,
            "lammps_executed": False,
        },
        "canonical_pw_validation": canonical_validation,
        "mpi_validation": mpi_info,
        "force_parser": "v023 block-aware main complete-force block",
        "training_eligible": False,
    }

    (PROVENANCE_DIR / "provenance_v025.json").write_text(
        json.dumps(
            json_safe(provenance),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    log("Validated successful v024 independent 9-image CI-NEB.")
    log("Extracted and validated nine final geometries from the v024 CRD file.")
    log("Validated fixed endpoints, monotonic qPT, central climbing image, and atom order.")
    log("Validated conda Open MPI launcher, pw.x linkage, and 3-rank smoke test.")

    print()
    print("STEP 27 / INDEPENDENT NEB-PATH SINGLE POINTS v025")
    print()
    print(f"Run root:          {RUN_ROOT}")
    print(f"Source v024:       {source_v024}")
    print(f"CRD:               {crd_path}")
    print(f"pw.x:              {PW_X}")
    print(f"mpirun:            {MPIRUN}")
    print(f"Images:            {EXPECTED_IMAGES}")
    print(f"Climbing image:    {climbing_image}")
    print(f"MPI ranks/case:    {MPI_RANKS}")
    print(f"OMP threads/rank:  {OMP_THREADS}")
    print(f"Binding:           {' '.join(MPI_BINDING_ARGS)}")
    print("Execution order:   sequential 1 -> 9")
    print("restart_mode:      from_scratch for every image")
    print("Unique prefix:     YES")
    print("Force parser:      v023 main complete-force block")
    print("neb.x execution:   NO")
    print("MTP execution:     NO")
    print("LAMMPS execution:  NO")
    print()

    records: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []

    try:
        for image_index, (image, geometry_row, neb_row) in enumerate(
            zip(
                images,
                geometry_rows,
                v024_results["final_table"],
            ),
            start=1,
        ):
            case_name = f"audit_neb_image_{image_index:02d}_v025"
            case_dir = CASES_DIR / case_name
            case_dir.mkdir(parents=True, exist_ok=False)
            (case_dir / "tmp").mkdir(parents=True, exist_ok=False)

            prefix = f"audit_neb_img_{image_index:02d}_v025"
            input_text = render_single_point_input(
                canonical_input,
                image["coordinates_ang"],
                prefix,
            )

            case_input = case_dir / "pw_v025.in"
            case_input.write_text(input_text, encoding="utf-8")
            shutil.copy2(
                case_input,
                INPUTS_DIR / f"image_{image_index:02d}_v025.in",
            )

            metadata = {
                "image_index": image_index,
                "case_name": case_name,
                "role": image["role"],
                "source_crd": crd_path,
                "source_crd_sha256": sha256(crd_path),
                "source_unit": image["source_unit"],
                "qpt_ang": geometry_row["qpt_ang"],
                "roo_ang": geometry_row["roo_ang"],
                "is_climbing_image": geometry_row[
                    "is_climbing_image"
                ],
                "neb_energy_ev": neb_row["energy_ev"],
                "prefix": prefix,
                "restart_mode": "from_scratch",
                "training_eligible": False,
            }
            (case_dir / "metadata_v025.json").write_text(
                json.dumps(
                    json_safe(metadata),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )

            log(
                f"[{image_index:02d}/{EXPECTED_IMAGES:02d}] "
                f"Starting {case_name}; "
                f"qPT={geometry_row['qpt_ang']:.8f} A; "
                f"NEB_E={neb_row['energy_ev']:.9f} eV."
            )

            returncode, elapsed, command = run_single_point(
                case_dir,
                image_index,
            )

            if returncode != 0:
                status = (
                    f"FAIL_SINGLE_POINT_IMAGE_{image_index:02d}_v025"
                )
                write_partial_failure_summary(
                    status,
                    source_v024,
                    records,
                    image_index,
                    f"pw.x return code {returncode}",
                )
                fatal(
                    f"image {image_index}: pw.x failed with "
                    f"return code {returncode}"
                )

            parsed = parse_pw_output(case_dir / "pw_v025.out")
            energy_difference = (
                parsed["energy_ev"] - neb_row["energy_ev"]
            )

            if abs(energy_difference) > NEB_ENERGY_HARD_TOL_EV:
                status = (
                    f"FAIL_NEB_ENERGY_MISMATCH_IMAGE_"
                    f"{image_index:02d}_v025"
                )
                write_partial_failure_summary(
                    status,
                    source_v024,
                    records,
                    image_index,
                    (
                        "single-point minus NEB energy="
                        f"{energy_difference:.6e} eV"
                    ),
                )
                fatal(
                    f"image {image_index}: single-point energy differs "
                    f"from v024 NEB by {energy_difference:.6e} eV"
                )

            extracted_path = (
                EXTRACTED_DIR
                / f"image_{image_index:02d}_main_force_block_v025.txt"
            )
            extracted_path.write_text(
                parsed["force_block_text"],
                encoding="utf-8",
            )

            record = {
                "image_index": image_index,
                "case_name": case_name,
                "role": image["role"],
                "coordinates_ang": image["coordinates_ang"],
                "qpt_ang": geometry_row["qpt_ang"],
                "roo_ang": geometry_row["roo_ang"],
                "is_climbing_image": geometry_row[
                    "is_climbing_image"
                ],
                "neb_energy_ev": neb_row["energy_ev"],
                "neb_error_ev_ang": neb_row["error_ev_ang"],
                "energy_difference_from_neb_ev": energy_difference,
                "elapsed_seconds": elapsed,
                "command": command,
                **parsed,
            }
            records.append(record)

            case_rows.append({
                "image_index": image_index,
                "case_name": case_name,
                "role": image["role"],
                "is_climbing_image": geometry_row[
                    "is_climbing_image"
                ],
                "qpt_ang": geometry_row["qpt_ang"],
                "roo_ang": geometry_row["roo_ang"],
                "neb_energy_ev": neb_row["energy_ev"],
                "single_point_energy_ev": parsed["energy_ev"],
                "single_point_minus_neb_ev": energy_difference,
                "energy_warning": (
                    abs(energy_difference)
                    > NEB_ENERGY_WARNING_TOL_EV
                ),
                "neb_error_ev_ang": neb_row["error_ev_ang"],
                "maximum_atomic_force_ev_ang": parsed[
                    "maximum_atomic_force_ev_ang"
                ],
                "true_net_force_x_ev_ang": parsed[
                    "net_force_vector_ev_ang"
                ][0],
                "true_net_force_y_ev_ang": parsed[
                    "net_force_vector_ev_ang"
                ][1],
                "true_net_force_z_ev_ang": parsed[
                    "net_force_vector_ev_ang"
                ][2],
                "true_net_force_norm_ev_ang": parsed[
                    "net_force_norm_ev_ang"
                ],
                "net_force_warning": parsed["net_force_warning"],
                "reported_total_force_ry_bohr": parsed[
                    "reported_total_force_ry_bohr"
                ],
                "calculated_total_force_ry_bohr": parsed[
                    "calculated_total_force_ry_bohr"
                ],
                "total_force_difference_ry_bohr": parsed[
                    "total_force_difference_ry_bohr"
                ],
                "main_force_block_count": parsed[
                    "main_force_block_count"
                ],
                "selected_force_block_header_line": parsed[
                    "selected_force_block_header_line"
                ],
                "force_line_count": len(parsed["forces_ev_ang"]),
                "scf_iterations": parsed["scf_iterations"],
                "elapsed_seconds": elapsed,
                "returncode": returncode,
                "output_sha256": parsed["output_sha256"],
                "status": "PASS",
            })

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
                component_rows.append({
                    "image_index": image_index,
                    "case_name": case_name,
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
                })

            log(
                f"[{image_index:02d}/{EXPECTED_IMAGES:02d}] PASS: "
                f"E={parsed['energy_ev']:.9f} eV; "
                f"dE_NEB={energy_difference:.3e} eV; "
                f"maxF={parsed['maximum_atomic_force_ev_ang']:.6f} eV/A; "
                f"|sumF|={parsed['net_force_norm_ev_ang']:.3e} eV/A; "
                f"time={elapsed / 60:.2f} min."
            )

    except SinglePointInterrupted:
        raise
    except Exception:
        cleanup_running_pointer_for_this_attempt()
        raise

    if len(records) != EXPECTED_IMAGES:
        fatal(
            f"completed {len(records)} images, expected {EXPECTED_IMAGES}"
        )

    single_point_energies = [
        record["energy_ev"] for record in records
    ]
    maximum_energy = max(single_point_energies)
    maximum_image = (
        single_point_energies.index(maximum_energy) + 1
    )

    if maximum_image != climbing_image:
        fatal(
            f"single-point maximum is image {maximum_image}, "
            f"v024 climbing image is {climbing_image}"
        )

    forward_barrier_sp = maximum_energy - single_point_energies[0]
    backward_barrier_sp = maximum_energy - single_point_energies[-1]

    forward_barrier_difference = (
        forward_barrier_sp - v024_results["forward_barrier_ev"]
    )
    backward_barrier_difference = (
        backward_barrier_sp - v024_results["backward_barrier_ev"]
    )

    if abs(forward_barrier_difference) > NEB_BARRIER_HARD_TOL_EV:
        fatal(
            "single-point forward barrier differs from v024 NEB by "
            f"{forward_barrier_difference:.6e} eV"
        )

    if abs(backward_barrier_difference) > NEB_BARRIER_HARD_TOL_EV:
        fatal(
            "single-point backward barrier differs from v024 NEB by "
            f"{backward_barrier_difference:.6e} eV"
        )

    write_labels_cfg(LABELS_CFG, records, cell_ang)

    if LABELS_CFG.read_text(encoding="utf-8").count("BEGIN_CFG") != EXPECTED_IMAGES:
        fatal("v025 CFG block count mismatch")

    write_tsv(
        CASE_REPORT_TSV,
        case_rows,
        fieldnames=[
            "image_index",
            "case_name",
            "role",
            "is_climbing_image",
            "qpt_ang",
            "roo_ang",
            "neb_energy_ev",
            "single_point_energy_ev",
            "single_point_minus_neb_ev",
            "energy_warning",
            "neb_error_ev_ang",
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
        ],
    )

    write_tsv(
        FORCE_COMPONENTS_TSV,
        component_rows,
        fieldnames=[
            "image_index",
            "case_name",
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
        ],
    )

    profile_rows: list[dict[str, Any]] = []
    reference_energy = single_point_energies[0]
    for record in records:
        profile_rows.append({
            "image_index": record["image_index"],
            "qpt_ang": record["qpt_ang"],
            "is_climbing_image": record["is_climbing_image"],
            "neb_energy_ev": record["neb_energy_ev"],
            "single_point_energy_ev": record["energy_ev"],
            "single_point_relative_to_left_ev": (
                record["energy_ev"] - reference_energy
            ),
            "single_point_minus_neb_ev": record[
                "energy_difference_from_neb_ev"
            ],
            "maximum_atomic_force_ev_ang": record[
                "maximum_atomic_force_ev_ang"
            ],
        })

    write_tsv(
        ENERGY_PROFILE_TSV,
        profile_rows,
        fieldnames=[
            "image_index",
            "qpt_ang",
            "is_climbing_image",
            "neb_energy_ev",
            "single_point_energy_ev",
            "single_point_relative_to_left_ev",
            "single_point_minus_neb_ev",
            "maximum_atomic_force_ev_ang",
        ],
    )

    maximum_energy_difference = max(
        abs(record["energy_difference_from_neb_ev"])
        for record in records
    )
    maximum_atomic_force = max(
        record["maximum_atomic_force_ev_ang"]
        for record in records
    )
    maximum_net_force = max(
        record["net_force_norm_ev_ang"]
        for record in records
    )
    maximum_total_force_mismatch = max(
        abs(record["total_force_difference_ry_bohr"])
        for record in records
    )
    energy_warning_count = sum(
        abs(record["energy_difference_from_neb_ev"])
        > NEB_ENERGY_WARNING_TOL_EV
        for record in records
    )
    net_force_warning_count = sum(
        record["net_force_warning"] for record in records
    )
    total_elapsed = sum(record["elapsed_seconds"] for record in records)

    status = "PASS_INDEPENDENT_NEB9_SINGLE_POINTS_LABELLED"

    report_lines = [
        "# Independent NEB-path single-point report v025",
        "",
        f"Created UTC: {utc_now()}",
        "",
        "## Status",
        "",
        f"- {status}",
        f"- Source v024: `{source_v024}`",
        f"- Source CRD: `{crd_path}`",
        f"- Images recomputed independently: {EXPECTED_IMAGES}/9",
        "- Every calculation used restart_mode='from_scratch'",
        "- Images were run sequentially with unique prefixes and empty outdirs",
        "- Direct pw.x execution: yes",
        "- neb.x execution: no",
        "- MTP execution: no",
        "- LAMMPS execution: no",
        "",
        "## Force parsing",
        "",
        "For each output, v025 reads exactly the nine complete atomic",
        "forces immediately following the final `Forces acting on atoms`",
        "header. Subsequent non-local and other contribution blocks are",
        "excluded. The resulting norm is checked against QE `Total force`,",
        "and the true vector residual `|sum_i F_i|` is checked separately.",
        "",
        "## Energetic consistency",
        "",
        f"- v024 forward barrier: {v024_results['forward_barrier_ev']:.12f} eV",
        f"- v025 forward barrier: {forward_barrier_sp:.12f} eV",
        f"- Forward difference: {forward_barrier_difference:.12e} eV",
        f"- v024 backward barrier: {v024_results['backward_barrier_ev']:.12f} eV",
        f"- v025 backward barrier: {backward_barrier_sp:.12f} eV",
        f"- Backward difference: {backward_barrier_difference:.12e} eV",
        f"- Maximum per-image |single-point minus NEB|: {maximum_energy_difference:.12e} eV",
        f"- Energy warnings above {NEB_ENERGY_WARNING_TOL_EV:.1e} eV: {energy_warning_count}",
        f"- Climbing/maximum-energy image: {climbing_image}",
        "",
        "## Force statistics",
        "",
        f"- Maximum atomic force: {maximum_atomic_force:.12f} eV/Angstrom",
        f"- Maximum true |sum_i F_i|: {maximum_net_force:.12e} eV/Angstrom",
        f"- Net-force warnings: {net_force_warning_count}",
        f"- Maximum QE Total-force norm mismatch: {maximum_total_force_mismatch:.12e} Ry/bohr",
        "",
        "## Authoritative outputs",
        "",
        f"- Frozen path labels: `{LABELS_CFG}`",
        f"- Case report: `{CASE_REPORT_TSV}`",
        f"- Force components: `{FORCE_COMPONENTS_TSV}`",
        f"- Energy profile: `{ENERGY_PROFILE_TSV}`",
        f"- Geometry manifest: `{GEOMETRY_MANIFEST_TSV}`",
        "",
        "The v025 CFG is audit-only and must not be used for training.",
    ]

    REPORT_MD.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    summary = {
        "created_utc": utc_now(),
        "status": status,
        "run_root": RUN_ROOT,
        "source_v020": source_v020,
        "source_v023": source_v023,
        "source_v024": source_v024,
        "source_crd": crd_path,
        "counts": {
            "images": EXPECTED_IMAGES,
            "force_vectors": EXPECTED_IMAGES * NAT,
            "force_components": EXPECTED_IMAGES * NAT * 3,
            "cfg_blocks": EXPECTED_IMAGES,
        },
        "execution": {
            "pw_x": PW_X,
            "mpirun": MPIRUN,
            "mpi_ranks_per_case": MPI_RANKS,
            "omp_threads_per_rank": OMP_THREADS,
            "binding_args": MPI_BINDING_ARGS,
            "sequential": True,
            "restart_mode": "from_scratch",
            "elapsed_seconds_sum": total_elapsed,
            "neb_x_executed": False,
            "mlp_executed": False,
            "lammps_executed": False,
        },
        "energetics": {
            "climbing_image": climbing_image,
            "v024_forward_barrier_ev": v024_results[
                "forward_barrier_ev"
            ],
            "v025_forward_barrier_ev": forward_barrier_sp,
            "forward_barrier_difference_ev": forward_barrier_difference,
            "v024_backward_barrier_ev": v024_results[
                "backward_barrier_ev"
            ],
            "v025_backward_barrier_ev": backward_barrier_sp,
            "backward_barrier_difference_ev": backward_barrier_difference,
            "maximum_per_image_energy_difference_ev": (
                maximum_energy_difference
            ),
            "energy_warning_count": energy_warning_count,
        },
        "forces": {
            "maximum_atomic_force_ev_ang": maximum_atomic_force,
            "maximum_true_net_force_norm_ev_ang": maximum_net_force,
            "net_force_warning_count": net_force_warning_count,
            "maximum_total_force_norm_mismatch_ry_bohr": (
                maximum_total_force_mismatch
            ),
        },
        "outputs": {
            "labels_cfg": LABELS_CFG,
            "case_report": CASE_REPORT_TSV,
            "force_components": FORCE_COMPONENTS_TSV,
            "energy_profile": ENERGY_PROFILE_TSV,
            "geometry_manifest": GEOMETRY_MANIFEST_TSV,
            "report": REPORT_MD,
        },
    }

    SUMMARY_JSON.write_text(
        json.dumps(
            json_safe(summary),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    checksum_paths = sorted(
        [
            path
            for path in RUN_ROOT.rglob("*")
            if path.is_file() and path != CHECKSUMS_TSV
        ],
        key=lambda path: str(path),
    )

    with CHECKSUMS_TSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            fieldnames=["path", "sha256"],
        )
        writer.writeheader()

        for path in checksum_paths:
            writer.writerow({
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
            })

    STATUS_FILE.write_text(status + "\n", encoding="utf-8")
    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
    cleanup_running_pointer_for_this_attempt()

    print()
    print(
        "PASS_INDEPENDENT_NEB9_SINGLE_POINTS_LABELLED: "
        "STEP 27 v025 COMPLETED"
    )
    print()
    print(f"Run root:                  {RUN_ROOT}")
    print(f"Independent cases:         {EXPECTED_IMAGES}/9")
    print(f"Climbing image:            {climbing_image}")
    print(f"v025 forward barrier:      {forward_barrier_sp:.8f} eV")
    print(f"v025 backward barrier:     {backward_barrier_sp:.8f} eV")
    print(
        f"Maximum |SP-NEB energy|:   "
        f"{maximum_energy_difference:.3e} eV"
    )
    print(
        f"Maximum atomic force:      "
        f"{maximum_atomic_force:.8f} eV/A"
    )
    print(
        f"Maximum true |sum F|:      "
        f"{maximum_net_force:.3e} eV/A"
    )
    print(f"Total case wall time:      {total_elapsed / 3600:.3f} h")
    print()
    print(f"Frozen labels CFG:         {LABELS_CFG}")
    print(f"Case report:               {CASE_REPORT_TSV}")
    print(f"Energy profile:            {ENERGY_PROFILE_TSV}")
    print(f"Force components:          {FORCE_COMPONENTS_TSV}")
    print(f"Report:                    {REPORT_MD}")
    print()
    print("pw.x WAS executed independently for 9 images.")
    print("neb.x was NOT executed.")
    print("mlp was NOT executed.")
    print("LAMMPS was NOT executed.")
    print()
    print("The frozen independent DFT audit set is now complete:")
    print("12 basin structures from v023 + 9 transition-path structures from v025.")


if __name__ == "__main__":
    source_for_interruption: Path | None = None

    try:
        if V024_POINTER.is_file():
            candidate = V024_POINTER.read_text(encoding="utf-8").strip()
            if candidate:
                source_for_interruption = Path(candidate)

        main()

    except SinglePointInterrupted as interruption:
        record_interruption(interruption, source_for_interruption)
        print(
            "\nINTERRUPTED_DURING_NEB_SINGLE_POINTS_v025: "
            f"{interruption.reason}; "
            f"image={interruption.image_index}",
            file=sys.stderr,
        )
        raise SystemExit(130)

    except Exception as error:
        try:
            if RUN_ROOT.exists():
                current_status = (
                    STATUS_FILE.read_text(encoding="utf-8").strip()
                    if STATUS_FILE.is_file()
                    else ""
                )

                if not current_status or current_status.startswith("RUNNING_"):
                    STATUS_FILE.write_text(
                        "FAIL_RUNTIME_v025\n",
                        encoding="utf-8",
                    )
                    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
                    FAILED_POINTER.write_text(
                        str(RUN_ROOT) + "\n",
                        encoding="utf-8",
                    )

            cleanup_running_pointer_for_this_attempt()
        except Exception:
            pass

        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

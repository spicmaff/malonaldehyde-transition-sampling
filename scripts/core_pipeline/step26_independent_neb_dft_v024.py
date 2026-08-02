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


ROOT = Path.home() / "malonaldehyde_mtp_al"

ENV_PREFIX = (
    Path.home()
    / "miniforge3"
    / "envs"
    / "malon_mtp"
)

NEB_X = ENV_PREFIX / "bin" / "neb.x"
MPIRUN = ENV_PREFIX / "bin" / "mpirun"
CONDA_LIB = ENV_PREFIX / "lib"

V019_POINTER = (
    ROOT
    / "09_strict_comparison"
    / "versions"
    / "v019_independent_audit_design"
    / "CURRENT_INDEPENDENT_AUDIT_DESIGN.txt"
)

V020_POINTER = (
    ROOT
    / "09_strict_comparison"
    / "versions"
    / "v020_pre_audit_protocol_lock"
    / "CURRENT_PRE_AUDIT_PROTOCOL_LOCK.txt"
)

V022_POINTER = (
    ROOT
    / "09_strict_comparison"
    / "versions"
    / "v022_basin_audit_force_restart_recovery"
    / "CURRENT_BASIN_AUDIT_FORCE_RECOVERY.txt"
)

V023_POINTER = (
    ROOT
    / "09_strict_comparison"
    / "versions"
    / "v023_basin_audit_force_block_reparse"
    / "CURRENT_BASIN_AUDIT_FORCE_BLOCK_REPARSE.txt"
)

VERSION_ROOT = (
    ROOT
    / "09_strict_comparison"
    / "versions"
    / "v024_independent_neb_dft"
)

CURRENT_POINTER = (
    VERSION_ROOT
    / "CURRENT_INDEPENDENT_NEB_DFT.txt"
)

RUNNING_POINTER = (
    VERSION_ROOT
    / "CURRENT_RUNNING_INDEPENDENT_NEB_DFT.txt"
)

FAILED_POINTER = (
    VERSION_ROOT
    / "LAST_FAILED_INDEPENDENT_NEB_DFT.txt"
)

INTERRUPTED_POINTER = (
    VERSION_ROOT
    / "LAST_INTERRUPTED_INDEPENDENT_NEB_DFT.txt"
)

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"

INPUT_DIR = RUN_ROOT / "input"
REPORT_DIR = RUN_ROOT / "reports"
PROVENANCE_DIR = RUN_ROOT / "provenance"

NEB_INPUT = INPUT_DIR / "independent_audit_neb_9img_v024.in"
NEB_OUTPUT = RUN_ROOT / "neb_v024.out"
NEB_ERROR = RUN_ROOT / "neb_v024.err"
STATUS_FILE = RUN_ROOT / "STATUS_v024.txt"
RUN_LOG = RUN_ROOT / "run_log_v024.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v024.json"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v024.tsv"
IMAGE_MANIFEST = REPORT_DIR / "initial_neb_images_v024.tsv"
FINAL_TABLE_TSV = REPORT_DIR / "final_neb_energy_error_table_v024.tsv"
REPORT_MD = REPORT_DIR / "independent_neb_dft_report_v024.md"

EXPECTED_IMAGES = 9
NAT = 9

EXPECTED_SYMBOLS = [
    "O", "H", "C", "H", "C", "H", "C", "O", "H"
]
EXPECTED_COMPOSITION = Counter({"C": 3, "H": 4, "O": 2})

MIN_PAIR_ANG = 0.65
MAX_SPAN_ANG = 5.50
CENTRAL_QPT_MAX_ANG = 0.08
IMAGE_MANIFEST_QPT_TOL_ANG = 2.0e-6

NEB_TIMEOUT_SECONDS = 72 * 3600
# Use all three physical cores inside one PW calculation at a time.
# Three image groups would run three independent high-cutoff PW instances
# concurrently and exceed the available WSL memory.
MPI_RANKS = 3
IMAGE_GROUPS = 1
OMP_THREADS = 1
RANKS_PER_IMAGE_GROUP = MPI_RANKS // IMAGE_GROUPS
MPI_BINDING_ARGS = [
    "--map-by", "core",
    "--bind-to", "core",
]

RUN_NEB = True
RUN_PW_DIRECT = False
RUN_MLP = False
RUN_LAMMPS = False
USE_OLD_NEB_COORDINATES = False
USE_AUDIT_FOR_TRAINING = False
PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V024_PREFLIGHT_ONLY", "0") == "1"
)

NUMBER = (
    r"[-+]?"
    r"(?:\d+(?:\.\d*)?|\.\d+)"
    r"(?:[EeDd][-+]?\d+)?"
)

PATH_ALLOWED_KEYS = {
    "string_method",
    "restart_mode",
    "nstep_path",
    "num_of_images",
    "opt_scheme",
    "ci_scheme",
    "first_last_opt",
    "minimum_image",
    "temp_req",
    "ds",
    "k_max",
    "k_min",
    "path_thr",
    "use_masses",
    "use_freezing",
    "lfcp",
    "fcp_mu",
    "fcp_thr",
    "fcp_scheme",
}

PATH_OUTPUT_ORDER = [
    "string_method",
    "restart_mode",
    "nstep_path",
    "num_of_images",
    "opt_scheme",
    "ci_scheme",
    "first_last_opt",
    "minimum_image",
    "temp_req",
    "ds",
    "k_max",
    "k_min",
    "path_thr",
    "use_masses",
    "use_freezing",
    "lfcp",
    "fcp_mu",
    "fcp_thr",
    "fcp_scheme",
]


class NebInterrupted(BaseException):
    def __init__(self, reason: str, elapsed_seconds: float | None = None):
        super().__init__(reason)
        self.reason = reason
        self.elapsed_seconds = elapsed_seconds




def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fatal(message: str) -> None:
    raise RuntimeError(message)


def log(message: str) -> None:
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def parse_number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


def parse_int(text: str) -> int:
    value = parse_number(unquote(text))
    rounded = int(round(value))
    if not math.isclose(value, rounded, rel_tol=0.0, abs_tol=1.0e-10):
        fatal(f"expected integer value, got {text!r}")
    return rounded


def parse_bool(text: str) -> bool:
    value = unquote(text).strip().lower()
    if value in {".true.", "true", "t"}:
        return True
    if value in {".false.", "false", "f"}:
        return False
    fatal(f"invalid logical value: {text!r}")


def unquote(text: str) -> str:
    value = text.strip()
    if (
        len(value) >= 2
        and value[0] in {"'", '"'}
        and value[-1] == value[0]
    ):
        return value[1:-1]
    return value


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
        return {str(key): json_safe(item) for key, item in value.items()}
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
        fatal(f"TSV missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def resolve_attempt(
    pointer: Path,
    status_filename: str,
    expected_status: str,
) -> Path:
    if not pointer.is_file():
        fatal(f"pointer missing: {pointer}")
    attempt = Path(pointer.read_text(encoding="utf-8").strip())
    if not attempt.is_dir():
        fatal(f"attempt directory missing: {attempt}")
    status_path = attempt / status_filename
    if not status_path.is_file():
        fatal(f"status file missing: {status_path}")
    status = status_path.read_text(encoding="utf-8").strip()
    if status != expected_status:
        fatal(
            f"unexpected status for {attempt}: {status!r}; "
            f"expected {expected_status!r}"
        )
    return attempt


def strip_inline_comment(line: str) -> str:
    quote: str | None = None
    result: list[str] = []
    for char in line:
        if quote is None and char in {"'", '"'}:
            quote = char
            result.append(char)
            continue
        if quote is not None and char == quote:
            quote = None
            result.append(char)
            continue
        if quote is None and char == "!":
            break
        result.append(char)
    return "".join(result)


def find_exact_line(lines: list[str], token: str, start: int = 0) -> int:
    target = token.upper()
    matches = [
        index
        for index in range(start, len(lines))
        if lines[index].strip().upper() == target
    ]
    if len(matches) != 1:
        fatal(f"expected exactly one {token}, found {len(matches)}")
    return matches[0]


def extract_namelist_lines(
    lines: list[str],
    name: str,
    search_start: int = 0,
    search_end: int | None = None,
) -> tuple[list[str], int, int]:
    if search_end is None:
        search_end = len(lines)
    start_re = re.compile(rf"^\s*&{re.escape(name)}\s*$", re.IGNORECASE)
    starts = [
        index
        for index in range(search_start, search_end)
        if start_re.match(lines[index])
    ]
    if len(starts) != 1:
        fatal(f"expected exactly one &{name}, found {len(starts)}")
    start = starts[0]
    for index in range(start + 1, search_end):
        if re.match(r"^\s*/\s*$", lines[index]):
            return lines[start:index + 1], start, index
    fatal(f"closing slash for &{name} not found")


def parse_namelist_assignments(block_lines: list[str]) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for raw_line in block_lines[1:-1]:
        line = strip_inline_comment(raw_line).strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*?)\s*,?\s*$", line)
        if not match:
            fatal(f"unsupported namelist line: {raw_line!r}")
        key = match.group(1).lower()
        value = match.group(2).strip()
        if key in assignments:
            fatal(f"duplicate namelist key: {key}")
        if not value:
            fatal(f"empty namelist value for {key}")
        assignments[key] = value
    return assignments


def extract_path_spec(source_text: str) -> dict[str, Any]:
    lines = source_text.splitlines()
    begin_path = find_exact_line(lines, "BEGIN_PATH_INPUT")
    end_path = find_exact_line(lines, "END_PATH_INPUT")
    if end_path <= begin_path:
        fatal("END_PATH_INPUT precedes BEGIN_PATH_INPUT")
    block, _, _ = extract_namelist_lines(
        lines,
        "PATH",
        search_start=begin_path + 1,
        search_end=end_path,
    )
    assignments = parse_namelist_assignments(block)
    unknown = sorted(set(assignments) - PATH_ALLOWED_KEYS)
    if unknown:
        fatal(f"unsupported v019 PATH keys: {unknown}")

    required = {
        "string_method",
        "restart_mode",
        "nstep_path",
        "num_of_images",
        "opt_scheme",
        "ci_scheme",
        "first_last_opt",
        "path_thr",
    }
    missing = sorted(required - set(assignments))
    if missing:
        fatal(f"v019 PATH missing keys: {missing}")

    if unquote(assignments["string_method"]).lower() != "neb":
        fatal("v019 string_method is not 'neb'")
    if parse_int(assignments["num_of_images"]) != EXPECTED_IMAGES:
        fatal("v019 num_of_images is not 9")
    if parse_int(assignments["nstep_path"]) <= 0:
        fatal("v019 nstep_path must be positive")
    if unquote(assignments["ci_scheme"]).lower() != "auto":
        fatal(
            "strict audit requires CI_scheme='auto'; "
            f"found {assignments['ci_scheme']!r}"
        )
    if parse_bool(assignments["first_last_opt"]):
        fatal("strict audit requires fixed endpoints")

    path_thr = parse_number(unquote(assignments["path_thr"]))
    if not (0.0 < path_thr <= 0.05):
        fatal(f"unexpected path_thr={path_thr}")

    clean = dict(assignments)
    clean["restart_mode"] = "'from_scratch'"
    clean["num_of_images"] = str(EXPECTED_IMAGES)

    return {
        "assignments": clean,
        "path_thr_ev_ang": path_thr,
        "nstep_path": parse_int(clean["nstep_path"]),
        "opt_scheme": unquote(clean["opt_scheme"]),
        "ci_scheme": unquote(clean["ci_scheme"]),
    }


def render_path_block(assignments: dict[str, str]) -> list[str]:
    lines = ["&PATH"]
    for key in PATH_OUTPUT_ORDER:
        if key in assignments:
            lines.append(f"  {key} = {assignments[key]},")
    lines.append("/")
    return lines


def parse_positions_from_neb(source_text: str) -> list[dict[str, Any]]:
    lines = source_text.splitlines()
    begin = find_exact_line(lines, "BEGIN_POSITIONS")
    end = find_exact_line(lines, "END_POSITIONS")
    if end <= begin:
        fatal("END_POSITIONS precedes BEGIN_POSITIONS")

    images: list[dict[str, Any]] = []
    index = begin + 1
    while index < end:
        token = lines[index].strip().upper()
        if not token:
            index += 1
            continue
        if token not in {"FIRST_IMAGE", "INTERMEDIATE_IMAGE", "LAST_IMAGE"}:
            fatal(f"unexpected line in BEGIN_POSITIONS: {lines[index]!r}")
        role = token
        index += 1
        while index < end and not lines[index].strip():
            index += 1
        if index >= end:
            fatal(f"missing ATOMIC_POSITIONS after {role}")
        header = lines[index].strip()
        if not header.upper().startswith("ATOMIC_POSITIONS"):
            fatal(f"expected ATOMIC_POSITIONS after {role}, got {header!r}")
        if "angstrom" not in header.lower():
            fatal(f"{role} positions are not in angstrom")
        index += 1

        symbols: list[str] = []
        coordinates: list[list[float]] = []
        for _ in range(NAT):
            if index >= end:
                fatal(f"truncated coordinates for {role}")
            fields = lines[index].split()
            if len(fields) < 4:
                fatal(f"invalid coordinate line: {lines[index]!r}")
            symbol = fields[0]
            try:
                xyz = [parse_number(fields[1]), parse_number(fields[2]), parse_number(fields[3])]
            except ValueError as exc:
                fatal(f"invalid coordinate line: {lines[index]!r}: {exc}")
            symbols.append(symbol)
            coordinates.append(xyz)
            index += 1

        if symbols != EXPECTED_SYMBOLS:
            fatal(f"atom order mismatch in {role}: {symbols}")
        if Counter(symbols) != EXPECTED_COMPOSITION:
            fatal(f"composition mismatch in {role}")
        images.append({
            "role": role,
            "symbols": symbols,
            "coordinates": coordinates,
        })

    roles = [image["role"] for image in images]
    expected_roles = ["FIRST_IMAGE"] + ["INTERMEDIATE_IMAGE"] * 7 + ["LAST_IMAGE"]
    if roles != expected_roles:
        fatal(f"unexpected NEB image role sequence: {roles}")
    return images


def geometry_metrics(coordinates: list[list[float]]) -> dict[str, Any]:
    distances: dict[tuple[int, int], float] = {}
    for first in range(NAT):
        for second in range(first + 1, NAT):
            distance = norm3([
                coordinates[first][axis] - coordinates[second][axis]
                for axis in range(3)
            ])
            distances[(first + 1, second + 1)] = distance
    minimum_pair, minimum_pair_ang = min(distances.items(), key=lambda item: item[1])
    maximum_span_ang = max(distances.values())
    r_o1_h = distances[(1, 2)]
    r_h_o2 = distances[(2, 8)]
    r_oo = distances[(1, 8)]
    return {
        "qpt_ang": r_o1_h - r_h_o2,
        "roo_ang": r_oo,
        "minimum_pair": minimum_pair,
        "minimum_pair_ang": minimum_pair_ang,
        "maximum_span_ang": maximum_span_ang,
    }


def validate_images(
    images: list[dict[str, Any]],
    manifest_path: Path,
) -> list[dict[str, Any]]:
    manifest_rows = read_tsv(manifest_path)
    if len(manifest_rows) != EXPECTED_IMAGES:
        fatal(f"v019 image manifest has {len(manifest_rows)} rows")

    rows: list[dict[str, Any]] = []
    qpts: list[float] = []
    for image_index, (image, manifest_row) in enumerate(zip(images, manifest_rows), start=1):
        metrics = geometry_metrics(image["coordinates"])
        if metrics["minimum_pair_ang"] <= MIN_PAIR_ANG:
            fatal(
                f"image {image_index}: minimum pair "
                f"{metrics['minimum_pair_ang']:.8f} A"
            )
        if metrics["maximum_span_ang"] >= MAX_SPAN_ANG:
            fatal(
                f"image {image_index}: maximum span "
                f"{metrics['maximum_span_ang']:.8f} A"
            )
        manifest_qpt = parse_number(manifest_row["qpt_ang"])
        if abs(metrics["qpt_ang"] - manifest_qpt) > IMAGE_MANIFEST_QPT_TOL_ANG:
            fatal(
                f"image {image_index}: qPT differs from v019 manifest by "
                f"{metrics['qpt_ang'] - manifest_qpt:.3e} A"
            )
        qpts.append(metrics["qpt_ang"])
        rows.append({
            "image_index": image_index,
            "role": image["role"],
            "qpt_ang": metrics["qpt_ang"],
            "roo_ang": metrics["roo_ang"],
            "minimum_pair_atoms": f"{metrics['minimum_pair'][0]}-{metrics['minimum_pair'][1]}",
            "minimum_pair_ang": metrics["minimum_pair_ang"],
            "maximum_span_ang": metrics["maximum_span_ang"],
            "v019_manifest_qpt_ang": manifest_qpt,
            "v019_qpt_difference_ang": metrics["qpt_ang"] - manifest_qpt,
        })

    if not all(qpts[index] < qpts[index + 1] for index in range(len(qpts) - 1)):
        fatal(f"initial qPT sequence is not strictly increasing: {qpts}")
    if abs(qpts[4]) >= CENTRAL_QPT_MAX_ANG:
        fatal(f"central-image qPT is too far from zero: {qpts[4]:.8f} A")
    if not (qpts[0] < -0.30 and qpts[-1] > 0.30):
        fatal("initial path does not connect the two proton-transfer basins")
    return rows


def extract_card_lines(
    lines: list[str],
    header_pattern: str,
    count: int,
) -> list[str]:
    pattern = re.compile(header_pattern, re.IGNORECASE)
    matches = [index for index, line in enumerate(lines) if pattern.match(line)]
    if len(matches) != 1:
        fatal(f"expected one card matching {header_pattern!r}, found {len(matches)}")
    start = matches[0]
    card = [lines[start]]
    index = start + 1
    while index < len(lines) and len(card) < count + 1:
        if lines[index].strip():
            card.append(lines[index])
        index += 1
    if len(card) != count + 1:
        fatal(f"card matching {header_pattern!r} is truncated")
    return card


def parse_control_value(control: dict[str, str], key: str) -> str:
    if key not in control:
        fatal(f"canonical CONTROL lacks {key}")
    return control[key]


def validate_canonical_engine(source_input: Path) -> dict[str, Any]:
    text = source_input.read_text(encoding="utf-8", errors="strict")
    lines = text.splitlines()

    control_block, _, _ = extract_namelist_lines(lines, "CONTROL")
    system_block, _, _ = extract_namelist_lines(lines, "SYSTEM")
    electrons_block, _, _ = extract_namelist_lines(lines, "ELECTRONS")

    control = parse_namelist_assignments(control_block)
    system = parse_namelist_assignments(system_block)
    electrons = parse_namelist_assignments(electrons_block)

    pseudo_dir = Path(unquote(parse_control_value(control, "pseudo_dir"))).expanduser()
    if not pseudo_dir.is_dir():
        fatal(f"pseudo_dir does not exist: {pseudo_dir}")

    expected_system_numbers = {
        "ibrav": 0.0,
        "nat": 9.0,
        "ntyp": 3.0,
        "ecutwfc": 80.0,
        "ecutrho": 960.0,
        "tot_charge": 0.0,
        "nspin": 1.0,
    }
    for key, expected in expected_system_numbers.items():
        if key not in system:
            fatal(f"canonical SYSTEM lacks {key}")
        actual = parse_number(unquote(system[key]))
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1.0e-10):
            fatal(f"canonical {key}={actual}, expected {expected}")

    expected_system_strings = {"occupations": "fixed", "input_dft": "pbe"}
    for key, expected in expected_system_strings.items():
        if unquote(system.get(key, "")).lower() != expected:
            fatal(f"canonical {key}={system.get(key)!r}, expected {expected!r}")

    for key in ["nosym", "noinv"]:
        if key not in system or not parse_bool(system[key]):
            fatal(f"canonical {key} is not true")

    expected_electron_numbers = {
        "conv_thr": 1.0e-10,
        "electron_maxstep": 200.0,
        "mixing_beta": 0.30,
    }
    for key, expected in expected_electron_numbers.items():
        if key not in electrons:
            fatal(f"canonical ELECTRONS lacks {key}")
        actual = parse_number(unquote(electrons[key]))
        tolerance = 1.0e-14 if key == "conv_thr" else 1.0e-10
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
            fatal(f"canonical {key}={actual}, expected {expected}")

    if unquote(electrons.get("mixing_mode", "")).lower() != "plain":
        fatal("canonical mixing_mode is not plain")
    if unquote(electrons.get("diagonalization", "")).lower() != "david":
        fatal("canonical diagonalization is not david")

    atomic_species = extract_card_lines(
        lines,
        r"^\s*ATOMIC_SPECIES\s*$",
        3,
    )
    species_symbols: list[str] = []
    for line in atomic_species[1:]:
        fields = line.split()
        if len(fields) < 3:
            fatal(f"invalid ATOMIC_SPECIES line: {line!r}")
        species_symbols.append(fields[0])
        pseudo_path = pseudo_dir / fields[2]
        if not pseudo_path.is_file():
            fatal(f"pseudopotential missing: {pseudo_path}")
    if species_symbols != ["C", "H", "O"]:
        fatal(f"unexpected ATOMIC_SPECIES order: {species_symbols}")

    cell = extract_card_lines(
        lines,
        r"^\s*CELL_PARAMETERS\s+angstrom\s*$",
        3,
    )
    vectors = [[parse_number(value) for value in line.split()[:3]] for line in cell[1:]]
    expected_vectors = [
        [16.0, 0.0, 0.0],
        [0.0, 16.0, 0.0],
        [0.0, 0.0, 16.0],
    ]
    for actual, expected in zip(vectors, expected_vectors):
        for actual_value, expected_value in zip(actual, expected):
            if not math.isclose(actual_value, expected_value, rel_tol=0.0, abs_tol=1.0e-8):
                fatal(f"unexpected cell vector: {actual}")

    k_matches = [
        line
        for line in lines
        if re.match(r"^\s*K_POINTS\s+gamma\s*$", line, re.IGNORECASE)
    ]
    if len(k_matches) != 1:
        fatal(f"expected one K_POINTS gamma card, found {len(k_matches)}")

    return {
        "pseudo_dir": pseudo_dir,
        "system_block": system_block,
        "electrons_block": electrons_block,
        "atomic_species": atomic_species,
        "cell": cell,
        "k_points": k_matches[0],
        "source_sha256": sha256(source_input),
    }


def render_neb_input(
    path_spec: dict[str, Any],
    engine: dict[str, Any],
    images: list[dict[str, Any]],
) -> str:
    lines: list[str] = [
        "BEGIN",
        "BEGIN_PATH_INPUT",
        *render_path_block(path_spec["assignments"]),
        "END_PATH_INPUT",
        "BEGIN_ENGINE_INPUT",
        "&CONTROL",
        "  calculation = 'scf',",
        "  restart_mode = 'from_scratch',",
        "  prefix = 'independent_audit_neb_v024',",
        f"  pseudo_dir = '{engine['pseudo_dir']}',",
        "  outdir = './tmp',",
        "  tprnfor = .true.,",
        "  tstress = .false.,",
        "  disk_io = 'low',",
        "  verbosity = 'high',",
        "/",
        *engine["system_block"],
        *engine["electrons_block"],
        *engine["atomic_species"],
        "BEGIN_POSITIONS",
    ]

    for image in images:
        lines.append(image["role"])
        lines.append("ATOMIC_POSITIONS angstrom")
        for symbol, coordinate in zip(image["symbols"], image["coordinates"]):
            lines.append(
                f"{symbol:<2s} "
                f"{coordinate[0]:.12f} "
                f"{coordinate[1]:.12f} "
                f"{coordinate[2]:.12f}"
            )

    lines.extend([
        "END_POSITIONS",
        *engine["cell"],
        engine["k_points"],
        "END_ENGINE_INPUT",
        "END",
        "",
    ])
    return "\n".join(lines)


def validate_rendered_neb_input(
    text: str,
    source_images: list[dict[str, Any]],
) -> None:
    if "outdir = './tmp'/" in text or "outdir = './tmp'/tmp'" in text:
        fatal("malformed outdir survived rendering")
    if text.count("outdir = './tmp',") != 1:
        fatal("rendered input does not contain exactly one clean outdir")
    if text.count("tprnfor = .true.,") != 1:
        fatal("rendered input does not contain exactly one tprnfor")
    reparsed = parse_positions_from_neb(text)
    if len(reparsed) != len(source_images):
        fatal("rendered NEB image count changed")
    for image_index, (source, target) in enumerate(zip(source_images, reparsed), start=1):
        if source["symbols"] != target["symbols"]:
            fatal(f"rendered image {image_index} symbol order changed")
        for atom_index, (source_xyz, target_xyz) in enumerate(
            zip(source["coordinates"], target["coordinates"]),
            start=1,
        ):
            delta = norm3([
                source_xyz[axis] - target_xyz[axis]
                for axis in range(3)
            ])
            if delta > 2.0e-10:
                fatal(
                    f"rendered image {image_index} atom {atom_index} "
                    f"changed by {delta:.3e} A"
                )

    lines = text.splitlines()
    control_block, _, _ = extract_namelist_lines(lines, "CONTROL")
    control = parse_namelist_assignments(control_block)
    expected = {
        "calculation": "scf",
        "restart_mode": "from_scratch",
        "prefix": "independent_audit_neb_v024",
        "outdir": "./tmp",
    }
    for key, expected_value in expected.items():
        if unquote(control.get(key, "")).lower() != expected_value.lower():
            fatal(f"rendered CONTROL {key}={control.get(key)!r}")
    if not parse_bool(control.get("tprnfor", "")):
        fatal("rendered CONTROL tprnfor is not true")


def build_qe_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["OMP_NUM_THREADS"] = str(OMP_THREADS)
    environment["OPENBLAS_NUM_THREADS"] = "1"
    environment["MKL_NUM_THREADS"] = "1"
    environment["NUMEXPR_NUM_THREADS"] = "1"
    environment["PATH"] = (
        str(ENV_PREFIX / "bin")
        + os.pathsep
        + environment.get("PATH", "")
    )
    # Do not expose unrelated GROMACS/PLUMED libraries to QE/Open MPI.
    environment["LD_LIBRARY_PATH"] = str(CONDA_LIB)
    return environment


def find_live_qe_processes() -> list[str]:
    current_pid = os.getpid()
    live: list[str] = []
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return live

    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == current_pid:
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            raw = (entry / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        command = raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
        if not command:
            continue
        if re.search(r"(?:^|/)(?:neb|pw)\.x(?:\s|$)", command):
            live.append(f"pid={pid} command={command}")
    return sorted(live)


def validate_mpi_stack() -> dict[str, Any]:
    if not MPIRUN.is_file() or not os.access(MPIRUN, os.X_OK):
        fatal(f"conda mpirun missing or not executable: {MPIRUN}")
    if not NEB_X.is_file() or not os.access(NEB_X, os.X_OK):
        fatal(f"conda neb.x missing or not executable: {NEB_X}")
    if IMAGE_GROUPS < 1:
        fatal("IMAGE_GROUPS must be positive")
    if MPI_RANKS < IMAGE_GROUPS:
        fatal("MPI rank count is smaller than image-group count")
    if MPI_RANKS % IMAGE_GROUPS != 0:
        fatal("MPI rank count is not divisible by image-group count")
    if EXPECTED_IMAGES % IMAGE_GROUPS != 0:
        fatal("image count is not divisible by image-group count")
    if RANKS_PER_IMAGE_GROUP != MPI_RANKS // IMAGE_GROUPS:
        fatal("RANKS_PER_IMAGE_GROUP constant is inconsistent")

    live = find_live_qe_processes()
    if live:
        fatal(
            "existing QE processes detected; refusing concurrent launch:\n"
            + "\n".join(live)
        )

    ldd_result = subprocess.run(
        ["ldd", str(NEB_X)],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if ldd_result.returncode != 0:
        fatal(f"ldd failed for neb.x: {ldd_result.stderr.strip()}")
    ldd_text = ldd_result.stdout
    conda_lib_resolved = CONDA_LIB.resolve()
    mpi_lines = [
        line.strip()
        for line in ldd_text.splitlines()
        if re.search(r"libmpi(?:_|\.)|libopen-pal|libpmix", line)
    ]
    if not mpi_lines:
        fatal("neb.x ldd output contains no MPI libraries")

    mpi_linkages: list[tuple[str, Path]] = []
    unresolved_mpi_lines: list[str] = []
    wrong_mpi_lines: list[str] = []

    for line in mpi_lines:
        match = re.search(r"=>\s+(\S+)", line)
        if match is None or match.group(1) == "not":
            unresolved_mpi_lines.append(line)
            continue

        linked_path = Path(match.group(1)).resolve()
        mpi_linkages.append((line, linked_path))

        if not (
            linked_path == conda_lib_resolved
            or conda_lib_resolved in linked_path.parents
        ):
            wrong_mpi_lines.append(
                f"{line}\n  resolved={linked_path}"
            )

    if unresolved_mpi_lines:
        fatal(
            "unable to resolve one or more MPI library linkages:\n"
            + "\n".join(unresolved_mpi_lines)
        )

    if wrong_mpi_lines:
        fatal(
            "neb.x is linked to MPI libraries outside the conda environment:\n"
            + "\n".join(wrong_mpi_lines)
        )

    if not any(
        "libmpi.so" in line
        and (
            linked_path == conda_lib_resolved
            or conda_lib_resolved in linked_path.parents
        )
        for line, linked_path in mpi_linkages
    ):
        fatal("conda libmpi.so was not found in neb.x linkage")

    version_result = subprocess.run(
        [str(MPIRUN), "--version"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        env=build_qe_environment(),
    )
    version_text = (version_result.stdout + "\n" + version_result.stderr).strip()
    if version_result.returncode != 0 or "Open MPI" not in version_text:
        fatal(f"unexpected conda mpirun version output: {version_text}")

    smoke_command = [
        str(MPIRUN),
        "-np", str(MPI_RANKS),
        *MPI_BINDING_ARGS,
        "/bin/sh", "-c",
        'printf "rank=%s size=%s\\n" "$OMPI_COMM_WORLD_RANK" "$OMPI_COMM_WORLD_SIZE"',
    ]
    smoke = subprocess.run(
        smoke_command,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
        env=build_qe_environment(),
    )
    if smoke.returncode != 0:
        fatal(
            "3-rank MPI smoke test failed:\n"
            f"stdout:\n{smoke.stdout}\n"
            f"stderr:\n{smoke.stderr}"
        )

    observed: set[tuple[int, int]] = set()
    for line in smoke.stdout.splitlines():
        match = re.fullmatch(r"rank=(\d+) size=(\d+)", line.strip())
        if match:
            observed.add((int(match.group(1)), int(match.group(2))))
    expected = {(rank, MPI_RANKS) for rank in range(MPI_RANKS)}
    if observed != expected:
        fatal(
            f"MPI smoke test rank set mismatch: observed={sorted(observed)}, "
            f"expected={sorted(expected)}; raw stdout={smoke.stdout!r}"
        )

    return {
        "mpirun": MPIRUN,
        "mpirun_version": version_text,
        "neb_x": NEB_X,
        "mpi_ranks": MPI_RANKS,
        "image_groups": IMAGE_GROUPS,
        "omp_threads": OMP_THREADS,
        "binding_args": MPI_BINDING_ARGS,
        "ldd_mpi_lines": mpi_lines,
        "smoke_command": smoke_command,
        "smoke_stdout": smoke.stdout,
        "smoke_stderr": smoke.stderr,
    }


def terminate_process_group(process: subprocess.Popen[str], reason: str) -> None:
    if process.poll() is not None:
        return

    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=30)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=30)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=30)


def run_neb() -> tuple[int, float]:
    environment = build_qe_environment()
    command = [
        str(MPIRUN),
        "-np", str(MPI_RANKS),
        *MPI_BINDING_ARGS,
        str(NEB_X),
        "-ni", str(IMAGE_GROUPS),
        "-inp", str(NEB_INPUT.relative_to(RUN_ROOT)),
    ]

    start = time.time()
    process: subprocess.Popen[str] | None = None

    with NEB_OUTPUT.open("w", encoding="utf-8", buffering=1) as stdout, NEB_ERROR.open(
        "w", encoding="utf-8", buffering=1
    ) as stderr:
        stderr.write("COMMAND: " + " ".join(command) + "\n")
        stderr.write(f"LD_LIBRARY_PATH={environment['LD_LIBRARY_PATH']}\n")
        stderr.write(f"OMP_NUM_THREADS={environment['OMP_NUM_THREADS']}\n\n")
        stderr.flush()

        try:
            process = subprocess.Popen(
                command,
                cwd=RUN_ROOT,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                bufsize=1,
                env=environment,
                start_new_session=True,
            )
            assert process.stdout is not None
            deadline = start + NEB_TIMEOUT_SECONDS

            for line in process.stdout:
                stdout.write(line)
                print(line, end="", flush=True)
                if time.time() > deadline:
                    stderr.write("\nTIMEOUT_EXPIRED_v024\n")
                    stderr.flush()
                    terminate_process_group(process, "timeout")
                    return 124, time.time() - start

            returncode = process.wait()
            return returncode, time.time() - start

        except KeyboardInterrupt:
            if process is not None:
                terminate_process_group(process, "SIGINT")
            elapsed = time.time() - start
            stderr.write("\nINTERRUPTED_BY_SIGINT_v024\n")
            stderr.flush()
            raise NebInterrupted("SIGINT", elapsed)

        except NebInterrupted:
            if process is not None:
                terminate_process_group(process, "external signal")
            raise

        except BaseException:
            if process is not None:
                terminate_process_group(process, "parent exception")
            raise

def parse_final_neb_table(lines: list[str]) -> list[dict[str, Any]]:
    header_indices = [
        index
        for index, line in enumerate(lines)
        if "image" in line.lower()
        and "energy (ev)" in line.lower()
        and "error (ev/a)" in line.lower()
    ]
    if not header_indices:
        fatal("final NEB image energy/error table not found")
    header = header_indices[-1]
    row_re = re.compile(
        rf"^\s*(\d+)\s+({NUMBER})\s+({NUMBER})(?:\s+([TF]))?\s*$",
        re.IGNORECASE,
    )
    rows: list[dict[str, Any]] = []
    for line in lines[header + 1:]:
        match = row_re.match(line)
        if not match:
            if rows:
                if len(rows) == EXPECTED_IMAGES:
                    break
                continue
            continue
        rows.append({
            "image_index": int(match.group(1)),
            "energy_ev": parse_number(match.group(2)),
            "error_ev_ang": parse_number(match.group(3)),
            "frozen": match.group(4) or "",
        })
        if len(rows) == EXPECTED_IMAGES:
            break
    if len(rows) != EXPECTED_IMAGES:
        fatal(f"parsed {len(rows)} rows from final NEB table, expected 9")
    if [row["image_index"] for row in rows] != list(range(1, EXPECTED_IMAGES + 1)):
        fatal("final NEB table image indices are not 1..9")
    return rows


def parse_neb_output(path: Path, path_thr: float) -> dict[str, Any]:
    if not path.is_file():
        fatal(f"NEB output missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if "JOB DONE." not in text:
        fatal("NEB output lacks JOB DONE")
    convergence_matches = re.findall(
        r"neb:\s*convergence\s+achieved\s+in\s+(\d+)\s+iterations",
        text,
        flags=re.IGNORECASE,
    )
    if not convergence_matches:
        fatal("NEB convergence marker missing")
    if re.search(r"convergence\s+NOT\s+achieved", text, flags=re.IGNORECASE):
        fatal("NEB output reports nonconvergence")

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
    if not forward_matches or not backward_matches:
        fatal("NEB activation energies missing")

    final_table = parse_final_neb_table(lines)
    internal_errors = [row["error_ev_ang"] for row in final_table[1:-1]]
    maximum_internal_error = max(internal_errors)
    if maximum_internal_error > path_thr + 5.0e-4:
        fatal(
            f"NEB claims convergence but maximum internal error is "
            f"{maximum_internal_error:.6f} eV/A, path_thr={path_thr:.6f}"
        )

    climbing_matches = re.findall(
        r"climbing\s+image\s*=\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    )
    climbing_image = int(climbing_matches[-1]) if climbing_matches else None
    if climbing_image is not None and not (2 <= climbing_image <= EXPECTED_IMAGES - 1):
        fatal(f"invalid climbing image index: {climbing_image}")

    path_length_matches = re.findall(
        rf"path\s+length\s*=\s*({NUMBER})\s+bohr",
        text,
        flags=re.IGNORECASE,
    )
    distance_matches = re.findall(
        rf"inter-image\s+distance\s*=\s*({NUMBER})\s+bohr",
        text,
        flags=re.IGNORECASE,
    )

    return {
        "iterations": int(convergence_matches[-1]),
        "activation_forward_ev": parse_number(forward_matches[-1]),
        "activation_backward_ev": parse_number(backward_matches[-1]),
        "climbing_image": climbing_image,
        "path_length_bohr": parse_number(path_length_matches[-1]) if path_length_matches else None,
        "inter_image_distance_bohr": parse_number(distance_matches[-1]) if distance_matches else None,
        "maximum_internal_error_ev_ang": maximum_internal_error,
        "final_table": final_table,
        "output_sha256": sha256(path),
    }


def main() -> None:
    if not RUN_NEB:
        fatal("RUN_NEB is disabled")
    if any([
        RUN_PW_DIRECT,
        RUN_MLP,
        RUN_LAMMPS,
        USE_OLD_NEB_COORDINATES,
        USE_AUDIT_FOR_TRAINING,
    ]):
        fatal("v024 execution or scientific guards were modified")
    mpi_info = validate_mpi_stack()

    v019 = resolve_attempt(
        V019_POINTER,
        "STATUS_v019.txt",
        "PASS_INDEPENDENT_AUDIT_DESIGN_FROZEN_NO_DFT",
    )
    v020 = resolve_attempt(
        V020_POINTER,
        "STATUS_v020.txt",
        "PASS_PRE_AUDIT_PROTOCOL_LOCK_NO_CALCULATIONS",
    )
    v022 = resolve_attempt(
        V022_POINTER,
        "STATUS_v022.txt",
        "PASS_BASIN_AUDIT_FORCE_RECOVERY12_LABELLED",
    )
    v023 = resolve_attempt(
        V023_POINTER,
        "STATUS_v023.txt",
        "PASS_BASIN_AUDIT_FORCE_BLOCK_REPARSE12_LABELLED",
    )

    source_neb_input = v019 / "neb_audit" / "independent_neb_9img_v019.in"
    source_manifest = v019 / "neb_audit" / "independent_neb_initial_path_9img_v019.tsv"
    canonical_pw = (
        v022
        / "cases"
        / "audit_basin_sp_v019_001"
        / "pw_force_restart_v022.in"
    )
    corrected_basin_cfg = (
        v023
        / "labels"
        / "frozen_basin_audit_labels_corrected_v023.cfg"
    )

    for required in [source_neb_input, source_manifest, canonical_pw, corrected_basin_cfg]:
        if not required.is_file():
            fatal(f"required upstream file missing: {required}")

    if corrected_basin_cfg.read_text(encoding="utf-8").count("BEGIN_CFG") != 12:
        fatal("authoritative v023 basin audit CFG does not contain 12 blocks")

    source_text = source_neb_input.read_text(encoding="utf-8", errors="strict")
    path_spec = extract_path_spec(source_text)
    images = parse_positions_from_neb(source_text)
    image_rows = validate_images(images, source_manifest)
    engine = validate_canonical_engine(canonical_pw)
    rendered = render_neb_input(path_spec, engine, images)
    validate_rendered_neb_input(rendered, images)

    if PREFLIGHT_ONLY:
        command = [
            str(MPIRUN),
            "-np", str(MPI_RANKS),
            *MPI_BINDING_ARGS,
            str(NEB_X),
            "-ni", str(IMAGE_GROUPS),
            "-inp", "input/independent_audit_neb_9img_v024.in",
        ]
        print("PASS_V024_MPI3_PREFLIGHT_NO_DFT")
        print(f"neb.x:        {NEB_X}")
        print(f"mpirun:       {MPIRUN}")
        print(f"MPI ranks:    {MPI_RANKS}")
        print(f"image groups: {IMAGE_GROUPS}")
        print(f"ranks/group:  {RANKS_PER_IMAGE_GROUP}")
        print(f"OMP threads:  {OMP_THREADS}")
        print(f"binding:      {' '.join(MPI_BINDING_ARGS)}")
        print(f"command:      {' '.join(command)}")
        print("No attempt directory was created.")
        print("neb.x was NOT executed.")
        return

    stale_running_pointer = None
    if RUNNING_POINTER.is_file():
        stale_running_pointer = RUNNING_POINTER.read_text(
            encoding="utf-8"
        ).strip() or None

    if RUN_ROOT.exists():
        fatal(f"attempt already exists: {RUN_ROOT}")
    for directory in [RUN_ROOT, INPUT_DIR, REPORT_DIR, PROVENANCE_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    STATUS_FILE.write_text("RUNNING_INDEPENDENT_NEB_DFT_v024\n", encoding="utf-8")
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    RUNNING_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    NEB_INPUT.write_text(rendered, encoding="utf-8")
    write_tsv(
        IMAGE_MANIFEST,
        image_rows,
        fieldnames=[
            "image_index",
            "role",
            "qpt_ang",
            "roo_ang",
            "minimum_pair_atoms",
            "minimum_pair_ang",
            "maximum_span_ang",
            "v019_manifest_qpt_ang",
            "v019_qpt_difference_ang",
        ],
    )

    shutil.copy2(source_neb_input, PROVENANCE_DIR / "independent_neb_9img_v019_original.in")
    shutil.copy2(source_manifest, PROVENANCE_DIR / "independent_neb_initial_path_9img_v019.tsv")
    shutil.copy2(canonical_pw, PROVENANCE_DIR / "canonical_pw_force_input_v022.in")

    provenance = {
        "created_utc": utc_now(),
        "v019": v019,
        "v020": v020,
        "v022": v022,
        "v023": v023,
        "source_v019_neb_input": source_neb_input,
        "source_v019_neb_input_sha256": sha256(source_neb_input),
        "source_v019_manifest_sha256": sha256(source_manifest),
        "canonical_pw_input": canonical_pw,
        "canonical_pw_input_sha256": sha256(canonical_pw),
        "corrected_basin_cfg": corrected_basin_cfg,
        "corrected_basin_cfg_sha256": sha256(corrected_basin_cfg),
        "rendered_neb_input": NEB_INPUT,
        "rendered_neb_input_sha256": sha256(NEB_INPUT),
        "path_spec": path_spec,
        "execution": {
            "neb_x": NEB_X,
            "mpirun": MPIRUN,
            "mpi_ranks": MPI_RANKS,
            "image_groups": IMAGE_GROUPS,
            "omp_threads": OMP_THREADS,
            "binding_args": MPI_BINDING_ARGS,
            "timeout_seconds": NEB_TIMEOUT_SECONDS,
            "ld_library_path_for_qe": str(CONDA_LIB),
            "pw_direct": False,
            "mlp": False,
            "lammps": False,
        },
        "mpi_validation": mpi_info,
        "stale_running_pointer_before_this_attempt": stale_running_pointer,
    }
    (PROVENANCE_DIR / "provenance_v024.json").write_text(
        json.dumps(json_safe(provenance), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    log("Validated v019 model-blind 9-image path and v023 corrected basin audit labels.")
    log("Rebuilt NEB input structurally from clean PATH, CONTROL, SYSTEM and ELECTRONS blocks.")
    log("Confirmed clean outdir='./tmp', tprnfor=.true., 9 images, monotonic qPT and fixed endpoints.")
    log("Validated conda Open MPI launcher, neb.x linkage, and 3-rank smoke test.")

    print()
    print("STEP 26 / INDEPENDENT 9-IMAGE DFT CI-NEB v024")
    print()
    print(f"Run root:          {RUN_ROOT}")
    print(f"neb.x:             {NEB_X}")
    print(f"mpirun:            {MPIRUN}")
    print(f"MPI ranks:         {MPI_RANKS}")
    print(f"Image groups:      {IMAGE_GROUPS}")
    print(f"Ranks/image group: {RANKS_PER_IMAGE_GROUP}")
    print(f"Binding:           {' '.join(MPI_BINDING_ARGS)}")
    print(f"Images:            {EXPECTED_IMAGES}")
    print(f"nstep_path:        {path_spec['nstep_path']}")
    print(f"opt_scheme:        {path_spec['opt_scheme']}")
    print(f"CI_scheme:         {path_spec['ci_scheme']}")
    print(f"path_thr:          {path_spec['path_thr_ev_ang']:.6f} eV/A")
    print(f"OMP threads:       {OMP_THREADS}")
    print(f"Timeout:           {NEB_TIMEOUT_SECONDS / 3600:.1f} h")
    print("Direct pw.x:       NO")
    print("MTP execution:     NO")
    print("LAMMPS execution:  NO")
    print()
    print("neb.x is now being executed. This may take many hours.")
    print()

    returncode, elapsed = run_neb()

    if returncode != 0:
        killed_by_sigkill = returncode in {137, -9}

        failure_status = (
            "FAIL_NEB_SIGKILL_PROBABLE_OOM_v024"
            if killed_by_sigkill
            else "FAIL_NEB_PROCESS_v024"
        )

        STATUS_FILE.write_text(
            failure_status + "\n",
            encoding="utf-8",
        )

        summary = {
            "created_utc": utc_now(),
            "status": failure_status,
            "run_root": RUN_ROOT,
            "returncode": returncode,
            "probable_oom": killed_by_sigkill,
            "elapsed_seconds": elapsed,
            "neb_input": NEB_INPUT,
            "neb_output": NEB_OUTPUT,
            "neb_error": NEB_ERROR,
            "mpi_ranks": MPI_RANKS,
            "image_groups": IMAGE_GROUPS,
            "ranks_per_image_group": RANKS_PER_IMAGE_GROUP,
            "omp_threads": OMP_THREADS,
        }

        SUMMARY_JSON.write_text(
            json.dumps(
                json_safe(summary),
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        if killed_by_sigkill:
            fatal(
                "neb.x was killed by SIGKILL "
                "(return code 137/-9); "
                "the probable cause is memory exhaustion"
            )

        fatal(f"neb.x failed with return code {returncode}")

    parsed = parse_neb_output(NEB_OUTPUT, path_spec["path_thr_ev_ang"])
    write_tsv(
        FINAL_TABLE_TSV,
        parsed["final_table"],
        fieldnames=["image_index", "energy_ev", "error_ev_ang", "frozen"],
    )

    generated_pw_inputs = sorted(RUN_ROOT.glob("pw_*.in"))
    save_dirs = sorted(RUN_ROOT.rglob("*.save"))
    crd_files = sorted(RUN_ROOT.glob("*.crd"))
    path_files = sorted(RUN_ROOT.glob("*.path"))

    if len(generated_pw_inputs) != EXPECTED_IMAGES:
        fatal(
            f"neb.x generated {len(generated_pw_inputs)} pw_*.in files, "
            f"expected {EXPECTED_IMAGES}"
        )
    if len(save_dirs) < EXPECTED_IMAGES:
        fatal(
            f"found only {len(save_dirs)} QE save directories after converged NEB"
        )
    if not (RUN_ROOT / "neb.dat").is_file():
        fatal("neb.x did not generate neb.dat")
    if not crd_files:
        fatal("converged NEB did not produce a .crd coordinate file")

    status = "PASS_INDEPENDENT_NEB9_DFT_CONVERGED"
    STATUS_FILE.write_text(status + "\n", encoding="utf-8")

    report_lines = [
        "# Independent 9-image DFT CI-NEB report v024",
        "",
        f"Created UTC: {utc_now()}",
        "",
        "## Status",
        "",
        f"- {status}",
        f"- NEB iterations: {parsed['iterations']}",
        f"- Forward activation energy: {parsed['activation_forward_ev']:.12f} eV",
        f"- Backward activation energy: {parsed['activation_backward_ev']:.12f} eV",
        f"- Climbing image: {parsed['climbing_image']}",
        f"- Maximum internal-image error: {parsed['maximum_internal_error_ev_ang']:.12f} eV/Angstrom",
        f"- Locked path threshold: {path_spec['path_thr_ev_ang']:.12f} eV/Angstrom",
        "",
        "## Input repair",
        "",
        "- The malformed v019 PW engine CONTROL block was not reused.",
        "- The v019 model-blind image coordinates and PATH settings were retained.",
        "- CONTROL was reconstructed with clean outdir='./tmp'.",
        "- tprnfor=.true. is inside CONTROL.",
        "- The DFT SYSTEM and ELECTRONS settings came from the validated v022 input.",
        "",
        "## Execution",
        "",
        f"- neb.x: `{NEB_X}`",
        f"- mpirun: `{MPIRUN}`",
        f"- MPI ranks: {MPI_RANKS}",
        f"- Image groups: {IMAGE_GROUPS}",
        f"- MPI binding: {' '.join(MPI_BINDING_ARGS)}",
        f"- Wall time: {elapsed / 3600:.6f} h",
        f"- OMP threads per rank: {OMP_THREADS}",
        "- Direct pw.x execution: no",
        "- MTP execution: no",
        "- LAMMPS execution: no",
        "",
        "## Files",
        "",
        f"- Corrected NEB input: `{NEB_INPUT}`",
        f"- NEB output: `{NEB_OUTPUT}`",
        f"- Final energy/error table: `{FINAL_TABLE_TSV}`",
        f"- Coordinate files: {', '.join(str(path) for path in crd_files)}",
        f"- Path files: {', '.join(str(path) for path in path_files) if path_files else 'none found'}",
        "",
        "The .crd path must be extracted and all nine final geometries",
        "must be recomputed by independent pw.x single points before",
        "the transition-path part of the frozen audit is complete.",
    ]
    REPORT_MD.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    summary = {
        "created_utc": utc_now(),
        "status": status,
        "run_root": RUN_ROOT,
        "elapsed_seconds": elapsed,
        "parallel_execution": {
            "mpirun": MPIRUN,
            "mpi_ranks": MPI_RANKS,
            "image_groups": IMAGE_GROUPS,
            "omp_threads_per_rank": OMP_THREADS,
            "binding_args": MPI_BINDING_ARGS,
        },
        "path": {
            "images": EXPECTED_IMAGES,
            "nstep_path": path_spec["nstep_path"],
            "path_thr_ev_ang": path_spec["path_thr_ev_ang"],
            "opt_scheme": path_spec["opt_scheme"],
            "ci_scheme": path_spec["ci_scheme"],
        },
        "result": parsed,
        "generated": {
            "pw_inputs": generated_pw_inputs,
            "save_directories": save_dirs,
            "crd_files": crd_files,
            "path_files": path_files,
        },
        "outputs": {
            "neb_input": NEB_INPUT,
            "neb_output": NEB_OUTPUT,
            "neb_error": NEB_ERROR,
            "initial_image_manifest": IMAGE_MANIFEST,
            "final_table": FINAL_TABLE_TSV,
            "report": REPORT_MD,
        },
    }
    SUMMARY_JSON.write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    checksum_paths = sorted(
        [path for path in RUN_ROOT.rglob("*") if path.is_file() and path != CHECKSUMS_TSV],
        key=lambda path: str(path),
    )
    with CHECKSUMS_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=["path", "sha256"])
        writer.writeheader()
        for path in checksum_paths:
            writer.writerow({
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
            })

    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
    if RUNNING_POINTER.is_file():
        RUNNING_POINTER.unlink()

    print()
    print("PASS_INDEPENDENT_NEB9_DFT_CONVERGED: STEP 26 v024 COMPLETED")
    print()
    print(f"Run root:                 {RUN_ROOT}")
    print(f"NEB iterations:           {parsed['iterations']}")
    print(f"Forward barrier:          {parsed['activation_forward_ev']:.8f} eV")
    print(f"Backward barrier:         {parsed['activation_backward_ev']:.8f} eV")
    print(f"Climbing image:           {parsed['climbing_image']}")
    print(f"Maximum internal error:   {parsed['maximum_internal_error_ev_ang']:.8f} eV/A")
    print(f"Wall time:                {elapsed / 3600:.3f} h")
    print()
    print(f"NEB output:               {NEB_OUTPUT}")
    print(f"Final table:              {FINAL_TABLE_TSV}")
    print(f"Coordinate file(s):       {', '.join(str(path) for path in crd_files)}")
    print()
    print("neb.x WAS executed and converged.")
    print("Direct pw.x was NOT executed by this script.")
    print("mlp was NOT executed.")
    print("LAMMPS was NOT executed.")
    print()
    print("Next stage: extract the final .crd path and run 9 independent pw.x single points.")


def cleanup_running_pointer_for_this_attempt() -> None:
    if not RUNNING_POINTER.is_file():
        return
    try:
        running_value = RUNNING_POINTER.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if running_value == str(RUN_ROOT):
        RUNNING_POINTER.unlink(missing_ok=True)


def record_interruption(interruption: NebInterrupted) -> None:
    try:
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        status = "INTERRUPTED_DURING_NEB_v024"
        STATUS_FILE.write_text(status + "\n", encoding="utf-8")
        VERSION_ROOT.mkdir(parents=True, exist_ok=True)
        INTERRUPTED_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
        cleanup_running_pointer_for_this_attempt()
        payload = {
            "created_utc": utc_now(),
            "status": status,
            "run_root": RUN_ROOT,
            "reason": interruption.reason,
            "elapsed_seconds": interruption.elapsed_seconds,
            "neb_input": NEB_INPUT,
            "neb_output": NEB_OUTPUT,
            "neb_error": NEB_ERROR,
            "mpi_ranks": MPI_RANKS,
            "image_groups": IMAGE_GROUPS,
            "omp_threads": OMP_THREADS,
        }
        SUMMARY_JSON.write_text(
            json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass


if __name__ == "__main__":
    previous_sigterm_handler = signal.getsignal(signal.SIGTERM)

    def _sigterm_handler(signum: int, frame: Any) -> None:
        raise NebInterrupted(signal.Signals(signum).name)

    signal.signal(signal.SIGTERM, _sigterm_handler)

    try:
        main()

    except KeyboardInterrupt:
        interruption = NebInterrupted("SIGINT")
        record_interruption(interruption)
        print("\nINTERRUPTED_DURING_NEB_v024: SIGINT", file=sys.stderr)
        raise SystemExit(130)

    except NebInterrupted as interruption:
        record_interruption(interruption)
        print(
            f"\nINTERRUPTED_DURING_NEB_v024: {interruption.reason}",
            file=sys.stderr,
        )
        raise SystemExit(130 if interruption.reason == "SIGINT" else 143)

    except Exception as error:
        try:
            RUN_ROOT.mkdir(parents=True, exist_ok=True)
            current_status = (
                STATUS_FILE.read_text(encoding="utf-8").strip()
                if STATUS_FILE.is_file()
                else ""
            )
            if not current_status.startswith("FAIL_"):
                STATUS_FILE.write_text("FAIL_RUNTIME_v024\n", encoding="utf-8")
            VERSION_ROOT.mkdir(parents=True, exist_ok=True)
            FAILED_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")
            cleanup_running_pointer_for_this_attempt()
        except Exception:
            pass
        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)

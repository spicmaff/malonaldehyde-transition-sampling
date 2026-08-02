#!/usr/bin/env python3
"""
Figure 04 rendering v014
========================

Render the secondary relaxed MTP-NEB structural diagnostic from the completed
visualization Step 01 v005 source package.

No DFT, NEB engine, model loading, training, ``mlp``, LAMMPS, or molecular
dynamics is executed.

Authoritative input:
    10_visualization/versions/
    v005_q1_dataviz_source_audit_source_oracle_recovery/
    CURRENT_VISUAL_SOURCE_AUDIT_V005.txt

Output:
    10_visualization/versions/
    v014_figure04_secondary_mtp_neb/attempt_<UTC>/

Panels
------
a. Frozen DFT NEB9 versus the converged targeted relaxed MTP-NEB profile.
b. Structural path audit in (qPT, R_OO), including the invalid basin collapse.

The targeted relaxed path is secondary evidence only because its MaxVol grades
remain strongly extrapolative. The basin optimized path is not assigned a
physically meaningful barrier.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


IMPLEMENTATION_ID = "RENDER_FIGURE04_SECONDARY_MTP_NEB_V014"
OUTPUT_VERSION = "v014_figure04_secondary_mtp_neb"
EXPECTED_INPUT_STATUS = "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"
STATUS_PASS = "PASS_FIGURE04_SECONDARY_MTP_NEB_RENDERED_V014"
STATUS_FAIL = "FAIL_FIGURE04_SECONDARY_MTP_NEB_V014"

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
OUTPUT_RELATIVE_ROOT = "10_visualization/versions/v014_figure04_secondary_mtp_neb"
OUTPUT_POINTER = "CURRENT_FIGURE04_SECONDARY_MTP_NEB_V014.txt"

PROFILE_FILE = "source_data/mtp_neb_paths_v005.tsv"
CLASSIFICATION_FILE = "source_data/mtp_neb_classification_v005.tsv"
DFT_GEOMETRY_FILE = "geometry/dft_independent_neb9_v005.xyz"
TARGETED_GEOMETRY_FILE = "geometry/mtp_neb_targeted_v005.xyz"
BASIN_GEOMETRY_FILE = "geometry/mtp_neb_basin_v005.xyz"
STYLE_FILE = "visual_style_lock_v005.json"
FIGURE_MANIFEST_FILE = "figure_manifest_v005.tsv"
SUMMARY_FILE = "summary_v005.json"
CHECKSUM_FILE = "checksums_v005.tsv"
STATUS_FILE = "STATUS_v005.txt"

SERIES_ORDER = ("DFT", "targeted", "basin")
EXPECTED_IMAGES = tuple(range(1, 10))
EXPECTED_ATOM_SEQUENCE = ("O", "H", "C", "H", "C", "H", "C", "O", "H")
NUMERIC_TOLERANCE = 5.0e-9
GEOMETRY_TOLERANCE_ANG = 2.0e-7
GEOMETRY_GUARD_ROO_ANG = 1.800

EXPECTED_METRICS = {
    "dft_barrier_ev": 0.036072093892926205,
    "targeted_barrier_ev": 0.030672292320105043,
    "targeted_barrier_abs_error_mev": 5.399801572821161,
    "targeted_maximum_image": 5,
    "targeted_maximum_neb_force_ev_ang": 0.02664574947856421,
    "targeted_maximum_rmsd_ang": 0.0023785855552754713,
    "targeted_grade_median": 5216.319957,
    "targeted_grade_max": 12006.843432,
    "basin_minimum_relative_energy_ev": -5.0962582067941185,
    "basin_minimum_roo_ang": 1.7985316061400438,
    "basin_minimum_pair_ang": 0.9519427449504909,
    "basin_maximum_neb_force_ev_ang": 11.442975922160553,
    "basin_grade_median": 9207.164193,
    "basin_grade_max": 535658.716794,
}


class FigureAuditError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Validation:
    check: str
    passed: bool
    observed: str
    expected: str
    severity: str = "ERROR"


@dataclasses.dataclass(frozen=True)
class XYZFrame:
    elements: tuple[str, ...]
    positions: tuple[tuple[float, float, float], ...]
    comment: str


@dataclasses.dataclass
class LockedInputs:
    attempt: Path
    profile_path: Path
    classification_path: Path
    dft_geometry_path: Path
    targeted_geometry_path: Path
    basin_geometry_path: Path
    style_path: Path
    figure_manifest_path: Path
    summary_path: Path
    checksums_path: Path
    profile_rows: list[dict[str, str]]
    classification_rows: list[dict[str, str]]
    dft_frames: list[XYZFrame]
    targeted_frames: list[XYZFrame]
    basin_frames: list[XYZFrame]
    style: dict[str, Any]
    summary: dict[str, Any]
    figure_manifest_row: dict[str, str]
    source_hashes: dict[str, str]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(path: Path, label: str) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FigureAuditError(f"Missing {label}: {path}")
    if path.stat().st_size <= 0:
        raise FigureAuditError(f"Empty {label}: {path}")
    return path


def read_text(path: Path) -> str:
    return require_file(path, "text file").read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise FigureAuditError(f"Invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FigureAuditError(f"Expected a JSON object: {path}")
    return value


def read_tsv(path: Path) -> list[dict[str, str]]:
    path = require_file(path, "TSV file")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise FigureAuditError(f"TSV has no header: {path}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise FigureAuditError(f"TSV has no rows: {path}")
    return rows


def parse_float(value: Any, label: str) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise FigureAuditError(f"Invalid float for {label}: {value!r}") from exc
    if not math.isfinite(result):
        raise FigureAuditError(f"Non-finite float for {label}: {value!r}")
    return result


def parse_optional_float(value: Any, label: str) -> float | None:
    stripped = str(value).strip()
    if not stripped:
        return None
    return parse_float(stripped, label)


def parse_int(value: Any, label: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise FigureAuditError(f"Invalid integer for {label}: {value!r}") from exc


def parse_bool(value: Any, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise FigureAuditError(f"Invalid boolean for {label}: {value!r}")


def close(a: float, b: float, tolerance: float = NUMERIC_TOLERANCE) -> bool:
    return abs(a - b) <= tolerance


def atomic_write_text(path: Path, text: str) -> None:
    path = path.resolve()
    if path.exists():
        raise FigureAuditError(f"Refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def atomic_write_tsv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> None:
    path = path.resolve()
    if path.exists():
        raise FigureAuditError(f"Refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            fieldnames=list(fieldnames),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    os.replace(temporary, path)


def parse_xyz(path: Path) -> list[XYZFrame]:
    lines = require_file(path, "XYZ geometry").read_text(
        encoding="utf-8"
    ).splitlines()
    frames: list[XYZFrame] = []
    cursor = 0
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        try:
            atom_count = int(lines[cursor].strip())
        except ValueError as exc:
            raise FigureAuditError(
                f"Invalid XYZ atom count at {path}:{cursor + 1}"
            ) from exc
        if atom_count != len(EXPECTED_ATOM_SEQUENCE):
            raise FigureAuditError(
                f"Unexpected atom count in {path}: {atom_count}"
            )
        if cursor + atom_count + 1 >= len(lines):
            raise FigureAuditError(f"Truncated XYZ frame in {path}")
        comment = lines[cursor + 1]
        elements: list[str] = []
        positions: list[tuple[float, float, float]] = []
        for offset in range(atom_count):
            tokens = lines[cursor + 2 + offset].split()
            if len(tokens) < 4:
                raise FigureAuditError(
                    f"Invalid XYZ atom row in {path}: "
                    f"{lines[cursor + 2 + offset]!r}"
                )
            element = tokens[0]
            xyz = tuple(
                parse_float(tokens[index], f"{path} coordinate")
                for index in (1, 2, 3)
            )
            elements.append(element)
            positions.append(xyz)
        if tuple(elements) != EXPECTED_ATOM_SEQUENCE:
            raise FigureAuditError(
                f"Atom sequence mismatch in {path}: {elements}"
            )
        frames.append(
            XYZFrame(
                elements=tuple(elements),
                positions=tuple(positions),
                comment=comment,
            )
        )
        cursor += atom_count + 2
    if not frames:
        raise FigureAuditError(f"No XYZ frames found: {path}")
    return frames


def distance(
    point_a: Sequence[float],
    point_b: Sequence[float],
) -> float:
    return math.sqrt(
        sum((float(a) - float(b)) ** 2 for a, b in zip(point_a, point_b))
    )


def frame_qpt_roo(frame: XYZFrame) -> tuple[float, float]:
    oxygen_left = frame.positions[0]
    proton = frame.positions[1]
    oxygen_right = frame.positions[7]
    qpt = distance(oxygen_left, proton) - distance(oxygen_right, proton)
    roo = distance(oxygen_left, oxygen_right)
    return qpt, roo


def verify_checksum_entry(
    attempt: Path,
    checksum_rows: Sequence[Mapping[str, str]],
    relative_path: str,
) -> str:
    matches = [
        row for row in checksum_rows
        if row.get("relative_path") == relative_path
    ]
    if len(matches) != 1:
        raise FigureAuditError(
            f"Expected one checksum row for {relative_path}; "
            f"found {len(matches)}"
        )
    target = require_file(attempt / relative_path, relative_path)
    expected_size = parse_int(matches[0]["size_bytes"], f"{relative_path} size")
    observed_size = target.stat().st_size
    expected_hash = matches[0]["sha256"].strip()
    observed_hash = sha256_file(target)
    if expected_size != observed_size or expected_hash != observed_hash:
        raise FigureAuditError(
            f"Input checksum mismatch for {relative_path}: "
            f"size={observed_size}/{expected_size}; "
            f"sha256={observed_hash}/{expected_hash}"
        )
    return observed_hash


def resolve_input_attempt(root: Path) -> Path:
    version_root = (root / INPUT_RELATIVE_ROOT).resolve()
    pointer = require_file(version_root / INPUT_POINTER, "v005 current pointer")
    raw = pointer.read_text(encoding="utf-8").strip()
    if not raw:
        raise FigureAuditError(f"Empty v005 pointer: {pointer}")
    attempt = Path(raw).expanduser().resolve()
    try:
        attempt.relative_to(version_root)
    except ValueError as exc:
        raise FigureAuditError(
            f"v005 pointer escapes expected version root: {attempt}"
        ) from exc
    if not attempt.is_dir():
        raise FigureAuditError(f"v005 pointer target is absent: {attempt}")
    observed_status = read_text(attempt / STATUS_FILE).strip()
    if observed_status != EXPECTED_INPUT_STATUS:
        raise FigureAuditError(
            f"Unexpected v005 status: {observed_status}; "
            f"expected {EXPECTED_INPUT_STATUS}"
        )
    return attempt


def load_locked_inputs(root: Path) -> LockedInputs:
    attempt = resolve_input_attempt(root)
    checksum_rows = read_tsv(attempt / CHECKSUM_FILE)
    relatives = (
        PROFILE_FILE,
        CLASSIFICATION_FILE,
        DFT_GEOMETRY_FILE,
        TARGETED_GEOMETRY_FILE,
        BASIN_GEOMETRY_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    source_hashes = {
        relative: verify_checksum_entry(attempt, checksum_rows, relative)
        for relative in relatives
    }

    manifest_rows = read_tsv(attempt / FIGURE_MANIFEST_FILE)
    matches = [row for row in manifest_rows if row.get("figure_id") == "Figure_4"]
    if len(matches) != 1:
        raise FigureAuditError(
            f"Expected one Figure_4 manifest row; found {len(matches)}"
        )
    manifest_row = matches[0]
    if manifest_row.get("status") != "SOURCE_DATA_READY":
        raise FigureAuditError(
            f"Figure_4 source status is {manifest_row.get('status')!r}"
        )

    return LockedInputs(
        attempt=attempt,
        profile_path=attempt / PROFILE_FILE,
        classification_path=attempt / CLASSIFICATION_FILE,
        dft_geometry_path=attempt / DFT_GEOMETRY_FILE,
        targeted_geometry_path=attempt / TARGETED_GEOMETRY_FILE,
        basin_geometry_path=attempt / BASIN_GEOMETRY_FILE,
        style_path=attempt / STYLE_FILE,
        figure_manifest_path=attempt / FIGURE_MANIFEST_FILE,
        summary_path=attempt / SUMMARY_FILE,
        checksums_path=attempt / CHECKSUM_FILE,
        profile_rows=read_tsv(attempt / PROFILE_FILE),
        classification_rows=read_tsv(attempt / CLASSIFICATION_FILE),
        dft_frames=parse_xyz(attempt / DFT_GEOMETRY_FILE),
        targeted_frames=parse_xyz(attempt / TARGETED_GEOMETRY_FILE),
        basin_frames=parse_xyz(attempt / BASIN_GEOMETRY_FILE),
        style=read_json(attempt / STYLE_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        figure_manifest_row=manifest_row,
        source_hashes=source_hashes,
    )


def profile_by_series(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, str]]]:
    output = {series: [] for series in SERIES_ORDER}
    for row in rows:
        series = row.get("series", "")
        if series not in output:
            raise FigureAuditError(f"Unexpected MTP-NEB series: {series!r}")
        output[series].append(dict(row))
    for series in SERIES_ORDER:
        output[series].sort(key=lambda row: parse_int(row["image"], "image"))
    return output


def classification_by_branch(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        branch = row.get("branch", "")
        if branch in output:
            raise FigureAuditError(f"Duplicate classification branch: {branch}")
        output[branch] = dict(row)
    return output


def validate_inputs(inputs: LockedInputs) -> list[Validation]:
    validations: list[Validation] = []
    profiles = profile_by_series(inputs.profile_rows)
    classes = classification_by_branch(inputs.classification_rows)

    validations.extend(
        [
            Validation(
                "profile_row_count",
                len(inputs.profile_rows) == 27,
                str(len(inputs.profile_rows)),
                "27",
            ),
            Validation(
                "classification_branch_set",
                set(classes) == {"basin", "targeted"},
                str(sorted(classes)),
                "['basin', 'targeted']",
            ),
            Validation(
                "geometry_frame_counts",
                all(
                    len(frames) == 9
                    for frames in (
                        inputs.dft_frames,
                        inputs.targeted_frames,
                        inputs.basin_frames,
                    )
                ),
                str(
                    [
                        len(inputs.dft_frames),
                        len(inputs.targeted_frames),
                        len(inputs.basin_frames),
                    ]
                ),
                "[9, 9, 9]",
            ),
        ]
    )

    for series in SERIES_ORDER:
        images = tuple(parse_int(row["image"], f"{series} image") for row in profiles[series])
        validations.append(
            Validation(
                f"{series}_image_sequence",
                images == EXPECTED_IMAGES,
                str(images),
                str(EXPECTED_IMAGES),
            )
        )

    dft_barrier = max(
        parse_float(row["delta_e_from_lower_endpoint_ev"], "DFT barrier")
        for row in profiles["DFT"]
    )
    targeted_barrier = max(
        parse_float(
            row["delta_e_from_lower_endpoint_ev"],
            "targeted barrier",
        )
        for row in profiles["targeted"]
    )
    barrier_abs_error_mev = 1000.0 * abs(dft_barrier - targeted_barrier)

    validations.extend(
        [
            Validation(
                "dft_barrier_locked",
                close(dft_barrier, EXPECTED_METRICS["dft_barrier_ev"]),
                f"{dft_barrier:.16g}",
                f"{EXPECTED_METRICS['dft_barrier_ev']:.16g}",
            ),
            Validation(
                "targeted_relaxed_barrier_locked",
                close(
                    targeted_barrier,
                    EXPECTED_METRICS["targeted_barrier_ev"],
                ),
                f"{targeted_barrier:.16g}",
                f"{EXPECTED_METRICS['targeted_barrier_ev']:.16g}",
            ),
            Validation(
                "targeted_relaxed_barrier_error_locked",
                close(
                    barrier_abs_error_mev,
                    EXPECTED_METRICS["targeted_barrier_abs_error_mev"],
                ),
                f"{barrier_abs_error_mev:.12g}",
                f"{EXPECTED_METRICS['targeted_barrier_abs_error_mev']:.12g}",
            ),
        ]
    )

    targeted = classes["targeted"]
    basin = classes["basin"]
    targeted_checks = {
        "classification": (
            targeted["classification"] == "converged_but_high_grade",
            targeted["classification"],
            "converged_but_high_grade",
        ),
        "barrier_valid": (
            parse_bool(targeted["barrier_valid"], "targeted barrier_valid"),
            targeted["barrier_valid"],
            "True",
        ),
        "converged": (
            parse_bool(targeted["converged"], "targeted converged"),
            targeted["converged"],
            "True",
        ),
        "maximum_image": (
            parse_int(targeted["maximum_image"], "targeted maximum_image")
            == EXPECTED_METRICS["targeted_maximum_image"],
            targeted["maximum_image"],
            str(EXPECTED_METRICS["targeted_maximum_image"]),
        ),
    }
    for name, (passed, observed, expected) in targeted_checks.items():
        validations.append(
            Validation(f"targeted_{name}", passed, str(observed), str(expected))
        )

    basin_checks = {
        "classification": (
            basin["classification"] == "invalid_geometry_collapse",
            basin["classification"],
            "invalid_geometry_collapse",
        ),
        "barrier_invalid": (
            not parse_bool(basin["barrier_valid"], "basin barrier_valid"),
            basin["barrier_valid"],
            "False",
        ),
        "not_converged": (
            not parse_bool(basin["converged"], "basin converged"),
            basin["converged"],
            "False",
        ),
        "guard_reason": (
            basin["guard_reason"] == "image5:roo<=1.800",
            basin["guard_reason"],
            "image5:roo<=1.800",
        ),
        "reported_barrier_blank": (
            not basin["reported_lower_endpoint_barrier_ev"].strip(),
            basin["reported_lower_endpoint_barrier_ev"],
            "blank",
        ),
    }
    for name, (passed, observed, expected) in basin_checks.items():
        validations.append(
            Validation(f"basin_{name}", passed, str(observed), str(expected))
        )

    numeric_classification_checks = {
        "targeted_maximum_neb_force_ev_ang": (
            targeted,
            "maximum_neb_force_ev_ang",
            EXPECTED_METRICS["targeted_maximum_neb_force_ev_ang"],
        ),
        "targeted_maximum_rmsd_ang": (
            targeted,
            "maximum_mass_weighted_rmsd_from_dft_image_ang",
            EXPECTED_METRICS["targeted_maximum_rmsd_ang"],
        ),
        "targeted_grade_median": (
            targeted,
            "grade_median",
            EXPECTED_METRICS["targeted_grade_median"],
        ),
        "targeted_grade_max": (
            targeted,
            "grade_max",
            EXPECTED_METRICS["targeted_grade_max"],
        ),
        "basin_minimum_relative_energy_ev": (
            basin,
            "minimum_relative_energy_from_left_ev",
            EXPECTED_METRICS["basin_minimum_relative_energy_ev"],
        ),
        "basin_minimum_roo_ang": (
            basin,
            "minimum_roo_ang",
            EXPECTED_METRICS["basin_minimum_roo_ang"],
        ),
        "basin_minimum_pair_ang": (
            basin,
            "minimum_pair_ang",
            EXPECTED_METRICS["basin_minimum_pair_ang"],
        ),
        "basin_maximum_neb_force_ev_ang": (
            basin,
            "maximum_neb_force_ev_ang",
            EXPECTED_METRICS["basin_maximum_neb_force_ev_ang"],
        ),
        "basin_grade_median": (
            basin,
            "grade_median",
            EXPECTED_METRICS["basin_grade_median"],
        ),
        "basin_grade_max": (
            basin,
            "grade_max",
            EXPECTED_METRICS["basin_grade_max"],
        ),
    }
    for name, (row, field, expected) in numeric_classification_checks.items():
        observed = parse_float(row[field], name)
        validations.append(
            Validation(
                name,
                close(observed, expected),
                f"{observed:.16g}",
                f"{expected:.16g}",
            )
        )

    frame_sets = {
        "DFT": inputs.dft_frames,
        "targeted": inputs.targeted_frames,
        "basin": inputs.basin_frames,
    }
    for series in SERIES_ORDER:
        for row, frame in zip(profiles[series], frame_sets[series]):
            image = parse_int(row["image"], f"{series} image")
            qpt, roo = frame_qpt_roo(frame)
            expected_qpt = parse_float(
                row["qpt_ang"], f"{series} qPT image {image}"
            )
            validations.append(
                Validation(
                    f"{series}_image{image}_geometry_qpt",
                    abs(qpt - expected_qpt) <= GEOMETRY_TOLERANCE_ANG,
                    f"{qpt:.12g}",
                    f"{expected_qpt:.12g} ± {GEOMETRY_TOLERANCE_ANG}",
                )
            )
            expected_roo = parse_optional_float(
                row["roo_ang"], f"{series} R_OO image {image}"
            )
            if expected_roo is not None:
                validations.append(
                    Validation(
                        f"{series}_image{image}_geometry_roo",
                        abs(roo - expected_roo) <= GEOMETRY_TOLERANCE_ANG,
                        f"{roo:.12g}",
                        f"{expected_roo:.12g} ± {GEOMETRY_TOLERANCE_ANG}",
                    )
                )

    failures = [
        validation for validation in validations
        if validation.severity == "ERROR" and not validation.passed
    ]
    if failures:
        raise FigureAuditError(
            "Figure 4 input validation failed: "
            + "; ".join(
                f"{item.check}: {item.observed} != {item.expected}"
                for item in failures
            )
        )
    return validations


def import_plotting() -> tuple[Any, Any, Any]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
        import numpy as np
    except Exception as exc:
        raise FigureAuditError(
            "Matplotlib and NumPy are required: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return matplotlib, plt, ticker, np


def configure_matplotlib(
    matplotlib: Any,
    style: Mapping[str, Any],
) -> None:
    palette = style["palette"]
    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "DejaVu Sans",
                "Arial",
                "Helvetica",
                "Liberation Sans",
            ],
            "font.size": 8.2,
            "axes.labelsize": 8.2,
            "axes.titlesize": 8.8,
            "xtick.labelsize": 7.3,
            "ytick.labelsize": 7.3,
            "legend.fontsize": 7.0,
            "axes.linewidth": 0.8,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.facecolor": palette["background"],
            "figure.facecolor": palette["background"],
        }
    )


def add_panel_label(axis: Any, label: str) -> Any:
    return axis.text(
        -0.105,
        1.025,
        label,
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=10.2,
        fontweight="bold",
        clip_on=False,
    )


def clean_axis(axis: Any, *, grid_axis: str = "y") -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(direction="out")
    axis.grid(axis=grid_axis, linewidth=0.45, alpha=0.22, zorder=0)


def text_bbox_overlap(
    bbox_a: Any,
    bbox_b: Any,
    minimum_area_pixels: float = 6.0,
) -> bool:
    x0 = max(bbox_a.x0, bbox_b.x0)
    y0 = max(bbox_a.y0, bbox_b.y0)
    x1 = min(bbox_a.x1, bbox_b.x1)
    y1 = min(bbox_a.y1, bbox_b.y1)
    return (
        x1 > x0
        and y1 > y0
        and (x1 - x0) * (y1 - y0) > minimum_area_pixels
    )


def validate_tracked_text_layout(
    figure: Any,
    tracked: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    figure_box = figure.bbox
    bboxes: list[tuple[str, Any]] = []
    outside: list[str] = []
    for label, artist in tracked:
        bbox = artist.get_window_extent(renderer=renderer)
        bboxes.append((label, bbox))
        if (
            bbox.x0 < figure_box.x0 - 1
            or bbox.y0 < figure_box.y0 - 1
            or bbox.x1 > figure_box.x1 + 1
            or bbox.y1 > figure_box.y1 + 1
        ):
            outside.append(label)

    overlaps: list[str] = []
    for index, (label_a, bbox_a) in enumerate(bboxes):
        for label_b, bbox_b in bboxes[index + 1:]:
            if text_bbox_overlap(bbox_a, bbox_b):
                overlaps.append(f"{label_a}<->{label_b}")

    if outside or overlaps:
        raise FigureAuditError(
            "Tracked-text layout validation failed: "
            f"outside={outside}; overlaps={overlaps}"
        )
    return {
        "tracked_text_count": len(tracked),
        "outside_canvas_count": len(outside),
        "overlap_count": len(overlaps),
    }


def render_figure(
    inputs: LockedInputs,
    output_base: Path,
) -> dict[str, Any]:
    matplotlib, plt, ticker, np = import_plotting()
    configure_matplotlib(matplotlib, inputs.style)
    palette = inputs.style["palette"]

    profiles = profile_by_series(inputs.profile_rows)
    classes = classification_by_branch(inputs.classification_rows)
    dft_color = palette["dft_reference"]
    targeted_color = palette["targeted_model"]
    basin_color = palette["basin_model"]
    transition_fill = palette["transition_region_fill"]
    background = palette["background"]

    geometry_paths: dict[str, list[tuple[float, float]]] = {}
    for series, frames in (
        ("DFT", inputs.dft_frames),
        ("targeted", inputs.targeted_frames),
        ("basin", inputs.basin_frames),
    ):
        geometry_paths[series] = [frame_qpt_roo(frame) for frame in frames]

    dft_barrier_mev = 1000.0 * max(
        parse_float(row["delta_e_from_lower_endpoint_ev"], "DFT barrier")
        for row in profiles["DFT"]
    )
    targeted_barrier_mev = 1000.0 * max(
        parse_float(
            row["delta_e_from_lower_endpoint_ev"],
            "targeted barrier",
        )
        for row in profiles["targeted"]
    )
    targeted_barrier_error_mev = abs(dft_barrier_mev - targeted_barrier_mev)

    targeted_class = classes["targeted"]
    basin_class = classes["basin"]

    figure = plt.figure(figsize=(9.20, 5.85), constrained_layout=False)
    grid = figure.add_gridspec(
        1,
        2,
        left=0.078,
        right=0.988,
        bottom=0.225,
        top=0.925,
        wspace=0.43,
        width_ratios=[1.30, 1.00],
    )
    ax_a = figure.add_subplot(grid[0, 0])
    ax_b = figure.add_subplot(grid[0, 1])
    tracked: list[tuple[str, Any]] = []

    # ------------------------------------------------------------------
    # a. DFT versus targeted relaxed energy profile.
    # ------------------------------------------------------------------
    ax_a.axvspan(
        -0.15,
        0.15,
        facecolor=transition_fill,
        edgecolor="none",
        alpha=0.82,
        zorder=0,
    )
    for series, label, color, marker in (
        ("DFT", "Frozen DFT NEB9", dft_color, "o"),
        ("targeted", "Targeted relaxed MTP-NEB", targeted_color, "s"),
    ):
        qpt = np.array(
            [parse_float(row["qpt_ang"], f"{series} qPT") for row in profiles[series]]
        )
        energy = np.array(
            [
                1000.0
                * parse_float(
                    row["delta_e_from_lower_endpoint_ev"],
                    f"{series} energy",
                )
                for row in profiles[series]
            ]
        )
        ax_a.plot(
            qpt,
            energy,
            color=color,
            linewidth=2.05,
            marker=marker,
            markersize=4.6,
            markerfacecolor="white" if series == "DFT" else color,
            markeredgecolor=color,
            markeredgewidth=1.0,
            label=label,
            zorder=3 if series == "DFT" else 2,
        )

    ax_a.set_xlim(-0.53, 0.53)
    ax_a.set_ylim(-1.4, 40.8)
    ax_a.xaxis.set_major_locator(ticker.MultipleLocator(0.25))
    ax_a.yaxis.set_major_locator(ticker.MultipleLocator(8))
    ax_a.set_xlabel(
        r"Proton-transfer coordinate, $q_{\mathrm{PT}}$ ($\mathrm{\AA}$)"
    )
    ax_a.set_ylabel("Relative energy (meV)")
    title_a = ax_a.set_title(
        "Targeted relaxation preserves a central barrier",
        loc="left",
        x=0.025,
        pad=11,
    )
    tracked.append(("a_title", title_a))
    panel_a = add_panel_label(ax_a, "a")
    tracked.append(("a_panel_label", panel_a))
    clean_axis(ax_a)
    ax_a.grid(axis="x", visible=False)

    legend_a = ax_a.legend(
        loc="upper left",
        frameon=False,
        borderaxespad=0.28,
        handlelength=2.4,
        labelspacing=0.45,
    )
    tracked.append(("a_legend", legend_a))

    tracked.append(
        (
            "a_barrier_box",
            ax_a.text(
                0.975,
                0.955,
                f"DFT barrier: {dft_barrier_mev:.2f} meV\n"
                f"Targeted relaxed: {targeted_barrier_mev:.2f} meV\n"
                f"Absolute error: {targeted_barrier_error_mev:.2f} meV",
                transform=ax_a.transAxes,
                ha="right",
                va="top",
                fontsize=6.9,
                linespacing=1.30,
                bbox={
                    "facecolor": "white",
                    "edgecolor": "#BBBBBB",
                    "linewidth": 0.5,
                    "boxstyle": "round,pad=0.38",
                    "alpha": 0.93,
                },
            ),
        )
    )
    tracked.append(
        (
            "a_high_grade_warning",
            ax_a.text(
                0.50,
                0.055,
                "Converged, but strongly extrapolative: "
                f"grade median/max = "
                f"{parse_float(targeted_class['grade_median'], 'targeted grade median'):.0f}/"
                f"{parse_float(targeted_class['grade_max'], 'targeted grade max'):.0f}",
                transform=ax_a.transAxes,
                ha="center",
                va="bottom",
                fontsize=6.6,
                color=basin_color,
                bbox={
                    "facecolor": "white",
                    "edgecolor": "none",
                    "pad": 0.35,
                    "alpha": 0.88,
                },
            ),
        )
    )

    # ------------------------------------------------------------------
    # b. Structural path and basin collapse.
    # ------------------------------------------------------------------
    for series, label, color, marker, linestyle in (
        ("DFT", "Frozen DFT path", dft_color, "o", "-"),
        ("targeted", "Targeted relaxed path", targeted_color, "s", "-"),
        ("basin", "Basin path — invalid", basin_color, "^", "--"),
    ):
        qpt = [pair[0] for pair in geometry_paths[series]]
        roo = [pair[1] for pair in geometry_paths[series]]
        ax_b.plot(
            qpt,
            roo,
            color=color,
            linewidth=2.0 if series != "basin" else 1.8,
            linestyle=linestyle,
            marker=marker,
            markersize=4.8,
            markerfacecolor=(
                "white" if series == "DFT" else color
            ),
            markeredgecolor=color,
            markeredgewidth=1.0,
            label=label,
            zorder={"DFT": 4, "targeted": 3, "basin": 2}[series],
        )

    ax_b.axhline(
        GEOMETRY_GUARD_ROO_ANG,
        color=basin_color,
        linestyle=":",
        linewidth=1.05,
        zorder=0,
    )
    collapse_index = min(
        range(len(geometry_paths["basin"])),
        key=lambda index: geometry_paths["basin"][index][1],
    )
    collapse_qpt, collapse_roo = geometry_paths["basin"][collapse_index]
    ax_b.scatter(
        [collapse_qpt],
        [collapse_roo],
        s=78,
        marker="X",
        facecolor=basin_color,
        edgecolor=basin_color,
        linewidth=1.0,
        zorder=6,
    )
    tracked.append(
        (
            "b_guard_label",
            ax_b.text(
                0.975,
                0.105,
                r"geometry guard: $R_{\mathrm{OO}}=1.800$ $\mathrm{\AA}$",
                transform=ax_b.transAxes,
                ha="right",
                va="bottom",
                fontsize=6.3,
                color=basin_color,
                bbox={
                    "facecolor": "white",
                    "edgecolor": "none",
                    "pad": 0.28,
                    "alpha": 0.88,
                },
            ),
        )
    )
    tracked.append(
        (
            "b_collapse_callout",
            ax_b.annotate(
                "INVALID basin collapse\n"
                fr"$R_{{\mathrm{{OO}}}}={collapse_roo:.3f}$ Å" "\n"
                f"false minimum = {parse_float(basin_class['minimum_relative_energy_from_left_ev'], 'basin minimum energy'):.3f} eV",
                xy=(collapse_qpt, collapse_roo),
                xycoords="data",
                xytext=(0.055, 0.285),
                textcoords=ax_b.transAxes,
                ha="left",
                va="bottom",
                fontsize=6.5,
                linespacing=1.22,
                color=basin_color,
                arrowprops={
                    "arrowstyle": "->",
                    "color": basin_color,
                    "linewidth": 0.9,
                },
                bbox={
                    "facecolor": "white",
                    "edgecolor": basin_color,
                    "linewidth": 0.55,
                    "boxstyle": "round,pad=0.32",
                    "alpha": 0.92,
                },
            ),
        )
    )
    tracked.append(
        (
            "b_targeted_callout",
            ax_b.text(
                0.975,
                0.565,
                "Targeted path\n"
                f"max force = "
                f"{parse_float(targeted_class['maximum_neb_force_ev_ang'], 'targeted max force'):.4f} eV Å⁻¹\n"
                f"max RMSD from DFT = "
                f"{parse_float(targeted_class['maximum_mass_weighted_rmsd_from_dft_image_ang'], 'targeted max RMSD'):.5f} Å",
                transform=ax_b.transAxes,
                ha="right",
                va="top",
                fontsize=6.6,
                linespacing=1.28,
                color=targeted_color,
                bbox={
                    "facecolor": "white",
                    "edgecolor": targeted_color,
                    "linewidth": 0.55,
                    "boxstyle": "round,pad=0.34",
                    "alpha": 0.92,
                },
            ),
        )
    )

    ax_b.set_xlim(-0.53, 0.53)
    ax_b.set_ylim(1.73, 2.68)
    ax_b.xaxis.set_major_locator(ticker.MultipleLocator(0.25))
    ax_b.yaxis.set_major_locator(ticker.MultipleLocator(0.20))
    ax_b.set_xlabel(
        r"Proton-transfer coordinate, $q_{\mathrm{PT}}$ ($\mathrm{\AA}$)"
    )
    ax_b.set_ylabel(r"Oxygen distance, $R_{\mathrm{OO}}$ ($\mathrm{\AA}$)")
    title_b = ax_b.set_title(
        "Structural path validity",
        loc="left",
        x=0.025,
        pad=11,
    )
    tracked.append(("b_title", title_b))
    panel_b = add_panel_label(ax_b, "b")
    tracked.append(("b_panel_label", panel_b))
    clean_axis(ax_b)
    ax_b.grid(axis="x", visible=False)
    legend_b = ax_b.legend(
        loc="upper left",
        bbox_to_anchor=(0.02, 0.975),
        frameon=False,
        borderaxespad=0.20,
        handlelength=2.1,
        labelspacing=0.42,
    )
    tracked.append(("b_legend", legend_b))

    tracked.append(
        (
            "figure_footnote",
            figure.text(
                0.078,
                0.075,
                "Secondary evidence only: the targeted relaxed path is numerically converged but remains strongly extrapolative.\n"
                "The basin path underwent geometry collapse, so no physical optimized barrier is reported.",
                ha="left",
                va="bottom",
                fontsize=6.20,
                color="#444444",
            ),
        )
    )

    tracked.extend(
        [
            ("a_xlabel", ax_a.xaxis.label),
            ("a_ylabel", ax_a.yaxis.label),
            ("b_xlabel", ax_b.xaxis.label),
            ("b_ylabel", ax_b.yaxis.label),
        ]
    )
    layout_validation = validate_tracked_text_layout(figure, tracked)

    output_base.parent.mkdir(parents=True, exist_ok=True)
    outputs = {
        "pdf": output_base.with_suffix(".pdf"),
        "svg": output_base.with_suffix(".svg"),
        "png": output_base.with_suffix(".png"),
        "tiff": output_base.with_suffix(".tiff"),
    }
    for path in outputs.values():
        if path.exists():
            raise FigureAuditError(f"Refusing to overwrite figure: {path}")

    metadata = {
        "Title": "Secondary relaxed MTP-NEB structural diagnostic",
        "Author": "Reproducible project rendering",
        "Subject": "Targeted relaxed barrier and basin geometry collapse",
        "Keywords": "malonaldehyde, MTP, NEB, geometry collapse, MaxVol",
        "Creator": IMPLEMENTATION_ID,
    }
    figure.savefig(
        outputs["pdf"],
        format="pdf",
        bbox_inches="tight",
        pad_inches=0.06,
        metadata=metadata,
    )
    figure.savefig(
        outputs["svg"],
        format="svg",
        bbox_inches="tight",
        pad_inches=0.06,
        metadata={
            "Title": metadata["Title"],
            "Description": metadata["Subject"],
        },
    )
    figure.savefig(
        outputs["png"],
        format="png",
        dpi=600,
        bbox_inches="tight",
        pad_inches=0.06,
        metadata={
            "Title": metadata["Title"],
            "Description": metadata["Subject"],
        },
    )
    figure.savefig(
        outputs["tiff"],
        format="tiff",
        dpi=600,
        bbox_inches="tight",
        pad_inches=0.06,
        pil_kwargs={"compression": "tiff_lzw"},
    )
    plt.close(figure)

    return {
        "outputs": {key: str(value) for key, value in outputs.items()},
        "dft_barrier_mev": dft_barrier_mev,
        "targeted_relaxed_barrier_mev": targeted_barrier_mev,
        "targeted_relaxed_barrier_abs_error_mev":
            targeted_barrier_error_mev,
        "targeted_maximum_image": parse_int(
            targeted_class["maximum_image"], "targeted maximum image"
        ),
        "targeted_grade_median": parse_float(
            targeted_class["grade_median"], "targeted grade median"
        ),
        "targeted_grade_max": parse_float(
            targeted_class["grade_max"], "targeted grade max"
        ),
        "basin_minimum_roo_ang": collapse_roo,
        "basin_minimum_relative_energy_ev": parse_float(
            basin_class["minimum_relative_energy_from_left_ev"],
            "basin minimum relative energy",
        ),
        "basin_maximum_neb_force_ev_ang": parse_float(
            basin_class["maximum_neb_force_ev_ang"],
            "basin maximum NEB force",
        ),
        "basin_grade_max": parse_float(
            basin_class["grade_max"], "basin grade max"
        ),
        "layout_validation": layout_validation,
        "scientific_execution": "NONE",
    }


def verify_rendered_files(
    output_paths: Mapping[str, Path],
) -> list[Validation]:
    validations: list[Validation] = []
    for key, path in output_paths.items():
        path = require_file(path, f"{key} figure")
        validations.append(
            Validation(
                f"{key}_file_nonempty",
                path.stat().st_size > 1000,
                str(path.stat().st_size),
                "> 1000 bytes",
            )
        )

    pdf = output_paths["pdf"]
    validations.append(
        Validation(
            "pdf_signature",
            pdf.read_bytes()[:5] == b"%PDF-",
            repr(pdf.read_bytes()[:5]),
            "b'%PDF-'",
        )
    )
    svg_text = output_paths["svg"].read_text(encoding="utf-8")
    validations.append(
        Validation(
            "svg_structure",
            "<svg" in svg_text and "</svg>" in svg_text,
            f"open={'<svg' in svg_text}; close={'</svg>' in svg_text}",
            "both True",
        )
    )

    try:
        from PIL import Image
        for key in ("png", "tiff"):
            with Image.open(output_paths[key]) as image:
                width, height = image.size
                validations.extend(
                    [
                        Validation(
                            f"{key}_dimensions",
                            width >= 4200 and height >= 2800,
                            f"{width}x{height}",
                            "at least 4200x2800 pixels",
                        ),
                        Validation(
                            f"{key}_mode",
                            image.mode in {"RGB", "RGBA"},
                            image.mode,
                            "RGB or RGBA",
                        ),
                    ]
                )
    except Exception as exc:
        raise FigureAuditError(
            f"Pillow verification failed: {type(exc).__name__}: {exc}"
        ) from exc

    failures = [item for item in validations if not item.passed]
    if failures:
        raise FigureAuditError(
            "Rendered-file validation failed: "
            + "; ".join(
                f"{item.check}={item.observed}" for item in failures
            )
        )
    return validations


def create_output_attempt(root: Path) -> tuple[Path, Path]:
    version_root = (root / OUTPUT_RELATIVE_ROOT).resolve()
    version_root.mkdir(parents=True, exist_ok=True)
    attempt = version_root / f"attempt_{utc_stamp()}"
    if attempt.exists():
        raise FigureAuditError(f"Output attempt exists: {attempt}")
    attempt.mkdir(parents=False, exist_ok=False)
    return version_root, attempt


def snapshot_inputs(
    inputs: LockedInputs,
    attempt: Path,
) -> dict[str, Path]:
    snapshot_dir = attempt / "source_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    outputs: dict[str, Path] = {}
    for relative in (
        PROFILE_FILE,
        CLASSIFICATION_FILE,
        DFT_GEOMETRY_FILE,
        TARGETED_GEOMETRY_FILE,
        BASIN_GEOMETRY_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    ):
        source = inputs.attempt / relative
        destination = snapshot_dir / relative.replace("/", "__")
        shutil.copy2(source, destination)
        outputs[relative] = destination
    return outputs


def build_panel_values(
    inputs: LockedInputs,
) -> list[dict[str, Any]]:
    profiles = profile_by_series(inputs.profile_rows)
    frame_map = {
        "DFT": inputs.dft_frames,
        "targeted": inputs.targeted_frames,
        "basin": inputs.basin_frames,
    }
    rows: list[dict[str, Any]] = []
    for series in SERIES_ORDER:
        for profile, frame in zip(profiles[series], frame_map[series]):
            qpt_geometry, roo_geometry = frame_qpt_roo(frame)
            rows.append(
                {
                    "series": series,
                    "image": parse_int(profile["image"], "image"),
                    "qpt_profile_ang": parse_float(
                        profile["qpt_ang"], "qPT"
                    ),
                    "qpt_geometry_ang": qpt_geometry,
                    "roo_geometry_ang": roo_geometry,
                    "relative_energy_mev": 1000.0 * parse_float(
                        profile["delta_e_from_lower_endpoint_ev"],
                        "relative energy",
                    ),
                    "classification": profile["classification"],
                    "plot_role": profile.get("plot_role", ""),
                }
            )
    return rows


def write_caption(
    path: Path,
    figure_data: Mapping[str, Any],
) -> None:
    caption = f"""# Figure 4. Targeted relaxed MTP-NEB remains structurally plausible, whereas the basin path collapses

**a,** Frozen independent PBE NEB9 profile and the targeted relaxed MTP-NEB
profile. The targeted optimized path retains a central maximum at image
{figure_data["targeted_maximum_image"]}, with a lower-endpoint barrier of
{figure_data["targeted_relaxed_barrier_mev"]:.2f} meV versus
{figure_data["dft_barrier_mev"]:.2f} meV for PBE; the absolute barrier error is
{figure_data["targeted_relaxed_barrier_abs_error_mev"]:.2f} meV.
**b,** Structural paths in proton-transfer coordinate and oxygen-oxygen
distance. The targeted path remains close to the DFT path, whereas the
basin-trained model crosses the geometry guard and collapses to
R_OO = {figure_data["basin_minimum_roo_ang"]:.3f} Å, accompanied by a false
deep minimum of {figure_data["basin_minimum_relative_energy_ev"]:.3f} eV.

The targeted relaxed path is secondary evidence only because its median and
maximum MaxVol grades remain {figure_data["targeted_grade_median"]:.0f} and
{figure_data["targeted_grade_max"]:.0f}, respectively. The basin path is an
invalid geometry-collapse diagnostic and is not assigned a physically
meaningful optimized barrier.
"""
    atomic_write_text(path, caption)


def write_report(
    path: Path,
    inputs: LockedInputs,
    validations: Sequence[Validation],
    figure_data: Mapping[str, Any],
    output_paths: Mapping[str, Path],
) -> None:
    report = f"""# Figure 4 secondary MTP-NEB render report v014

Created UTC: `{utc_iso()}`

Status: `{STATUS_PASS}`

## Scope

This stage rendered the secondary relaxed MTP-NEB diagnostic from the completed
v005 source package. It did not execute DFT, an NEB engine, model loading,
training, `mlp`, LAMMPS, or molecular dynamics.

## Locked input

- v005 attempt: `{inputs.attempt}`
- normalized profiles: `{inputs.profile_path}`
- normalized classifications: `{inputs.classification_path}`
- DFT NEB9 geometry: `{inputs.dft_geometry_path}`
- targeted relaxed geometry: `{inputs.targeted_geometry_path}`
- basin invalid geometry: `{inputs.basin_geometry_path}`

Every source was verified against `checksums_v005.tsv`.

## Main numerical results

- DFT lower-endpoint barrier: `{figure_data["dft_barrier_mev"]:.9f}` meV
- targeted relaxed barrier:
  `{figure_data["targeted_relaxed_barrier_mev"]:.9f}` meV
- targeted relaxed absolute barrier error:
  `{figure_data["targeted_relaxed_barrier_abs_error_mev"]:.9f}` meV
- targeted median/max grade:
  `{figure_data["targeted_grade_median"]:.6f}` /
  `{figure_data["targeted_grade_max"]:.6f}`
- basin minimum R_OO: `{figure_data["basin_minimum_roo_ang"]:.12f}` Å
- basin false minimum:
  `{figure_data["basin_minimum_relative_energy_ev"]:.12f}` eV
- basin maximum NEB force:
  `{figure_data["basin_maximum_neb_force_ev_ang"]:.12f}` eV/Å
- basin maximum grade: `{figure_data["basin_grade_max"]:.6f}`

## Interpretation

The targeted optimized path is numerically converged and structurally close to
the DFT path, but it remains strongly extrapolative and therefore provides
secondary evidence only. The basin-trained model undergoes a catastrophic
central geometry collapse and does not provide a physically meaningful
optimized barrier.

## Layout validation

Tracked artists:
`{figure_data["layout_validation"]["tracked_text_count"]}`

Detected tracked-text overlaps:
`{figure_data["layout_validation"]["overlap_count"]}`

Tracked artists outside canvas:
`{figure_data["layout_validation"]["outside_canvas_count"]}`

## Rendered outputs

- PDF: `{output_paths["pdf"]}`
- SVG: `{output_paths["svg"]}`
- PNG: `{output_paths["png"]}`
- TIFF: `{output_paths["tiff"]}`

## Validation

Passed checks: `{sum(item.passed for item in validations)}`

Failed checks: `{sum(not item.passed for item in validations)}`
"""
    atomic_write_text(path, report)


def validation_rows(
    validations: Sequence[Validation],
) -> list[dict[str, Any]]:
    return [dataclasses.asdict(validation) for validation in validations]


def write_checksums(attempt: Path) -> Path:
    path = attempt / "checksums_v014.tsv"
    rows: list[dict[str, Any]] = []
    for candidate in sorted(attempt.rglob("*")):
        if not candidate.is_file() or candidate == path:
            continue
        rows.append(
            {
                "relative_path": str(candidate.relative_to(attempt)),
                "size_bytes": candidate.stat().st_size,
                "sha256": sha256_file(candidate),
            }
        )
    atomic_write_tsv(
        path,
        ["relative_path", "size_bytes", "sha256"],
        rows,
    )
    return path


def update_pointer(
    version_root: Path,
    attempt: Path,
) -> Path:
    pointer = version_root / OUTPUT_POINTER
    temporary = version_root / f".{OUTPUT_POINTER}.tmp.{os.getpid()}"
    temporary.write_text(str(attempt.resolve()) + "\n", encoding="utf-8")
    os.replace(temporary, pointer)
    return pointer


def run(root: Path, validate_only: bool = False) -> int:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FigureAuditError(f"Project root is not a directory: {root}")

    inputs = load_locked_inputs(root)
    validations = validate_inputs(inputs)

    if validate_only:
        print("VALIDATE_ONLY=PASS")
        print(f"INPUT_ATTEMPT={inputs.attempt}")
        print(f"PROFILE_ROWS={len(inputs.profile_rows)}")
        print(f"CLASSIFICATION_ROWS={len(inputs.classification_rows)}")
        print(
            "GEOMETRY_FRAMES="
            f"{len(inputs.dft_frames)},"
            f"{len(inputs.targeted_frames)},"
            f"{len(inputs.basin_frames)}"
        )
        print(f"VALIDATION_CHECKS={len(validations)}")
        print("SCIENTIFIC_EXECUTION=NONE")
        return 0

    version_root, attempt = create_output_attempt(root)
    try:
        figures_dir = attempt / "figures"
        reports_dir = attempt / "reports"
        source_data_dir = attempt / "source_data"
        figures_dir.mkdir(parents=True, exist_ok=False)
        reports_dir.mkdir(parents=True, exist_ok=False)
        source_data_dir.mkdir(parents=True, exist_ok=False)

        snapshot_paths = snapshot_inputs(inputs, attempt)
        output_base = figures_dir / "figure04_secondary_mtp_neb_v014"
        figure_data = render_figure(inputs, output_base)
        output_paths = {
            key: Path(value) for key, value in figure_data["outputs"].items()
        }
        validations.extend(verify_rendered_files(output_paths))

        panel_values = build_panel_values(inputs)
        panel_values_path = (
            source_data_dir / "figure04_panel_values_v014.tsv"
        )
        atomic_write_tsv(
            panel_values_path,
            list(panel_values[0].keys()),
            panel_values,
        )

        validation_path = reports_dir / "figure04_validation_v014.tsv"
        atomic_write_tsv(
            validation_path,
            ["check", "passed", "observed", "expected", "severity"],
            validation_rows(validations),
        )

        caption_path = attempt / "figure04_caption_v014.md"
        write_caption(caption_path, figure_data)

        report_path = reports_dir / "figure04_render_report_v014.md"
        write_report(
            report_path,
            inputs,
            validations,
            figure_data,
            output_paths,
        )

        data_lock = {
            "schema_version": "1.0",
            "created_utc": utc_iso(),
            "implementation": IMPLEMENTATION_ID,
            "input_attempt": str(inputs.attempt),
            "input_status": EXPECTED_INPUT_STATUS,
            "source_hashes": inputs.source_hashes,
            "figure_manifest_row": inputs.figure_manifest_row,
            "expected_metrics": EXPECTED_METRICS,
            "geometry_guard_roo_ang": GEOMETRY_GUARD_ROO_ANG,
            "scientific_execution": {
                "dft": False,
                "neb_engine": False,
                "model_loading": False,
                "training": False,
                "mlp": False,
                "lammps": False,
                "md": False,
            },
        }
        data_lock_path = attempt / "figure04_data_lock_v014.json"
        atomic_write_json(data_lock_path, data_lock)

        manifest_rows = [
            {
                "artifact_id": "Figure_4",
                "role": "secondary_mtp_neb_structural_diagnostic",
                "pdf": str(output_paths["pdf"].relative_to(attempt)),
                "svg": str(output_paths["svg"].relative_to(attempt)),
                "png": str(output_paths["png"].relative_to(attempt)),
                "tiff": str(output_paths["tiff"].relative_to(attempt)),
                "caption": str(caption_path.relative_to(attempt)),
                "status": "RENDERED_AND_VALIDATED",
                "scientific_message": inputs.figure_manifest_row[
                    "scientific_message"
                ],
                "mandatory_caveat": inputs.figure_manifest_row[
                    "mandatory_caveat"
                ],
            }
        ]
        manifest_path = attempt / "figure04_manifest_v014.tsv"
        atomic_write_tsv(
            manifest_path,
            list(manifest_rows[0].keys()),
            manifest_rows,
        )

        summary = {
            "schema_version": "1.0",
            "created_utc": utc_iso(),
            "implementation": IMPLEMENTATION_ID,
            "status": STATUS_PASS,
            "input_attempt": str(inputs.attempt),
            "output_attempt": str(attempt),
            "figure_data": figure_data,
            "outputs": {
                "manifest": str(manifest_path),
                "caption": str(caption_path),
                "report": str(report_path),
                "validation": str(validation_path),
                "data_lock": str(data_lock_path),
                "panel_values": str(panel_values_path),
                "source_snapshot": {
                    key: str(value) for key, value in snapshot_paths.items()
                },
            },
            "scientific_claim": (
                "The targeted relaxed MTP-NEB path is geometrically plausible "
                "and retains a central barrier, whereas the basin-trained path "
                "undergoes invalid geometry collapse."
            ),
            "mandatory_caveat": (
                "The targeted optimized path remains strongly extrapolative "
                "and is secondary evidence only."
            ),
            "next_stage": (
                "Render Figure 1 equal-budget design and coverage workflow."
            ),
        }
        summary_path = attempt / "summary_v014.json"
        atomic_write_json(summary_path, summary)

        atomic_write_text(attempt / "STATUS_v014.txt", STATUS_PASS + "\n")
        checksums_path = write_checksums(attempt)
        pointer_path = update_pointer(version_root, attempt)

        print(STATUS_PASS)
        print(f"RUN_DIR={attempt}")
        print(f"PDF={output_paths['pdf']}")
        print(f"SVG={output_paths['svg']}")
        print(f"PNG={output_paths['png']}")
        print(f"TIFF={output_paths['tiff']}")
        print(f"CAPTION={caption_path}")
        print(f"REPORT={report_path}")
        print(f"VALIDATION={validation_path}")
        print(f"SUMMARY={summary_path}")
        print(f"CHECKSUMS={checksums_path}")
        print(f"CURRENT_POINTER={pointer_path}")
        print("SCIENTIFIC_EXECUTION=NONE")
        return 0
    except Exception:
        failure_path = attempt / "STATUS_v014.txt"
        if not failure_path.exists():
            failure_path.write_text(STATUS_FAIL + "\n", encoding="utf-8")
        raise


PROFILE_HEADER = [
    "series",
    "image",
    "qpt_ang",
    "energy_ev",
    "delta_e_from_left_ev",
    "delta_e_from_lower_endpoint_ev",
    "roo_ang",
    "minimum_pair_ang",
    "mass_weighted_rmsd_from_dft_image_ang",
    "classification",
    "delta_e_from_left_mev",
    "delta_e_from_lower_endpoint_mev",
    "plot_role",
]

EXACT_PROFILE_ROWS = [
    ("DFT",1,-0.483891404936579,-1949.728382132342,0.0,0.000107348919073047,"","",0.0,"reference"),
    ("DFT",2,-0.3880116402035043,-1949.724562470055,0.00381966228701458,0.003927011206087627,"","",0.0,"reference"),
    ("DFT",3,-0.26005757218361825,-1949.711683320944,0.016698811397873214,0.01680616031694626,"","",0.0,"reference"),
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
]


def synthetic_geometry_frame(
    qpt: float,
    roo: float,
    comment: str,
) -> XYZFrame:
    oxygen_left = (-roo / 2.0, 0.0, 0.0)
    oxygen_right = (roo / 2.0, 0.0, 0.0)
    proton = (qpt / 2.0, 0.0, 0.0)
    positions = (
        oxygen_left,
        proton,
        (-1.4, 0.8, 0.0),
        (-1.9, 1.2, 0.1),
        (0.0, 1.3, 0.0),
        (0.0, 2.0, 0.1),
        (1.4, 0.8, 0.0),
        oxygen_right,
        (1.9, 1.2, -0.1),
    )
    return XYZFrame(
        elements=EXPECTED_ATOM_SEQUENCE,
        positions=positions,
        comment=comment,
    )


def write_xyz(path: Path, frames: Sequence[XYZFrame]) -> None:
    chunks: list[str] = []
    for frame in frames:
        chunks.append(str(len(frame.elements)))
        chunks.append(frame.comment)
        for element, position in zip(frame.elements, frame.positions):
            chunks.append(
                f"{element} "
                f"{position[0]:.16f} "
                f"{position[1]:.16f} "
                f"{position[2]:.16f}"
            )
    atomic_write_text(path, "\n".join(chunks) + "\n")


def make_synthetic_fixture(root: Path) -> Path:
    attempt = root / INPUT_RELATIVE_ROOT / "attempt_20990101T000000Z"
    (attempt / "source_data").mkdir(parents=True)
    (attempt / "geometry").mkdir(parents=True)

    profile_rows: list[dict[str, Any]] = []
    for row in EXACT_PROFILE_ROWS:
        (
            series,
            image,
            qpt,
            energy,
            delta_left,
            delta_lower,
            roo,
            minimum_pair,
            rmsd,
            classification,
        ) = row
        profile_rows.append(
            {
                "series": series,
                "image": image,
                "qpt_ang": qpt,
                "energy_ev": energy,
                "delta_e_from_left_ev": delta_left,
                "delta_e_from_lower_endpoint_ev": delta_lower,
                "roo_ang": roo,
                "minimum_pair_ang": minimum_pair,
                "mass_weighted_rmsd_from_dft_image_ang": rmsd,
                "classification": classification,
                "delta_e_from_left_mev": 1000.0 * float(delta_left),
                "delta_e_from_lower_endpoint_mev": 1000.0 * float(delta_lower),
                "plot_role": (
                    "reference" if series == "DFT"
                    else "failure_diagnostic" if series == "basin"
                    else "secondary_high_grade_diagnostic"
                ),
            }
        )
    atomic_write_tsv(
        attempt / PROFILE_FILE,
        PROFILE_HEADER,
        profile_rows,
    )

    classification_rows = [
        {
            "branch": "basin",
            "classification": "invalid_geometry_collapse",
            "barrier_valid": False,
            "optimization_status": "geometry_guard_stop",
            "converged": False,
            "maximum_neb_force_ev_ang": 11.442975922160553,
            "guard_reason": "image5:roo<=1.800",
            "minimum_relative_energy_from_left_ev": -5.0962582067941185,
            "minimum_roo_ang": 1.7985316061400438,
            "minimum_pair_ang": 0.9519427449504909,
            "maximum_mass_weighted_rmsd_from_dft_image_ang": 0.2495966907319963,
            "formal_lower_endpoint_barrier_ev": 0.0005612818879399128,
            "reported_lower_endpoint_barrier_ev": "",
            "maximum_image": 8,
            "grade_median": 9207.164193,
            "grade_max": 535658.716794,
            "interpretation": (
                "No physically meaningful optimized barrier: "
                "transition-region geometry collapsed into a false deep minimum."
            ),
        },
        {
            "branch": "targeted",
            "classification": "converged_but_high_grade",
            "barrier_valid": True,
            "optimization_status": "converged",
            "converged": True,
            "maximum_neb_force_ev_ang": 0.02664574947856421,
            "guard_reason": "",
            "minimum_relative_energy_from_left_ev": -9.319589935330441e-07,
            "minimum_roo_ang": 2.3924957584555977,
            "minimum_pair_ang": 1.0443962266868019,
            "maximum_mass_weighted_rmsd_from_dft_image_ang": 0.0023785855552754713,
            "formal_lower_endpoint_barrier_ev": 0.030672292320105043,
            "reported_lower_endpoint_barrier_ev": 0.030672292320105043,
            "maximum_image": 5,
            "grade_median": 5216.319957,
            "grade_max": 12006.843432,
            "interpretation": (
                "Numerically converged central path, but strongly "
                "extrapolative by MaxVol grade."
            ),
        },
    ]
    atomic_write_tsv(
        attempt / CLASSIFICATION_FILE,
        list(classification_rows[0].keys()),
        classification_rows,
    )

    by_series = profile_by_series(
        [{key: str(value) for key, value in row.items()} for row in profile_rows]
    )
    synthetic_dft_roo = [
        2.49924,
        2.45770,
        2.41924,
        2.39920,
        2.39250,
        2.39917,
        2.41919,
        2.45766,
        2.49906,
    ]
    for series, path, dft_roo in (
        ("DFT", attempt / DFT_GEOMETRY_FILE, synthetic_dft_roo),
        ("targeted", attempt / TARGETED_GEOMETRY_FILE, None),
        ("basin", attempt / BASIN_GEOMETRY_FILE, None),
    ):
        frames: list[XYZFrame] = []
        for index, row in enumerate(by_series[series]):
            qpt = parse_float(row["qpt_ang"], "synthetic qPT")
            if dft_roo is None:
                roo = parse_float(row["roo_ang"], "synthetic R_OO")
            else:
                roo = dft_roo[index]
            frames.append(
                synthetic_geometry_frame(qpt, roo, f"{series} image {index + 1}")
            )
        write_xyz(path, frames)

    style = {
        "palette": {
            "dft_reference": "#111111",
            "common_dataset": "#9E9E9E",
            "basin_model": "#D55E00",
            "targeted_model": "#0072B2",
            "audit": "#CC79A7",
            "failure": "#A50026",
            "transition_region_fill": "#E6E6E6",
            "background": "#FFFFFF",
        }
    }
    atomic_write_json(attempt / STYLE_FILE, style)
    manifest = [
        {
            "figure_id": "Figure_4",
            "title": "Secondary MTP-NEB structural diagnostic",
            "panels": (
                "a energy profiles; b qPT-R_OO paths; "
                "c targeted relaxed barrier; d basin collapse"
            ),
            "primary_source_data": (
                "source_data/mtp_neb_paths_v005.tsv; "
                "source_data/mtp_neb_classification_v005.tsv"
            ),
            "geometry_sources": (
                "geometry/mtp_neb_basin_v005.xyz; "
                "geometry/mtp_neb_targeted_v005.xyz; "
                "geometry/dft_independent_neb9_v005.xyz"
            ),
            "status": "SOURCE_DATA_READY",
            "scientific_message": (
                "The targeted path is geometrically plausible and numerically "
                "converged, whereas the basin path collapses."
            ),
            "mandatory_caveat": (
                "The targeted optimized path remains strongly extrapolative "
                "and is secondary evidence only."
            ),
        }
    ]
    atomic_write_tsv(
        attempt / FIGURE_MANIFEST_FILE,
        list(manifest[0].keys()),
        manifest,
    )
    atomic_write_json(attempt / SUMMARY_FILE, {"status": EXPECTED_INPUT_STATUS})
    atomic_write_text(attempt / STATUS_FILE, EXPECTED_INPUT_STATUS + "\n")

    checksum_rows: list[dict[str, Any]] = []
    for relative in (
        PROFILE_FILE,
        CLASSIFICATION_FILE,
        DFT_GEOMETRY_FILE,
        TARGETED_GEOMETRY_FILE,
        BASIN_GEOMETRY_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    ):
        path = attempt / relative
        checksum_rows.append(
            {
                "relative_path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    atomic_write_tsv(
        attempt / CHECKSUM_FILE,
        ["relative_path", "size_bytes", "sha256"],
        checksum_rows,
    )
    version_root = root / INPUT_RELATIVE_ROOT
    atomic_write_text(version_root / INPUT_POINTER, str(attempt) + "\n")
    return attempt


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="figure04_v014_test_") as temp:
        root = Path(temp)
        make_synthetic_fixture(root)
        inputs = load_locked_inputs(root)
        validations = validate_inputs(inputs)
        output_base = root / "synthetic_output" / "figure04"
        figure_data = render_figure(inputs, output_base)
        output_paths = {
            key: Path(value) for key, value in figure_data["outputs"].items()
        }
        validations.extend(verify_rendered_files(output_paths))
        if not all(item.passed for item in validations):
            raise FigureAuditError("Synthetic self-test has failed checks")
        print("SELF_TEST=PASS")
        print(f"VALIDATION_CHECKS={len(validations)}")
        print(
            "LAYOUT_OVERLAPS="
            f"{figure_data['layout_validation']['overlap_count']}"
        )
        print(
            "OUTSIDE_CANVAS="
            f"{figure_data['layout_validation']['outside_canvas_count']}"
        )
        print("FORMATS=PDF,SVG,PNG,TIFF")
        print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render Figure 4 from the completed v005 normalized source package."
        )
    )
    parser.add_argument(
        "--root",
        default="${PROJECT_ROOT}",
        help="Project root",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate locked input without creating an output attempt",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a synthetic renderer regression",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.self_test:
            return self_test()
        return run(Path(arguments.root), validate_only=arguments.validate_only)
    except FigureAuditError as exc:
        print(f"FIGURE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"UNEXPECTED_ERROR: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

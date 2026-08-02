#!/usr/bin/env python3
"""
Supplementary Figure S2 rendering v022
======================================

Render MaxVol applicability-grade distributions and frozen/relaxed path-grade
summaries from the completed visualization Step 01 v005 source package.

No DFT, model loading, training, ``mlp``, LAMMPS, molecular dynamics, NEB
optimization, or new grade calculation is executed.

Authoritative input
-------------------
10_visualization/versions/
v005_q1_dataviz_source_audit_source_oracle_recovery/
CURRENT_VISUAL_SOURCE_AUDIT_V005.txt

Output
------
10_visualization/versions/
v022_supplementary_figure_s2_applicability_grades_spacious/
attempt_<UTC>/

Panels
------
a. Per-configuration frozen-audit MaxVol grades for basin12 and independent
   NEB9 subsets, evaluated by the basin-trained and transition-targeted models.
b. Median and maximum MaxVol-grade summaries for frozen NEB9 and relaxed
   MTP-NEB paths.

Scientific scope
----------------
MaxVol grade is an applicability criterion, not a measured DFT error.
The relaxed-path source package exports median/max summaries, not all nine
per-image relaxed grades; panel b therefore shows summary ranges only.
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
import statistics
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


IMPLEMENTATION_ID = (
    "RENDER_SUPPLEMENTARY_FIGURE_S2_APPLICABILITY_GRADES_V022"
)
OUTPUT_VERSION = "v022_supplementary_figure_s2_applicability_grades_spacious"
EXPECTED_INPUT_STATUS = (
    "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"
)
STATUS_PASS = (
    "PASS_SUPPLEMENTARY_FIGURE_S2_APPLICABILITY_GRADES_RENDERED_V022"
)
STATUS_FAIL = (
    "FAIL_SUPPLEMENTARY_FIGURE_S2_APPLICABILITY_GRADES_V022"
)

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
OUTPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v022_supplementary_figure_s2_applicability_grades_spacious"
)
OUTPUT_POINTER = (
    "CURRENT_SUPPLEMENTARY_FIGURE_S2_APPLICABILITY_GRADES_V022.txt"
)

AUDIT_PER_CONFIGURATION_FILE = (
    "source_data/audit21_per_configuration_metrics_v005.tsv"
)
AUDIT_GRADE_SUMMARY_FILE = "source_data/audit21_grade_metrics_v005.tsv"
MTP_NEB_CLASSIFICATION_FILE = (
    "source_data/mtp_neb_classification_v005.tsv"
)
STYLE_FILE = "visual_style_lock_v005.json"
FIGURE_MANIFEST_FILE = "figure_manifest_v005.tsv"
SUMMARY_FILE = "summary_v005.json"
CHECKSUM_FILE = "checksums_v005.tsv"
STATUS_FILE = "STATUS_v005.txt"

EXTRAPOLATION_THRESHOLD = 2.0
BREAK_THRESHOLD = 10.0
NUMERIC_TOLERANCE = 5.0e-6
EXPECTED_AUDIT_ROWS = 42

EXPECTED_AUDIT_SUMMARIES = {
    ("basin", "all21"): {
        "configuration_count": 21,
        "grade_min": 0.995678,
        "grade_median": 184.111709,
        "grade_mean": 2726.872850904762,
        "grade_max": 14500.8526,
        "grade_gt_2_count": 19,
        "grade_gt_10_count": 19,
    },
    ("basin", "basin12"): {
        "configuration_count": 12,
        "grade_min": 21.911523,
        "grade_median": 152.7413905,
        "grade_mean": 159.80299483333332,
        "grade_max": 451.651071,
        "grade_gt_2_count": 12,
        "grade_gt_10_count": 12,
    },
    ("basin", "neb9"): {
        "configuration_count": 9,
        "grade_min": 0.995678,
        "grade_median": 6678.371548,
        "grade_mean": 6149.632659,
        "grade_max": 14500.8526,
        "grade_gt_2_count": 7,
        "grade_gt_10_count": 7,
    },
    ("targeted", "all21"): {
        "configuration_count": 21,
        "grade_min": 0.996587,
        "grade_median": 337.381367,
        "grade_mean": 2397.292358238095,
        "grade_max": 12326.803231,
        "grade_gt_2_count": 19,
        "grade_gt_10_count": 19,
    },
    ("targeted", "basin12"): {
        "configuration_count": 12,
        "grade_min": 55.26369,
        "grade_median": 302.946011,
        "grade_mean": 312.0563424166667,
        "grade_max": 871.164892,
        "grade_gt_2_count": 12,
        "grade_gt_10_count": 12,
    },
    ("targeted", "neb9"): {
        "configuration_count": 9,
        "grade_min": 0.996587,
        "grade_median": 5497.731726,
        "grade_mean": 5177.607046,
        "grade_max": 12326.803231,
        "grade_gt_2_count": 7,
        "grade_gt_10_count": 7,
    },
}

EXPECTED_RELAXED_SUMMARIES = {
    "basin": {
        "classification": "invalid_geometry_collapse",
        "barrier_valid": False,
        "converged": False,
        "grade_median": 9207.164193,
        "grade_max": 535658.716794,
    },
    "targeted": {
        "classification": "converged_but_high_grade",
        "barrier_valid": True,
        "converged": True,
        "grade_median": 5216.319957,
        "grade_max": 12006.843432,
    },
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


@dataclasses.dataclass
class LockedInputs:
    attempt: Path
    audit_per_configuration_path: Path
    audit_grade_summary_path: Path
    mtp_neb_classification_path: Path
    style_path: Path
    figure_manifest_path: Path
    summary_path: Path
    checksums_path: Path
    audit_rows: list[dict[str, str]]
    audit_summary_rows: list[dict[str, str]]
    mtp_neb_classification_rows: list[dict[str, str]]
    style: dict[str, Any]
    summary: dict[str, Any]
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


def close(
    observed: float,
    expected: float,
    tolerance: float = NUMERIC_TOLERANCE,
) -> bool:
    scale = max(1.0, abs(expected))
    return abs(observed - expected) <= tolerance * scale


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


def verify_checksum_entry(
    attempt: Path,
    checksum_rows: Sequence[Mapping[str, str]],
    relative_path: str,
) -> str:
    matches = [
        row
        for row in checksum_rows
        if row.get("relative_path") == relative_path
    ]
    if len(matches) != 1:
        raise FigureAuditError(
            f"Expected one checksum row for {relative_path}; "
            f"found {len(matches)}"
        )
    target = require_file(attempt / relative_path, relative_path)
    expected_size = parse_int(
        matches[0]["size_bytes"],
        f"{relative_path} expected size",
    )
    expected_hash = matches[0]["sha256"].strip()
    observed_size = target.stat().st_size
    observed_hash = sha256_file(target)
    if observed_size != expected_size or observed_hash != expected_hash:
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
            f"Unexpected v005 status: observed={observed_status}; "
            f"expected={EXPECTED_INPUT_STATUS}"
        )
    return attempt


def load_locked_inputs(root: Path) -> LockedInputs:
    attempt = resolve_input_attempt(root)
    checksum_rows = read_tsv(attempt / CHECKSUM_FILE)
    relatives = (
        AUDIT_PER_CONFIGURATION_FILE,
        AUDIT_GRADE_SUMMARY_FILE,
        MTP_NEB_CLASSIFICATION_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    source_hashes = {
        relative: verify_checksum_entry(attempt, checksum_rows, relative)
        for relative in relatives
    }

    return LockedInputs(
        attempt=attempt,
        audit_per_configuration_path=(
            attempt / AUDIT_PER_CONFIGURATION_FILE
        ),
        audit_grade_summary_path=attempt / AUDIT_GRADE_SUMMARY_FILE,
        mtp_neb_classification_path=(
            attempt / MTP_NEB_CLASSIFICATION_FILE
        ),
        style_path=attempt / STYLE_FILE,
        figure_manifest_path=attempt / FIGURE_MANIFEST_FILE,
        summary_path=attempt / SUMMARY_FILE,
        checksums_path=attempt / CHECKSUM_FILE,
        audit_rows=read_tsv(attempt / AUDIT_PER_CONFIGURATION_FILE),
        audit_summary_rows=read_tsv(attempt / AUDIT_GRADE_SUMMARY_FILE),
        mtp_neb_classification_rows=read_tsv(
            attempt / MTP_NEB_CLASSIFICATION_FILE
        ),
        style=read_json(attempt / STYLE_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        source_hashes=source_hashes,
    )


def audit_summary_lookup(
    rows: Sequence[Mapping[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    output: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row.get("model", ""), row.get("subset", ""))
        if key in output:
            raise FigureAuditError(f"Duplicate audit summary row: {key}")
        output[key] = dict(row)
    return output


def relaxed_summary_lookup(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        branch = row.get("branch", "")
        if branch in output:
            raise FigureAuditError(
                f"Duplicate relaxed-path classification row: {branch}"
            )
        output[branch] = dict(row)
    return output


def audit_values(
    inputs: LockedInputs,
) -> dict[tuple[str, str], list[float]]:
    output: dict[tuple[str, str], list[float]] = {
        ("basin", "basin12"): [],
        ("basin", "neb9"): [],
        ("targeted", "basin12"): [],
        ("targeted", "neb9"): [],
    }
    for row in inputs.audit_rows:
        key = (row.get("model", ""), row.get("subset", ""))
        if key not in output:
            raise FigureAuditError(
                f"Unexpected audit per-configuration group: {key}"
            )
        output[key].append(
            parse_float(row["mv_grade"], f"{key} mv_grade")
        )
    return output


def validate_inputs(inputs: LockedInputs) -> list[Validation]:
    validations: list[Validation] = []
    summary = audit_summary_lookup(inputs.audit_summary_rows)
    relaxed = relaxed_summary_lookup(inputs.mtp_neb_classification_rows)
    values = audit_values(inputs)

    validations.extend(
        [
            Validation(
                "audit_per_configuration_row_count",
                len(inputs.audit_rows) == EXPECTED_AUDIT_ROWS,
                str(len(inputs.audit_rows)),
                str(EXPECTED_AUDIT_ROWS),
            ),
            Validation(
                "audit_summary_key_set",
                set(summary) == set(EXPECTED_AUDIT_SUMMARIES),
                str(sorted(summary)),
                str(sorted(EXPECTED_AUDIT_SUMMARIES)),
            ),
            Validation(
                "relaxed_summary_branch_set",
                set(relaxed) == {"basin", "targeted"},
                str(sorted(relaxed)),
                "['basin', 'targeted']",
            ),
        ]
    )

    numeric_fields = (
        "grade_min",
        "grade_median",
        "grade_mean",
        "grade_max",
    )
    integer_fields = (
        "configuration_count",
        "grade_gt_2_count",
        "grade_gt_10_count",
    )

    for key, expected in EXPECTED_AUDIT_SUMMARIES.items():
        row = summary.get(key)
        if row is None:
            continue
        model, subset = key
        for field in numeric_fields:
            observed = parse_float(
                row[field],
                f"{model}/{subset} {field}",
            )
            validations.append(
                Validation(
                    f"{model}_{subset}_{field}_locked",
                    close(observed, float(expected[field])),
                    f"{observed:.12g}",
                    f"{float(expected[field]):.12g}",
                )
            )
        for field in integer_fields:
            observed = parse_int(
                row[field],
                f"{model}/{subset} {field}",
            )
            validations.append(
                Validation(
                    f"{model}_{subset}_{field}_locked",
                    observed == int(expected[field]),
                    str(observed),
                    str(int(expected[field])),
                )
            )

    for key, group_values in values.items():
        expected = EXPECTED_AUDIT_SUMMARIES[key]
        ordered = sorted(group_values)
        validations.extend(
            [
                Validation(
                    f"{key[0]}_{key[1]}_per_configuration_count",
                    len(ordered) == int(expected["configuration_count"]),
                    str(len(ordered)),
                    str(int(expected["configuration_count"])),
                ),
                Validation(
                    f"{key[0]}_{key[1]}_per_configuration_min",
                    close(min(ordered), float(expected["grade_min"])),
                    f"{min(ordered):.12g}",
                    f"{float(expected['grade_min']):.12g}",
                ),
                Validation(
                    f"{key[0]}_{key[1]}_per_configuration_median",
                    close(
                        statistics.median(ordered),
                        float(expected["grade_median"]),
                    ),
                    f"{statistics.median(ordered):.12g}",
                    f"{float(expected['grade_median']):.12g}",
                ),
                Validation(
                    f"{key[0]}_{key[1]}_per_configuration_max",
                    close(max(ordered), float(expected["grade_max"])),
                    f"{max(ordered):.12g}",
                    f"{float(expected['grade_max']):.12g}",
                ),
                Validation(
                    f"{key[0]}_{key[1]}_per_configuration_gt2",
                    sum(value > EXTRAPOLATION_THRESHOLD for value in ordered)
                    == int(expected["grade_gt_2_count"]),
                    str(
                        sum(
                            value > EXTRAPOLATION_THRESHOLD
                            for value in ordered
                        )
                    ),
                    str(int(expected["grade_gt_2_count"])),
                ),
                Validation(
                    f"{key[0]}_{key[1]}_per_configuration_gt10",
                    sum(value > BREAK_THRESHOLD for value in ordered)
                    == int(expected["grade_gt_10_count"]),
                    str(
                        sum(value > BREAK_THRESHOLD for value in ordered)
                    ),
                    str(int(expected["grade_gt_10_count"])),
                ),
            ]
        )

    for branch, expected in EXPECTED_RELAXED_SUMMARIES.items():
        row = relaxed.get(branch)
        if row is None:
            continue
        validations.extend(
            [
                Validation(
                    f"{branch}_relaxed_classification_locked",
                    row["classification"] == expected["classification"],
                    row["classification"],
                    str(expected["classification"]),
                ),
                Validation(
                    f"{branch}_relaxed_barrier_valid_locked",
                    parse_bool(
                        row["barrier_valid"],
                        f"{branch} barrier_valid",
                    )
                    is bool(expected["barrier_valid"]),
                    row["barrier_valid"],
                    str(expected["barrier_valid"]),
                ),
                Validation(
                    f"{branch}_relaxed_converged_locked",
                    parse_bool(
                        row["converged"],
                        f"{branch} converged",
                    )
                    is bool(expected["converged"]),
                    row["converged"],
                    str(expected["converged"]),
                ),
            ]
        )
        for field in ("grade_median", "grade_max"):
            observed = parse_float(
                row[field],
                f"{branch} relaxed {field}",
            )
            validations.append(
                Validation(
                    f"{branch}_relaxed_{field}_locked",
                    close(observed, float(expected[field])),
                    f"{observed:.12g}",
                    f"{float(expected[field]):.12g}",
                )
            )

    failures = [
        item for item in validations
        if item.severity == "ERROR" and not item.passed
    ]
    if failures:
        raise FigureAuditError(
            "Supplementary Figure S2 input validation failed: "
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
            "font.size": 8.4,
            "axes.labelsize": 8.4,
            "axes.titlesize": 9.0,
            "xtick.labelsize": 7.2,
            "ytick.labelsize": 7.2,
            "legend.fontsize": 6.9,
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
    axis.grid(
        axis=grid_axis,
        linewidth=0.45,
        alpha=0.22,
        zorder=0,
    )


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

    values = audit_values(inputs)
    audit_summary = audit_summary_lookup(inputs.audit_summary_rows)
    relaxed_summary = relaxed_summary_lookup(
        inputs.mtp_neb_classification_rows
    )

    basin_color = palette["basin_model"]
    targeted_color = palette["targeted_model"]
    audit_color = palette["audit"]
    dft_color = palette["dft_reference"]
    common_color = palette["common_dataset"]

    figure = plt.figure(figsize=(10.60, 6.10), constrained_layout=False)
    grid = figure.add_gridspec(
        1,
        2,
        left=0.075,
        right=0.988,
        bottom=0.225,
        top=0.880,
        wspace=0.40,
        width_ratios=[1.16, 1.00],
    )
    ax_a = figure.add_subplot(grid[0, 0])
    ax_b = figure.add_subplot(grid[0, 1])
    tracked: list[tuple[str, Any]] = []

    # ------------------------------------------------------------------
    # a. Full frozen-audit distributions.
    # ------------------------------------------------------------------
    group_specs = (
        (("basin", "basin12"), 0.00, basin_color, "D"),
        (("basin", "neb9"), 1.30, basin_color, "o"),
        (("targeted", "basin12"), 3.30, targeted_color, "D"),
        (("targeted", "neb9"), 4.60, targeted_color, "o"),
    )
    for group_index, (key, x_center, color, marker) in enumerate(group_specs):
        ordered = sorted(values[key])
        offsets = np.linspace(-0.22, 0.22, len(ordered))
        ax_a.scatter(
            x_center + offsets,
            ordered,
            s=34,
            marker=marker,
            facecolor=(
                "white" if key[1] == "neb9" else color
            ),
            edgecolor=color,
            linewidth=1.0,
            alpha=0.95,
            zorder=3,
        )
        median = statistics.median(ordered)
        ax_a.hlines(
            median,
            x_center - 0.31,
            x_center + 0.31,
            color=color,
            linewidth=2.2,
            zorder=4,
        )

    ax_a.axhline(
        EXTRAPOLATION_THRESHOLD,
        color=audit_color,
        linestyle="--",
        linewidth=1.0,
        zorder=0,
    )
    ax_a.axhline(
        BREAK_THRESHOLD,
        color=basin_color,
        linestyle="--",
        linewidth=1.0,
        zorder=0,
    )
    tracked.extend(
        [
            (
                "a_gamma2",
                ax_a.text(
                    5.02,
                    EXTRAPOLATION_THRESHOLD * 1.10,
                    r"$\gamma=2$ extrapolation",
                    ha="right",
                    va="bottom",
                    fontsize=6.3,
                    color=audit_color,
                    bbox={
                        "facecolor": "white",
                        "edgecolor": "none",
                        "pad": 0.20,
                        "alpha": 0.88,
                    },
                ),
            ),
            (
                "a_gamma10",
                ax_a.text(
                    5.02,
                    BREAK_THRESHOLD * 1.10,
                    r"$\gamma=10$ break",
                    ha="right",
                    va="bottom",
                    fontsize=6.3,
                    color=basin_color,
                    bbox={
                        "facecolor": "white",
                        "edgecolor": "none",
                        "pad": 0.20,
                        "alpha": 0.88,
                    },
                ),
            ),
            (
                "a_summary",
                ax_a.text(
                    0.05,
                    0.965,
                    "19/21 exceed "
                    r"$\gamma=10$"
                    "\nfor both models",
                    transform=ax_a.transAxes,
                    ha="left",
                    va="top",
                    fontsize=6.55,
                    fontweight="bold",
                    color=dft_color,
                    bbox={
                        "facecolor": "white",
                        "edgecolor": "#BBBBBB",
                        "linewidth": 0.45,
                        "boxstyle": "round,pad=0.30",
                        "alpha": 0.92,
                    },
                ),
            ),
        ]
    )

    ax_a.set_yscale("log")
    ax_a.set_ylim(0.70, 50000.0)
    ax_a.set_xlim(-0.65, 5.20)
    ax_a.set_xticks(
        [0.00, 1.30, 3.30, 4.60],
        ["basin12", "NEB9", "basin12", "NEB9"],
    )
    ax_a.set_ylabel(r"MaxVol applicability grade, $\gamma$")
    ax_a.set_xlabel("Frozen audit subset")
    title_a = ax_a.set_title(
        "Frozen-audit grade distributions",
        loc="left",
        x=0.025,
        pad=10,
    )
    tracked.append(("a_title", title_a))
    tracked.append(("a_panel_label", add_panel_label(ax_a, "a")))
    clean_axis(ax_a)

    ax_a.text(
        0.255,
        -0.145,
        "Basin-trained model",
        transform=ax_a.transAxes,
        ha="center",
        va="top",
        fontsize=6.8,
        fontweight="bold",
        color=basin_color,
        clip_on=False,
    )
    ax_a.text(
        0.745,
        -0.145,
        "Transition-targeted model",
        transform=ax_a.transAxes,
        ha="center",
        va="top",
        fontsize=6.8,
        fontweight="bold",
        color=targeted_color,
        clip_on=False,
    )

    # Legend uses subset shapes and median line.
    ax_a.scatter(
        [],
        [],
        s=34,
        marker="D",
        facecolor=common_color,
        edgecolor=common_color,
        label="basin12 configuration",
    )
    ax_a.scatter(
        [],
        [],
        s=34,
        marker="o",
        facecolor="white",
        edgecolor=dft_color,
        label="independent NEB9 image",
    )
    ax_a.plot(
        [],
        [],
        color=dft_color,
        linewidth=2.2,
        label="subset median",
    )
    legend_a = ax_a.legend(
        loc="lower left",
        frameon=False,
        borderaxespad=0.25,
        handletextpad=0.45,
        labelspacing=0.38,
    )
    tracked.append(("a_legend", legend_a))

    # ------------------------------------------------------------------
    # b. Frozen versus relaxed path summaries.
    # ------------------------------------------------------------------
    summary_specs = (
        (
            0.0,
            "Basin\nfrozen NEB9",
            basin_color,
            False,
            parse_float(
                audit_summary[("basin", "neb9")]["grade_median"],
                "basin frozen median",
            ),
            parse_float(
                audit_summary[("basin", "neb9")]["grade_max"],
                "basin frozen max",
            ),
        ),
        (
            1.65,
            "Basin\nrelaxed",
            basin_color,
            True,
            parse_float(
                relaxed_summary["basin"]["grade_median"],
                "basin relaxed median",
            ),
            parse_float(
                relaxed_summary["basin"]["grade_max"],
                "basin relaxed max",
            ),
        ),
        (
            4.40,
            "Targeted\nfrozen NEB9",
            targeted_color,
            False,
            parse_float(
                audit_summary[("targeted", "neb9")]["grade_median"],
                "targeted frozen median",
            ),
            parse_float(
                audit_summary[("targeted", "neb9")]["grade_max"],
                "targeted frozen max",
            ),
        ),
        (
            6.05,
            "Targeted\nrelaxed",
            targeted_color,
            True,
            parse_float(
                relaxed_summary["targeted"]["grade_median"],
                "targeted relaxed median",
            ),
            parse_float(
                relaxed_summary["targeted"]["grade_max"],
                "targeted relaxed max",
            ),
        ),
    )

    label_offsets = {
        "Basin\nfrozen NEB9": (0.10, "left", 1.15),
        "Basin\nrelaxed": (0.00, "center", 1.18),
        "Targeted\nfrozen NEB9": (0.00, "center", 1.15),
        "Targeted\nrelaxed": (0.00, "center", 1.15),
    }

    for x_position, label, color, relaxed, median, maximum in summary_specs:
        ax_b.vlines(
            x_position,
            median,
            maximum,
            color=color,
            linewidth=2.0,
            alpha=0.82,
            zorder=2,
        )
        ax_b.scatter(
            [x_position],
            [median],
            s=62,
            marker="s" if relaxed else "o",
            facecolor=color if relaxed else "white",
            edgecolor=color,
            linewidth=1.2,
            zorder=4,
        )
        ax_b.scatter(
            [x_position],
            [maximum],
            s=62,
            marker="s" if relaxed else "o",
            facecolor="white",
            edgecolor=color,
            linewidth=1.2,
            zorder=4,
        )
        dx, ha, yscale = label_offsets[label]
        tracked.append(
            (
                f"b_max_{label}",
                ax_b.text(
                    x_position + dx,
                    maximum * yscale,
                    f"{maximum:.2e}",
                    ha=ha,
                    va="bottom",
                    fontsize=6.2,
                    color=color,
                ),
            )
        )

    ax_b.axhline(
        EXTRAPOLATION_THRESHOLD,
        color=audit_color,
        linestyle="--",
        linewidth=1.0,
        zorder=0,
    )
    ax_b.axhline(
        BREAK_THRESHOLD,
        color=basin_color,
        linestyle="--",
        linewidth=1.0,
        zorder=0,
    )
    tracked.extend(
        [
            (
                "b_gamma2",
                ax_b.text(
                    6.78,
                    EXTRAPOLATION_THRESHOLD * 1.12,
                    r"$\gamma=2$",
                    ha="right",
                    va="bottom",
                    fontsize=6.2,
                    color=audit_color,
                ),
            ),
            (
                "b_gamma10",
                ax_b.text(
                    6.78,
                    BREAK_THRESHOLD * 1.12,
                    r"$\gamma=10$",
                    ha="right",
                    va="bottom",
                    fontsize=6.2,
                    color=basin_color,
                ),
            ),
        ]
    )

    ax_b.set_yscale("log")
    ax_b.set_ylim(0.70, 2.00e6)
    ax_b.set_xlim(-0.70, 6.95)
    ax_b.set_xticks(
        [item[0] for item in summary_specs],
        [item[1] for item in summary_specs],
    )
    ax_b.set_ylabel(r"MaxVol applicability grade, $\gamma$")
    ax_b.set_xlabel("Path diagnostic")
    title_b = ax_b.set_title(
        "Frozen and relaxed path-grade summaries",
        loc="left",
        x=0.025,
        pad=10,
    )
    tracked.append(("b_title", title_b))
    tracked.append(("b_panel_label", add_panel_label(ax_b, "b")))
    clean_axis(ax_b)

    ax_b.scatter(
        [],
        [],
        s=58,
        marker="o",
        facecolor="white",
        edgecolor=dft_color,
        label="frozen NEB9",
    )
    ax_b.scatter(
        [],
        [],
        s=58,
        marker="s",
        facecolor=dft_color,
        edgecolor=dft_color,
        label="relaxed MTP-NEB",
    )
    ax_b.scatter(
        [],
        [],
        s=58,
        marker="s",
        facecolor=dft_color,
        edgecolor=dft_color,
        label="median",
    )
    ax_b.scatter(
        [],
        [],
        s=58,
        marker="s",
        facecolor="white",
        edgecolor=dft_color,
        label="maximum",
    )
    legend_b = ax_b.legend(
        loc="lower left",
        bbox_to_anchor=(0.02, 0.03),
        frameon=False,
        borderaxespad=0.25,
        handletextpad=0.40,
        labelspacing=0.36,
    )
    tracked.append(("b_legend", legend_b))

    tracked.append(
        (
            "figure_footnote",
            figure.text(
                0.080,
                0.055,
                r"Dashed lines mark $\gamma=2$ and $\gamma=10$. "
                "MaxVol grade is an applicability criterion, not a "
                "measured DFT error. Relaxed paths are shown as "
                "median-to-maximum summaries.",
                ha="left",
                va="bottom",
                fontsize=6.35,
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
        "Title": "Supplementary Figure S2: MaxVol applicability grades",
        "Author": "Reproducible project rendering",
        "Subject": (
            "Frozen-audit distributions and frozen/relaxed path summaries"
        ),
        "Keywords": (
            "malonaldehyde, MTP, MaxVol, applicability, frozen audit, NEB"
        ),
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
        "outputs": {key: str(path) for key, path in outputs.items()},
        "audit_row_count": len(inputs.audit_rows),
        "basin_all21_gt10": parse_int(
            audit_summary[("basin", "all21")]["grade_gt_10_count"],
            "basin all21 >10",
        ),
        "targeted_all21_gt10": parse_int(
            audit_summary[("targeted", "all21")]["grade_gt_10_count"],
            "targeted all21 >10",
        ),
        "targeted_frozen_neb9_median": parse_float(
            audit_summary[("targeted", "neb9")]["grade_median"],
            "targeted frozen NEB9 median",
        ),
        "targeted_relaxed_median": parse_float(
            relaxed_summary["targeted"]["grade_median"],
            "targeted relaxed median",
        ),
        "targeted_relaxed_maximum": parse_float(
            relaxed_summary["targeted"]["grade_max"],
            "targeted relaxed maximum",
        ),
        "basin_relaxed_maximum": parse_float(
            relaxed_summary["basin"]["grade_max"],
            "basin relaxed maximum",
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
                            width >= 4100 and height >= 2300,
                            f"{width}x{height}",
                            "at least 4100x2300 pixels",
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
        AUDIT_PER_CONFIGURATION_FILE,
        AUDIT_GRADE_SUMMARY_FILE,
        MTP_NEB_CLASSIFICATION_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    ):
        source = inputs.attempt / relative
        destination = snapshot_dir / relative.replace("/", "__")
        shutil.copy2(source, destination)
        outputs[relative] = destination
    return outputs


def build_source_rows(
    inputs: LockedInputs,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in inputs.audit_rows:
        output.append(
            {
                "record_type": "frozen_audit_configuration",
                "model": row["model"],
                "subset": row["subset"],
                "record_id": row.get("audit_id", ""),
                "grade": parse_float(
                    row["mv_grade"],
                    "frozen audit mv_grade",
                ),
                "grade_median": "",
                "grade_maximum": "",
                "classification": "",
            }
        )

    relaxed = relaxed_summary_lookup(inputs.mtp_neb_classification_rows)
    for branch in ("basin", "targeted"):
        output.append(
            {
                "record_type": "relaxed_path_summary",
                "model": branch,
                "subset": "relaxed_mtp_neb",
                "record_id": branch,
                "grade": "",
                "grade_median": parse_float(
                    relaxed[branch]["grade_median"],
                    f"{branch} relaxed median",
                ),
                "grade_maximum": parse_float(
                    relaxed[branch]["grade_max"],
                    f"{branch} relaxed max",
                ),
                "classification": relaxed[branch]["classification"],
            }
        )
    return output


def write_caption(
    path: Path,
    figure_data: Mapping[str, Any],
) -> None:
    caption = f"""# Supplementary Figure S2. Static accuracy improvement does not make the reaction-path region interpolative

**a,** Per-configuration MaxVol applicability grades for the 21 held-out
frozen-audit structures, separated into basin12 and independent NEB9 subsets
and evaluated by the basin-trained and transition-targeted models. Horizontal
bars show subset medians. Nineteen of 21 configurations exceed gamma = 10 for
both models. **b,** Median-to-maximum grade summaries for frozen NEB9 and
relaxed MTP-NEB paths. The transition-targeted relaxed path has median and
maximum grades of {figure_data["targeted_relaxed_median"]:.0f} and
{figure_data["targeted_relaxed_maximum"]:.0f}, respectively; the basin relaxed
path reaches {figure_data["basin_relaxed_maximum"]:.0f} and is classified as an
invalid geometry collapse.

Dashed lines mark gamma = 2 and gamma = 10. MaxVol grade is an applicability
criterion, not a measured DFT error. The v005 package exports median and maximum
grades for relaxed paths rather than all nine per-image relaxed grades, so
panel b is a summary-range plot.
"""
    atomic_write_text(path, caption)


def validation_rows(
    validations: Sequence[Validation],
) -> list[dict[str, Any]]:
    return [dataclasses.asdict(validation) for validation in validations]


def write_report(
    path: Path,
    inputs: LockedInputs,
    validations: Sequence[Validation],
    figure_data: Mapping[str, Any],
    output_paths: Mapping[str, Path],
) -> None:
    report = f"""# Supplementary Figure S2 applicability-grade report v022

Created UTC: `{utc_iso()}`

Status: `{STATUS_PASS}`

## Scope

This stage rendered frozen-audit MaxVol-grade distributions and frozen/relaxed
path-grade summaries from the completed v005 normalized source package. It did
not execute DFT, model loading, training, `mlp`, LAMMPS, molecular dynamics,
NEB optimization, or a new grade calculation.

## Locked input

- v005 attempt: `{inputs.attempt}`
- frozen per-configuration metrics:
  `{inputs.audit_per_configuration_path}`
- frozen grade summaries: `{inputs.audit_grade_summary_path}`
- relaxed MTP-NEB summaries: `{inputs.mtp_neb_classification_path}`

Every input was verified against `checksums_v005.tsv`.

## Main results

- frozen per-configuration rows: `{figure_data["audit_row_count"]}`
- basin-model audit21 above gamma 10:
  `{figure_data["basin_all21_gt10"]}/21`
- targeted-model audit21 above gamma 10:
  `{figure_data["targeted_all21_gt10"]}/21`
- targeted frozen NEB9 median grade:
  `{figure_data["targeted_frozen_neb9_median"]:.6f}`
- targeted relaxed median/max grade:
  `{figure_data["targeted_relaxed_median"]:.6f}` /
  `{figure_data["targeted_relaxed_maximum"]:.6f}`
- basin relaxed maximum grade:
  `{figure_data["basin_relaxed_maximum"]:.6f}`

## Interpretation

Transition-focused labeling substantially improves frozen energies, forces and
barrier recovery, but the reaction-path configurations remain strongly
extrapolative by the MaxVol applicability criterion. Accuracy improvement and
applicability-domain coverage are therefore distinct properties.

The basin relaxed path is an invalid geometry-collapse diagnostic. The
targeted relaxed path is geometrically plausible but high-grade and remains
secondary evidence only.

## Layout validation

- tracked artists:
  `{figure_data["layout_validation"]["tracked_text_count"]}`
- detected tracked-text overlaps:
  `{figure_data["layout_validation"]["overlap_count"]}`
- tracked artists outside canvas:
  `{figure_data["layout_validation"]["outside_canvas_count"]}`

## Rendered outputs

- PDF: `{output_paths["pdf"]}`
- SVG: `{output_paths["svg"]}`
- PNG: `{output_paths["png"]}`
- TIFF: `{output_paths["tiff"]}`

## Validation

- passed checks: `{sum(item.passed for item in validations)}`
- failed checks: `{sum(not item.passed for item in validations)}`
"""
    atomic_write_text(path, report)


def write_checksums(attempt: Path) -> Path:
    path = attempt / "checksums_v022.tsv"
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
        print(f"AUDIT_ROWS={len(inputs.audit_rows)}")
        print(f"AUDIT_SUMMARY_ROWS={len(inputs.audit_summary_rows)}")
        print(
            "RELAXED_CLASSIFICATION_ROWS="
            f"{len(inputs.mtp_neb_classification_rows)}"
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

        output_base = (
            figures_dir
            / "supplementary_figure_s2_applicability_grades_spacious_v022"
        )
        figure_data = render_figure(inputs, output_base)
        output_paths = {
            key: Path(value)
            for key, value in figure_data["outputs"].items()
        }
        validations.extend(verify_rendered_files(output_paths))

        source_rows = build_source_rows(inputs)
        source_values_path = (
            source_data_dir
            / "supplementary_figure_s2_values_v022.tsv"
        )
        atomic_write_tsv(
            source_values_path,
            list(source_rows[0].keys()),
            source_rows,
        )

        validation_path = (
            reports_dir
            / "supplementary_figure_s2_validation_v022.tsv"
        )
        atomic_write_tsv(
            validation_path,
            ["check", "passed", "observed", "expected", "severity"],
            validation_rows(validations),
        )

        caption_path = (
            attempt / "supplementary_figure_s2_caption_v022.md"
        )
        write_caption(caption_path, figure_data)

        report_path = (
            reports_dir
            / "supplementary_figure_s2_render_report_v022.md"
        )
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
            "expected_audit_summaries": {
                f"{model}/{subset}": values
                for (model, subset), values
                in EXPECTED_AUDIT_SUMMARIES.items()
            },
            "expected_relaxed_summaries": EXPECTED_RELAXED_SUMMARIES,
            "thresholds": {
                "extrapolation": EXTRAPOLATION_THRESHOLD,
                "break": BREAK_THRESHOLD,
            },
            "scientific_execution": {
                "dft": False,
                "model_loading": False,
                "training": False,
                "mlp": False,
                "lammps": False,
                "md": False,
                "neb_optimization": False,
                "new_grade_calculation": False,
            },
        }
        data_lock_path = (
            attempt / "supplementary_figure_s2_data_lock_v022.json"
        )
        atomic_write_json(data_lock_path, data_lock)

        manifest_rows = [
            {
                "artifact_id": "Supplementary_Figure_S2",
                "role": "applicability_grade_distributions",
                "pdf": str(output_paths["pdf"].relative_to(attempt)),
                "svg": str(output_paths["svg"].relative_to(attempt)),
                "png": str(output_paths["png"].relative_to(attempt)),
                "tiff": str(output_paths["tiff"].relative_to(attempt)),
                "caption": str(caption_path.relative_to(attempt)),
                "status": "RENDERED_AND_VALIDATED",
                "scientific_message": (
                    "Static accuracy improvement does not make frozen or "
                    "relaxed reaction-path configurations interpolative."
                ),
                "mandatory_caveat": (
                    "MaxVol grade is an applicability criterion, not a "
                    "measured DFT error."
                ),
            }
        ]
        manifest_path = (
            attempt / "supplementary_figure_s2_manifest_v022.tsv"
        )
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
                "source_values": str(source_values_path),
                "source_snapshot": {
                    key: str(value)
                    for key, value in snapshot_paths.items()
                },
            },
            "scientific_claim": (
                "Accuracy improvement and applicability-domain coverage "
                "remain distinct properties."
            ),
            "mandatory_caveat": (
                "The relaxed-path panel contains median/max summaries, "
                "not full per-image relaxed-grade distributions."
            ),
            "next_stage": (
                "Build Supplementary Table S1 complete numerical audit."
            ),
        }
        summary_path = attempt / "summary_v022.json"
        atomic_write_json(summary_path, summary)

        atomic_write_text(attempt / "STATUS_v022.txt", STATUS_PASS + "\n")
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
        failure_path = attempt / "STATUS_v022.txt"
        if not failure_path.exists():
            failure_path.write_text(STATUS_FAIL + "\n", encoding="utf-8")
        raise


def synthetic_group_values() -> dict[tuple[str, str], list[float]]:
    return {
        ("basin", "basin12"): [
            21.911523,
            45.0,
            75.0,
            100.0,
            130.0,
            152.7413905,
            152.7413905,
            180.0,
            210.0,
            250.0,
            300.0,
            451.651071,
        ],
        ("basin", "neb9"): [
            0.995678,
            1.2,
            1200.0,
            3500.0,
            6678.371548,
            7200.0,
            9000.0,
            13000.0,
            14500.8526,
        ],
        ("targeted", "basin12"): [
            55.26369,
            100.0,
            175.0,
            225.0,
            275.0,
            302.946011,
            302.946011,
            360.0,
            425.0,
            525.0,
            650.0,
            871.164892,
        ],
        ("targeted", "neb9"): [
            0.996587,
            1.3,
            950.0,
            3000.0,
            5497.731726,
            6500.0,
            8000.0,
            10500.0,
            12326.803231,
        ],
    }


def make_synthetic_fixture(root: Path) -> Path:
    attempt = root / INPUT_RELATIVE_ROOT / "attempt_20990101T000000Z"
    (attempt / "source_data").mkdir(parents=True)

    audit_rows: list[dict[str, Any]] = []
    for (model, subset), grades in synthetic_group_values().items():
        for index, grade in enumerate(grades, start=1):
            audit_rows.append(
                {
                    "audit_id": f"{subset}_{index:02d}",
                    "subset": subset,
                    "subset_index": index,
                    "model": model,
                    "qpt_ang": 0.0,
                    "roo_ang": 2.5,
                    "mv_grade": grade,
                }
            )
    atomic_write_tsv(
        attempt / AUDIT_PER_CONFIGURATION_FILE,
        list(audit_rows[0].keys()),
        audit_rows,
    )

    summary_rows: list[dict[str, Any]] = []
    for key, values in EXPECTED_AUDIT_SUMMARIES.items():
        summary_rows.append(
            {
                "model": key[0],
                "subset": key[1],
                **values,
            }
        )
    atomic_write_tsv(
        attempt / AUDIT_GRADE_SUMMARY_FILE,
        list(summary_rows[0].keys()),
        summary_rows,
    )

    relaxed_rows = [
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
            "maximum_mass_weighted_rmsd_from_dft_image_ang":
                0.2495966907319963,
            "formal_lower_endpoint_barrier_ev": 0.0005612818879399128,
            "reported_lower_endpoint_barrier_ev": "",
            "maximum_image": 8,
            "grade_median": 9207.164193,
            "grade_max": 535658.716794,
            "interpretation": "invalid synthetic collapse",
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
            "maximum_mass_weighted_rmsd_from_dft_image_ang":
                0.0023785855552754713,
            "formal_lower_endpoint_barrier_ev": 0.030672292320105043,
            "reported_lower_endpoint_barrier_ev": 0.030672292320105043,
            "maximum_image": 5,
            "grade_median": 5216.319957,
            "grade_max": 12006.843432,
            "interpretation": "synthetic high-grade targeted path",
        },
    ]
    atomic_write_tsv(
        attempt / MTP_NEB_CLASSIFICATION_FILE,
        list(relaxed_rows[0].keys()),
        relaxed_rows,
    )

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

    manifest_rows = [
        {
            "figure_id": "Figure_3",
            "title": "Deployment applicability diagnostic",
            "panels": "audit grades and first-step diagnostics",
            "primary_source_data": (
                f"{AUDIT_PER_CONFIGURATION_FILE}; "
                f"{AUDIT_GRADE_SUMMARY_FILE}"
            ),
            "geometry_sources": "",
            "status": "SOURCE_DATA_READY",
            "scientific_message": "synthetic",
            "mandatory_caveat": "MaxVol grade is not DFT error.",
        },
        {
            "figure_id": "Figure_4",
            "title": "Secondary MTP-NEB diagnostic",
            "panels": "relaxed path",
            "primary_source_data": MTP_NEB_CLASSIFICATION_FILE,
            "geometry_sources": "",
            "status": "SOURCE_DATA_READY",
            "scientific_message": "synthetic",
            "mandatory_caveat": "high-grade secondary evidence",
        },
    ]
    atomic_write_tsv(
        attempt / FIGURE_MANIFEST_FILE,
        list(manifest_rows[0].keys()),
        manifest_rows,
    )
    atomic_write_json(
        attempt / SUMMARY_FILE,
        {"status": EXPECTED_INPUT_STATUS},
    )
    atomic_write_text(attempt / STATUS_FILE, EXPECTED_INPUT_STATUS + "\n")

    checksum_rows: list[dict[str, Any]] = []
    for relative in (
        AUDIT_PER_CONFIGURATION_FILE,
        AUDIT_GRADE_SUMMARY_FILE,
        MTP_NEB_CLASSIFICATION_FILE,
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
    with tempfile.TemporaryDirectory(prefix="supplementary_s2_v021_test_") as temp:
        root = Path(temp)
        make_synthetic_fixture(root)
        inputs = load_locked_inputs(root)
        validations = validate_inputs(inputs)
        output_base = root / "synthetic_output" / "supplementary_s2"
        figure_data = render_figure(inputs, output_base)
        output_paths = {
            key: Path(value)
            for key, value in figure_data["outputs"].items()
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
            "Render Supplementary Figure S2 from the completed v005 "
            "normalized source package."
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
        return run(
            Path(arguments.root),
            validate_only=arguments.validate_only,
        )
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

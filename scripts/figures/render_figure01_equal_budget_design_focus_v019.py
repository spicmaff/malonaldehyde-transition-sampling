#!/usr/bin/env python3
"""
Figure 01 rendering v019
========================

Render the controlled equal-budget design, configurational coverage map, and
post-training evaluation hierarchy from the completed visualization Step 01
v005 source package.

No DFT, model loading, training, NEB, ``mlp``, LAMMPS, or molecular dynamics is
executed.

Authoritative input:
    10_visualization/versions/
    v005_q1_dataviz_source_audit_source_oracle_recovery/
    CURRENT_VISUAL_SOURCE_AUDIT_V005.txt

Output:
    10_visualization/versions/
    v019_figure01_equal_budget_design_focus_v019/attempt_<UTC>/

Panels
------
a. Controlled equal-budget training design.
b. Training allocation and frozen-audit coverage in (qPT, R_OO).
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


IMPLEMENTATION_ID = "RENDER_FIGURE01_EQUAL_BUDGET_DESIGN_FOCUS_V019"
OUTPUT_VERSION = "v019_figure01_equal_budget_design_focus_v019"
EXPECTED_INPUT_STATUS = "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"
STATUS_PASS = "PASS_FIGURE01_EQUAL_BUDGET_DESIGN_FOCUS_RENDERED_V019"
STATUS_FAIL = "FAIL_FIGURE01_EQUAL_BUDGET_DESIGN_FOCUS_V019"

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
OUTPUT_RELATIVE_ROOT = "10_visualization/versions/v019_figure01_equal_budget_design_focus_v019"
OUTPUT_POINTER = "CURRENT_FIGURE01_EQUAL_BUDGET_DESIGN_FOCUS_V019.txt"

COVERAGE_FILE = "source_data/dataset_coverage_v005.tsv"
STYLE_FILE = "visual_style_lock_v005.json"
FIGURE_MANIFEST_FILE = "figure_manifest_v005.tsv"
SUMMARY_FILE = "summary_v005.json"
CHECKSUM_FILE = "checksums_v005.tsv"
STATUS_FILE = "STATUS_v005.txt"

EXPECTED_COUNTS = {
    "common36": 36,
    "basin24": 24,
    "targeted24": 24,
    "audit_basin12": 12,
    "audit_neb9": 9,
    "audit21": 21,
    "basin60": 60,
    "targeted60": 60,
    "all_points": 105,
}
TRANSITION_QPT_LIMIT_ANG = 0.15
NUMERIC_TOLERANCE = 1.0e-10


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
    coverage_path: Path
    style_path: Path
    figure_manifest_path: Path
    summary_path: Path
    checksums_path: Path
    coverage_rows: list[dict[str, str]]
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
        raise FigureAuditError(f"Expected JSON object: {path}")
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


def parse_bool(value: Any, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise FigureAuditError(f"Invalid boolean for {label}: {value!r}")


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
        row for row in checksum_rows
        if row.get("relative_path") == relative_path
    ]
    if len(matches) != 1:
        raise FigureAuditError(
            f"Expected one checksum row for {relative_path}; found {len(matches)}"
        )
    target = require_file(attempt / relative_path, relative_path)
    expected_size = int(matches[0]["size_bytes"])
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
    status = read_text(attempt / STATUS_FILE).strip()
    if status != EXPECTED_INPUT_STATUS:
        raise FigureAuditError(
            f"Unexpected v005 status: {status}; expected {EXPECTED_INPUT_STATUS}"
        )
    return attempt


def load_locked_inputs(root: Path) -> LockedInputs:
    attempt = resolve_input_attempt(root)
    checksum_rows = read_tsv(attempt / CHECKSUM_FILE)
    relatives = (
        COVERAGE_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    source_hashes = {
        relative: verify_checksum_entry(attempt, checksum_rows, relative)
        for relative in relatives
    }

    manifest_rows = read_tsv(attempt / FIGURE_MANIFEST_FILE)
    matches = [row for row in manifest_rows if row.get("figure_id") == "Figure_1"]
    if len(matches) != 1:
        raise FigureAuditError(
            f"Expected one Figure_1 manifest row; found {len(matches)}"
        )
    manifest_row = matches[0]
    if manifest_row.get("status") != "SOURCE_DATA_READY":
        raise FigureAuditError(
            f"Figure_1 source status is {manifest_row.get('status')!r}"
        )

    return LockedInputs(
        attempt=attempt,
        coverage_path=attempt / COVERAGE_FILE,
        style_path=attempt / STYLE_FILE,
        figure_manifest_path=attempt / FIGURE_MANIFEST_FILE,
        summary_path=attempt / SUMMARY_FILE,
        checksums_path=attempt / CHECKSUM_FILE,
        coverage_rows=read_tsv(attempt / COVERAGE_FILE),
        style=read_json(attempt / STYLE_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        figure_manifest_row=manifest_row,
        source_hashes=source_hashes,
    )


def coverage_groups(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, str]]]:
    expected_groups = {
        "common36",
        "basin24",
        "targeted24",
        "audit_basin12",
        "audit_neb9",
    }
    output = {group: [] for group in expected_groups}
    for row in rows:
        group = row.get("dataset_group", "")
        if group not in output:
            raise FigureAuditError(f"Unexpected coverage group: {group!r}")
        output[group].append(dict(row))
    return output


def validate_inputs(inputs: LockedInputs) -> list[Validation]:
    validations: list[Validation] = []
    groups = coverage_groups(inputs.coverage_rows)

    observed_counts = {group: len(rows) for group, rows in groups.items()}
    observed_counts["audit21"] = (
        observed_counts["audit_basin12"] + observed_counts["audit_neb9"]
    )
    observed_counts["basin60"] = sum(
        parse_bool(row["in_basin60"], "in_basin60")
        for row in inputs.coverage_rows
    )
    observed_counts["targeted60"] = sum(
        parse_bool(row["in_targeted60"], "in_targeted60")
        for row in inputs.coverage_rows
    )
    observed_counts["all_points"] = len(inputs.coverage_rows)

    for key, expected in EXPECTED_COUNTS.items():
        validations.append(
            Validation(
                f"coverage_count_{key}",
                observed_counts[key] == expected,
                str(observed_counts[key]),
                str(expected),
            )
        )

    for index, row in enumerate(inputs.coverage_rows, start=1):
        group = row["dataset_group"]
        qpt = parse_float(row["qpt_ang"], f"row {index} qPT")
        roo = parse_float(row["roo_ang"], f"row {index} R_OO")
        validations.extend(
            [
                Validation(
                    f"row{index}_finite_qpt",
                    math.isfinite(qpt),
                    str(qpt),
                    "finite",
                ),
                Validation(
                    f"row{index}_physical_roo",
                    1.5 < roo < 5.0,
                    f"{roo:.9f}",
                    "1.5 < R_OO < 5.0 Å",
                ),
            ]
        )
        is_audit = parse_bool(row["is_frozen_audit"], "is_frozen_audit")
        in_basin = parse_bool(row["in_basin60"], "in_basin60")
        in_targeted = parse_bool(row["in_targeted60"], "in_targeted60")

        if group == "common36":
            passed = (not is_audit) and in_basin and in_targeted
            expected = "training, in both 60-config sets"
        elif group == "basin24":
            passed = (not is_audit) and in_basin and (not in_targeted)
            expected = "training, basin branch only"
        elif group == "targeted24":
            passed = (not is_audit) and (not in_basin) and in_targeted
            expected = "training, targeted branch only"
        else:
            passed = is_audit and (not in_basin) and (not in_targeted)
            expected = "held out from both training sets"
        validations.append(
            Validation(
                f"row{index}_{group}_membership",
                passed,
                f"audit={is_audit}; basin60={in_basin}; targeted60={in_targeted}",
                expected,
            )
        )

    targeted_abs_qpt = [
        abs(parse_float(row["qpt_ang"], "targeted qPT"))
        for row in groups["targeted24"]
    ]
    basin_abs_qpt = [
        abs(parse_float(row["qpt_ang"], "basin qPT"))
        for row in groups["basin24"]
    ]
    validations.append(
        Validation(
            "allocation_separation_visible",
            sum(targeted_abs_qpt) / len(targeted_abs_qpt)
            < sum(basin_abs_qpt) / len(basin_abs_qpt),
            (
                f"mean |qPT| targeted={sum(targeted_abs_qpt)/len(targeted_abs_qpt):.6f}; "
                f"basin={sum(basin_abs_qpt)/len(basin_abs_qpt):.6f}"
            ),
            "targeted mean |qPT| < basin mean |qPT|",
        )
    )

    failures = [item for item in validations if not item.passed]
    if failures:
        raise FigureAuditError(
            "Figure 1 input validation failed: "
            + "; ".join(
                f"{item.check}: {item.observed} != {item.expected}"
                for item in failures[:12]
            )
        )
    return validations


def import_plotting() -> tuple[Any, Any, Any, Any]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        import numpy as np
    except Exception as exc:
        raise FigureAuditError(
            "Matplotlib and NumPy are required: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return matplotlib, plt, patches, np


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
            "xtick.labelsize": 7.2,
            "ytick.labelsize": 7.2,
            "legend.fontsize": 6.8,
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
        -0.055,
        1.020,
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


def add_rounded_box(
    axis: Any,
    patches: Any,
    tracked: list[tuple[str, Any]],
    *,
    box_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
    facecolor: str,
    edgecolor: str,
    title: str,
    body: str,
    title_color: str,
    body_color: str = "#222222",
    title_size: float = 7.35,
    body_size: float = 6.75,
) -> None:
    patch = patches.FancyBboxPatch(
        (x, y),
        width,
        height,
        transform=axis.transAxes,
        boxstyle="round,pad=0.012,rounding_size=0.022",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=1.0,
    )
    axis.add_patch(patch)
    title_artist = axis.text(
        x + width / 2.0,
        y + height * 0.75,
        title,
        transform=axis.transAxes,
        ha="center",
        va="center",
        fontsize=title_size,
        fontweight="bold",
        color=title_color,
    )
    body_artist = axis.text(
        x + width / 2.0,
        y + height * 0.24,
        body,
        transform=axis.transAxes,
        ha="center",
        va="center",
        fontsize=body_size,
        linespacing=1.23,
        color=body_color,
    )
    tracked.extend(
        [
            (f"{box_id}_title", title_artist),
            (f"{box_id}_body", body_artist),
        ]
    )


def render_figure(
    inputs: LockedInputs,
    output_base: Path,
) -> dict[str, Any]:
    matplotlib, plt, patches, np = import_plotting()
    configure_matplotlib(matplotlib, inputs.style)
    palette = inputs["style"] if False else inputs.style["palette"]

    common_color = palette["common_dataset"]
    basin_color = palette["basin_model"]
    targeted_color = palette["targeted_model"]
    audit_color = palette["audit"]
    dft_color = palette["dft_reference"]
    transition_fill = palette["transition_region_fill"]

    groups = coverage_groups(inputs.coverage_rows)
    all_qpt = [parse_float(row["qpt_ang"], "coverage qPT") for row in inputs.coverage_rows]
    all_roo = [parse_float(row["roo_ang"], "coverage R_OO") for row in inputs.coverage_rows]

    figure = plt.figure(figsize=(10.90, 6.95), constrained_layout=False)
    grid = figure.add_gridspec(
        2,
        1,
        left=0.070,
        right=0.985,
        bottom=0.135,
        top=0.945,
        hspace=0.40,
        height_ratios=[0.58, 1.42],
    )
    ax_a = figure.add_subplot(grid[0, 0])
    ax_b = figure.add_subplot(grid[1, 0])
    tracked: list[tuple[str, Any]] = []

    # a. Equal-budget design (simplified horizontal bars).
    ax_a.set_axis_off()
    title_a = ax_a.set_title(
        "Controlled equal-budget training design",
        loc="left",
        x=0.018,
        pad=10,
    )
    tracked.append(("a_title", title_a))
    tracked.append(("a_panel_label", add_panel_label(ax_a, "a")))
    tracked.append((
        "a_header",
        ax_a.text(
            0.50, 0.93,
            "Equal final DFT-labeling budget: 60 configurations per model",
            transform=ax_a.transAxes,
            ha="center", va="center",
            fontsize=8.0, fontweight="bold", color=dft_color,
        ),
    ))

    def budget_row(y_center: float, branch_label: str, extra_label: str, extra_color: str, row_id: str) -> None:
        bar_x = 0.215
        common_w = 0.395
        extra_w = 0.245
        bar_h = 0.19
        y0 = y_center - bar_h / 2.0
        tracked.append((
            f"{row_id}_row_label",
            ax_a.text(0.055, y_center, branch_label, transform=ax_a.transAxes,
                      ha="left", va="center", fontsize=7.55, fontweight="bold", color=extra_color),
        ))
        ax_a.add_patch(patches.FancyBboxPatch(
            (bar_x, y0), common_w, bar_h, transform=ax_a.transAxes,
            boxstyle="round,pad=0.012,rounding_size=0.020",
            facecolor="#F1F1F1", edgecolor=common_color, linewidth=1.0,
        ))
        ax_a.add_patch(patches.FancyBboxPatch(
            (bar_x + common_w + 0.018, y0), extra_w, bar_h, transform=ax_a.transAxes,
            boxstyle="round,pad=0.012,rounding_size=0.020",
            facecolor="#FFF3E8" if extra_color == basin_color else "#EAF4F8",
            edgecolor=extra_color, linewidth=1.0,
        ))
        tracked.extend([
            (f"{row_id}_common_text", ax_a.text(bar_x + common_w / 2.0, y_center, "Common 36", transform=ax_a.transAxes,
                                                ha="center", va="center", fontsize=6.95, fontweight="bold", color="#555555")),
            (f"{row_id}_extra_text", ax_a.text(bar_x + common_w + 0.018 + extra_w / 2.0, y_center,
                                               extra_label + "\n60 total", transform=ax_a.transAxes,
                                               ha="center", va="center", fontsize=6.55, linespacing=1.00,
                                               fontweight="bold", color=extra_color)),
        ])

    budget_row(0.675, "Basin-focused model", "+ 24 basin-focused", basin_color, "a_basin")
    budget_row(0.315, "Transition-focused model", "+ 24 transition-focused", targeted_color, "a_targeted")
    tracked.append((
        "a_controlled_factors",
        ax_a.text(0.50, 0.020,
                  "Identical DFT protocol  •  identical L12 MTP template  •  identical hyperparameters  •  identical training procedure",
                  transform=ax_a.transAxes, ha="center", va="bottom", fontsize=5.90, color="#444444"),
    ))

    # b. Coverage map.
    ax_b.axvspan(-TRANSITION_QPT_LIMIT_ANG, TRANSITION_QPT_LIMIT_ANG,
                 facecolor=transition_fill, edgecolor="none", alpha=0.85, zorder=0)
    scatter_specs = (
        ("common36", "Common36", common_color, "o", 18, 0.45, common_color, 0.0),
        ("basin24", "Basin-focused +24", basin_color, "^", 36, 0.95, basin_color, 0.7),
        ("targeted24", "Transition-focused +24", targeted_color, "s", 34, 0.95, targeted_color, 0.7),
        ("audit_basin12", "Frozen audit: basin12", audit_color, "D", 40, 1.0, "white", 1.2),
        ("audit_neb9", "Frozen audit: NEB9", dft_color, "o", 45, 1.0, "white", 1.2),
    )
    zorders = {"common36": 1, "basin24": 2, "targeted24": 3, "audit_basin12": 4, "audit_neb9": 5}
    for group, label, color, marker, size, alpha, facecolor, linewidth in scatter_specs:
        rows = groups[group]
        ax_b.scatter(
            [parse_float(row["qpt_ang"], f"{group} qPT") for row in rows],
            [parse_float(row["roo_ang"], f"{group} R_OO") for row in rows],
            s=size, marker=marker, facecolor=facecolor, edgecolor=color,
            linewidth=linewidth, alpha=alpha, label=label, zorder=zorders[group],
        )
    qpt_span = max(all_qpt) - min(all_qpt)
    roo_span = max(all_roo) - min(all_roo)
    ax_b.set_xlim(min(all_qpt) - max(0.05, 0.08 * qpt_span), max(all_qpt) + max(0.05, 0.08 * qpt_span))
    ax_b.set_ylim(min(all_roo) - max(0.05, 0.12 * roo_span), max(all_roo) + max(0.05, 0.12 * roo_span))
    ax_b.set_xlabel(r"Proton-transfer coordinate, $q_{\mathrm{PT}}$ ($\mathrm{\AA}$)")
    ax_b.set_ylabel(r"Oxygen distance, $R_{\mathrm{OO}}$ ($\mathrm{\AA}$)")
    title_b = ax_b.set_title("Training allocation and held-out coverage", loc="left", x=0.018, pad=16)
    tracked.append(("b_title", title_b))
    tracked.append(("b_panel_label", add_panel_label(ax_b, "b")))
    clean_axis(ax_b)
    legend_b = ax_b.legend(
        loc="lower center",
        bbox_to_anchor=(0.50, 1.165),
        ncol=3,
        frameon=True,
        facecolor="white",
        edgecolor="#CCCCCC",
        framealpha=0.94,
        borderpad=0.36,
        handletextpad=0.32,
        columnspacing=0.90,
        labelspacing=0.30,
        fontsize=6.35,
    )
    tracked.append(("b_legend", legend_b))
    tracked.append((
        "b_transition_label",
        ax_b.text(0.50, 0.988, r"transition region: $|q_{\mathrm{PT}}|\leq0.15$ $\mathrm{\AA}$",
                  transform=ax_b.transAxes, ha="center", va="top", fontsize=6.55, color="#555555",
                  bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.22, "alpha": 0.84}),
    ))

    tracked.append(("figure_footnote", figure.text(
        0.070, 0.028,
        "Equal-budget comparison isolates placement of the 24 added DFT labels;\n"
        "the MaxVol ranking contribution itself is not isolated.",
        ha="left", va="bottom", fontsize=6.15, color="#444444")))

    tracked.extend([("b_xlabel", ax_b.xaxis.label), ("b_ylabel", ax_b.yaxis.label)])
    layout_validation = validate_tracked_text_layout(figure, tracked)

    output_base.parent.mkdir(parents=True, exist_ok=True)
    outputs = {"pdf": output_base.with_suffix(".pdf"), "svg": output_base.with_suffix(".svg"),
               "png": output_base.with_suffix(".png"), "tiff": output_base.with_suffix(".tiff")}
    for path in outputs.values():
        if path.exists():
            raise FigureAuditError(f"Refusing to overwrite figure: {path}")
    metadata = {"Title": "Equal-budget design and configurational coverage (focus layout)",
                "Author": "Reproducible project rendering",
                "Subject": "Controlled basin-focused versus transition-focused MTP training design",
                "Keywords": "malonaldehyde, MTP, equal budget, proton transfer, coverage",
                "Creator": IMPLEMENTATION_ID}
    figure.savefig(outputs["pdf"], format="pdf", bbox_inches="tight", pad_inches=0.06, metadata=metadata)
    figure.savefig(outputs["svg"], format="svg", bbox_inches="tight", pad_inches=0.06,
                   metadata={"Title": metadata["Title"], "Description": metadata["Subject"]})
    figure.savefig(outputs["png"], format="png", dpi=600, bbox_inches="tight", pad_inches=0.06,
                   metadata={"Title": metadata["Title"], "Description": metadata["Subject"]})
    figure.savefig(outputs["tiff"], format="tiff", dpi=600, bbox_inches="tight", pad_inches=0.06,
                   pil_kwargs={"compression": "tiff_lzw"})
    plt.close(figure)

    targeted_mean_abs_qpt = sum(abs(parse_float(row["qpt_ang"], "targeted qPT")) for row in groups["targeted24"]) / EXPECTED_COUNTS["targeted24"]
    basin_mean_abs_qpt = sum(abs(parse_float(row["qpt_ang"], "basin qPT")) for row in groups["basin24"]) / EXPECTED_COUNTS["basin24"]
    return {"outputs": {key: str(value) for key, value in outputs.items()},
            "counts": EXPECTED_COUNTS,
            "targeted24_mean_abs_qpt_ang": targeted_mean_abs_qpt,
            "basin24_mean_abs_qpt_ang": basin_mean_abs_qpt,
            "transition_qpt_limit_ang": TRANSITION_QPT_LIMIT_ANG,
            "layout_validation": layout_validation,
            "scientific_execution": "NONE"}


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
                            width >= 4800 and height >= 3200,
                            f"{width}x{height}",
                            "at least 4800x3200 pixels",
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
        COVERAGE_FILE,
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
    rows: list[dict[str, Any]] = []
    for row in inputs.coverage_rows:
        rows.append(
            {
                "coverage_index": row["coverage_index"],
                "dataset_group": row["dataset_group"],
                "source_id": row["source_id"],
                "side": row["side"],
                "subset": row["subset"],
                "qpt_ang": parse_float(row["qpt_ang"], "qPT"),
                "roo_ang": parse_float(row["roo_ang"], "R_OO"),
                "is_frozen_audit": parse_bool(
                    row["is_frozen_audit"], "is_frozen_audit"
                ),
                "in_basin60": parse_bool(row["in_basin60"], "in_basin60"),
                "in_targeted60": parse_bool(
                    row["in_targeted60"], "in_targeted60"
                ),
            }
        )
    return rows


def write_caption(
    path: Path,
    figure_data: Mapping[str, Any],
) -> None:
    caption = f"""# Figure 1. Equal-budget training design and configurational coverage

**a,** Both final MTPs contain 60 DFT-labeled configurations. They share the
same 36-configuration common set and differ only in the placement of 24 added
labels: basin-focused or transition-focused. The DFT protocol, L12 MTP
template, hyperparameters, and training procedure are identical. **b,**
Training and frozen-audit configurations in proton-transfer coordinate and
oxygen-oxygen distance. The transition-focused additions cluster more strongly
inside the central reaction corridor, whereas the basin-focused additions stay
closer to endpoint regions. The 21 held-out audit structures comprise 12 basin
configurations and an independent nine-image NEB path. **c,**
Held-out evaluation hierarchy linking the frozen audit (Figure 2), relaxed
MTP-NEB path validation (Figure 4), and first-update applicability diagnostic
(Figure 3).

The controlled comparison isolates placement of the 24 added DFT labels. It
does not isolate the contribution of MaxVol ranking versus another
transition-focused selection rule. The transition region is defined as
|q_PT| <= {figure_data["transition_qpt_limit_ang"]:.2f} Å.
"""
    atomic_write_text(path, caption)


def write_report(
    path: Path,
    inputs: LockedInputs,
    validations: Sequence[Validation],
    figure_data: Mapping[str, Any],
    output_paths: Mapping[str, Path],
) -> None:
    report = f"""# Figure 1 equal-budget design text-clear render report v017

Created UTC: `{utc_iso()}`

Status: `{STATUS_PASS}`

## Scope

This stage rendered the controlled equal-budget design, configurational
coverage map, and evaluation hierarchy from the completed v005 source package.
It did not execute DFT, model loading, training, NEB, `mlp`, LAMMPS, or
molecular dynamics.

## Locked input

- v005 attempt: `{inputs.attempt}`
- coverage table: `{inputs.coverage_path}`
- style lock: `{inputs.style_path}`
- Figure 1 manifest: `{inputs.figure_manifest_path}`

Every source was verified against `checksums_v005.tsv`.

## Counts

- common set: `{figure_data["counts"]["common36"]}`
- basin-focused additions: `{figure_data["counts"]["basin24"]}`
- transition-focused additions: `{figure_data["counts"]["targeted24"]}`
- frozen audit: `{figure_data["counts"]["audit21"]}`
- basin training set: `{figure_data["counts"]["basin60"]}`
- targeted training set: `{figure_data["counts"]["targeted60"]}`

## Spatial allocation

- mean absolute qPT, basin additions:
  `{figure_data["basin24_mean_abs_qpt_ang"]:.9f}` Å
- mean absolute qPT, targeted additions:
  `{figure_data["targeted24_mean_abs_qpt_ang"]:.9f}` Å
- transition definition: `|qPT| <= {figure_data["transition_qpt_limit_ang"]:.2f} Å`

## Interpretation

The comparison controls the final number of DFT labels and all model/training
settings. The principal experimental variable is the spatial placement of the
24 branch-specific labels. Frozen audit, relaxed MTP-NEB, and first-update
deployment diagnostics are post-training evaluations and are not returned to
training.

## Layout validation

Tracked artists: `{figure_data["layout_validation"]["tracked_text_count"]}`

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
    path = attempt / "checksums_v019.tsv"
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
        groups = coverage_groups(inputs.coverage_rows)
        print("VALIDATE_ONLY=PASS")
        print(f"INPUT_ATTEMPT={inputs.attempt}")
        print(f"COVERAGE_ROWS={len(inputs.coverage_rows)}")
        print(f"COMMON36_ROWS={len(groups['common36'])}")
        print(f"BASIN24_ROWS={len(groups['basin24'])}")
        print(f"TARGETED24_ROWS={len(groups['targeted24'])}")
        print(f"AUDIT21_ROWS={len(groups['audit_basin12']) + len(groups['audit_neb9'])}")
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
        output_base = figures_dir / "figure01_equal_budget_design_focus_v019"
        figure_data = render_figure(inputs, output_base)
        output_paths = {
            key: Path(value) for key, value in figure_data["outputs"].items()
        }
        validations.extend(verify_rendered_files(output_paths))

        panel_values = build_panel_values(inputs)
        panel_values_path = source_data_dir / "figure01_coverage_values_v017.tsv"
        atomic_write_tsv(
            panel_values_path,
            list(panel_values[0].keys()),
            panel_values,
        )

        validation_path = reports_dir / "figure01_validation_v019.tsv"
        atomic_write_tsv(
            validation_path,
            ["check", "passed", "observed", "expected", "severity"],
            validation_rows(validations),
        )

        caption_path = attempt / "figure01_caption_v019.md"
        write_caption(caption_path, figure_data)

        report_path = reports_dir / "figure01_render_report_v019.md"
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
            "expected_counts": EXPECTED_COUNTS,
            "transition_qpt_limit_ang": TRANSITION_QPT_LIMIT_ANG,
            "scientific_execution": {
                "dft": False,
                "model_loading": False,
                "training": False,
                "neb": False,
                "mlp": False,
                "lammps": False,
                "md": False,
            },
        }
        data_lock_path = attempt / "figure01_data_lock_v017.json"
        atomic_write_json(data_lock_path, data_lock)

        manifest_rows = [
            {
                "artifact_id": "Figure_1",
                "role": "equal_budget_design_and_coverage",
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
        manifest_path = attempt / "figure01_manifest_v017.tsv"
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
                "The final models have equal training-set size and differ "
                "principally in spatial allocation of the 24 branch-specific "
                "DFT labels."
            ),
            "mandatory_caveat": (
                "The design isolates transition-focused allocation, not the "
                "isolated contribution of MaxVol ranking versus another "
                "transition-focused selection rule."
            ),
            "next_stage": (
                "Prepare supplementary grade-consistency and distribution figures."
            ),
        }
        summary_path = attempt / "summary_v019.json"
        atomic_write_json(summary_path, summary)

        atomic_write_text(attempt / "STATUS_v019.txt", STATUS_PASS + "\n")
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
        failure_path = attempt / "STATUS_v019.txt"
        if not failure_path.exists():
            failure_path.write_text(STATUS_FAIL + "\n", encoding="utf-8")
        raise


COVERAGE_FIELDS = [
    "coverage_index",
    "dataset_group",
    "source_id",
    "side",
    "subset",
    "qpt_ang",
    "roo_ang",
    "dft_energy_ev",
    "maximum_atomic_force_ev_ang",
    "selection_mv_grade",
    "basin_model_mv_grade",
    "targeted_model_mv_grade",
    "is_frozen_audit",
    "in_basin60",
    "in_targeted60",
    "source_version",
    "source_file",
]


def synthetic_row(
    index: int,
    group: str,
    qpt: float,
    roo: float,
    *,
    side: str,
    subset: str,
    audit: bool,
    basin60: bool,
    targeted60: bool,
) -> dict[str, Any]:
    return {
        "coverage_index": index,
        "dataset_group": group,
        "source_id": f"{group}_{index:03d}",
        "side": side,
        "subset": subset,
        "qpt_ang": qpt,
        "roo_ang": roo,
        "dft_energy_ev": "",
        "maximum_atomic_force_ev_ang": "",
        "selection_mv_grade": "",
        "basin_model_mv_grade": "",
        "targeted_model_mv_grade": "",
        "is_frozen_audit": audit,
        "in_basin60": basin60,
        "in_targeted60": targeted60,
        "source_version": "synthetic",
        "source_file": "/synthetic",
    }


def make_synthetic_fixture(root: Path) -> Path:
    attempt = root / INPUT_RELATIVE_ROOT / "attempt_20990101T000000Z"
    (attempt / "source_data").mkdir(parents=True)

    rows: list[dict[str, Any]] = []
    index = 0

    # Shared common set: two endpoint clouds with moderate spread.
    for side_sign, side in ((-1.0, "left"), (1.0, "right")):
        for local in range(18):
            index += 1
            qpt = side_sign * (0.34 + 0.012 * local)
            roo = 2.43 + 0.012 * (local % 6) + 0.004 * (local // 6)
            rows.append(
                synthetic_row(
                    index,
                    "common36",
                    qpt,
                    roo,
                    side=side,
                    subset="training_common",
                    audit=False,
                    basin60=True,
                    targeted60=True,
                )
            )

    # Basin-focused additions.
    for side_sign, side in ((-1.0, "left"), (1.0, "right")):
        for local in range(12):
            index += 1
            qpt = side_sign * (0.405 + 0.009 * local)
            roo = 2.48 + 0.010 * (local % 4) + 0.006 * (local // 4)
            rows.append(
                synthetic_row(
                    index,
                    "basin24",
                    qpt,
                    roo,
                    side=side,
                    subset="training_basin_added",
                    audit=False,
                    basin60=True,
                    targeted60=False,
                )
            )

    # Transition-focused additions.
    for local in range(24):
        index += 1
        qpt = -0.138 + (0.276 / 23.0) * local
        roo = 2.34 + 0.10 * (1.0 - abs(qpt) / 0.15) + 0.006 * ((local % 3) - 1)
        rows.append(
            synthetic_row(
                index,
                "targeted24",
                qpt,
                roo,
                side="transition",
                subset="training_targeted_added",
                audit=False,
                basin60=False,
                targeted60=True,
            )
        )

    # Held-out basin12.
    for side_sign, side in ((-1.0, "left"), (1.0, "right")):
        for local in range(6):
            index += 1
            qpt = side_sign * (0.39 + 0.018 * local)
            roo = 2.45 + 0.016 * local
            rows.append(
                synthetic_row(
                    index,
                    "audit_basin12",
                    qpt,
                    roo,
                    side=side,
                    subset="basin12",
                    audit=True,
                    basin60=False,
                    targeted60=False,
                )
            )

    # Independent NEB9.
    neb_qpt = [-0.484, -0.388, -0.260, -0.128, 0.0, 0.128, 0.260, 0.388, 0.484]
    neb_roo = [2.499, 2.458, 2.419, 2.399, 2.392, 2.399, 2.419, 2.458, 2.499]
    for local, (qpt, roo) in enumerate(zip(neb_qpt, neb_roo), start=1):
        index += 1
        side = "transition" if abs(qpt) <= 0.15 else ("left" if qpt < 0 else "right")
        rows.append(
            synthetic_row(
                index,
                "audit_neb9",
                qpt,
                roo,
                side=side,
                subset="neb9",
                audit=True,
                basin60=False,
                targeted60=False,
            )
        )

    atomic_write_tsv(attempt / COVERAGE_FILE, COVERAGE_FIELDS, rows)
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
            "figure_id": "Figure_1",
            "title": "Equal-budget design and configurational coverage (focus layout)",
            "panels": "a equal-budget design; b qPT-R_OO coverage; c evaluation hierarchy",
            "primary_source_data": COVERAGE_FILE,
            "geometry_sources": "not used by this renderer",
            "status": "SOURCE_DATA_READY",
            "scientific_message": (
                "The two final models have equal size and differ only in allocation "
                "of the 24 added DFT configurations."
            ),
            "mandatory_caveat": (
                "This design isolates transition-focused allocation, not the isolated "
                "contribution of MaxVol versus random transition sampling."
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
        COVERAGE_FILE,
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
    with tempfile.TemporaryDirectory(prefix="figure01_v019_test_") as temp:
        root = Path(temp)
        make_synthetic_fixture(root)
        inputs = load_locked_inputs(root)
        validations = validate_inputs(inputs)
        output_base = root / "synthetic_output" / "figure01"
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
            "Render Figure 1 from the completed v005 normalized source package."
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

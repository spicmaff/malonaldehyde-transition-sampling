#!/usr/bin/env python3
"""
Supplementary Figure S1 rendering v020
======================================

Render the online-versus-offline-exact MaxVol-grade consistency audit from the
completed visualization Step 01 v005 source package.

No DFT, model loading, training, ``mlp``, LAMMPS, molecular dynamics, or new
grade calculation is executed.

Authoritative input:
    10_visualization/versions/
    v005_q1_dataviz_source_audit_source_oracle_recovery/
    CURRENT_VISUAL_SOURCE_AUDIT_V005.txt

Output:
    10_visualization/versions/
    v020_supplementary_figure_s1_selection_interface_consistency/
    attempt_<UTC>/

Panels
------
a. Original online selection grade versus offline-exact grade.
b. Absolute relative difference for the six first-update diagnostic cases.

Scientific scope
----------------
This figure validates numerical consistency of the selection interface. MaxVol
grade is an applicability criterion, not a measured DFT energy or force error.
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


IMPLEMENTATION_ID = (
    "RENDER_SUPPLEMENTARY_FIGURE_S1_SELECTION_INTERFACE_CONSISTENCY_V020"
)
OUTPUT_VERSION = (
    "v020_supplementary_figure_s1_selection_interface_consistency"
)
EXPECTED_INPUT_STATUS = (
    "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"
)
STATUS_PASS = (
    "PASS_SUPPLEMENTARY_FIGURE_S1_SELECTION_INTERFACE_CONSISTENCY_"
    "RENDERED_V020"
)
STATUS_FAIL = (
    "FAIL_SUPPLEMENTARY_FIGURE_S1_SELECTION_INTERFACE_CONSISTENCY_V020"
)

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
OUTPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v020_supplementary_figure_s1_selection_interface_consistency"
)
OUTPUT_POINTER = (
    "CURRENT_SUPPLEMENTARY_FIGURE_S1_SELECTION_INTERFACE_CONSISTENCY_V020.txt"
)

FIRST_STEP_FILE = "source_data/first_step_extrapolation_v005.tsv"
ORACLE_CONTRACT_FILE = "source_data/source_oracle_contract_v005.json"
STYLE_FILE = "visual_style_lock_v005.json"
FIGURE_MANIFEST_FILE = "figure_manifest_v005.tsv"
SUMMARY_FILE = "summary_v005.json"
CHECKSUM_FILE = "checksums_v005.tsv"
STATUS_FILE = "STATUS_v005.txt"

EXPECTED_SOURCE_ORACLE_CLASSIFICATION = "EXACT_SOURCE_ORACLE_REPLAY_PASS"
BREAK_THRESHOLD = 10.0
NUMERIC_TOLERANCE = 5.0e-9
MAX_ALLOWED_RELATIVE_DIFFERENCE = 2.5e-4

CASE_ORDER = (
    "T100_left",
    "T100_right",
    "T300_left",
    "T300_right",
    "T500_left",
    "T500_right",
)

EXPECTED_CASES = {
    "T100_left": {
        "temperature_K": 100.0,
        "side": "left",
        "online": 66.410239,
        "offline": 66.415434,
    },
    "T100_right": {
        "temperature_K": 100.0,
        "side": "right",
        "online": 79.987407,
        "offline": 79.969427,
    },
    "T300_left": {
        "temperature_K": 300.0,
        "side": "left",
        "online": 67.924938,
        "offline": 67.928927,
    },
    "T300_right": {
        "temperature_K": 300.0,
        "side": "right",
        "online": 47.845043,
        "offline": 47.844478,
    },
    "T500_left": {
        "temperature_K": 500.0,
        "side": "left",
        "online": 99.936321,
        "offline": 99.921547,
    },
    "T500_right": {
        "temperature_K": 500.0,
        "side": "right",
        "online": 147.705216,
        "offline": 147.709445,
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
    first_step_path: Path
    oracle_contract_path: Path
    style_path: Path
    figure_manifest_path: Path
    summary_path: Path
    checksums_path: Path
    first_step_rows: list[dict[str, str]]
    oracle_contract: dict[str, Any]
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
    expected_size = int(matches[0]["size_bytes"])
    observed_size = target.stat().st_size
    expected_hash = matches[0]["sha256"].strip()
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
        FIRST_STEP_FILE,
        ORACLE_CONTRACT_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    source_hashes = {
        relative: verify_checksum_entry(attempt, checksum_rows, relative)
        for relative in relatives
    }

    manifest_rows = read_tsv(attempt / FIGURE_MANIFEST_FILE)
    matches = [row for row in manifest_rows if row.get("figure_id") == "Figure_3"]
    if len(matches) != 1:
        raise FigureAuditError(
            f"Expected one Figure_3 manifest row; found {len(matches)}"
        )
    manifest_row = matches[0]
    if manifest_row.get("status") != "SOURCE_DATA_READY":
        raise FigureAuditError(
            f"Figure_3 source status is {manifest_row.get('status')!r}"
        )

    return LockedInputs(
        attempt=attempt,
        first_step_path=attempt / FIRST_STEP_FILE,
        oracle_contract_path=attempt / ORACLE_CONTRACT_FILE,
        style_path=attempt / STYLE_FILE,
        figure_manifest_path=attempt / FIGURE_MANIFEST_FILE,
        summary_path=attempt / SUMMARY_FILE,
        checksums_path=attempt / CHECKSUM_FILE,
        first_step_rows=read_tsv(attempt / FIRST_STEP_FILE),
        oracle_contract=read_json(attempt / ORACLE_CONTRACT_FILE),
        style=read_json(attempt / STYLE_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        figure_manifest_row=manifest_row,
        source_hashes=source_hashes,
    )


def first_step_by_id(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        trajectory_id = row.get("trajectory_id", "")
        if not trajectory_id:
            raise FigureAuditError("First-step row has no trajectory_id")
        if trajectory_id in output:
            raise FigureAuditError(
                f"Duplicate first-step trajectory_id: {trajectory_id}"
            )
        output[trajectory_id] = dict(row)
    return output


def case_rows(inputs: LockedInputs) -> list[dict[str, Any]]:
    by_id = first_step_by_id(inputs.first_step_rows)
    rows: list[dict[str, Any]] = []
    for trajectory_id in CASE_ORDER:
        row = by_id[trajectory_id]
        online = parse_float(
            row["original_online_break_grade"],
            f"{trajectory_id} online grade",
        )
        offline = parse_float(
            row["offline_exact_break_mv_grade"],
            f"{trajectory_id} offline grade",
        )
        relative_difference = parse_float(
            row["online_offline_relative_difference"],
            f"{trajectory_id} relative difference",
        )
        rows.append(
            {
                "trajectory_id": trajectory_id,
                "temperature_K": parse_float(
                    row["temperature_K"],
                    f"{trajectory_id} temperature",
                ),
                "side": row["side"].strip(),
                "online_grade": online,
                "offline_exact_grade": offline,
                "absolute_difference": abs(online - offline),
                "relative_difference": relative_difference,
                "relative_difference_percent": 100.0 * relative_difference,
                "threshold_class_agreement": parse_bool(
                    row["threshold_class_agreement"],
                    f"{trajectory_id} threshold agreement",
                ),
            }
        )
    return rows


def validate_inputs(inputs: LockedInputs) -> list[Validation]:
    validations: list[Validation] = []
    by_id = first_step_by_id(inputs.first_step_rows)
    validations.append(
        Validation(
            "case_ids_exact",
            set(by_id) == set(CASE_ORDER),
            str(sorted(by_id)),
            str(sorted(CASE_ORDER)),
        )
    )

    for trajectory_id in CASE_ORDER:
        row = by_id[trajectory_id]
        expected = EXPECTED_CASES[trajectory_id]
        online = parse_float(
            row["original_online_break_grade"],
            f"{trajectory_id} online grade",
        )
        offline = parse_float(
            row["offline_exact_break_mv_grade"],
            f"{trajectory_id} offline grade",
        )
        temperature = parse_float(
            row["temperature_K"],
            f"{trajectory_id} temperature",
        )
        relative_difference = parse_float(
            row["online_offline_relative_difference"],
            f"{trajectory_id} relative difference",
        )
        derived_relative_difference = abs(online - offline) / offline

        validations.extend(
            [
                Validation(
                    f"{trajectory_id}_temperature_locked",
                    close(temperature, expected["temperature_K"]),
                    f"{temperature:.16g}",
                    f"{expected['temperature_K']:.16g}",
                ),
                Validation(
                    f"{trajectory_id}_side_locked",
                    row["side"].strip() == expected["side"],
                    row["side"].strip(),
                    expected["side"],
                ),
                Validation(
                    f"{trajectory_id}_online_locked",
                    close(online, expected["online"]),
                    f"{online:.16g}",
                    f"{expected['online']:.16g}",
                ),
                Validation(
                    f"{trajectory_id}_offline_locked",
                    close(offline, expected["offline"]),
                    f"{offline:.16g}",
                    f"{expected['offline']:.16g}",
                ),
                Validation(
                    f"{trajectory_id}_relative_difference_self_consistent",
                    close(
                        relative_difference,
                        derived_relative_difference,
                        tolerance=2.0e-12,
                    ),
                    f"{relative_difference:.16g}",
                    f"{derived_relative_difference:.16g}",
                ),
                Validation(
                    f"{trajectory_id}_online_break_class",
                    online > BREAK_THRESHOLD,
                    f"{online:.9f}",
                    f"> {BREAK_THRESHOLD}",
                ),
                Validation(
                    f"{trajectory_id}_offline_break_class",
                    offline > BREAK_THRESHOLD,
                    f"{offline:.9f}",
                    f"> {BREAK_THRESHOLD}",
                ),
                Validation(
                    f"{trajectory_id}_threshold_class_agreement",
                    parse_bool(
                        row["threshold_class_agreement"],
                        f"{trajectory_id} threshold agreement",
                    ),
                    row["threshold_class_agreement"],
                    "True",
                ),
                Validation(
                    f"{trajectory_id}_source_oracle_pass",
                    row["source_oracle_replay_classification"]
                    == EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
                    row["source_oracle_replay_classification"],
                    EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
                ),
                Validation(
                    f"{trajectory_id}_no_physical_dft_error_measurement",
                    not parse_bool(
                        row["physical_dft_error_measured"],
                        f"{trajectory_id} DFT error measured",
                    ),
                    row["physical_dft_error_measured"],
                    "False",
                ),
            ]
        )

    rows = case_rows(inputs)
    maximum_relative_difference = max(
        row["relative_difference"] for row in rows
    )
    validations.extend(
        [
            Validation(
                "all_six_threshold_classes_agree",
                all(row["threshold_class_agreement"] for row in rows),
                str(
                    sum(
                        row["threshold_class_agreement"]
                        for row in rows
                    )
                ),
                "6",
            ),
            Validation(
                "maximum_relative_difference_below_lock",
                maximum_relative_difference < MAX_ALLOWED_RELATIVE_DIFFERENCE,
                f"{maximum_relative_difference:.12g}",
                f"< {MAX_ALLOWED_RELATIVE_DIFFERENCE}",
            ),
            Validation(
                "source_oracle_contract_classification",
                inputs.oracle_contract.get("classification")
                == EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
                str(inputs.oracle_contract.get("classification")),
                EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
            ),
        ]
    )

    failures = [
        item for item in validations
        if item.severity == "ERROR" and not item.passed
    ]
    if failures:
        raise FigureAuditError(
            "Supplementary Figure S1 input validation failed: "
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


def clean_axis(axis: Any, *, grid_axis: str = "both") -> None:
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

    rows = case_rows(inputs)
    common_color = palette["common_dataset"]
    basin_color = palette["basin_model"]
    targeted_color = palette["targeted_model"]
    dft_color = palette["dft_reference"]
    background = palette["background"]

    temperature_colors = {
        100: common_color,
        300: basin_color,
        500: targeted_color,
    }
    side_markers = {"left": "^", "right": "o"}

    figure = plt.figure(figsize=(8.65, 4.55), constrained_layout=False)
    grid = figure.add_gridspec(
        1,
        2,
        left=0.085,
        right=0.985,
        bottom=0.205,
        top=0.890,
        wspace=0.42,
        width_ratios=[1.28, 0.92],
    )
    ax_a = figure.add_subplot(grid[0, 0])
    ax_b = figure.add_subplot(grid[0, 1])
    tracked: list[tuple[str, Any]] = []

    # ------------------------------------------------------------------
    # a. Online versus offline-exact grade.
    # ------------------------------------------------------------------
    minimum_grade = min(
        min(row["online_grade"], row["offline_exact_grade"])
        for row in rows
    )
    maximum_grade = max(
        max(row["online_grade"], row["offline_exact_grade"])
        for row in rows
    )
    axis_padding = 8.0
    axis_min = math.floor((minimum_grade - axis_padding) / 10.0) * 10.0
    axis_max = math.ceil((maximum_grade + axis_padding) / 10.0) * 10.0

    ax_a.plot(
        [axis_min, axis_max],
        [axis_min, axis_max],
        linestyle="--",
        linewidth=1.2,
        color=dft_color,
        alpha=0.70,
        label=r"$y=x$",
        zorder=1,
    )

    label_offsets = {
        "T100_left": (8, -12),
        "T100_right": (8, 8),
        "T300_left": (-10, 10),
        "T300_right": (8, -14),
        "T500_left": (8, 8),
        "T500_right": (-10, 10),
    }

    for row in rows:
        temperature = int(row["temperature_K"])
        color = temperature_colors[temperature]
        marker = side_markers[row["side"]]
        ax_a.scatter(
            [row["online_grade"]],
            [row["offline_exact_grade"]],
            s=64,
            marker=marker,
            facecolor=color,
            edgecolor=color,
            linewidth=1.0,
            zorder=3,
        )
        dx, dy = label_offsets[row["trajectory_id"]]
        label = f"{temperature} {'L' if row['side'] == 'left' else 'R'}"
        artist = ax_a.annotate(
            label,
            (row["online_grade"], row["offline_exact_grade"]),
            xytext=(dx, dy),
            textcoords="offset points",
            ha="left" if dx >= 0 else "right",
            va="bottom" if dy >= 0 else "top",
            fontsize=6.7,
            color="#333333",
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "pad": 0.22,
                "alpha": 0.84,
            },
        )
        tracked.append((f"a_label_{row['trajectory_id']}", artist))

    ax_a.set_xlim(axis_min, axis_max)
    ax_a.set_ylim(axis_min, axis_max)
    ax_a.set_aspect("equal", adjustable="box")
    ax_a.xaxis.set_major_locator(ticker.MultipleLocator(20))
    ax_a.yaxis.set_major_locator(ticker.MultipleLocator(20))
    ax_a.set_xlabel("Original online MaxVol grade")
    ax_a.set_ylabel("Offline-exact MaxVol grade")
    title_a = ax_a.set_title(
        "Selection-interface grade agreement",
        loc="left",
        x=0.025,
        pad=10,
    )
    tracked.append(("a_title", title_a))
    tracked.append(("a_panel_label", add_panel_label(ax_a, "a")))
    clean_axis(ax_a)

    tracked.append(
        (
            "a_summary",
            ax_a.text(
                0.04,
                0.96,
                "Threshold class: 6/6 agree\n"
                "All six cases remain above grade 10",
                transform=ax_a.transAxes,
                ha="left",
                va="top",
                fontsize=6.6,
                linespacing=1.25,
                color="#333333",
                bbox={
                    "facecolor": "white",
                    "edgecolor": "#BBBBBB",
                    "linewidth": 0.5,
                    "boxstyle": "round,pad=0.34",
                    "alpha": 0.92,
                },
            ),
        )
    )

    # Shared encoding legend.
    for temperature, color in temperature_colors.items():
        ax_a.scatter(
            [],
            [],
            s=50,
            marker="s",
            facecolor=color,
            edgecolor=color,
            label=f"{temperature} K",
        )
    ax_a.scatter(
        [],
        [],
        s=50,
        marker="^",
        facecolor="white",
        edgecolor=dft_color,
        label="Left",
    )
    ax_a.scatter(
        [],
        [],
        s=50,
        marker="o",
        facecolor="white",
        edgecolor=dft_color,
        label="Right",
    )
    legend_a = ax_a.legend(
        loc="lower right",
        frameon=False,
        ncol=2,
        borderaxespad=0.25,
        handletextpad=0.35,
        columnspacing=0.85,
        labelspacing=0.35,
    )
    tracked.append(("a_legend", legend_a))

    # ------------------------------------------------------------------
    # b. Absolute relative difference.
    # ------------------------------------------------------------------
    y_positions = np.arange(len(rows))[::-1]
    differences_percent = np.array(
        [row["relative_difference_percent"] for row in rows]
    )
    for y_position, row in zip(y_positions, rows):
        temperature = int(row["temperature_K"])
        color = temperature_colors[temperature]
        marker = side_markers[row["side"]]
        ax_b.hlines(
            y_position,
            0.0,
            row["relative_difference_percent"],
            color=color,
            linewidth=1.6,
            alpha=0.72,
            zorder=1,
        )
        ax_b.scatter(
            [row["relative_difference_percent"]],
            [y_position],
            s=58,
            marker=marker,
            facecolor=color,
            edgecolor=color,
            linewidth=0.9,
            zorder=3,
        )
        tracked.append(
            (
                f"b_value_{row['trajectory_id']}",
                ax_b.text(
                    row["relative_difference_percent"] + 0.00065,
                    y_position,
                    f"{row['relative_difference_percent']:.4f}%",
                    ha="left",
                    va="center",
                    fontsize=6.6,
                    color="#333333",
                ),
            )
        )

    maximum_percent = max(differences_percent)
    ax_b.axvline(
        100.0 * MAX_ALLOWED_RELATIVE_DIFFERENCE,
        color=dft_color,
        linestyle=":",
        linewidth=1.0,
        zorder=0,
    )
    tracked.append(
        (
            "b_lock_label",
            ax_b.text(
                100.0 * MAX_ALLOWED_RELATIVE_DIFFERENCE - 0.00035,
                len(rows) - 1.10,
                "validation lock 0.025%",
                ha="right",
                va="top",
                fontsize=6.2,
                color=dft_color,
                bbox={
                    "facecolor": "white",
                    "edgecolor": "none",
                    "pad": 0.22,
                    "alpha": 0.88,
                },
            ),
        )
    )
    tracked.append(
        (
            "b_maximum_callout",
            ax_b.text(
                0.97,
                0.08,
                f"Maximum = {maximum_percent:.4f}%\n"
                "Selection-interface consistent",
                transform=ax_b.transAxes,
                ha="right",
                va="bottom",
                fontsize=6.6,
                linespacing=1.25,
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

    ax_b.set_yticks(
        y_positions,
        [
            f"{int(row['temperature_K'])} "
            f"{'L' if row['side'] == 'left' else 'R'}"
            for row in rows
        ],
    )
    ax_b.set_xlim(0.0, 0.0285)
    ax_b.xaxis.set_major_locator(ticker.MultipleLocator(0.005))
    ax_b.xaxis.set_major_formatter(
        ticker.FuncFormatter(lambda value, _: f"{value:.3f}%")
    )
    ax_b.set_xlabel("Absolute relative difference")
    title_b = ax_b.set_title(
        "Online/offline-exact residual",
        loc="left",
        x=0.025,
        pad=10,
    )
    tracked.append(("b_title", title_b))
    tracked.append(("b_panel_label", add_panel_label(ax_b, "b")))
    clean_axis(ax_b, grid_axis="x")

    tracked.append(
        (
            "figure_footnote",
            figure.text(
                0.085,
                0.055,
                "Exact source-oracle diagnostic. MaxVol grade is an "
                "applicability criterion, not a measured DFT error.",
                ha="left",
                va="bottom",
                fontsize=6.45,
                color="#444444",
            ),
        )
    )
    tracked.extend(
        [
            ("a_xlabel", ax_a.xaxis.label),
            ("a_ylabel", ax_a.yaxis.label),
            ("b_xlabel", ax_b.xaxis.label),
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
        "Title": "Supplementary Figure S1: selection-interface consistency",
        "Author": "Reproducible project rendering",
        "Subject": "Original online versus offline-exact MaxVol grades",
        "Keywords": "malonaldehyde, MTP, MaxVol, selection interface",
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
        "case_count": len(rows),
        "threshold_class_agreement_count": sum(
            row["threshold_class_agreement"] for row in rows
        ),
        "maximum_absolute_difference": max(
            row["absolute_difference"] for row in rows
        ),
        "maximum_relative_difference": max(
            row["relative_difference"] for row in rows
        ),
        "maximum_relative_difference_percent": maximum_percent,
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
                            width >= 3900 and height >= 2100,
                            f"{width}x{height}",
                            "at least 3900x2100 pixels",
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
        FIRST_STEP_FILE,
        ORACLE_CONTRACT_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    ):
        source = inputs.attempt / relative
        destination = snapshot_dir / relative.replace("/", "__")
        shutil.copy2(source, destination)
        outputs[relative] = destination
    return outputs


def build_source_rows(inputs: LockedInputs) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in case_rows(inputs):
        rows.append(
            {
                "trajectory_id": row["trajectory_id"],
                "temperature_K": row["temperature_K"],
                "side": row["side"],
                "original_online_grade": row["online_grade"],
                "offline_exact_grade": row["offline_exact_grade"],
                "absolute_difference": row["absolute_difference"],
                "absolute_relative_difference": row["relative_difference"],
                "absolute_relative_difference_percent":
                    row["relative_difference_percent"],
                "threshold_class_agreement":
                    row["threshold_class_agreement"],
            }
        )
    return rows


def write_caption(
    path: Path,
    figure_data: Mapping[str, Any],
) -> None:
    caption = f"""# Supplementary Figure S1. Online and offline-exact MaxVol grades agree for all six first-update cases

**a,** Original online selection-interface grade versus the independently
replayed offline-exact grade for the six source-oracle first-update diagnostic
geometries. The dashed identity line denotes exact numerical agreement.
All six configurations retain the same break classification above
gamma = 10. **b,** Absolute relative online/offline-exact difference for each
case. The maximum relative difference is
{figure_data["maximum_relative_difference_percent"]:.4f}%, below the locked
0.025% validation limit.

This comparison validates consistency of the online selection interface with
the offline-exact replay. MaxVol grade is an applicability criterion and does
not measure the physical DFT energy or force error on these geometries.
"""
    atomic_write_text(path, caption)


def write_report(
    path: Path,
    inputs: LockedInputs,
    validations: Sequence[Validation],
    figure_data: Mapping[str, Any],
    output_paths: Mapping[str, Path],
) -> None:
    report = f"""# Supplementary Figure S1 selection-interface consistency report v020

Created UTC: `{utc_iso()}`

Status: `{STATUS_PASS}`

## Scope

This stage rendered the original-online versus offline-exact MaxVol-grade
comparison from the completed v005 normalized source package. It did not run
DFT, model loading, training, `mlp`, LAMMPS, molecular dynamics, or a new grade
calculation.

## Locked input

- v005 attempt: `{inputs.attempt}`
- first-update table: `{inputs.first_step_path}`
- source-oracle contract: `{inputs.oracle_contract_path}`
- style lock: `{inputs.style_path}`

Every source was verified against `checksums_v005.tsv`.

## Main results

- cases: `{figure_data["case_count"]}`
- threshold-class agreements:
  `{figure_data["threshold_class_agreement_count"]}/6`
- maximum absolute grade difference:
  `{figure_data["maximum_absolute_difference"]:.9f}`
- maximum relative grade difference:
  `{figure_data["maximum_relative_difference"]:.12g}`
- maximum relative grade difference:
  `{figure_data["maximum_relative_difference_percent"]:.6f}%`

## Interpretation

Original online and offline-exact grades are numerically consistent and assign
the same break class to all six cases. Therefore, the first-update rejection is
not explained by a mismatch between the online selection interface and the
offline-exact replay.

This audit does not establish a physical DFT error on the rejected geometries.

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


def validation_rows(
    validations: Sequence[Validation],
) -> list[dict[str, Any]]:
    return [dataclasses.asdict(validation) for validation in validations]


def write_checksums(attempt: Path) -> Path:
    path = attempt / "checksums_v020.tsv"
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
        print(f"FIRST_STEP_ROWS={len(inputs.first_step_rows)}")
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
            / "supplementary_figure_s1_selection_interface_consistency_v020"
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
            / "supplementary_figure_s1_values_v020.tsv"
        )
        atomic_write_tsv(
            source_values_path,
            list(source_rows[0].keys()),
            source_rows,
        )

        validation_path = (
            reports_dir
            / "supplementary_figure_s1_validation_v020.tsv"
        )
        atomic_write_tsv(
            validation_path,
            ["check", "passed", "observed", "expected", "severity"],
            validation_rows(validations),
        )

        caption_path = (
            attempt / "supplementary_figure_s1_caption_v020.md"
        )
        write_caption(caption_path, figure_data)

        report_path = (
            reports_dir
            / "supplementary_figure_s1_render_report_v020.md"
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
            "expected_cases": EXPECTED_CASES,
            "break_threshold": BREAK_THRESHOLD,
            "maximum_allowed_relative_difference":
                MAX_ALLOWED_RELATIVE_DIFFERENCE,
            "scientific_execution": {
                "dft": False,
                "model_loading": False,
                "training": False,
                "mlp": False,
                "lammps": False,
                "md": False,
                "new_grade_calculation": False,
            },
        }
        data_lock_path = (
            attempt / "supplementary_figure_s1_data_lock_v020.json"
        )
        atomic_write_json(data_lock_path, data_lock)

        manifest_rows = [
            {
                "artifact_id": "Supplementary_Figure_S1",
                "role": "selection_interface_consistency",
                "pdf": str(output_paths["pdf"].relative_to(attempt)),
                "svg": str(output_paths["svg"].relative_to(attempt)),
                "png": str(output_paths["png"].relative_to(attempt)),
                "tiff": str(output_paths["tiff"].relative_to(attempt)),
                "caption": str(caption_path.relative_to(attempt)),
                "status": "RENDERED_AND_VALIDATED",
                "scientific_message": (
                    "Original online and offline-exact MaxVol grades "
                    "agree for all six first-update cases."
                ),
                "mandatory_caveat": (
                    "MaxVol grade is an applicability criterion, "
                    "not a measured DFT error."
                ),
            }
        ]
        manifest_path = (
            attempt / "supplementary_figure_s1_manifest_v020.tsv"
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
                "The online selection interface and offline-exact replay "
                "are numerically consistent."
            ),
            "mandatory_caveat": (
                "This consistency audit does not measure physical DFT error."
            ),
            "next_stage": (
                "Render Supplementary Figure S2 full MaxVol-grade "
                "distributions."
            ),
        }
        summary_path = attempt / "summary_v020.json"
        atomic_write_json(summary_path, summary)

        atomic_write_text(attempt / "STATUS_v020.txt", STATUS_PASS + "\n")
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
        failure_path = attempt / "STATUS_v020.txt"
        if not failure_path.exists():
            failure_path.write_text(STATUS_FAIL + "\n", encoding="utf-8")
        raise


def synthetic_first_step_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trajectory_id in CASE_ORDER:
        expected = EXPECTED_CASES[trajectory_id]
        online = expected["online"]
        offline = expected["offline"]
        relative_difference = abs(online - offline) / offline
        rows.append(
            {
                "trajectory_id": trajectory_id,
                "temperature_K": expected["temperature_K"],
                "side": expected["side"],
                "original_online_break_grade": online,
                "offline_exact_break_mv_grade": offline,
                "online_offline_relative_difference": relative_difference,
                "threshold_class_agreement": True,
                "source_oracle_replay_classification":
                    EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
                "physical_dft_error_measured": False,
            }
        )
    return rows


def make_synthetic_fixture(root: Path) -> Path:
    attempt = root / INPUT_RELATIVE_ROOT / "attempt_20990101T000000Z"
    (attempt / "source_data").mkdir(parents=True)

    first_step_rows = synthetic_first_step_rows()
    atomic_write_tsv(
        attempt / FIRST_STEP_FILE,
        list(first_step_rows[0].keys()),
        first_step_rows,
    )

    atomic_write_json(
        attempt / ORACLE_CONTRACT_FILE,
        {
            "classification": EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
            "scientific_execution": "NONE",
        },
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
            "panels": "first-update grade and displacement",
            "primary_source_data": FIRST_STEP_FILE,
            "geometry_sources": "",
            "status": "SOURCE_DATA_READY",
            "scientific_message": (
                "First attempted updates exceed the MaxVol break threshold."
            ),
            "mandatory_caveat": (
                "MaxVol grade is not a physical DFT error."
            ),
        }
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
        FIRST_STEP_FILE,
        ORACLE_CONTRACT_FILE,
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
    with tempfile.TemporaryDirectory(prefix="supplementary_s1_v020_test_") as temp:
        root = Path(temp)
        make_synthetic_fixture(root)
        inputs = load_locked_inputs(root)
        validations = validate_inputs(inputs)
        output_base = root / "synthetic_output" / "supplementary_s1"
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
        print(
            "MAX_RELATIVE_DIFFERENCE_PERCENT="
            f"{figure_data['maximum_relative_difference_percent']:.6f}"
        )
        print("FORMATS=PDF,SVG,PNG,TIFF")
        print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render Supplementary Figure S1 from the completed v005 "
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

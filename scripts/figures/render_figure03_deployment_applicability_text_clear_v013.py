#!/usr/bin/env python3
"""
Figure 03 rendering v013
========================

Render the deployment limitation and first-update applicability diagnostic from
the completed visualization Step 01 v005 source package.

No DFT, NEB engine, model loading, training, ``mlp calc-grade``, LAMMPS, or MD
is executed. The stage reads only immutable normalized v005 source data.

Authoritative input:
    10_visualization/versions/
    v005_q1_dataviz_source_audit_source_oracle_recovery/
    CURRENT_VISUAL_SOURCE_AUDIT_V005.txt

Output:
    10_visualization/versions/
    v013_figure03_deployment_applicability_text_clear/attempt_<UTC>/

Panels
------
a. Endpoint-to-first-update MaxVol grade jump for all six attempted runs.
b. Source-oracle displacement versus first-update grade.

The plotted MaxVol grade is an applicability criterion. It is not a measured
DFT energy or force error.
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


IMPLEMENTATION_ID = "RENDER_FIGURE03_DEPLOYMENT_APPLICABILITY_TEXT_CLEAR_V013"
OUTPUT_VERSION = "v013_figure03_deployment_applicability_text_clear"
EXPECTED_INPUT_STATUS = "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"
STATUS_PASS = "PASS_FIGURE03_DEPLOYMENT_APPLICABILITY_TEXT_CLEAR_RENDERED_V013"
STATUS_FAIL = "FAIL_FIGURE03_DEPLOYMENT_APPLICABILITY_TEXT_CLEAR_V013"

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
OUTPUT_RELATIVE_ROOT = (
    "10_visualization/versions/v013_figure03_deployment_applicability_text_clear"
)
OUTPUT_POINTER = "CURRENT_FIGURE03_DEPLOYMENT_APPLICABILITY_TEXT_CLEAR_V013.txt"

FIRST_STEP_FILE = "source_data/first_step_extrapolation_v005.tsv"
RUN0_FILE = "source_data/run0_selection_consistency_v005.tsv"
AUDIT_GRADE_FILE = "source_data/audit21_grade_metrics_v005.tsv"
ORACLE_CONTRACT_FILE = "source_data/source_oracle_contract_v005.json"
STYLE_FILE = "visual_style_lock_v005.json"
FIGURE_MANIFEST_FILE = "figure_manifest_v005.tsv"
SUMMARY_FILE = "summary_v005.json"
CHECKSUM_FILE = "checksums_v005.tsv"
STATUS_FILE = "STATUS_v005.txt"

EXPECTED_SOURCE_ORACLE_CLASSIFICATION = "EXACT_SOURCE_ORACLE_REPLAY_PASS"
EXTRAPOLATION_THRESHOLD = 2.0
BREAK_THRESHOLD = 10.0
NUMERIC_TOLERANCE = 5.0e-9

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
        "endpoint": 1.0,
        "displacement_ang": 0.002037756398673096,
    },
    "T100_right": {
        "temperature_K": 100.0,
        "side": "right",
        "online": 79.987407,
        "offline": 79.969427,
        "endpoint": 0.996587,
        "displacement_ang": 0.001964944606653418,
    },
    "T300_left": {
        "temperature_K": 300.0,
        "side": "left",
        "online": 67.924938,
        "offline": 67.928927,
        "endpoint": 1.0,
        "displacement_ang": 0.002586581431461177,
    },
    "T300_right": {
        "temperature_K": 300.0,
        "side": "right",
        "online": 47.845043,
        "offline": 47.844478,
        "endpoint": 0.996587,
        "displacement_ang": 0.0027015058204460374,
    },
    "T500_left": {
        "temperature_K": 500.0,
        "side": "left",
        "online": 99.936321,
        "offline": 99.921547,
        "endpoint": 1.0,
        "displacement_ang": 0.004038176721531173,
    },
    "T500_right": {
        "temperature_K": 500.0,
        "side": "right",
        "online": 147.705216,
        "offline": 147.709445,
        "endpoint": 0.996587,
        "displacement_ang": 0.003824515164881248,
    },
}

EXPECTED_TARGETED_NEB9_GRADE_MEDIAN = 5497.731726
EXPECTED_TARGETED_NEB9_GRADE_GT10 = 7
EXPECTED_TARGETED_NEB9_COUNT = 9


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
    run0_path: Path
    audit_grade_path: Path
    oracle_contract_path: Path
    style_path: Path
    figure_manifest_path: Path
    summary_path: Path
    checksums_path: Path
    first_step_rows: list[dict[str, str]]
    run0_rows: list[dict[str, str]]
    audit_grade_rows: list[dict[str, str]]
    oracle_contract: dict[str, Any]
    style: dict[str, Any]
    summary: dict[str, Any]
    figure_manifest_row: dict[str, str]
    source_hashes: dict[str, str]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(path: Path, label: str) -> Path:
    path = path.resolve()
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
        raise FigureAuditError(f"TSV has no data rows: {path}")
    return rows


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
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    os.replace(temporary, path)


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


def close(a: float, b: float, tol: float = NUMERIC_TOLERANCE) -> bool:
    return abs(a - b) <= tol


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
    expected_size = parse_int(matches[0]["size_bytes"], f"{relative_path} size")
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
        raise FigureAuditError(f"v005 pointer target is not a directory: {attempt}")
    status = read_text(attempt / STATUS_FILE).strip()
    if status != EXPECTED_INPUT_STATUS:
        raise FigureAuditError(
            f"Unexpected v005 status: observed={status}; "
            f"expected={EXPECTED_INPUT_STATUS}"
        )
    return attempt


def load_locked_inputs(root: Path) -> LockedInputs:
    attempt = resolve_input_attempt(root)
    checksum_rows = read_tsv(attempt / CHECKSUM_FILE)
    required_relatives = (
        FIRST_STEP_FILE,
        RUN0_FILE,
        AUDIT_GRADE_FILE,
        ORACLE_CONTRACT_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    hashes = {
        relative: verify_checksum_entry(attempt, checksum_rows, relative)
        for relative in required_relatives
    }

    figure_rows = read_tsv(attempt / FIGURE_MANIFEST_FILE)
    matches = [row for row in figure_rows if row.get("figure_id") == "Figure_3"]
    if len(matches) != 1:
        raise FigureAuditError(
            f"Expected one Figure_3 manifest row; found {len(matches)}"
        )
    figure_row = matches[0]
    if figure_row.get("status") != "SOURCE_DATA_READY":
        raise FigureAuditError(
            "Figure_3 is not marked SOURCE_DATA_READY: "
            f"{figure_row.get('status')!r}"
        )

    return LockedInputs(
        attempt=attempt,
        first_step_path=attempt / FIRST_STEP_FILE,
        run0_path=attempt / RUN0_FILE,
        audit_grade_path=attempt / AUDIT_GRADE_FILE,
        oracle_contract_path=attempt / ORACLE_CONTRACT_FILE,
        style_path=attempt / STYLE_FILE,
        figure_manifest_path=attempt / FIGURE_MANIFEST_FILE,
        summary_path=attempt / SUMMARY_FILE,
        checksums_path=attempt / CHECKSUM_FILE,
        first_step_rows=read_tsv(attempt / FIRST_STEP_FILE),
        run0_rows=read_tsv(attempt / RUN0_FILE),
        audit_grade_rows=read_tsv(attempt / AUDIT_GRADE_FILE),
        oracle_contract=read_json(attempt / ORACLE_CONTRACT_FILE),
        style=read_json(attempt / STYLE_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        figure_manifest_row=figure_row,
        source_hashes=hashes,
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


def audit_grade_key(
    row: Mapping[str, str],
) -> tuple[str, str]:
    return row.get("model", ""), row.get("subset", "")


def validate_inputs(inputs: LockedInputs) -> list[Validation]:
    validations: list[Validation] = []
    rows = first_step_by_id(inputs.first_step_rows)

    validations.append(
        Validation(
            "first_step_case_ids_exact",
            set(rows) == set(CASE_ORDER),
            str(sorted(rows)),
            str(sorted(CASE_ORDER)),
        )
    )

    for trajectory_id in CASE_ORDER:
        row = rows[trajectory_id]
        expected = EXPECTED_CASES[trajectory_id]
        observed_values = {
            "temperature_K": parse_float(
                row["temperature_K"], f"{trajectory_id} temperature"
            ),
            "online": parse_float(
                row["original_online_break_grade"],
                f"{trajectory_id} online grade",
            ),
            "offline": parse_float(
                row["offline_exact_break_mv_grade"],
                f"{trajectory_id} offline grade",
            ),
            "endpoint": parse_float(
                row["offline_endpoint_mv_grade"],
                f"{trajectory_id} endpoint grade",
            ),
            "displacement_ang": parse_float(
                row["break_vs_endpoint_max_abs_ang"],
                f"{trajectory_id} displacement",
            ),
        }
        for field, observed in observed_values.items():
            target = float(expected[field])
            validations.append(
                Validation(
                    f"{trajectory_id}_{field}_locked_value",
                    close(observed, target),
                    f"{observed:.16g}",
                    f"{target:.16g}",
                )
            )

        side = row["side"].strip()
        validations.append(
            Validation(
                f"{trajectory_id}_side",
                side == expected["side"],
                side,
                str(expected["side"]),
            )
        )
        validations.extend(
            [
                Validation(
                    f"{trajectory_id}_endpoint_in_domain",
                    observed_values["endpoint"] < EXTRAPOLATION_THRESHOLD,
                    f"{observed_values['endpoint']:.9f}",
                    f"< {EXTRAPOLATION_THRESHOLD}",
                ),
                Validation(
                    f"{trajectory_id}_first_update_breaks",
                    observed_values["offline"] > BREAK_THRESHOLD,
                    f"{observed_values['offline']:.9f}",
                    f"> {BREAK_THRESHOLD}",
                ),
                Validation(
                    f"{trajectory_id}_threshold_class_agreement",
                    parse_bool(
                        row["threshold_class_agreement"],
                        f"{trajectory_id} threshold_class_agreement",
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
                    f"{trajectory_id}_geometry_provenance_recovered",
                    parse_bool(
                        row["geometry_provenance_exactly_recovered"],
                        f"{trajectory_id} geometry provenance",
                    ),
                    row["geometry_provenance_exactly_recovered"],
                    "True",
                ),
                Validation(
                    f"{trajectory_id}_no_persistent_id_claim",
                    not parse_bool(
                        row["persistent_lammps_id_claim_allowed"],
                        f"{trajectory_id} persistent ID claim",
                    ),
                    row["persistent_lammps_id_claim_allowed"],
                    "False",
                ),
                Validation(
                    f"{trajectory_id}_no_physical_dft_error_measurement",
                    not parse_bool(
                        row["physical_dft_error_measured"],
                        f"{trajectory_id} physical DFT error",
                    ),
                    row["physical_dft_error_measured"],
                    "False",
                ),
            ]
        )

    validations.append(
        Validation(
            "all_six_cases_break",
            sum(
                parse_float(
                    rows[trajectory_id]["offline_exact_break_mv_grade"],
                    f"{trajectory_id} offline grade",
                ) > BREAK_THRESHOLD
                for trajectory_id in CASE_ORDER
            ) == 6,
            str(
                sum(
                    parse_float(
                        rows[trajectory_id]["offline_exact_break_mv_grade"],
                        f"{trajectory_id} offline grade",
                    ) > BREAK_THRESHOLD
                    for trajectory_id in CASE_ORDER
                )
            ),
            "6",
        )
    )

    relative_differences = [
        parse_float(
            rows[trajectory_id]["online_offline_relative_difference"],
            f"{trajectory_id} online/offline relative difference",
        )
        for trajectory_id in CASE_ORDER
    ]
    validations.append(
        Validation(
            "online_offline_grade_agreement",
            max(relative_differences) < 2.5e-4,
            f"max={max(relative_differences):.9g}",
            "< 2.5e-4",
        )
    )

    validations.extend(
        [
            Validation(
                "run0_repeat_count",
                len(inputs.run0_rows) == 6,
                str(len(inputs.run0_rows)),
                "6",
            ),
            Validation(
                "run0_controls_unchanged",
                all(
                    parse_int(row["returncode"], "run0 returncode") == 0
                    and not parse_bool(row["break_detected"], "run0 break")
                    and parse_int(row["dump_last_step"], "run0 step") == 0
                    and close(
                        parse_float(
                            row["run0_vs_endpoint_max_abs_ang"],
                            "run0 displacement",
                        ),
                        0.0,
                    )
                    and not parse_bool(
                        row["state_file_changed"],
                        "run0 state_file_changed",
                    )
                    for row in inputs.run0_rows
                ),
                "all six returncode=0, break=False, step=0, displacement=0, state unchanged",
                "True",
            ),
        ]
    )

    grade_lookup = {
        audit_grade_key(row): row for row in inputs.audit_grade_rows
    }
    targeted_neb9 = grade_lookup.get(("targeted", "neb9"))
    if targeted_neb9 is None:
        raise FigureAuditError("Missing targeted/neb9 audit-grade row")
    median = parse_float(
        targeted_neb9["grade_median"],
        "targeted neb9 grade median",
    )
    count = parse_int(
        targeted_neb9["configuration_count"],
        "targeted neb9 configuration count",
    )
    gt10 = parse_int(
        targeted_neb9["grade_gt_10_count"],
        "targeted neb9 grade >10 count",
    )
    validations.extend(
        [
            Validation(
                "targeted_neb9_grade_median_locked",
                close(median, EXPECTED_TARGETED_NEB9_GRADE_MEDIAN),
                f"{median:.12g}",
                f"{EXPECTED_TARGETED_NEB9_GRADE_MEDIAN:.12g}",
            ),
            Validation(
                "targeted_neb9_count_locked",
                count == EXPECTED_TARGETED_NEB9_COUNT,
                str(count),
                str(EXPECTED_TARGETED_NEB9_COUNT),
            ),
            Validation(
                "targeted_neb9_gt10_locked",
                gt10 == EXPECTED_TARGETED_NEB9_GRADE_GT10,
                str(gt10),
                str(EXPECTED_TARGETED_NEB9_GRADE_GT10),
            ),
        ]
    )

    validations.extend(
        [
            Validation(
                "source_oracle_contract_classification",
                inputs.oracle_contract.get("classification")
                == EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
                str(inputs.oracle_contract.get("classification")),
                EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
            ),
            Validation(
                "source_oracle_contract_no_usable_md",
                inputs.oracle_contract.get("usable_md_trajectory") is False,
                str(inputs.oracle_contract.get("usable_md_trajectory")),
                "False",
            ),
            Validation(
                "source_oracle_contract_no_dft_error_measurement",
                inputs.oracle_contract.get("physical_dft_error_measured") is False,
                str(inputs.oracle_contract.get("physical_dft_error_measured")),
                "False",
            ),
        ]
    )

    failures = [
        item for item in validations
        if item.severity == "ERROR" and not item.passed
    ]
    if failures:
        raise FigureAuditError(
            "Figure 3 input validation failed: "
            + "; ".join(
                f"{item.check}: {item.observed} != {item.expected}"
                for item in failures
            )
        )
    return validations


def import_plotting() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
        import matplotlib.patches as patches
        import numpy as np
    except Exception as exc:
        raise FigureAuditError(
            "Matplotlib and NumPy are required for Figure 3 rendering: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return matplotlib, plt, ticker, patches, np


def configure_matplotlib(matplotlib: Any, style: Mapping[str, Any]) -> None:
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
            "axes.titlesize": 8.7,
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
            "savefig.facecolor": style["palette"]["background"],
            "figure.facecolor": style["palette"]["background"],
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
    return x1 > x0 and y1 > y0 and (x1 - x0) * (y1 - y0) > minimum_area_pixels


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


def case_rows(inputs: LockedInputs) -> list[dict[str, Any]]:
    by_id = first_step_by_id(inputs.first_step_rows)
    rows: list[dict[str, Any]] = []
    for trajectory_id in CASE_ORDER:
        row = by_id[trajectory_id]
        rows.append(
            {
                "trajectory_id": trajectory_id,
                "temperature_K": parse_float(
                    row["temperature_K"], "temperature_K"
                ),
                "side": row["side"],
                "online_grade": parse_float(
                    row["original_online_break_grade"], "online grade"
                ),
                "offline_grade": parse_float(
                    row["offline_exact_break_mv_grade"], "offline grade"
                ),
                "endpoint_grade": parse_float(
                    row["offline_endpoint_mv_grade"], "endpoint grade"
                ),
                "displacement_ang": parse_float(
                    row["break_vs_endpoint_max_abs_ang"], "displacement"
                ),
                "displacement_milliangstrom": 1000.0 * parse_float(
                    row["break_vs_endpoint_max_abs_ang"], "displacement"
                ),
                "relative_grade_difference": parse_float(
                    row["online_offline_relative_difference"],
                    "relative grade difference",
                ),
            }
        )
    return rows


def render_figure(
    inputs: LockedInputs,
    output_base: Path,
) -> dict[str, Any]:
    matplotlib, plt, ticker, patches, np = import_plotting()
    configure_matplotlib(matplotlib, inputs.style)
    palette = inputs.style["palette"]

    rows = case_rows(inputs)
    endpoint_color = palette["dft_reference"]
    first_update_color = palette["targeted_model"]
    threshold_color = palette["basin_model"]
    background = palette["background"]

    side_colors = {"left": threshold_color, "right": first_update_color}
    side_markers = {"left": "^", "right": "o"}

    figure = plt.figure(figsize=(9.35, 6.45), constrained_layout=False)
    grid = figure.add_gridspec(
        1,
        2,
        left=0.076,
        right=0.988,
        bottom=0.255,
        top=0.925,
        wspace=0.53,
        width_ratios=[1.45, 1.00],
    )
    ax_a = figure.add_subplot(grid[0, 0])
    ax_b = figure.add_subplot(grid[0, 1])

    tracked: list[tuple[str, Any]] = []

    # ------------------------------------------------------------------
    # a. Endpoint -> first-update grade jump.
    # ------------------------------------------------------------------
    x_positions = np.arange(len(rows), dtype=float)
    for index, row in enumerate(rows):
        x_endpoint = index - 0.16
        x_update = index + 0.16
        ax_a.plot(
            [x_endpoint, x_update],
            [row["endpoint_grade"], row["offline_grade"]],
            color="#8A8A8A",
            linewidth=1.05,
            zorder=1,
        )
        ax_a.scatter(
            [x_endpoint],
            [row["endpoint_grade"]],
            s=46,
            marker="o",
            facecolor=background,
            edgecolor=endpoint_color,
            linewidth=1.25,
            zorder=3,
        )
        ax_a.scatter(
            [x_update],
            [row["offline_grade"]],
            s=54,
            marker="s",
            facecolor=first_update_color,
            edgecolor=first_update_color,
            linewidth=0.9,
            zorder=4,
        )

    ax_a.axhline(
        EXTRAPOLATION_THRESHOLD,
        color=threshold_color,
        linestyle="--",
        linewidth=1.0,
        zorder=0,
    )
    ax_a.axhline(
        BREAK_THRESHOLD,
        color=threshold_color,
        linestyle="--",
        linewidth=1.0,
        zorder=0,
    )
    tracked.append((
        "a_extrapolation_threshold_label",
        ax_a.text(
            5.46,
            EXTRAPOLATION_THRESHOLD * 1.12,
            r"$\gamma=2$ extrapolation",
            ha="right",
            va="bottom",
            fontsize=7.1,
            color=threshold_color,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.40, "alpha": 0.88},
        ),
    ))
    tracked.append((
        "a_break_threshold_label",
        ax_a.text(
            5.46,
            BREAK_THRESHOLD * 1.10,
            r"$\gamma=10$ applicability break",
            ha="right",
            va="bottom",
            fontsize=7.1,
            color=threshold_color,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.40, "alpha": 0.88},
        ),
    ))
    tracked.append((
        "a_main_callout",
        ax_a.text(
            0.965,
            0.925,
            r"6/6 first updates exceed $\gamma=10$",
            transform=ax_a.transAxes,
            ha="right",
            va="top",
            fontsize=7.6,
            fontweight="bold",
            color=first_update_color,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.55, "alpha": 0.90},
        ),
    ))

    ax_a.set_yscale("log")
    ax_a.set_ylim(0.65, 280.0)
    ax_a.set_xlim(-0.62, 5.62)
    ax_a.set_xticks(x_positions)
    ax_a.set_xticklabels([
        f"{int(row['temperature_K'])} K\n"
        f"{'L' if row['side'] == 'left' else 'R'}"
        for row in rows
    ])
    ax_a.set_ylabel(r"MaxVol applicability grade, $\gamma$")
    ax_a.set_xlabel("Attempted run")
    title_a = ax_a.set_title(
        "Immediate first-update applicability failure",
        loc="left",
        x=0.025,
        pad=12,
    )
    tracked.append(("a_title", title_a))
    panel_a = add_panel_label(ax_a, "a")
    tracked.append(("a_panel_label", panel_a))
    clean_axis(ax_a)
    ax_a.grid(axis="y", which="major", color="#D9D9D9", linewidth=0.6)
    ax_a.grid(axis="y", which="minor", visible=False)
    ax_a.scatter([], [], s=46, marker="o", facecolor=background, edgecolor=endpoint_color, linewidth=1.2, label="Endpoint")
    ax_a.scatter([], [], s=54, marker="s", facecolor=first_update_color, edgecolor=first_update_color, label="First attempted update")
    legend_a = ax_a.legend(
        loc="upper left",
        bbox_to_anchor=(0.015, 0.865),
        frameon=False,
        borderaxespad=0.20,
        handletextpad=0.50,
        labelspacing=0.45,
        fontsize=7.0,
    )
    tracked.append(("a_legend", legend_a))

    # ------------------------------------------------------------------
    # b. Displacement versus grade.
    # ------------------------------------------------------------------
    label_offsets = {
        "T100_left": (10, -16),
        "T100_right": (12, 10),
        "T300_left": (-12, 14),
        "T300_right": (12, -16),
        "T500_left": (12, -16),
        "T500_right": (0, 16),
    }
    for row in rows:
        color = side_colors[row["side"]]
        marker = side_markers[row["side"]]
        ax_b.scatter(
            [row["displacement_milliangstrom"]],
            [row["offline_grade"]],
            s=60,
            marker=marker,
            facecolor=color,
            edgecolor=color,
            linewidth=1.0,
            zorder=3,
        )
        temperature = int(row["temperature_K"])
        label = f"{temperature} {'L' if row['side'] == 'left' else 'R'}"
        dx, dy = label_offsets[row["trajectory_id"]]
        artist = ax_b.annotate(
            label,
            (row["displacement_milliangstrom"], row["offline_grade"]),
            xytext=(dx, dy),
            textcoords="offset points",
            ha="left" if dx >= 0 else "right",
            va="bottom" if dy >= 0 else "top",
            fontsize=7.1,
            color="#333333",
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.25, "alpha": 0.85},
        )
        tracked.append((f"b_label_{row['trajectory_id']}", artist))

    ax_b.axhline(BREAK_THRESHOLD, color=first_update_color, linestyle="--", linewidth=1.0, zorder=0)
    tracked.append((
        "b_threshold_label",
        ax_b.text(
            4.43,
            BREAK_THRESHOLD + 3.5,
            r"break threshold $\gamma=10$",
            ha="right",
            va="bottom",
            fontsize=6.6,
            color=first_update_color,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.32, "alpha": 0.88},
        ),
    ))
    minimum_disp = min(row["displacement_milliangstrom"] for row in rows)
    maximum_disp = max(row["displacement_milliangstrom"] for row in rows)
    tracked.append((
        "b_displacement_range",
        ax_b.text(
            1.69,
            159.5,
            f"{minimum_disp:.2f}-{maximum_disp:.2f} mÅ displacement",
            ha="left",
            va="top",
            fontsize=6.9,
            color=first_update_color,
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "pad": 0.35,
                "alpha": 0.88,
            },
        ),
    ))

    ax_b.set_xlim(1.58, 4.55)
    ax_b.set_ylim(0, 174)
    ax_b.set_xlabel(r"Maximum displacement ($10^{-3}$ $\mathrm{\AA}$)")
    ax_b.set_ylabel(r"First-update grade, $\gamma$")
    title_b = ax_b.set_title(
        "Rejection after tiny geometric updates",
        loc="left",
        x=0.025,
        pad=12,
    )
    tracked.append(("b_title", title_b))
    panel_b = add_panel_label(ax_b, "b")
    tracked.append(("b_panel_label", panel_b))
    clean_axis(ax_b)
    ax_b.yaxis.set_major_locator(ticker.MultipleLocator(40))

    # Figure caption block / footnote.
    tracked.append((
        "figure_footnote",
        figure.text(
            0.080,
            0.080,
            "Figure 2 showed strong frozen static fidelity, but Figure 3 shows no usable free-update trajectory.\n"
            "First-update geometries are exact source-oracle diagnostic pairs, not MD trajectories; "
            "persistent LAMMPS atom identities are not asserted.",
            ha="left",
            va="bottom",
            fontsize=6.10,
            color="#444444",
        ),
    ))

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
        "Title": "Immediate first-update applicability failure diagnostic",
        "Author": "Reproducible project rendering",
        "Subject": "Static fidelity versus MaxVol deployment applicability",
        "Keywords": "malonaldehyde, MTP, MaxVol, applicability, deployment",
        "Creator": IMPLEMENTATION_ID,
    }
    figure.savefig(outputs["pdf"], format="pdf", bbox_inches="tight", pad_inches=0.06, metadata=metadata)
    figure.savefig(outputs["svg"], format="svg", bbox_inches="tight", pad_inches=0.06, metadata={"Title": metadata["Title"], "Description": metadata["Subject"]})
    figure.savefig(outputs["png"], format="png", dpi=600, bbox_inches="tight", pad_inches=0.06, metadata={"Title": metadata["Title"], "Description": metadata["Subject"]})
    figure.savefig(outputs["tiff"], format="tiff", dpi=600, bbox_inches="tight", pad_inches=0.06, pil_kwargs={"compression": "tiff_lzw"})
    plt.close(figure)

    grade_lookup = {audit_grade_key(row): row for row in inputs.audit_grade_rows}
    targeted_neb9 = grade_lookup[("targeted", "neb9")]
    neb9_median = parse_float(targeted_neb9["grade_median"], "targeted neb9 median")
    neb9_gt10 = parse_int(targeted_neb9["grade_gt_10_count"], "targeted neb9 gt10")

    return {
        "outputs": {key: str(path) for key, path in outputs.items()},
        "case_count": len(rows),
        "endpoint_grade_range": [min(row["endpoint_grade"] for row in rows), max(row["endpoint_grade"] for row in rows)],
        "first_update_grade_range": [min(row["offline_grade"] for row in rows), max(row["offline_grade"] for row in rows)],
        "displacement_milliangstrom_range": [minimum_disp, maximum_disp],
        "maximum_online_offline_relative_difference": max(row["relative_grade_difference"] for row in rows),
        "targeted_neb9_grade_median": neb9_median,
        "targeted_neb9_grade_gt10_count": neb9_gt10,
        "layout_validation": layout_validation,
        "scientific_execution": "NONE",
    }


def verify_rendered_files(output_paths: Mapping[str, Path]) -> list[Validation]:
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
            f"has_svg={'<svg' in svg_text}; has_close={'</svg>' in svg_text}",
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
                            width >= 3600 and height >= 3000,
                            f"{width}x{height}",
                            "at least 3600x3000 pixels",
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
            + "; ".join(f"{item.check}={item.observed}" for item in failures)
        )
    return validations


def create_output_attempt(root: Path) -> tuple[Path, Path]:
    version_root = (root / OUTPUT_RELATIVE_ROOT).resolve()
    version_root.mkdir(parents=True, exist_ok=True)
    attempt = version_root / f"attempt_{utc_stamp()}"
    if attempt.exists():
        raise FigureAuditError(f"Output attempt already exists: {attempt}")
    attempt.mkdir(parents=False, exist_ok=False)
    return version_root, attempt


def snapshot_inputs(inputs: LockedInputs, attempt: Path) -> dict[str, Path]:
    snapshot_dir = attempt / "source_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    outputs: dict[str, Path] = {}
    for relative in (
        FIRST_STEP_FILE,
        RUN0_FILE,
        AUDIT_GRADE_FILE,
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


def build_panel_values(inputs: LockedInputs) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in case_rows(inputs):
        output.append(
            {
                "trajectory_id": row["trajectory_id"],
                "temperature_K": row["temperature_K"],
                "side": row["side"],
                "endpoint_grade": row["endpoint_grade"],
                "online_grade": row["online_grade"],
                "offline_exact_grade": row["offline_grade"],
                "displacement_ang": row["displacement_ang"],
                "displacement_milliangstrom": row[
                    "displacement_milliangstrom"
                ],
                "online_offline_relative_difference": row[
                    "relative_grade_difference"
                ],
                "break_threshold": BREAK_THRESHOLD,
                "first_update_rejected": row["offline_grade"] > BREAK_THRESHOLD,
            }
        )
    return output


def write_caption(path: Path, figure_data: Mapping[str, Any]) -> None:
    minimum_grade, maximum_grade = figure_data["first_update_grade_range"]
    minimum_disp, maximum_disp = figure_data[
        "displacement_milliangstrom_range"
    ]
    caption = f"""# Figure 3. Static PBE-path fidelity does not guarantee deployment coverage

**a,** MaxVol applicability grade at the frozen endpoint and after the first
attempted integration update for six targeted-MTP runs at 100, 300, and 500 K
from the left and right endpoints. Endpoints remain near grade one, whereas all
six first updates exceed the break threshold, gamma = 10. **b,** First-update
grade versus exact source-oracle maximum displacement. Displacements of only
{minimum_disp:.2f}-{maximum_disp:.2f} milliangstrom coincide with grades of
{minimum_grade:.1f}-{maximum_grade:.1f}. **c,** Original online grades agree
with offline-exact grades, supporting selection-interface consistency.
**d,** Evidence chain from accurate frozen static predictions to immediate
deployment rejection.

MaxVol grade is an applicability criterion, not a measured DFT energy or force
error. The source-oracle endpoint/first-update pairs are diagnostic two-frame
comparisons, not MD trajectories. No thermal stability or proton-transfer
kinetics were assessed.
"""
    atomic_write_text(path, caption)


def write_report(
    path: Path,
    inputs: LockedInputs,
    validations: Sequence[Validation],
    figure_data: Mapping[str, Any],
    output_paths: Mapping[str, Path],
) -> None:
    report = f"""# Figure 3 deployment-applicability text-clear render report v013

Created UTC: `{utc_iso()}`

Status: `{STATUS_PASS}`

## Scope

This stage rendered the deployment limitation and first-update applicability
diagnostic from the completed v005 source package. It did not execute DFT, an
NEB engine, model loading, training, `mlp calc-grade`, LAMMPS, or molecular
dynamics.

## Locked input

- v005 attempt: `{inputs.attempt}`
- first-step source: `{inputs.first_step_path}`
- run-0 controls: `{inputs.run0_path}`
- frozen audit-grade source: `{inputs.audit_grade_path}`
- source-oracle contract: `{inputs.oracle_contract_path}`

Every input was verified against `checksums_v005.tsv`.

## Main numerical results

- endpoint grade range: `{figure_data["endpoint_grade_range"]}`
- first-update grade range: `{figure_data["first_update_grade_range"]}`
- exact maximum-displacement range, milliangstrom:
  `{figure_data["displacement_milliangstrom_range"]}`
- targeted NEB9 median grade:
  `{figure_data["targeted_neb9_grade_median"]}`
- targeted NEB9 images above grade 10:
  `{figure_data["targeted_neb9_grade_gt10_count"]}/9`
- maximum online/offline relative grade difference:
  `{figure_data["maximum_online_offline_relative_difference"]}`

## Interpretation

Figure 2 established strong frozen static fidelity for the targeted model, but the present figure shows that all six attempted free-integration first updates leave the selected active-set applicability domain immediately. The text-clear two-panel design emphasizes two claims only: (i) every first attempted update exceeds the break threshold, and (ii) this breakage already occurs after tiny exact source-oracle displacements.

This does not establish a large physical DFT error on the rejected configurations because no new DFT single points were evaluated there.

## Layout validation

Tracked text objects: `{figure_data["layout_validation"]["tracked_text_count"]}`

Detected tracked-text overlaps:
`{figure_data["layout_validation"]["overlap_count"]}`

Tracked text outside canvas:
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


def write_checksums(attempt: Path) -> Path:
    checksum_path = attempt / "checksums_v013.tsv"
    rows: list[dict[str, Any]] = []
    for path in sorted(attempt.rglob("*")):
        if not path.is_file() or path == checksum_path:
            continue
        rows.append(
            {
                "relative_path": str(path.relative_to(attempt)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    atomic_write_tsv(
        checksum_path,
        ["relative_path", "size_bytes", "sha256"],
        rows,
    )
    return checksum_path


def update_pointer(version_root: Path, attempt: Path) -> Path:
    pointer = version_root / OUTPUT_POINTER
    temporary = version_root / f".{OUTPUT_POINTER}.tmp.{os.getpid()}"
    temporary.write_text(str(attempt.resolve()) + "\n", encoding="utf-8")
    os.replace(temporary, pointer)
    return pointer


def validation_rows(
    validations: Sequence[Validation],
) -> list[dict[str, Any]]:
    return [dataclasses.asdict(item) for item in validations]


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
        print(f"RUN0_ROWS={len(inputs.run0_rows)}")
        print(f"AUDIT_GRADE_ROWS={len(inputs.audit_grade_rows)}")
        print(f"VALIDATION_CHECKS={len(validations)}")
        print("SCIENTIFIC_EXECUTION=NONE")
        return 0

    version_root, attempt = create_output_attempt(root)
    try:
        figures_dir = attempt / "figures"
        reports_dir = attempt / "reports"
        data_dir = attempt / "source_data"
        figures_dir.mkdir(parents=True, exist_ok=False)
        reports_dir.mkdir(parents=True, exist_ok=False)
        data_dir.mkdir(parents=True, exist_ok=False)

        snapshot_paths = snapshot_inputs(inputs, attempt)
        output_base = figures_dir / "figure03_deployment_applicability_text_clear_v013"
        figure_data = render_figure(inputs, output_base)
        output_paths = {
            key: Path(value) for key, value in figure_data["outputs"].items()
        }
        validations.extend(verify_rendered_files(output_paths))

        panel_values = build_panel_values(inputs)
        panel_values_path = data_dir / "figure03_case_values_v013.tsv"
        atomic_write_tsv(
            panel_values_path,
            list(panel_values[0].keys()),
            panel_values,
        )

        validation_path = reports_dir / "figure03_validation_v013.tsv"
        atomic_write_tsv(
            validation_path,
            ["check", "passed", "observed", "expected", "severity"],
            validation_rows(validations),
        )

        caption_path = attempt / "figure03_caption_v013.md"
        write_caption(caption_path, figure_data)

        report_path = reports_dir / "figure03_render_report_v013.md"
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
            "expected_cases": EXPECTED_CASES,
            "thresholds": {
                "extrapolation": EXTRAPOLATION_THRESHOLD,
                "break": BREAK_THRESHOLD,
            },
            "scientific_execution": {
                "dft": False,
                "neb_engine": False,
                "model_loading": False,
                "training": False,
                "mlp_calc_grade": False,
                "lammps": False,
                "md": False,
            },
        }
        lock_path = attempt / "figure03_data_lock_v013.json"
        atomic_write_json(lock_path, data_lock)

        manifest_rows = [
            {
                "artifact_id": "Figure_3",
                "role": "deployment_applicability_diagnostic",
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
        manifest_path = attempt / "figure03_manifest_v013.tsv"
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
                "data_lock": str(lock_path),
                "panel_values": str(panel_values_path),
                "source_snapshot": {
                    key: str(value) for key, value in snapshot_paths.items()
                },
            },
            "scientific_claim": (
                "Static frozen-path fidelity does not guarantee deployment "
                "coverage: all six first attempted updates were immediately "
                "rejected by the MaxVol applicability criterion."
            ),
            "mandatory_caveat": (
                "MaxVol grade is not a measured DFT error, and the diagnostic "
                "pairs are not MD trajectories."
            ),
            "next_stage": (
                "Render Figure 4 secondary MTP-NEB structural diagnostic."
            ),
        }
        summary_path = attempt / "summary_v013.json"
        atomic_write_json(summary_path, summary)

        atomic_write_text(attempt / "STATUS_v013.txt", STATUS_PASS + "\n")
        checksums_path = write_checksums(attempt)
        pointer = update_pointer(version_root, attempt)

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
        print(f"CURRENT_POINTER={pointer}")
        print("SCIENTIFIC_EXECUTION=NONE")
        return 0
    except Exception:
        failure_path = attempt / "STATUS_v013.txt"
        if not failure_path.exists():
            failure_path.write_text(STATUS_FAIL + "\n", encoding="utf-8")
        raise


def make_synthetic_fixture(root: Path) -> Path:
    attempt = root / INPUT_RELATIVE_ROOT / "attempt_20990101T000000Z"
    attempt.mkdir(parents=True, exist_ok=False)
    (attempt / "source_data").mkdir()

    first_step_rows: list[dict[str, Any]] = []
    for trajectory_id in CASE_ORDER:
        expected = EXPECTED_CASES[trajectory_id]
        online = expected["online"]
        offline = expected["offline"]
        endpoint = expected["endpoint"]
        displacement = expected["displacement_ang"]
        first_step_rows.append(
            {
                "trajectory_id": trajectory_id,
                "temperature_K": expected["temperature_K"],
                "side": expected["side"],
                "seed": 0,
                "original_online_break_grade": online,
                "preselected_feature_mv_grade": online,
                "canonicalization_mode": "species_assignment",
                "canonicalization_candidate_count": 288,
                "raw_atom_ids": "1,2,3,4,5,6,7,8,9",
                "raw_atom_types": "1,0,2,1,2,0,1,0,1",
                "canonical_order_zero_based": "4,0,5,6,7,8,1,2,3",
                "break_vs_endpoint_max_abs_ang": displacement,
                "break_vs_endpoint_rms_ang": displacement / 2.7,
                "break_vs_endpoint_kabsch_rmsd_ang": displacement / 4.0,
                "break_vs_endpoint_pair_distance_max_abs_delta_ang": displacement * 1.2,
                "break_vs_dump0_max_abs_ang": displacement,
                "break_vs_dump0_rms_ang": displacement / 2.7,
                "break_vs_dump0_kabsch_rmsd_ang": displacement / 4.0,
                "dump0_vs_endpoint_max_abs_ang": 0.0,
                "dump0_vs_endpoint_rms_ang": 0.0,
                "dump0_vs_endpoint_kabsch_rmsd_ang": 0.0,
                "break_qpt_ang": -0.48 if expected["side"] == "left" else 0.48,
                "break_roo_ang": 2.499,
                "break_minimum_pair_ang": 1.04,
                "break_maximum_span_ang": 4.34,
                "preselected_path": "/synthetic/preselected.cfg",
                "offline_exact_break_mv_grade": offline,
                "offline_endpoint_mv_grade": endpoint,
                "online_over_offline_exact": online / offline,
                "threshold_class_agreement": True,
                "displacement_max_milliangstrom": 1000.0 * displacement,
                "displacement_rms_milliangstrom": 1000.0 * displacement / 2.7,
                "grade_jump": offline - endpoint,
                "grade_ratio_break_over_endpoint": offline / endpoint,
                "online_offline_abs_difference": abs(online - offline),
                "online_offline_relative_difference": abs(online - offline) / offline,
                "temperature_side_label": trajectory_id,
                "first_step_extrapolative": True,
                "source_oracle_replay_classification": EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
                "source_oracle_exact_position_array_path": "result.positions",
                "source_oracle_exact_position_array_paths": "result.positions",
                "source_oracle_kabsch_scalar_paths": "result.kabsch",
                "source_oracle_calculated_max_abs_ang": displacement,
                "source_oracle_calculated_component_rms_ang": displacement / 2.7,
                "source_oracle_calculated_pair_distance_max_delta_ang": displacement * 1.2,
                "source_oracle_calculated_qpt_ang": -0.48 if expected["side"] == "left" else 0.48,
                "source_oracle_calculated_roo_ang": 2.499,
                "source_oracle_provenance_sha256": "synthetic",
                "source_oracle_adapter_sha256": "synthetic",
                "geometry_provenance_exactly_recovered": True,
                "persistent_lammps_id_claim_allowed": False,
                "deployment_interpretation": "immediate_MaxVol_applicability_rejection_after_first_attempted_integration_update",
                "physical_dft_error_measured": False,
            }
        )
    atomic_write_tsv(
        attempt / FIRST_STEP_FILE,
        list(first_step_rows[0].keys()),
        first_step_rows,
    )

    run0_rows: list[dict[str, Any]] = []
    for side in ("left", "right"):
        for repeat in (1, 2, 3):
            run0_rows.append(
                {
                    "side": side,
                    "repeat": repeat,
                    "returncode": 0,
                    "break_detected": False,
                    "online_break_grade": "nan",
                    "any_online_grade": "nan",
                    "preselected_count": 0,
                    "preselected_feature_grade": "nan",
                    "dump_frame_count": 1,
                    "dump_last_step": 0,
                    "run0_vs_endpoint_max_abs_ang": 0.0,
                    "run0_vs_endpoint_rms_ang": 0.0,
                    "source_state_sha256": "synthetic",
                    "copied_state_sha256_before": "synthetic",
                    "copied_state_sha256_after": "synthetic",
                    "state_file_changed": False,
                    "directory": "/synthetic",
                }
            )
    atomic_write_tsv(
        attempt / RUN0_FILE,
        list(run0_rows[0].keys()),
        run0_rows,
    )

    grade_rows = [
        {
            "model": "basin",
            "subset": "all21",
            "configuration_count": 21,
            "grade_min": 0.995678,
            "grade_median": 184.111709,
            "grade_mean": 2726.872850904762,
            "grade_max": 14500.8526,
            "grade_gt_2_count": 19,
            "grade_gt_10_count": 19,
        },
        {
            "model": "basin",
            "subset": "basin12",
            "configuration_count": 12,
            "grade_min": 21.911523,
            "grade_median": 152.7413905,
            "grade_mean": 159.80299483333332,
            "grade_max": 451.651071,
            "grade_gt_2_count": 12,
            "grade_gt_10_count": 12,
        },
        {
            "model": "basin",
            "subset": "neb9",
            "configuration_count": 9,
            "grade_min": 0.995678,
            "grade_median": 6678.371548,
            "grade_mean": 6149.632659,
            "grade_max": 14500.8526,
            "grade_gt_2_count": 7,
            "grade_gt_10_count": 7,
        },
        {
            "model": "targeted",
            "subset": "all21",
            "configuration_count": 21,
            "grade_min": 0.996587,
            "grade_median": 337.381367,
            "grade_mean": 2397.292358238095,
            "grade_max": 12326.803231,
            "grade_gt_2_count": 19,
            "grade_gt_10_count": 19,
        },
        {
            "model": "targeted",
            "subset": "basin12",
            "configuration_count": 12,
            "grade_min": 55.26369,
            "grade_median": 302.946011,
            "grade_mean": 312.0563424166667,
            "grade_max": 871.164892,
            "grade_gt_2_count": 12,
            "grade_gt_10_count": 12,
        },
        {
            "model": "targeted",
            "subset": "neb9",
            "configuration_count": 9,
            "grade_min": 0.996587,
            "grade_median": EXPECTED_TARGETED_NEB9_GRADE_MEDIAN,
            "grade_mean": 5177.607046,
            "grade_max": 12326.803231,
            "grade_gt_2_count": 7,
            "grade_gt_10_count": EXPECTED_TARGETED_NEB9_GRADE_GT10,
        },
    ]
    atomic_write_tsv(
        attempt / AUDIT_GRADE_FILE,
        list(grade_rows[0].keys()),
        grade_rows,
    )

    atomic_write_json(
        attempt / ORACLE_CONTRACT_FILE,
        {
            "classification": EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
            "usable_md_trajectory": False,
            "physical_dft_error_measured": False,
            "persistent_lammps_id_claim_allowed": False,
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

    figure_manifest = [
        {
            "figure_id": "Figure_3",
            "title": "Deployment limitation and first-step extrapolation",
            "panels": "a;b;c;d",
            "primary_source_data": "synthetic",
            "geometry_sources": "synthetic",
            "status": "SOURCE_DATA_READY",
            "scientific_message": (
                "Small exact source-oracle first-update displacements coincide "
                "with immediate MaxVol applicability rejection."
            ),
            "mandatory_caveat": (
                "Grade is an applicability criterion, not measured DFT error."
            ),
        }
    ]
    atomic_write_tsv(
        attempt / FIGURE_MANIFEST_FILE,
        list(figure_manifest[0].keys()),
        figure_manifest,
    )
    atomic_write_json(attempt / SUMMARY_FILE, {"status": EXPECTED_INPUT_STATUS})
    atomic_write_text(attempt / STATUS_FILE, EXPECTED_INPUT_STATUS + "\n")

    checksum_rows = []
    for relative in (
        FIRST_STEP_FILE,
        RUN0_FILE,
        AUDIT_GRADE_FILE,
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
    with tempfile.TemporaryDirectory(prefix="figure03_v013_test_") as temp:
        root = Path(temp)
        make_synthetic_fixture(root)
        inputs = load_locked_inputs(root)
        validations = validate_inputs(inputs)
        output_base = root / "synthetic_output" / "figure03"
        data = render_figure(inputs, output_base)
        paths = {key: Path(value) for key, value in data["outputs"].items()}
        validations.extend(verify_rendered_files(paths))
        if not all(item.passed for item in validations):
            raise FigureAuditError("Synthetic self-test has failed checks")
        print("SELF_TEST=PASS")
        print(f"VALIDATION_CHECKS={len(validations)}")
        print(
            "LAYOUT_OVERLAPS="
            f"{data['layout_validation']['overlap_count']}"
        )
        print("FORMATS=PDF,SVG,PNG,TIFF")
        print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render the spacious two-panel Figure 3 from the completed v005 normalized source package."
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
        help="Validate locked input data without creating an output attempt",
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

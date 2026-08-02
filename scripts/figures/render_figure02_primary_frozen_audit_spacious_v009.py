#!/usr/bin/env python3
"""
Figure 02 rendering v009
========================

Render the primary frozen-audit result from the completed visualization Step 01
v005 source package. No scientific calculation, model loading, training, DFT,
NEB engine, LAMMPS, MD, or active-set evaluation is performed.

Authoritative input:
    10_visualization/versions/
    v005_q1_dataviz_source_audit_source_oracle_recovery/
    CURRENT_VISUAL_SOURCE_AUDIT_V005.txt

Output:
    10_visualization/versions/
    v009_figure02_primary_frozen_audit_spacious/attempt_<UTC>/

The figure contains:
    a. DFT/basin/targeted NEB9 profiles
    b. lower-endpoint barriers
    c. barrier absolute errors
    d. transition-region force-component RMSE

The PBE barrier is treated only as the locked reference for the frozen audit.
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


IMPLEMENTATION_ID = "RENDER_FIGURE02_PRIMARY_FROZEN_AUDIT_V009"
OUTPUT_VERSION = "v009_figure02_primary_frozen_audit_spacious"
EXPECTED_INPUT_STATUS = "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"
STATUS_PASS = "PASS_FIGURE02_PRIMARY_FROZEN_AUDIT_SPACIOUS_RENDERED_V009"
STATUS_FAIL = "FAIL_FIGURE02_PRIMARY_FROZEN_AUDIT_SPACIOUS_V009"

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
OUTPUT_RELATIVE_ROOT = (
    "10_visualization/versions/v009_figure02_primary_frozen_audit_spacious"
)
OUTPUT_POINTER = "CURRENT_FIGURE02_PRIMARY_FROZEN_AUDIT_SPACIOUS_V009.txt"

PROFILE_FILE = "source_data/neb9_energy_profiles_v005.tsv"
BARRIER_FILE = "source_data/neb9_barrier_summary_v005.tsv"
PRIMARY_FILE = "source_data/primary_metric_summary_v005.tsv"
TRANSITION_FILE = "source_data/transition_region_force_rows_v005.tsv"
STYLE_FILE = "visual_style_lock_v005.json"
FIGURE_MANIFEST_FILE = "figure_manifest_v005.tsv"
SUMMARY_FILE = "summary_v005.json"
CHECKSUM_FILE = "checksums_v005.tsv"
STATUS_FILE = "STATUS_v005.txt"

SERIES_ORDER = ("DFT", "basin", "targeted")
MODEL_ORDER = ("basin", "targeted")
EXPECTED_IMAGES = tuple(range(1, 10))
EXPECTED_TRANSITION_IMAGES = (4, 5, 6)

EXPECTED_METRICS = {
    "dft_barrier_mev": 36.072093892926205,
    "basin_barrier_mev": 0.8263598228950286,
    "targeted_barrier_mev": 31.971700288977445,
    "basin_barrier_abs_error_mev": 35.245734070031176,
    "targeted_barrier_abs_error_mev": 4.10039360394876,
    "barrier_improvement_factor": 8.595695309857287,
    "basin_transition_force_rmse": 0.1760826457854536,
    "targeted_transition_force_rmse": 0.07868490481909636,
    "force_improvement_factor": 2.237819899385827,
}
NUMERIC_TOLERANCE = 5.0e-9
PROFILE_TOLERANCE = 5.0e-10


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
    profile_path: Path
    barrier_path: Path
    primary_path: Path
    transition_path: Path
    style_path: Path
    figure_manifest_path: Path
    summary_path: Path
    checksums_path: Path
    rows_profile: list[dict[str, str]]
    rows_barrier: list[dict[str, str]]
    rows_primary: list[dict[str, str]]
    rows_transition: list[dict[str, str]]
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
        result = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise FigureAuditError(f"Invalid integer for {label}: {value!r}") from exc
    return result


def close(a: float, b: float, tol: float = NUMERIC_TOLERANCE) -> bool:
    return abs(a - b) <= tol


def verify_checksum_entry(
    attempt: Path,
    checksum_rows: Sequence[Mapping[str, str]],
    relative_path: str,
) -> str:
    matches = [row for row in checksum_rows if row.get("relative_path") == relative_path]
    if len(matches) != 1:
        raise FigureAuditError(
            f"Expected one checksum row for {relative_path}; found {len(matches)}"
        )
    target = require_file(attempt / relative_path, relative_path)
    observed_size = target.stat().st_size
    expected_size = parse_int(matches[0]["size_bytes"], f"{relative_path} size")
    observed_hash = sha256_file(target)
    expected_hash = matches[0]["sha256"].strip()
    if observed_size != expected_size or observed_hash != expected_hash:
        raise FigureAuditError(
            f"Input checksum mismatch for {relative_path}: "
            f"size {observed_size}/{expected_size}; "
            f"sha256 {observed_hash}/{expected_hash}"
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
        PROFILE_FILE,
        BARRIER_FILE,
        PRIMARY_FILE,
        TRANSITION_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    hashes = {
        relative: verify_checksum_entry(attempt, checksum_rows, relative)
        for relative in required_relatives
    }

    figure_rows = read_tsv(attempt / FIGURE_MANIFEST_FILE)
    matches = [row for row in figure_rows if row.get("figure_id") == "Figure_2"]
    if len(matches) != 1:
        raise FigureAuditError(
            f"Expected one Figure_2 manifest row; found {len(matches)}"
        )
    figure_row = matches[0]
    if figure_row.get("status") != "SOURCE_DATA_READY_NEXT_TO_RENDER":
        raise FigureAuditError(
            "Figure_2 is not marked SOURCE_DATA_READY_NEXT_TO_RENDER: "
            f"{figure_row.get('status')!r}"
        )

    return LockedInputs(
        attempt=attempt,
        profile_path=attempt / PROFILE_FILE,
        barrier_path=attempt / BARRIER_FILE,
        primary_path=attempt / PRIMARY_FILE,
        transition_path=attempt / TRANSITION_FILE,
        style_path=attempt / STYLE_FILE,
        figure_manifest_path=attempt / FIGURE_MANIFEST_FILE,
        summary_path=attempt / SUMMARY_FILE,
        checksums_path=attempt / CHECKSUM_FILE,
        rows_profile=read_tsv(attempt / PROFILE_FILE),
        rows_barrier=read_tsv(attempt / BARRIER_FILE),
        rows_primary=read_tsv(attempt / PRIMARY_FILE),
        rows_transition=read_tsv(attempt / TRANSITION_FILE),
        style=read_json(attempt / STYLE_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        figure_manifest_row=figure_row,
        source_hashes=hashes,
    )


def rows_by_key(
    rows: Sequence[Mapping[str, str]],
    key: str,
) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        value = row[key]
        if value in output:
            raise FigureAuditError(f"Duplicate {key} value: {value!r}")
        output[value] = dict(row)
    return output


def validate_inputs(inputs: LockedInputs) -> list[Validation]:
    validations: list[Validation] = []

    profile_by_series: dict[str, list[dict[str, str]]] = {
        series: [] for series in SERIES_ORDER
    }
    unknown_series = set()
    for row in inputs.rows_profile:
        series = row.get("series", "")
        if series not in profile_by_series:
            unknown_series.add(series)
            continue
        profile_by_series[series].append(row)

    validations.append(
        Validation(
            "profile_series_exact",
            not unknown_series and all(len(profile_by_series[s]) == 9 for s in SERIES_ORDER),
            f"unknown={sorted(unknown_series)}; counts="
            + ",".join(f"{s}:{len(profile_by_series[s])}" for s in SERIES_ORDER),
            "DFT:9,basin:9,targeted:9 and no unknown series",
        )
    )

    qpt_by_image: dict[int, float] = {}
    for series, rows in profile_by_series.items():
        rows.sort(key=lambda row: parse_int(row["image"], f"{series} image"))
        images = tuple(parse_int(row["image"], f"{series} image") for row in rows)
        validations.append(
            Validation(
                f"{series}_image_sequence",
                images == EXPECTED_IMAGES,
                str(images),
                str(EXPECTED_IMAGES),
            )
        )
        for row in rows:
            image = parse_int(row["image"], f"{series} image")
            qpt = parse_float(row["qpt_ang"], f"{series} image {image} qPT")
            if image in qpt_by_image:
                if abs(qpt_by_image[image] - qpt) > PROFILE_TOLERANCE:
                    raise FigureAuditError(
                        f"qPT differs between series at image {image}"
                    )
            else:
                qpt_by_image[image] = qpt

    barrier_by_series = rows_by_key(inputs.rows_barrier, "series")
    validations.append(
        Validation(
            "barrier_series_exact",
            set(barrier_by_series) == set(SERIES_ORDER),
            str(sorted(barrier_by_series)),
            str(sorted(SERIES_ORDER)),
        )
    )

    recomputed_barriers: dict[str, float] = {}
    recomputed_max_images: dict[str, int] = {}
    for series in SERIES_ORDER:
        rows = sorted(
            profile_by_series[series],
            key=lambda row: parse_int(row["image"], f"{series} image"),
        )
        energies = [
            parse_float(
                row["delta_e_from_lower_endpoint_mev"],
                f"{series} delta energy",
            )
            for row in rows
        ]
        barrier = max(energies)
        max_image = parse_int(rows[energies.index(barrier)]["image"], "max image")
        recomputed_barriers[series] = barrier
        recomputed_max_images[series] = max_image

        table_barrier = parse_float(
            barrier_by_series[series]["lower_endpoint_barrier_mev"],
            f"{series} barrier",
        )
        table_max_image = parse_int(
            barrier_by_series[series]["maximum_image"],
            f"{series} maximum image",
        )
        validations.extend(
            [
                Validation(
                    f"{series}_barrier_matches_profile",
                    close(barrier, table_barrier),
                    f"{barrier:.15g}",
                    f"{table_barrier:.15g}",
                ),
                Validation(
                    f"{series}_maximum_image_matches_profile",
                    max_image == table_max_image,
                    str(max_image),
                    str(table_max_image),
                ),
            ]
        )

    expected_barriers = {
        "DFT": EXPECTED_METRICS["dft_barrier_mev"],
        "basin": EXPECTED_METRICS["basin_barrier_mev"],
        "targeted": EXPECTED_METRICS["targeted_barrier_mev"],
    }
    for series, expected in expected_barriers.items():
        validations.append(
            Validation(
                f"{series}_barrier_locked_value",
                close(recomputed_barriers[series], expected),
                f"{recomputed_barriers[series]:.15g}",
                f"{expected:.15g}",
            )
        )

    primary_by_metric = rows_by_key(inputs.rows_primary, "metric")
    expected_metric_names = {
        "transition_force_component_rmse_ev_ang",
        "lower_endpoint_barrier_abs_error_mev",
    }
    validations.append(
        Validation(
            "primary_metric_names_exact",
            set(primary_by_metric) == expected_metric_names,
            str(sorted(primary_by_metric)),
            str(sorted(expected_metric_names)),
        )
    )

    barrier_metric = primary_by_metric["lower_endpoint_barrier_abs_error_mev"]
    force_metric = primary_by_metric["transition_force_component_rmse_ev_ang"]

    locked_values = {
        "basin_barrier_abs_error_mev": parse_float(
            barrier_metric["basin"], "basin barrier error"
        ),
        "targeted_barrier_abs_error_mev": parse_float(
            barrier_metric["targeted"], "targeted barrier error"
        ),
        "barrier_improvement_factor": parse_float(
            barrier_metric["basin_over_targeted"], "barrier improvement"
        ),
        "basin_transition_force_rmse": parse_float(
            force_metric["basin"], "basin transition force RMSE"
        ),
        "targeted_transition_force_rmse": parse_float(
            force_metric["targeted"], "targeted transition force RMSE"
        ),
        "force_improvement_factor": parse_float(
            force_metric["basin_over_targeted"], "force improvement"
        ),
    }
    for key, observed in locked_values.items():
        expected = EXPECTED_METRICS[key]
        validations.append(
            Validation(
                f"{key}_locked_value",
                close(observed, expected),
                f"{observed:.15g}",
                f"{expected:.15g}",
            )
        )

    transition_by_model: dict[str, list[dict[str, str]]] = {
        model: [] for model in MODEL_ORDER
    }
    for row in inputs.rows_transition:
        model = row.get("model", "")
        if model not in transition_by_model:
            raise FigureAuditError(f"Unexpected transition model: {model!r}")
        transition_by_model[model].append(row)

    for model in MODEL_ORDER:
        rows = sorted(
            transition_by_model[model],
            key=lambda row: parse_int(row["image"], f"{model} image"),
        )
        images = tuple(parse_int(row["image"], f"{model} image") for row in rows)
        validations.append(
            Validation(
                f"{model}_transition_images_exact",
                images == EXPECTED_TRANSITION_IMAGES,
                str(images),
                str(EXPECTED_TRANSITION_IMAGES),
            )
        )
        component_values = [
            parse_float(
                row["force_component_rmse_ev_ang"],
                f"{model} image-level force RMSE",
            )
            for row in rows
        ]
        validations.append(
            Validation(
                f"{model}_transition_values_positive",
                all(value > 0.0 for value in component_values),
                ",".join(f"{value:.9f}" for value in component_values),
                "all > 0",
            )
        )

    validations.extend(
        [
            Validation(
                "targeted_barrier_error_lower",
                locked_values["targeted_barrier_abs_error_mev"]
                < locked_values["basin_barrier_abs_error_mev"],
                f"{locked_values['targeted_barrier_abs_error_mev']:.9f} < "
                f"{locked_values['basin_barrier_abs_error_mev']:.9f}",
                "True",
            ),
            Validation(
                "targeted_transition_force_lower",
                locked_values["targeted_transition_force_rmse"]
                < locked_values["basin_transition_force_rmse"],
                f"{locked_values['targeted_transition_force_rmse']:.9f} < "
                f"{locked_values['basin_transition_force_rmse']:.9f}",
                "True",
            ),
            Validation(
                "targeted_absolute_barrier_gate",
                locked_values["targeted_barrier_abs_error_mev"] < 50.0,
                f"{locked_values['targeted_barrier_abs_error_mev']:.9f} meV",
                "< 50 meV",
            ),
            Validation(
                "targeted_force_gate",
                locked_values["targeted_transition_force_rmse"] < 0.15,
                f"{locked_values['targeted_transition_force_rmse']:.9f} eV/A",
                "< 0.15 eV/A",
            ),
        ]
    )

    failures = [
        validation
        for validation in validations
        if validation.severity == "ERROR" and not validation.passed
    ]
    if failures:
        details = "; ".join(
            f"{item.check}: {item.observed} != {item.expected}"
            for item in failures
        )
        raise FigureAuditError(f"Figure 2 input validation failed: {details}")
    return validations


def import_plotting() -> tuple[Any, Any, Any, Any]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
        import numpy as np
    except Exception as exc:
        raise FigureAuditError(
            "Matplotlib and NumPy are required for Figure 2 rendering: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return matplotlib, plt, ticker, np


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
            "axes.titlesize": 8.6,
            "xtick.labelsize": 7.4,
            "ytick.labelsize": 7.4,
            "legend.fontsize": 7.3,
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


def add_panel_label(axis: Any, label: str) -> None:
    axis.text(
        -0.14,
        1.03,
        label,
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=10.2,
        fontweight="bold",
        clip_on=False,
    )


def clean_axis(axis: Any) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(direction="out")
    axis.grid(axis="y", linewidth=0.45, alpha=0.22, zorder=0)


def annotate_bar_values(
    axis: Any,
    bars: Sequence[Any],
    values: Sequence[float],
    formatter: Any,
    pad_fraction: float = 0.025,
) -> None:
    ymax = max(values) if values else 1.0
    pad = ymax * pad_fraction
    for bar, value in zip(bars, values):
        axis.text(
            bar.get_x() + bar.get_width() / 2.0,
            value + pad,
            formatter(value),
            ha="center",
            va="bottom",
            fontsize=7.1,
        )





def render_figure(
    inputs: LockedInputs,
    output_base: Path,
) -> dict[str, Any]:
    matplotlib, plt, ticker, np = import_plotting()
    configure_matplotlib(matplotlib, inputs.style)
    palette = inputs.style["palette"]

    profile_by_series: dict[str, list[dict[str, str]]] = {
        series: [] for series in SERIES_ORDER
    }
    for row in inputs.rows_profile:
        profile_by_series[row["series"]].append(row)
    for rows in profile_by_series.values():
        rows.sort(key=lambda row: parse_int(row["image"], "image"))

    barriers = rows_by_key(inputs.rows_barrier, "series")
    primary = rows_by_key(inputs.rows_primary, "metric")
    transition_by_model: dict[str, list[dict[str, str]]] = {
        model: [] for model in MODEL_ORDER
    }
    for row in inputs.rows_transition:
        transition_by_model[row["model"]].append(row)
    for rows in transition_by_model.values():
        rows.sort(key=lambda row: parse_int(row["image"], "transition image"))

    colors = {
        "DFT": palette["dft_reference"],
        "basin": palette["basin_model"],
        "targeted": palette["targeted_model"],
    }
    labels = {
        "DFT": "DFT reference",
        "basin": "Basin-trained MTP",
        "targeted": "Transition-targeted MTP",
    }
    markers = {"DFT": "o", "basin": "^", "targeted": "s"}
    linestyles = {"DFT": "-", "basin": "--", "targeted": "-"}

    figure = plt.figure(figsize=(8.0, 5.55), constrained_layout=False)
    grid = figure.add_gridspec(
        3,
        2,
        width_ratios=(1.62, 1.0),
        height_ratios=(1.0, 1.0, 1.0),
        left=0.078,
        right=0.988,
        bottom=0.225,
        top=0.955,
        wspace=0.44,
        hspace=0.82,
    )
    ax_a = figure.add_subplot(grid[:, 0])
    ax_b = figure.add_subplot(grid[0, 1])
    ax_c = figure.add_subplot(grid[1, 1])
    ax_d = figure.add_subplot(grid[2, 1])

    # ------------------------------------------------------------------
    # a. Frozen NEB9 profile
    # ------------------------------------------------------------------
    ax_a.axvspan(
        -0.15,
        0.15,
        facecolor=palette["transition_region_fill"],
        edgecolor="none",
        alpha=0.82,
        zorder=0,
    )
    all_profile_values: list[float] = []
    for series in SERIES_ORDER:
        rows = profile_by_series[series]
        x = np.array(
            [parse_float(row["qpt_ang"], f"{series} qPT") for row in rows]
        )
        y = np.array(
            [
                parse_float(
                    row["delta_e_from_lower_endpoint_mev"],
                    f"{series} relative energy",
                )
                for row in rows
            ]
        )
        all_profile_values.extend(float(value) for value in y)
        ax_a.plot(
            x,
            y,
            color=colors[series],
            linestyle=linestyles[series],
            marker=markers[series],
            markersize=4.4,
            linewidth=2.15 if series == "DFT" else 1.9,
            markerfacecolor=(
                "white" if series in {"DFT", "basin"} else colors[series]
            ),
            markeredgecolor=colors[series],
            markeredgewidth=0.95,
            label=labels[series],
            zorder={"DFT": 4, "targeted": 3, "basin": 2}[series],
        )

    data_min = min(all_profile_values)
    data_max = max(all_profile_values)
    data_span = max(data_max - data_min, 1.0)
    lower = min(-1.4, data_min - 0.09 * data_span)
    upper = data_max + 0.10 * data_span
    ax_a.set_ylim(lower, upper)
    ax_a.axhline(
        0.0,
        color="#777777",
        linewidth=0.65,
        linestyle="-",
        alpha=0.65,
        zorder=1,
    )
    ax_a.text(
        0.0,
        lower + 0.11 * (upper - lower),
        r"$|q_{\mathrm{PT}}|\leq0.15\ \mathrm{\AA}$",
        ha="center",
        va="bottom",
        fontsize=6.9,
        bbox={
            "boxstyle": "round,pad=0.20",
            "facecolor": "white",
            "edgecolor": "none",
            "alpha": 0.86,
        },
        zorder=6,
    )
    ax_a.set_xlabel(
        r"Proton-transfer coordinate, $q_{\mathrm{PT}}$ ($\mathrm{\AA}$)"
    )
    ax_a.set_ylabel("Relative energy (meV)")
    ax_a.set_title(
        "Frozen independent PBE NEB9 profile",
        loc="left",
        x=0.05,
        pad=10,
        fontweight="normal",
    )
    ax_a.set_xlim(-0.53, 0.53)
    ax_a.xaxis.set_major_locator(ticker.MultipleLocator(0.25))
    ax_a.yaxis.set_major_locator(ticker.MaxNLocator(nbins=6))
    ax_a.legend(
        loc="upper left",
        frameon=False,
        borderaxespad=0.25,
        handlelength=2.5,
        labelspacing=0.45,
    )
    clean_axis(ax_a)
    ax_a.grid(axis="x", visible=False)
    add_panel_label(ax_a, "a")

    y_three = np.array([2.0, 1.0, 0.0])
    y_two = np.array([1.0, 0.0])

    # ------------------------------------------------------------------
    # b. Lower-endpoint barrier
    # ------------------------------------------------------------------
    barrier_values = [
        parse_float(
            barriers[series]["lower_endpoint_barrier_mev"],
            f"{series} barrier",
        )
        for series in SERIES_ORDER
    ]
    for y_pos, series, value in zip(y_three, SERIES_ORDER, barrier_values):
        ax_b.hlines(
            y_pos,
            0.0,
            value,
            color=colors[series],
            linewidth=2.1,
            alpha=0.72,
            zorder=1,
        )
        ax_b.scatter(
            [value],
            [y_pos],
            s=48,
            marker=markers[series],
            facecolor="white" if series in {"DFT", "basin"} else colors[series],
            edgecolor=colors[series],
            linewidth=1.3,
            zorder=3,
        )
        label_x = min(value + 1.7, 42.3)
        ax_b.text(
            label_x,
            y_pos,
            f"{value:.2f}",
            ha="left",
            va="center",
            fontsize=7.5,
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "pad": 0.65,
                "alpha": 0.86,
            },
        )
    ax_b.set_yticks(y_three)
    ax_b.set_yticklabels(["DFT", "Basin", "Targeted"])
    ax_b.set_xlim(0, 45.0)
    ax_b.set_ylim(-0.50, 2.50)
    ax_b.xaxis.set_major_locator(ticker.MultipleLocator(10))
    ax_b.set_xlabel("Barrier (meV)", labelpad=3)
    ax_b.set_title(
        "Lower-endpoint barrier",
        loc="left",
        x=0.12,
        pad=10,
        fontweight="normal",
    )
    clean_axis(ax_b)
    ax_b.grid(axis="y", visible=False)
    add_panel_label(ax_b, "b")

    # ------------------------------------------------------------------
    # c. Barrier error
    # ------------------------------------------------------------------
    barrier_metric = primary["lower_endpoint_barrier_abs_error_mev"]
    error_values = [
        parse_float(barrier_metric[model], f"{model} barrier error")
        for model in MODEL_ORDER
    ]
    for y_pos, model, value in zip(y_two, MODEL_ORDER, error_values):
        ax_c.hlines(
            y_pos,
            0.0,
            value,
            color=colors[model],
            linewidth=2.4,
            alpha=0.74,
            zorder=1,
        )
        ax_c.scatter(
            [value],
            [y_pos],
            s=52,
            marker=markers[model],
            facecolor=colors[model],
            edgecolor=colors[model],
            linewidth=1.0,
            zorder=3,
        )
        ax_c.text(
            value + 1.45,
            y_pos,
            f"{value:.2f}",
            ha="left",
            va="center",
            fontsize=7.5,
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "pad": 0.65,
                "alpha": 0.86,
            },
        )
    barrier_factor = parse_float(
        barrier_metric["basin_over_targeted"], "barrier improvement"
    )
    ax_c.annotate(
        "",
        xy=(error_values[1], 1.66),
        xytext=(error_values[0], 1.66),
        arrowprops={
            "arrowstyle": "<->",
            "color": colors["targeted"],
            "linewidth": 1.05,
            "shrinkA": 0,
            "shrinkB": 0,
        },
        annotation_clip=False,
    )
    ax_c.text(
        sum(error_values) / 2.0,
        1.88,
        f"{barrier_factor:.2f}× lower",
        ha="center",
        va="bottom",
        fontsize=7.4,
        fontweight="bold",
        color=colors["targeted"],
        bbox={
            "facecolor": "white",
            "edgecolor": "none",
            "pad": 0.45,
            "alpha": 0.86,
        },
    )
    ax_c.set_yticks(y_two)
    ax_c.set_yticklabels(["Basin", "Targeted"])
    ax_c.set_xlim(0, 43.2)
    ax_c.set_ylim(-0.48, 2.08)
    ax_c.xaxis.set_major_locator(ticker.MultipleLocator(10))
    ax_c.set_xlabel("Absolute error (meV)", labelpad=3)
    ax_c.set_title(
        "Barrier error",
        loc="left",
        x=0.12,
        pad=10,
        fontweight="normal",
    )
    clean_axis(ax_c)
    ax_c.grid(axis="y", visible=False)
    add_panel_label(ax_c, "c")

    # ------------------------------------------------------------------
    # d. Transition-region force RMSE
    # ------------------------------------------------------------------
    force_metric = primary["transition_force_component_rmse_ev_ang"]
    force_values = [
        parse_float(force_metric[model], f"{model} force RMSE")
        for model in MODEL_ORDER
    ]
    legend_handle = None
    for y_pos, model, value in zip(y_two, MODEL_ORDER, force_values):
        ax_d.hlines(
            y_pos,
            0.0,
            value,
            color=colors[model],
            linewidth=2.4,
            alpha=0.74,
            zorder=1,
        )
        ax_d.scatter(
            [value],
            [y_pos],
            s=56,
            marker=markers[model],
            facecolor=colors[model],
            edgecolor=colors[model],
            linewidth=1.0,
            zorder=4,
        )
        image_values = [
            parse_float(
                row["force_component_rmse_ev_ang"],
                f"{model} image force RMSE",
            )
            for row in transition_by_model[model]
        ]
        y_offsets = np.array([-0.14, 0.0, 0.14])
        scatter = ax_d.scatter(
            image_values,
            y_pos + y_offsets,
            s=22,
            marker="o",
            facecolor="white",
            edgecolor=colors[model],
            linewidth=0.95,
            zorder=3,
        )
        if legend_handle is None:
            legend_handle = scatter

        fixed_label_x = 0.208
        ax_d.text(
            fixed_label_x,
            y_pos,
            f"{value:.3f}",
            ha="left",
            va="center",
            fontsize=7.5,
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "pad": 0.65,
                "alpha": 0.86,
            },
            zorder=6,
        )

    force_factor = parse_float(
        force_metric["basin_over_targeted"], "force improvement"
    )
    ax_d.annotate(
        "",
        xy=(force_values[1], 1.66),
        xytext=(force_values[0], 1.66),
        arrowprops={
            "arrowstyle": "<->",
            "color": colors["targeted"],
            "linewidth": 1.05,
            "shrinkA": 0,
            "shrinkB": 0,
        },
        annotation_clip=False,
    )
    ax_d.text(
        sum(force_values) / 2.0,
        1.88,
        f"{force_factor:.2f}× lower",
        ha="center",
        va="bottom",
        fontsize=7.4,
        fontweight="bold",
        color=colors["targeted"],
        bbox={
            "facecolor": "white",
            "edgecolor": "none",
            "pad": 0.45,
            "alpha": 0.86,
        },
    )
    if legend_handle is not None:
        ax_d.legend(
            [legend_handle],
            ["Open circles = images 4–6"],
            loc="upper left",
            bbox_to_anchor=(0.02, 0.84),
            frameon=False,
            borderaxespad=0.20,
            handletextpad=0.35,
            fontsize=6.3,
        )

    ax_d.set_yticks(y_two)
    ax_d.set_yticklabels(["Basin", "Targeted"])
    ax_d.set_xlim(0, 0.245)
    ax_d.set_ylim(-0.48, 2.08)
    ax_d.xaxis.set_major_locator(ticker.MultipleLocator(0.05))
    ax_d.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.2f"))
    ax_d.set_xlabel(
        r"Force-component RMSE (eV $\mathrm{\AA}^{-1}$)",
        labelpad=3,
    )
    ax_d.set_title(
        r"Transition region, $|q_{\mathrm{PT}}|\leq0.15\ \mathrm{\AA}$",
        loc="left",
        x=0.12,
        pad=10,
        fontweight="normal",
    )
    clean_axis(ax_d)
    ax_d.grid(axis="y", visible=False)
    add_panel_label(ax_d, "d")

    figure.text(
        0.078,
        0.086,
        "Frozen audit with identical 60-configuration training budgets "
        "(36 common + 24 branch-specific DFT labels).",
        ha="left",
        va="bottom",
        fontsize=6.8,
    )
    figure.text(
        0.078,
        0.048,
        "PBE is the locked comparison reference, not a benchmark-quality "
        "physical proton-transfer barrier.",
        ha="left",
        va="bottom",
        fontsize=6.8,
        color="#444444",
    )

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
        "Title": "Primary frozen-audit result for malonaldehyde MTP comparison",
        "Author": "Reproducible project rendering",
        "Subject": "Equal-budget basin versus transition-targeted MTP audit",
        "Keywords": "malonaldehyde, MTP, NEB, proton transfer, frozen audit",
        "Creator": IMPLEMENTATION_ID,
    }
    figure.savefig(
        outputs["pdf"],
        format="pdf",
        bbox_inches="tight",
        pad_inches=0.05,
        metadata=metadata,
    )
    figure.savefig(
        outputs["svg"],
        format="svg",
        bbox_inches="tight",
        pad_inches=0.05,
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
        pad_inches=0.05,
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
        pad_inches=0.05,
        pil_kwargs={"compression": "tiff_lzw"},
    )
    plt.close(figure)

    return {
        "outputs": {key: str(path) for key, path in outputs.items()},
        "barriers_mev": dict(zip(SERIES_ORDER, barrier_values)),
        "barrier_abs_errors_mev": dict(zip(MODEL_ORDER, error_values)),
        "transition_force_rmse_ev_ang": dict(zip(MODEL_ORDER, force_values)),
        "barrier_improvement_factor": barrier_factor,
        "force_improvement_factor": force_factor,
        "transition_images": list(EXPECTED_TRANSITION_IMAGES),
        "layout": (
            "spacious_profile_left_with_separated_horizontal_comparisons"
        ),
        "negative_profile_values_visible": True,
        "non_overlapping_annotation_polish": True,
        "extra_spacing_applied": True,
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
                            width >= 3600 and height >= 2200,
                            f"{width}x{height}",
                            "at least 3600x2200 pixels",
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
        PROFILE_FILE,
        BARRIER_FILE,
        PRIMARY_FILE,
        TRANSITION_FILE,
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
    barriers = rows_by_key(inputs.rows_barrier, "series")
    primary = rows_by_key(inputs.rows_primary, "metric")
    rows: list[dict[str, Any]] = []
    for series in SERIES_ORDER:
        rows.append(
            {
                "panel": "b",
                "quantity": "lower_endpoint_barrier",
                "series": series,
                "value": parse_float(
                    barriers[series]["lower_endpoint_barrier_mev"],
                    f"{series} barrier",
                ),
                "unit": "meV",
            }
        )
    for model in MODEL_ORDER:
        rows.extend(
            [
                {
                    "panel": "c",
                    "quantity": "lower_endpoint_barrier_abs_error",
                    "series": model,
                    "value": parse_float(
                        primary["lower_endpoint_barrier_abs_error_mev"][model],
                        f"{model} barrier error",
                    ),
                    "unit": "meV",
                },
                {
                    "panel": "d",
                    "quantity": "transition_force_component_rmse",
                    "series": model,
                    "value": parse_float(
                        primary["transition_force_component_rmse_ev_ang"][model],
                        f"{model} force RMSE",
                    ),
                    "unit": "eV/Angstrom",
                },
            ]
        )
    return rows


def write_caption(path: Path, figure_data: Mapping[str, Any]) -> None:
    barrier_factor = figure_data["barrier_improvement_factor"]
    force_factor = figure_data["force_improvement_factor"]
    caption = f"""# Figure 2. Transition-focused equal-budget sampling improves static PBE-path fidelity

**a,** Relative-energy profiles along the frozen independent nine-image PBE
proton-transfer path. The shaded interval marks the preregistered transition
region, $|q_{{\\mathrm{{PT}}}}| \\le 0.15$ Angstrom. **b,** Lower-endpoint barriers, defined as the maximum path energy minus the
lower endpoint. **c,** Absolute barrier error relative to the locked PBE
reference. **d,** Force-component RMSE in transition images 4-6; large filled
symbols show combined RMSE and open circles show image-level values.

Both final MTPs contain 60 training configurations: 36 shared configurations
plus 24 branch-specific DFT labels. Relative to basin-only allocation,
transition-focused allocation reduces the lower-endpoint barrier error by
{barrier_factor:.2f}-fold and the transition-region force-component RMSE by
{force_factor:.2f}-fold. The PBE path is the locked reference for this frozen
audit and should not be interpreted as a benchmark-quality physical
proton-transfer barrier.
"""
    atomic_write_text(path, caption)


def write_report(
    path: Path,
    inputs: LockedInputs,
    validations: Sequence[Validation],
    figure_data: Mapping[str, Any],
    output_paths: Mapping[str, Path],
) -> None:
    report = f"""# Figure 2 primary frozen-audit redesign report v009

Created UTC: `{utc_iso()}`

Status: `{STATUS_PASS}`

## Scope

This stage rendered the redesigned four-panel primary result from the completed v005
visualization source audit. It did not execute Quantum ESPRESSO, an NEB engine,
MLIP training, `mlp calc-grade`, LAMMPS, or molecular dynamics.

## Locked input

- v005 attempt: `{inputs.attempt}`
- v005 status: `{EXPECTED_INPUT_STATUS}`
- profile source: `{inputs.profile_path}`
- barrier source: `{inputs.barrier_path}`
- primary metric source: `{inputs.primary_path}`
- transition-row source: `{inputs.transition_path}`

All plotted inputs were verified against `checksums_v005.tsv` before rendering.

## Rendered result

- PDF: `{output_paths["pdf"]}`
- SVG: `{output_paths["svg"]}`
- PNG: `{output_paths["png"]}`
- TIFF: `{output_paths["tiff"]}`

Barrier improvement factor: `{figure_data["barrier_improvement_factor"]:.9f}`

Transition-force improvement factor: `{figure_data["force_improvement_factor"]:.9f}`

## Scientific interpretation

At equal DFT budget, placing the 24 branch-specific labels in the transition
region improves the static PBE-path prediction relative to placing them in the
basins. This result isolates label allocation under the frozen comparison; it
does not establish the marginal advantage of MaxVol over another
transition-focused selection procedure.

The PBE barrier is the locked frozen-audit reference, not a benchmark-quality
physical barrier.

## Validation

Passed checks: `{sum(item.passed for item in validations)}`

Failed checks: `{sum(not item.passed for item in validations)}`
"""
    atomic_write_text(path, report)


def write_checksums(attempt: Path) -> Path:
    checksum_path = attempt / "checksums_v009.tsv"
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


def validation_rows(validations: Sequence[Validation]) -> list[dict[str, Any]]:
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
        print(f"PROFILE_ROWS={len(inputs.rows_profile)}")
        print(f"BARRIER_ROWS={len(inputs.rows_barrier)}")
        print(f"PRIMARY_METRICS={len(inputs.rows_primary)}")
        print(f"TRANSITION_ROWS={len(inputs.rows_transition)}")
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
        output_base = figures_dir / "figure02_primary_frozen_audit_spacious_v009"
        figure_data = render_figure(inputs, output_base)
        output_paths = {
            key: Path(value) for key, value in figure_data["outputs"].items()
        }
        render_validations = verify_rendered_files(output_paths)
        validations.extend(render_validations)

        panel_values = build_panel_values(inputs)
        panel_values_path = data_dir / "figure02_panel_values_v009.tsv"
        atomic_write_tsv(
            panel_values_path,
            ["panel", "quantity", "series", "value", "unit"],
            panel_values,
        )

        validation_path = reports_dir / "figure02_validation_v009.tsv"
        atomic_write_tsv(
            validation_path,
            ["check", "passed", "observed", "expected", "severity"],
            validation_rows(validations),
        )

        caption_path = attempt / "figure02_caption_v009.md"
        write_caption(caption_path, figure_data)

        report_path = reports_dir / "figure02_render_report_v009.md"
        write_report(
            report_path,
            inputs,
            validations,
            figure_data,
            output_paths,
        )

        input_lock = {
            "schema_version": "1.0",
            "created_utc": utc_iso(),
            "implementation": IMPLEMENTATION_ID,
            "input_attempt": str(inputs.attempt),
            "input_status": EXPECTED_INPUT_STATUS,
            "source_hashes": inputs.source_hashes,
            "figure_manifest_row": inputs.figure_manifest_row,
            "expected_numeric_lock": EXPECTED_METRICS,
            "scientific_execution": {
                "qe": False,
                "neb_engine": False,
                "mlip_training": False,
                "mlp_calc_grade": False,
                "lammps": False,
                "md": False,
            },
        }
        lock_path = attempt / "figure02_data_lock_v009.json"
        atomic_write_json(lock_path, input_lock)

        manifest_rows = [
            {
                "artifact_id": "Figure_2",
                "role": "primary_frozen_audit_figure",
                "pdf": str(output_paths["pdf"].relative_to(attempt)),
                "svg": str(output_paths["svg"].relative_to(attempt)),
                "png": str(output_paths["png"].relative_to(attempt)),
                "tiff": str(output_paths["tiff"].relative_to(attempt)),
                "caption": str(caption_path.relative_to(attempt)),
                "status": "RENDERED_AND_VALIDATED",
                "scientific_message": inputs.figure_manifest_row["scientific_message"],
                "mandatory_caveat": inputs.figure_manifest_row["mandatory_caveat"],
            }
        ]
        manifest_path = attempt / "figure02_manifest_v009.tsv"
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
                "At equal DFT budget, transition-focused label allocation "
                "improves frozen static PBE-path fidelity relative to "
                "basin-only allocation."
            ),
            "mandatory_caveat": (
                "The locked PBE barrier is not a benchmark-quality physical "
                "proton-transfer barrier."
            ),
            "next_stage": (
                "Render Figure 3 deployment limitation from exact "
                "source-oracle geometry and frozen applicability-grade data."
            ),
        }
        summary_path = attempt / "summary_v009.json"
        atomic_write_json(summary_path, summary)

        atomic_write_text(attempt / "STATUS_v009.txt", STATUS_PASS + "\n")
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
        failure_path = attempt / "STATUS_v009.txt"
        if not failure_path.exists():
            failure_path.write_text(STATUS_FAIL + "\n", encoding="utf-8")
        raise


def make_synthetic_fixture(root: Path) -> Path:
    """Build a minimal v005-like source package for renderer regression."""
    attempt = (
        root
        / INPUT_RELATIVE_ROOT
        / "attempt_20990101T000000Z"
    )
    attempt.mkdir(parents=True, exist_ok=False)
    (attempt / "source_data").mkdir()

    qpt = [-0.484, -0.388, -0.260, -0.128, 0.0, 0.128, 0.260, 0.388, 0.484]
    dft = [0.0, 4.0, 18.0, 31.0, 36.072093892926205, 31.0, 18.0, 4.0, 0.1]
    basin = [0.0, 0.8, 0.7, 0.4, 0.5, 0.3, 0.2, 0.1, 0.0]
    targeted = [0.0, 3.6, 16.2, 27.8, 31.971700288977445, 27.8, 16.2, 3.6, 0.0]
    profile_rows = []
    for series, values in (("DFT", dft), ("basin", basin), ("targeted", targeted)):
        for index, (x, y) in enumerate(zip(qpt, values), start=1):
            profile_rows.append(
                {
                    "series": series,
                    "image": index,
                    "qpt_ang": x,
                    "roo_ang": 2.5,
                    "energy_ev": -100.0 + y / 1000.0,
                    "delta_e_from_lower_endpoint_ev": y / 1000.0,
                    "delta_e_from_lower_endpoint_mev": y,
                    "profile_error_ev": 0.0,
                    "profile_error_mev": 0.0,
                    "is_transition_region": abs(x) <= 0.15,
                }
            )
    atomic_write_tsv(
        attempt / PROFILE_FILE,
        list(profile_rows[0].keys()),
        profile_rows,
    )
    barriers = [
        {
            "series": "DFT",
            "lower_endpoint_barrier_ev": EXPECTED_METRICS["dft_barrier_mev"] / 1000,
            "lower_endpoint_barrier_mev": EXPECTED_METRICS["dft_barrier_mev"],
            "absolute_error_ev": 0.0,
            "absolute_error_mev": 0.0,
            "maximum_image": 5,
            "maximum_qpt_ang": 0.0,
            "lower_endpoint_image": 1,
        },
        {
            "series": "basin",
            "lower_endpoint_barrier_ev": EXPECTED_METRICS["basin_barrier_mev"] / 1000,
            "lower_endpoint_barrier_mev": EXPECTED_METRICS["basin_barrier_mev"],
            "absolute_error_ev": EXPECTED_METRICS["basin_barrier_abs_error_mev"] / 1000,
            "absolute_error_mev": EXPECTED_METRICS["basin_barrier_abs_error_mev"],
            "maximum_image": 2,
            "maximum_qpt_ang": qpt[1],
            "lower_endpoint_image": 9,
        },
        {
            "series": "targeted",
            "lower_endpoint_barrier_ev": EXPECTED_METRICS["targeted_barrier_mev"] / 1000,
            "lower_endpoint_barrier_mev": EXPECTED_METRICS["targeted_barrier_mev"],
            "absolute_error_ev": EXPECTED_METRICS["targeted_barrier_abs_error_mev"] / 1000,
            "absolute_error_mev": EXPECTED_METRICS["targeted_barrier_abs_error_mev"],
            "maximum_image": 5,
            "maximum_qpt_ang": 0.0,
            "lower_endpoint_image": 9,
        },
    ]
    atomic_write_tsv(
        attempt / BARRIER_FILE,
        list(barriers[0].keys()),
        barriers,
    )
    primary = [
        {
            "metric": "transition_force_component_rmse_ev_ang",
            "definition": "synthetic",
            "unit": "eV/Angstrom",
            "basin": EXPECTED_METRICS["basin_transition_force_rmse"],
            "targeted": EXPECTED_METRICS["targeted_transition_force_rmse"],
            "targeted_minus_basin": (
                EXPECTED_METRICS["targeted_transition_force_rmse"]
                - EXPECTED_METRICS["basin_transition_force_rmse"]
            ),
            "basin_over_targeted": EXPECTED_METRICS["force_improvement_factor"],
            "targeted_better": True,
            "authoritative_source": "synthetic",
        },
        {
            "metric": "lower_endpoint_barrier_abs_error_mev",
            "definition": "synthetic",
            "unit": "meV",
            "basin": EXPECTED_METRICS["basin_barrier_abs_error_mev"],
            "targeted": EXPECTED_METRICS["targeted_barrier_abs_error_mev"],
            "targeted_minus_basin": (
                EXPECTED_METRICS["targeted_barrier_abs_error_mev"]
                - EXPECTED_METRICS["basin_barrier_abs_error_mev"]
            ),
            "basin_over_targeted": EXPECTED_METRICS["barrier_improvement_factor"],
            "targeted_better": True,
            "authoritative_source": "synthetic",
        },
    ]
    atomic_write_tsv(
        attempt / PRIMARY_FILE,
        list(primary[0].keys()),
        primary,
    )
    transition = []
    values = {
        "basin": [0.1674, 0.1922, 0.1675],
        "targeted": [0.0762, 0.0834, 0.0762],
    }
    for model in MODEL_ORDER:
        for image, value in zip(EXPECTED_TRANSITION_IMAGES, values[model]):
            transition.append(
                {
                    "model": model,
                    "image": image,
                    "qpt_ang": qpt[image - 1],
                    "force_component_rmse_ev_ang": value,
                    "force_component_mae_ev_ang": value * 0.6,
                    "force_component_max_abs_ev_ang": value * 3.0,
                    "selection_rule": "abs(qPT)<=0.15 A",
                }
            )
    atomic_write_tsv(
        attempt / TRANSITION_FILE,
        list(transition[0].keys()),
        transition,
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
            "figure_id": "Figure_2",
            "title": "Primary frozen-audit result",
            "panels": "a;b;c;d",
            "primary_source_data": "synthetic",
            "geometry_sources": "synthetic",
            "status": "SOURCE_DATA_READY_NEXT_TO_RENDER",
            "scientific_message": "synthetic scientific message",
            "mandatory_caveat": "synthetic caveat",
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
        PROFILE_FILE,
        BARRIER_FILE,
        PRIMARY_FILE,
        TRANSITION_FILE,
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
    with tempfile.TemporaryDirectory(prefix="figure02_v009_test_") as temp:
        root = Path(temp)
        make_synthetic_fixture(root)
        inputs = load_locked_inputs(root)

        # Synthetic profile intentionally uses the exact locked barriers.
        # Replace basin profile maximum with the locked basin barrier.
        rows = read_tsv(inputs.profile_path)
        for row in rows:
            if row["series"] == "basin" and row["image"] == "2":
                row["delta_e_from_lower_endpoint_mev"] = str(
                    EXPECTED_METRICS["basin_barrier_mev"]
                )
                row["delta_e_from_lower_endpoint_ev"] = str(
                    EXPECTED_METRICS["basin_barrier_mev"] / 1000.0
                )
        inputs.profile_path.unlink()
        atomic_write_tsv(inputs.profile_path, list(rows[0].keys()), rows)

        # Refresh checksum for the modified fixture profile.
        checksum_rows = read_tsv(inputs.checksums_path)
        for row in checksum_rows:
            if row["relative_path"] == PROFILE_FILE:
                row["size_bytes"] = str(inputs.profile_path.stat().st_size)
                row["sha256"] = sha256_file(inputs.profile_path)
        inputs.checksums_path.unlink()
        atomic_write_tsv(
            inputs.checksums_path,
            list(checksum_rows[0].keys()),
            checksum_rows,
        )

        inputs = load_locked_inputs(root)
        validations = validate_inputs(inputs)
        output_base = root / "synthetic_output" / "figure02"
        data = render_figure(inputs, output_base)
        paths = {key: Path(value) for key, value in data["outputs"].items()}
        validations.extend(verify_rendered_files(paths))
        if not all(item.passed for item in validations):
            raise FigureAuditError("Synthetic self-test has failed checks")
        print("SELF_TEST=PASS")
        print(f"VALIDATION_CHECKS={len(validations)}")
        print("FORMATS=PDF,SVG,PNG,TIFF")
        print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render Figure 2 from the completed v005 normalized source package."
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

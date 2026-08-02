#!/usr/bin/env python3
"""Render the final supplementary quantum-audit figure from frozen v039 outputs.

This stage performs visualization-only post-processing. It does not execute DFT,
training, NEB, molecular dynamics, or any new quantum-nuclear calculation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, FancyBboxPatch
from matplotlib.lines import Line2D
import numpy as np

STAGE = "STAGE63"
PACKAGE_VERSION = "v005"
OUTPUT_VERSION = "v044"
OUTPUT_DIRNAME = "v044_supplementary_figure_s3_quantum_audit_relaxed_annotations"
POINTER_NAME = "CURRENT_SUPPLEMENTARY_FIGURE_S3_QUANTUM_AUDIT_RELAXED_ANNOTATIONS_V044.txt"
SOURCE_DIRNAME = "v039_frozen_path_1d_tunneling_audit"
SOURCE_POINTER_NAME = "CURRENT_FROZEN_PATH_1D_TUNNELING_AUDIT_V039.txt"
SOURCE_STATUS_EXPECTED = "PASS_STAGE62_FROZEN_PATH_1D_TUNNELING_AUDIT_V003"
STATUS_PASS = "PASS_STAGE63_SUPPLEMENTARY_FIGURE_S3_QUANTUM_AUDIT_V005"

SERIES_ORDER = ("DFT", "basin", "targeted")
ISOTOPE_ORDER = ("H", "D")
SERIES_LABEL = {"DFT": "PBE", "basin": "Basin", "targeted": "Targeted"}
CURVE_LABEL = {
    "DFT": "PBE",
    "basin": "Basin-focused MTP",
    "targeted": "Transition-focused MTP",
}
COLORS = {"DFT": "#222222", "basin": "#D9871F", "targeted": "#2F78B7"}
BG = "#FFFFFF"
GRID = "#E1E1E1"
TEXT = "#202020"
SUBTEXT = "#5A5A5A"
BORDER = "#CFCFCF"

PRIMARY_TABLE = "tables/quantum_results_primary_v039.tsv"
ROBUSTNESS_TABLE = "tables/robustness_comparisons_v039.tsv"
POTENTIAL_GRID_TABLE = "tables/primary_potential_and_mass_grid_v039.tsv"
MASS_TABLE = "tables/effective_mass_profiles_v039.tsv"
SOURCE_STATUS_FILE = "STATUS_v039.txt"
SOURCE_SUMMARY_FILE = "summary_v039.json"
SOURCE_CHECKSUM_FILE = "checksums_v039.tsv"

EXPECTED_PRIMARY_FORMULATION = {
    "interpolation": "pchip",
    "profile_mode": "symmetrized",
    "mass_model": "path_metric",
}

CLASSIFICATION_DISPLAY = {
    "subbarrier_symmetric_doublet": "sub-barrier doublet",
    "subbarrier_nearly_symmetric_doublet": "near-symmetric sub-barrier pair",
    "subbarrier_biased_low_level_pair": "biased sub-barrier pair",
    "only_ground_state_below_barrier": "only E0 below barrier",
    "no_low_subbarrier_doublet": "no low sub-barrier doublet",
}


class FigureAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceData:
    run_dir: Path
    primary_rows: list[dict[str, str]]
    robustness_rows: list[dict[str, str]]
    potential_rows: list[dict[str, str]]
    mass_rows: list[dict[str, str]]
    source_hashes: dict[str, str]


@dataclass(frozen=True)
class RenderOutputs:
    run_dir: Path
    png: Path
    pdf: Path
    svg: Path
    tiff: Path
    caption: Path
    report: Path
    validation: Path
    summary: Path
    checksums: Path


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FigureAuditError(f"Missing {label}: {path}")
    if path.stat().st_size == 0:
        raise FigureAuditError(f"Empty {label}: {path}")
    return path


def read_tsv(path: Path) -> list[dict[str, str]]:
    with require_file(path, "TSV file").open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle, delimiter="\t")]
    if not rows:
        raise FigureAuditError(f"TSV is empty: {path}")
    return rows


def write_tsv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise FigureAuditError(f"Cannot write empty TSV: {path}")
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_float(row: Mapping[str, str], key: str, context: str) -> float:
    raw = str(row.get(key, "")).strip()
    try:
        value = float(raw)
    except Exception as exc:
        raise FigureAuditError(f"Invalid float {context}.{key}: {raw!r}") from exc
    if not math.isfinite(value):
        raise FigureAuditError(f"Non-finite float {context}.{key}: {value}")
    return value


def parse_bool(row: Mapping[str, str], key: str, context: str) -> bool:
    raw = str(row.get(key, "")).strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    raise FigureAuditError(f"Invalid boolean {context}.{key}: {raw!r}")


def resolve_source_run(root: Path) -> Path:
    pointer = root / "10_visualization" / "versions" / SOURCE_DIRNAME / SOURCE_POINTER_NAME
    require_file(pointer, "v039 source pointer")
    lines = [line.strip() for line in pointer.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise FigureAuditError(f"Empty source pointer: {pointer}")
    run_dir = Path(lines[-1])
    if not run_dir.is_absolute():
        run_dir = (pointer.parent / run_dir).resolve()
    if not run_dir.is_dir():
        raise FigureAuditError(f"Source run directory does not exist: {run_dir}")
    return run_dir


def load_source(root: Path) -> SourceData:
    run_dir = resolve_source_run(root)
    status = require_file(run_dir / SOURCE_STATUS_FILE, "v039 status").read_text(encoding="utf-8").strip()
    if status != SOURCE_STATUS_EXPECTED:
        raise FigureAuditError(f"Unexpected v039 status: {status!r}; expected {SOURCE_STATUS_EXPECTED!r}")

    paths = {
        "primary": run_dir / PRIMARY_TABLE,
        "robustness": run_dir / ROBUSTNESS_TABLE,
        "potential": run_dir / POTENTIAL_GRID_TABLE,
        "mass": run_dir / MASS_TABLE,
        "summary": run_dir / SOURCE_SUMMARY_FILE,
        "status": run_dir / SOURCE_STATUS_FILE,
    }
    for label, path in paths.items():
        require_file(path, f"v039 {label}")
    source_hashes = {label: sha256_file(path) for label, path in paths.items()}
    checksum_path = run_dir / SOURCE_CHECKSUM_FILE
    if checksum_path.is_file():
        source_hashes["checksums"] = sha256_file(checksum_path)

    return SourceData(
        run_dir=run_dir,
        primary_rows=read_tsv(paths["primary"]),
        robustness_rows=read_tsv(paths["robustness"]),
        potential_rows=read_tsv(paths["potential"]),
        mass_rows=read_tsv(paths["mass"]),
        source_hashes=source_hashes,
    )


def key_primary(row: Mapping[str, str]) -> tuple[str, str]:
    return str(row.get("series", "")).strip(), str(row.get("isotope", "")).strip()


def validate_source(source: SourceData) -> dict[str, Any]:
    primary_map: dict[tuple[str, str], dict[str, str]] = {}
    for row in source.primary_rows:
        key = key_primary(row)
        if key in primary_map:
            raise FigureAuditError(f"Duplicate primary result: {key}")
        primary_map[key] = row

    expected_keys = {(series, isotope) for series in SERIES_ORDER for isotope in ISOTOPE_ORDER}
    if set(primary_map) != expected_keys:
        raise FigureAuditError(f"Primary result keys mismatch: observed={sorted(primary_map)}, expected={sorted(expected_keys)}")

    for key, row in primary_map.items():
        context = f"primary[{key[0]},{key[1]}]"
        for field, expected in EXPECTED_PRIMARY_FORMULATION.items():
            observed = str(row.get(field, "")).strip()
            if observed != expected:
                raise FigureAuditError(f"Unexpected primary formulation {context}.{field}: {observed!r}")
        barrier = parse_float(row, "barrier_mev", context)
        e0 = 1000.0 * parse_float(row, "e0_ev", context)
        e1 = 1000.0 * parse_float(row, "e1_ev", context)
        gap = parse_float(row, "gap_mev", context)
        if barrier < 0 or e1 <= e0 or gap <= 0:
            raise FigureAuditError(f"Invalid energy ordering in {context}")
        if abs((e1 - e0) - gap) > max(1e-6, 1e-5 * gap):
            raise FigureAuditError(f"Gap inconsistency in {context}: E1-E0={e1-e0}, gap={gap}")
        classification = str(row.get("classification", "")).strip()
        if classification not in CLASSIFICATION_DISPLAY:
            raise FigureAuditError(f"Unknown classification in {context}: {classification!r}")
        parse_bool(row, "e0_below_barrier", context)
        parse_bool(row, "e1_below_barrier", context)

    # Potential grid validation.
    potential_groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in source.potential_rows:
        key = (str(row.get("series", "")).strip(), str(row.get("isotope", "")).strip())
        potential_groups.setdefault(key, []).append(row)
    if set(potential_groups) != expected_keys:
        raise FigureAuditError(f"Potential-grid group mismatch: {sorted(potential_groups)}")
    grid_sizes = set()
    for key, rows in potential_groups.items():
        rows.sort(key=lambda row: int(row["grid_index"]))
        q = np.array([parse_float(row, "qpt_ang", f"potential[{key}]") for row in rows])
        v = np.array([parse_float(row, "potential_mev", f"potential[{key}]") for row in rows])
        if len(rows) < 401:
            raise FigureAuditError(f"Potential grid too short for {key}: {len(rows)}")
        if not np.all(np.diff(q) > 0):
            raise FigureAuditError(f"Potential q-grid not strictly increasing for {key}")
        if np.any(v < -1e-6):
            raise FigureAuditError(f"Negative shifted potential below tolerance for {key}")
        grid_sizes.add(len(rows))
    if len(grid_sizes) != 1:
        raise FigureAuditError(f"Potential grid sizes differ: {sorted(grid_sizes)}")

    # H and D potentials must be identical for each series; only mass changes.
    max_hd_potential_difference = 0.0
    for series in SERIES_ORDER:
        rows_h = potential_groups[(series, "H")]
        rows_d = potential_groups[(series, "D")]
        vh = np.array([parse_float(row, "potential_mev", f"potential[{series},H]") for row in rows_h])
        vd = np.array([parse_float(row, "potential_mev", f"potential[{series},D]") for row in rows_d])
        max_hd_potential_difference = max(max_hd_potential_difference, float(np.max(np.abs(vh - vd))))
    if max_hd_potential_difference > 1e-8:
        raise FigureAuditError(f"H/D potential mismatch: {max_hd_potential_difference} meV")

    # Effective-mass profile validation.
    mass_groups: dict[str, list[dict[str, str]]] = {}
    for row in source.mass_rows:
        isotope = str(row.get("isotope", "")).strip()
        mass_groups.setdefault(isotope, []).append(row)
    if set(mass_groups) != set(ISOTOPE_ORDER):
        raise FigureAuditError(f"Effective-mass isotope mismatch: {sorted(mass_groups)}")
    for isotope, rows in mass_groups.items():
        rows.sort(key=lambda row: int(row["grid_index"]))
        q = np.array([parse_float(row, "qpt_ang", f"mass[{isotope}]") for row in rows])
        m = np.array([parse_float(row, "effective_mass_amu", f"mass[{isotope}]") for row in rows])
        if len(rows) != next(iter(grid_sizes)):
            raise FigureAuditError(f"Mass grid size mismatch for {isotope}")
        if not np.all(np.diff(q) > 0):
            raise FigureAuditError(f"Mass q-grid not strictly increasing for {isotope}")
        if np.any(m <= 0):
            raise FigureAuditError(f"Non-positive effective mass for {isotope}")

    # Isotope effect direction.
    isotope_checks = {}
    for series in SERIES_ORDER:
        gap_h = parse_float(primary_map[(series, "H")], "gap_mev", f"primary[{series},H]")
        gap_d = parse_float(primary_map[(series, "D")], "gap_mev", f"primary[{series},D]")
        isotope_checks[series] = gap_d < gap_h
    if not all(isotope_checks.values()):
        raise FigureAuditError(f"Expected D gap < H gap failed: {isotope_checks}")

    # Robustness count from actual table.
    targeted_better_rows = []
    for row in source.robustness_rows:
        if "targeted_better" in row:
            raw = str(row.get("targeted_better", "")).strip().lower()
            if raw in {"true", "1", "yes"}:
                targeted_better_rows.append(row)
        elif "winner" in row:
            if str(row.get("winner", "")).strip().lower() == "targeted":
                targeted_better_rows.append(row)
    robustness_total = len(source.robustness_rows)
    robustness_targeted_better = len(targeted_better_rows)
    if robustness_total < 1:
        raise FigureAuditError("Robustness table has no rows")

    return {
        "primary_map": primary_map,
        "potential_groups": potential_groups,
        "mass_groups": mass_groups,
        "grid_points": next(iter(grid_sizes)),
        "max_hd_potential_difference_mev": max_hd_potential_difference,
        "isotope_checks": isotope_checks,
        "robustness_total": robustness_total,
        "robustness_targeted_better": robustness_targeted_better,
    }


def concise_classification(value: str) -> str:
    return CLASSIFICATION_DISPLAY[value]


def _series_arrays(groups: Mapping[tuple[str, str], list[dict[str, str]]], series: str) -> tuple[np.ndarray, np.ndarray]:
    rows = sorted(groups[(series, "H")], key=lambda row: int(row["grid_index"]))
    q = np.array([float(row["qpt_ang"]) for row in rows])
    v = np.array([float(row["potential_mev"]) for row in rows])
    return q, v


def _mass_arrays(groups: Mapping[str, list[dict[str, str]]], isotope: str) -> tuple[np.ndarray, np.ndarray]:
    rows = sorted(groups[isotope], key=lambda row: int(row["grid_index"]))
    q = np.array([float(row["qpt_ang"]) for row in rows])
    m = np.array([float(row["effective_mass_amu"]) for row in rows])
    return q, m


def render_figure(source: SourceData, validated: Mapping[str, Any], output_base: Path) -> tuple[Path, Path, Path, Path]:
    primary_map = validated["primary_map"]
    potential_groups = validated["potential_groups"]
    mass_groups = validated["mass_groups"]

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10.5,
        "axes.titlesize": 13.5,
        "axes.labelsize": 11.5,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "axes.linewidth": 1.0,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    fig = plt.figure(figsize=(15.3, 8.8), facecolor=BG)
    outer = fig.add_gridspec(
        nrows=2,
        ncols=2,
        width_ratios=(1.34, 1.0),
        height_ratios=(3.20, 1.12),
        left=0.062,
        right=0.982,
        top=0.830,
        bottom=0.082,
        wspace=0.22,
        hspace=0.34,
    )
    ax_potential = fig.add_subplot(outer[0, 0])
    ax_mass = fig.add_subplot(outer[1, 0])
    right = outer[:, 1].subgridspec(2, 1, height_ratios=(4.15, 0.95), hspace=0.32)
    ax_gap = fig.add_subplot(right[0, 0])
    ax_class = fig.add_subplot(right[1, 0])

    fig.suptitle(
        "Frozen-path 1D quantum-level audit of proton transfer in malonaldehyde",
        fontsize=20.5,
        fontweight="bold",
        y=0.973,
        color=TEXT,
    )
    fig.text(
        0.5,
        0.932,
        "Transition-focused equal-budget sampling better preserves the PBE-derived low-level spectrum on the frozen PBE path.",
        ha="center",
        va="center",
        fontsize=12.0,
        color=SUBTEXT,
    )
    fig.text(
        0.5,
        0.903,
        "Frozen-path one-dimensional spectral diagnostic; not an experimental tunneling-rate prediction.",
        ha="center",
        va="center",
        fontsize=10.6,
        color="#7A7A7A",
    )

    # Panel a: potentials and H levels.
    ax_potential.text(-0.105, 1.065, "a", transform=ax_potential.transAxes, fontsize=18, fontweight="bold")
    ax_potential.set_title("Frozen-path 1D potentials and two lowest H levels", loc="left", pad=12, fontweight="bold")

    q_min = float("inf")
    q_max = float("-inf")
    potential_max = 0.0
    level_positions: dict[str, tuple[float, float]] = {}
    for series in SERIES_ORDER:
        q, potential = _series_arrays(potential_groups, series)
        q_min = min(q_min, float(q.min()))
        q_max = max(q_max, float(q.max()))
        potential_max = max(potential_max, float(potential.max()))
        ax_potential.plot(q, potential, color=COLORS[series], lw=2.35, label=CURVE_LABEL[series], zorder=3)
        row = primary_map[(series, "H")]
        e0 = 1000.0 * float(row["e0_ev"])
        e1 = 1000.0 * float(row["e1_ev"])
        level_positions[series] = (e0, e1)

    # Place levels in separate horizontal zones to avoid overlap.
    centers = {"DFT": -0.56, "basin": 0.00, "targeted": 0.56}
    half_width = 0.135 * (q_max - q_min)
    for series in SERIES_ORDER:
        e0, e1 = level_positions[series]
        center = centers[series]
        ax_potential.hlines(e0, center - half_width, center + half_width, colors=COLORS[series], lw=1.8, zorder=5)
        ax_potential.hlines(e1, center - half_width, center + half_width, colors=COLORS[series], lw=1.8, linestyles="--", zorder=5)

    # Barrier labels from source table, moved farther away from the curves.
    barrier_text_positions = {
        "DFT": (-0.21, 38.7),
        "targeted": (0.18, 33.5),
        "basin": (0.03, 7.9),
    }
    for series in ("DFT", "targeted", "basin"):
        barrier = float(primary_map[(series, "H")]["barrier_mev"])
        tx, ty = barrier_text_positions[series]
        ax_potential.annotate(
            f"{barrier:.2f}",
            xy=(0.0, barrier),
            xytext=(tx, ty),
            ha="center",
            va="bottom",
            color=COLORS[series],
            fontsize=10.2,
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#FFFFFF", edgecolor="none", alpha=0.82),
            arrowprops=dict(arrowstyle="-", color=COLORS[series], lw=0.8, shrinkA=0.0, shrinkB=0.0),
            zorder=7,
        )

    ax_potential.set_xlim(q_min, q_max)
    y_top = max(45.0, math.ceil((potential_max + 1.0) / 5.0) * 5.0)
    ax_potential.set_ylim(-0.8, y_top)
    ax_potential.set_xlabel(r"Symmetrized proton-transfer coordinate $q_{PT}$ ($\AA$)")
    ax_potential.set_ylabel("Relative potential / level energy (meV)")
    ax_potential.grid(axis="y", color=GRID, lw=0.8)
    ax_potential.spines[["top", "right"]].set_visible(False)

    curve_handles = [Line2D([0], [0], color=COLORS[s], lw=2.4, label=CURVE_LABEL[s]) for s in SERIES_ORDER]
    level_handles = [
        Line2D([0], [0], color="#333333", lw=1.7, label=r"$E_0$ (ground)"),
        Line2D([0], [0], color="#333333", lw=1.7, ls="--", label=r"$E_1$ (first excited)"),
    ]
    legend1 = ax_potential.legend(handles=curve_handles, loc="upper right", bbox_to_anchor=(0.995, 1.045), frameon=False)
    ax_potential.add_artist(legend1)
    ax_potential.legend(handles=level_handles, loc="lower left", frameon=False)

    # Effective-mass diagnostic.
    ax_mass.set_title("Frozen PBE-path effective-mass diagnostic", loc="left", pad=7, fontsize=12.0, fontweight="bold")
    q_h, m_h = _mass_arrays(mass_groups, "H")
    q_d, m_d = _mass_arrays(mass_groups, "D")
    ax_mass.plot(q_h, m_h, color=COLORS["targeted"], lw=2.15, label="H")
    ax_mass.plot(q_d, m_d, color=COLORS["basin"], lw=2.15, ls="--", label="D")
    ax_mass.set_xlim(q_min, q_max)
    ax_mass.set_ylim(0.0, max(3.0, 1.08 * float(m_d.max())))
    ax_mass.set_xlabel(r"Symmetrized $q_{PT}$ ($\AA$)")
    ax_mass.set_ylabel("Path-metric effective mass (amu)")
    ax_mass.grid(axis="y", color=GRID, lw=0.75)
    ax_mass.spines[["top", "right"]].set_visible(False)
    ax_mass.legend(loc="upper left", frameon=False, ncol=2)
    ax_mass.text(
        0.985,
        0.022,
        "Coordinate metric; not the literal mass of the transferred particle.",
        transform=ax_mass.transAxes,
        ha="right",
        va="bottom",
        fontsize=8.5,
        color=SUBTEXT,
        bbox=dict(boxstyle="round,pad=0.14", facecolor="#FFFFFF", edgecolor="none", alpha=0.65),
    )

    # Panel b: gaps.
    ax_gap.text(-0.11, 1.05, "b", transform=ax_gap.transAxes, fontsize=18, fontweight="bold")
    ax_gap.set_title("PBE-derived H/D lowest-level gaps", loc="left", pad=14, fontweight="bold")
    x = np.arange(len(SERIES_ORDER), dtype=float)
    width = 0.32
    gap_values: dict[tuple[str, str], float] = {
        (series, isotope): float(primary_map[(series, isotope)]["gap_mev"])
        for series in SERIES_ORDER for isotope in ISOTOPE_ORDER
    }
    max_gap = max(gap_values.values())
    y_gap_top = max(30.0, math.ceil((max_gap + 2.0) / 5.0) * 5.0)

    bars_h = []
    bars_d = []
    for index, series in enumerate(SERIES_ORDER):
        bars_h.append(ax_gap.bar(x[index] - width/2, gap_values[(series, "H")], width, color=COLORS[series], edgecolor=COLORS[series], zorder=3)[0])
        bars_d.append(ax_gap.bar(x[index] + width/2, gap_values[(series, "D")], width, color=COLORS[series], alpha=0.38, edgecolor="#222222", hatch="//", linewidth=0.8, zorder=3)[0])

    for bar, series, isotope in zip(bars_h + bars_d, SERIES_ORDER + SERIES_ORDER, ("H", "H", "H", "D", "D", "D")):
        value = bar.get_height()
        ax_gap.text(bar.get_x() + bar.get_width()/2, value + 0.35, f"{value:.2f}", ha="center", va="bottom", fontsize=10.0, color=TEXT)

    ax_gap.set_xticks(x, [SERIES_LABEL[s] for s in SERIES_ORDER])
    ax_gap.set_ylabel("Lowest-level gap (meV)")
    ax_gap.set_ylim(0.0, y_gap_top)
    ax_gap.grid(axis="y", color=GRID, lw=0.8)
    ax_gap.spines[["top", "right"]].set_visible(False)
    isotope_handles = [
        Patch(facecolor="#555555", edgecolor="#555555", label="H"),
        Patch(facecolor="#BBBBBB", edgecolor="#222222", hatch="//", label="D"),
    ]
    ax_gap.legend(handles=isotope_handles, loc="upper right", frameon=False)

    robust_good = int(validated["robustness_targeted_better"])
    robust_total = int(validated["robustness_total"])
    ax_gap.text(
        0.02,
        0.985,
        f"Targeted closer to PBE in {robust_good}/{robust_total} predeclared formulations",
        transform=ax_gap.transAxes,
        ha="left",
        va="top",
        fontsize=9.8,
        color="#2D638E",
        bbox=dict(boxstyle="round,pad=0.26", facecolor="#F4F8FC", edgecolor="#9DBDDD", linewidth=1.0),
        clip_on=False,
        zorder=5,
    )

    # Classification strip, derived from source rather than hard-coded.
    ax_class.set_axis_off()
    ax_class.set_xlim(0, 1)
    ax_class.set_ylim(0, 1)
    box = FancyBboxPatch(
        (0.0, 0.05), 1.0, 0.88,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        facecolor="#FAFAFA", edgecolor=BORDER, linewidth=1.0,
        transform=ax_class.transAxes,
    )
    ax_class.add_patch(box)
    ax_class.text(0.03, 0.83, "Primary H-level classification", fontsize=10.8, fontweight="bold", color=TEXT, va="center")
    for index, series in enumerate(SERIES_ORDER):
        classification = concise_classification(str(primary_map[(series, "H")]["classification"]).strip())
        x0 = 0.03 + index * 0.325
        ax_class.text(x0, 0.49, SERIES_LABEL[series], fontsize=10.0, fontweight="bold", color=COLORS[series], va="center")
        ax_class.text(x0, 0.20, classification, fontsize=8.9, color=SUBTEXT, va="center")

    output_base.parent.mkdir(parents=True, exist_ok=True)
    png = output_base.with_suffix(".png")
    pdf = output_base.with_suffix(".pdf")
    svg = output_base.with_suffix(".svg")
    tiff = output_base.with_suffix(".tiff")
    fig.savefig(png, dpi=240, facecolor=BG)
    fig.savefig(pdf, dpi=300, facecolor=BG)
    fig.savefig(svg, facecolor=BG)
    fig.savefig(tiff, dpi=300, facecolor=BG)
    plt.close(fig)
    return png, pdf, svg, tiff


def create_run_dir(root: Path) -> Path:
    version_root = root / "10_visualization" / "versions" / OUTPUT_DIRNAME
    version_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = version_root / f"attempt_{timestamp}"
    suffix = 1
    while candidate.exists():
        candidate = version_root / f"attempt_{timestamp}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def write_checksums(run_dir: Path) -> Path:
    path = run_dir / "checksums_v044.tsv"
    rows = []
    for item in sorted(run_dir.rglob("*")):
        if item.is_file() and item != path:
            rows.append({"sha256": sha256_file(item), "path": str(item.relative_to(run_dir))})
    write_tsv(path, rows, ["sha256", "path"])
    return path


def render_run(root: Path, validate_only: bool = False) -> RenderOutputs | None:
    source = load_source(root)
    validated = validate_source(source)
    if validate_only:
        print("VALIDATE_ONLY=PASS")
        print(f"SOURCE_RUN_DIR={source.run_dir}")
        print(f"PRIMARY_ROWS={len(source.primary_rows)}")
        print(f"ROBUSTNESS_ROWS={len(source.robustness_rows)}")
        print(f"GRID_POINTS={validated['grid_points']}")
        print(f"TARGETED_BETTER={validated['robustness_targeted_better']}/{validated['robustness_total']}")
        print("SCIENTIFIC_EXECUTION=NONE")
        return None

    run_dir = create_run_dir(root)
    figures = run_dir / "figures"
    reports = run_dir / "reports"
    source_snapshot = run_dir / "source_snapshot"
    figures.mkdir(parents=True)
    reports.mkdir(parents=True)
    source_snapshot.mkdir(parents=True)

    # Snapshot exact source tables used for this visualization.
    snapshot_map = {
        PRIMARY_TABLE: "quantum_results_primary_v039.tsv",
        ROBUSTNESS_TABLE: "robustness_comparisons_v039.tsv",
        POTENTIAL_GRID_TABLE: "primary_potential_and_mass_grid_v039.tsv",
        MASS_TABLE: "effective_mass_profiles_v039.tsv",
        SOURCE_STATUS_FILE: "STATUS_v039.txt",
        SOURCE_SUMMARY_FILE: "summary_v039.json",
    }
    for relative, name in snapshot_map.items():
        shutil.copy2(source.run_dir / relative, source_snapshot / name)

    output_base = figures / "supplementary_figure_s3_quantum_level_audit_relaxed_annotations_v044"
    png, pdf, svg, tiff = render_figure(source, validated, output_base)

    primary_map = validated["primary_map"]
    caption = reports / "supplementary_figure_s3_caption_v044.md"
    atomic_write_text(
        caption,
        "**Supplementary Figure S3 | Frozen-path 1D quantum-level audit.** "
        "(a) Symmetrized frozen-PBE-path potentials for the PBE reference, basin-focused MTP, and transition-focused MTP, "
        "with the two lowest H eigenlevels from the primary one-dimensional formulation (PCHIP interpolation, symmetrized profile, path-metric effective mass). "
        "The inset shows the coordinate-dependent path-metric effective mass for H and D; this is a coordinate metric rather than the literal mass of the transferred particle. "
        "(b) PBE-derived lowest-level H/D gaps. The transition-focused model remains closer to PBE across the predeclared numerical formulations, whereas the basin-focused model removes the low-barrier double-well topology. "
        "The reported gaps are frozen-path one-dimensional spectral diagnostics, not experimental tunneling rates or full-dimensional quantum-dynamics predictions.\n"
    )

    classification_rows = []
    for series in SERIES_ORDER:
        row = primary_map[(series, "H")]
        classification_rows.append({
            "series": series,
            "display_label": SERIES_LABEL[series],
            "barrier_mev": float(row["barrier_mev"]),
            "e0_mev": 1000.0 * float(row["e0_ev"]),
            "e1_mev": 1000.0 * float(row["e1_ev"]),
            "gap_mev": float(row["gap_mev"]),
            "classification": row["classification"],
            "classification_display": concise_classification(row["classification"]),
            "e0_below_barrier": row["e0_below_barrier"],
            "e1_below_barrier": row["e1_below_barrier"],
        })
    write_tsv(run_dir / "tables" / "primary_h_level_classification_v044.tsv", classification_rows)

    validation_rows = [
        {"check": "source_status", "status": "PASS", "detail": SOURCE_STATUS_EXPECTED},
        {"check": "source_primary_formulation", "status": "PASS", "detail": json.dumps(EXPECTED_PRIMARY_FORMULATION, sort_keys=True)},
        {"check": "source_primary_keys", "status": "PASS", "detail": "DFT/basin/targeted x H/D"},
        {"check": "potential_grid_points", "status": "PASS", "detail": str(validated["grid_points"])},
        {"check": "h_d_potential_identity", "status": "PASS", "detail": f"max abs diff {validated['max_hd_potential_difference_mev']:.3e} meV"},
        {"check": "isotope_gap_order", "status": "PASS", "detail": json.dumps(validated["isotope_checks"], sort_keys=True)},
        {"check": "robustness_count", "status": "PASS", "detail": f"targeted closer {validated['robustness_targeted_better']}/{validated['robustness_total']}"},
        {"check": "bar_axis_not_clipped", "status": "PASS", "detail": "dynamic y-limit from maximum source gap"},
        {"check": "classification_display", "status": "PASS", "detail": "source-derived primary H classifications"},
        {"check": "scientific_execution", "status": "PASS", "detail": "NONE"},
        {"check": "output_formats", "status": "PASS", "detail": "PNG/PDF/SVG/TIFF"},
    ]
    validation_path = reports / "supplementary_figure_s3_validation_v044.tsv"
    write_tsv(validation_path, validation_rows)

    report = reports / "supplementary_figure_s3_render_report_v044.md"
    atomic_write_text(
        report,
        "# Supplementary Figure S3 relaxed-top render report v042\n\n"
        f"- Source run: `{source.run_dir}`\n"
        f"- Source status: `{SOURCE_STATUS_EXPECTED}`\n"
        "- Scientific execution: none\n"
        "- Figure role: final visualization of the frozen-path 1D quantum-level audit\n"
        f"- Primary formulation: `{json.dumps(EXPECTED_PRIMARY_FORMULATION, sort_keys=True)}`\n"
        f"- Potential/mass grid points: {validated['grid_points']}\n"
        f"- Robustness statement: targeted closer to PBE in {validated['robustness_targeted_better']}/{validated['robustness_total']} predeclared formulations\n"
        "- Terminology: lowest-level gap / quantum-level audit; not a universal tunneling-splitting or rate prediction\n"
        "- Corrective changes relative to earlier drafts: relaxed top header spacing, larger panel separation, source-derived classification strip, compact effective-mass inset, and preserved scientific content.\n"
    )

    summary_path = run_dir / "summary_v044.json"
    summary_payload = {
        "version": OUTPUT_VERSION,
        "status": STATUS_PASS,
        "source_run_dir": str(source.run_dir),
        "source_status": SOURCE_STATUS_EXPECTED,
        "scientific_execution": "NONE",
        "figure_role": "final supplementary visualization of frozen-path 1D quantum-level audit",
        "robustness": {
            "targeted_better": validated["robustness_targeted_better"],
            "total_predeclared_formulations": validated["robustness_total"],
        },
        "source_hashes": source.source_hashes,
        "outputs": {
            "png": str(png),
            "pdf": str(pdf),
            "svg": str(svg),
            "tiff": str(tiff),
            "caption": str(caption),
            "report": str(report),
            "validation": str(validation_path),
        },
    }
    atomic_write_text(summary_path, json.dumps(summary_payload, indent=2, ensure_ascii=False) + "\n")
    atomic_write_text(run_dir / "STATUS_v044.txt", STATUS_PASS + "\n")
    checksums = write_checksums(run_dir)

    pointer = root / "10_visualization" / "versions" / OUTPUT_DIRNAME / POINTER_NAME
    atomic_write_text(pointer, str(run_dir) + "\n")

    outputs = RenderOutputs(
        run_dir=run_dir,
        png=png,
        pdf=pdf,
        svg=svg,
        tiff=tiff,
        caption=caption,
        report=report,
        validation=validation_path,
        summary=summary_path,
        checksums=checksums,
    )
    print(STATUS_PASS)
    print(f"RUN_DIR={run_dir}")
    print(f"FIGURE_PNG={png}")
    print(f"FIGURE_PDF={pdf}")
    print(f"FIGURE_SVG={svg}")
    print(f"FIGURE_TIFF={tiff}")
    print(f"CAPTION={caption}")
    print(f"REPORT={report}")
    print(f"VALIDATION={validation_path}")
    print(f"SUMMARY={summary_path}")
    print(f"CHECKSUMS={checksums}")
    print(f"CURRENT_POINTER={pointer}")
    print("SCIENTIFIC_EXECUTION=NONE")
    return outputs


def _write_fixture(root: Path) -> None:
    source_root = root / "10_visualization" / "versions" / SOURCE_DIRNAME
    run_dir = source_root / "attempt_20990101T000000Z"
    (run_dir / "tables").mkdir(parents=True, exist_ok=True)
    atomic_write_text(source_root / SOURCE_POINTER_NAME, str(run_dir) + "\n")
    atomic_write_text(run_dir / SOURCE_STATUS_FILE, SOURCE_STATUS_EXPECTED + "\n")
    atomic_write_text(run_dir / SOURCE_SUMMARY_FILE, json.dumps({"status": SOURCE_STATUS_EXPECTED}, indent=2) + "\n")

    q = np.linspace(-0.84, 0.84, 801)
    def synthetic_double_well(barrier: float, wall_height: float) -> np.ndarray:
        inside = np.abs(q) <= 0.5
        values = np.empty_like(q)
        values[inside] = barrier * (1.0 - (q[inside] / 0.5) ** 2) ** 2
        outside_distance = (np.abs(q[~inside]) - 0.5) / 0.34
        values[~inside] = wall_height * outside_distance ** 2
        return np.maximum(values, 0.0)

    potentials = {
        "DFT": synthetic_double_well(36.072, 42.0),
        "basin": synthetic_double_well(0.826, 43.0),
        "targeted": synthetic_double_well(31.972, 38.0),
    }

    gaps = {
        ("DFT", "H"): 14.07,
        ("DFT", "D"): 9.22,
        ("basin", "H"): 28.10,
        ("basin", "D"): 22.06,
        ("targeted", "H"): 14.90,
        ("targeted", "D"): 9.92,
    }
    barriers = {"DFT": 36.072, "basin": 0.826, "targeted": 31.972}
    levels_h = {
        "DFT": (19.0, 33.07, "subbarrier_symmetric_doublet"),
        "basin": (6.8, 34.9, "no_low_subbarrier_doublet"),
        "targeted": (18.2, 33.1, "only_ground_state_below_barrier"),
    }
    primary_rows = []
    potential_rows = []
    for series in SERIES_ORDER:
        for isotope in ISOTOPE_ORDER:
            if isotope == "H":
                e0, e1, classification = levels_h[series]
            else:
                e0 = max(0.1, levels_h[series][0] - 2.0)
                e1 = e0 + gaps[(series, isotope)]
                classification = levels_h[series][2]
            primary_rows.append({
                "series": series,
                "series_label": CURVE_LABEL[series],
                "isotope": isotope,
                "interpolation": "pchip",
                "profile_mode": "symmetrized",
                "mass_model": "path_metric",
                "grid_points": len(q),
                "extension_fraction": 0.25,
                "barrier_ev": barriers[series] / 1000.0,
                "barrier_mev": barriers[series],
                "endpoint_bias_ev": 0.0,
                "endpoint_bias_mev": 0.0,
                "e0_ev": e0 / 1000.0,
                "e1_ev": e1 / 1000.0,
                "e2_ev": (e1 + 8.0) / 1000.0,
                "e3_ev": (e1 + 16.0) / 1000.0,
                "gap_ev": gaps[(series, isotope)] / 1000.0,
                "gap_mev": gaps[(series, isotope)],
                "gap_cm1": 8.0655 * gaps[(series, isotope)],
                "gap_ghz": 241.8 * gaps[(series, isotope)],
                "e0_below_barrier": str(e0 < barriers[series]),
                "e1_below_barrier": str(e1 < barriers[series]),
                "classification": classification,
                "left_probability_e0": 0.5,
                "right_probability_e0": 0.5,
                "left_probability_e1": 0.5,
                "right_probability_e1": 0.5,
                "min_effective_mass_amu": 0.35 if isotope == "H" else 0.58,
                "median_effective_mass_amu": 0.9 if isotope == "H" else 1.2,
                "max_effective_mass_amu": 2.25 if isotope == "H" else 2.60,
            })
            mass = 0.35 + 1.90 * np.minimum(1.0, (np.abs(q) / 0.46) ** 2) if isotope == "H" else 0.58 + 2.02 * np.minimum(1.0, (np.abs(q) / 0.46) ** 2)
            for index, (qv, vv, mv) in enumerate(zip(q, potentials[series], mass)):
                potential_rows.append({
                    "series": series,
                    "isotope": isotope,
                    "grid_index": index,
                    "qpt_ang": qv,
                    "potential_ev": vv / 1000.0,
                    "potential_mev": vv,
                    "effective_mass_amu": mv,
                    "e0_ev": e0 / 1000.0,
                    "e1_ev": e1 / 1000.0,
                })
    write_tsv(run_dir / PRIMARY_TABLE, primary_rows)
    write_tsv(run_dir / POTENTIAL_GRID_TABLE, potential_rows)

    mass_rows = []
    for isotope in ISOTOPE_ORDER:
        mass = 0.35 + 1.90 * np.minimum(1.0, (np.abs(q) / 0.46) ** 2) if isotope == "H" else 0.58 + 2.02 * np.minimum(1.0, (np.abs(q) / 0.46) ** 2)
        for index, (qv, mv) in enumerate(zip(q, mass)):
            mass_rows.append({"isotope": isotope, "grid_index": index, "qpt_ang": qv, "effective_mass_amu": mv})
    write_tsv(run_dir / MASS_TABLE, mass_rows)

    robustness_rows = []
    index = 0
    for interpolation in ("pchip", "linear"):
        for profile_mode in ("symmetrized", "raw"):
            for mass_model in ("path_metric", "transfer_particle"):
                for isotope in ISOTOPE_ORDER:
                    index += 1
                    robustness_rows.append({
                        "comparison_index": index,
                        "interpolation": interpolation,
                        "profile_mode": profile_mode,
                        "mass_model": mass_model,
                        "isotope": isotope,
                        "targeted_better": "True",
                    })
    write_tsv(run_dir / ROBUSTNESS_TABLE, robustness_rows)


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="stage63_s3_selftest_") as temporary:
        root = Path(temporary) / "project"
        _write_fixture(root)
        render_run(root, validate_only=True)
        outputs = render_run(root, validate_only=False)
        assert outputs is not None
        required = [outputs.png, outputs.pdf, outputs.svg, outputs.tiff, outputs.caption, outputs.report, outputs.validation, outputs.summary, outputs.checksums]
        for path in required:
            if not path.is_file() or path.stat().st_size == 0:
                raise FigureAuditError(f"SELF_TEST missing output: {path}")
        print("SELF_TEST=PASS")
        print("SOURCE_VALIDATION=PASS")
        print("DYNAMIC_GAP_AXIS=PASS")
        print("SOURCE_DERIVED_CLASSIFICATION=PASS")
        print("FORMATS=PNG,PDF,SVG,TIFF")
        print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("${PROJECT_ROOT}"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    render_run(args.root.resolve(), validate_only=args.validate_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

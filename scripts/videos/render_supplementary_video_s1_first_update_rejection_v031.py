#!/usr/bin/env python3
"""Supplementary Video S1 v031: tiny update, immediate rejection.

Render a clean, checksum-locked animation of the six endpoint/first-update
MaxVol grade pairs recovered in the v005 visualization source package.

The video shows only two measured states per attempted run. Connecting segments
encode pairing and visual change between those states; they are not physical
trajectories. MaxVol grade is an applicability criterion, not a measured DFT
energy or force error.

No DFT, NEB, model loading, training, MLP evaluation, LAMMPS, or MD is executed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
from PIL import Image, ImageDraw, ImageFont

IMPLEMENTATION_ID = "RENDER_SUPPLEMENTARY_VIDEO_S1_FIRST_UPDATE_REJECTION_V031"
VERSION = "v031"
OUTPUT_VERSION = "v031_supplementary_video_s1_first_update_rejection"
OUTPUT_POINTER = "CURRENT_SUPPLEMENTARY_VIDEO_S1_FIRST_UPDATE_REJECTION_V031.txt"
STATUS_PASS = "PASS_SUPPLEMENTARY_VIDEO_S1_FIRST_UPDATE_REJECTION_RENDERED_V031"
STATUS_FAIL = "FAIL_SUPPLEMENTARY_VIDEO_S1_FIRST_UPDATE_REJECTION_V031"

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
EXPECTED_INPUT_STATUS = "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"

FIRST_STEP_FILE = "source_data/first_step_extrapolation_v005.tsv"
RUN0_FILE = "source_data/run0_selection_consistency_v005.tsv"
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

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_DPI = 100
DEFAULT_FPS = 30
DEFAULT_DURATION_SECONDS = 5.8

BG = "#FFFFFF"
TEXT = "#202020"
MUTED = "#5D5D5D"
GRID = "#DDDDDD"
ENDPOINT = "#777777"
UPDATE = "#A31621"
UPDATE_LIGHT = "#D9A0A5"
THRESHOLD = "#D55E00"
EXTRAP = "#CC79A7"
ZONE_LOW = "#F4F4F4"
ZONE_MID = "#FCF3F8"
ZONE_HIGH = "#FFF7F7"

# Small x offsets keep endpoint markers distinct without implying extra x data.
X_JITTER = {
    "T100_left": -0.055,
    "T100_right": 0.055,
    "T300_left": -0.033,
    "T300_right": 0.033,
    "T500_left": -0.011,
    "T500_right": 0.011,
}

# Label positions avoid collisions between 66.4 and 67.9 on the log axis.
LABEL_Y = {
    "T300_right": 43.0,
    "T100_left": 56.0,
    "T300_left": 69.0,
    "T100_right": 84.0,
    "T500_left": 108.0,
    "T500_right": 151.0,
}

CASE_START = {
    "T100_left": 0.00,
    "T100_right": 0.07,
    "T300_left": 0.14,
    "T300_right": 0.21,
    "T500_left": 0.28,
    "T500_right": 0.35,
}
CASE_SPAN = 0.65


class VideoAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class LockedInputs:
    attempt: Path
    first_step_rows: list[dict[str, str]]
    run0_rows: list[dict[str, str]]
    oracle_contract: dict[str, Any]
    style: dict[str, Any]
    manifest_rows: list[dict[str, str]]
    summary: dict[str, Any]
    source_hashes: dict[str, str]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise VideoAuditError(f"Missing {label}: {path}")
    if path.stat().st_size <= 0:
        raise VideoAuditError(f"Empty {label}: {path}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    return require_file(path, "text file").read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(read_text(path))
    if not isinstance(value, dict):
        raise VideoAuditError(f"Expected JSON object: {path}")
    return value


def read_tsv(path: Path) -> list[dict[str, str]]:
    with require_file(path, "TSV file").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = [dict(row) for row in reader]
    if not rows:
        raise VideoAuditError(f"TSV has no rows: {path}")
    return rows


def parse_float(value: Any, label: str) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise VideoAuditError(f"Invalid float for {label}: {value!r}") from exc
    if not math.isfinite(result):
        raise VideoAuditError(f"Non-finite float for {label}: {value!r}")
    return result


def parse_int(value: Any, label: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise VideoAuditError(f"Invalid integer for {label}: {value!r}") from exc


def parse_bool(value: Any, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", ""}:
        return False
    raise VideoAuditError(f"Invalid boolean for {label}: {value!r}")


def close(a: float, b: float, tolerance: float = NUMERIC_TOLERANCE) -> bool:
    return abs(a - b) <= tolerance


def atomic_write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def atomic_write_tsv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    os.replace(temporary, path)


def resolve_input_attempt(root: Path) -> Path:
    version_root = (root / INPUT_RELATIVE_ROOT).resolve()
    pointer_path = require_file(version_root / INPUT_POINTER, "v005 current pointer")
    raw = pointer_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise VideoAuditError(f"Empty v005 pointer: {pointer_path}")
    attempt = Path(raw).expanduser().resolve()
    try:
        attempt.relative_to(version_root)
    except ValueError as exc:
        raise VideoAuditError(f"v005 pointer escapes expected version root: {attempt}") from exc
    if not attempt.is_dir():
        raise VideoAuditError(f"v005 pointer target is absent: {attempt}")
    status = read_text(attempt / STATUS_FILE).strip()
    if status != EXPECTED_INPUT_STATUS:
        raise VideoAuditError(f"Unexpected v005 status: observed={status}; expected={EXPECTED_INPUT_STATUS}")
    return attempt


def verify_checksum_entry(attempt: Path, checksum_rows: Sequence[Mapping[str, str]], relative_path: str) -> str:
    matches = [row for row in checksum_rows if row.get("relative_path") == relative_path]
    if len(matches) != 1:
        raise VideoAuditError(f"Expected one checksum row for {relative_path}; found {len(matches)}")
    target = require_file(attempt / relative_path, relative_path)
    expected_size = parse_int(matches[0]["size_bytes"], f"{relative_path} expected size")
    expected_hash = matches[0]["sha256"].strip()
    observed_size = target.stat().st_size
    observed_hash = sha256_file(target)
    if observed_size != expected_size or observed_hash != expected_hash:
        raise VideoAuditError(
            f"Input checksum mismatch for {relative_path}: size={observed_size}/{expected_size}; "
            f"sha256={observed_hash}/{expected_hash}"
        )
    return observed_hash


def load_locked_inputs(root: Path) -> LockedInputs:
    attempt = resolve_input_attempt(root)
    checksum_rows = read_tsv(attempt / CHECKSUM_FILE)
    relatives = (
        FIRST_STEP_FILE,
        RUN0_FILE,
        ORACLE_CONTRACT_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    source_hashes = {relative: verify_checksum_entry(attempt, checksum_rows, relative) for relative in relatives}
    return LockedInputs(
        attempt=attempt,
        first_step_rows=read_tsv(attempt / FIRST_STEP_FILE),
        run0_rows=read_tsv(attempt / RUN0_FILE),
        oracle_contract=read_json(attempt / ORACLE_CONTRACT_FILE),
        style=read_json(attempt / STYLE_FILE),
        manifest_rows=read_tsv(attempt / FIGURE_MANIFEST_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        source_hashes=source_hashes,
    )


def first_step_by_id(rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        trajectory_id = row.get("trajectory_id", "").strip()
        if not trajectory_id:
            raise VideoAuditError("First-step row has no trajectory_id")
        if trajectory_id in result:
            raise VideoAuditError(f"Duplicate trajectory_id: {trajectory_id}")
        result[trajectory_id] = dict(row)
    return result


def validate_inputs(inputs: LockedInputs) -> dict[str, Any]:
    rows = first_step_by_id(inputs.first_step_rows)
    if set(rows) != set(CASE_ORDER):
        raise VideoAuditError(f"Unexpected first-step cases: {sorted(rows)}")

    checks = 1
    for trajectory_id in CASE_ORDER:
        row = rows[trajectory_id]
        expected = EXPECTED_CASES[trajectory_id]
        observed = {
            "temperature_K": parse_float(row["temperature_K"], f"{trajectory_id} temperature"),
            "online": parse_float(row["original_online_break_grade"], f"{trajectory_id} online grade"),
            "offline": parse_float(row["offline_exact_break_mv_grade"], f"{trajectory_id} offline grade"),
            "endpoint": parse_float(row["offline_endpoint_mv_grade"], f"{trajectory_id} endpoint grade"),
            "displacement_ang": parse_float(row["break_vs_endpoint_max_abs_ang"], f"{trajectory_id} displacement"),
        }
        for field, value in observed.items():
            if not close(value, float(expected[field])):
                raise VideoAuditError(
                    f"Locked value mismatch for {trajectory_id}/{field}: observed={value}; expected={expected[field]}"
                )
            checks += 1
        if row["side"].strip() != expected["side"]:
            raise VideoAuditError(f"Side mismatch for {trajectory_id}")
        checks += 1
        if observed["endpoint"] >= EXTRAPOLATION_THRESHOLD:
            raise VideoAuditError(f"Endpoint is not below gamma=2 for {trajectory_id}")
        if observed["offline"] <= BREAK_THRESHOLD:
            raise VideoAuditError(f"First update does not exceed gamma=10 for {trajectory_id}")
        if not parse_bool(row["threshold_class_agreement"], f"{trajectory_id} threshold agreement"):
            raise VideoAuditError(f"Threshold class disagreement for {trajectory_id}")
        if row["source_oracle_replay_classification"] != EXPECTED_SOURCE_ORACLE_CLASSIFICATION:
            raise VideoAuditError(f"Source-oracle replay not exact for {trajectory_id}")
        if not parse_bool(row["geometry_provenance_exactly_recovered"], f"{trajectory_id} geometry provenance"):
            raise VideoAuditError(f"Geometry provenance not recovered for {trajectory_id}")
        if parse_bool(row["persistent_lammps_id_claim_allowed"], f"{trajectory_id} persistent ID claim"):
            raise VideoAuditError(f"Persistent LAMMPS identity claim unexpectedly allowed for {trajectory_id}")
        if parse_bool(row["physical_dft_error_measured"], f"{trajectory_id} DFT error measurement"):
            raise VideoAuditError(f"Physical DFT error unexpectedly marked measured for {trajectory_id}")
        checks += 7

    if len(inputs.run0_rows) != 6:
        raise VideoAuditError(f"Expected six run-0 controls; found {len(inputs.run0_rows)}")
    checks += 1
    for row in inputs.run0_rows:
        if parse_int(row["returncode"], "run0 returncode") != 0:
            raise VideoAuditError("A run-0 control returned non-zero")
        if parse_bool(row["break_detected"], "run0 break"):
            raise VideoAuditError("A run-0 control detected a break")
        if parse_int(row["dump_last_step"], "run0 step") != 0:
            raise VideoAuditError("A run-0 control advanced beyond step 0")
        if not close(parse_float(row["run0_vs_endpoint_max_abs_ang"], "run0 displacement"), 0.0):
            raise VideoAuditError("A run-0 control changed the endpoint geometry")
        if parse_bool(row["state_file_changed"], "run0 state change"):
            raise VideoAuditError("A run-0 control changed its state file")
    checks += 5

    return {
        "checks": checks,
        "case_count": len(CASE_ORDER),
        "endpoint_range": [
            min(parse_float(rows[c]["offline_endpoint_mv_grade"], "endpoint") for c in CASE_ORDER),
            max(parse_float(rows[c]["offline_endpoint_mv_grade"], "endpoint") for c in CASE_ORDER),
        ],
        "first_update_range": [
            min(parse_float(rows[c]["offline_exact_break_mv_grade"], "first update") for c in CASE_ORDER),
            max(parse_float(rows[c]["offline_exact_break_mv_grade"], "first update") for c in CASE_ORDER),
        ],
        "displacement_mA_range": [
            1000.0 * min(parse_float(rows[c]["break_vs_endpoint_max_abs_ang"], "displacement") for c in CASE_ORDER),
            1000.0 * max(parse_float(rows[c]["break_vs_endpoint_max_abs_ang"], "displacement") for c in CASE_ORDER),
        ],
    }


def snapshot_inputs(inputs: LockedInputs, destination: Path) -> None:
    relatives = (
        FIRST_STEP_FILE,
        RUN0_FILE,
        ORACLE_CONTRACT_FILE,
        STYLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
        CHECKSUM_FILE,
        STATUS_FILE,
    )
    for relative in relatives:
        src = inputs.attempt / relative
        dst = destination / relative
        ensure_dir(dst.parent)
        shutil.copy2(src, dst)


def create_run_dir(root: Path) -> Path:
    version_root = root / "10_visualization" / "versions" / OUTPUT_VERSION
    ensure_dir(version_root)
    run_dir = Path(tempfile.mkdtemp(prefix="attempt_", dir=str(version_root)))
    for name in ("frames", "video", "figures", "tables", "reports", "source_snapshot"):
        ensure_dir(run_dir / name)
    return run_dir


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def case_progress(global_reveal: float, case_id: str) -> float:
    start = CASE_START[case_id]
    return smoothstep((global_reveal - start) / CASE_SPAN)


def frame_timing(frame_index: int, frame_count: int) -> tuple[float, float]:
    """Return normalized time and global reveal progress.

    0.00–0.16: endpoint hold
    0.16–0.66: continuous staggered reveal
    0.66–1.00: final hold
    """
    if frame_count <= 1:
        t = 1.0
    else:
        t = frame_index / float(frame_count - 1)
    if t <= 0.16:
        reveal = 0.0
    elif t >= 0.66:
        reveal = 1.0
    else:
        reveal = (t - 0.16) / 0.50
    return t, reveal


def log_interpolate(start: float, end: float, fraction: float) -> float:
    return math.exp((1.0 - fraction) * math.log(start) + fraction * math.log(end))


def gradient_line(ax: Any, x0: float, y0: float, x1: float, y1: float, fraction: float, alpha: float) -> tuple[float, float]:
    fraction = max(0.0, min(1.0, fraction))
    if fraction <= 0.0:
        return x0, y0
    n_segments = max(2, int(40 * fraction))
    ts = np.linspace(0.0, fraction, n_segments + 1)
    xs = x0 + (x1 - x0) * ts
    ys = np.exp(np.log(y0) + (np.log(y1) - np.log(y0)) * ts)
    points = np.column_stack([xs, ys]).reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    cmap = LinearSegmentedColormap.from_list("endpoint_to_update", [ENDPOINT, UPDATE])
    collection = LineCollection(segments, cmap=cmap, linewidth=2.7, alpha=alpha, zorder=4)
    collection.set_array(ts[:-1])
    collection.set_clim(0.0, 1.0)
    ax.add_collection(collection)
    return float(xs[-1]), float(ys[-1])


def case_marker(side: str) -> str:
    return "^" if side == "left" else "o"


def label_for_case(case_id: str, row: Mapping[str, str]) -> str:
    temperature = int(round(parse_float(row["temperature_K"], "temperature")))
    side = "L" if row["side"].strip() == "left" else "R"
    displacement_mA = 1000.0 * parse_float(row["break_vs_endpoint_max_abs_ang"], "displacement")
    grade = parse_float(row["offline_exact_break_mv_grade"], "grade")
    return f"{temperature} K {side}   {displacement_mA:.2f} mÅ   γ={grade:.1f}"


def render_frame(
    rows: Mapping[str, Mapping[str, str]],
    frame_index: int,
    frame_count: int,
    destination: Path,
    *,
    width: int,
    height: int,
    dpi: int,
) -> dict[str, Any]:
    t, reveal = frame_timing(frame_index, frame_count)
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, facecolor=BG)

    fig.text(0.055, 0.935, "Tiny update, immediate rejection", ha="left", va="top", fontsize=32, fontweight="bold", color=TEXT)
    fig.text(
        0.055,
        0.885,
        "Endpoint and first-update states only",
        ha="left",
        va="top",
        fontsize=16,
        color=MUTED,
    )
    fig.text(
        0.055,
        0.852,
        "Paired segments indicate correspondence, not a physical trajectory.",
        ha="left",
        va="top",
        fontsize=12.8,
        color=MUTED,
    )

    ax = fig.add_axes([0.095, 0.205, 0.735, 0.615])
    ax.set_yscale("log")
    ax.set_xlim(-0.20, 1.52)
    ax.set_ylim(0.72, 230.0)

    ax.axhspan(0.72, EXTRAPOLATION_THRESHOLD, facecolor=ZONE_LOW, zorder=0)
    ax.axhspan(EXTRAPOLATION_THRESHOLD, BREAK_THRESHOLD, facecolor=ZONE_MID, zorder=0)
    ax.axhspan(BREAK_THRESHOLD, 230.0, facecolor=ZONE_HIGH, zorder=0)
    ax.axhline(EXTRAPOLATION_THRESHOLD, color=EXTRAP, lw=1.8, ls=(0, (5, 4)), zorder=1)
    ax.axhline(BREAK_THRESHOLD, color=THRESHOLD, lw=2.1, ls=(0, (5, 3)), zorder=1)

    ax.text(1.47, 1.34, "interpolative", ha="right", va="center", fontsize=11.5, color=MUTED)
    ax.text(1.47, 4.2, "extrapolative", ha="right", va="center", fontsize=11.5, color=EXTRAP)
    ax.text(1.47, 17.0, "rejected", ha="right", va="center", fontsize=11.5, color=THRESHOLD)

    ax.text(-0.17, EXTRAPOLATION_THRESHOLD * 1.06, r"$\gamma=2$", ha="left", va="bottom", fontsize=11.5, color=EXTRAP)
    ax.text(-0.17, BREAK_THRESHOLD * 1.06, r"$\gamma=10$ rejection threshold", ha="left", va="bottom", fontsize=11.5, color=THRESHOLD)

    completed = 0
    case_states: dict[str, dict[str, float]] = {}
    for case_id in CASE_ORDER:
        row = rows[case_id]
        p = case_progress(reveal, case_id)
        endpoint_grade = parse_float(row["offline_endpoint_mv_grade"], f"{case_id} endpoint")
        update_grade = parse_float(row["offline_exact_break_mv_grade"], f"{case_id} update")
        jitter = X_JITTER[case_id]
        x0 = 0.0 + jitter
        x1 = 1.0 + jitter
        marker = case_marker(row["side"].strip())

        ax.scatter(
            [x0],
            [endpoint_grade],
            s=92,
            marker=marker,
            facecolor="white",
            edgecolor=ENDPOINT,
            linewidth=1.7,
            zorder=7,
        )

        current_x, current_y = gradient_line(ax, x0, endpoint_grade, x1, update_grade, p, alpha=0.90)
        ax.scatter(
            [current_x],
            [current_y],
            s=98,
            marker=marker,
            facecolor=UPDATE if p > 0.02 else "white",
            edgecolor=UPDATE if p > 0.02 else ENDPOINT,
            linewidth=1.5,
            alpha=max(0.25, p),
            zorder=8,
        )

        if current_y > BREAK_THRESHOLD:
            completed += 1

        label_alpha = smoothstep((p - 0.58) / 0.42)
        label_y = LABEL_Y[case_id]
        if label_alpha > 0.005:
            ax.plot(
                [current_x + 0.018, 1.105, 1.145],
                [current_y, label_y, label_y],
                color=UPDATE_LIGHT,
                lw=1.1,
                alpha=0.75 * label_alpha,
                zorder=5,
            )
            ax.text(
                1.16,
                label_y,
                label_for_case(case_id, row),
                ha="left",
                va="center",
                fontsize=11.2,
                color=UPDATE,
                alpha=label_alpha,
                zorder=9,
            )
        case_states[case_id] = {"progress": p, "current_grade": current_y}

    ax.set_xticks([0.0, 1.0], ["accepted endpoint", "first free update"])
    ax.tick_params(axis="x", labelsize=15, pad=12)
    ax.set_ylabel(r"MaxVol applicability grade, $\gamma$", fontsize=16)
    ax.tick_params(axis="y", labelsize=12)
    ax.grid(axis="y", which="major", color=GRID, lw=0.8, alpha=0.65)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#666666")
    ax.spines["bottom"].set_color("#666666")

    fig.text(0.885, 0.94, f"{completed} / 6", ha="center", va="top", fontsize=40, fontweight="bold", color=UPDATE if completed else ENDPOINT)
    fig.text(0.885, 0.885, "updates rejected", ha="center", va="top", fontsize=15, color=MUTED)

    displacement_values = [1000.0 * parse_float(rows[c]["break_vs_endpoint_max_abs_ang"], "displacement") for c in CASE_ORDER]
    grade_values = [parse_float(rows[c]["offline_exact_break_mv_grade"], "first update grade") for c in CASE_ORDER]
    fig.text(
        0.095,
        0.117,
        f"maximum displacement: {min(displacement_values):.2f}–{max(displacement_values):.2f} mÅ   •   "
        f"first-update grade: {min(grade_values):.1f}–{max(grade_values):.1f}",
        ha="left",
        va="center",
        fontsize=16,
        color=TEXT,
    )
    fig.text(
        0.095,
        0.073,
        "MaxVol grade is an applicability criterion, not a measured DFT error.   •   Triangles: left; circles: right.",
        ha="left",
        va="center",
        fontsize=12.6,
        color=MUTED,
    )

    fig.savefig(destination, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return {"time_fraction": t, "reveal": reveal, "rejected_count": completed, "case_states": case_states}


def run_ffmpeg(frame_pattern: str, fps: int, output: Path, codec: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise VideoAuditError("ffmpeg is required for video encoding")
    if codec == "mp4":
        command = [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            frame_pattern,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output.as_posix(),
        ]
    elif codec == "webm":
        command = [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            frame_pattern,
            "-c:v",
            "libvpx-vp9",
            "-crf",
            "30",
            "-b:v",
            "0",
            "-pix_fmt",
            "yuv420p",
            output.as_posix(),
        ]
    else:
        raise ValueError(codec)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise VideoAuditError(f"ffmpeg failed for {output}:\n{result.stderr}")


def write_preview_gif(frame_paths: Sequence[Path], output: Path, fps: int, max_width: int = 960) -> None:
    images: list[Image.Image] = []
    for path in frame_paths:
        image = Image.open(path).convert("RGB")
        if image.width > max_width:
            height = int(round(image.height * max_width / image.width))
            image = image.resize((max_width, height), Image.Resampling.LANCZOS)
        images.append(image.convert("P", palette=Image.Palette.ADAPTIVE))
    duration = int(round(1000.0 / fps))
    images[0].save(output, save_all=True, append_images=images[1:], duration=duration, loop=0, disposal=2)
    for image in images:
        image.close()


def render_contact_sheet(frame_paths: Sequence[Path], labels: Sequence[str], destination: Path) -> None:
    images = [Image.open(path).convert("RGB") for path in frame_paths]
    thumb_width = 760
    thumb_height = int(round(images[0].height * thumb_width / images[0].width))
    cols = 2
    rows = 2
    pad = 28
    title_height = 70
    label_height = 30
    canvas = Image.new(
        "RGB",
        (
            pad + cols * thumb_width + (cols - 1) * pad + pad,
            title_height + rows * (label_height + thumb_height) + (rows - 1) * pad + pad,
        ),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((pad, 20), "Supplementary Video S1 v031 — endpoint to first-update applicability rejection", fill=(25, 25, 25), font=font)
    for index, (image, label) in enumerate(zip(images, labels)):
        row = index // cols
        col = index % cols
        x = pad + col * (thumb_width + pad)
        y = title_height + row * (label_height + thumb_height + pad)
        draw.text((x, y), label, fill=(25, 25, 25), font=font)
        canvas.paste(image.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS), (x, y + label_height))
    canvas.save(destination)
    for image in images:
        image.close()


def write_checksums(run_dir: Path) -> Path:
    output = run_dir / f"checksums_{VERSION}.tsv"
    rows = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path != output:
            rows.append({
                "relative_path": str(path.relative_to(run_dir)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    atomic_write_tsv(output, ["relative_path", "size_bytes", "sha256"], rows)
    return output


def render_attempt(
    root: Path,
    inputs: LockedInputs,
    *,
    width: int,
    height: int,
    dpi: int,
    fps: int,
    duration_seconds: float,
) -> dict[str, Any]:
    validation = validate_inputs(inputs)
    rows = first_step_by_id(inputs.first_step_rows)
    run_dir = create_run_dir(root)
    snapshot_inputs(inputs, run_dir / "source_snapshot")

    frame_count = max(2, int(round(fps * duration_seconds)))
    frame_paths: list[Path] = []
    manifest_rows: list[dict[str, Any]] = []
    for frame_index in range(frame_count):
        path = run_dir / "frames" / f"supplementary_video_s1_frame_{frame_index:04d}.png"
        state = render_frame(rows, frame_index, frame_count, path, width=width, height=height, dpi=dpi)
        frame_paths.append(path)
        manifest_rows.append({
            "frame_index": frame_index,
            "time_seconds": frame_index / float(fps),
            "time_fraction": state["time_fraction"],
            "reveal": state["reveal"],
            "rejected_count": state["rejected_count"],
        })

    mp4 = run_dir / "video" / f"supplementary_video_s1_first_update_rejection_{VERSION}.mp4"
    webm = run_dir / "video" / f"supplementary_video_s1_first_update_rejection_{VERSION}.webm"
    gif = run_dir / "video" / f"supplementary_video_s1_first_update_rejection_preview_{VERSION}.gif"
    pattern = str(run_dir / "frames" / "supplementary_video_s1_frame_%04d.png")
    run_ffmpeg(pattern, fps, mp4, "mp4")
    run_ffmpeg(pattern, fps, webm, "webm")

    # Preview GIF uses every second frame at full render, every frame in small tests.
    gif_stride = 2 if len(frame_paths) > 100 else 1
    gif_frames = frame_paths[::gif_stride]
    write_preview_gif(gif_frames, gif, max(1, fps // gif_stride))

    selected_indices = [0, int(0.27 * (frame_count - 1)), int(0.58 * (frame_count - 1)), frame_count - 1]
    selected_paths = [frame_paths[index] for index in selected_indices]
    selected_labels = ["endpoint hold", "continuous reveal", "threshold crossings", "6 / 6 rejected"]
    contact_sheet = run_dir / "figures" / f"supplementary_video_s1_contact_sheet_{VERSION}.png"
    render_contact_sheet(selected_paths, selected_labels, contact_sheet)
    poster = run_dir / "figures" / f"supplementary_video_s1_final_poster_{VERSION}.png"
    shutil.copy2(frame_paths[-1], poster)

    case_manifest = []
    for case_id in CASE_ORDER:
        row = rows[case_id]
        case_manifest.append({
            "trajectory_id": case_id,
            "temperature_K": row["temperature_K"],
            "side": row["side"],
            "endpoint_grade": row["offline_endpoint_mv_grade"],
            "first_update_grade": row["offline_exact_break_mv_grade"],
            "online_first_update_grade": row["original_online_break_grade"],
            "maximum_displacement_ang": row["break_vs_endpoint_max_abs_ang"],
            "maximum_displacement_milliangstrom": 1000.0 * parse_float(row["break_vs_endpoint_max_abs_ang"], "displacement"),
            "source_oracle_replay_classification": row["source_oracle_replay_classification"],
            "physical_dft_error_measured": row["physical_dft_error_measured"],
        })
    atomic_write_tsv(
        run_dir / "tables" / f"supplementary_video_s1_case_manifest_{VERSION}.tsv",
        list(case_manifest[0].keys()),
        case_manifest,
    )
    atomic_write_tsv(
        run_dir / "tables" / f"supplementary_video_s1_frame_manifest_{VERSION}.tsv",
        list(manifest_rows[0].keys()),
        manifest_rows,
    )

    caption = (
        "Supplementary Video S1. Six checksum-locked source-oracle endpoint/first-update pairs are shown for targeted-MTP "
        "attempts initiated from the left and right endpoints at 100, 300, and 500 K. All endpoint grades are near one, "
        "whereas every first-update grade lies above the rejection threshold gamma = 10. The maximum coordinate displacement "
        "is only 1.96–4.04 mÅ, but the first-update grades span 47.8–147.7. Connecting segments pair the two measured states; "
        "they do not represent physical trajectories. MaxVol grade is an applicability criterion, not a measured DFT error.\n"
    )
    atomic_write_text(run_dir / f"supplementary_video_s1_caption_{VERSION}.md", caption)

    report = (
        "# Supplementary Video S1 v031 render report\n\n"
        f"- implementation: `{IMPLEMENTATION_ID}`\n"
        f"- input attempt: `{inputs.attempt}`\n"
        f"- output attempt: `{run_dir}`\n"
        f"- resolution: `{width}x{height}`\n"
        f"- fps: `{fps}`\n"
        f"- frame count: `{frame_count}`\n"
        f"- duration: `{frame_count / float(fps):.3f} s`\n"
        "- motion: one continuous staggered reveal; no stop-start holds between cases\n"
        "- popup annotations: none\n"
        "- scientific execution: none\n"
        "- source interpretation: endpoint and first-update states only; connecting segments are not trajectories\n"
    )
    atomic_write_text(run_dir / "reports" / f"supplementary_video_s1_report_{VERSION}.md", report)

    validation_rows = [
        {"check": "locked_input_checks", "status": "PASS", "detail": validation["checks"]},
        {"check": "case_count", "status": "PASS", "detail": len(CASE_ORDER)},
        {"check": "all_endpoints_below_gamma_2", "status": "PASS", "detail": "6/6"},
        {"check": "all_first_updates_above_gamma_10", "status": "PASS", "detail": "6/6"},
        {"check": "full_video_rendered", "status": "PASS", "detail": "TRUE"},
        {"check": "scientific_execution", "status": "PASS", "detail": "NONE"},
    ]
    atomic_write_tsv(
        run_dir / "reports" / f"supplementary_video_s1_validation_{VERSION}.tsv",
        ["check", "status", "detail"],
        validation_rows,
    )

    summary = {
        "schema_version": "1.0",
        "implementation": IMPLEMENTATION_ID,
        "status": STATUS_PASS,
        "input_attempt": str(inputs.attempt),
        "output_attempt": str(run_dir),
        "scientific_execution": "NONE",
        "full_video_rendered": True,
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frame_count,
        "duration_seconds": frame_count / float(fps),
        "endpoint_grade_range": validation["endpoint_range"],
        "first_update_grade_range": validation["first_update_range"],
        "displacement_milliangstrom_range": validation["displacement_mA_range"],
        "source_hashes": inputs.source_hashes,
        "outputs": {
            "mp4": str(mp4),
            "webm": str(webm),
            "gif": str(gif),
            "contact_sheet": str(contact_sheet),
            "poster": str(poster),
        },
    }
    atomic_write_json(run_dir / f"summary_{VERSION}.json", summary)
    atomic_write_text(run_dir / f"STATUS_{VERSION}.txt", STATUS_PASS + "\n")
    checksums = write_checksums(run_dir)

    pointer = root / "10_visualization" / "versions" / OUTPUT_VERSION / OUTPUT_POINTER
    atomic_write_text(pointer, str(run_dir) + "\n")

    return {
        "run_dir": run_dir,
        "mp4": mp4,
        "webm": webm,
        "gif": gif,
        "contact_sheet": contact_sheet,
        "poster": poster,
        "checksums": checksums,
        "pointer": pointer,
        "summary": run_dir / f"summary_{VERSION}.json",
        "report": run_dir / "reports" / f"supplementary_video_s1_report_{VERSION}.md",
        "frame_count": frame_count,
    }


def make_synthetic_fixture(root: Path) -> Path:
    attempt = root / INPUT_RELATIVE_ROOT / "attempt_20990101T000000Z"
    ensure_dir(attempt / "source_data")

    first_step_rows: list[dict[str, Any]] = []
    for case_id in CASE_ORDER:
        expected = EXPECTED_CASES[case_id]
        first_step_rows.append({
            "trajectory_id": case_id,
            "temperature_K": expected["temperature_K"],
            "side": expected["side"],
            "seed": 0,
            "original_online_break_grade": expected["online"],
            "preselected_feature_mv_grade": expected["online"],
            "canonicalization_mode": "species_assignment",
            "canonicalization_candidate_count": 288,
            "raw_atom_ids": "1,2,3,4,5,6,7,8,9",
            "raw_atom_types": "1,0,2,1,2,0,1,0,1",
            "canonical_order_zero_based": "4,0,5,6,7,8,1,2,3",
            "break_vs_endpoint_max_abs_ang": expected["displacement_ang"],
            "break_vs_endpoint_rms_ang": expected["displacement_ang"] / 2.7,
            "break_vs_endpoint_kabsch_rmsd_ang": expected["displacement_ang"] / 4.0,
            "break_vs_endpoint_pair_distance_max_abs_delta_ang": expected["displacement_ang"] * 1.2,
            "break_vs_dump0_max_abs_ang": expected["displacement_ang"],
            "break_vs_dump0_rms_ang": expected["displacement_ang"] / 2.7,
            "break_vs_dump0_kabsch_rmsd_ang": expected["displacement_ang"] / 4.0,
            "dump0_vs_endpoint_max_abs_ang": 0.0,
            "dump0_vs_endpoint_rms_ang": 0.0,
            "dump0_vs_endpoint_kabsch_rmsd_ang": 0.0,
            "break_qpt_ang": -0.48 if expected["side"] == "left" else 0.48,
            "break_roo_ang": 2.499,
            "break_minimum_pair_ang": 1.04,
            "break_maximum_span_ang": 4.34,
            "preselected_path": "/synthetic/preselected.cfg",
            "offline_exact_break_mv_grade": expected["offline"],
            "offline_endpoint_mv_grade": expected["endpoint"],
            "online_over_offline_exact": expected["online"] / expected["offline"],
            "threshold_class_agreement": True,
            "displacement_max_milliangstrom": 1000.0 * expected["displacement_ang"],
            "displacement_rms_milliangstrom": 1000.0 * expected["displacement_ang"] / 2.7,
            "grade_jump": expected["offline"] - expected["endpoint"],
            "grade_ratio_break_over_endpoint": expected["offline"] / expected["endpoint"],
            "online_offline_abs_difference": abs(expected["online"] - expected["offline"]),
            "online_offline_relative_difference": abs(expected["online"] - expected["offline"]) / expected["offline"],
            "temperature_side_label": case_id,
            "first_step_extrapolative": True,
            "source_oracle_replay_classification": EXPECTED_SOURCE_ORACLE_CLASSIFICATION,
            "source_oracle_exact_position_array_path": "result.positions",
            "source_oracle_exact_position_array_paths": "result.positions",
            "source_oracle_kabsch_scalar_paths": "result.kabsch",
            "source_oracle_calculated_max_abs_ang": expected["displacement_ang"],
            "source_oracle_calculated_component_rms_ang": expected["displacement_ang"] / 2.7,
            "source_oracle_calculated_pair_distance_max_delta_ang": expected["displacement_ang"] * 1.2,
            "source_oracle_calculated_qpt_ang": -0.48 if expected["side"] == "left" else 0.48,
            "source_oracle_calculated_roo_ang": 2.499,
            "source_oracle_provenance_sha256": "synthetic",
            "source_oracle_adapter_sha256": "synthetic",
            "geometry_provenance_exactly_recovered": True,
            "persistent_lammps_id_claim_allowed": False,
            "deployment_interpretation": "immediate_MaxVol_applicability_rejection_after_first_attempted_integration_update",
            "physical_dft_error_measured": False,
        })
    atomic_write_tsv(attempt / FIRST_STEP_FILE, list(first_step_rows[0].keys()), first_step_rows)

    run0_rows = []
    for side in ("left", "right"):
        for repeat in (1, 2, 3):
            run0_rows.append({
                "side": side,
                "repeat": repeat,
                "returncode": 0,
                "break_detected": False,
                "dump_last_step": 0,
                "run0_vs_endpoint_max_abs_ang": 0.0,
                "run0_vs_endpoint_rms_ang": 0.0,
                "state_file_changed": False,
            })
    atomic_write_tsv(attempt / RUN0_FILE, list(run0_rows[0].keys()), run0_rows)
    atomic_write_json(attempt / ORACLE_CONTRACT_FILE, {"classification": EXPECTED_SOURCE_ORACLE_CLASSIFICATION})
    atomic_write_json(attempt / STYLE_FILE, {"palette": {"failure": UPDATE}})
    atomic_write_tsv(attempt / FIGURE_MANIFEST_FILE, ["figure_id", "status"], [{"figure_id": "Figure_3", "status": "SOURCE_DATA_READY"}])
    atomic_write_json(attempt / SUMMARY_FILE, {"status": EXPECTED_INPUT_STATUS})
    atomic_write_text(attempt / STATUS_FILE, EXPECTED_INPUT_STATUS + "\n")

    checksum_rows = []
    for relative in (FIRST_STEP_FILE, RUN0_FILE, ORACLE_CONTRACT_FILE, STYLE_FILE, FIGURE_MANIFEST_FILE, SUMMARY_FILE):
        path = attempt / relative
        checksum_rows.append({
            "relative_path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    atomic_write_tsv(attempt / CHECKSUM_FILE, ["relative_path", "size_bytes", "sha256"], checksum_rows)
    atomic_write_text(root / INPUT_RELATIVE_ROOT / INPUT_POINTER, str(attempt) + "\n")
    return attempt


def perform_validate_only(root: Path) -> int:
    inputs = load_locked_inputs(root)
    validation = validate_inputs(inputs)
    print("VALIDATE_ONLY=PASS")
    print(f"INPUT_ATTEMPT={inputs.attempt}")
    print(f"CASE_COUNT={validation['case_count']}")
    print(f"VALIDATION_CHECKS={validation['checks']}")
    print(f"ENDPOINT_GRADE_RANGE={validation['endpoint_range'][0]:.6f},{validation['endpoint_range'][1]:.6f}")
    print(f"FIRST_UPDATE_GRADE_RANGE={validation['first_update_range'][0]:.6f},{validation['first_update_range'][1]:.6f}")
    print(f"DISPLACEMENT_MA_RANGE={validation['displacement_mA_range'][0]:.6f},{validation['displacement_mA_range'][1]:.6f}")
    print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="supp_video_s1_v031_selftest_") as temporary:
        root = Path(temporary) / "root"
        ensure_dir(root)
        make_synthetic_fixture(root)
        inputs = load_locked_inputs(root)
        validation = validate_inputs(inputs)
        result = render_attempt(
            root,
            inputs,
            width=960,
            height=540,
            dpi=100,
            fps=12,
            duration_seconds=2.5,
        )
        for path in (result["mp4"], result["webm"], result["gif"], result["contact_sheet"], result["poster"]):
            if not path.is_file() or path.stat().st_size <= 0:
                raise VideoAuditError(f"Self-test missing output: {path}")
        print("SELF_TEST=PASS")
        print(f"VALIDATION_CHECKS={validation['checks']}")
        print("CASE_COUNT=6")
        print("FORMATS=MP4,WEBM,GIF,PNG")
        print("CHECKSUM_LOCK=PASS")
        print("FULL_VIDEO_RENDERED=TRUE")
        print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("${PROJECT_ROOT}"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--duration-seconds", type=float, default=DEFAULT_DURATION_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.self_test:
            return self_test()
        if arguments.validate_only:
            return perform_validate_only(arguments.root)
        inputs = load_locked_inputs(arguments.root)
        result = render_attempt(
            arguments.root,
            inputs,
            width=arguments.width,
            height=arguments.height,
            dpi=arguments.dpi,
            fps=arguments.fps,
            duration_seconds=arguments.duration_seconds,
        )
        print(STATUS_PASS)
        print(f"RUN_DIR={result['run_dir']}")
        print(f"VIDEO_MP4={result['mp4']}")
        print(f"VIDEO_WEBM={result['webm']}")
        print(f"VIDEO_GIF={result['gif']}")
        print(f"CONTACT_SHEET={result['contact_sheet']}")
        print(f"POSTER={result['poster']}")
        print(f"REPORT={result['report']}")
        print(f"SUMMARY={result['summary']}")
        print(f"CHECKSUMS={result['checksums']}")
        print(f"CURRENT_POINTER={result['pointer']}")
        print(f"FRAME_COUNT={result['frame_count']}")
        print("FULL_VIDEO_RENDERED=TRUE")
        print("SCIENTIFIC_EXECUTION=NONE")
        return 0
    except Exception as exc:
        print(f"{STATUS_FAIL}: {type(exc).__name__}: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

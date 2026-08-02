#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import math
import os
import shutil
import sys

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from strict_postaudit_common_v001 import (
    VERSIONS,
    finite_float,
    read_tsv,
    require_file,
    require_hash,
    resolve_attempt,
    sha256,
    utc_now,
    utc_stamp,
    write_checksums,
    write_tsv,
)


IMPLEMENTATION_ID = "STEP32B_V030R_PRIMARY_METRIC_PROTOCOL_RECOVERY_V001"

V028_POINTER = (
    VERSIONS
    / "v028_equal_budget_l12_training"
    / "CURRENT_EQUAL_BUDGET_L12_MODELS.txt"
)
V029_POINTER = (
    VERSIONS
    / "v029_frozen_audit21_evaluation"
    / "CURRENT_FROZEN_AUDIT21_EVALUATION.txt"
)
V030_POINTER = (
    VERSIONS
    / "v030_final_primary_analysis"
    / "CURRENT_FINAL_PRIMARY_ANALYSIS.txt"
)

VERSION_ROOT = VERSIONS / "v030_protocol_metric_recovery"
CURRENT_POINTER = (
    VERSION_ROOT / "CURRENT_PRIMARY_METRIC_PROTOCOL_RECOVERY.txt"
)

STAMP = utc_stamp()
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"

INPUTS_DIR = RUN_ROOT / "inputs"
TABLES_DIR = RUN_ROOT / "tables"
FIGURES_DIR = RUN_ROOT / "figures"
REPORTS_DIR = RUN_ROOT / "reports"
PROVENANCE_DIR = RUN_ROOT / "provenance"

STATUS_FILE = RUN_ROOT / "STATUS_v030r.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v030r.json"
REPORT_MD = REPORTS_DIR / "primary_metric_protocol_recovery_v030r.md"
PRIMARY_METRICS_TSV = TABLES_DIR / "preregistered_primary_metrics_v030r.tsv"
TRANSITION_ROWS_TSV = TABLES_DIR / "transition_region_rows_v030r.tsv"
BARRIER_PROFILE_TSV = TABLES_DIR / "lower_endpoint_barrier_profile_v030r.tsv"
FIGURE_MANIFEST_TSV = FIGURES_DIR / "figure_manifest_v030r.tsv"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v030r.tsv"

EXPECTED_V028_STATUS = (
    "PASS_EQUAL_BUDGET_L12_MODELS_LOCKED_READY_FOR_FROZEN_AUDIT"
)
EXPECTED_V029_STATUS = (
    "PASS_FROZEN_AUDIT21_EVALUATED_NO_POST_AUDIT_TUNING"
)
EXPECTED_V030_STATUS = "PASS_FINAL_PRIMARY_ANALYSIS_AND_FIGURES"

EXPECTED_BASIN_MODEL_SHA256 = (
    "45d80443c5f62cdfa30bbd1512cf58e31cd16fe2bb0b50cec147a92350d7a7ff"
)
EXPECTED_TARGETED_MODEL_SHA256 = (
    "30175dae673d63e0b318e5e3ba311a9f61afe88929a5d19c69a744a47aeef99f"
)

TRANSITION_QPT_LIMIT_ANG = 0.15
TRANSITION_MINIMUM_IMAGES = 3

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V030R_PREFLIGHT_ONLY", "0") == "1"
)


def number(row: dict[str, str], key: str) -> float:
    return finite_float(row.get(key), key)


def save_figure(
    figure: plt.Figure,
    stem: str,
    description: str,
    manifest: list[dict[str, Any]],
) -> None:
    png = FIGURES_DIR / f"{stem}.png"
    pdf = FIGURES_DIR / f"{stem}.pdf"
    figure.tight_layout()
    figure.savefig(png, dpi=220, bbox_inches="tight")
    figure.savefig(pdf, bbox_inches="tight")
    plt.close(figure)
    manifest.append(
        {
            "figure": stem,
            "description": description,
            "png": png,
            "png_sha256": sha256(png),
            "pdf": pdf,
            "pdf_sha256": sha256(pdf),
        }
    )


def load_inputs() -> dict[str, Any]:
    v028 = resolve_attempt(
        V028_POINTER,
        "STATUS_v028.txt",
        EXPECTED_V028_STATUS,
        "v028",
    )
    v029 = resolve_attempt(
        V029_POINTER,
        "STATUS_v029.txt",
        EXPECTED_V029_STATUS,
        "v029",
    )
    v030 = resolve_attempt(
        V030_POINTER,
        "STATUS_v030.txt",
        EXPECTED_V030_STATUS,
        "v030 superseded analysis",
    )

    basin_model = require_file(
        v028 / "models" / "basin" / "pot_basin60_l12_v001.mtp",
        "basin model",
    )
    targeted_model = require_file(
        v028
        / "models"
        / "targeted"
        / "pot_targeted60_l12_v001.mtp",
        "targeted model",
    )
    require_hash(basin_model, EXPECTED_BASIN_MODEL_SHA256, "basin model")
    require_hash(
        targeted_model,
        EXPECTED_TARGETED_MODEL_SHA256,
        "targeted model",
    )

    per_configuration_path = require_file(
        v029 / "reports" / "per_configuration_errors_v029.tsv",
        "per-configuration audit errors",
    )
    profile_path = require_file(
        v029 / "reports" / "neb9_energy_profile_v029.tsv",
        "NEB9 energy profile",
    )
    subset_path = require_file(
        v029 / "reports" / "subset_metrics_v029.tsv",
        "subset metrics",
    )
    grades_path = require_file(
        v029 / "reports" / "grade_metrics_v029.tsv",
        "grade metrics",
    )
    original_summary = require_file(
        v030 / "summary_v030.json",
        "superseded v030 summary",
    )
    original_report = require_file(
        v030 / "reports" / "final_primary_result_v030.md",
        "superseded v030 report",
    )

    per_rows = read_tsv(per_configuration_path)
    profile_rows = read_tsv(profile_path)
    subset_rows = read_tsv(subset_path)
    grade_rows = read_tsv(grades_path)

    counts = {
        model: sum(
            row["model"] == model and row["subset"] == "neb9"
            for row in per_rows
        )
        for model in ("basin", "targeted")
    }
    if counts != {"basin": 9, "targeted": 9}:
        raise RuntimeError(f"unexpected per-configuration NEB9 counts: {counts}")

    profile_counts = {
        model: sum(row["model"] == model for row in profile_rows)
        for model in ("basin", "targeted")
    }
    if profile_counts != {"basin": 9, "targeted": 9}:
        raise RuntimeError(f"unexpected profile counts: {profile_counts}")

    return {
        "v028": v028,
        "v029": v029,
        "v030": v030,
        "basin_model": basin_model,
        "targeted_model": targeted_model,
        "paths": {
            "per_configuration": per_configuration_path,
            "profile": profile_path,
            "subset": subset_path,
            "grades": grades_path,
            "original_summary": original_summary,
            "original_report": original_report,
        },
        "per_rows": per_rows,
        "profile_rows": profile_rows,
        "subset_rows": subset_rows,
        "grade_rows": grade_rows,
    }


def transition_rows(
    per_rows: list[dict[str, str]],
    model: str,
) -> list[dict[str, str]]:
    neb = [
        row
        for row in per_rows
        if row["model"] == model and row["subset"] == "neb9"
    ]
    selected = [
        row
        for row in neb
        if abs(number(row, "qpt_ang")) <= TRANSITION_QPT_LIMIT_ANG
    ]

    if len(selected) < TRANSITION_MINIMUM_IMAGES:
        internal = [
            row
            for row in neb
            if 2 <= int(row["subset_index"]) <= 8
        ]
        selected = sorted(
            internal,
            key=lambda row: abs(number(row, "qpt_ang")),
        )[:TRANSITION_MINIMUM_IMAGES]

    selected = sorted(
        selected,
        key=lambda row: int(row["subset_index"]),
    )
    if len(selected) != TRANSITION_MINIMUM_IMAGES:
        raise RuntimeError(
            f"{model}: transition selection count={len(selected)}, "
            f"expected {TRANSITION_MINIMUM_IMAGES}"
        )
    return selected


def combined_transition_force_rmse(
    rows: list[dict[str, str]],
) -> float:
    values = np.asarray(
        [
            number(row, "force_component_rmse_ev_ang")
            for row in rows
        ],
        dtype=float,
    )
    return float(np.sqrt(np.mean(values ** 2)))


def lower_endpoint_barriers(
    profile_rows: list[dict[str, str]],
) -> dict[str, Any]:
    dft_reference = sorted(
        [
            row
            for row in profile_rows
            if row["model"] == "basin"
        ],
        key=lambda row: int(row["image"]),
    )
    dft_energies = np.asarray(
        [number(row, "dft_energy_ev") for row in dft_reference],
        dtype=float,
    )
    dft_lower_endpoint = float(
        min(dft_energies[0], dft_energies[-1])
    )
    dft_barrier = float(np.max(dft_energies) - dft_lower_endpoint)

    result: dict[str, Any] = {
        "dft": {
            "energies": dft_energies,
            "lower_endpoint_ev": dft_lower_endpoint,
            "barrier_ev": dft_barrier,
            "maximum_image": int(np.argmax(dft_energies)) + 1,
        }
    }

    for model in ("basin", "targeted"):
        model_rows = sorted(
            [row for row in profile_rows if row["model"] == model],
            key=lambda row: int(row["image"]),
        )
        energies = np.asarray(
            [number(row, "model_energy_ev") for row in model_rows],
            dtype=float,
        )
        lower_endpoint = float(min(energies[0], energies[-1]))
        barrier = float(np.max(energies) - lower_endpoint)
        error = barrier - dft_barrier
        result[model] = {
            "rows": model_rows,
            "energies": energies,
            "lower_endpoint_ev": lower_endpoint,
            "barrier_ev": barrier,
            "barrier_error_ev": error,
            "barrier_abs_error_mev": abs(error) * 1000.0,
            "maximum_image": int(np.argmax(energies)) + 1,
        }
    return result


def main() -> None:
    data = load_inputs()

    basin_transition_rows = transition_rows(data["per_rows"], "basin")
    targeted_transition_rows = transition_rows(
        data["per_rows"],
        "targeted",
    )
    basin_transition_force = combined_transition_force_rmse(
        basin_transition_rows
    )
    targeted_transition_force = combined_transition_force_rmse(
        targeted_transition_rows
    )

    barriers = lower_endpoint_barriers(data["profile_rows"])
    dft_barrier = barriers["dft"]["barrier_ev"]
    basin_barrier_error_mev = barriers["basin"][
        "barrier_abs_error_mev"
    ]
    targeted_barrier_error_mev = barriers["targeted"][
        "barrier_abs_error_mev"
    ]

    transition_force_improvement = (
        basin_transition_force / targeted_transition_force
    )
    barrier_error_improvement = (
        basin_barrier_error_mev / targeted_barrier_error_mev
    )

    primary_gate_pass = (
        targeted_transition_force < basin_transition_force
        and targeted_barrier_error_mev < basin_barrier_error_mev
    )

    selected_images = [
        int(row["subset_index"]) for row in basin_transition_rows
    ]
    selected_qpts = [
        number(row, "qpt_ang") for row in basin_transition_rows
    ]

    if selected_images != [
        int(row["subset_index"]) for row in targeted_transition_rows
    ]:
        raise RuntimeError("transition image selection differs by model")

    if PREFLIGHT_ONLY:
        print("PASS_V030R_PREFLIGHT_PROTOCOL_RECOVERY_NO_CALCULATIONS")
        print(f"source v028:              {data['v028']}")
        print(f"source v029:              {data['v029']}")
        print(f"superseded v030:          {data['v030']}")
        print(
            "transition images:       "
            + ",".join(str(value) for value in selected_images)
        )
        print(
            "transition qPT:          "
            + ", ".join(f"{value:+.8f}" for value in selected_qpts)
            + " A"
        )
        print(
            "transition F RMSE:       "
            f"{basin_transition_force:.12f} basin / "
            f"{targeted_transition_force:.12f} targeted eV/A"
        )
        print(f"DFT lower-end barrier:    {dft_barrier:.12f} eV")
        print(
            "barrier abs errors:      "
            f"{basin_barrier_error_mev:.9f} basin / "
            f"{targeted_barrier_error_mev:.9f} targeted meV"
        )
        print(
            "primary gate:            "
            + ("PASS" if primary_gate_pass else "FAIL")
        )
        print("attempt directory:        NOT CREATED")
        print("mlp/QE/NEB/LAMMPS:        NOT EXECUTED")
        return

    if RUN_ROOT.exists():
        raise RuntimeError(f"attempt already exists: {RUN_ROOT}")

    for directory in (
        INPUTS_DIR,
        TABLES_DIR,
        FIGURES_DIR,
        REPORTS_DIR,
        PROVENANCE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    for source in data["paths"].values():
        shutil.copy2(source, INPUTS_DIR / source.name)

    shutil.copy2(
        Path(__file__).resolve(),
        PROVENANCE_DIR / Path(__file__).name,
    )
    helper_source = Path(__file__).resolve().with_name(
        "strict_postaudit_common_v001.py"
    )
    if helper_source.is_file():
        shutil.copy2(
            helper_source,
            PROVENANCE_DIR / helper_source.name,
        )

    transition_output_rows: list[dict[str, Any]] = []
    for model, rows in (
        ("basin", basin_transition_rows),
        ("targeted", targeted_transition_rows),
    ):
        for row in rows:
            transition_output_rows.append(
                {
                    "model": model,
                    "image": int(row["subset_index"]),
                    "qpt_ang": number(row, "qpt_ang"),
                    "force_component_rmse_ev_ang": number(
                        row,
                        "force_component_rmse_ev_ang",
                    ),
                    "force_component_mae_ev_ang": number(
                        row,
                        "force_component_mae_ev_ang",
                    ),
                    "force_component_max_abs_ev_ang": number(
                        row,
                        "force_component_max_abs_ev_ang",
                    ),
                    "selection_rule":
                        f"abs(qPT)<={TRANSITION_QPT_LIMIT_ANG:.2f} A",
                }
            )
    write_tsv(TRANSITION_ROWS_TSV, transition_output_rows)

    barrier_profile_rows: list[dict[str, Any]] = []
    dft_rows = sorted(
        [
            row
            for row in data["profile_rows"]
            if row["model"] == "basin"
        ],
        key=lambda row: int(row["image"]),
    )
    for index, dft_row in enumerate(dft_rows):
        barrier_profile_rows.append(
            {
                "series": "DFT",
                "image": int(dft_row["image"]),
                "qpt_ang": number(dft_row, "qpt_ang"),
                "energy_ev": number(dft_row, "dft_energy_ev"),
                "delta_e_from_lower_endpoint_ev":
                    number(dft_row, "dft_energy_ev")
                    - barriers["dft"]["lower_endpoint_ev"],
            }
        )
    for model in ("basin", "targeted"):
        for index, row in enumerate(barriers[model]["rows"]):
            energy = barriers[model]["energies"][index]
            barrier_profile_rows.append(
                {
                    "series": model,
                    "image": int(row["image"]),
                    "qpt_ang": number(row, "qpt_ang"),
                    "energy_ev": energy,
                    "delta_e_from_lower_endpoint_ev":
                        energy - barriers[model]["lower_endpoint_ev"],
                }
            )
    write_tsv(BARRIER_PROFILE_TSV, barrier_profile_rows)

    primary_rows = [
        {
            "metric": "transition_force_component_rmse_ev_ang",
            "definition":
                "combined components over NEB images with abs(qPT)<=0.15 A",
            "basin": basin_transition_force,
            "targeted": targeted_transition_force,
            "targeted_minus_basin":
                targeted_transition_force - basin_transition_force,
            "basin_over_targeted":
                transition_force_improvement,
            "targeted_better": targeted_transition_force < basin_transition_force,
        },
        {
            "metric": "lower_endpoint_barrier_abs_error_mev",
            "definition":
                "abs[(max E - min(endpoint E))_model - "
                "(max E - min(endpoint E))_DFT]",
            "basin": basin_barrier_error_mev,
            "targeted": targeted_barrier_error_mev,
            "targeted_minus_basin":
                targeted_barrier_error_mev - basin_barrier_error_mev,
            "basin_over_targeted":
                barrier_error_improvement,
            "targeted_better":
                targeted_barrier_error_mev < basin_barrier_error_mev,
        },
    ]
    write_tsv(PRIMARY_METRICS_TSV, primary_rows)

    figure_manifest: list[dict[str, Any]] = []

    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    for series in ("DFT", "basin", "targeted"):
        rows = [
            row
            for row in barrier_profile_rows
            if row["series"] == series
        ]
        rows.sort(key=lambda row: int(row["image"]))
        axis.plot(
            [float(row["qpt_ang"]) for row in rows],
            [
                1000.0 * float(
                    row["delta_e_from_lower_endpoint_ev"]
                )
                for row in rows
            ],
            marker="o",
            label=series,
        )
    axis.axvline(0.0, linewidth=0.8, linestyle="--")
    axis.set_xlabel(r"$q_{\mathrm{PT}}$ (Å)")
    axis.set_ylabel(
        r"$\Delta E$ from lower endpoint (meV)"
    )
    axis.set_title(
        "Frozen NEB9 profile using preregistered endpoint reference"
    )
    axis.legend()
    axis.grid(True, alpha=0.25)
    save_figure(
        figure,
        "figure_01_lower_endpoint_neb9_profile",
        "DFT and model profiles referenced to each series' lower endpoint.",
        figure_manifest,
    )

    figure, axis = plt.subplots(figsize=(7.0, 4.8))
    x = np.arange(2)
    values = [
        basin_transition_force,
        targeted_transition_force,
    ]
    axis.bar(x, values)
    axis.set_xticks(x, ["basin", "targeted"])
    axis.set_ylabel("Transition force-component RMSE (eV/Å)")
    axis.set_title(
        "Preregistered transition-region force metric "
        "(NEB images 4–6)"
    )
    axis.grid(True, axis="y", alpha=0.25)
    save_figure(
        figure,
        "figure_02_transition_force_rmse",
        "Combined force-component RMSE for the preregistered transition region.",
        figure_manifest,
    )

    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    for model in ("basin", "targeted"):
        rows = [
            row
            for row in transition_output_rows
            if row["model"] == model
        ]
        rows.sort(key=lambda row: int(row["image"]))
        axis.plot(
            [float(row["qpt_ang"]) for row in rows],
            [
                float(row["force_component_rmse_ev_ang"])
                for row in rows
            ],
            marker="o",
            label=model,
        )
    axis.axvline(0.0, linewidth=0.8, linestyle="--")
    axis.set_xlabel(r"$q_{\mathrm{PT}}$ (Å)")
    axis.set_ylabel("Per-image force-component RMSE (eV/Å)")
    axis.set_title("Force errors in the preregistered transition region")
    axis.legend()
    axis.grid(True, alpha=0.25)
    save_figure(
        figure,
        "figure_03_transition_force_by_image",
        "Per-image force-component errors for NEB images 4, 5 and 6.",
        figure_manifest,
    )

    figure, axis = plt.subplots(figsize=(7.0, 4.8))
    values = [
        dft_barrier * 1000.0,
        barriers["basin"]["barrier_ev"] * 1000.0,
        barriers["targeted"]["barrier_ev"] * 1000.0,
    ]
    axis.bar(np.arange(3), values)
    axis.set_xticks(
        np.arange(3),
        ["DFT", "basin MTP", "targeted MTP"],
    )
    axis.set_ylabel("Lower-endpoint barrier (meV)")
    axis.set_title("Preregistered proton-transfer barrier")
    axis.grid(True, axis="y", alpha=0.25)
    save_figure(
        figure,
        "figure_04_lower_endpoint_barrier",
        "DFT and model barriers using max(E)-min(endpoint energies).",
        figure_manifest,
    )

    figure, axis = plt.subplots(figsize=(7.0, 4.8))
    axis.bar(
        np.arange(2),
        [basin_barrier_error_mev, targeted_barrier_error_mev],
    )
    axis.set_xticks(np.arange(2), ["basin", "targeted"])
    axis.set_ylabel("Absolute barrier error (meV)")
    axis.set_title("Preregistered lower-endpoint barrier error")
    axis.grid(True, axis="y", alpha=0.25)
    save_figure(
        figure,
        "figure_05_lower_endpoint_barrier_error",
        "Absolute errors of the preregistered barrier metric.",
        figure_manifest,
    )

    write_tsv(
        FIGURE_MANIFEST_TSV,
        figure_manifest,
        [
            "figure",
            "description",
            "png",
            "png_sha256",
            "pdf",
            "pdf_sha256",
        ],
    )

    status = (
        "PASS_PRIMARY_METRIC_PROTOCOL_RECOVERY_AND_FIGURES"
        if primary_gate_pass
        else "FAIL_PRIMARY_GATE_TARGETED_NOT_BETTER"
    )
    STATUS_FILE.write_text(status + "\n", encoding="utf-8")

    summary = {
        "created_utc": utc_now(),
        "status": status,
        "implementation_id": IMPLEMENTATION_ID,
        "run_root": str(RUN_ROOT),
        "source_v028": str(data["v028"]),
        "source_v029": str(data["v029"]),
        "superseded_v030": str(data["v030"]),
        "supersession_reason":
            "v030 used forward-from-left barrier and all-NEB force RMSE "
            "instead of the preregistered lower-endpoint barrier and "
            "transition-region force RMSE.",
        "preregistered_primary_metrics": {
            "transition_region": {
                "selection_rule":
                    f"abs(qPT)<={TRANSITION_QPT_LIMIT_ANG:.2f} A; "
                    "fallback to three internal images nearest zero",
                "images": selected_images,
                "qpt_ang": selected_qpts,
                "force_component_rmse_ev_ang": {
                    "basin": basin_transition_force,
                    "targeted": targeted_transition_force,
                    "improvement_factor":
                        transition_force_improvement,
                },
            },
            "lower_endpoint_barrier": {
                "definition":
                    "max(E1..E9)-min(E1,E9)",
                "dft_barrier_ev": dft_barrier,
                "basin_barrier_ev":
                    barriers["basin"]["barrier_ev"],
                "targeted_barrier_ev":
                    barriers["targeted"]["barrier_ev"],
                "absolute_error_mev": {
                    "basin": basin_barrier_error_mev,
                    "targeted": targeted_barrier_error_mev,
                    "improvement_factor":
                        barrier_error_improvement,
                },
            },
        },
        "primary_gate": {
            "targeted_transition_force_lower": (
                targeted_transition_force < basin_transition_force
            ),
            "targeted_barrier_error_lower": (
                targeted_barrier_error_mev < basin_barrier_error_mev
            ),
            "pass": primary_gate_pass,
        },
        "scientific_integrity": {
            "new_scientific_calculation": False,
            "mlp_executed": False,
            "qe_executed": False,
            "lammps_executed": False,
            "post_audit_training": False,
            "metric_definition_changed": False,
            "metric_implementation_corrected": True,
        },
        "outputs": {
            "primary_metrics": str(PRIMARY_METRICS_TSV),
            "transition_rows": str(TRANSITION_ROWS_TSV),
            "barrier_profile": str(BARRIER_PROFILE_TSV),
            "figures": [
                {
                    key: str(value) if isinstance(value, Path) else value
                    for key, value in row.items()
                }
                for row in figure_manifest
            ],
            "report": str(REPORT_MD),
        },
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    REPORT_MD.write_text(
        f"""# Primary metric protocol recovery v030r

Created UTC: {utc_now()}

Status: `{status}`

## Why this recovery exists

The immutable v030 analysis used two descriptive audit metrics as if
they were the preregistered primary metrics:

- force-component RMSE over all nine NEB images;
- forward barrier measured from the left endpoint.

The locked protocol instead requires:

- transition-region force-component RMSE for `|qPT| <= 0.15 Å`;
- barrier `max(E1..E9) - min(E1,E9)`.

No model, label, prediction or scientific calculation was changed.
v029 remains the authoritative frozen audit. v030 remains immutable and
is marked as superseded for primary-metric interpretation.

## Preregistered transition-force metric

Selected images: {", ".join(str(value) for value in selected_images)}

Selected qPT values:
{", ".join(f"{value:+.8f}" for value in selected_qpts)} Å

- basin: {basin_transition_force:.12f} eV/Å;
- targeted: {targeted_transition_force:.12f} eV/Å;
- improvement: {transition_force_improvement:.6f}x.

## Preregistered lower-endpoint barrier

- DFT: {dft_barrier:.12f} eV;
- basin model: {barriers['basin']['barrier_ev']:.12f} eV;
- targeted model: {barriers['targeted']['barrier_ev']:.12f} eV;
- basin absolute error: {basin_barrier_error_mev:.9f} meV;
- targeted absolute error: {targeted_barrier_error_mev:.9f} meV;
- improvement: {barrier_error_improvement:.6f}x.

## Primary gate

Targeted transition-force RMSE lower: {
    targeted_transition_force < basin_transition_force
}

Targeted lower-endpoint barrier error lower: {
    targeted_barrier_error_mev < basin_barrier_error_mev
}

Overall primary gate: `{"PASS" if primary_gate_pass else "FAIL"}`

No MLP, Quantum ESPRESSO, NEB or LAMMPS executable was run.
""",
        encoding="utf-8",
    )

    write_checksums(RUN_ROOT, CHECKSUMS_TSV)
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    print()
    print(
        f"{status}: STEP 32B v030r COMPLETED"
    )
    print()
    print(f"Run root:                  {RUN_ROOT}")
    print(
        "Transition F RMSE:         "
        f"{basin_transition_force:.12f} -> "
        f"{targeted_transition_force:.12f} eV/A"
    )
    print(
        "Transition improvement:    "
        f"{transition_force_improvement:.6f}x"
    )
    print(
        "Barrier abs error:         "
        f"{basin_barrier_error_mev:.9f} -> "
        f"{targeted_barrier_error_mev:.9f} meV"
    )
    print(
        "Barrier improvement:       "
        f"{barrier_error_improvement:.6f}x"
    )
    print(
        "Primary gate:              "
        + ("PASS" if primary_gate_pass else "FAIL")
    )
    print(f"Report:                    {REPORT_MD}")
    print(f"Summary:                   {SUMMARY_JSON}")
    print()
    print("No scientific executable was run.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

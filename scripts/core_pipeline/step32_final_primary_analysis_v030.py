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
    ROOT,
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


IMPLEMENTATION_ID = "STEP32_V030_FINAL_PRIMARY_ANALYSIS_V001"

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

VERSION_ROOT = VERSIONS / "v030_final_primary_analysis"
CURRENT_POINTER = VERSION_ROOT / "CURRENT_FINAL_PRIMARY_ANALYSIS.txt"

STAMP = utc_stamp()
RUN_ROOT = VERSION_ROOT / f"attempt_{STAMP}"

INPUTS_DIR = RUN_ROOT / "inputs"
TABLES_DIR = RUN_ROOT / "tables"
FIGURES_DIR = RUN_ROOT / "figures"
REPORTS_DIR = RUN_ROOT / "reports"
PROVENANCE_DIR = RUN_ROOT / "provenance"

STATUS_FILE = RUN_ROOT / "STATUS_v030.txt"
SUMMARY_JSON = RUN_ROOT / "summary_v030.json"
REPORT_MD = REPORTS_DIR / "final_primary_result_v030.md"
FIGURE_MANIFEST_TSV = FIGURES_DIR / "figure_manifest_v030.tsv"
CHECKSUMS_TSV = RUN_ROOT / "checksums_v030.tsv"

EXPECTED_V028_STATUS = (
    "PASS_EQUAL_BUDGET_L12_MODELS_LOCKED_READY_FOR_FROZEN_AUDIT"
)
EXPECTED_V029_STATUS = (
    "PASS_FROZEN_AUDIT21_EVALUATED_NO_POST_AUDIT_TUNING"
)
EXPECTED_BASIN_MODEL_SHA256 = (
    "45d80443c5f62cdfa30bbd1512cf58e31cd16fe2bb0b50cec147a92350d7a7ff"
)
EXPECTED_TARGETED_MODEL_SHA256 = (
    "30175dae673d63e0b318e5e3ba311a9f61afe88929a5d19c69a744a47aeef99f"
)

PREFLIGHT_ONLY = (
    "--preflight-only" in sys.argv
    or os.environ.get("V030_PREFLIGHT_ONLY", "0") == "1"
)


def index_rows(
    rows: list[dict[str, str]],
    *keys: str,
) -> dict[tuple[str, ...], dict[str, str]]:
    result: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row[name] for name in keys)
        if key in result:
            raise RuntimeError(f"duplicate TSV key {key}")
        result[key] = row
    return result


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

    required_tables = {
        "subset": require_file(
            v029 / "reports" / "subset_metrics_v029.tsv",
            "subset metrics",
        ),
        "grades": require_file(
            v029 / "reports" / "grade_metrics_v029.tsv",
            "grade metrics",
        ),
        "barriers": require_file(
            v029 / "reports" / "neb9_barrier_metrics_v029.tsv",
            "barrier metrics",
        ),
        "profile": require_file(
            v029 / "reports" / "neb9_energy_profile_v029.tsv",
            "NEB profile",
        ),
        "per_configuration": require_file(
            v029 / "reports" / "per_configuration_errors_v029.tsv",
            "per-configuration errors",
        ),
        "comparison": require_file(
            v029 / "reports" / "model_comparison_v029.tsv",
            "model comparison",
        ),
    }
    rows = {name: read_tsv(path) for name, path in required_tables.items()}

    subset_index = index_rows(rows["subset"], "model", "subset")
    grade_index = index_rows(rows["grades"], "model", "subset")
    barrier_index = index_rows(rows["barriers"], "model")

    for model in ("basin", "targeted"):
        for subset_name in ("all21", "basin12", "neb9"):
            if (model, subset_name) not in subset_index:
                raise RuntimeError(f"missing subset row {(model, subset_name)}")
            if (model, subset_name) not in grade_index:
                raise RuntimeError(f"missing grade row {(model, subset_name)}")
        if (model,) not in barrier_index:
            raise RuntimeError(f"missing barrier row {model}")

    profile_counts = {
        model: sum(row["model"] == model for row in rows["profile"])
        for model in ("basin", "targeted")
    }
    if profile_counts != {"basin": 9, "targeted": 9}:
        raise RuntimeError(f"unexpected NEB profile counts: {profile_counts}")

    per_counts = {
        model: sum(
            row["model"] == model
            for row in rows["per_configuration"]
        )
        for model in ("basin", "targeted")
    }
    if per_counts != {"basin": 21, "targeted": 21}:
        raise RuntimeError(f"unexpected per-configuration counts: {per_counts}")

    return {
        "v028": v028,
        "v029": v029,
        "basin_model": basin_model,
        "targeted_model": targeted_model,
        "tables": required_tables,
        "rows": rows,
        "subset_index": subset_index,
        "grade_index": grade_index,
        "barrier_index": barrier_index,
    }


def main() -> None:
    data = load_inputs()
    subset = data["subset_index"]
    barriers = data["barrier_index"]
    rows = data["rows"]

    basin_neb_e = number(subset[("basin", "neb9")], "energy_rmse_ev")
    targeted_neb_e = number(
        subset[("targeted", "neb9")],
        "energy_rmse_ev",
    )
    basin_neb_f = number(
        subset[("basin", "neb9")],
        "force_component_rmse_ev_ang",
    )
    targeted_neb_f = number(
        subset[("targeted", "neb9")],
        "force_component_rmse_ev_ang",
    )
    basin_basin_e = number(
        subset[("basin", "basin12")],
        "energy_rmse_ev",
    )
    targeted_basin_e = number(
        subset[("targeted", "basin12")],
        "energy_rmse_ev",
    )
    basin_basin_f = number(
        subset[("basin", "basin12")],
        "force_component_rmse_ev_ang",
    )
    targeted_basin_f = number(
        subset[("targeted", "basin12")],
        "force_component_rmse_ev_ang",
    )
    basin_profile = number(
        barriers[("basin",)],
        "profile_rmse_ev",
    )
    targeted_profile = number(
        barriers[("targeted",)],
        "profile_rmse_ev",
    )
    basin_barrier_error = number(
        barriers[("basin",)],
        "forward_barrier_abs_error_mev",
    )
    targeted_barrier_error = number(
        barriers[("targeted",)],
        "forward_barrier_abs_error_mev",
    )

    ratios = {
        "neb9_energy_rmse_improvement":
            basin_neb_e / targeted_neb_e,
        "neb9_force_rmse_improvement":
            basin_neb_f / targeted_neb_f,
        "neb_profile_rmse_improvement":
            basin_profile / targeted_profile,
        "forward_barrier_error_improvement":
            basin_barrier_error / targeted_barrier_error,
        "basin12_energy_rmse_cost":
            targeted_basin_e / basin_basin_e,
        "basin12_force_rmse_cost":
            targeted_basin_f / basin_basin_f,
    }

    if PREFLIGHT_ONLY:
        print("PASS_V030_PREFLIGHT_NO_SCIENTIFIC_EXECUTABLES")
        print(f"source v028:              {data['v028']}")
        print(f"source v029:              {data['v029']}")
        print("models:                   locked and hash-verified")
        print("audit tables:             6/6 validated")
        print("NEB profile rows:         9 basin + 9 targeted")
        print("per-configuration rows:   21 basin + 21 targeted")
        print(
            "NEB energy improvement:  "
            f"{ratios['neb9_energy_rmse_improvement']:.3f}x"
        )
        print(
            "barrier-error improvement:"
            f" {ratios['forward_barrier_error_improvement']:.3f}x"
        )
        print("attempt directory:        NOT CREATED")
        print("mlp/QE/LAMMPS:            NOT EXECUTED")
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

    for source in data["tables"].values():
        shutil.copy2(source, INPUTS_DIR / source.name)
    shutil.copy2(Path(__file__).resolve(), PROVENANCE_DIR / Path(__file__).name)
    helper_source = Path(__file__).resolve().with_name(
        "strict_postaudit_common_v001.py"
    )
    if helper_source.is_file():
        shutil.copy2(helper_source, PROVENANCE_DIR / helper_source.name)

    figure_manifest: list[dict[str, Any]] = []

    profile_by_model: dict[str, list[dict[str, str]]] = {}
    for model in ("basin", "targeted"):
        model_rows = [
            row for row in rows["profile"] if row["model"] == model
        ]
        model_rows.sort(key=lambda row: int(row["image"]))
        profile_by_model[model] = model_rows

    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    dft_rows = profile_by_model["basin"]
    axis.plot(
        [number(row, "qpt_ang") for row in dft_rows],
        [
            1000.0 * number(row, "dft_delta_e_from_left_ev")
            for row in dft_rows
        ],
        marker="o",
        linewidth=2,
        label="DFT",
    )
    for model in ("basin", "targeted"):
        model_rows = profile_by_model[model]
        axis.plot(
            [number(row, "qpt_ang") for row in model_rows],
            [
                1000.0 * number(row, "model_delta_e_from_left_ev")
                for row in model_rows
            ],
            marker="o",
            linewidth=1.8,
            label=f"{model} MTP",
        )
    axis.set_xlabel(r"$q_{\mathrm{PT}}$ (Å)")
    axis.set_ylabel(r"$\Delta E$ from left endpoint (meV)")
    axis.set_title("Frozen DFT NEB9 energy profile")
    axis.axvline(0.0, linewidth=0.8, linestyle="--")
    axis.legend()
    axis.grid(True, alpha=0.25)
    save_figure(
        figure,
        "figure_01_neb9_energy_profile",
        "DFT, basin-MTP and targeted-MTP relative energies along qPT.",
        figure_manifest,
    )

    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    for model in ("basin", "targeted"):
        model_rows = [
            row
            for row in rows["per_configuration"]
            if row["model"] == model and row["subset"] == "neb9"
        ]
        model_rows.sort(key=lambda row: int(row["subset_index"]))
        axis.plot(
            [number(row, "qpt_ang") for row in model_rows],
            [
                1000.0 * number(row, "energy_error_ev")
                for row in model_rows
            ],
            marker="o",
            label=model,
        )
    axis.axhline(0.0, linewidth=0.8)
    axis.axvline(0.0, linewidth=0.8, linestyle="--")
    axis.set_xlabel(r"$q_{\mathrm{PT}}$ (Å)")
    axis.set_ylabel("Raw energy error (meV)")
    axis.set_title("Energy error on frozen NEB9 geometries")
    axis.legend()
    axis.grid(True, alpha=0.25)
    save_figure(
        figure,
        "figure_02_neb9_energy_error",
        "Raw energy error for every frozen NEB9 image.",
        figure_manifest,
    )

    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    for model in ("basin", "targeted"):
        model_rows = [
            row
            for row in rows["per_configuration"]
            if row["model"] == model and row["subset"] == "neb9"
        ]
        model_rows.sort(key=lambda row: int(row["subset_index"]))
        axis.plot(
            [number(row, "qpt_ang") for row in model_rows],
            [
                number(row, "force_component_rmse_ev_ang")
                for row in model_rows
            ],
            marker="o",
            label=model,
        )
    axis.axvline(0.0, linewidth=0.8, linestyle="--")
    axis.set_xlabel(r"$q_{\mathrm{PT}}$ (Å)")
    axis.set_ylabel("Force-component RMSE (eV/Å)")
    axis.set_title("Force error on frozen NEB9 geometries")
    axis.legend()
    axis.grid(True, alpha=0.25)
    save_figure(
        figure,
        "figure_03_neb9_force_error",
        "Per-configuration force-component RMSE along frozen NEB9.",
        figure_manifest,
    )

    subset_names = ["basin12", "neb9"]
    x = np.arange(len(subset_names), dtype=float)
    width = 0.36

    figure, axis = plt.subplots(figsize=(6.8, 4.8))
    axis.bar(
        x - width / 2,
        [
            1000.0 * number(
                subset[("basin", subset_name)],
                "energy_rmse_ev",
            )
            for subset_name in subset_names
        ],
        width,
        label="basin",
    )
    axis.bar(
        x + width / 2,
        [
            1000.0 * number(
                subset[("targeted", subset_name)],
                "energy_rmse_ev",
            )
            for subset_name in subset_names
        ],
        width,
        label="targeted",
    )
    axis.set_xticks(x, subset_names)
    axis.set_ylabel("Energy RMSE (meV/configuration)")
    axis.set_title("Accuracy trade-off at equal DFT budget")
    axis.legend()
    axis.grid(True, axis="y", alpha=0.25)
    save_figure(
        figure,
        "figure_04_subset_energy_rmse",
        "Basin12 and NEB9 energy RMSE for both equal-budget models.",
        figure_manifest,
    )

    figure, axis = plt.subplots(figsize=(6.8, 4.8))
    axis.bar(
        x - width / 2,
        [
            number(
                subset[("basin", subset_name)],
                "force_component_rmse_ev_ang",
            )
            for subset_name in subset_names
        ],
        width,
        label="basin",
    )
    axis.bar(
        x + width / 2,
        [
            number(
                subset[("targeted", subset_name)],
                "force_component_rmse_ev_ang",
            )
            for subset_name in subset_names
        ],
        width,
        label="targeted",
    )
    axis.set_xticks(x, subset_names)
    axis.set_ylabel("Force-component RMSE (eV/Å)")
    axis.set_title("Force accuracy trade-off at equal DFT budget")
    axis.legend()
    axis.grid(True, axis="y", alpha=0.25)
    save_figure(
        figure,
        "figure_05_subset_force_rmse",
        "Basin12 and NEB9 force-component RMSE for both models.",
        figure_manifest,
    )

    figure, axis = plt.subplots(figsize=(7.0, 5.0))
    for model in ("basin", "targeted"):
        model_rows = [
            row
            for row in rows["per_configuration"]
            if row["model"] == model
        ]
        axis.scatter(
            [number(row, "mv_grade") for row in model_rows],
            [
                1000.0 * number(row, "energy_abs_error_ev")
                for row in model_rows
            ],
            label=model,
            alpha=0.8,
        )
    axis.set_xscale("log")
    axis.set_xlabel("MaxVol grade")
    axis.set_ylabel("Absolute energy error (meV)")
    axis.set_title("Extrapolation grade versus observed energy error")
    axis.legend()
    axis.grid(True, which="both", alpha=0.25)
    save_figure(
        figure,
        "figure_06_grade_vs_energy_error",
        "MaxVol grade compared with observed audit energy error.",
        figure_manifest,
    )

    figure, axis = plt.subplots(figsize=(6.8, 4.8))
    values = [
        1000.0 * number(
            barriers[("basin",)],
            "dft_forward_barrier_ev",
        ),
        1000.0 * number(
            barriers[("basin",)],
            "model_forward_barrier_ev",
        ),
        1000.0 * number(
            barriers[("targeted",)],
            "model_forward_barrier_ev",
        ),
    ]
    axis.bar(np.arange(3), values)
    axis.set_xticks(
        np.arange(3),
        ["DFT", "basin MTP", "targeted MTP"],
    )
    axis.set_ylabel("Forward barrier (meV)")
    axis.set_title("Forward proton-transfer barrier")
    axis.grid(True, axis="y", alpha=0.25)
    save_figure(
        figure,
        "figure_07_forward_barrier",
        "DFT and MTP forward barrier heights.",
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

    result_rows = [
        {
            "quantity": "neb9_energy_rmse_mev",
            "basin": basin_neb_e * 1000.0,
            "targeted": targeted_neb_e * 1000.0,
            "targeted_minus_basin":
                (targeted_neb_e - basin_neb_e) * 1000.0,
            "basin_over_targeted":
                ratios["neb9_energy_rmse_improvement"],
        },
        {
            "quantity": "neb9_force_component_rmse_ev_ang",
            "basin": basin_neb_f,
            "targeted": targeted_neb_f,
            "targeted_minus_basin": targeted_neb_f - basin_neb_f,
            "basin_over_targeted":
                ratios["neb9_force_rmse_improvement"],
        },
        {
            "quantity": "neb_profile_rmse_mev",
            "basin": basin_profile * 1000.0,
            "targeted": targeted_profile * 1000.0,
            "targeted_minus_basin":
                (targeted_profile - basin_profile) * 1000.0,
            "basin_over_targeted":
                ratios["neb_profile_rmse_improvement"],
        },
        {
            "quantity": "forward_barrier_abs_error_mev",
            "basin": basin_barrier_error,
            "targeted": targeted_barrier_error,
            "targeted_minus_basin":
                targeted_barrier_error - basin_barrier_error,
            "basin_over_targeted":
                ratios["forward_barrier_error_improvement"],
        },
        {
            "quantity": "basin12_energy_rmse_mev",
            "basin": basin_basin_e * 1000.0,
            "targeted": targeted_basin_e * 1000.0,
            "targeted_minus_basin":
                (targeted_basin_e - basin_basin_e) * 1000.0,
            "basin_over_targeted": basin_basin_e / targeted_basin_e,
        },
        {
            "quantity": "basin12_force_component_rmse_ev_ang",
            "basin": basin_basin_f,
            "targeted": targeted_basin_f,
            "targeted_minus_basin":
                targeted_basin_f - basin_basin_f,
            "basin_over_targeted": basin_basin_f / targeted_basin_f,
        },
    ]
    result_table = TABLES_DIR / "primary_equal_budget_result_v030.tsv"
    write_tsv(result_table, result_rows)

    summary = {
        "created_utc": utc_now(),
        "status": "PASS_FINAL_PRIMARY_ANALYSIS_AND_FIGURES",
        "implementation_id": IMPLEMENTATION_ID,
        "run_root": str(RUN_ROOT),
        "source_v028": str(data["v028"]),
        "source_v029": str(data["v029"]),
        "model_hashes": {
            "basin": sha256(data["basin_model"]),
            "targeted": sha256(data["targeted_model"]),
        },
        "primary_result": {
            "neb9_energy_rmse_mev": {
                "basin": basin_neb_e * 1000.0,
                "targeted": targeted_neb_e * 1000.0,
                "improvement_factor":
                    ratios["neb9_energy_rmse_improvement"],
            },
            "neb9_force_rmse_ev_ang": {
                "basin": basin_neb_f,
                "targeted": targeted_neb_f,
                "improvement_factor":
                    ratios["neb9_force_rmse_improvement"],
            },
            "neb_profile_rmse_mev": {
                "basin": basin_profile * 1000.0,
                "targeted": targeted_profile * 1000.0,
                "improvement_factor":
                    ratios["neb_profile_rmse_improvement"],
            },
            "forward_barrier_abs_error_mev": {
                "basin": basin_barrier_error,
                "targeted": targeted_barrier_error,
                "improvement_factor":
                    ratios["forward_barrier_error_improvement"],
            },
            "basin12_energy_rmse_mev": {
                "basin": basin_basin_e * 1000.0,
                "targeted": targeted_basin_e * 1000.0,
            },
            "basin12_force_rmse_ev_ang": {
                "basin": basin_basin_f,
                "targeted": targeted_basin_f,
            },
        },
        "interpretation": {
            "supported_claim":
                "At equal DFT budget and fixed MTP architecture, targeted "
                "transition-region labelling greatly improves the proton-"
                "transfer energy profile and barrier while retaining "
                "sub-meV basin energy accuracy.",
            "not_supported":
                "The targeted model is not established as a universal "
                "production potential; audit MaxVol grades remain very high.",
            "post_audit_tuning": False,
        },
        "figures": [
            {
                key: str(value) if isinstance(value, Path) else value
                for key, value in item.items()
            }
            for item in figure_manifest
        ],
        "result_table": str(result_table),
        "report": str(REPORT_MD),
        "execution": {
            "matplotlib_only": True,
            "mlp": False,
            "pw_x": False,
            "neb_x": False,
            "lammps": False,
        },
    }
    SUMMARY_JSON.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    REPORT_MD.write_text(
        f"""# Final primary equal-budget result v030

Created UTC: {utc_now()}

Status: `PASS_FINAL_PRIMARY_ANALYSIS_AND_FIGURES`

## Main result

At the same new-label budget (`K=24`), the same common36 prefix,
the same level-12 MTP architecture and the same training settings,
targeted transition-region labelling produced:

- NEB9 energy RMSE: {basin_neb_e * 1000.0:.3f} -> {targeted_neb_e * 1000.0:.3f} meV;
- NEB9 force-component RMSE: {basin_neb_f:.6f} -> {targeted_neb_f:.6f} eV/Angstrom;
- NEB relative-profile RMSE: {basin_profile * 1000.0:.3f} -> {targeted_profile * 1000.0:.3f} meV;
- forward-barrier absolute error: {basin_barrier_error:.3f} -> {targeted_barrier_error:.3f} meV.

The corresponding improvement factors are
{ratios['neb9_energy_rmse_improvement']:.2f}x,
{ratios['neb9_force_rmse_improvement']:.2f}x,
{ratios['neb_profile_rmse_improvement']:.2f}x and
{ratios['forward_barrier_error_improvement']:.2f}x.

## Local trade-off

The basin-only model remains slightly more accurate on basin12:

- energy RMSE: {basin_basin_e * 1000.0:.3f} versus {targeted_basin_e * 1000.0:.3f} meV;
- force-component RMSE: {basin_basin_f:.6f} versus {targeted_basin_f:.6f} eV/Angstrom.

Thus the result is a controlled redistribution of accuracy rather
than a claim that one model dominates in every region.

## Scope

The independent frozen audit supports the comparative sampling claim.
It does not establish the targeted MTP as a globally reliable production
potential. MaxVol grades remain high, and no post-audit retraining or
hyperparameter change is permitted within this strict comparison.

No MLP, Quantum ESPRESSO, NEB or LAMMPS calculation was executed
in v030.
""",
        encoding="utf-8",
    )

    STATUS_FILE.write_text(
        "PASS_FINAL_PRIMARY_ANALYSIS_AND_FIGURES\n",
        encoding="utf-8",
    )
    write_checksums(RUN_ROOT, CHECKSUMS_TSV)
    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    CURRENT_POINTER.write_text(str(RUN_ROOT) + "\n", encoding="utf-8")

    print()
    print("PASS_FINAL_PRIMARY_ANALYSIS_AND_FIGURES: STEP 32 v030 COMPLETED")
    print()
    print(f"Run root:                  {RUN_ROOT}")
    print(f"Figures:                   {len(figure_manifest)} PNG + PDF pairs")
    print(
        "NEB9 E-RMSE improvement:  "
        f"{ratios['neb9_energy_rmse_improvement']:.3f}x"
    )
    print(
        "Profile-RMSE improvement: "
        f"{ratios['neb_profile_rmse_improvement']:.3f}x"
    )
    print(
        "Barrier-error improvement:"
        f" {ratios['forward_barrier_error_improvement']:.3f}x"
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

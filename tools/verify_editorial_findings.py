#!/usr/bin/env python3
"""Recompute editorial diagnostics from saved public evidence, without physics calls.

Standard library only. CFG arithmetic below is independent of the historical
summary tables. Existing strict verifiers additionally authenticate the original
QE blocks, geometry guards and input manifests; their separate scope is recorded.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import re
import statistics
from collections import defaultdict
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "76e0e22967f408480b5a713d8f94f6c9e9981105"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_table(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def cfg(path):
    """Independent ordered-atom reader of the deposited nine-atom CFG format."""
    blocks = re.findall(r"(?ms)^\s*BEGIN_CFG\s*\n(.*?)^\s*END_CFG\s*$", path.read_text())
    require(blocks, f"No CFG entries: {path}")
    result = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        n = int(lines[lines.index("Size") + 1])
        require(n == 9, "Nine atoms required")
        starts = [i for i, line in enumerate(lines) if line.startswith("AtomData:")]
        require(len(starts) == 1, "One ordered atom block required")
        start = starts[0]
        keys = lines[start].split(":", 1)[1].split()
        atoms = [dict(zip(keys, row.split())) for row in lines[start + 1:start + n + 1]]
        require([int(atom["id"]) for atom in atoms] == list(range(1, 10)), "Atom order changed")
        features = {}
        for line in lines:
            if line.startswith("Feature "):
                _, key, value = line.split(None, 2)
                require(key not in features, "Duplicate feature")
                features[key] = value
        entry = {"xyz": [[float(atom[k]) for k in ("cartes_x", "cartes_y", "cartes_z")] for atom in atoms],
                 "forces": [[float(atom[k]) for k in ("fx", "fy", "fz")] for atom in atoms],
                 "types": [int(atom["type"]) for atom in atoms],
                 "energy": float(lines[lines.index("Energy") + 1]), "features": features}
        require(entry["types"] == [2, 1, 0, 1, 0, 1, 0, 2, 1], "Species or order changed")
        require(all(math.isfinite(x) for row in entry["xyz"] + entry["forces"] for x in row), "Nonfinite data")
        result.append(entry)
    return result


def descriptors(entry):
    xyz = entry["xyz"]
    return {"qPT_A": math.dist(xyz[0], xyz[1]) - math.dist(xyz[7], xyz[1]),
            "OO_A": math.dist(xyz[0], xyz[7])}


def force_rmse(references, predictions):
    delta = [b - a for ref, pred in zip(references, predictions)
             for ra, rb in zip(ref["forces"], pred["forces"]) for a, b in zip(ra, rb)]
    require(delta and len(delta) == len(references) * 27, "Force denominator mismatch")
    return math.sqrt(math.fsum(x * x for x in delta) / len(delta))


def barrier(configurations):
    energies = [entry["energy"] for entry in configurations]
    return 1000 * (max(energies) - min(energies[0], energies[-1]))


def pair_distances(entry):
    return [math.dist(entry["xyz"][i], entry["xyz"][j]) for i in range(9) for j in range(i)]


def original_and_geometry():
    root = ROOT / "data/frozen_models_v028"
    reference = cfg(root / "frozen_audit21_labels_v029.cfg")
    indices = [i for i, entry in enumerate(reference) if entry["features"].get("audit_subset") == "neb9"]
    require(len(indices) == 9, "Nine PBE supports required")
    neb = [reference[i] for i in indices]
    central_indices = [i for i in indices if abs(descriptors(reference[i])["qPT_A"]) <= .15]
    require(len(central_indices) == 3, "Three central configurations required")
    train = {branch: cfg(root / f"train_{branch}60_v028.cfg") for branch in ("basin", "targeted")}
    metrics = {}
    for branch in train:
        predictions = cfg(root / f"audit21_predictions_{branch}_v029.cfg")
        predicted_neb = [predictions[i] for i in indices]
        metrics[branch] = {
            "model_barrier_meV": barrier(predicted_neb),
            "barrier_error_meV": abs(barrier(predicted_neb) - barrier(neb)),
            "central_force_RMSE_eV_A": force_rmse([reference[i] for i in central_indices], [predictions[i] for i in central_indices]),
        }
    require(abs(metrics["basin"]["barrier_error_meV"] - 35.245734070031176) < 1e-10, "Original basin regression")
    require(abs(metrics["targeted"]["central_force_RMSE_eV_A"] - .07868490481909637) < 1e-12, "Original targeted regression")
    ranges = {branch: [min(descriptors(c)["OO_A"] for c in values), max(descriptors(c)["OO_A"] for c in values)] for branch, values in train.items()}
    central_training = [descriptors(c)["OO_A"] for c in train["targeted"] if abs(descriptors(c)["qPT_A"]) <= .15]
    overlaps = []
    for branch, configurations in train.items():
        for i, entry in enumerate(neb, 1):
            for j, training in enumerate(configurations, 1):
                distance = max(abs(x-y) for x, y in zip(pair_distances(entry), pair_distances(training)))
                if distance <= 2.1e-6:
                    overlaps.append({"branch": branch, "neb_image": i, "training_index": j, "pair_distance_max_A": distance})
    require([(o["branch"], o["neb_image"]) for o in overlaps] == [("basin", 1), ("basin", 9), ("targeted", 1), ("targeted", 9)], "Known endpoint overlaps changed")
    generator_path = ROOT / "scripts/core_pipeline/step28_fresh_tube_active_selection_v026.py"
    generator_text = generator_path.read_text()
    function = next(node for node in ast.parse(generator_text).body if isinstance(node, ast.FunctionDef) and node.name == "generate_tube")
    source = ast.get_source_segment(generator_text, function)
    require('base = (1.0 - item["s"]) * left + item["s"] * right_aligned' in source, "Generation expression changed")
    below = {branch: [i for i, c in enumerate(neb, 1) if descriptors(c)["OO_A"] < ranges[branch][0]] for branch in train}
    require(all(values == list(range(2, 9)) for values in below.values()), "Seven interior image gap changed")
    geometry = {"training_OO_range_A": ranges,
                "pbe_path": [{"image": i, **descriptors(c)} for i, c in enumerate(neb, 1)],
                "internal_images_below_training_range": below,
                "central_PBE_OO_A": descriptors(neb[4])["OO_A"],
                "OO_gap_below_training_minimum_A": ranges["targeted"][0] - descriptors(neb[4])["OO_A"],
                "central_targeted_training_count": len(central_training),
                "central_targeted_training_OO_range_A": [min(central_training), max(central_training)],
                "generation": {"path": str(generator_path.relative_to(ROOT)), "line": function.lineno,
                               "base": "(1-s)*left + s*right_aligned", "scope": "Aligned-endpoint linear interpolation plus prescribed perturbations, not a tube centered on the relaxed NEB path."},
                "geometry_scope": "O-O range is a two-coordinate projection finding, not a full feature-space or universal extrapolation classification."}
    seed_rows = read_table(ROOT / "data/robustness/v028_seed_robustness_v001/ALL_METRICS.tsv")
    seed_pairs = []
    for i in range(5):
        pair = {r["branch"]: r for r in seed_rows if int(r["seed_index"]) == i}
        bw = float(pair["targeted"]["lower_endpoint_barrier_abs_error_meV"]) < float(pair["basin"]["lower_endpoint_barrier_abs_error_meV"])
        fw = float(pair["targeted"]["transition_region_force_component_RMSE_eV_A"]) < float(pair["basin"]["transition_region_force_component_RMSE_eV_A"])
        seed_pairs.append({"seed_index": i, "barrier_win": bw, "force_win": fw, "joint_win": bw and fw})
    return {"PBE_barrier_meV": barrier(neb), "metrics": metrics,
            "central_audit_indices_1based": [i+1 for i in central_indices], "endpoint_overlaps": overlaps,
            "PBE_endpoint_asymmetry_meV": abs(neb[0]["energy"] - neb[-1]["energy"]) * 1000,
            "five_seed_metric_table": {"scope": "Counts from published metric table, not independent replay of the ten seed-model prediction arrays.",
                                       "pairs": seed_pairs, "joint_wins": sum(r["joint_win"] for r in seed_pairs)}}, geometry


def offpath():
    root = ROOT / "data/studies/pbe14_mtp20_v001"
    reference = cfg(root / "references/PBE14_EXACT.cfg")
    roles = {r["id"]: r for r in read_table(root / "GEOMETRY_ROLES.tsv")}
    model_rows = read_table(root / "MODELS_AND_PREDICTIONS_SHA256.tsv")
    blocks, case_rows = defaultdict(list), []
    for model in model_rows:
        predicted = cfg(root / model["prediction_path"])
        require(len(predicted) == len(reference) == 14, "PBE14 size")
        for ref, pred in zip(reference, predicted):
            candidate = ref["features"]["candidate_id"]
            require(pred["features"]["candidate_id"] == candidate, "Candidate order changed")
            role = roles[candidate]
            value = force_rmse([ref], [pred])
            key = (int(model["seed_index"]), model["branch"], int(model["budget"]), role["region"], role["mode"])
            blocks[key].append(value)
            case_rows.append({"seed_index": key[0], "branch": key[1], "budget": key[2], "region": key[3], "mode": key[4], "id": candidate, "force_RMSE_eV_A": value})
    block_means = {key: statistics.mean(values) for key, values in blocks.items()}
    require(len(case_rows) == 280 and len(block_means) == 160, "Expected 280 cases and 160 blocks")
    modes = ["OO_breathing", "C_skeletal_bend", "H_lateral", "H_out_of_plane"]
    regions = ["BASIN_LEFT", "TRANSITION_CENTER"]
    region_means = {(i,b,c,r): statistics.mean(block_means[i,b,c,r,m] for m in modes)
                    for i in range(5) for b in ("basin", "targeted") for c in (2000,8000) for r in regions}
    cell_means = {(r,c,b): statistics.mean(region_means[i,b,c,r] for i in range(5)) for r in regions for c in (2000,8000) for b in ("basin", "targeted")}
    contrasts = [region_means[i,"targeted",8000,"TRANSITION_CENTER"] - region_means[i,"basin",8000,"TRANSITION_CENTER"] for i in range(5)]
    primary = statistics.mean(contrasts)
    require(abs(primary - (-.1461353992591766)) < 1e-13, "PBE14 primary changed")
    require(sum(x < 0 for x in contrasts) == 4, "Four primary wins changed")
    modes_summary, leave_one_out = [], []
    for mode in modes:
        differences = [block_means[i,"targeted",8000,"TRANSITION_CENTER",mode] - block_means[i,"basin",8000,"TRANSITION_CENTER",mode] for i in range(5)]
        contribution = statistics.mean(differences) / 4
        modes_summary.append({"mode": mode, "contribution_to_primary_mean_eV_A": contribution,
                              "fraction_of_signed_primary_mean": contribution / primary,
                              "paired_differences_eV_A": differences, "targeted_win_count": sum(x < 0 for x in differences)})
        kept = [m for m in modes if m != mode]
        deleted = [statistics.mean(block_means[i,"targeted",8000,"TRANSITION_CENTER",m] - block_means[i,"basin",8000,"TRANSITION_CENTER",m] for m in kept) for i in range(5)]
        leave_one_out.append({"removed_mode": mode, "mean_difference_eV_A": statistics.mean(deleted),
                              "paired_differences_eV_A": deleted, "targeted_win_count": sum(x < 0 for x in deleted)})
    basin_change = cell_means["TRANSITION_CENTER",8000,"basin"] - cell_means["TRANSITION_CENTER",2000,"basin"]
    targeted_change = cell_means["TRANSITION_CENTER",8000,"targeted"] - cell_means["TRANSITION_CENTER",2000,"targeted"]
    equal_case_contrasts = []
    for i in range(5):
        by_branch = {b: statistics.mean(row["force_RMSE_eV_A"] for row in case_rows if (row["seed_index"],row["branch"],row["budget"],row["region"]) == (i,b,8000,"TRANSITION_CENTER")) for b in ("basin","targeted")}
        equal_case_contrasts.append(by_branch["targeted"] - by_branch["basin"])
    return {"primary": {"mean_eV_A": primary, "median_eV_A": statistics.median(contrasts), "paired_differences_eV_A": contrasts, "targeted_wins": sum(x < 0 for x in contrasts)},
            "cell_means": [{"region": r, "budget": c, "branch": b, "force_RMSE_eV_A": v} for (r,c,b), v in cell_means.items()],
            "directions": modes_summary, "leave_one_block_out": leave_one_out,
            "equal_geometry_weight_sensitivity": {"mean_difference_eV_A": statistics.mean(equal_case_contrasts), "paired_differences_eV_A": equal_case_contrasts},
            "budget_difference_decomposition": {"basin_error_change_eV_A": basin_change, "targeted_error_change_eV_A": targeted_change,
                                                "gap_growth_eV_A": basin_change - targeted_change, "basin_fraction_of_gap_growth": basin_change / (basin_change - targeted_change)},
            "scope": "Primary endpoint uses equal physical-block weights. Leave-one-block-out and equal-geometry weighting are exploratory sensitivity analyses, not replacement endpoints. Arithmetic gap decomposition is not a causal optimizer diagnosis.",
            "cardinality": {"references": 14, "models": len(model_rows), "cases": len(case_rows), "blocks": len(block_means)}}


def optimization_aggregates():
    payload = json.loads((ROOT / "data/optimization_story/v001/OPTIMIZATION_STORY.json").read_text())
    states = {r["id"]: r for r in payload["theory"]["main4500"]["states"]}
    rows = {r["state"]: r for r in payload["theory"]["linear_system"]["row_loss_table"]}
    with localcontext() as context:
        context.prec = 100
        for row in rows.values():
            require(abs(Decimal(row["data_loss"]) + Decimal(row["ridge_penalty"]) - Decimal(row["Q_fixed_D"])) < Decimal("1e-95"), "Aggregate Q identity failed")
        diffs = {name: str(Decimal(rows["S2"][field]) - Decimal(rows["S1c"][field])) for name, field in [("data_loss", "data_loss"), ("ridge_penalty", "ridge_penalty"), ("Q", "Q_fixed_D")]}
        q_reduction = str(100*(1-Decimal(rows["S2"]["Q_fixed_D"])/Decimal(rows["S1c"]["Q_fixed_D"])))
    cov = payload["theory"]["COV"]
    review_source = (ROOT / "site/presentation_review.py").read_text()
    availability_declared = "main4500" in review_source and "unavailable" in review_source and "recovery" in review_source
    require(availability_declared, "Review availability declaration changed; inspect before updating this diagnostic")
    require(states["S3"]["native_J"] is None, "Unmeasured S3 gained a value")
    require(not cov["candidate_coefficients_exported"] and cov["candidate_native_EF_or_gradient"] == "NOT_EVALUATED", "COV scope changed")
    return {"native_J_S2_over_S0": states["S2"]["native_J"]/states["S0"]["native_J"],
            "native_J_S2q_minus_S2": states["S2q"]["native_J"]-states["S2"]["native_J"],
            "S1c_to_S2_row_deltas": diffs, "Q_reduction_percent": q_reduction,
            "COV": {k: cov[k] for k in ["percent_of_total_data_loss_removed", "coefficient_increment_l2", "regularized_stack_condition_number", "candidate_coefficients_exported", "candidate_native_EF_or_gradient", "off_training_accuracy", "theorem", "covariance_scope"]},
            "availability": {"declared_complete_recovery_bundle_unavailable": availability_declared, "source": "site/presentation_review.py",
                             "restricted_source_distribution": payload["scope"]["public_reproduction"],
                             "scope": "Repository declaration inspected; no access to or search of the author's private storage. Public aggregates permit arithmetic checks, not a fresh native replay or independent matrix/proof reconstruction."},
            "evidence_class": "PUBLISHED_AGGREGATE_ARITHMETIC"}


def verify():
    original, geometry = original_and_geometry()
    pbe = offpath()
    # Additional strict guards authenticate raw QE force conversions, source
    # hashes, serialization tolerances and all twenty logs. They run no models.
    from verify_pbe14_offpath import verify as verify_raw_pbe
    from verify_optimizer_budget import verify as verify_raw_budget
    raw = verify_raw_pbe()
    budget = verify_raw_budget()
    require(abs(raw["primary"]["mean"]-pbe["primary"]["mean_eV_A"]) < 1e-14, "Independent aggregation mismatch")
    paths = ["data/frozen_models_v028/frozen_audit21_labels_v029.cfg", "data/frozen_models_v028/audit21_predictions_basin_v029.cfg",
             "data/frozen_models_v028/audit21_predictions_targeted_v029.cfg", "data/frozen_models_v028/train_basin60_v028.cfg",
             "data/frozen_models_v028/train_targeted60_v028.cfg", "data/studies/pbe14_mtp20_v001/INPUT_MANIFEST.json",
             "data/studies/optimization_budget_v001/INPUT_MANIFEST.json", "data/optimization_story/v001/OPTIMIZATION_STORY.json",
             "scripts/core_pipeline/step28_fresh_tube_active_selection_v026.py"]
    return {"schema": "proton-editorial-findings-v1", "baseline_commit": BASELINE, "new_scientific_calls": 0,
            "status": "PASS_SAVED_EVIDENCE_AND_AGGREGATE_ARITHMETIC", "original": original, "geometry": geometry, "offpath": pbe,
            "optimization": optimization_aggregates(), "strict_verification": {
                "PBE14": raw["status"], "optimizer_budget": budget["status"],
                "model_count": budget["model_count"], "printed_main_rows": budget["total_printed_main_rows"],
                "visible_long_run_increases": budget["visible_long_run_increases"],
                "all_visible_increases_at_50_step_boundaries": budget["all_visible_increases_on_50_step_boundaries"]},
            "reference_precision": {"PBE_endpoint_asymmetry_meV": original["PBE_endpoint_asymmetry_meV"],
                "scope": "Endpoint asymmetry is a diagnostic, not an uncertainty bound. No new cutoff/cell/path convergence sweep was performed.",
                "settings_source": "docs/SOFTWARE_PROVENANCE.md", "cell_A": 16, "ecutwfc_Ry": 80, "ecutrho_Ry": 960,
                "k_points": "Gamma", "functional": "PBE", "pseudopotential_family": "PSlibrary scalar-relativistic PBE PAW",
                "NEB_source_guard": "CI_scheme=auto; fixed endpoints; 9 images; 0<path_thr<=0.05 eV/A. This is a source guard, not a newly recovered exact final residual or convergence sweep."},
            "source_sha256": {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT/"docs/editorial-findings.json")
    parser.add_argument("--check", action="store_true", help="Compare regenerated content with the stored report without writing")
    args = parser.parse_args()
    result = verify()
    serialized = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    if args.check:
        require(args.out.read_text() == serialized, "Saved editorial report differs from current evidence")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized)
    print(json.dumps({"status": result["status"], "new_scientific_calls": 0,
                      "interior_images_below_Train60_OO": len(result["geometry"]["internal_images_below_training_range"]["targeted"]),
                      "PBE14_primary_mean_eV_A": result["offpath"]["primary"]["mean_eV_A"],
                      "long_log_increases": result["strict_verification"]["visible_long_run_increases"]}, indent=2))


if __name__ == "__main__":
    main()

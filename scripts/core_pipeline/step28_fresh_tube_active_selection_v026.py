#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

IMPLEMENTATION_ID = "STEP28_V026_CORRECTED_MATERIALIZATION_V003"

ROOT = Path.home() / "malonaldehyde_mtp_al"
VERS = ROOT / "09_strict_comparison" / "versions"

POINTERS = {
    "v016": VERS / "v016_common_seed_dft_labels" / "CURRENT_COMMON_DFT_LABELING.txt",
    "v018": VERS / "v018_common36_l12_protocol_recovery" / "CURRENT_COMMON36_L12_MODEL.txt",
    "v020": VERS / "v020_pre_audit_protocol_lock" / "CURRENT_PRE_AUDIT_PROTOCOL_LOCK.txt",
    "v023": VERS / "v023_basin_audit_force_block_reparse" / "CURRENT_BASIN_AUDIT_FORCE_BLOCK_REPARSE.txt",
    "v024": VERS / "v024_independent_neb_dft" / "CURRENT_INDEPENDENT_NEB_DFT.txt",
    "v025": VERS / "v025_independent_neb_single_points" / "CURRENT_INDEPENDENT_NEB_SINGLE_POINTS.txt",
}

STATUSES = {
    "v016": ("STATUS_v016.txt", "PASS_ALL_DFT_LABELLED_COMMON36"),
    "v018": ("STATUS_v018.txt", "PASS_COMMON36_L12_READY_FOR_FRESH_TUBE"),
    "v020": ("STATUS_v020.txt", "PASS_PRE_AUDIT_PROTOCOL_LOCK_NO_CALCULATIONS"),
    "v023": ("STATUS_v023.txt", "PASS_BASIN_AUDIT_FORCE_BLOCK_REPARSE12_LABELLED"),
    "v024": ("STATUS_v024.txt", "PASS_INDEPENDENT_NEB9_DFT_CONVERGED"),
    "v025": ("STATUS_v025.txt", "PASS_INDEPENDENT_NEB9_SINGLE_POINTS_LABELLED"),
}

VERSION_ROOT = VERS / "v026_fresh_tube_active_selection"
CURRENT_POINTER = VERSION_ROOT / "CURRENT_FRESH_TUBE_ACTIVE_SELECTION.txt"
MLP = ROOT / "01_environment" / "v001" / "software" / "bin" / "mlp"

PROTOCOL_SHA = "0309ca4ca419458a847f1606759c792f0dfc4019108343e3d5a9721f5704d3b8"
COMMON_SHA = "49c8331a88546d964fb9c0fe97bac65729fed228351e7ebee3524d59d7b93cce"
MODEL_SHA = "cdeaa59d485f5e77c01750deb704fd454b67055b846a7b4264146157bee6a13a"
ALS_SHA = "363f4fcd6cc2a78436ba8dbf9c0ba4c0c65fc434ac02edff0c2f6d69713b7cb9"

NAT = 9
SYMBOLS = ["O", "H", "C", "H", "C", "H", "C", "O", "H"]
TYPE = {"C": 0, "H": 1, "O": 2}
MASS = np.array([15.999, 1.008, 12.011, 1.008, 12.011, 1.008, 12.011, 15.999, 1.008])
O1, HSTAR, O2 = 0, 1, 7
ALIGN = np.array([0, 2, 3, 4, 5, 6, 7, 8], dtype=int)
GAMMA = 2.0
MIN_PAIR = 0.65
ROO_MIN = 2.20
ROO_MAX = 2.80
MAX_SPAN = 5.50
BASIN_QPT = 0.30
FINGERPRINT_DUPLICATE_TOL = 5.0e-5
# Locked in v020 as COORDINATE_DUPLICATE_TOL_ANG.
# This tolerance is also the appropriate bound for a text CFG
# serialization round-trip through mlp calc-grade/select-add.
COORDINATE_MATCH_TOL = 1.0e-6
TUBE_N = 24
RESERVOIR_N = 96
RESERVOIR_PER_SIDE = 48
MLP_TIMEOUT = 3600

ACTIVE_STATUS: Path | None = None


@dataclass
class Block:
    raw: str
    features: dict[str, str]
    positions: np.ndarray
    types: list[int]
    cell: np.ndarray | None
    order: int


@dataclass
class Candidate:
    order: int
    candidate_id: str
    s: float
    perturbation: str
    projection: str
    target_rms: float
    seed: int
    fallback: float
    actual_rms: float
    positions: np.ndarray
    qpt: float
    roo: float
    min_pair: float
    max_span: float
    fingerprint: np.ndarray
    normal: np.ndarray


@dataclass
class BasinCandidate:
    row_index: int
    reservoir_order: int
    candidate_id: str
    side: str
    recipe: str
    base_rms_ang: float
    directed_amplitude_ang: float
    amplitude_scale: float
    seed: int
    positions: np.ndarray
    qpt: float
    roo: float
    min_pair: float
    max_span: float
    fingerprint: np.ndarray
    base_target_rms_ang: float
    base_actual_rms_ang: float
    final_displacement_rms_ang: float
    valid_unique: bool
    rejection_reasons: list[str]
    nearest_common36_fingerprint_rms_ang: float
    nearest_prior_valid_fingerprint_rms_ang: float | None


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fatal(msg: str) -> None:
    raise RuntimeError(msg)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        fatal(f"{label} missing: {path}")
    return path


def resolve_pointer(path: Path, label: str) -> Path:
    require_file(path, f"{label} pointer")
    target = Path(path.read_text(encoding="utf-8").strip())
    if not target.is_dir():
        fatal(f"{label} attempt missing: {target}")
    return target


def check_status(attempt: Path, filename: str, expected: str, label: str) -> None:
    actual = require_file(attempt / filename, f"{label} status").read_text(encoding="utf-8").strip()
    if actual != expected:
        fatal(f"{label} status mismatch: expected {expected!r}, got {actual!r}")


def check_hash(path: Path, expected: str, label: str) -> None:
    actual = sha(path)
    if actual != expected:
        fatal(f"{label} SHA256 mismatch\nexpected={expected}\nactual={actual}\npath={path}")


def number(text: str) -> float:
    return float(text.replace("D", "E").replace("d", "e"))


def bool_value(text: str) -> bool:
    value = text.strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    fatal(f"invalid boolean: {text!r}")


def read_tsv(path: Path) -> list[dict[str, str]]:
    require_file(path, "TSV")
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def split_cfg(text: str) -> list[str]:
    out, current = [], None
    for line in text.splitlines(keepends=True):
        token = line.strip()
        if token == "BEGIN_CFG":
            if current is not None:
                fatal("nested BEGIN_CFG")
            current = [line]
        elif current is not None:
            current.append(line)
            if token == "END_CFG":
                raw = "".join(current).rstrip() + "\n"
                out.append(raw)
                current = None
    if current is not None:
        fatal("unterminated CFG block")
    return out


def features(raw: str) -> dict[str, str]:
    result = {}
    pattern = re.compile(r"^\s*Feature\s+(\S+)\s+(.*?)\s*$")
    for line in raw.splitlines():
        match = pattern.match(line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def parse_block(raw: str, order: int) -> Block:
    lines = raw.splitlines()
    size = None
    cell = None
    positions = None
    types = None

    for i, line in enumerate(lines):
        token = line.strip()
        if token == "Size":
            size = int(lines[i + 1].strip())
        elif token == "Supercell":
            cell = np.array([[number(x) for x in lines[i + j].split()[:3]] for j in (1, 2, 3)])
        elif token.startswith("AtomData:"):
            if size is None:
                fatal("AtomData before Size")
            columns = token.split(":", 1)[1].split()
            needed = {"id", "type", "cartes_x", "cartes_y", "cartes_z"}
            if not needed.issubset(columns):
                fatal(f"bad AtomData columns: {columns}")
            idx = {name: columns.index(name) for name in columns}
            p, t = [], []
            for j in range(size):
                row = lines[i + 1 + j].split()
                t.append(int(row[idx["type"]]))
                p.append([number(row[idx["cartes_x"]]), number(row[idx["cartes_y"]]), number(row[idx["cartes_z"]])])
            positions = np.array(p)
            types = t

    if size != NAT or positions is None or positions.shape != (NAT, 3) or types is None:
        fatal("malformed or wrong-size CFG block")
    if not np.all(np.isfinite(positions)):
        fatal("non-finite CFG positions")
    return Block(raw, features(raw), positions, types, cell, order)


def read_cfg(path: Path) -> list[Block]:
    raw = split_cfg(require_file(path, "CFG").read_text(encoding="utf-8"))
    return [parse_block(block, i + 1) for i, block in enumerate(raw)]


def write_raw_cfg(path: Path, raw_blocks: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for raw in raw_blocks:
            f.write(raw.rstrip() + "\n\n")


def add_features(raw: str, extra: dict[str, Any]) -> str:
    lines = raw.rstrip().splitlines()
    if not lines or lines[-1].strip() != "END_CFG":
        fatal("cannot annotate malformed CFG")
    additions = [f" Feature   {key} {value}" for key, value in sorted(extra.items())]
    return "\n".join(lines[:-1] + additions + ["END_CFG"]) + "\n"


def parse_qe_geometry(path: Path) -> tuple[list[str], np.ndarray, np.ndarray]:
    lines = require_file(path, "QE endpoint input").read_text(encoding="utf-8").splitlines()
    syms = None
    pos = None
    cell = None
    for i, line in enumerate(lines):
        token = line.strip()
        upper = token.upper()
        if upper.startswith("ATOMIC_POSITIONS"):
            if "angstrom" not in token.lower():
                fatal(f"{path}: ATOMIC_POSITIONS is not angstrom")
            syms, rows = [], []
            for j in range(NAT):
                fields = lines[i + 1 + j].split()
                syms.append(fields[0])
                rows.append([number(fields[1]), number(fields[2]), number(fields[3])])
            pos = np.array(rows)
        elif upper.startswith("CELL_PARAMETERS"):
            if "angstrom" not in token.lower():
                fatal(f"{path}: CELL_PARAMETERS is not angstrom")
            cell = np.array([[number(x) for x in lines[i + j].split()[:3]] for j in (1, 2, 3)])
    if syms != SYMBOLS or pos is None or cell is None:
        fatal(f"{path}: endpoint geometry or atom order invalid")
    return syms, pos, cell


def pair_distances(pos: np.ndarray) -> dict[tuple[int, int], float]:
    if pos.shape != (NAT, 3):
        fatal(f"coordinate shape {pos.shape}, expected {(NAT, 3)}")
    if not np.all(np.isfinite(pos)):
        fatal("non-finite coordinates")
    result: dict[tuple[int, int], float] = {}
    for i in range(NAT):
        for j in range(i + 1, NAT):
            result[(i, j)] = float(np.linalg.norm(pos[i] - pos[j]))
    return result


def metrics(pos: np.ndarray) -> dict[str, Any]:
    distances = pair_distances(pos)
    ordered_pairs = sorted(distances)
    minimum_pair, minimum_distance = min(distances.items(), key=lambda item: item[1])
    qpt = distances[(O1, HSTAR)] - distances[(HSTAR, O2)]
    roo = distances[(O1, O2)]
    return {
        "qpt": float(qpt),
        "roo": float(roo),
        "min_pair": float(minimum_distance),
        "minimum_pair_indices": (minimum_pair[0] + 1, minimum_pair[1] + 1),
        "max_span": float(max(distances.values())),
        "fingerprint": np.asarray([distances[pair] for pair in ordered_pairs], dtype=float),
    }


def geometry_reasons(pos: np.ndarray, side: str | None = None) -> tuple[dict[str, Any], list[str]]:
    met = metrics(pos)
    reasons: list[str] = []
    if met["min_pair"] <= MIN_PAIR:
        reasons.append(f"minimum_pair={met['min_pair']:.12f}<=0.65")
    if not (ROO_MIN < met["roo"] < ROO_MAX):
        reasons.append(f"R_OO={met['roo']:.12f}_outside_(2.20,2.80)")
    if met["max_span"] >= MAX_SPAN:
        reasons.append(f"maximum_span={met['max_span']:.12f}>=5.50")
    if side == "left" and met["qpt"] >= -BASIN_QPT:
        reasons.append(f"left_qPT={met['qpt']:.12f}>=-0.30")
    if side == "right" and met["qpt"] <= BASIN_QPT:
        reasons.append(f"right_qPT={met['qpt']:.12f}<=+0.30")
    return met, reasons


def fingerprint_rms(first: np.ndarray, second: np.ndarray) -> float:
    if first.shape != second.shape:
        fatal(f"fingerprint shape mismatch: {first.shape}, {second.shape}")
    return float(np.sqrt(np.mean((first - second) ** 2)))


def displacement_rms(displacement: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.sum(displacement ** 2, axis=1))))


def mass_center(pos: np.ndarray) -> np.ndarray:
    return np.sum(MASS[:, None] * pos, axis=0) / np.sum(MASS)


def kabsch(mobile: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, float]:
    weights = MASS[ALIGN]
    mobile_fit = mobile[ALIGN]
    reference_fit = reference[ALIGN]
    mobile_center = np.average(mobile_fit, axis=0, weights=weights)
    reference_center = np.average(reference_fit, axis=0, weights=weights)
    x = mobile_fit - mobile_center
    y = reference_fit - reference_center
    covariance = x.T @ (weights[:, None] * y)
    u, _, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0.0:
        vt[-1, :] *= -1.0
        rotation = vt.T @ u.T
    if not np.isclose(np.linalg.det(rotation), 1.0, atol=1.0e-10):
        fatal("improper Kabsch rotation")
    aligned = (mobile - mobile_center) @ rotation.T + reference_center
    difference = aligned[ALIGN] - reference_fit
    rmsd = float(np.sqrt(np.sum(weights * np.sum(difference ** 2, axis=1)) / np.sum(weights)))
    return aligned, rmsd


def molecular_plane_normal(pos: np.ndarray) -> np.ndarray:
    # Exact locked plane: O1 - C2 - O2, Python indices 0, 4, 7.
    vector_a = pos[4] - pos[0]
    vector_b = pos[7] - pos[0]
    normal = np.cross(vector_a, vector_b)
    norm = float(np.linalg.norm(normal))
    if norm < 1.0e-10:
        fatal("could not define O1-C2-O2 molecular plane normal")
    normal = normal / norm
    dominant = int(np.argmax(np.abs(normal)))
    if normal[dominant] < 0.0:
        normal *= -1.0
    return normal


def rigid_residuals(pos: np.ndarray, displacement: np.ndarray) -> tuple[float, float]:
    translation = np.sum(MASS[:, None] * displacement, axis=0) / np.sum(MASS)
    centered = pos - mass_center(pos)
    angular = np.sum(
        MASS[:, None] * np.cross(centered, displacement),
        axis=0,
    )
    return float(np.linalg.norm(translation)), float(np.linalg.norm(angular))


def remove_translation_and_rotation(pos: np.ndarray, displacement: np.ndarray) -> np.ndarray:
    displacement = np.array(displacement, dtype=float, copy=True)
    translation = np.sum(MASS[:, None] * displacement, axis=0) / np.sum(MASS)
    displacement -= translation

    centered = pos - mass_center(pos)
    inertia = np.zeros((3, 3), dtype=float)
    angular = np.zeros(3, dtype=float)
    identity = np.eye(3)

    for mass, position, delta in zip(MASS, centered, displacement):
        inertia += mass * (
            np.dot(position, position) * identity - np.outer(position, position)
        )
        angular += mass * np.cross(position, delta)

    try:
        omega = np.linalg.solve(inertia, angular)
    except np.linalg.LinAlgError as error:
        fatal(f"failed to remove infinitesimal rotation: {error}")

    displacement -= np.cross(omega[None, :], centered)
    translation = np.sum(MASS[:, None] * displacement, axis=0) / np.sum(MASS)
    displacement -= translation
    return displacement


def locked_random_direction(pos: np.ndarray, kind: str, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    displacement = rng.normal(loc=0.0, scale=1.0, size=(NAT, 3))
    normal = molecular_plane_normal(pos)

    if kind in {"isotropic_micro", "isotropic_010", "isotropic_015", "roo_breathing", "donor_oh_mode"}:
        pass
    elif kind in {"in_plane_micro", "in_plane_012"}:
        displacement -= np.outer(displacement @ normal, normal)
    elif kind in {"out_of_plane_micro", "out_of_plane_010"}:
        displacement = np.outer(displacement @ normal, normal)
    else:
        fatal(f"unknown perturbation recipe: {kind}")

    displacement = remove_translation_and_rotation(pos, displacement)
    value = displacement_rms(displacement)
    if not math.isfinite(value) or value < 1.0e-12:
        fatal(f"degenerate random direction for {kind}, seed={seed}")
    displacement /= value

    translation_residual, angular_residual = rigid_residuals(pos, displacement)
    if translation_residual > 1.0e-10 or angular_residual > 1.0e-8:
        fatal(
            f"rigid-motion removal residual too large for {kind}, seed={seed}: "
            f"translation={translation_residual:.3e}, angular={angular_residual:.3e}"
        )
    return displacement, normal


def parse_tube_spec(path: Path) -> list[dict[str, Any]]:
    rows = read_tsv(path)
    required = {
        "candidate_order", "candidate_id", "interpolation_coordinate",
        "perturbation", "projection", "target_rms_ang", "rng", "seed",
        "fallback_factors", "gamma_prefilter",
        "training_eligible_before_selection", "audit_source_used",
    }
    if len(rows) != TUBE_N:
        fatal(f"tube spec has {len(rows)} rows, expected {TUBE_N}")
    if not rows or not required.issubset(rows[0]):
        fatal(f"tube spec columns missing: {sorted(required - set(rows[0] if rows else []))}")

    parsed: list[dict[str, Any]] = []
    for row in rows:
        parsed.append({
            "order": int(row["candidate_order"]),
            "id": row["candidate_id"],
            "s": number(row["interpolation_coordinate"]),
            "kind": row["perturbation"],
            "projection": row["projection"],
            "target": number(row["target_rms_ang"]),
            "rng": row["rng"],
            "seed": int(row["seed"]),
            "fallbacks": [number(x) for x in row["fallback_factors"].split(",")],
            "gamma": row["gamma_prefilter"].replace(" ", ""),
            "eligible": bool_value(row["training_eligible_before_selection"]),
            "audit": bool_value(row["audit_source_used"]),
        })

    parsed.sort(key=lambda item: item["order"])
    if [item["order"] for item in parsed] != list(range(1, TUBE_N + 1)):
        fatal("tube candidate order is not exactly 1..24")
    if len({item["id"] for item in parsed}) != TUBE_N:
        fatal("tube candidate IDs are not unique")

    expected_coordinates = [0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85]
    expected_recipe = {
        "isotropic_micro": ("none", 0.010),
        "in_plane_micro": ("molecular_plane", 0.012),
        "out_of_plane_micro": ("plane_normal", 0.010),
    }
    expected_seed_family = {
        "isotropic_micro": 210000,
        "in_plane_micro": 220000,
        "out_of_plane_micro": 230000,
    }

    for item in parsed:
        if item["rng"] != "numpy_PCG64":
            fatal(f"tube RNG mismatch for {item['id']}: {item['rng']}")
        if item["fallbacks"] != [1.0, 0.75, 0.5, 0.25]:
            fatal(f"tube fallback mismatch for {item['id']}: {item['fallbacks']}")
        if item["gamma"] != ">2.0" or item["eligible"] or item["audit"]:
            fatal(f"tube selection/blindness mismatch for {item['id']}")
        if item["kind"] not in expected_recipe:
            fatal(f"unknown tube recipe in lock: {item['kind']}")
        expected_projection, expected_target = expected_recipe[item["kind"]]
        if item["projection"] != expected_projection or abs(item["target"] - expected_target) > 1.0e-12:
            fatal(f"tube recipe parameters mismatch for {item['id']}")

        coordinate_index = expected_coordinates.index(item["s"]) + 1 if item["s"] in expected_coordinates else None
        perturbation_index = ["isotropic_micro", "in_plane_micro", "out_of_plane_micro"].index(item["kind"]) + 1
        if coordinate_index is None:
            fatal(f"unexpected tube interpolation coordinate: {item['s']}")
        expected_seed = expected_seed_family[item["kind"]] + 100 * coordinate_index + perturbation_index
        if item["seed"] != expected_seed:
            fatal(f"tube seed mismatch for {item['id']}: {item['seed']} != {expected_seed}")

    for coordinate in expected_coordinates:
        if sum(abs(item["s"] - coordinate) < 1.0e-12 for item in parsed) != 3:
            fatal(f"tube coordinate {coordinate} does not have exactly 3 candidates")
    return parsed


def generate_tube(spec: list[dict[str, Any]], left: np.ndarray, right_aligned: np.ndarray) -> list[Candidate]:
    result: list[Candidate] = []
    accepted_fingerprints: list[np.ndarray] = []

    for item in spec:
        base = (1.0 - item["s"]) * left + item["s"] * right_aligned
        direction, normal = locked_random_direction(base, item["kind"], item["seed"])
        accepted: Candidate | None = None
        failure_reasons: list[str] = []

        for factor in item["fallbacks"]:
            displacement = direction * item["target"] * factor
            pos = base + displacement
            met, reasons = geometry_reasons(pos)

            duplicate_distance = math.inf
            if accepted_fingerprints:
                duplicate_distance = min(
                    fingerprint_rms(met["fingerprint"], previous)
                    for previous in accepted_fingerprints
                )
                if duplicate_distance <= FINGERPRINT_DUPLICATE_TOL:
                    reasons.append(
                        f"tube_fingerprint_duplicate_rms={duplicate_distance:.12e}"
                    )

            if reasons:
                failure_reasons.append(f"factor={factor:.2f}: " + "; ".join(reasons))
                continue

            actual_rms = displacement_rms(displacement)
            expected_rms = item["target"] * factor
            if abs(actual_rms - expected_rms) > 1.0e-11:
                fatal(
                    f"{item['id']}: actual RMS {actual_rms:.12e} != expected {expected_rms:.12e}"
                )

            accepted = Candidate(
                order=item["order"],
                candidate_id=item["id"],
                s=item["s"],
                perturbation=item["kind"],
                projection=item["projection"],
                target_rms=item["target"],
                seed=item["seed"],
                fallback=factor,
                actual_rms=actual_rms,
                positions=pos,
                qpt=met["qpt"],
                roo=met["roo"],
                min_pair=met["min_pair"],
                max_span=met["max_span"],
                fingerprint=met["fingerprint"],
                normal=normal,
            )
            break

        if accepted is None:
            fatal(
                f"all locked fallback factors failed for {item['id']}: "
                + " | ".join(failure_reasons)
            )

        result.append(accepted)
        accepted_fingerprints.append(accepted.fingerprint)

    if len(result) != TUBE_N:
        fatal(f"generated {len(result)} tube candidates, expected {TUBE_N}")
    return result


def write_tube(path: Path, candidates: list[Candidate], cell: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write("BEGIN_CFG\n Size\n    9\n Supercell\n")
            for row in cell:
                handle.write(f"    {row[0]:.16g} {row[1]:.16g} {row[2]:.16g}\n")
            handle.write(" AtomData:  id type cartes_x cartes_y cartes_z\n")
            for index, (symbol, position) in enumerate(zip(SYMBOLS, candidate.positions), start=1):
                handle.write(
                    f"    {index:4d} {TYPE[symbol]:2d} "
                    f"{position[0]:.16g} {position[1]:.16g} {position[2]:.16g}\n"
                )
            feature_values = {
                "accepted_fallback_factor": f"{candidate.fallback:.8f}",
                "actual_rms_ang": f"{candidate.actual_rms:.12f}",
                "audit_source_used": "false",
                "candidate_id": candidate.candidate_id,
                "candidate_order": candidate.order,
                "fingerprint_duplicate_tolerance_ang": f"{FINGERPRINT_DUPLICATE_TOL:.12g}",
                "gamma_prefilter": ">2.0",
                "interpolation_coordinate": f"{candidate.s:.8f}",
                "maximum_span_ang": f"{candidate.max_span:.12f}",
                "minimum_pair_ang": f"{candidate.min_pair:.12f}",
                "perturbation": candidate.perturbation,
                "projection": candidate.projection,
                "q_pt_ang": f"{candidate.qpt:.12f}",
                "r_oo_ang": f"{candidate.roo:.12f}",
                "region": "fresh_transition_tube",
                "rigid_translation_removed": "true",
                "rigid_infinitesimal_rotation_removed": "true",
                "rng": "numpy_PCG64",
                "seed": candidate.seed,
                "target_rms_ang": f"{candidate.target_rms:.8f}",
                "training_eligible_before_selection": "false",
                "unlabeled": "true",
                "version": "v026_corrected",
            }
            for key, value in sorted(feature_values.items()):
                handle.write(f" Feature   {key} {value}\n")
            handle.write("END_CFG\n\n")

def candidate_id(block: Block) -> str:
    value = block.features.get("candidate_id", "").strip()
    if not value:
        fatal(f"CFG block {block.order} lacks candidate_id")
    return value


def grade(block: Block) -> float:
    for key in ("MV_grade", "mv_grade", "grade"):
        if key in block.features:
            value = number(block.features[key].split()[0])
            if not math.isfinite(value):
                fatal(f"non-finite grade for {candidate_id(block)}")
            return value
    fatal(f"MV_grade missing for {candidate_id(block)}")


def run_mlp(command: list[str], cwd: Path, stdout: Path, stderr: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=MLP_TIMEOUT, check=False)
    stdout.write_text(result.stdout, encoding="utf-8")
    stderr.write_text(result.stderr, encoding="utf-8")
    return result


def parse_basin_spec(path: Path) -> list[dict[str, Any]]:
    rows = read_tsv(path)
    required = {
        "reservoir_order", "candidate_id", "side", "recipe",
        "base_rms_ang", "directed_amplitude_ang", "amplitude_scale",
        "rng", "seed", "minimum_abs_qpt_ang", "minimum_pair_ang",
        "audit_source_used", "mtp_grade_used",
    }
    if len(rows) != RESERVOIR_N:
        fatal(f"basin reservoir spec has {len(rows)} rows, expected {RESERVOIR_N}")
    if not rows or not required.issubset(rows[0]):
        fatal(f"basin reservoir columns missing: {sorted(required - set(rows[0] if rows else []))}")

    expected_recipes = [
        ("isotropic_010", 0.010, 0.000),
        ("isotropic_015", 0.015, 0.000),
        ("in_plane_012", 0.012, 0.000),
        ("out_of_plane_010", 0.010, 0.000),
        ("roo_breathing", 0.006, 0.008),
        ("donor_oh_mode", 0.006, 0.006),
    ]

    parsed: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows, start=1):
        minimum_pair_text = row["minimum_pair_ang"].strip()
        if not minimum_pair_text.startswith(">"):
            fatal(f"basin minimum_pair lock lacks strict operator in row {row_index}")
        minimum_pair_value = number(minimum_pair_text[1:])
        item = {
            "row_index": row_index,
            "order": int(row["reservoir_order"]),
            "id": row["candidate_id"],
            "side": row["side"],
            "recipe": row["recipe"],
            "base_rms": number(row["base_rms_ang"]),
            "directed": number(row["directed_amplitude_ang"]),
            "scale": number(row["amplitude_scale"]),
            "rng": row["rng"],
            "seed": int(row["seed"]),
            "minimum_abs_qpt": number(row["minimum_abs_qpt_ang"]),
            "minimum_pair": minimum_pair_value,
            "audit": bool_value(row["audit_source_used"]),
            "mtp_grade": bool_value(row["mtp_grade_used"]),
        }
        parsed.append(item)

    if len({item["id"] for item in parsed}) != RESERVOIR_N:
        fatal("basin reservoir candidate IDs are not unique")

    for side, side_offset, seed_base in (("left", 0, 320000), ("right", 48, 330000)):
        subset = parsed[side_offset:side_offset + RESERVOIR_PER_SIDE]
        if len(subset) != RESERVOIR_PER_SIDE or any(item["side"] != side for item in subset):
            fatal(f"basin reservoir {side} block is not 48 contiguous rows")
        if [item["order"] for item in subset] != list(range(1, RESERVOIR_PER_SIDE + 1)):
            fatal(f"basin reservoir order mismatch for {side}")

        for item in subset:
            recipe_name, expected_base, expected_directed = expected_recipes[(item["order"] - 1) % 6]
            cycle = (item["order"] - 1) // 6
            expected_scale = 1.0 + 0.10 * cycle
            expected_seed = seed_base + item["order"]
            expected_id = f"basin_control_{side}_{item['order']:03d}_v001"

            if item["id"] != expected_id:
                fatal(f"basin candidate ID mismatch: {item['id']} != {expected_id}")
            if item["recipe"] != recipe_name:
                fatal(f"basin recipe mismatch for {item['id']}")
            if abs(item["base_rms"] - expected_base) > 1.0e-12:
                fatal(f"basin base RMS mismatch for {item['id']}")
            if abs(item["directed"] - expected_directed) > 1.0e-12:
                fatal(f"basin directed amplitude mismatch for {item['id']}")
            if abs(item["scale"] - expected_scale) > 1.0e-12:
                fatal(f"basin amplitude scale mismatch for {item['id']}")
            if item["rng"] != "numpy_PCG64" or item["seed"] != expected_seed:
                fatal(f"basin RNG/seed mismatch for {item['id']}")
            if abs(item["minimum_abs_qpt"] - BASIN_QPT) > 1.0e-12:
                fatal(f"basin qPT threshold mismatch for {item['id']}")
            if abs(item["minimum_pair"] - MIN_PAIR) > 1.0e-12:
                fatal(f"basin minimum-pair threshold mismatch for {item['id']}")
            if item["audit"] or item["mtp_grade"]:
                fatal(f"basin blindness flags invalid for {item['id']}")
    return parsed


def parse_common36_fingerprints(common_path: Path) -> list[tuple[str, np.ndarray]]:
    blocks = read_cfg(common_path)
    if len(blocks) != 36:
        fatal(f"common36 contains {len(blocks)} blocks, expected 36")
    expected_types = [TYPE[symbol] for symbol in SYMBOLS]
    result: list[tuple[str, np.ndarray]] = []
    for block in blocks:
        if block.types != expected_types:
            fatal(f"common36 atom-type order mismatch in block {block.order}: {block.types}")
        identifier = (
            block.features.get("candidate_id")
            or block.features.get("configuration_id")
            or block.features.get("id")
            or f"common36_{block.order:03d}"
        )
        result.append((identifier, metrics(block.positions)["fingerprint"]))
    return result


def make_basin_candidate_geometry(endpoint: np.ndarray, item: dict[str, Any]) -> tuple[np.ndarray, float, float, float]:
    target_base_rms = item["base_rms"] * item["scale"]
    direction, _ = locked_random_direction(endpoint, item["recipe"], item["seed"])
    base_displacement = direction * target_base_rms
    base_actual_rms = displacement_rms(base_displacement)
    if abs(base_actual_rms - target_base_rms) > 1.0e-11:
        fatal(f"basin base RMS mismatch after normalization for {item['id']}")

    displacement = np.array(base_displacement, copy=True)
    directed_amplitude = item["directed"] * item["scale"]

    if item["recipe"] == "roo_breathing":
        oo_vector = endpoint[O2] - endpoint[O1]
        oo_unit = oo_vector / np.linalg.norm(oo_vector)
        displacement[O1] -= directed_amplitude * oo_unit
        displacement[O2] += directed_amplitude * oo_unit
        displacement = remove_translation_and_rotation(endpoint, displacement)

    elif item["recipe"] == "donor_oh_mode":
        endpoint_qpt = metrics(endpoint)["qpt"]
        donor_index = O1 if endpoint_qpt < 0.0 else O2
        donor_to_h = endpoint[HSTAR] - endpoint[donor_index]
        donor_to_h /= np.linalg.norm(donor_to_h)
        # Move H* toward the donor oxygen, following the pre-audit v019 operator.
        displacement[HSTAR] -= directed_amplitude * donor_to_h
        displacement = remove_translation_and_rotation(endpoint, displacement)

    elif item["directed"] != 0.0:
        fatal(f"unexpected directed amplitude for {item['id']}")

    final_rms = displacement_rms(displacement)
    return endpoint + displacement, target_base_rms, base_actual_rms, final_rms


def materialize_basin_reservoir(
    spec: list[dict[str, Any]],
    left: np.ndarray,
    right_aligned: np.ndarray,
    common_fingerprints: list[tuple[str, np.ndarray]],
) -> list[BasinCandidate]:
    records: list[BasinCandidate] = []
    prior_valid: list[tuple[str, np.ndarray]] = []

    for item in spec:
        endpoint = left if item["side"] == "left" else right_aligned
        positions, base_target, base_actual, final_rms = make_basin_candidate_geometry(endpoint, item)
        met, reasons = geometry_reasons(positions, side=item["side"])

        nearest_common = min(
            fingerprint_rms(met["fingerprint"], fingerprint)
            for _, fingerprint in common_fingerprints
        )
        if nearest_common <= FINGERPRINT_DUPLICATE_TOL:
            reasons.append(f"duplicate_common36_fingerprint_rms={nearest_common:.12e}")

        nearest_prior: float | None = None
        if prior_valid:
            nearest_prior = min(
                fingerprint_rms(met["fingerprint"], fingerprint)
                for _, fingerprint in prior_valid
            )
            if nearest_prior <= FINGERPRINT_DUPLICATE_TOL:
                reasons.append(f"duplicate_prior_basin_fingerprint_rms={nearest_prior:.12e}")

        valid = not reasons
        record = BasinCandidate(
            row_index=item["row_index"],
            reservoir_order=item["order"],
            candidate_id=item["id"],
            side=item["side"],
            recipe=item["recipe"],
            base_rms_ang=item["base_rms"],
            directed_amplitude_ang=item["directed"],
            amplitude_scale=item["scale"],
            seed=item["seed"],
            positions=positions,
            qpt=met["qpt"],
            roo=met["roo"],
            min_pair=met["min_pair"],
            max_span=met["max_span"],
            fingerprint=met["fingerprint"],
            base_target_rms_ang=base_target,
            base_actual_rms_ang=base_actual,
            final_displacement_rms_ang=final_rms,
            valid_unique=valid,
            rejection_reasons=reasons,
            nearest_common36_fingerprint_rms_ang=nearest_common,
            nearest_prior_valid_fingerprint_rms_ang=nearest_prior,
        )
        records.append(record)
        if valid:
            prior_valid.append((record.candidate_id, record.fingerprint))

    if len(records) != RESERVOIR_N:
        fatal(f"materialized {len(records)} basin candidates, expected {RESERVOIR_N}")

    valid_left = [record for record in records if record.side == "left" and record.valid_unique]
    valid_right = [record for record in records if record.side == "right" and record.valid_unique]
    if len(valid_left) < 12 or len(valid_right) < 12:
        fatal(
            "locked reservoir cannot support worst-case K=24: "
            f"valid left={len(valid_left)}, valid right={len(valid_right)}"
        )
    return records


def basin_raw_cfg(record: BasinCandidate, cell: np.ndarray) -> str:
    lines = ["BEGIN_CFG", " Size", "    9", " Supercell"]
    for row in cell:
        lines.append(f"    {row[0]:.16g} {row[1]:.16g} {row[2]:.16g}")
    lines.append(" AtomData:  id type cartes_x cartes_y cartes_z")
    for index, (symbol, position) in enumerate(zip(SYMBOLS, record.positions), start=1):
        lines.append(
            f"    {index:4d} {TYPE[symbol]:2d} "
            f"{position[0]:.16g} {position[1]:.16g} {position[2]:.16g}"
        )
    feature_values = {
        "amplitude_scale": f"{record.amplitude_scale:.8f}",
        "audit_source_used": "false",
        "base_actual_rms_ang": f"{record.base_actual_rms_ang:.12f}",
        "base_rms_ang": f"{record.base_rms_ang:.8f}",
        "base_target_scaled_rms_ang": f"{record.base_target_rms_ang:.12f}",
        "candidate_id": record.candidate_id,
        "directed_amplitude_ang": f"{record.directed_amplitude_ang:.8f}",
        "final_displacement_rms_ang": f"{record.final_displacement_rms_ang:.12f}",
        "maximum_span_ang": f"{record.max_span:.12f}",
        "minimum_pair_ang": f"{record.min_pair:.12f}",
        "mtp_grade_used": "false",
        "q_pt_ang": f"{record.qpt:.12f}",
        "r_oo_ang": f"{record.roo:.12f}",
        "recipe": record.recipe,
        "rejection_reasons": "none" if not record.rejection_reasons else "|".join(record.rejection_reasons),
        "reservoir_order": record.reservoir_order,
        "rng": "numpy_PCG64",
        "seed": record.seed,
        "side": record.side,
        "technical_materialization_rule": "v019_operators_plus_v020_numeric_lock",
        "training_eligible_before_dft": "false",
        "valid_unique": str(record.valid_unique).lower(),
        "version": "v026_corrected",
    }
    for key, value in sorted(feature_values.items()):
        lines.append(f" Feature   {key} {value}")
    lines.append("END_CFG")
    return "\n".join(lines) + "\n"


def select_basin_records(records: list[BasinCandidate], k: int) -> tuple[list[BasinCandidate], int, int]:
    if not 0 <= k <= TUBE_N:
        fatal(f"invalid K for basin selection: {k}")
    left_quota = (k + 1) // 2
    right_quota = k // 2
    valid_left = sorted(
        [record for record in records if record.side == "left" and record.valid_unique],
        key=lambda record: record.reservoir_order,
    )
    valid_right = sorted(
        [record for record in records if record.side == "right" and record.valid_unique],
        key=lambda record: record.reservoir_order,
    )
    selected = valid_left[:left_quota] + valid_right[:right_quota]
    if len(selected) != k:
        fatal(
            f"could not fill exact basin K={k}: "
            f"left {len(valid_left)}/{left_quota}, right {len(valid_right)}/{right_quota}"
        )
    return selected, left_quota, right_quota

def recover_selected(selected: list[Block], graded: list[Block]) -> list[tuple[Block, str]]:
    source = {candidate_id(block): block for block in graded}
    out: list[tuple[Block, str]] = []
    used: set[str] = set()

    for block in selected:
        cid = block.features.get("candidate_id", "").strip()

        if cid:
            if cid not in source:
                fatal(f"select-add candidate ID not found in graded pool: {cid}")
            validate_cfg_roundtrip(block, source[cid], cid, "select-add")
        else:
            matches = [
                key for key, reference in source.items()
                if (
                    block.types == reference.types
                    and np.allclose(
                        block.positions,
                        reference.positions,
                        atol=COORDINATE_MATCH_TOL,
                        rtol=0,
                    )
                )
            ]
            if len(matches) != 1:
                fatal(f"cannot recover selected candidate ID; matches={matches}")
            cid = matches[0]
            validate_cfg_roundtrip(block, source[cid], cid, "select-add")

        if cid in used:
            fatal(f"select-add produced duplicate candidate: {cid}")
        used.add(cid)
        out.append((block, cid))

    return out


def write_queue_files(directory: Path, blocks: list[tuple[Block, str]], role: str, k: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for index, (block, cid) in enumerate(blocks, 1):
        raw = add_features(block.raw, {
            "dft_queue_index": index,
            "dft_queue_role": role,
            "equal_budget_K": k,
            "selected_for_dft": "true",
            "training_eligible_after_dft": "true",
            "version": "v026",
        })
        write_raw_cfg(directory / f"{index:03d}_{cid}.cfg", [raw])


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def verify_v020_checksum(v020: Path, path: Path) -> None:
    checksum_path = require_file(v020 / "checksums_v020.tsv", "v020 checksums")
    rows = read_tsv(checksum_path)
    lookup = {row["path"]: row["sha256"] for row in rows}
    relative = path.relative_to(ROOT).as_posix()
    if relative not in lookup:
        fatal(f"v020 checksum entry missing for {relative}")
    check_hash(path, lookup[relative], f"v020 locked file {path.name}")


def geometry_roundtrip_diagnostics(first: Block, second: Block) -> dict[str, float | bool]:
    delta = first.positions - second.positions
    direct_max_abs = float(np.max(np.abs(delta)))
    direct_rms = float(np.sqrt(np.mean(np.sum(delta ** 2, axis=1))))
    fingerprint_delta = metrics(first.positions)["fingerprint"] - metrics(second.positions)["fingerprint"]
    fingerprint_rms_value = float(np.sqrt(np.mean(fingerprint_delta ** 2)))

    if first.cell is None and second.cell is None:
        cell_max_abs = 0.0
    elif first.cell is None or second.cell is None:
        cell_max_abs = math.inf
    else:
        cell_max_abs = float(np.max(np.abs(first.cell - second.cell)))

    return {
        "direct_max_abs_ang": direct_max_abs,
        "direct_rms_ang": direct_rms,
        "fingerprint_rms_ang": fingerprint_rms_value,
        "cell_max_abs_ang": cell_max_abs,
        "types_equal": first.types == second.types,
    }


def validate_cfg_roundtrip(block: Block, reference: Block, cid: str, stage: str) -> None:
    diagnostics = geometry_roundtrip_diagnostics(block, reference)

    if not diagnostics["types_equal"]:
        fatal(f"{stage} atom types changed for candidate {cid}")

    if diagnostics["cell_max_abs_ang"] > COORDINATE_MATCH_TOL:
        fatal(
            f"{stage} cell changed for candidate {cid}: "
            f"max_abs={diagnostics['cell_max_abs_ang']:.3e} A; "
            f"tolerance={COORDINATE_MATCH_TOL:.3e} A"
        )

    if diagnostics["direct_max_abs_ang"] > COORDINATE_MATCH_TOL:
        fatal(
            f"{stage} geometry changed for candidate {cid}: "
            f"max_abs={diagnostics['direct_max_abs_ang']:.3e} A; "
            f"atomwise_RMS={diagnostics['direct_rms_ang']:.3e} A; "
            f"fingerprint_RMS={diagnostics['fingerprint_rms_ang']:.3e} A; "
            f"locked_tolerance={COORDINATE_MATCH_TOL:.3e} A"
        )


def recover_graded_blocks(graded: list[Block], generated: list[Block]) -> list[tuple[Block, str]]:
    source: dict[str, Block] = {candidate_id(block): block for block in generated}
    if len(source) != len(generated):
        fatal("generated tube CFG contains duplicate candidate IDs")
    recovered: list[tuple[Block, str]] = []
    used: set[str] = set()
    for block in graded:
        cid = block.features.get("candidate_id", "").strip()
        if cid:
            if cid not in source:
                fatal(f"graded candidate ID not found in generated pool: {cid}")
            validate_cfg_roundtrip(block, source[cid], cid, "calc-grade")
        else:
            matches = [
                key for key, source_block in source.items()
                if (
                    block.types == source_block.types
                    and np.allclose(
                        block.positions,
                        source_block.positions,
                        atol=COORDINATE_MATCH_TOL,
                        rtol=0,
                    )
                )
            ]
            if len(matches) != 1:
                fatal(f"cannot recover graded candidate ID; matches={matches}")
            cid = matches[0]
            validate_cfg_roundtrip(block, source[cid], cid, "calc-grade")
        if cid in used:
            fatal(f"duplicate graded candidate: {cid}")
        used.add(cid)
        recovered.append((block, cid))
    if used != set(source):
        missing = sorted(set(source) - used)
        extra = sorted(used - set(source))
        fatal(f"graded candidate set differs from generated tube set; missing={missing}; extra={extra}")
    return recovered


def main() -> None:
    global ACTIVE_STATUS

    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    attempts = {name: resolve_pointer(path, name) for name, path in POINTERS.items()}
    for name, (filename, expected) in STATUSES.items():
        check_status(attempts[name], filename, expected, name)

    v016, v018, v020 = attempts["v016"], attempts["v018"], attempts["v020"]
    common = require_file(v016 / "datasets" / "train_common_strict_v001.cfg", "common36")
    model = require_file(v018 / "selected_model" / "selected_common36_l12_v018.mtp", "v018 model")
    v018_als = require_file(v018 / "active_learning_state" / "state_common36_l12_v018.als", "v018 ALS")
    check_hash(common, COMMON_SHA, "common36")
    check_hash(model, MODEL_SHA, "v018 model")
    check_hash(v018_als, ALS_SHA, "v018 ALS")

    common_fingerprints = parse_common36_fingerprints(common)

    protocol_md = require_file(v020 / "protocol_lock" / "PRE_AUDIT_STRICT_PROTOCOL_LOCK_v001.md", "v020 lock")
    protocol_json = require_file(v020 / "protocol_lock" / "PRE_AUDIT_STRICT_PROTOCOL_LOCK_v001.json", "v020 lock JSON")
    tube_spec_path = require_file(v020 / "specifications" / "fresh_transition_tube_24_spec_v001.tsv", "tube spec")
    tube_method = require_file(v020 / "specifications" / "fresh_transition_tube_generation_method_v001.md", "tube method")
    active_method = require_file(v020 / "specifications" / "active_selection_and_K_definition_v001.md", "active selection method")
    basin_spec_path = require_file(v020 / "specifications" / "basin_control_candidate_reservoir_96_spec_v001.tsv", "basin reservoir spec")
    basin_method = require_file(v020 / "specifications" / "basin_control_generation_method_v001.md", "basin method")
    final_training = require_file(v020 / "specifications" / "final_equal_budget_training_protocol_v001.md", "final training protocol")
    v019_source = require_file(ROOT / "scripts" / "step21_prepare_independent_audit_v019.py", "pre-audit v019 source")

    for locked_file in (
        protocol_md, protocol_json, tube_spec_path, tube_method,
        active_method, basin_spec_path, basin_method, final_training,
    ):
        verify_v020_checksum(v020, locked_file)

    lock_text = protocol_md.read_text(encoding="utf-8") + protocol_json.read_text(encoding="utf-8")
    for required_hash in (PROTOCOL_SHA, COMMON_SHA, MODEL_SHA, ALS_SHA):
        if required_hash not in lock_text:
            fatal(f"locked hash absent from v020 lock: {required_hash}")

    left_input = require_file(
        v016 / "source_dft_inputs" / "strict_common_dft_v015_001" / "pw.in",
        "left endpoint",
    )
    right_input = require_file(
        v016 / "source_dft_inputs" / "strict_common_dft_v015_002" / "pw.in",
        "right endpoint",
    )
    symbols_left, left, cell_left = parse_qe_geometry(left_input)
    symbols_right, right, cell_right = parse_qe_geometry(right_input)
    if symbols_left != symbols_right or not np.allclose(cell_left, cell_right, atol=1.0e-12, rtol=0):
        fatal("endpoint atom order or cells differ")
    if not np.allclose(cell_left, np.diag([16.0, 16.0, 16.0]), atol=1.0e-10, rtol=0):
        fatal(f"unexpected endpoint cell:\n{cell_left}")

    left_metrics, left_reasons = geometry_reasons(left, side="left")
    right_raw_metrics, right_raw_reasons = geometry_reasons(right, side="right")
    if left_reasons:
        fatal("left endpoint validation failed: " + "; ".join(left_reasons))
    if right_raw_reasons:
        fatal("right endpoint validation failed: " + "; ".join(right_raw_reasons))

    right_aligned, alignment_rmsd = kabsch(right, left)
    right_metrics, right_reasons = geometry_reasons(right_aligned, side="right")
    if right_reasons:
        fatal("aligned right endpoint validation failed: " + "; ".join(right_reasons))
    if alignment_rmsd > 0.50:
        fatal(f"mass-weighted Kabsch RMSD too large: {alignment_rmsd:.8f} A")

    tube_spec = parse_tube_spec(tube_spec_path)
    tube = generate_tube(tube_spec, left, right_aligned)

    basin_spec = parse_basin_spec(basin_spec_path)
    basin_records = materialize_basin_reservoir(
        basin_spec,
        left,
        right_aligned,
        common_fingerprints,
    )
    valid_left = [record for record in basin_records if record.side == "left" and record.valid_unique]
    valid_right = [record for record in basin_records if record.side == "right" and record.valid_unique]
    invalid_records = [record for record in basin_records if not record.valid_unique]

    if not MLP.is_file() or not os.access(MLP, os.X_OK):
        fatal(f"mlp missing or not executable: {MLP}")
    help_outputs: dict[str, str] = {}
    for command in ("calc-grade", "select-add"):
        result = subprocess.run(
            [str(MLP), "help", command],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        output = result.stdout + result.stderr
        help_outputs[command] = output
        if command not in output:
            fatal(f"local mlp help validation failed for {command}")
    if "--als-filename" not in help_outputs["calc-grade"]:
        fatal("local calc-grade help does not advertise --als-filename")

    if args.preflight_only:
        print("PASS_V026_CORRECTED_PREFLIGHT_NO_MLP_NO_DFT")
        print(f"common36:                 {common}")
        print(f"level-12 model:           {model}")
        print(f"v020 lock:                {v020}")
        print(f"tube materialized:        {len(tube)}/{TUBE_N}")
        print(
            f"tube qPT range:           "
            f"{min(candidate.qpt for candidate in tube):.8f} to "
            f"{max(candidate.qpt for candidate in tube):.8f} A"
        )
        print(
            f"tube R_OO range:          "
            f"{min(candidate.roo for candidate in tube):.8f} to "
            f"{max(candidate.roo for candidate in tube):.8f} A"
        )
        print(f"basin materialized:       {len(basin_records)}/{RESERVOIR_N}")
        print(
            f"basin valid unique:       {len(valid_left)} left + "
            f"{len(valid_right)} right; invalid={len(invalid_records)}"
        )
        print("worst-case basin K=24:    PASS (12 left + 12 right available)")
        print(f"endpoint qPT:             {left_metrics['qpt']:.8f}, {right_metrics['qpt']:.8f} A")
        print(f"mass-weighted Kabsch RMSD:{alignment_rmsd:.8f} A")
        print(f"selection rule:           strictly gamma > {GAMMA}")
        print(f"CFG round-trip tolerance: {COORDINATE_MATCH_TOL:.1e} A (locked v020 coordinate tolerance)")
        print("audit candidate files:    NOT OPENED")
        print("attempt directory:        NOT CREATED")
        print("mlp calc-grade:           NOT EXECUTED")
        print("mlp select-add:           NOT EXECUTED")
        print("pw.x/neb.x/train/LAMMPS:  NOT EXECUTED")
        return

    run_root = VERSION_ROOT / f"attempt_{stamp()}"
    if run_root.exists():
        fatal(f"attempt already exists: {run_root}")
    directories = {
        "tube": run_root / "tube",
        "selection": run_root / "selection",
        "basin": run_root / "basin_control",
        "reports": run_root / "reports",
        "provenance": run_root / "provenance",
        "queues": run_root / "dft_queues",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)

    status_path = run_root / "STATUS_v026.txt"
    ACTIVE_STATUS = status_path
    status_path.write_text("RUNNING_FRESH_TUBE_ACTIVE_SELECTION_v026\n", encoding="utf-8")
    run_log = run_root / "run_log_v026.txt"

    def log(message: str) -> None:
        line = f"[{now()}] {message}"
        print(line, flush=True)
        with run_log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    for source in (
        protocol_md, protocol_json, tube_spec_path, tube_method,
        active_method, basin_spec_path, basin_method, final_training,
    ):
        shutil.copy2(source, directories["provenance"] / source.name)
    shutil.copy2(left_input, directories["provenance"] / "left_endpoint_source_pw.in")
    shutil.copy2(right_input, directories["provenance"] / "right_endpoint_source_pw.in")
    shutil.copy2(v019_source, directories["provenance"] / v019_source.name)
    shutil.copy2(Path(__file__).resolve(), directories["provenance"] / Path(__file__).name)

    materialization_note = directories["provenance"] / "BASIN_TECHNICAL_MATERIALIZATION_RULE_v026.md"
    materialization_note.write_text(
        "\n".join([
            "# Basin-control technical materialization rule v026",
            "",
            "The v020 lock fixes the 96 recipe rows, amplitudes, scales, seeds,",
            "side allocation, geometric filters and duplicate rules, but does not",
            "contain an executable coordinate-construction function.",
            "",
            "This implementation uses only pre-audit information:",
            "",
            "- random and rigid-motion operators copied from v019;",
            "- O1-C2-O2 plane definition copied from v019;",
            "- R_OO breathing and donor-OH direction definitions copied from v019;",
            "- all numeric RMS values, directed amplitudes, scales and seeds from v020.",
            "",
            "No audit geometry, energy, force, MTP grade or selected targeted",
            "geometry was used to define or filter the basin reservoir.",
            "",
        ]) + "\n",
        encoding="utf-8",
    )

    tube_pool = directories["tube"] / "fresh_transition_tube_24_v026.cfg"
    graded_cfg = directories["tube"] / "fresh_transition_tube_24_with_grades_v026.cfg"
    preselected_cfg = directories["selection"] / "tube_gamma_gt_2_preselected_v026.cfg"
    selected_cfg = directories["selection"] / "tube_maxvol_selected_K_v026.cfg"
    calc_grade_als = directories["selection"] / "state_common36_l12_calc_grade_v026.als"

    write_tube(tube_pool, tube, cell_left)
    generated_blocks = read_cfg(tube_pool)
    if len(generated_blocks) != TUBE_N:
        fatal("written tube pool count mismatch")

    tube_generation_rows = [{
        "candidate_order": candidate.order,
        "candidate_id": candidate.candidate_id,
        "interpolation_coordinate": candidate.s,
        "perturbation": candidate.perturbation,
        "projection": candidate.projection,
        "target_rms_ang": candidate.target_rms,
        "accepted_fallback_factor": candidate.fallback,
        "actual_rms_ang": candidate.actual_rms,
        "seed": candidate.seed,
        "qpt_ang": candidate.qpt,
        "roo_ang": candidate.roo,
        "minimum_pair_ang": candidate.min_pair,
        "maximum_span_ang": candidate.max_span,
        "audit_source_used": False,
    } for candidate in tube]
    write_tsv(
        directories["reports"] / "fresh_transition_tube_generation_v026.tsv",
        tube_generation_rows,
        list(tube_generation_rows[0]),
    )

    reservoir_all_cfg = directories["basin"] / "basin_control_materialized_reservoir_96_v026.cfg"
    reservoir_valid_cfg = directories["basin"] / "basin_control_valid_unique_reservoir_v026.cfg"
    write_raw_cfg(reservoir_all_cfg, [basin_raw_cfg(record, cell_left) for record in basin_records])
    write_raw_cfg(
        reservoir_valid_cfg,
        [basin_raw_cfg(record, cell_left) for record in basin_records if record.valid_unique],
    )
    if len(read_cfg(reservoir_all_cfg)) != RESERVOIR_N:
        fatal("written basin reservoir count mismatch")

    basin_materialization_rows = [{
        "row_index": record.row_index,
        "reservoir_order": record.reservoir_order,
        "candidate_id": record.candidate_id,
        "side": record.side,
        "recipe": record.recipe,
        "base_rms_ang": record.base_rms_ang,
        "directed_amplitude_ang": record.directed_amplitude_ang,
        "amplitude_scale": record.amplitude_scale,
        "seed": record.seed,
        "base_target_scaled_rms_ang": record.base_target_rms_ang,
        "base_actual_rms_ang": record.base_actual_rms_ang,
        "final_displacement_rms_ang": record.final_displacement_rms_ang,
        "qpt_ang": record.qpt,
        "roo_ang": record.roo,
        "minimum_pair_ang": record.min_pair,
        "maximum_span_ang": record.max_span,
        "nearest_common36_fingerprint_rms_ang": record.nearest_common36_fingerprint_rms_ang,
        "nearest_prior_valid_fingerprint_rms_ang": "" if record.nearest_prior_valid_fingerprint_rms_ang is None else record.nearest_prior_valid_fingerprint_rms_ang,
        "valid_unique": record.valid_unique,
        "rejection_reasons": "" if not record.rejection_reasons else "|".join(record.rejection_reasons),
    } for record in basin_records]
    write_tsv(
        directories["reports"] / "basin_control_materialization_96_v026.tsv",
        basin_materialization_rows,
        list(basin_materialization_rows[0]),
    )

    log("Validated v016/v018/v020 and completed v023/v024/v025 audit statuses.")
    log("Generated locked tube24 and materialized locked basin reservoir96 without opening audit candidate files.")
    log(f"Basin reservoir validity: {len(valid_left)} left + {len(valid_right)} right; invalid={len(invalid_records)}.")

    calc_command = [
        str(MLP), "calc-grade", str(model), str(common),
        str(tube_pool), str(graded_cfg),
        f"--als-filename={calc_grade_als}",
    ]
    calc_result = run_mlp(
        calc_command,
        run_root,
        directories["reports"] / "calc_grade_v026.stdout.txt",
        directories["reports"] / "calc_grade_v026.stderr.txt",
    )
    if calc_result.returncode != 0:
        status_path.write_text("FAIL_CALC_GRADE_v026\n", encoding="utf-8")
        fatal(f"mlp calc-grade failed with return code {calc_result.returncode}")
    require_file(calc_grade_als, "calc-grade ALS output")

    graded_blocks = read_cfg(graded_cfg)
    if len(graded_blocks) != TUBE_N:
        fatal(f"calc-grade output count {len(graded_blocks)}, expected {TUBE_N}")
    recovered_graded = recover_graded_blocks(graded_blocks, generated_blocks)
    tube_by_id = {candidate.candidate_id: candidate for candidate in tube}
    graded_by_id: dict[str, Block] = {}
    grade_rows: list[dict[str, Any]] = []
    preselected_pairs: list[tuple[Block, str]] = []

    for block, cid in recovered_graded:
        if not block.features.get("candidate_id", "").strip():
            block = parse_block(
                add_features(block.raw, {"candidate_id": cid}),
                block.order,
            )
        current_grade = grade(block)
        take = current_grade > GAMMA
        graded_by_id[cid] = block
        if take:
            preselected_pairs.append((block, cid))
        candidate = tube_by_id[cid]
        grade_rows.append({
            "candidate_order": candidate.order,
            "candidate_id": cid,
            "interpolation_coordinate": candidate.s,
            "perturbation": candidate.perturbation,
            "qpt_ang": candidate.qpt,
            "roo_ang": candidate.roo,
            "mv_grade": current_grade,
            "strict_gamma_gt_2": take,
        })

    grade_rows.sort(key=lambda row: int(row["candidate_order"]))
    write_tsv(
        directories["reports"] / "fresh_transition_tube_grades_v026.tsv",
        grade_rows,
        list(grade_rows[0]),
    )
    write_raw_cfg(
        preselected_cfg,
        [
            add_features(block.raw, {"candidate_id": cid})
            if not block.features.get("candidate_id", "").strip()
            else block.raw
            for block, cid in preselected_pairs
        ],
    )

    minimum_grade = min(float(row["mv_grade"]) for row in grade_rows)
    maximum_grade = max(float(row["mv_grade"]) for row in grade_rows)
    log(
        f"calc-grade PASS: grade range {minimum_grade:.6f}-{maximum_grade:.6f}; "
        f"strict gamma>2 pool {len(preselected_pairs)}/{TUBE_N}."
    )

    if not preselected_pairs:
        final_status = "STOP_K0_NO_EXTRAPOLATIVE_TUBE_CANDIDATES_v026"
        status_path.write_text(final_status + "\n", encoding="utf-8")
        summary = {
            "created_utc": now(),
            "status": final_status,
            "K": 0,
            "run_root": run_root,
            "audit_candidate_files_opened": False,
            "execution": {"calc_grade": True, "select_add": False, "pw": False, "neb": False, "train": False, "lammps": False},
        }
        (run_root / "summary_v026.json").write_text(json.dumps(json_safe(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        VERSION_ROOT.mkdir(parents=True, exist_ok=True)
        CURRENT_POINTER.write_text(str(run_root) + "\n", encoding="utf-8")
        ACTIVE_STATUS = None
        print(f"\n{final_status}\nRun root: {run_root}\nK=0; strict comparison stopped before DFT queue creation.")
        return

    select_command = [
        str(MLP), "select-add", str(model), str(common),
        str(preselected_cfg), str(selected_cfg),
    ]
    select_result = run_mlp(
        select_command,
        run_root,
        directories["reports"] / "select_add_v026.stdout.txt",
        directories["reports"] / "select_add_v026.stderr.txt",
    )
    if select_result.returncode != 0:
        status_path.write_text("FAIL_SELECT_ADD_v026\n", encoding="utf-8")
        fatal(f"mlp select-add failed with return code {select_result.returncode}")

    selected_blocks = read_cfg(selected_cfg) if selected_cfg.is_file() else []
    recovered_selected = recover_selected(selected_blocks, list(graded_by_id.values()))
    selected_ids = [cid for _, cid in recovered_selected]
    if len(selected_ids) != len(set(selected_ids)):
        fatal("select-add produced duplicate selected candidates")
    allowed_ids = {cid for _, cid in preselected_pairs}
    if not set(selected_ids).issubset(allowed_ids):
        fatal("select-add output contains a candidate outside strict gamma>2 pool")

    k = len(recovered_selected)
    if k == 0:
        final_status = "STOP_K0_AFTER_SELECT_ADD_v026"
        status_path.write_text(final_status + "\n", encoding="utf-8")
        summary = {
            "created_utc": now(),
            "status": final_status,
            "K": 0,
            "run_root": run_root,
            "audit_candidate_files_opened": False,
            "execution": {"calc_grade": True, "select_add": True, "pw": False, "neb": False, "train": False, "lammps": False},
        }
        (run_root / "summary_v026.json").write_text(json.dumps(json_safe(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        VERSION_ROOT.mkdir(parents=True, exist_ok=True)
        CURRENT_POINTER.write_text(str(run_root) + "\n", encoding="utf-8")
        ACTIVE_STATUS = None
        print(f"\n{final_status}\nRun root: {run_root}\nK=0; strict comparison stopped.")
        return
    if k > len(preselected_pairs) or k > TUBE_N:
        fatal(f"invalid K={k}")

    selected_rows: list[dict[str, Any]] = []
    for selection_order, (_, cid) in enumerate(recovered_selected, start=1):
        current_grade = grade(graded_by_id[cid])
        if not current_grade > GAMMA:
            fatal(f"selected candidate fails strict gamma>2: {cid}")
        candidate = tube_by_id[cid]
        selected_rows.append({
            "selection_order": selection_order,
            "candidate_id": cid,
            "candidate_order": candidate.order,
            "interpolation_coordinate": candidate.s,
            "perturbation": candidate.perturbation,
            "qpt_ang": candidate.qpt,
            "roo_ang": candidate.roo,
            "mv_grade": current_grade,
        })
    write_tsv(
        directories["reports"] / "tube_maxvol_selected_K_v026.tsv",
        selected_rows,
        list(selected_rows[0]),
    )

    selected_basin, left_quota, right_quota = select_basin_records(basin_records, k)

    # DFT queue and later training order are candidate-ID order by the locked protocol.
    targeted_queue_ids = sorted(selected_ids)
    basin_queue_records = sorted(selected_basin, key=lambda record: record.candidate_id)
    targeted_queue_pairs = [(graded_by_id[cid], cid) for cid in targeted_queue_ids]
    basin_queue_pairs: list[tuple[Block, str]] = []
    basin_selected_raw: list[str] = []
    basin_manifest_rows: list[dict[str, Any]] = []

    for queue_index, record in enumerate(basin_queue_records, start=1):
        raw = add_features(
            basin_raw_cfg(record, cell_left),
            {
                "dft_queue_index": queue_index,
                "dft_queue_role": "equal_budget_basin_control",
                "equal_budget_K": k,
                "selected_for_dft": "true",
                "training_eligible_after_dft": "true",
            },
        )
        block = parse_block(raw, queue_index)
        basin_selected_raw.append(raw)
        basin_queue_pairs.append((block, record.candidate_id))
        basin_manifest_rows.append({
            "queue_index": queue_index,
            "candidate_id": record.candidate_id,
            "side": record.side,
            "reservoir_order": record.reservoir_order,
            "recipe": record.recipe,
            "qpt_ang": record.qpt,
            "roo_ang": record.roo,
            "minimum_pair_ang": record.min_pair,
            "equal_budget_K": k,
        })

    basin_selected_cfg = directories["basin"] / "basin_control_selected_exact_K_v026.cfg"
    write_raw_cfg(basin_selected_cfg, basin_selected_raw)
    if len(read_cfg(basin_selected_cfg)) != k:
        fatal("written basin-control selected CFG count mismatch")
    write_tsv(
        directories["reports"] / "basin_control_selected_exact_K_v026.tsv",
        basin_manifest_rows,
        list(basin_manifest_rows[0]),
    )

    write_queue_files(directories["queues"] / "targeted_tube", targeted_queue_pairs, "targeted_tube", k)
    write_queue_files(directories["queues"] / "basin_control", basin_queue_pairs, "equal_budget_basin_control", k)

    targeted_manifest_rows = []
    for queue_index, cid in enumerate(targeted_queue_ids, start=1):
        candidate = tube_by_id[cid]
        targeted_manifest_rows.append({
            "queue_index": queue_index,
            "candidate_id": cid,
            "candidate_order": candidate.order,
            "interpolation_coordinate": candidate.s,
            "perturbation": candidate.perturbation,
            "qpt_ang": candidate.qpt,
            "roo_ang": candidate.roo,
            "mv_grade": grade(graded_by_id[cid]),
            "equal_budget_K": k,
        })
    write_tsv(
        directories["reports"] / "targeted_dft_queue_manifest_v026.tsv",
        targeted_manifest_rows,
        list(targeted_manifest_rows[0]),
    )

    log(
        f"select-add PASS: exact K={k}; prepared targeted K={k} and "
        f"basin {left_quota} left + {right_quota} right."
    )

    final_status = "PASS_FRESH_TUBE_SELECTION_K_FIXED_BASIN_QUEUE_READY"
    status_path.write_text(final_status + "\n", encoding="utf-8")
    report_path = directories["reports"] / "fresh_tube_active_selection_report_v026.md"
    report_path.write_text(
        "\n".join([
            "# Fresh transition-tube active selection report v026", "",
            f"Created UTC: {now()}", "", f"Status: `{final_status}`", "",
            "## Selection", "",
            f"- generated tube candidates: {TUBE_N}",
            f"- strict gamma > 2 candidates: {len(preselected_pairs)}",
            f"- validated select-add output count K: {k}",
            f"- grade range: {minimum_grade:.12f} to {maximum_grade:.12f}", "",
            "## Equal-budget queues", "",
            f"- targeted DFT queue: {k}",
            f"- basin-control DFT queue: {k}",
            f"- basin allocation: {left_quota} left + {right_quota} right", "",
            "## Basin materialization", "",
            f"- locked reservoir rows: {RESERVOIR_N}",
            f"- valid unique candidates: {len(valid_left)} left + {len(valid_right)} right",
            f"- invalid candidates: {len(invalid_records)}",
            "- technical rule: pre-audit v019 operators plus v020 numeric lock", "",
            "## Blindness and execution", "",
            "- v023/v024/v025 successful statuses checked",
            "- audit candidate coordinate/energy/force files opened: no",
            "- mlp calc-grade executed: yes",
            "- mlp select-add executed: yes",
            "- pw.x executed: no",
            "- neb.x executed: no",
            "- mlp train executed: no",
            "- LAMMPS executed: no", "",
            "Next stage: equal-budget DFT labelling of both frozen K-structure queues.",
        ]) + "\n",
        encoding="utf-8",
    )

    summary = {
        "created_utc": now(),
        "status": final_status,
        "run_root": run_root,
        "K": k,
        "gamma_threshold": GAMMA,
        "tube": {
            "generated": TUBE_N,
            "prefiltered_gamma_gt_2": len(preselected_pairs),
            "selected": k,
            "minimum_grade": minimum_grade,
            "maximum_grade": maximum_grade,
        },
        "basin_control": {
            "materialized": RESERVOIR_N,
            "valid_left": len(valid_left),
            "valid_right": len(valid_right),
            "invalid": len(invalid_records),
            "selected": k,
            "left_quota": left_quota,
            "right_quota": right_quota,
            "technical_materialization_rule": "v019_operators_plus_v020_numeric_lock",
        },
        "blindness": {
            "audit_statuses_checked": True,
            "audit_candidate_files_opened": False,
            "audit_used_in_generation": False,
            "audit_used_in_selection": False,
        },
        "execution": {
            "calc_grade": True,
            "select_add": True,
            "pw": False,
            "neb": False,
            "train": False,
            "lammps": False,
        },
        "upstream_hashes": {
            "common36": sha(common),
            "model": sha(model),
            "v018_als": sha(v018_als),
            "protocol": PROTOCOL_SHA,
            "v019_source": sha(v019_source),
        },
        "outputs": {
            "tube_pool": tube_pool,
            "graded_tube": graded_cfg,
            "preselected_tube": preselected_cfg,
            "selected_tube": selected_cfg,
            "basin_reservoir_all": reservoir_all_cfg,
            "basin_reservoir_valid": reservoir_valid_cfg,
            "selected_basin": basin_selected_cfg,
            "targeted_queue": directories["queues"] / "targeted_tube",
            "basin_queue": directories["queues"] / "basin_control",
            "report": report_path,
        },
    }
    (run_root / "summary_v026.json").write_text(
        json.dumps(json_safe(summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    checksum_rows: list[dict[str, str]] = []
    checksum_file = run_root / "checksums_v026.tsv"
    for path in sorted(run_root.rglob("*")):
        if path.is_file() and path != checksum_file:
            checksum_rows.append({
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha(path),
            })
    write_tsv(checksum_file, checksum_rows, ["path", "sha256"])

    VERSION_ROOT.mkdir(parents=True, exist_ok=True)
    CURRENT_POINTER.write_text(str(run_root) + "\n", encoding="utf-8")
    ACTIVE_STATUS = None

    print("\nPASS_FRESH_TUBE_SELECTION_K_FIXED_BASIN_QUEUE_READY: STEP 28 v026 COMPLETED\n")
    print(f"Run root:                  {run_root}")
    print(f"Fresh tube candidates:     {TUBE_N}")
    print(f"Strict gamma>2 candidates: {len(preselected_pairs)}")
    print(f"MaxVol-selected K:         {k}")
    print(f"Grade range:               {minimum_grade:.6f} - {maximum_grade:.6f}")
    print(f"Targeted DFT queue:        {k}")
    print(f"Basin-control DFT queue:   {k} ({left_quota} left + {right_quota} right)")
    print(f"Basin valid reservoir:     {len(valid_left)} left + {len(valid_right)} right")
    print(f"\nSelected tube:             {selected_cfg}")
    print(f"Selected basin control:    {basin_selected_cfg}")
    print(f"Report:                    {report_path}\n")
    print("mlp calc-grade WAS executed.")
    print("mlp select-add WAS executed.")
    print("pw.x, neb.x, mlp train and LAMMPS were NOT executed.")
    print("\nNext stage: equal-budget DFT labelling of both K-structure queues.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        if ACTIVE_STATUS is not None:
            ACTIVE_STATUS.write_text("INTERRUPTED_v026\n", encoding="utf-8")
        print("\nINTERRUPTED_v026", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        if ACTIVE_STATUS is not None and ACTIVE_STATUS.exists():
            current = ACTIVE_STATUS.read_text(encoding="utf-8").strip()
            if current.startswith("RUNNING_"):
                ACTIVE_STATUS.write_text("FAIL_RUNTIME_v026\n", encoding="utf-8")
        print(f"\nFATAL: {error}", file=sys.stderr)
        raise

#!/usr/bin/env python3
"""
Supplementary Table S1 builder v023
===================================

Build a complete numerical audit table from the completed visualization Step 01
v005 source package.

No DFT, model loading, training, ``mlp``, LAMMPS, molecular dynamics, NEB
optimization, or new physical evaluation is executed. The stage only validates,
reformats, and combines already frozen normalized results.

Authoritative input
-------------------
10_visualization/versions/
v005_q1_dataviz_source_audit_source_oracle_recovery/
CURRENT_VISUAL_SOURCE_AUDIT_V005.txt

Output
------
10_visualization/versions/
v023_supplementary_table_s1_complete_numerical_audit/
attempt_<UTC>/

Primary outputs
---------------
- long-form TSV and CSV;
- manuscript-ready Markdown comparison table;
- manuscript-ready LaTeX table;
- caption, report, validation, manifest, data lock and checksums.
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
import statistics
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


IMPLEMENTATION_ID = (
    "BUILD_SUPPLEMENTARY_TABLE_S1_COMPLETE_NUMERICAL_AUDIT_V023"
)
OUTPUT_VERSION = (
    "v023_supplementary_table_s1_complete_numerical_audit"
)
EXPECTED_INPUT_STATUS = (
    "PASS_VISUAL_SOURCE_AUDIT_V005_SOURCE_ORACLE_DATA_READY"
)
STATUS_PASS = (
    "PASS_SUPPLEMENTARY_TABLE_S1_COMPLETE_NUMERICAL_AUDIT_BUILT_V023"
)
STATUS_FAIL = (
    "FAIL_SUPPLEMENTARY_TABLE_S1_COMPLETE_NUMERICAL_AUDIT_V023"
)

INPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v005_q1_dataviz_source_audit_source_oracle_recovery"
)
INPUT_POINTER = "CURRENT_VISUAL_SOURCE_AUDIT_V005.txt"
OUTPUT_RELATIVE_ROOT = (
    "10_visualization/versions/"
    "v023_supplementary_table_s1_complete_numerical_audit"
)
OUTPUT_POINTER = (
    "CURRENT_SUPPLEMENTARY_TABLE_S1_COMPLETE_NUMERICAL_AUDIT_V023.txt"
)

COVERAGE_FILE = "source_data/dataset_coverage_v005.tsv"
SUBSET_METRICS_FILE = "source_data/audit21_subset_metrics_v005.tsv"
GRADE_METRICS_FILE = "source_data/audit21_grade_metrics_v005.tsv"
BARRIER_FILE = "source_data/neb9_barrier_summary_v005.tsv"
PRIMARY_FILE = "source_data/primary_metric_summary_v005.tsv"
RELAXED_FILE = "source_data/mtp_neb_classification_v005.tsv"
FIRST_STEP_FILE = "source_data/first_step_extrapolation_v005.tsv"
ORACLE_FILE = "source_data/source_oracle_contract_v005.json"
FIGURE_MANIFEST_FILE = "figure_manifest_v005.tsv"
SUMMARY_FILE = "summary_v005.json"
CHECKSUM_FILE = "checksums_v005.tsv"
STATUS_FILE = "STATUS_v005.txt"

NUMERIC_TOLERANCE = 5.0e-8
BREAK_THRESHOLD = 10.0
EXTRAPOLATION_THRESHOLD = 2.0

EXPECTED_COUNTS = {
    "common36": 36,
    "basin24": 24,
    "targeted24": 24,
    "audit_basin12": 12,
    "audit_neb9": 9,
    "basin60": 60,
    "targeted60": 60,
}

EXPECTED_SUBSET_METRICS = {
    ("basin", "all21"): {
        "configuration_count": 21,
        "energy_rmse_ev": 0.014244128813933506,
        "force_component_rmse_ev_ang": 0.07424800697902224,
    },
    ("basin", "basin12"): {
        "configuration_count": 12,
        "energy_rmse_ev": 0.00010950307118496787,
        "force_component_rmse_ev_ang": 0.003804298377309356,
    },
    ("basin", "neb9"): {
        "configuration_count": 9,
        "energy_rmse_ev": 0.02175789876485563,
        "force_component_rmse_ev_ang": 0.11333060051301846,
    },
    ("targeted", "all21"): {
        "configuration_count": 21,
        "energy_rmse_ev": 0.0013757227692346484,
        "force_component_rmse_ev_ang": 0.03482665626621564,
    },
    ("targeted", "basin12"): {
        "configuration_count": 12,
        "energy_rmse_ev": 0.0002834689237029412,
        "force_component_rmse_ev_ang": 0.004592659486354435,
    },
    ("targeted", "neb9"): {
        "configuration_count": 9,
        "energy_rmse_ev": 0.0020758029323383383,
        "force_component_rmse_ev_ang": 0.05293361194982999,
    },
}

EXPECTED_GRADES = {
    ("basin", "all21"): {
        "grade_median": 184.111709,
        "grade_max": 14500.8526,
        "grade_gt_10_count": 19,
    },
    ("basin", "neb9"): {
        "grade_median": 6678.371548,
        "grade_max": 14500.8526,
        "grade_gt_10_count": 7,
    },
    ("targeted", "all21"): {
        "grade_median": 337.381367,
        "grade_max": 12326.803231,
        "grade_gt_10_count": 19,
    },
    ("targeted", "neb9"): {
        "grade_median": 5497.731726,
        "grade_max": 12326.803231,
        "grade_gt_10_count": 7,
    },
}

EXPECTED_BARRIERS = {
    "DFT": {
        "lower_endpoint_barrier_mev": 36.072093892926205,
        "absolute_error_mev": 0.0,
    },
    "basin": {
        "lower_endpoint_barrier_mev": 0.8263598228950286,
        "absolute_error_mev": 35.245734070031176,
    },
    "targeted": {
        "lower_endpoint_barrier_mev": 31.971700288977445,
        "absolute_error_mev": 4.10039360394876,
    },
}

EXPECTED_PRIMARY = {
    "transition_force_component_rmse_ev_ang": {
        "basin": 0.1760826457854536,
        "targeted": 0.07868490481909636,
        "basin_over_targeted": 2.237819899385827,
    },
    "lower_endpoint_barrier_abs_error_mev": {
        "basin": 35.245734070031176,
        "targeted": 4.10039360394876,
        "basin_over_targeted": 8.595695309857287,
    },
}

EXPECTED_RELAXED = {
    "basin": {
        "classification": "invalid_geometry_collapse",
        "barrier_valid": False,
        "converged": False,
        "reported_lower_endpoint_barrier_ev": None,
        "maximum_neb_force_ev_ang": 11.442975922160553,
        "minimum_relative_energy_from_left_ev": -5.0962582067941185,
        "minimum_roo_ang": 1.7985316061400438,
        "minimum_pair_ang": 0.9519427449504909,
        "maximum_mass_weighted_rmsd_from_dft_image_ang":
            0.2495966907319963,
        "grade_median": 9207.164193,
        "grade_max": 535658.716794,
    },
    "targeted": {
        "classification": "converged_but_high_grade",
        "barrier_valid": True,
        "converged": True,
        "reported_lower_endpoint_barrier_ev": 0.030672292320105043,
        "maximum_neb_force_ev_ang": 0.02664574947856421,
        "minimum_relative_energy_from_left_ev": -9.319589935330441e-07,
        "minimum_roo_ang": 2.3924957584555977,
        "minimum_pair_ang": 1.0443962266868019,
        "maximum_mass_weighted_rmsd_from_dft_image_ang":
            0.0023785855552754713,
        "grade_median": 5216.319957,
        "grade_max": 12006.843432,
    },
}

EXPECTED_FIRST_STEP = {
    "T100_left": {
        "online": 66.410239,
        "offline": 66.415434,
        "endpoint": 1.0,
        "displacement_ang": 0.002037756398673096,
    },
    "T100_right": {
        "online": 79.987407,
        "offline": 79.969427,
        "endpoint": 0.996587,
        "displacement_ang": 0.001964944606653418,
    },
    "T300_left": {
        "online": 67.924938,
        "offline": 67.928927,
        "endpoint": 1.0,
        "displacement_ang": 0.002586581431461177,
    },
    "T300_right": {
        "online": 47.845043,
        "offline": 47.844478,
        "endpoint": 0.996587,
        "displacement_ang": 0.0027015058204460374,
    },
    "T500_left": {
        "online": 99.936321,
        "offline": 99.921547,
        "endpoint": 1.0,
        "displacement_ang": 0.004038176721531173,
    },
    "T500_right": {
        "online": 147.705216,
        "offline": 147.709445,
        "endpoint": 0.996587,
        "displacement_ang": 0.003824515164881248,
    },
}

EXPECTED_ORACLE_CLASSIFICATION = "EXACT_SOURCE_ORACLE_REPLAY_PASS"


class TableAuditError(RuntimeError):
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
    coverage_rows: list[dict[str, str]]
    subset_rows: list[dict[str, str]]
    grade_rows: list[dict[str, str]]
    barrier_rows: list[dict[str, str]]
    primary_rows: list[dict[str, str]]
    relaxed_rows: list[dict[str, str]]
    first_step_rows: list[dict[str, str]]
    oracle: dict[str, Any]
    manifest_rows: list[dict[str, str]]
    summary: dict[str, Any]
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
        raise TableAuditError(f"Missing {label}: {path}")
    if path.stat().st_size <= 0:
        raise TableAuditError(f"Empty {label}: {path}")
    return path


def read_text(path: Path) -> str:
    return require_file(path, "text file").read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise TableAuditError(f"Invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TableAuditError(f"Expected JSON object: {path}")
    return value


def read_tsv(path: Path) -> list[dict[str, str]]:
    path = require_file(path, "TSV file")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise TableAuditError(f"TSV has no header: {path}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise TableAuditError(f"TSV has no rows: {path}")
    return rows


def parse_float(value: Any, label: str) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise TableAuditError(f"Invalid float for {label}: {value!r}") from exc
    if not math.isfinite(result):
        raise TableAuditError(f"Non-finite float for {label}: {value!r}")
    return result


def parse_optional_float(value: Any, label: str) -> float | None:
    raw = str(value).strip()
    if raw == "":
        return None
    return parse_float(raw, label)


def parse_int(value: Any, label: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise TableAuditError(f"Invalid integer for {label}: {value!r}") from exc


def parse_bool(value: Any, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise TableAuditError(f"Invalid boolean for {label}: {value!r}")


def close(observed: float, expected: float) -> bool:
    scale = max(1.0, abs(expected))
    return abs(observed - expected) <= NUMERIC_TOLERANCE * scale


def atomic_write_text(path: Path, text: str) -> None:
    path = path.resolve()
    if path.exists():
        raise TableAuditError(f"Refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def atomic_write_delimited(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    delimiter: str,
) -> None:
    path = path.resolve()
    if path.exists():
        raise TableAuditError(f"Refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            delimiter=delimiter,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    os.replace(temporary, path)


def atomic_write_tsv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> None:
    atomic_write_delimited(path, fieldnames, rows, "\t")


def atomic_write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> None:
    atomic_write_delimited(path, fieldnames, rows, ",")


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
        raise TableAuditError(
            f"Expected one checksum row for {relative_path}; "
            f"found {len(matches)}"
        )
    target = require_file(attempt / relative_path, relative_path)
    expected_size = parse_int(
        matches[0]["size_bytes"],
        f"{relative_path} size",
    )
    expected_hash = matches[0]["sha256"].strip()
    observed_size = target.stat().st_size
    observed_hash = sha256_file(target)
    if observed_size != expected_size or observed_hash != expected_hash:
        raise TableAuditError(
            f"Checksum mismatch for {relative_path}: "
            f"size={observed_size}/{expected_size}; "
            f"sha256={observed_hash}/{expected_hash}"
        )
    return observed_hash


def resolve_input_attempt(root: Path) -> Path:
    version_root = (root / INPUT_RELATIVE_ROOT).resolve()
    pointer = require_file(version_root / INPUT_POINTER, "v005 current pointer")
    raw = pointer.read_text(encoding="utf-8").strip()
    if not raw:
        raise TableAuditError(f"Empty v005 pointer: {pointer}")
    attempt = Path(raw).expanduser().resolve()
    try:
        attempt.relative_to(version_root)
    except ValueError as exc:
        raise TableAuditError(
            f"v005 pointer escapes expected version root: {attempt}"
        ) from exc
    if not attempt.is_dir():
        raise TableAuditError(f"v005 pointer target is absent: {attempt}")
    status = read_text(attempt / STATUS_FILE).strip()
    if status != EXPECTED_INPUT_STATUS:
        raise TableAuditError(
            f"Unexpected v005 status: {status}; "
            f"expected {EXPECTED_INPUT_STATUS}"
        )
    return attempt


def load_locked_inputs(root: Path) -> LockedInputs:
    attempt = resolve_input_attempt(root)
    checksum_rows = read_tsv(attempt / CHECKSUM_FILE)
    relatives = (
        COVERAGE_FILE,
        SUBSET_METRICS_FILE,
        GRADE_METRICS_FILE,
        BARRIER_FILE,
        PRIMARY_FILE,
        RELAXED_FILE,
        FIRST_STEP_FILE,
        ORACLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    )
    source_hashes = {
        relative: verify_checksum_entry(attempt, checksum_rows, relative)
        for relative in relatives
    }
    return LockedInputs(
        attempt=attempt,
        coverage_rows=read_tsv(attempt / COVERAGE_FILE),
        subset_rows=read_tsv(attempt / SUBSET_METRICS_FILE),
        grade_rows=read_tsv(attempt / GRADE_METRICS_FILE),
        barrier_rows=read_tsv(attempt / BARRIER_FILE),
        primary_rows=read_tsv(attempt / PRIMARY_FILE),
        relaxed_rows=read_tsv(attempt / RELAXED_FILE),
        first_step_rows=read_tsv(attempt / FIRST_STEP_FILE),
        oracle=read_json(attempt / ORACLE_FILE),
        manifest_rows=read_tsv(attempt / FIGURE_MANIFEST_FILE),
        summary=read_json(attempt / SUMMARY_FILE),
        source_hashes=source_hashes,
    )


def lookup(
    rows: Sequence[Mapping[str, str]],
    key_fields: Sequence[str],
) -> dict[tuple[str, ...], dict[str, str]]:
    output: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row.get(field, "") for field in key_fields)
        if key in output:
            raise TableAuditError(f"Duplicate row for key {key_fields}={key}")
        output[key] = dict(row)
    return output


def validate_inputs(inputs: LockedInputs) -> list[Validation]:
    validations: list[Validation] = []

    coverage_counts: dict[str, int] = {}
    for row in inputs.coverage_rows:
        group = row["dataset_group"]
        coverage_counts[group] = coverage_counts.get(group, 0) + 1
    coverage_counts["basin60"] = sum(
        parse_bool(row["in_basin60"], "in_basin60")
        for row in inputs.coverage_rows
    )
    coverage_counts["targeted60"] = sum(
        parse_bool(row["in_targeted60"], "in_targeted60")
        for row in inputs.coverage_rows
    )
    for key, expected in EXPECTED_COUNTS.items():
        validations.append(
            Validation(
                f"coverage_count_{key}",
                coverage_counts.get(key, 0) == expected,
                str(coverage_counts.get(key, 0)),
                str(expected),
            )
        )

    subset = lookup(inputs.subset_rows, ("model", "subset"))
    validations.append(
        Validation(
            "subset_metric_keys",
            set(subset) == set(EXPECTED_SUBSET_METRICS),
            str(sorted(subset)),
            str(sorted(EXPECTED_SUBSET_METRICS)),
        )
    )
    for key, expected in EXPECTED_SUBSET_METRICS.items():
        row = subset[key]
        for field, expected_value in expected.items():
            if field == "configuration_count":
                observed = parse_int(row[field], f"{key} {field}")
                passed = observed == expected_value
            else:
                observed = parse_float(row[field], f"{key} {field}")
                passed = close(observed, float(expected_value))
            validations.append(
                Validation(
                    f"{key[0]}_{key[1]}_{field}",
                    passed,
                    str(observed),
                    str(expected_value),
                )
            )

    grades = lookup(inputs.grade_rows, ("model", "subset"))
    for key, expected in EXPECTED_GRADES.items():
        row = grades.get(key)
        validations.append(
            Validation(
                f"grade_row_{key[0]}_{key[1]}_present",
                row is not None,
                str(row is not None),
                "True",
            )
        )
        if row is None:
            continue
        for field, expected_value in expected.items():
            if field.endswith("_count"):
                observed = parse_int(row[field], f"{key} {field}")
                passed = observed == expected_value
            else:
                observed = parse_float(row[field], f"{key} {field}")
                passed = close(observed, float(expected_value))
            validations.append(
                Validation(
                    f"{key[0]}_{key[1]}_{field}",
                    passed,
                    str(observed),
                    str(expected_value),
                )
            )

    barriers = lookup(inputs.barrier_rows, ("series",))
    for series, expected in EXPECTED_BARRIERS.items():
        row = barriers.get((series,))
        validations.append(
            Validation(
                f"barrier_{series}_present",
                row is not None,
                str(row is not None),
                "True",
            )
        )
        if row is None:
            continue
        for field, expected_value in expected.items():
            observed = parse_float(row[field], f"{series} {field}")
            validations.append(
                Validation(
                    f"barrier_{series}_{field}",
                    close(observed, expected_value),
                    str(observed),
                    str(expected_value),
                )
            )

    primary = lookup(inputs.primary_rows, ("metric",))
    for metric, expected in EXPECTED_PRIMARY.items():
        row = primary.get((metric,))
        validations.append(
            Validation(
                f"primary_{metric}_present",
                row is not None,
                str(row is not None),
                "True",
            )
        )
        if row is None:
            continue
        for field, expected_value in expected.items():
            observed = parse_float(row[field], f"{metric} {field}")
            validations.append(
                Validation(
                    f"primary_{metric}_{field}",
                    close(observed, expected_value),
                    str(observed),
                    str(expected_value),
                )
            )

    relaxed = lookup(inputs.relaxed_rows, ("branch",))
    for branch, expected in EXPECTED_RELAXED.items():
        row = relaxed.get((branch,))
        validations.append(
            Validation(
                f"relaxed_{branch}_present",
                row is not None,
                str(row is not None),
                "True",
            )
        )
        if row is None:
            continue
        validations.extend(
            [
                Validation(
                    f"relaxed_{branch}_classification",
                    row["classification"] == expected["classification"],
                    row["classification"],
                    str(expected["classification"]),
                ),
                Validation(
                    f"relaxed_{branch}_barrier_valid",
                    parse_bool(row["barrier_valid"], "barrier_valid")
                    == expected["barrier_valid"],
                    row["barrier_valid"],
                    str(expected["barrier_valid"]),
                ),
                Validation(
                    f"relaxed_{branch}_converged",
                    parse_bool(row["converged"], "converged")
                    == expected["converged"],
                    row["converged"],
                    str(expected["converged"]),
                ),
            ]
        )
        for field in (
            "maximum_neb_force_ev_ang",
            "minimum_relative_energy_from_left_ev",
            "minimum_roo_ang",
            "minimum_pair_ang",
            "maximum_mass_weighted_rmsd_from_dft_image_ang",
            "grade_median",
            "grade_max",
        ):
            observed = parse_float(row[field], f"{branch} {field}")
            validations.append(
                Validation(
                    f"relaxed_{branch}_{field}",
                    close(observed, float(expected[field])),
                    str(observed),
                    str(expected[field]),
                )
            )
        observed_barrier = parse_optional_float(
            row["reported_lower_endpoint_barrier_ev"],
            f"{branch} reported barrier",
        )
        expected_barrier = expected["reported_lower_endpoint_barrier_ev"]
        passed = (
            observed_barrier is None and expected_barrier is None
        ) or (
            observed_barrier is not None
            and expected_barrier is not None
            and close(observed_barrier, float(expected_barrier))
        )
        validations.append(
            Validation(
                f"relaxed_{branch}_reported_barrier",
                passed,
                str(observed_barrier),
                str(expected_barrier),
            )
        )

    first_step = lookup(inputs.first_step_rows, ("trajectory_id",))
    validations.append(
        Validation(
            "first_step_case_set",
            set(key[0] for key in first_step) == set(EXPECTED_FIRST_STEP),
            str(sorted(key[0] for key in first_step)),
            str(sorted(EXPECTED_FIRST_STEP)),
        )
    )
    for case_id, expected in EXPECTED_FIRST_STEP.items():
        row = first_step[(case_id,)]
        fields = {
            "original_online_break_grade": expected["online"],
            "offline_exact_break_mv_grade": expected["offline"],
            "offline_endpoint_mv_grade": expected["endpoint"],
            "break_vs_endpoint_max_abs_ang":
                expected["displacement_ang"],
        }
        for field, expected_value in fields.items():
            observed = parse_float(row[field], f"{case_id} {field}")
            validations.append(
                Validation(
                    f"{case_id}_{field}",
                    close(observed, expected_value),
                    str(observed),
                    str(expected_value),
                )
            )
        validations.extend(
            [
                Validation(
                    f"{case_id}_threshold_agreement",
                    parse_bool(
                        row["threshold_class_agreement"],
                        "threshold_class_agreement",
                    ),
                    row["threshold_class_agreement"],
                    "True",
                ),
                Validation(
                    f"{case_id}_rejected",
                    parse_float(
                        row["offline_exact_break_mv_grade"],
                        "offline exact grade",
                    ) > BREAK_THRESHOLD,
                    row["offline_exact_break_mv_grade"],
                    f"> {BREAK_THRESHOLD}",
                ),
                Validation(
                    f"{case_id}_no_physical_dft_error",
                    not parse_bool(
                        row["physical_dft_error_measured"],
                        "physical_dft_error_measured",
                    ),
                    row["physical_dft_error_measured"],
                    "False",
                ),
            ]
        )

    validations.append(
        Validation(
            "source_oracle_classification",
            inputs.oracle.get("classification")
            == EXPECTED_ORACLE_CLASSIFICATION,
            str(inputs.oracle.get("classification")),
            EXPECTED_ORACLE_CLASSIFICATION,
        )
    )

    failures = [
        validation for validation in validations
        if validation.severity == "ERROR" and not validation.passed
    ]
    if failures:
        raise TableAuditError(
            "Supplementary Table S1 input validation failed: "
            + "; ".join(
                f"{item.check}: {item.observed} != {item.expected}"
                for item in failures
            )
        )
    return validations


def fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "not reported"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == 0:
            return "0"
        if abs(value) >= 1.0e4 or abs(value) < 1.0e-3:
            return f"{value:.4e}"
        return f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return str(value)


def table_row(
    section: str,
    metric: str,
    unit: str,
    basin: Any,
    targeted: Any,
    comparison: str,
    interpretation: str,
    source: str,
    scope: str = "model comparison",
) -> dict[str, Any]:
    return {
        "section": section,
        "metric": metric,
        "unit": unit,
        "scope": scope,
        "basin_trained": fmt(basin),
        "transition_targeted": fmt(targeted),
        "comparison": comparison,
        "interpretation": interpretation,
        "authoritative_source": source,
    }


def build_table_rows(inputs: LockedInputs) -> list[dict[str, Any]]:
    subset = lookup(inputs.subset_rows, ("model", "subset"))
    grades = lookup(inputs.grade_rows, ("model", "subset"))
    barriers = lookup(inputs.barrier_rows, ("series",))
    primary = lookup(inputs.primary_rows, ("metric",))
    relaxed = lookup(inputs.relaxed_rows, ("branch",))

    first_values = []
    relative_differences = []
    displacements = []
    endpoint_grades = []
    for row in inputs.first_step_rows:
        online = parse_float(
            row["original_online_break_grade"],
            "online grade",
        )
        offline = parse_float(
            row["offline_exact_break_mv_grade"],
            "offline grade",
        )
        endpoint = parse_float(
            row["offline_endpoint_mv_grade"],
            "endpoint grade",
        )
        displacement = parse_float(
            row["break_vs_endpoint_max_abs_ang"],
            "first-step displacement",
        )
        first_values.append(offline)
        endpoint_grades.append(endpoint)
        displacements.append(1000.0 * displacement)
        relative_differences.append(abs(online - offline) / abs(offline))

    rows: list[dict[str, Any]] = []
    rows.extend(
        [
            table_row(
                "Training design",
                "Total training configurations",
                "configurations",
                60,
                60,
                "equal budget",
                "Identical total DFT-labeling budget.",
                COVERAGE_FILE,
            ),
            table_row(
                "Training design",
                "Shared common configurations",
                "configurations",
                36,
                36,
                "shared",
                "Common36 is present in both branches.",
                COVERAGE_FILE,
            ),
            table_row(
                "Training design",
                "Branch-specific added configurations",
                "configurations",
                24,
                24,
                "equal count",
                "Only spatial placement differs between branches.",
                COVERAGE_FILE,
            ),
        ]
    )

    for subset_name, display in (
        ("all21", "Frozen audit21 energy RMSE"),
        ("basin12", "Frozen basin12 energy RMSE"),
        ("neb9", "Independent NEB9 energy RMSE"),
    ):
        basin_value = parse_float(
            subset[("basin", subset_name)]["energy_rmse_ev"],
            f"basin {subset_name} energy RMSE",
        )
        targeted_value = parse_float(
            subset[("targeted", subset_name)]["energy_rmse_ev"],
            f"targeted {subset_name} energy RMSE",
        )
        rows.append(
            table_row(
                "Frozen audit",
                display,
                "eV",
                basin_value,
                targeted_value,
                f"{basin_value / targeted_value:.3f}x basin/targeted",
                "Lower is better.",
                SUBSET_METRICS_FILE,
            )
        )

    for subset_name, display in (
        ("all21", "Frozen audit21 force-component RMSE"),
        ("basin12", "Frozen basin12 force-component RMSE"),
        ("neb9", "Independent NEB9 force-component RMSE"),
    ):
        basin_value = parse_float(
            subset[("basin", subset_name)]["force_component_rmse_ev_ang"],
            f"basin {subset_name} force RMSE",
        )
        targeted_value = parse_float(
            subset[("targeted", subset_name)]["force_component_rmse_ev_ang"],
            f"targeted {subset_name} force RMSE",
        )
        rows.append(
            table_row(
                "Frozen audit",
                display,
                "eV A^-1",
                basin_value,
                targeted_value,
                f"{basin_value / targeted_value:.3f}x basin/targeted",
                "Lower is better.",
                SUBSET_METRICS_FILE,
            )
        )

    transition = primary[
        ("transition_force_component_rmse_ev_ang",)
    ]
    rows.append(
        table_row(
            "Frozen audit",
            "Transition-region force-component RMSE",
            "eV A^-1",
            parse_float(transition["basin"], "basin transition force"),
            parse_float(
                transition["targeted"],
                "targeted transition force",
            ),
            (
                f"{parse_float(transition['basin_over_targeted'], 'ratio'):.3f}x "
                "lower for targeted"
            ),
            "Primary preregistered force metric over NEB images 4-6.",
            PRIMARY_FILE,
        )
    )

    rows.append(
        table_row(
            "Frozen audit",
            "Lower-endpoint barrier",
            "meV",
            parse_float(
                barriers[("basin",)]["lower_endpoint_barrier_mev"],
                "basin barrier",
            ),
            parse_float(
                barriers[("targeted",)]["lower_endpoint_barrier_mev"],
                "targeted barrier",
            ),
            "DFT reference = 36.0721 meV",
            "PBE is the locked comparison reference.",
            BARRIER_FILE,
        )
    )
    rows.append(
        table_row(
            "Frozen audit",
            "Absolute lower-endpoint barrier error",
            "meV",
            parse_float(
                barriers[("basin",)]["absolute_error_mev"],
                "basin barrier error",
            ),
            parse_float(
                barriers[("targeted",)]["absolute_error_mev"],
                "targeted barrier error",
            ),
            (
                f"{parse_float(primary[('lower_endpoint_barrier_abs_error_mev',)]['basin_over_targeted'], 'barrier ratio'):.3f}x "
                "lower for targeted"
            ),
            "Primary preregistered barrier metric.",
            f"{BARRIER_FILE}; {PRIMARY_FILE}",
        )
    )

    for subset_name, display in (
        ("all21", "Frozen audit21 grade median"),
        ("neb9", "Independent NEB9 grade median"),
    ):
        rows.append(
            table_row(
                "Applicability grades",
                display,
                "gamma",
                parse_float(
                    grades[("basin", subset_name)]["grade_median"],
                    "basin grade median",
                ),
                parse_float(
                    grades[("targeted", subset_name)]["grade_median"],
                    "targeted grade median",
                ),
                "gamma > 10 is break-class",
                "Applicability criterion, not measured DFT error.",
                GRADE_METRICS_FILE,
            )
        )
    for subset_name, display in (
        ("all21", "Frozen audit21 grade maximum"),
        ("neb9", "Independent NEB9 grade maximum"),
    ):
        rows.append(
            table_row(
                "Applicability grades",
                display,
                "gamma",
                parse_float(
                    grades[("basin", subset_name)]["grade_max"],
                    "basin grade max",
                ),
                parse_float(
                    grades[("targeted", subset_name)]["grade_max"],
                    "targeted grade max",
                ),
                "gamma > 10 is break-class",
                "Applicability criterion, not measured DFT error.",
                GRADE_METRICS_FILE,
            )
        )
    rows.append(
        table_row(
            "Applicability grades",
            "Frozen audit21 configurations above gamma=10",
            "count / 21",
            parse_int(
                grades[("basin", "all21")]["grade_gt_10_count"],
                "basin gt10",
            ),
            parse_int(
                grades[("targeted", "all21")]["grade_gt_10_count"],
                "targeted gt10",
            ),
            "19/21 for both",
            "High grades are systematic across the audit.",
            GRADE_METRICS_FILE,
        )
    )

    basin_relaxed = relaxed[("basin",)]
    targeted_relaxed = relaxed[("targeted",)]
    rows.extend(
        [
            table_row(
                "Relaxed MTP-NEB",
                "Classification",
                "",
                basin_relaxed["classification"],
                targeted_relaxed["classification"],
                "qualitative divergence",
                (
                    "Basin path collapses; targeted path converges but "
                    "remains high-grade."
                ),
                RELAXED_FILE,
            ),
            table_row(
                "Relaxed MTP-NEB",
                "Reported physical lower-endpoint barrier",
                "meV",
                None,
                1000.0 * parse_float(
                    targeted_relaxed[
                        "reported_lower_endpoint_barrier_ev"
                    ],
                    "targeted relaxed barrier",
                ),
                "basin barrier not reported",
                (
                    "No physical basin barrier is reported after geometry "
                    "collapse."
                ),
                RELAXED_FILE,
            ),
            table_row(
                "Relaxed MTP-NEB",
                "Absolute barrier error versus locked PBE reference",
                "meV",
                None,
                abs(
                    1000.0 * parse_float(
                        targeted_relaxed[
                            "reported_lower_endpoint_barrier_ev"
                        ],
                        "targeted relaxed barrier",
                    )
                    - EXPECTED_BARRIERS["DFT"][
                        "lower_endpoint_barrier_mev"
                    ]
                ),
                "targeted secondary evidence",
                "Targeted relaxed path remains strongly extrapolative.",
                RELAXED_FILE,
            ),
            table_row(
                "Relaxed MTP-NEB",
                "Maximum NEB force",
                "eV A^-1",
                parse_float(
                    basin_relaxed["maximum_neb_force_ev_ang"],
                    "basin max force",
                ),
                parse_float(
                    targeted_relaxed["maximum_neb_force_ev_ang"],
                    "targeted max force",
                ),
                "targeted numerically converged",
                "Basin optimization is invalid due to collapse.",
                RELAXED_FILE,
            ),
            table_row(
                "Relaxed MTP-NEB",
                "Maximum mass-weighted RMSD from DFT image",
                "A",
                parse_float(
                    basin_relaxed[
                        "maximum_mass_weighted_rmsd_from_dft_image_ang"
                    ],
                    "basin max RMSD",
                ),
                parse_float(
                    targeted_relaxed[
                        "maximum_mass_weighted_rmsd_from_dft_image_ang"
                    ],
                    "targeted max RMSD",
                ),
                "lower is closer to DFT path",
                "Targeted path closely follows the DFT geometry.",
                RELAXED_FILE,
            ),
            table_row(
                "Relaxed MTP-NEB",
                "Minimum R_OO",
                "A",
                parse_float(
                    basin_relaxed["minimum_roo_ang"],
                    "basin min R_OO",
                ),
                parse_float(
                    targeted_relaxed["minimum_roo_ang"],
                    "targeted min R_OO",
                ),
                "geometry guard = 1.800 A",
                "Basin path crosses the collapse guard.",
                RELAXED_FILE,
            ),
            table_row(
                "Relaxed MTP-NEB",
                "Minimum relative energy from left endpoint",
                "eV",
                parse_float(
                    basin_relaxed[
                        "minimum_relative_energy_from_left_ev"
                    ],
                    "basin min energy",
                ),
                parse_float(
                    targeted_relaxed[
                        "minimum_relative_energy_from_left_ev"
                    ],
                    "targeted min energy",
                ),
                "basin false deep minimum",
                "Basin value is a failure diagnostic, not a physical state.",
                RELAXED_FILE,
            ),
            table_row(
                "Relaxed MTP-NEB",
                "Grade median",
                "gamma",
                parse_float(
                    basin_relaxed["grade_median"],
                    "basin relaxed median",
                ),
                parse_float(
                    targeted_relaxed["grade_median"],
                    "targeted relaxed median",
                ),
                "both far above gamma=10",
                "Relaxed paths remain outside validated applicability.",
                RELAXED_FILE,
            ),
            table_row(
                "Relaxed MTP-NEB",
                "Grade maximum",
                "gamma",
                parse_float(
                    basin_relaxed["grade_max"],
                    "basin relaxed max",
                ),
                parse_float(
                    targeted_relaxed["grade_max"],
                    "targeted relaxed max",
                ),
                "both far above gamma=10",
                "Applicability grade is not measured DFT error.",
                RELAXED_FILE,
            ),
        ]
    )

    rows.extend(
        [
            table_row(
                "First-update deployment diagnostic",
                "Attempted cases rejected above gamma=10",
                "count / 6",
                "not assessed",
                sum(value > BREAK_THRESHOLD for value in first_values),
                "targeted model only",
                "All six first attempted updates were rejected.",
                FIRST_STEP_FILE,
                scope="targeted deployment diagnostic",
            ),
            table_row(
                "First-update deployment diagnostic",
                "Endpoint grade range",
                "gamma",
                "not assessed",
                (
                    f"{min(endpoint_grades):.6f}-"
                    f"{max(endpoint_grades):.6f}"
                ),
                "targeted model only",
                "Endpoints remain near grade 1.",
                FIRST_STEP_FILE,
                scope="targeted deployment diagnostic",
            ),
            table_row(
                "First-update deployment diagnostic",
                "First-update grade range",
                "gamma",
                "not assessed",
                f"{min(first_values):.6f}-{max(first_values):.6f}",
                "targeted model only",
                "Immediate transition into break-class applicability.",
                FIRST_STEP_FILE,
                scope="targeted deployment diagnostic",
            ),
            table_row(
                "First-update deployment diagnostic",
                "Maximum displacement range",
                "mA",
                "not assessed",
                f"{min(displacements):.3f}-{max(displacements):.3f}",
                "targeted model only",
                "Very small geometry updates already trigger rejection.",
                FIRST_STEP_FILE,
                scope="targeted deployment diagnostic",
            ),
            table_row(
                "First-update deployment diagnostic",
                "Online/offline maximum relative difference",
                "%",
                "not assessed",
                100.0 * max(relative_differences),
                "targeted model only",
                "Selection-interface consistency confirmed.",
                f"{FIRST_STEP_FILE}; {ORACLE_FILE}",
                scope="targeted deployment diagnostic",
            ),
            table_row(
                "First-update deployment diagnostic",
                "Usable MD trajectory",
                "",
                "not assessed",
                "no",
                "targeted model only",
                "Thermal stability and proton-transfer kinetics not assessed.",
                ORACLE_FILE,
                scope="targeted deployment diagnostic",
            ),
        ]
    )
    return rows


def markdown_escape(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", " ")


def build_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Supplementary Table S1. Complete numerical audit",
        "",
        "| Section | Metric | Unit | Basin-trained | Transition-targeted | Comparison / scope |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(str(row[field]))
                for field in (
                    "section",
                    "metric",
                    "unit",
                    "basin_trained",
                    "transition_targeted",
                    "comparison",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "**Notes.** PBE is the locked internal comparison reference, not a "
            "benchmark-quality physical proton-transfer barrier. MaxVol grade "
            "is an applicability criterion, not a measured DFT error. The "
            "first-update deployment diagnostic was performed for the "
            "transition-targeted model only. No physical optimized barrier is "
            "reported for the basin relaxed path after geometry collapse.",
            "",
        ]
    )
    return "\n".join(lines)


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def build_latex(rows: Sequence[Mapping[str, Any]]) -> str:
    body: list[str] = []
    current_section = None
    for row in rows:
        if row["section"] != current_section:
            current_section = row["section"]
            body.append(
                r"\multicolumn{6}{l}{\textbf{"
                + latex_escape(str(current_section))
                + r"}} \\"
            )
        fields = (
            row["metric"],
            row["unit"],
            row["basin_trained"],
            row["transition_targeted"],
            row["comparison"],
            row["scope"],
        )
        body.append(
            " & ".join(latex_escape(str(value)) for value in fields)
            + r" \\"
        )
    return r"""\begin{longtable}{p{0.27\linewidth} p{0.08\linewidth} p{0.13\linewidth} p{0.15\linewidth} p{0.19\linewidth} p{0.14\linewidth}}
\caption{Complete numerical audit of the equal-budget basin-trained and transition-targeted MTP comparison.}\\
\toprule
Metric & Unit & Basin-trained & Transition-targeted & Comparison & Scope \\
\midrule
\endfirsthead
\toprule
Metric & Unit & Basin-trained & Transition-targeted & Comparison & Scope \\
\midrule
\endhead
""" + "\n".join(body) + r"""
\bottomrule
\end{longtable}

\noindent\textit{Notes.} PBE is the locked internal comparison reference, not a benchmark-quality physical proton-transfer barrier. MaxVol grade is an applicability criterion, not a measured DFT error. The first-update deployment diagnostic was performed for the transition-targeted model only. No physical optimized barrier is reported for the basin relaxed path after geometry collapse.
"""


def write_caption(path: Path) -> None:
    caption = """# Supplementary Table S1. Complete numerical audit of the equal-budget comparison

The table consolidates training-set counts, frozen audit errors, frozen
barrier recovery, MaxVol applicability grades, relaxed MTP-NEB diagnostics and
the transition-targeted first-update deployment diagnostic. Values are copied
or deterministically reformatted from the checksum-locked v005 normalized
source package.

PBE is the locked internal comparison reference rather than a
benchmark-quality physical proton-transfer barrier. MaxVol grade is an
applicability criterion, not a measured DFT error. The first-update deployment
diagnostic was performed only for the transition-targeted model. The basin
relaxed path underwent geometry collapse, so no physical optimized basin
barrier is reported.
"""
    atomic_write_text(path, caption)


def validation_rows(
    validations: Sequence[Validation],
) -> list[dict[str, Any]]:
    return [dataclasses.asdict(item) for item in validations]


def write_checksums(attempt: Path) -> Path:
    path = attempt / "checksums_v023.tsv"
    rows = []
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


def update_pointer(version_root: Path, attempt: Path) -> Path:
    pointer = version_root / OUTPUT_POINTER
    temporary = version_root / f".{OUTPUT_POINTER}.tmp.{os.getpid()}"
    temporary.write_text(str(attempt.resolve()) + "\n", encoding="utf-8")
    os.replace(temporary, pointer)
    return pointer


def create_output_attempt(root: Path) -> tuple[Path, Path]:
    version_root = (root / OUTPUT_RELATIVE_ROOT).resolve()
    version_root.mkdir(parents=True, exist_ok=True)
    attempt = version_root / f"attempt_{utc_stamp()}"
    if attempt.exists():
        raise TableAuditError(f"Output attempt exists: {attempt}")
    attempt.mkdir(parents=False, exist_ok=False)
    return version_root, attempt


def snapshot_inputs(inputs: LockedInputs, attempt: Path) -> dict[str, Path]:
    snapshot_dir = attempt / "source_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    outputs = {}
    for relative in (
        COVERAGE_FILE,
        SUBSET_METRICS_FILE,
        GRADE_METRICS_FILE,
        BARRIER_FILE,
        PRIMARY_FILE,
        RELAXED_FILE,
        FIRST_STEP_FILE,
        ORACLE_FILE,
        FIGURE_MANIFEST_FILE,
        SUMMARY_FILE,
    ):
        source = inputs.attempt / relative
        destination = snapshot_dir / relative.replace("/", "__")
        shutil.copy2(source, destination)
        outputs[relative] = destination
    return outputs


def run(root: Path, validate_only: bool = False) -> int:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise TableAuditError(f"Project root is not a directory: {root}")

    inputs = load_locked_inputs(root)
    validations = validate_inputs(inputs)
    rows = build_table_rows(inputs)

    if validate_only:
        print("VALIDATE_ONLY=PASS")
        print(f"INPUT_ATTEMPT={inputs.attempt}")
        print(f"TABLE_ROWS={len(rows)}")
        print(f"VALIDATION_CHECKS={len(validations)}")
        print("SCIENTIFIC_EXECUTION=NONE")
        return 0

    version_root, attempt = create_output_attempt(root)
    try:
        tables_dir = attempt / "tables"
        reports_dir = attempt / "reports"
        tables_dir.mkdir(parents=True, exist_ok=False)
        reports_dir.mkdir(parents=True, exist_ok=False)

        snapshot_paths = snapshot_inputs(inputs, attempt)

        fields = [
            "section",
            "metric",
            "unit",
            "scope",
            "basin_trained",
            "transition_targeted",
            "comparison",
            "interpretation",
            "authoritative_source",
        ]
        tsv_path = (
            tables_dir
            / "supplementary_table_s1_complete_numerical_audit_v023.tsv"
        )
        csv_path = (
            tables_dir
            / "supplementary_table_s1_complete_numerical_audit_v023.csv"
        )
        md_path = (
            tables_dir
            / "supplementary_table_s1_complete_numerical_audit_v023.md"
        )
        tex_path = (
            tables_dir
            / "supplementary_table_s1_complete_numerical_audit_v023.tex"
        )
        atomic_write_tsv(tsv_path, fields, rows)
        atomic_write_csv(csv_path, fields, rows)
        atomic_write_text(md_path, build_markdown(rows))
        atomic_write_text(tex_path, build_latex(rows))

        caption_path = attempt / "supplementary_table_s1_caption_v023.md"
        write_caption(caption_path)

        validation_path = (
            reports_dir
            / "supplementary_table_s1_validation_v023.tsv"
        )
        atomic_write_tsv(
            validation_path,
            ["check", "passed", "observed", "expected", "severity"],
            validation_rows(validations),
        )

        report_path = (
            reports_dir
            / "supplementary_table_s1_build_report_v023.md"
        )
        report = f"""# Supplementary Table S1 build report v023

Created UTC: `{utc_iso()}`

Status: `{STATUS_PASS}`

## Scope

This stage consolidated already frozen normalized values. No DFT, model
loading, training, `mlp`, LAMMPS, molecular dynamics, NEB optimization or new
physical evaluation was executed.

## Locked input

- v005 attempt: `{inputs.attempt}`
- verified source files: `{len(inputs.source_hashes)}`
- validation checks: `{len(validations)}`
- output table rows: `{len(rows)}`

## Outputs

- TSV: `{tsv_path}`
- CSV: `{csv_path}`
- Markdown: `{md_path}`
- LaTeX: `{tex_path}`
- Caption: `{caption_path}`
- Validation: `{validation_path}`

## Scientific interpretation

The table separates three levels of evidence: frozen pointwise fidelity,
relaxed-path topology and deployment applicability. Transition-focused labeling
improves frozen and relaxed-path behavior at equal DFT budget, but does not
bring the reaction-path or first-update configurations inside the validated
MaxVol applicability domain.

## Mandatory caveats

- PBE is the locked internal comparison reference.
- MaxVol grade is not a measured DFT error.
- The first-update diagnostic is targeted-model-only and is not an MD trajectory.
- No physical optimized barrier is reported for the collapsed basin path.
"""
        atomic_write_text(report_path, report)

        data_lock_path = (
            attempt / "supplementary_table_s1_data_lock_v023.json"
        )
        atomic_write_json(
            data_lock_path,
            {
                "schema_version": "1.0",
                "created_utc": utc_iso(),
                "implementation": IMPLEMENTATION_ID,
                "input_attempt": str(inputs.attempt),
                "input_status": EXPECTED_INPUT_STATUS,
                "source_hashes": inputs.source_hashes,
                "expected_counts": EXPECTED_COUNTS,
                "thresholds": {
                    "extrapolation": EXTRAPOLATION_THRESHOLD,
                    "break": BREAK_THRESHOLD,
                },
                "scientific_execution": {
                    "dft": False,
                    "model_loading": False,
                    "training": False,
                    "mlp": False,
                    "lammps": False,
                    "md": False,
                    "neb_optimization": False,
                    "new_physical_evaluation": False,
                },
            },
        )

        manifest_path = (
            attempt / "supplementary_table_s1_manifest_v023.tsv"
        )
        manifest_rows = [
            {
                "artifact_id": "Supplementary_Table_S1",
                "role": "complete_numerical_audit",
                "tsv": str(tsv_path.relative_to(attempt)),
                "csv": str(csv_path.relative_to(attempt)),
                "markdown": str(md_path.relative_to(attempt)),
                "latex": str(tex_path.relative_to(attempt)),
                "caption": str(caption_path.relative_to(attempt)),
                "status": "BUILT_AND_VALIDATED",
                "scientific_message": (
                    "Transition-focused equal-budget labeling improves "
                    "frozen and relaxed-path fidelity but does not ensure "
                    "deployment applicability."
                ),
                "mandatory_caveat": (
                    "MaxVol grade is not measured DFT error; first-update "
                    "diagnostic is targeted-model-only."
                ),
            }
        ]
        atomic_write_tsv(
            manifest_path,
            list(manifest_rows[0].keys()),
            manifest_rows,
        )

        summary_path = attempt / "summary_v023.json"
        atomic_write_json(
            summary_path,
            {
                "schema_version": "1.0",
                "created_utc": utc_iso(),
                "implementation": IMPLEMENTATION_ID,
                "status": STATUS_PASS,
                "input_attempt": str(inputs.attempt),
                "output_attempt": str(attempt),
                "table_row_count": len(rows),
                "outputs": {
                    "tsv": str(tsv_path),
                    "csv": str(csv_path),
                    "markdown": str(md_path),
                    "latex": str(tex_path),
                    "caption": str(caption_path),
                    "report": str(report_path),
                    "validation": str(validation_path),
                    "manifest": str(manifest_path),
                    "data_lock": str(data_lock_path),
                    "source_snapshot": {
                        key: str(value)
                        for key, value in snapshot_paths.items()
                    },
                },
                "next_stage": (
                    "Build the manuscript Results/Discussion evidence map "
                    "and locked figure captions."
                ),
            },
        )

        atomic_write_text(attempt / "STATUS_v023.txt", STATUS_PASS + "\n")
        checksums_path = write_checksums(attempt)
        pointer_path = update_pointer(version_root, attempt)

        print(STATUS_PASS)
        print(f"RUN_DIR={attempt}")
        print(f"TSV={tsv_path}")
        print(f"CSV={csv_path}")
        print(f"MARKDOWN={md_path}")
        print(f"LATEX={tex_path}")
        print(f"CAPTION={caption_path}")
        print(f"REPORT={report_path}")
        print(f"VALIDATION={validation_path}")
        print(f"SUMMARY={summary_path}")
        print(f"CHECKSUMS={checksums_path}")
        print(f"CURRENT_POINTER={pointer_path}")
        print("SCIENTIFIC_EXECUTION=NONE")
        return 0
    except Exception:
        status_path = attempt / "STATUS_v023.txt"
        if not status_path.exists():
            status_path.write_text(STATUS_FAIL + "\n", encoding="utf-8")
        raise


def synthetic_coverage_rows() -> list[dict[str, Any]]:
    rows = []
    index = 0
    for group, count in (
        ("common36", 36),
        ("basin24", 24),
        ("targeted24", 24),
        ("audit_basin12", 12),
        ("audit_neb9", 9),
    ):
        for item in range(count):
            index += 1
            rows.append(
                {
                    "coverage_index": index,
                    "dataset_group": group,
                    "source_id": f"{group}_{item + 1:02d}",
                    "side": "",
                    "subset": group,
                    "qpt_ang": 0.0,
                    "roo_ang": 2.5,
                    "dft_energy_ev": -100.0,
                    "maximum_atomic_force_ev_ang": 0.0,
                    "selection_mv_grade": "",
                    "basin_model_mv_grade": "",
                    "targeted_model_mv_grade": "",
                    "is_frozen_audit": group.startswith("audit_"),
                    "in_basin60": group in {"common36", "basin24"},
                    "in_targeted60": group in {"common36", "targeted24"},
                    "source_version": "synthetic",
                    "source_file": "synthetic",
                }
            )
    return rows


def make_synthetic_fixture(root: Path) -> Path:
    attempt = root / INPUT_RELATIVE_ROOT / "attempt_20990101T000000Z"
    (attempt / "source_data").mkdir(parents=True)

    atomic_write_tsv(
        attempt / COVERAGE_FILE,
        list(synthetic_coverage_rows()[0].keys()),
        synthetic_coverage_rows(),
    )

    subset_rows = []
    for (model, subset), values in EXPECTED_SUBSET_METRICS.items():
        subset_rows.append(
            {
                "model": model,
                "subset": subset,
                "configuration_count": values["configuration_count"],
                "energy_rmse_ev": values["energy_rmse_ev"],
                "energy_mae_ev": values["energy_rmse_ev"] * 0.8,
                "energy_max_abs_ev": values["energy_rmse_ev"] * 1.7,
                "energy_mean_error_ev": 0.0,
                "energy_centered_rmse_ev": values["energy_rmse_ev"],
                "force_component_rmse_ev_ang":
                    values["force_component_rmse_ev_ang"],
                "force_component_mae_ev_ang":
                    values["force_component_rmse_ev_ang"] * 0.8,
                "force_component_max_abs_ev_ang":
                    values["force_component_rmse_ev_ang"] * 2.0,
                "force_vector_rmse_ev_ang":
                    values["force_component_rmse_ev_ang"] * math.sqrt(3.0),
                "force_vector_max_ev_ang":
                    values["force_component_rmse_ev_ang"] * 3.0,
            }
        )
    atomic_write_tsv(
        attempt / SUBSET_METRICS_FILE,
        list(subset_rows[0].keys()),
        subset_rows,
    )

    grade_rows = []
    for model in ("basin", "targeted"):
        for subset in ("all21", "basin12", "neb9"):
            source = EXPECTED_GRADES.get((model, subset), {})
            grade_rows.append(
                {
                    "model": model,
                    "subset": subset,
                    "configuration_count":
                        EXPECTED_SUBSET_METRICS[(model, subset)][
                            "configuration_count"
                        ],
                    "grade_min": 1.0,
                    "grade_median": source.get("grade_median", 200.0),
                    "grade_mean": source.get("grade_median", 200.0),
                    "grade_max": source.get("grade_max", 1000.0),
                    "grade_gt_2_count":
                        EXPECTED_SUBSET_METRICS[(model, subset)][
                            "configuration_count"
                        ],
                    "grade_gt_10_count":
                        source.get("grade_gt_10_count", 12),
                }
            )
    atomic_write_tsv(
        attempt / GRADE_METRICS_FILE,
        list(grade_rows[0].keys()),
        grade_rows,
    )

    barrier_rows = []
    for series, values in EXPECTED_BARRIERS.items():
        barrier_rows.append(
            {
                "series": series,
                "lower_endpoint_barrier_ev":
                    values["lower_endpoint_barrier_mev"] / 1000.0,
                "lower_endpoint_barrier_mev":
                    values["lower_endpoint_barrier_mev"],
                "absolute_error_ev": values["absolute_error_mev"] / 1000.0,
                "absolute_error_mev": values["absolute_error_mev"],
                "maximum_image": 5,
                "maximum_qpt_ang": 0.0,
                "lower_endpoint_image": 1,
            }
        )
    atomic_write_tsv(
        attempt / BARRIER_FILE,
        list(barrier_rows[0].keys()),
        barrier_rows,
    )

    primary_rows = []
    for metric, values in EXPECTED_PRIMARY.items():
        primary_rows.append(
            {
                "metric": metric,
                "definition": "synthetic",
                "unit": "eV/A" if "force" in metric else "meV",
                "basin": values["basin"],
                "targeted": values["targeted"],
                "targeted_minus_basin":
                    values["targeted"] - values["basin"],
                "basin_over_targeted": values["basin_over_targeted"],
                "targeted_better": True,
                "authoritative_source": "synthetic",
            }
        )
    atomic_write_tsv(
        attempt / PRIMARY_FILE,
        list(primary_rows[0].keys()),
        primary_rows,
    )

    relaxed_rows = []
    for branch, values in EXPECTED_RELAXED.items():
        relaxed_rows.append(
            {
                "branch": branch,
                "classification": values["classification"],
                "barrier_valid": values["barrier_valid"],
                "optimization_status":
                    "converged" if values["converged"]
                    else "geometry_guard_stop",
                "converged": values["converged"],
                "maximum_neb_force_ev_ang":
                    values["maximum_neb_force_ev_ang"],
                "guard_reason":
                    "" if branch == "targeted"
                    else "image5:roo<=1.800",
                "minimum_relative_energy_from_left_ev":
                    values["minimum_relative_energy_from_left_ev"],
                "minimum_roo_ang": values["minimum_roo_ang"],
                "minimum_pair_ang": values["minimum_pair_ang"],
                "maximum_mass_weighted_rmsd_from_dft_image_ang":
                    values[
                        "maximum_mass_weighted_rmsd_from_dft_image_ang"
                    ],
                "formal_lower_endpoint_barrier_ev":
                    0.0005612818879399128
                    if branch == "basin"
                    else values["reported_lower_endpoint_barrier_ev"],
                "reported_lower_endpoint_barrier_ev":
                    ""
                    if values["reported_lower_endpoint_barrier_ev"] is None
                    else values["reported_lower_endpoint_barrier_ev"],
                "maximum_image": 5,
                "grade_median": values["grade_median"],
                "grade_max": values["grade_max"],
                "interpretation": "synthetic",
            }
        )
    atomic_write_tsv(
        attempt / RELAXED_FILE,
        list(relaxed_rows[0].keys()),
        relaxed_rows,
    )

    first_step_rows = []
    for case_id, values in EXPECTED_FIRST_STEP.items():
        first_step_rows.append(
            {
                "trajectory_id": case_id,
                "temperature_K": int(case_id[1:4]),
                "side": case_id.split("_")[1],
                "original_online_break_grade": values["online"],
                "offline_exact_break_mv_grade": values["offline"],
                "offline_endpoint_mv_grade": values["endpoint"],
                "break_vs_endpoint_max_abs_ang":
                    values["displacement_ang"],
                "threshold_class_agreement": True,
                "physical_dft_error_measured": False,
            }
        )
    atomic_write_tsv(
        attempt / FIRST_STEP_FILE,
        list(first_step_rows[0].keys()),
        first_step_rows,
    )

    atomic_write_json(
        attempt / ORACLE_FILE,
        {
            "classification": EXPECTED_ORACLE_CLASSIFICATION,
            "usable_md_trajectory": False,
            "physical_dft_error_measured": False,
        },
    )
    manifest_rows = [
        {
            "figure_id": f"Figure_{index}",
            "title": "synthetic",
            "panels": "synthetic",
            "primary_source_data": "synthetic",
            "geometry_sources": "",
            "status": "SOURCE_DATA_READY",
            "scientific_message": "synthetic",
            "mandatory_caveat": "synthetic",
        }
        for index in (1, 2, 3, 4)
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

    checksum_rows = []
    for relative in (
        COVERAGE_FILE,
        SUBSET_METRICS_FILE,
        GRADE_METRICS_FILE,
        BARRIER_FILE,
        PRIMARY_FILE,
        RELAXED_FILE,
        FIRST_STEP_FILE,
        ORACLE_FILE,
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
    with tempfile.TemporaryDirectory(prefix="supp_table_s1_v023_test_") as temp:
        root = Path(temp)
        make_synthetic_fixture(root)
        inputs = load_locked_inputs(root)
        validations = validate_inputs(inputs)
        rows = build_table_rows(inputs)
        if not rows:
            raise TableAuditError("Synthetic table has no rows")
        markdown = build_markdown(rows)
        latex = build_latex(rows)
        if "Transition-targeted" not in markdown:
            raise TableAuditError("Markdown table regression")
        if "\\begin{longtable}" not in latex:
            raise TableAuditError("LaTeX table regression")
        print("SELF_TEST=PASS")
        print(f"VALIDATION_CHECKS={len(validations)}")
        print(f"TABLE_ROWS={len(rows)}")
        print("FORMATS=TSV,CSV,MARKDOWN,LATEX")
        print("SCIENTIFIC_EXECUTION=NONE")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build Supplementary Table S1 from the completed v005 "
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
        help="Run a synthetic table-builder regression",
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
    except TableAuditError as exc:
        print(f"TABLE_AUDIT_ERROR: {exc}", file=sys.stderr)
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

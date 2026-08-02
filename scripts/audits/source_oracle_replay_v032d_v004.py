#!/usr/bin/env python3
"""
MALONALDEHYDE v032d CFG-BLOCK SOURCE-ORACLE REPLAY v004

Purpose
-------
Replay the final v032d canonicalization and displacement logic by calling the
exact hash-locked pure function from the frozen provenance source, rather than
reimplementing Kabsch, unwrapping, assignment ranking, or RMS conventions.

The fixed scientific inputs are:
- raw selector-captured preselected.cfg for each of six trajectories;
- frozen offline endpoint geometry.cfg for the corresponding side;
- the frozen row in captured_break_configurations_v032d.tsv.

No alternative endpoint, atom mapping, or alignment is searched. The only
"search" performed is structural introspection of the exact source function's
returned object to identify which named return fields were written to the
final table.

This stage never runs DFT, LAMMPS, MD, mlp calc-grade, model loading, or
training. All upstream files are read-only.
"""

from __future__ import annotations

import argparse
import builtins
import ast
import csv
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import inspect
import json
import math
import os
import re
import shutil
import sys
import tarfile
import traceback
import types
import copy
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


STAGE = "v032k_v032d_cfgblock_source_oracle_replay"
VERSION = "v004"
DEFAULT_ROOT = Path("${PROJECT_ROOT}")
OUTPUT_REL = Path("09_strict_comparison/versions") / STAGE
POINTER_NAME = "CURRENT_V032D_CFGBLOCK_SOURCE_ORACLE_REPLAY.txt"
STATUS_NAME = "STATUS_v032k.txt"

EXPECTED_SOURCE_SHA256 = (
    "8585a400029d74b7c5c13c4f37220e3954b5a4d90015d4f4cbee478f80de91be"
)
TRAJECTORIES = (
    "T100_left", "T100_right",
    "T300_left", "T300_right",
    "T500_left", "T500_right",
)
LOCKED_ELEMENTS = ("O", "H", "C", "H", "C", "H", "C", "O", "H")
MLIP_TO_ELEMENT = {0: "C", 1: "H", 2: "O"}

TOL = 2.0e-8
ORDER_KEYS = (
    "canonical_order_zero_based", "order", "canonical_order",
    "assignment", "permutation", "indices",
)
POSITION_WORDS = ("position", "positions", "coords", "coordinates", "cartes")
TYPE_WORDS = ("type", "types")
ELEMENT_WORDS = ("element", "elements", "symbol", "symbols", "species")


class AuditError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Atom:
    atom_id: int
    atom_type: int
    element: str
    position: tuple[float, float, float]


@dataclasses.dataclass
class CFGFrame:
    path: Path
    atoms: list[Atom]
    cell: np.ndarray
    features: dict[str, str]

    def positions(self) -> np.ndarray:
        return np.asarray([a.position for a in self.atoms], dtype=float)

    def types(self) -> np.ndarray:
        return np.asarray([a.atom_type for a in self.atoms], dtype=int)

    def elements(self) -> tuple[str, ...]:
        return tuple(a.element for a in self.atoms)

    def ids(self) -> tuple[int, ...]:
        return tuple(a.atom_id for a in self.atoms)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def log(message: str) -> None:
    print(f"[{utc_now()}] {message}", flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise AuditError(f"Missing {label}: {path}")
    return path.resolve()


def require_dir(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise AuditError(f"Missing {label}: {path}")
    return path.resolve()


def ensure_under(path: Path, root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AuditError(f"{label} escapes project root: {resolved}") from exc
    return resolved


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(
        payload, indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n")


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.16g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def atomic_tsv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        fields = ordered
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(fields), delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: fmt(row.get(key)) for key in fields})
    os.replace(tmp, path)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f, delimiter="\t")]


def resolve_current(version_root: Path, pointer_name: str) -> Path:
    pointer = require_file(version_root / pointer_name, pointer_name)
    target = Path(pointer.read_text(encoding="utf-8").strip())
    if not target.is_absolute():
        target = version_root / target
    return require_dir(target, f"target of {pointer_name}")


def find_unique(base: Path, patterns: Sequence[str], label: str) -> Path:
    found: set[Path] = set()
    for pattern in patterns:
        for path in base.glob(pattern):
            if path.is_file():
                found.add(path.resolve())
    ordered = sorted(found)
    if len(ordered) != 1:
        raise AuditError(
            f"Expected one {label} under {base}; found {len(ordered)}: {ordered}"
        )
    return ordered[0]


def parse_ints(text: str) -> tuple[int, ...]:
    return tuple(int(x.strip()) for x in str(text).split(",") if x.strip())


def parse_float(row: Mapping[str, str], key: str) -> float:
    text = str(row.get(key, "")).strip()
    if not text:
        raise AuditError(f"Missing table value {key}")
    return float(text)


def parse_cfg(path: Path) -> CFGFrame:
    text = path.read_text(encoding="utf-8", errors="strict")
    blocks = re.findall(r"(?s)BEGIN_CFG(.*?)END_CFG", text)
    if len(blocks) != 1:
        raise AuditError(f"Expected one CFG block in {path}; found {len(blocks)}")
    lines = blocks[0].splitlines()
    size: int | None = None
    cell = np.eye(3, dtype=float)
    atoms: list[Atom] = []
    features: dict[str, str] = {}
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "Size":
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            size = int(float(lines[i].strip()))
        elif s == "Supercell":
            rows = []
            for _ in range(3):
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                rows.append([float(x) for x in lines[i].split()[:3]])
            cell = np.asarray(rows, dtype=float)
        elif s.startswith("AtomData:"):
            if size is None:
                raise AuditError(f"AtomData before Size in {path}")
            headers = s.split(":", 1)[1].split()
            col = {name: idx for idx, name in enumerate(headers)}
            required = {"id", "type", "cartes_x", "cartes_y", "cartes_z"}
            if not required.issubset(col):
                raise AuditError(f"Unsupported CFG columns in {path}: {headers}")
            atoms = []
            while len(atoms) < size:
                i += 1
                if i >= len(lines):
                    raise AuditError(f"Truncated AtomData in {path}")
                row = lines[i].strip()
                if not row:
                    continue
                values = row.split()
                atom_type = int(float(values[col["type"]]))
                if atom_type not in MLIP_TO_ELEMENT:
                    raise AuditError(f"Unknown MLIP type {atom_type} in {path}")
                atoms.append(Atom(
                    atom_id=int(float(values[col["id"]])),
                    atom_type=atom_type,
                    element=MLIP_TO_ELEMENT[atom_type],
                    position=(
                        float(values[col["cartes_x"]]),
                        float(values[col["cartes_y"]]),
                        float(values[col["cartes_z"]]),
                    ),
                ))
        elif s.startswith("Feature"):
            parts = s.split(maxsplit=2)
            if len(parts) >= 2:
                features[parts[1]] = parts[2] if len(parts) == 3 else ""
        i += 1
    if size != 9 or len(atoms) != 9:
        raise AuditError(f"Expected nine atoms in {path}; Size={size}, rows={len(atoms)}")
    return CFGFrame(path.resolve(), atoms, cell, features)


def paths_for_project(root: Path) -> dict[str, Path]:
    v032 = resolve_current(
        require_dir(
            root / "09_strict_comparison/versions/v032_targeted_md_diagnostics",
            "v032 root",
        ),
        "CURRENT_TARGETED_MD_DIAGNOSTICS.txt",
    )
    v032d = resolve_current(
        require_dir(
            root / "09_strict_comparison/versions/v032_selection_interface_diagnostic",
            "v032d root",
        ),
        "CURRENT_V032_SELECTION_INTERFACE_DIAGNOSTIC.txt",
    )
    return {
        "v032": v032,
        "v032d": v032d,
        "source": find_unique(
            v032d,
            (
                "provenance/step34c_v032_selection_interface_diagnostic_v032d.py",
                "**/step34c_v032_selection_interface_diagnostic_v032d.py",
            ),
            "final v032d source",
        ),
        "captured": find_unique(
            v032d,
            (
                "tables/captured_break_configurations_v032d.tsv",
                "**/captured_break_configurations_v032d.tsv",
            ),
            "captured-break table",
        ),
        "offline": require_dir(
            v032d / "offline_exact_grades", "offline_exact_grades"
        ),
    }


def offline_cfg(offline: Path, logical_name: str) -> Path:
    return find_unique(
        require_dir(offline / logical_name, logical_name),
        ("geometry.cfg", "**/geometry.cfg"),
        f"{logical_name}/geometry.cfg",
    )


def _node_call_name(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def _safe_static_expression(node: ast.AST | None) -> bool:
    """Return True only for side-effect-free top-level constant expressions."""
    if node is None:
        return True
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, ast.Attribute):
        return _safe_static_expression(node.value)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_safe_static_expression(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            _safe_static_expression(key) and _safe_static_expression(value)
            for key, value in zip(node.keys, node.values)
        )
    if isinstance(node, ast.UnaryOp):
        return _safe_static_expression(node.operand)
    if isinstance(node, ast.BinOp):
        return (
            _safe_static_expression(node.left)
            and _safe_static_expression(node.right)
        )
    if isinstance(node, ast.BoolOp):
        return all(_safe_static_expression(value) for value in node.values)
    if isinstance(node, ast.Compare):
        return (
            _safe_static_expression(node.left)
            and all(_safe_static_expression(value) for value in node.comparators)
        )
    if isinstance(node, ast.IfExp):
        return all(
            _safe_static_expression(value)
            for value in (node.test, node.body, node.orelse)
        )
    if isinstance(node, ast.Subscript):
        return (
            _safe_static_expression(node.value)
            and _safe_static_expression(node.slice)
        )
    if isinstance(node, ast.Slice):
        return all(
            _safe_static_expression(value)
            for value in (node.lower, node.upper, node.step)
        )
    if isinstance(node, (ast.JoinedStr, ast.FormattedValue)):
        return all(_safe_static_expression(child) for child in ast.iter_child_nodes(node))
    # Calls, comprehensions, lambdas, awaits and generators are excluded.
    return False


def _assignment_names(node: ast.AST) -> set[str]:
    targets: list[ast.AST] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    names: set[str] = set()
    for target in targets:
        for child in ast.walk(target):
            if isinstance(child, ast.Name):
                names.add(child.id)
    return names


def source_ast_audit(source_path: Path) -> dict[str, Any]:
    """
    Inventory the frozen module without requiring it to be import-safe.

    Non-definition top-level expressions are recorded as excluded executable
    nodes. They are not evidence of a damaged source file and are never run by
    the sanitized oracle module.
    """
    source = source_path.read_text(encoding="utf-8", errors="strict")
    tree = ast.parse(source)
    top_level: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    static_assignments: list[dict[str, Any]] = []

    for node in tree.body:
        record = {
            "node_type": type(node).__name__,
            "line": getattr(node, "lineno", None),
        }
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            record["sanitized_action"] = "INCLUDE_IMPORT"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            record["sanitized_action"] = "INCLUDE_FUNCTION_IF_DEPENDENCY"
            record["name"] = node.name
        elif isinstance(node, ast.ClassDef):
            record["sanitized_action"] = "INCLUDE_CLASS_IF_DEPENDENCY"
            record["name"] = node.name
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            safe = _safe_static_expression(value)
            record["names"] = sorted(_assignment_names(node))
            record["static_safe"] = safe
            record["sanitized_action"] = (
                "INCLUDE_STATIC_ASSIGNMENT" if safe else "EXCLUDE_EXECUTABLE_ASSIGNMENT"
            )
            static_assignments.append(record.copy())
            if not safe:
                excluded.append(record.copy())
        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            record["sanitized_action"] = "INCLUDE_MODULE_DOCSTRING"
        else:
            record["sanitized_action"] = "EXCLUDE_TOP_LEVEL_EXECUTION"
            try:
                record["source"] = ast.unparse(node)[:1000]
            except Exception:
                record["source"] = ""
            excluded.append(record.copy())
        top_level.append(record)

    return {
        "source": source,
        "tree": tree,
        "unsafe": [],
        "excluded": excluded,
        "static_assignments": static_assignments,
        "top_level": top_level,
    }


def _loaded_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }


def _definition_dependency_closure(
    tree: ast.Module,
    root_definition: str,
) -> tuple[set[str], dict[str, ast.AST]]:
    definitions: dict[str, ast.AST] = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    if root_definition not in definitions:
        raise AuditError(f"Missing oracle definition: {root_definition}")
    required = {root_definition}
    queue = [root_definition]
    while queue:
        current = queue.pop()
        for name in sorted(_loaded_names(definitions[current])):
            if name in definitions and name not in required:
                required.add(name)
                queue.append(name)
    return required, definitions


def _import_bound_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.add(alias.asname or alias.name.split(".", 1)[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            if alias.name == "*":
                names.add("*")
            else:
                names.add(alias.asname or alias.name)
    return names


def _top_level_symbol_tables(tree: ast.Module) -> dict[str, Any]:
    definitions: dict[str, ast.AST] = {}
    assignments: dict[str, ast.AST] = {}
    imports: dict[str, ast.AST] = {}
    star_imports: list[ast.AST] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for name in _assignment_names(node):
                assignments[name] = node
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound = _import_bound_names(node)
            if "*" in bound:
                star_imports.append(node)
            for name in bound - {"*"}:
                imports[name] = node
    return {
        "definitions": definitions,
        "assignments": assignments,
        "imports": imports,
        "star_imports": star_imports,
    }


def _minimal_global_dependency_plan(
    tree: ast.Module,
    required_definitions: set[str],
) -> dict[str, Any]:
    """
    Resolve only module globals actually referenced by the oracle closure.

    v002 included every syntactically static assignment in the frozen module.
    That was too broad: an unrelated static f-string referenced STAMP, while
    the executable STAMP initializer was correctly excluded. The result was a
    construction-time NameError even though STAMP was not part of the
    canonicalizer dependency graph.

    v004 starts from the exact function/class closure and recursively selects
    only referenced imports and side-effect-free assignments. Unsafe required
    assignments are reported explicitly and never executed.
    """
    symbols = _top_level_symbol_tables(tree)
    definitions: dict[str, ast.AST] = symbols["definitions"]
    assignments: dict[str, ast.AST] = symbols["assignments"]
    imports: dict[str, ast.AST] = symbols["imports"]

    needed_names: set[str] = set()
    for name in required_definitions:
        needed_names.update(_loaded_names(definitions[name]))

    selected_assignment_nodes: set[int] = set()
    selected_assignments: list[ast.AST] = []
    selected_import_nodes: set[int] = set()
    selected_imports: list[ast.AST] = []
    unsafe_required_assignments: list[dict[str, Any]] = []
    resolution_rows: list[dict[str, Any]] = []

    queue = list(sorted(needed_names))
    visited: set[str] = set()
    while queue:
        name = queue.pop(0)
        if name in visited:
            continue
        visited.add(name)

        if name in required_definitions:
            resolution_rows.append({
                "name": name,
                "resolution": "required_definition",
            })
            continue
        if name in imports:
            node = imports[name]
            if id(node) not in selected_import_nodes:
                selected_import_nodes.add(id(node))
                selected_imports.append(node)
            resolution_rows.append({
                "name": name,
                "resolution": "selected_import",
                "line": getattr(node, "lineno", None),
            })
            continue
        if name in assignments:
            node = assignments[name]
            if not _safe_static_expression(node.value):
                unsafe_required_assignments.append({
                    "name": name,
                    "line": getattr(node, "lineno", None),
                    "expression": ast.unparse(node.value),
                    "reason": "required_assignment_contains_execution",
                })
                resolution_rows.append({
                    "name": name,
                    "resolution": "unsafe_required_assignment",
                    "line": getattr(node, "lineno", None),
                })
                continue
            if id(node) not in selected_assignment_nodes:
                selected_assignment_nodes.add(id(node))
                selected_assignments.append(node)
                dependencies = sorted(_loaded_names(node.value))
                queue.extend(dep for dep in dependencies if dep not in visited)
            resolution_rows.append({
                "name": name,
                "resolution": "selected_static_assignment",
                "line": getattr(node, "lineno", None),
            })
            continue
        if name in dir(builtins) or name in {
            "__name__", "__file__", "__package__", "__annotations__"
        }:
            resolution_rows.append({
                "name": name,
                "resolution": "builtin_or_module_special",
            })
            continue
        # Most remaining names are function locals. Record them, but do not
        # fabricate a module global or treat them as an error.
        resolution_rows.append({
            "name": name,
            "resolution": "not_a_known_top_level_symbol",
        })

    # Preserve original source order for exact assignment/import semantics.
    order = {id(node): index for index, node in enumerate(tree.body)}
    selected_imports.sort(key=lambda node: order[id(node)])
    selected_assignments.sort(key=lambda node: order[id(node)])

    return {
        "selected_imports": selected_imports,
        "selected_assignments": selected_assignments,
        "unsafe_required_assignments": unsafe_required_assignments,
        "resolution_rows": resolution_rows,
        "initial_loaded_names": sorted(needed_names),
    }


def _definition_time_loaded_names(node: ast.AST) -> set[str]:
    """Names evaluated while a definition statement itself is executed."""
    expressions: list[ast.AST] = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        expressions.extend(node.args.defaults)
        expressions.extend(value for value in node.args.kw_defaults if value is not None)
        if node.returns is not None:
            expressions.append(node.returns)
        for argument in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        ):
            if argument.annotation is not None:
                expressions.append(argument.annotation)
        if node.args.vararg and node.args.vararg.annotation is not None:
            expressions.append(node.args.vararg.annotation)
        if node.args.kwarg and node.args.kwarg.annotation is not None:
            expressions.append(node.args.kwarg.annotation)
    elif isinstance(node, ast.ClassDef):
        expressions.extend(node.bases)
        expressions.extend(keyword.value for keyword in node.keywords)
    loaded: set[str] = set()
    for expression in expressions:
        loaded.update(_loaded_names(expression))
    return loaded


def build_sanitized_oracle_module(
    source_path: Path,
    root: Path,
    audit: Mapping[str, Any],
    canonical_function: str,
) -> tuple[Any, dict[str, Any], str]:
    """
    Compile a minimal oracle-only module from the exact frozen AST.

    Included:
    - the module docstring and future imports;
    - only imports referenced by the exact oracle definition closure;
    - only side-effect-free assignments referenced by that closure;
    - the canonicalizer and its transitive top-level function/class helpers.

    Excluded:
    - every unrelated assignment, including the STAMP-dependent path state that
      caused the v002 construction failure;
    - every top-level expression, main guard, loop, and executable assignment;
    - unrelated function/class definitions.
    """
    tree: ast.Module = audit["tree"]
    required, definitions = _definition_dependency_closure(
        tree, canonical_function
    )
    plan = _minimal_global_dependency_plan(tree, required)

    if plan["unsafe_required_assignments"]:
        raise AuditError(
            "Oracle closure requires executable top-level assignment(s), which "
            "cannot be replayed safely: "
            + json.dumps(plan["unsafe_required_assignments"], sort_keys=True)
        )

    selected_import_ids = {id(node) for node in plan["selected_imports"]}
    selected_assignment_ids = {id(node) for node in plan["selected_assignments"]}

    body: list[ast.stmt] = []
    included_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []

    # First module docstring only.
    for node in tree.body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            body.append(copy.deepcopy(node))
            included_rows.append({
                "line": getattr(node, "lineno", None),
                "node_type": "Expr",
                "reason": "module_docstring",
            })
            break

    # Future imports must precede all ordinary statements.
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            body.append(copy.deepcopy(node))
            included_rows.append({
                "line": getattr(node, "lineno", None),
                "node_type": "ImportFrom",
                "reason": "future_import",
                "bound_names": sorted(_import_bound_names(node)),
            })

    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if id(node) in selected_import_ids:
                body.append(copy.deepcopy(node))
                included_rows.append({
                    "line": getattr(node, "lineno", None),
                    "node_type": type(node).__name__,
                    "reason": "minimal_required_import",
                    "bound_names": sorted(_import_bound_names(node)),
                })
            else:
                excluded_rows.append({
                    "line": getattr(node, "lineno", None),
                    "node_type": type(node).__name__,
                    "reason": "unreferenced_import_excluded",
                    "bound_names": sorted(_import_bound_names(node)),
                })
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            if id(node) in selected_assignment_ids:
                body.append(copy.deepcopy(node))
                included_rows.append({
                    "line": getattr(node, "lineno", None),
                    "node_type": type(node).__name__,
                    "reason": "minimal_required_static_assignment",
                    "names": sorted(_assignment_names(node)),
                    "loaded_names": sorted(_loaded_names(node.value)),
                })
            else:
                excluded_rows.append({
                    "line": getattr(node, "lineno", None),
                    "node_type": type(node).__name__,
                    "reason": "unreferenced_assignment_excluded",
                    "names": sorted(_assignment_names(node)),
                    "static_safe": _safe_static_expression(node.value),
                })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in required:
                cloned = copy.deepcopy(node)
                decorators = list(getattr(cloned, "decorator_list", []))
                if decorators:
                    excluded_rows.append({
                        "line": getattr(node, "lineno", None),
                        "node_type": type(node).__name__,
                        "name": node.name,
                        "reason": "decorators_stripped",
                        "decorators": [ast.unparse(value) for value in decorators],
                    })
                    cloned.decorator_list = []
                body.append(cloned)
                included_rows.append({
                    "line": getattr(node, "lineno", None),
                    "node_type": type(node).__name__,
                    "name": node.name,
                    "reason": "oracle_dependency",
                    "definition_time_loaded_names": sorted(
                        _definition_time_loaded_names(node)
                    ),
                })
            else:
                excluded_rows.append({
                    "line": getattr(node, "lineno", None),
                    "node_type": type(node).__name__,
                    "name": node.name,
                    "reason": "unrelated_definition",
                })
        elif not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            excluded_rows.append({
                "line": getattr(node, "lineno", None),
                "node_type": type(node).__name__,
                "reason": "top_level_execution_excluded",
            })

    sanitized_tree = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(sanitized_tree)
    sanitized_source = ast.unparse(sanitized_tree) + "\n"

    module_name = "_v032d_cfgblock_source_oracle_hashlocked"
    module = types.ModuleType(module_name)
    module.__file__ = str(source_path)
    module.__package__ = ""
    module.__dict__["__builtins__"] = builtins.__dict__

    sys.path.insert(0, str(root / "scripts"))
    sys.path.insert(0, str(source_path.parent))
    try:
        code = compile(
            sanitized_tree,
            filename=str(source_path) + "::<minimal_closure_oracle>",
            mode="exec",
        )
        exec(code, module.__dict__, module.__dict__)
    except Exception as exc:
        provided_names = sorted(
            name for name in module.__dict__ if not name.startswith("__")
        )
        raise AuditError(
            "CFG-block oracle module construction failed: "
            f"{type(exc).__name__}: {exc}; "
            f"provided_names={provided_names}; "
            f"selected_assignments="
            f"{[sorted(_assignment_names(node)) for node in plan['selected_assignments']]}"
        ) from exc
    finally:
        for value in (str(source_path.parent), str(root / "scripts")):
            try:
                sys.path.remove(value)
            except ValueError:
                pass

    if not hasattr(module, canonical_function):
        raise AuditError(
            f"CFG-block module lacks canonicalizer {canonical_function}"
        )

    metadata = {
        "canonical_function": canonical_function,
        "required_definitions": sorted(required),
        "selected_imports": [
            {
                "line": getattr(node, "lineno", None),
                "source": ast.unparse(node),
                "bound_names": sorted(_import_bound_names(node)),
            }
            for node in plan["selected_imports"]
        ],
        "selected_assignments": [
            {
                "line": getattr(node, "lineno", None),
                "source": ast.unparse(node),
                "names": sorted(_assignment_names(node)),
                "loaded_names": sorted(_loaded_names(node.value)),
            }
            for node in plan["selected_assignments"]
        ],
        "unsafe_required_assignments": plan["unsafe_required_assignments"],
        "global_resolution": plan["resolution_rows"],
        "initial_loaded_names": plan["initial_loaded_names"],
        "included": included_rows,
        "excluded": excluded_rows,
        "sanitized_source_sha256": hashlib.sha256(
            sanitized_source.encode("utf-8")
        ).hexdigest(),
    }
    return module, metadata, sanitized_source

def function_source(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def discover_functions(source: str, tree: ast.Module) -> dict[str, Any]:
    function_nodes = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    inventory: list[dict[str, Any]] = []
    canonical_candidates: list[tuple[int, str]] = []
    table_candidates: list[tuple[int, str]] = []
    kabsch_candidates: list[tuple[int, str]] = []

    for name, node in function_nodes.items():
        segment = function_source(source, node)
        lower = segment.lower()
        keywords = [
            keyword for keyword in (
                "species_assignment",
                "pair_distance_max_abs_delta_ang",
                "canonical_order_zero_based",
                "break_vs_endpoint_max_abs_ang",
                "break_vs_endpoint_kabsch_rmsd_ang",
                "np.linalg.svd",
            )
            if keyword.lower() in lower
        ]
        inventory.append({
            "function": name,
            "line_start": node.lineno,
            "line_end": getattr(node, "end_lineno", node.lineno),
            "arguments": ",".join(arg.arg for arg in node.args.args),
            "keyword_hits": ",".join(keywords),
            "source_sha256": hashlib.sha256(segment.encode()).hexdigest(),
        })
        span = getattr(node, "end_lineno", node.lineno) - node.lineno
        if (
            "species_assignment" in lower
            and "pair_distance_max_abs_delta_ang" in lower
        ):
            canonical_candidates.append((span, name))
        if (
            "break_vs_endpoint_max_abs_ang" in lower
            and "break_vs_endpoint_kabsch_rmsd_ang" in lower
        ):
            table_candidates.append((span, name))
        if "np.linalg.svd" in lower:
            kabsch_candidates.append((span, name))

    if not canonical_candidates:
        raise AuditError(
            "Could not identify canonicalization function from exact source"
        )
    canonical_candidates.sort()
    table_candidates.sort()
    kabsch_candidates.sort()
    return {
        "nodes": function_nodes,
        "inventory": inventory,
        "canonical_function": canonical_candidates[0][1],
        "canonical_candidates": [name for _, name in canonical_candidates],
        "table_function": (
            table_candidates[0][1] if table_candidates else None
        ),
        "table_candidates": [name for _, name in table_candidates],
        "kabsch_candidates": [name for _, name in kabsch_candidates],
    }


def import_hash_locked_module(
    source_path: Path,
    root: Path,
    audit: Mapping[str, Any],
    canonical_function: str,
) -> tuple[Any, dict[str, Any], str]:
    return build_sanitized_oracle_module(
        source_path=source_path,
        root=root,
        audit=audit,
        canonical_function=canonical_function,
    )

def has_any(name: str, words: Sequence[str]) -> bool:
    lower = name.lower()
    return any(word in lower for word in words)


class OracleCFGBlockAdapter(types.SimpleNamespace):
    """Non-executing structural adapter for the frozen source CFGBlock API."""

    def copy(self) -> "OracleCFGBlockAdapter":
        return copy.deepcopy(self)


def make_oracle_cfgblock(frame: CFGFrame, role: str) -> OracleCFGBlockAdapter:
    """
    Materialize the attribute contract used by the exact frozen canonicalizer.

    Python type annotations are not runtime-enforced.  Passing this structural
    object avoids importing or constructing the original top-level CFGBlock
    class while preserving the exact arrays read from the frozen CFG artifact.
    No coordinates, types, IDs, or cell values are changed.
    """
    positions = np.asarray(frame.positions(), dtype=float).copy()
    atom_types = np.asarray(frame.types(), dtype=int).copy()
    atom_ids = np.asarray(frame.ids(), dtype=int).copy()
    supercell = np.asarray(frame.cell, dtype=float).copy()
    elements = np.asarray(frame.elements(), dtype=object)
    zero_forces = np.zeros_like(positions)

    adapter = OracleCFGBlockAdapter(
        # Exact/common frozen-source field spellings.
        size=len(frame.atoms),
        natoms=len(frame.atoms),
        n_atoms=len(frame.atoms),
        atom_count=len(frame.atoms),
        supercell=supercell,
        cell=supercell,
        cell_matrix=supercell,
        lattice=supercell,
        ids=atom_ids,
        atom_ids=atom_ids,
        types=atom_types,
        atom_types=atom_types,
        elements=elements,
        species=elements,
        positions=positions,
        cartes=positions,
        coordinates=positions,
        coords=positions,
        forces=zero_forces,
        energy=float("nan"),
        features=dict(frame.features),
        path=frame.path,
        source_path=frame.path,
        label=role,
        role=role,
    )
    return adapter


def bind_canonicalizer(
    function: Any,
    raw: CFGFrame,
    reference: CFGFrame,
    trajectory_id: str,
    side: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Bind the exact frozen signature.

    The discovered source signature is currently
    ``(block: CFGBlock, endpoint: CFGBlock, label: str)``.  These names receive
    structural CFGBlock adapters created directly from the two frozen CFG
    files.  The broader semantic fallbacks remain only for future hash-locked
    source variants and are recorded explicitly in the binding table.
    """
    signature = inspect.signature(function)
    raw_positions = raw.positions()
    raw_types = raw.types()
    raw_elements = np.asarray(raw.elements(), dtype=object)
    ref_positions = reference.positions()
    ref_types = reference.types()
    ref_elements = np.asarray(reference.elements(), dtype=object)
    raw_block = make_oracle_cfgblock(raw, f"{trajectory_id}:raw_break")
    endpoint_block = make_oracle_cfgblock(
        reference, f"{trajectory_id}:endpoint_{side}"
    )
    pair_matrix = None

    kwargs: dict[str, Any] = {}
    decisions: list[dict[str, Any]] = []
    unresolved: list[str] = []

    for parameter in signature.parameters.values():
        name = parameter.name
        lower = name.lower()
        value: Any = None
        source_label: str | None = None

        # Exact frozen v032d parameter contract.  These checks precede all
        # token-based fallbacks because ``endpoint`` is an object, not an array.
        if lower in {"block", "cfg_block", "mobile_block", "raw_block"}:
            value, source_label = raw_block, "raw_CFGBlock_adapter"
        elif lower in {
            "endpoint", "endpoint_block", "reference_block", "ref_block"
        }:
            value, source_label = endpoint_block, "endpoint_CFGBlock_adapter"
        elif lower in {"label", "case_label", "name"}:
            value, source_label = trajectory_id, "trajectory_label"
        else:
            is_ref = any(token in lower for token in (
                "reference", "ref_", "target", "endpoint", "canonical"
            ))

            if has_any(lower, TYPE_WORDS):
                if is_ref:
                    value, source_label = ref_types, "reference_types"
                else:
                    value, source_label = raw_types, "raw_types"
            elif has_any(lower, ELEMENT_WORDS):
                if is_ref:
                    value, source_label = ref_elements, "reference_elements"
                else:
                    value, source_label = raw_elements, "raw_elements"
            elif has_any(lower, POSITION_WORDS) or lower in {
                "reference", "mobile", "raw", "positions"
            }:
                if is_ref or lower == "reference":
                    value, source_label = ref_positions, "reference_positions"
                else:
                    value, source_label = raw_positions, "raw_positions"
            elif any(token in lower for token in (
                "supercell", "cell_matrix", "lattice"
            )):
                value, source_label = raw.cell, "raw_cell"
            elif lower in {"cell", "box", "supercell"}:
                value, source_label = raw.cell, "raw_cell"
            elif "box_length" in lower or "cell_length" in lower:
                value, source_label = np.diag(raw.cell), "cell_diagonal"
            elif "pair" in lower and "matrix" in lower:
                if pair_matrix is None:
                    pair_matrix = np.linalg.norm(
                        ref_positions[:, None, :] - ref_positions[None, :, :],
                        axis=2,
                    )
                value, source_label = pair_matrix, "reference_pair_matrix"
            elif lower in {"trajectory_id", "case_id", "run_id"}:
                value, source_label = trajectory_id, "trajectory_id"
            elif lower == "side":
                value, source_label = side, "side"
            elif parameter.default is not inspect._empty:
                decisions.append({
                    "parameter": name,
                    "annotation": str(parameter.annotation),
                    "binding": "DEFAULT",
                    "python_type": "",
                    "shape": "",
                })
                continue
            else:
                unresolved.append(name)
                continue

        kwargs[name] = value
        decisions.append({
            "parameter": name,
            "annotation": str(parameter.annotation),
            "binding": source_label,
            "python_type": type(value).__name__,
            "shape": getattr(value, "shape", ""),
            "value_preview": (
                value if isinstance(value, (str, int, float)) else ""
            ),
            "adapter_attributes": (
                sorted(value.__dict__) if isinstance(value, OracleCFGBlockAdapter)
                else ""
            ),
        })

    if unresolved:
        raise AuditError(
            f"Unresolved required canonicalizer parameters {unresolved}; "
            f"signature={signature}"
        )

    result = function(**kwargs)
    return {
        "result": result,
        "signature": str(signature),
        "kwargs": kwargs,
    }, {
        "signature": str(signature),
        "decisions": decisions,
    }

def flatten_object(
    value: Any,
    prefix: str = "result",
    depth: int = 0,
    seen: set[int] | None = None,
) -> list[dict[str, Any]]:
    if seen is None:
        seen = set()
    if depth > 7:
        return [{"path": prefix, "kind": "depth_limit", "value": ""}]
    identity = id(value)
    if isinstance(value, (dict, list, tuple, np.ndarray)) and identity in seen:
        return [{"path": prefix, "kind": "cycle", "value": ""}]
    if isinstance(value, (dict, list, tuple, np.ndarray)):
        seen.add(identity)

    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            rows.extend(flatten_object(
                child, f"{prefix}.{key}", depth + 1, seen
            ))
    elif isinstance(value, np.ndarray):
        if value.ndim == 0:
            rows.append({
                "path": prefix, "kind": "scalar",
                "value": float(value), "shape": value.shape,
            })
        else:
            rows.append({
                "path": prefix, "kind": "ndarray",
                "value": "", "shape": tuple(value.shape),
                "dtype": str(value.dtype),
                "_object": value,
            })
    elif isinstance(value, (list, tuple)):
        # Preserve numeric vectors as a single leaf; recurse otherwise.
        try:
            array = np.asarray(value)
            if array.dtype.kind in "iuf" and array.ndim in (1, 2):
                rows.append({
                    "path": prefix, "kind": "numeric_sequence",
                    "value": "", "shape": tuple(array.shape),
                    "dtype": str(array.dtype),
                    "_object": array,
                })
            else:
                raise ValueError
        except Exception:
            for index, child in enumerate(value):
                rows.extend(flatten_object(
                    child, f"{prefix}[{index}]", depth + 1, seen
                ))
    elif isinstance(value, (int, float, np.integer, np.floating)):
        rows.append({
            "path": prefix, "kind": "scalar",
            "value": float(value), "shape": "",
        })
    elif isinstance(value, str):
        rows.append({
            "path": prefix, "kind": "string",
            "value": value, "shape": "",
        })
    elif value is None:
        rows.append({
            "path": prefix, "kind": "none",
            "value": "", "shape": "",
        })
    else:
        rows.append({
            "path": prefix, "kind": type(value).__name__,
            "value": repr(value)[:500], "shape": "",
        })
    return rows


def kabsch_component_rms(moving: np.ndarray, reference: np.ndarray) -> float:
    p = moving - moving.mean(axis=0)
    q = reference - reference.mean(axis=0)
    u, _, vt = np.linalg.svd(p.T @ q)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    aligned = p @ rotation
    return float(np.sqrt(np.mean((aligned - q) ** 2)))


def geometry_values(
    positions: np.ndarray,
    reference: np.ndarray,
) -> dict[str, float]:
    diff = positions - reference
    pair = 0.0
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            pair = max(
                pair,
                abs(
                    np.linalg.norm(positions[i] - positions[j])
                    - np.linalg.norm(reference[i] - reference[j])
                ),
            )
    o1, h, o2 = positions[0], positions[1], positions[7]
    return {
        "max_abs": float(np.max(np.abs(diff))),
        "component_rms": float(np.sqrt(np.mean(diff ** 2))),
        "atom_rms": float(np.sqrt(np.mean(np.sum(diff ** 2, axis=1)))),
        "kabsch_component_rms": kabsch_component_rms(positions, reference),
        "pair_distance_max_delta": float(pair),
        "qpt": float(np.linalg.norm(o1 - h) - np.linalg.norm(o2 - h)),
        "roo": float(np.linalg.norm(o1 - o2)),
    }


def expected_metrics(row: Mapping[str, str]) -> dict[str, float]:
    return {
        "max_abs": parse_float(row, "break_vs_endpoint_max_abs_ang"),
        "component_rms": parse_float(row, "break_vs_endpoint_rms_ang"),
        "kabsch": parse_float(
            row, "break_vs_endpoint_kabsch_rmsd_ang"
        ),
        "pair_distance_max_delta": parse_float(
            row,
            "break_vs_endpoint_pair_distance_max_abs_delta_ang",
        ),
        "qpt": parse_float(row, "break_qpt_ang"),
        "roo": parse_float(row, "break_roo_ang"),
    }


def exact_match(value: float, expected: float) -> bool:
    return abs(value - expected) <= TOL


def inspect_oracle_result(
    result: Any,
    reference: CFGFrame,
    expected: Mapping[str, float],
    recorded_order: tuple[int, ...],
    trajectory_id: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    leaves = flatten_object(result)
    leaf_rows: list[dict[str, Any]] = []
    match_rows: list[dict[str, Any]] = []
    arrays: list[tuple[str, np.ndarray]] = []
    scalars: list[tuple[str, float]] = []
    orders: list[tuple[str, tuple[int, ...]]] = []

    for leaf in leaves:
        obj = leaf.pop("_object", None)
        row = {"trajectory_id": trajectory_id, **leaf}
        leaf_rows.append(row)
        if obj is not None:
            arr = np.asarray(obj)
            if arr.shape == (9, 3) and arr.dtype.kind in "iuf":
                arrays.append((leaf["path"], arr.astype(float)))
            elif arr.shape == (9,) and arr.dtype.kind in "iu":
                orders.append((
                    leaf["path"], tuple(int(x) for x in arr.tolist())
                ))
        elif leaf["kind"] == "scalar":
            scalars.append((leaf["path"], float(leaf["value"])))

    reference_positions = reference.positions()
    array_evidence: list[dict[str, Any]] = []
    for path, positions in arrays:
        values = geometry_values(positions, reference_positions)
        record: dict[str, Any] = {
            "trajectory_id": trajectory_id,
            "array_path": path,
            **values,
        }
        for metric, value in values.items():
            expected_key = (
                "kabsch" if metric == "kabsch_component_rms" else metric
            )
            if expected_key in expected:
                record[f"{metric}_expected"] = expected[expected_key]
                record[f"{metric}_residual"] = (
                    value - expected[expected_key]
                )
                record[f"{metric}_pass"] = exact_match(
                    value, expected[expected_key]
                )
        array_evidence.append(record)

    for path, value in scalars:
        for metric, target in expected.items():
            if exact_match(value, target):
                match_rows.append({
                    "trajectory_id": trajectory_id,
                    "leaf_path": path,
                    "leaf_value": value,
                    "matched_metric": metric,
                    "table_value": target,
                    "residual": value - target,
                })

    order_matches = [
        {"path": path, "order": order}
        for path, order in orders if order == recorded_order
    ]

    # Determine whether one exact source-returned array explains the position
    # metrics simultaneously. This is not a free scientific fit: all arrays
    # come from the one exact source call with one fixed reference.
    exact_array_paths = []
    for record in array_evidence:
        required = (
            record.get("max_abs_pass") is True,
            record.get("component_rms_pass") is True,
            record.get("pair_distance_max_delta_pass") is True,
            record.get("qpt_pass") is True,
            record.get("roo_pass") is True,
        )
        if all(required):
            exact_array_paths.append(record["array_path"])

    scalar_match_by_metric: dict[str, list[str]] = {}
    for metric in expected:
        scalar_match_by_metric[metric] = [
            row["leaf_path"] for row in match_rows
            if row["matched_metric"] == metric
        ]

    summary = {
        "trajectory_id": trajectory_id,
        "return_leaf_count": len(leaf_rows),
        "returned_array_count": len(arrays),
        "returned_scalar_count": len(scalars),
        "returned_order_count": len(orders),
        "recorded_order_match_paths": [
            row["path"] for row in order_matches
        ],
        "recorded_order_reproduced": bool(order_matches),
        "exact_position_array_paths": exact_array_paths,
        "exact_position_array_found": bool(exact_array_paths),
        "scalar_match_paths_by_metric": scalar_match_by_metric,
        "source_scalar_kabsch_match_found": bool(
            scalar_match_by_metric["kabsch"]
        ),
        "source_scalar_pair_match_found": bool(
            scalar_match_by_metric["pair_distance_max_delta"]
        ),
    }
    return leaf_rows, array_evidence + match_rows, summary


def extract_source_fragments(
    source: str,
    discovery: Mapping[str, Any],
) -> dict[str, str]:
    fragments: dict[str, str] = {}
    for role, name in (
        ("canonical", discovery["canonical_function"]),
        ("table", discovery["table_function"]),
    ):
        if name and name in discovery["nodes"]:
            fragments[role] = function_source(
                source, discovery["nodes"][name]
            )
    for index, name in enumerate(discovery["kabsch_candidates"], start=1):
        fragments[f"kabsch_{index:02d}_{name}"] = function_source(
            source, discovery["nodes"][name]
        )
    return fragments


def source_assignment_inventory(
    source: str,
    node: ast.AST | None,
) -> list[dict[str, Any]]:
    if node is None:
        return []
    rows: list[dict[str, Any]] = []
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Assign, ast.AnnAssign)):
            targets: list[str] = []
            if isinstance(sub, ast.Assign):
                targets = [ast.unparse(target) for target in sub.targets]
                value = sub.value
            else:
                targets = [ast.unparse(sub.target)]
                value = sub.value
            rhs = ast.unparse(value) if value is not None else ""
            if any(token in (" ".join(targets) + " " + rhs) for token in (
                "endpoint_max", "endpoint_rms", "endpoint_kabsch",
                "break_vs_endpoint", "canonical", "pair_distance",
            )):
                rows.append({
                    "line": getattr(sub, "lineno", None),
                    "targets": ",".join(targets),
                    "rhs": rhs,
                    "source_segment": ast.get_source_segment(source, sub) or "",
                })
    rows.sort(key=lambda row: (row["line"] or 0, row["targets"]))
    return rows


def classify(
    invocation_rows: Sequence[Mapping[str, Any]],
    oracle_summaries: Sequence[Mapping[str, Any]],
) -> str:
    if any(row["status"] != "PASS" for row in invocation_rows):
        return "SOURCE_ORACLE_INVOCATION_UNRESOLVED"
    order_ok = all(
        summary["recorded_order_reproduced"]
        for summary in oracle_summaries
    )
    position_ok = all(
        summary["exact_position_array_found"]
        for summary in oracle_summaries
    )
    kabsch_ok = all(
        summary["source_scalar_kabsch_match_found"]
        for summary in oracle_summaries
    )
    if order_ok and position_ok and kabsch_ok:
        return "EXACT_SOURCE_ORACLE_REPLAY_PASS"
    if order_ok and position_ok:
        return "SOURCE_ORACLE_POSITION_REPLAY_PASS_KABSCH_FIELD_UNRESOLVED"
    if order_ok:
        return "SOURCE_ORACLE_CANONICAL_ORDER_PASS_METRIC_FIELD_UNRESOLVED"
    return "SOURCE_ORACLE_RECORDED_ORDER_NOT_REPRODUCED"


def artifact(path: Path, role: str, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "role": role,
        "path": str(resolved),
        "relative_path": (
            str(resolved.relative_to(root))
            if resolved.is_relative_to(root) else ""
        ),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def checksums(attempt: Path) -> None:
    rows = []
    for path in sorted(attempt.rglob("*")):
        if path.is_file() and path.name != "checksums_v004.tsv":
            rows.append({
                "relative_path": str(path.relative_to(attempt)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    atomic_tsv(
        attempt / "checksums_v004.tsv",
        rows,
        ("relative_path", "size_bytes", "sha256"),
    )


def bundle(attempt: Path) -> Path:
    output = attempt / "v032d_source_oracle_replay_bundle_v004.tar.gz"
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(attempt.rglob("*")):
            if path.is_file() and path != output:
                archive.add(path, arcname=str(path.relative_to(attempt)))
    return output


def self_test() -> None:
    source = r'''
"""Synthetic source with a prohibited top-level call."""
from __future__ import annotations
import numpy as np
STATIC_SCALE = 2.0

def make_stamp():
    raise RuntimeError("STAMP_INITIALIZER_EXECUTED")

STAMP = make_stamp()
UNRELATED_STATIC_PATH = f"/tmp/{STAMP}/output"

def forbidden_side_effect():
    raise RuntimeError("TOP_LEVEL_SIDE_EFFECT_EXECUTED")

forbidden_side_effect()

def helper(x):
    return x * STATIC_SCALE / STATIC_SCALE

def canonical(raw_types, raw_positions, reference_types, reference):
    candidates = []
    candidates.append(("species_assignment", tuple(range(9))))
    positions = helper(raw_positions)
    return {
        "canonical_order_zero_based": tuple(range(9)),
        "positions": positions,
        "pair_distance_max_abs_delta_ang": 0.0,
        "kabsch_rmsd_ang": 0.0,
    }

if __name__ == "__main__":
    forbidden_side_effect()
'''
    tree = ast.parse(source)
    discovery = discover_functions(source, tree)
    if discovery["canonical_function"] != "canonical":
        raise AuditError("Function-discovery self-test failed")

    synthetic_audit = {
        "source": source,
        "tree": tree,
        "unsafe": [],
        "excluded": [],
        "top_level": [],
    }
    module, metadata, _ = build_sanitized_oracle_module(
        source_path=Path("/tmp/synthetic_v032d_oracle.py"),
        root=Path("/tmp"),
        audit=synthetic_audit,
        canonical_function="canonical",
    )
    ref = np.arange(27, dtype=float).reshape(9, 3)
    result = module.canonical(
        raw_types=np.zeros(9, dtype=int),
        raw_positions=ref,
        reference_types=np.zeros(9, dtype=int),
        reference=ref,
    )
    if not np.array_equal(result["positions"], ref):
        raise AuditError("Sanitized-module execution self-test failed")
    if "helper" not in metadata["required_definitions"]:
        raise AuditError("Dependency-closure self-test failed")
    selected_names = {
        name
        for row in metadata["selected_assignments"]
        for name in row["names"]
    }
    if "STATIC_SCALE" not in selected_names:
        raise AuditError("Required static assignment was not selected")
    if "STAMP" in selected_names or "UNRELATED_STATIC_PATH" in selected_names:
        raise AuditError("Unrelated STAMP-dependent assignment leaked into closure")
    if not any(
        row.get("reason") == "top_level_execution_excluded"
        for row in metadata["excluded"]
    ):
        raise AuditError("Top-level exclusion self-test failed")

    values = geometry_values(ref + 0.001, ref)
    if not math.isclose(values["max_abs"], 0.001, abs_tol=1e-14):
        raise AuditError("Geometry self-test failed")
    # Exact-signature structural binding regression.
    mock_raw = CFGFrame(
        path=Path("/tmp/raw.cfg"),
        atoms=[
            Atom(i + 1, [1, 0, 2, 1, 2, 0, 1, 0, 1][i],
                 MLIP_TO_ELEMENT[[1, 0, 2, 1, 2, 0, 1, 0, 1][i]],
                 tuple(ref[i]))
            for i in range(9)
        ],
        cell=np.eye(3) * 16.0,
        features={},
    )
    mock_endpoint = CFGFrame(
        path=Path("/tmp/endpoint.cfg"),
        atoms=[
            Atom(i + 1, [2, 1, 0, 1, 0, 1, 0, 2, 1][i],
                 MLIP_TO_ELEMENT[[2, 1, 0, 1, 0, 1, 0, 2, 1][i]],
                 tuple(ref[i]))
            for i in range(9)
        ],
        cell=np.eye(3) * 16.0,
        features={},
    )

    def exact_signature_mock(block: "CFGBlock", endpoint: "CFGBlock", label: str):
        assert isinstance(block, OracleCFGBlockAdapter)
        assert isinstance(endpoint, OracleCFGBlockAdapter)
        assert block.positions.shape == (9, 3)
        assert endpoint.supercell.shape == (3, 3)
        assert label == "T100_left"
        return {"label": label, "order": tuple(range(9))}

    mock_call, mock_binding = bind_canonicalizer(
        exact_signature_mock,
        mock_raw,
        mock_endpoint,
        "T100_left",
        "left",
    )
    if mock_call["result"]["label"] != "T100_left":
        raise AuditError("CFGBlock adapter binding regression failed")
    observed_bindings = {
        row["parameter"]: row["binding"]
        for row in mock_binding["decisions"]
    }
    expected_bindings = {
        "block": "raw_CFGBlock_adapter",
        "endpoint": "endpoint_CFGBlock_adapter",
        "label": "trajectory_label",
    }
    if observed_bindings != expected_bindings:
        raise AuditError(
            f"Unexpected exact-signature bindings: {observed_bindings}"
        )

    print("SELF_TEST=PASS")
    print("EXACT_CFGBLOCK_SIGNATURE_BINDING=PASS")
    print(f"CANONICAL_FUNCTION={discovery['canonical_function']}")
    print("CFGBLOCK_ADAPTER_STAMP_DEPENDENCY=EXCLUDED")
    print(f"DEPENDENCY_DEFINITIONS={','.join(metadata['required_definitions'])}")
    print("MINIMAL_GLOBAL_ASSIGNMENTS=" + ",".join(sorted(selected_names)))
    print(f"DIRECT_MAX_ABS_A={values['max_abs']:.12g}")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    root = require_dir(args.root.expanduser().resolve(), "project root")
    project = paths_for_project(root)
    source_path = project["source"]
    observed_sha = sha256_file(source_path)
    if observed_sha != EXPECTED_SOURCE_SHA256:
        raise AuditError(
            f"Source SHA mismatch: expected={EXPECTED_SOURCE_SHA256}; "
            f"observed={observed_sha}"
        )

    source_audit = source_ast_audit(source_path)
    discovery = discover_functions(
        source_audit["source"], source_audit["tree"]
    )
    fragments = extract_source_fragments(
        source_audit["source"], discovery
    )
    table_node = (
        discovery["nodes"].get(discovery["table_function"])
        if discovery["table_function"] else None
    )
    assignment_rows = source_assignment_inventory(
        source_audit["source"], table_node
    )

    captured = read_tsv(project["captured"])
    rows_by_id = {row["trajectory_id"]: row for row in captured}
    if tuple(sorted(rows_by_id)) != tuple(sorted(TRAJECTORIES)):
        raise AuditError(f"Unexpected trajectories: {sorted(rows_by_id)}")

    # Check all fixed inputs before importing the exact module.
    preflight_rows = []
    for trajectory_id in TRAJECTORIES:
        row = rows_by_id[trajectory_id]
        raw_path = require_file(
            ensure_under(Path(row["preselected_path"]), root, "preselected"),
            f"{trajectory_id} preselected.cfg",
        )
        endpoint_path = offline_cfg(
            project["offline"], f"endpoint_{row['side']}"
        )
        raw = parse_cfg(raw_path)
        endpoint = parse_cfg(endpoint_path)
        if endpoint.elements() != LOCKED_ELEMENTS:
            raise AuditError(
                f"{trajectory_id}: endpoint not in locked order: "
                f"{endpoint.elements()}"
            )
        preflight_rows.append({
            "trajectory_id": trajectory_id,
            "raw_path": str(raw_path),
            "raw_sha256": sha256_file(raw_path),
            "raw_ids": raw.ids(),
            "raw_types": tuple(int(x) for x in raw.types()),
            "raw_elements": raw.elements(),
            "endpoint_path": str(endpoint_path),
            "endpoint_sha256": sha256_file(endpoint_path),
            "endpoint_elements": endpoint.elements(),
            "recorded_order": parse_ints(
                row["canonical_order_zero_based"]
            ),
        })

    log(f"Source: {source_path}")
    log(f"Source SHA256: {observed_sha}")
    log(f"Canonicalizer: {discovery['canonical_function']}")
    log(f"Canonicalizer candidates: {discovery['canonical_candidates']}")
    log(f"Table function: {discovery['table_function']}")
    log(f"Kabsch candidates: {discovery['kabsch_candidates']}")
    log(f"Excluded top-level executable nodes: {len(source_audit['excluded'])}")

    module, sanitized_metadata, sanitized_source = import_hash_locked_module(
        source_path=source_path,
        root=root,
        audit=source_audit,
        canonical_function=discovery["canonical_function"],
    )
    function = getattr(module, discovery["canonical_function"])
    log(
        "Sanitized oracle module: PASS; required definitions="
        + ",".join(sanitized_metadata["required_definitions"])
    )

    # Execute the exact pure canonicalizer on all six fixed input pairs during
    # preflight.  This is not a scientific recalculation: it is the hash-locked
    # source function whose outputs are being audited.  Performing the calls
    # here prevents a nominal VALIDATE_ONLY pass when the structural CFGBlock
    # adapter is incomplete.
    preflight_oracle_rows: list[dict[str, Any]] = []
    for trajectory_id in TRAJECTORIES:
        row = rows_by_id[trajectory_id]
        raw_path = require_file(
            ensure_under(Path(row["preselected_path"]), root, "preselected"),
            f"{trajectory_id} preselected.cfg",
        )
        endpoint_path = offline_cfg(
            project["offline"], f"endpoint_{row['side']}"
        )
        raw = parse_cfg(raw_path)
        endpoint = parse_cfg(endpoint_path)
        try:
            smoke_call, smoke_binding = bind_canonicalizer(
                function=function,
                raw=raw,
                reference=endpoint,
                trajectory_id=trajectory_id,
                side=row["side"],
            )
        except Exception as exc:
            raise AuditError(
                f"{trajectory_id}: exact canonicalizer preflight failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        preflight_oracle_rows.append({
            "trajectory_id": trajectory_id,
            "status": "PASS",
            "signature": str(inspect.signature(function)),
            "result_type": type(smoke_call["result"]).__name__,
            "bindings": {
                item["parameter"]: item["binding"]
                for item in smoke_binding["decisions"]
            },
        })
        log(
            f"{trajectory_id}: exact canonicalizer preflight PASS; "
            f"result_type={type(smoke_call['result']).__name__}"
        )

    if args.validate_only:
        print("VALIDATE_ONLY=PASS")
        print(f"SOURCE_SHA256={observed_sha}")
        print(f"CANONICAL_FUNCTION={discovery['canonical_function']}")
        print(f"TABLE_FUNCTION={discovery['table_function']}")
        print(f"KABSCH_CANDIDATES={','.join(discovery['kabsch_candidates'])}")
        print(f"EXCLUDED_TOP_LEVEL_NODES={len(source_audit['excluded'])}")
        print(f"SANITIZED_REQUIRED_DEFINITIONS={','.join(sanitized_metadata['required_definitions'])}")
        print(f"SANITIZED_SOURCE_SHA256={sanitized_metadata['sanitized_source_sha256']}")
        print("SANITIZED_MODULE=PASS")
        print(f"EXACT_CANONICALIZER_PREFLIGHT_CALLS={len(preflight_oracle_rows)}")
        print("EXACT_CFGBLOCK_SIGNATURE_BINDING=PASS")
        print("FIXED_REFERENCE=frozen_offline_endpoint_geometry_cfg")
        print("SCIENTIFIC_EXECUTION=NONE")
        return 0

    attempt_root = root / OUTPUT_REL
    attempt_root.mkdir(parents=True, exist_ok=True)
    attempt = attempt_root / f"attempt_{utc_stamp()}"
    if attempt.exists():
        raise AuditError(f"Refusing existing attempt: {attempt}")
    for directory in (
        attempt,
        attempt / "tables",
        attempt / "reports",
        attempt / "provenance",
        attempt / "source_fragments",
    ):
        directory.mkdir(parents=True, exist_ok=(directory == attempt))

    shutil.copy2(source_path, attempt / "provenance" / source_path.name)
    shutil.copy2(
        project["captured"],
        attempt / "provenance/captured_break_configurations_v032d.tsv",
    )

    atomic_tsv(attempt / "tables/preflight_v004.tsv", preflight_rows)
    atomic_tsv(
        attempt / "tables/exact_canonicalizer_preflight_v004.tsv",
        preflight_oracle_rows,
    )
    atomic_tsv(
        attempt / "tables/source_function_inventory_v004.tsv",
        discovery["inventory"],
    )
    atomic_tsv(
        attempt / "tables/source_table_assignment_inventory_v004.tsv",
        assignment_rows,
    )
    atomic_json(
        attempt / "reports/source_ast_safety_v004.json",
        {
            "unsafe": source_audit["unsafe"],
            "excluded": source_audit["excluded"],
            "top_level": source_audit["top_level"],
            "sanitized_module": sanitized_metadata,
        },
    )
    atomic_text(
        attempt / "provenance/sanitized_oracle_module_v004.py",
        sanitized_source,
    )
    for role, fragment in fragments.items():
        atomic_text(
            attempt / "source_fragments" / f"{role}.py.txt",
            fragment + "\n",
        )


    invocation_rows: list[dict[str, Any]] = []
    binding_rows: list[dict[str, Any]] = []
    leaf_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    oracle_summaries: list[dict[str, Any]] = []
    artifact_rows = [
        artifact(source_path, "exact_v032d_source", root),
        artifact(project["captured"], "captured_table", root),
    ]

    for trajectory_id in TRAJECTORIES:
        row = rows_by_id[trajectory_id]
        raw_path = require_file(
            ensure_under(Path(row["preselected_path"]), root, "preselected"),
            f"{trajectory_id} preselected.cfg",
        )
        endpoint_path = offline_cfg(
            project["offline"], f"endpoint_{row['side']}"
        )
        raw = parse_cfg(raw_path)
        endpoint = parse_cfg(endpoint_path)
        recorded_order = parse_ints(
            row["canonical_order_zero_based"]
        )
        target = expected_metrics(row)

        try:
            call, binding = bind_canonicalizer(
                function=function,
                raw=raw,
                reference=endpoint,
                trajectory_id=trajectory_id,
                side=row["side"],
            )
            leaves, evidence, summary = inspect_oracle_result(
                result=call["result"],
                reference=endpoint,
                expected=target,
                recorded_order=recorded_order,
                trajectory_id=trajectory_id,
            )
            invocation_rows.append({
                "trajectory_id": trajectory_id,
                "status": "PASS",
                "canonical_function": discovery["canonical_function"],
                "signature": call["signature"],
                "error": "",
                "result_type": type(call["result"]).__name__,
            })
            for decision in binding["decisions"]:
                binding_rows.append({
                    "trajectory_id": trajectory_id,
                    **decision,
                })
            leaf_rows.extend(leaves)
            evidence_rows.extend(evidence)
            oracle_summaries.append(summary)
            log(
                f"{trajectory_id}: source call PASS; "
                f"order={summary['recorded_order_reproduced']}; "
                f"position_array={summary['exact_position_array_found']}; "
                f"kabsch_scalar={summary['source_scalar_kabsch_match_found']}"
            )
        except Exception as exc:
            invocation_rows.append({
                "trajectory_id": trajectory_id,
                "status": "FAIL",
                "canonical_function": discovery["canonical_function"],
                "signature": str(inspect.signature(function)),
                "error": f"{type(exc).__name__}: {exc}",
                "result_type": "",
            })
            oracle_summaries.append({
                "trajectory_id": trajectory_id,
                "recorded_order_reproduced": False,
                "exact_position_array_found": False,
                "source_scalar_kabsch_match_found": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
            log(f"{trajectory_id}: source call FAIL: {type(exc).__name__}: {exc}")

        artifact_rows.extend([
            artifact(raw_path, f"{trajectory_id}:raw_preselected", root),
            artifact(endpoint_path, f"{trajectory_id}:fixed_endpoint", root),
        ])

    classification = classify(invocation_rows, oracle_summaries)

    atomic_tsv(
        attempt / "tables/source_oracle_invocations_v004.tsv",
        invocation_rows,
    )
    atomic_tsv(
        attempt / "tables/source_oracle_bindings_v004.tsv",
        binding_rows,
    )
    atomic_tsv(
        attempt / "tables/source_oracle_return_leaves_v004.tsv",
        leaf_rows,
    )
    atomic_tsv(
        attempt / "tables/source_oracle_metric_evidence_v004.tsv",
        evidence_rows,
    )
    atomic_tsv(
        attempt / "tables/source_oracle_summary_v004.tsv",
        oracle_summaries,
    )
    atomic_tsv(
        attempt / "tables/input_artifact_manifest_v004.tsv",
        artifact_rows,
    )

    summary = {
        "created_utc": utc_now(),
        "stage": STAGE,
        "version": VERSION,
        "classification": classification,
        "source": str(source_path),
        "source_sha256": observed_sha,
        "canonical_function": discovery["canonical_function"],
        "sanitized_module": sanitized_metadata,
        "canonical_candidates": discovery["canonical_candidates"],
        "table_function": discovery["table_function"],
        "kabsch_candidates": discovery["kabsch_candidates"],
        "fixed_contract": {
            "raw": "frozen preselected.cfg",
            "reference": "frozen offline endpoint geometry.cfg for same side",
            "mapping": "exact source canonicalization function",
            "alternative_reference_search": False,
            "alternative_mapping_search": False,
            "alignment_formula_reimplementation": False,
            "return_field_introspection": True,
        },
        "scientific_execution": {
            "dft": False,
            "lammps": False,
            "md": False,
            "calc_grade": False,
            "model_loading": False,
            "training": False,
            "upstream_modified": False,
        },
        "invocations": invocation_rows,
        "oracle_results": oracle_summaries,
        "figure_policy": {
            "first_step_displacement_usable": (
                classification == "EXACT_SOURCE_ORACLE_REPLAY_PASS"
            ),
            "maxvol_rejection_claim_allowed": True,
            "physical_error_claim_allowed": False,
        },
    }
    atomic_json(attempt / "summary_v004.json", summary)

    report = [
        "# v032d source-oracle replay v004",
        "",
        f"Classification: `{classification}`",
        "",
        f"Exact source: `{source_path}`",
        f"SHA256: `{observed_sha}`",
        f"Canonicalization function: `{discovery['canonical_function']}`",
        f"Signature: `{inspect.signature(function)}`",
        "",
        "The canonicalization function was called from a sanitized AST module",
        "constructed from the exact frozen source. Top-level executable expressions,",
        "main guards, and unrelated definitions were excluded rather than executed.",
        "No alternative endpoint, atom assignment, or alignment implementation was used.",
        "",
        "| trajectory | invocation | recorded order | exact returned position field | exact Kabsch scalar field |",
        "|---|---|---:|---:|---:|",
    ]
    inv_by_id = {row["trajectory_id"]: row for row in invocation_rows}
    for result in oracle_summaries:
        report.append(
            f"| {result['trajectory_id']} | "
            f"{inv_by_id[result['trajectory_id']]['status']} | "
            f"{result.get('recorded_order_reproduced', False)} | "
            f"{result.get('exact_position_array_found', False)} | "
            f"{result.get('source_scalar_kabsch_match_found', False)} |"
        )
    report.extend([
        "",
        "A failed source invocation is a binding/provenance-recovery result, not",
        "evidence of damaged DFT, MTP training, or the v029/v030r frozen audit.",
        "",
    ])
    atomic_text(
        attempt / "reports/source_oracle_replay_report_v004.md",
        "\n".join(report),
    )

    atomic_text(
        attempt / STATUS_NAME,
        "PASS_SOURCE_ORACLE_AUDIT_COMPLETED__" + classification + "\n",
    )
    checksums(attempt)
    output_bundle = bundle(attempt)
    checksums(attempt)
    pointer = attempt_root / POINTER_NAME
    atomic_text(pointer, str(attempt) + "\n")

    print("============================================================")
    print("SOURCE-ORACLE REPLAY COMPLETED")
    print("============================================================")
    print(f"CLASSIFICATION={classification}")
    print(f"RUN_DIR={attempt}")
    print(f"STATUS={attempt / STATUS_NAME}")
    print(f"SUMMARY={attempt / 'summary_v004.json'}")
    print(f"REPORT={attempt / 'reports/source_oracle_replay_report_v004.md'}")
    print(f"INVOCATIONS={attempt / 'tables/source_oracle_invocations_v004.tsv'}")
    print(f"BINDINGS={attempt / 'tables/source_oracle_bindings_v004.tsv'}")
    print(f"RETURNS={attempt / 'tables/source_oracle_return_leaves_v004.tsv'}")
    print(f"EVIDENCE={attempt / 'tables/source_oracle_metric_evidence_v004.tsv'}")
    print(f"FRAGMENTS={attempt / 'source_fragments'}")
    print(f"BUNDLE={output_bundle}")
    print(f"CURRENT_POINTER={pointer}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print(f"AUDIT_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except KeyboardInterrupt:
        print("INTERRUPTED", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"UNEXPECTED_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(3)

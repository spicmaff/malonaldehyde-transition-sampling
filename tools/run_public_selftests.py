#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

STATUS = "PASS_PUBLIC_REPOSITORY_SELFTESTS_V001"
REQUIRED = (
    "README.md", "CITATION.cff", "environment.yml", "requirements.txt",
    "docs/PIPELINE.md", "docs/REPRODUCIBILITY_STATUS.md",
    "docs/EXECUTION_BOUNDARY.md", "docs/CI_SCOPE.md",
    "scripts/SCRIPT_INDEX.tsv",
    "scripts/core_pipeline/CORE_PIPELINE_MANIFEST.tsv",
    "tools/audit_public_repo.py", "tools/run_public_selftests.py",
    ".github/workflows/audit.yml", ".github/workflows/selftest.yml",
    "reproduce/run_repository_selftests.sh",
)
DEPRECATED = (
    "scripts/stage62_frozen_path_1d_tunneling_audit_v003.py",
    "scripts/render_stage63_supplementary_figure_s3_quantum_audit_v005.py",
)

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("root", nargs="?", type=Path, default=Path("."))
    root = p.parse_args().root.resolve()
    failures = []
    checks = {}

    missing = [x for x in REQUIRED if not (root / x).is_file()]
    if missing:
        failures.append(f"Missing required files: {missing}")
    checks["required_files"] = len(REQUIRED) - len(missing)

    for rel in DEPRECATED:
        if (root / rel).exists():
            failures.append(f"Deprecated duplicate exists: {rel}")

    cp = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "scripts", "tools"],
        cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if cp.returncode:
        failures.append("Python compilation failed:\n" + cp.stdout)
    checks["python_compile"] = cp.returncode == 0

    core = rows(root / "scripts/core_pipeline/CORE_PIPELINE_MANIFEST.tsv")
    if len(core) != 12:
        failures.append(f"Expected 12 core scripts, found {len(core)}")
    seen = set()
    for row in core:
        rel = row["repository_path"]
        if rel in seen:
            failures.append(f"Duplicate core manifest path: {rel}")
        seen.add(rel)
        path = root / rel
        if not path.is_file():
            failures.append(f"Missing core script: {rel}")
        elif sha(path) != row["repository_sha256"]:
            failures.append(f"Core checksum mismatch: {rel}")
    checks["core_manifest_entries"] = len(core)

    index = {r["repository_path"]: r for r in rows(root / "scripts/SCRIPT_INDEX.tsv")}
    actual = {
        p.relative_to(root).as_posix(): p
        for p in sorted((root / "scripts").rglob("*.py"))
    }
    if set(index) != set(actual):
        failures.append("SCRIPT_INDEX.tsv does not exactly match scripts/**/*.py")
    for rel, path in actual.items():
        row = index.get(rel)
        if not row:
            continue
        if row["sha256"] != sha(path):
            failures.append(f"Script-index checksum mismatch: {rel}")
        if row["size_bytes"] != str(path.stat().st_size):
            failures.append(f"Script-index size mismatch: {rel}")
    checks["script_index_entries"] = len(index)

    env = (root / "environment.yml").read_text(encoding="utf-8").lower()
    req = (root / "requirements.txt").read_text(encoding="utf-8").lower()
    for token, text, name in (("pillow", env, "environment.yml"),
                              ("ffmpeg", env, "environment.yml"),
                              ("pillow", req, "requirements.txt")):
        if token not in text:
            failures.append(f"{token} missing from {name}")

    readme = (root / "README.md").read_text(encoding="utf-8").lower()
    if "being promoted separately" in readme:
        failures.append("README contains obsolete promotion statement")
    if "clean-clone verification" not in readme:
        failures.append("README lacks clean-clone verification section")
    if "reproducibility boundary" not in readme:
        failures.append("README lacks reproducibility boundary")

    workflow = (root / ".github/workflows/selftest.yml").read_text(encoding="utf-8")
    if "run_public_selftests.py" not in workflow:
        failures.append("Self-test workflow does not invoke public self-tests")

    audit = subprocess.run(
        [sys.executable, "tools/audit_public_repo.py", "."],
        cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if audit.returncode:
        failures.append("Public repository audit failed:\n" + audit.stdout)
    checks["public_audit"] = audit.returncode == 0

    result = {
        "status": STATUS if not failures else "FAIL",
        "root": str(root), "checks": checks,
        "failure_count": len(failures), "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1

if __name__ == "__main__":
    raise SystemExit(main())

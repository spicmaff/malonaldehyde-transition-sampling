#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

MAX_GIT_FILE_MB = 95.0
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github_classic_pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("github_fine_grained_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
)
PRIVATE_PATH_PATTERNS = (
    ("linux_home_path", re.compile(r"/home/(?!USER/)[A-Za-z0-9._-]+/")),
    ("windows_user_path", re.compile(r"(?:[A-Za-z]:\\Users\\|/mnt/[a-z]/Users/)(?!USER[/\\])[^/\\\s]+[/\\]")),
)
TEXT_SUFFIXES = {".py", ".sh", ".md", ".txt", ".tsv", ".csv", ".json", ".yaml", ".yml", ".cff", ".toml", ".ini", ".cfg", ".rst", ".xyz"}


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def is_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    try:
        data = path.read_bytes()[:8192]
    except OSError:
        return False
    return b"\x00" not in data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    failures = []
    warnings = []
    total_bytes = 0
    file_count = 0
    for path in iter_files(root):
        file_count += 1
        size = path.stat().st_size
        total_bytes += size
        mb = size / (1024 * 1024)
        rel = path.relative_to(root).as_posix()
        if mb >= MAX_GIT_FILE_MB:
            failures.append({"type": "oversize_file", "path": rel, "size_mb": mb})
        elif mb >= 20:
            warnings.append({"type": "large_file", "path": rel, "size_mb": mb})
        if not is_text(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append({"type": "secret_pattern", "pattern": label, "path": rel})
        for label, pattern in PRIVATE_PATH_PATTERNS:
            if pattern.search(text):
                failures.append({"type": "private_path", "pattern": label, "path": rel})
    required = (
        "README.md", "LICENSE", "CITATION.cff", ".gitignore",
        "docs/LIMITATIONS.md", "provenance/PUBLIC_ASSET_MANIFEST.tsv",
    )
    for rel in required:
        if not (root / rel).is_file():
            failures.append({"type": "missing_required_file", "path": rel})
    payload = {
        "status": "PASS" if not failures else "FAIL",
        "root": str(root),
        "file_count": file_count,
        "total_size_mb": total_bytes / (1024 * 1024),
        "max_git_file_mb": MAX_GIT_FILE_MB,
        "warnings": warnings,
        "failures": failures,
    }
    print(json.dumps(payload, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

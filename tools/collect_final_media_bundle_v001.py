#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

VERSION = "v001"
BUNDLE_DIRNAME = f"final_media_bundle_{VERSION}"
CURRENT_POINTER_NAME = f"CURRENT_FINAL_MEDIA_BUNDLE_{VERSION.upper()}.txt"


class BundleError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateSpec:
    logical_name: str
    category: str
    output_name: str
    patterns: Tuple[str, ...]
    required: bool = False
    description: str = ""


SPECS: Tuple[CandidateSpec, ...] = (
    CandidateSpec(
        logical_name="video01_clean_mp4",
        category="videos",
        output_name="video01_relaxed_path_clean_v030.mp4",
        patterns=("video01_relaxed_path_clean_v030.mp4",),
        description="Video 01 clean final MP4",
    ),
    CandidateSpec(
        logical_name="video01_clean_gif",
        category="gifs",
        output_name="video01_relaxed_path_clean_v030.gif",
        patterns=("video01_relaxed_path_clean_preview_v030.gif", "*v030*.gif"),
        description="Video 01 clean GIF preview",
    ),
    CandidateSpec(
        logical_name="video01_central_frame_png",
        category="images",
        output_name="video01_state_image05_v030_full.png",
        patterns=("video01_state_image05_v030_full.png", "video01_state_image05_v030*.png"),
        description="Video 01 representative still",
    ),
    CandidateSpec(
        logical_name="supplementary_video_s1_mp4",
        category="videos",
        output_name="supplementary_video_s1_first_update_rejection_v031.mp4",
        patterns=("supplementary_video_s1_first_update_rejection_v031.mp4",),
        description="Supplementary video S1 MP4",
    ),
    CandidateSpec(
        logical_name="supplementary_video_s1_gif",
        category="gifs",
        output_name="supplementary_video_s1_first_update_rejection_preview_v031.gif",
        patterns=("supplementary_video_s1_first_update_rejection_preview_v031.gif",),
        description="Supplementary video S1 GIF preview",
    ),
    CandidateSpec(
        logical_name="supplementary_video_s1_contact_sheet_png",
        category="images",
        output_name="supplementary_video_s1_contact_sheet_v031.png",
        patterns=("supplementary_video_s1_contact_sheet_v031.png",),
        description="Supplementary video S1 contact sheet",
    ),
    CandidateSpec(
        logical_name="supplementary_video_s1_final_poster_png",
        category="images",
        output_name="supplementary_video_s1_final_poster_v031.png",
        patterns=("supplementary_video_s1_final_poster_v031.png",),
        description="Supplementary video S1 poster",
    ),
    CandidateSpec(
        logical_name="video02_clean_mp4",
        category="videos",
        output_name="video02_proton_transfer_pbe_mep_clean_v034.mp4",
        patterns=(
            "video02_proton_transfer_pbe_mep_clean_v034.mp4",
            "video02_proton_transfer_pbe_mep_clean_v033.mp4",
        ),
        description="Video 02 clean PBE-MEP MP4",
    ),
    CandidateSpec(
        logical_name="video02_clean_gif",
        category="gifs",
        output_name="video02_proton_transfer_pbe_mep_clean_preview.gif",
        patterns=(
            "video02_proton_transfer_pbe_mep_clean_preview_v034.gif",
            "video02_proton_transfer_pbe_mep_clean_preview_v033.gif",
        ),
        description="Video 02 clean GIF preview",
    ),
    CandidateSpec(
        logical_name="video02_storyboard_png",
        category="images",
        output_name="video02_pbe_mep_storyboard.png",
        patterns=("video02_pbe_mep_storyboard_v034.png", "video02_pbe_mep_storyboard_v033.png"),
        description="Video 02 storyboard",
    ),
    CandidateSpec(
        logical_name="video02_central_state_png",
        category="images",
        output_name="video02_pbe_mep_central_state.png",
        patterns=("video02_pbe_mep_central_state_v034.png", "video02_pbe_mep_central_state_v033.png"),
        description="Video 02 representative still",
    ),
    CandidateSpec(
        logical_name="quantum_audit_figure_png",
        category="images",
        output_name="supplementary_figure_s3_quantum_level_audit_v044.png",
        patterns=(
            "supplementary_figure_s3_quantum_level_audit_relaxed_annotations_v044_synthetic_preview.png",
            "supplementary_figure_s3_quantum_level_audit_relaxed_top_v042_synthetic_preview.png",
            "supplementary_figure_s3_quantum_level_audit_final_v040_synthetic_preview.png",
        ),
        description="Final quantum-audit figure PNG",
    ),
    CandidateSpec(
        logical_name="quantum_audit_figure_pdf",
        category="pdf",
        output_name="supplementary_figure_s3_quantum_level_audit_v044.pdf",
        patterns=(
            "supplementary_figure_s3_quantum_level_audit_relaxed_annotations_v044_synthetic_preview.pdf",
            "supplementary_figure_s3_quantum_level_audit_relaxed_top_v042_synthetic_preview.pdf",
            "supplementary_figure_s3_quantum_level_audit_final_v040_synthetic_preview.pdf",
        ),
        description="Final quantum-audit figure PDF",
    ),
    CandidateSpec(
        logical_name="graphical_abstract_png",
        category="images",
        output_name="graphical_abstract_v036_preview.png",
        patterns=("graphical_abstract_v036_preview.png", "graphical_abstract_v035_preview.png"),
        description="Graphical abstract PNG",
    ),
    CandidateSpec(
        logical_name="graphical_abstract_pdf",
        category="pdf",
        output_name="graphical_abstract_v036_preview.pdf",
        patterns=("graphical_abstract_v036_preview.pdf", "graphical_abstract_v035_preview.pdf"),
        description="Graphical abstract PDF",
    ),
)


PACKAGE_DIRS = ("images", "videos", "gifs", "pdf", "tables")


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def newest_key(path: Path) -> Tuple[float, str]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = -1.0
    return (mtime, str(path))


def build_search_roots(root: Path, extra_roots: Sequence[Path]) -> List[Path]:
    roots: List[Path] = []
    def add(p: Path) -> None:
        try:
            p = p.resolve()
        except Exception:
            p = p.absolute()
        if p.exists() and p.is_dir() and p not in roots:
            roots.append(p)
    add(root)
    add(root / "10_visualization")
    add(root / "10_visualization" / "versions")
    for extra in extra_roots:
        add(extra)
    for fallback in (Path("/mnt/data"), Path.cwd()):
        add(fallback)
    return roots


def find_matches(search_roots: Sequence[Path], pattern: str) -> List[Path]:
    matches: List[Path] = []
    seen = set()
    for search_root in search_roots:
        try:
            found_iter = search_root.rglob(pattern)
        except Exception:
            continue
        for p in found_iter:
            if not p.is_file():
                continue
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            matches.append(p.resolve())
    matches.sort(key=newest_key)
    return matches


def select_best_source(search_roots: Sequence[Path], spec: CandidateSpec) -> Optional[Path]:
    for pattern in spec.patterns:
        matches = find_matches(search_roots, pattern)
        if matches:
            return matches[-1]
    return None


def ensure_clean_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_manifest(records: List[dict], manifest_path: Path) -> None:
    fieldnames = [
        "logical_name",
        "category",
        "description",
        "selected_source",
        "destination_relative_path",
        "size_bytes",
        "sha256",
        "selected",
    ]
    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def write_checksums(run_dir: Path, checksum_path: Path) -> None:
    lines: List[str] = []
    for file_path in sorted(p for p in run_dir.rglob("*") if p.is_file() and p.name != checksum_path.name):
        rel = file_path.relative_to(run_dir)
        lines.append(f"{compute_sha256(file_path)}  {rel.as_posix()}")
    checksum_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_readme(run_dir: Path, root: Path, records: List[dict], manifest_rel: Path, checksum_rel: Path, search_roots: Sequence[Path]) -> None:
    present = [r for r in records if r["selected"] == "YES"]
    missing = [r for r in records if r["selected"] == "NO"]
    lines = [
        f"# Final media bundle {VERSION}",
        "",
        "This bundle contains ready-to-use project visuals only (images, videos, GIF previews, and PDF exports).",
        "",
        f"Generated UTC: {dt.datetime.utcnow().isoformat(timespec='seconds')}Z",
        f"Project root: {root}",
        f"Bundle directory: {run_dir}",
        "",
        "## Search roots used",
        "",
    ]
    lines.extend([f"- `{p}`" for p in search_roots])
    lines.extend([
        "",
        "## Included assets",
        "",
    ])
    if present:
        lines.extend([f"- `{r['destination_relative_path']}` ← `{r['selected_source']}`" for r in present])
    else:
        lines.append("- No assets were found.")
    lines.extend([
        "",
        "## Missing optional assets",
        "",
    ])
    if missing:
        lines.extend([f"- {r['logical_name']}" for r in missing])
    else:
        lines.append("- None")
    lines.extend([
        "",
        f"Manifest: `{manifest_rel.as_posix()}`",
        f"Checksums: `{checksum_rel.as_posix()}`",
    ])
    (run_dir / "README_FINAL_MEDIA_BUNDLE_V001.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def maybe_make_tar(run_dir: Path) -> Optional[Path]:
    tar_path = run_dir.with_suffix(".tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(run_dir, arcname=run_dir.name)
    return tar_path


def collect_bundle(root: Path, extra_roots: Sequence[Path], out_root: Optional[Path], make_tar: bool) -> int:
    if not root.exists():
        raise BundleError(f"Root does not exist: {root}")
    timestamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bundle_parent = out_root if out_root is not None else (root / "10_visualization" / BUNDLE_DIRNAME)
    run_dir = bundle_parent / f"attempt_{timestamp}"
    for dirname in PACKAGE_DIRS:
        ensure_clean_dir(run_dir / dirname)
    search_roots = build_search_roots(root, extra_roots)

    records: List[dict] = []
    found_count = 0
    for spec in SPECS:
        source = select_best_source(search_roots, spec)
        if source is None:
            records.append({
                "logical_name": spec.logical_name,
                "category": spec.category,
                "description": spec.description,
                "selected_source": "",
                "destination_relative_path": "",
                "size_bytes": "",
                "sha256": "",
                "selected": "NO",
            })
            continue
        destination = run_dir / spec.category / spec.output_name
        ensure_clean_dir(destination.parent)
        shutil.copy2(source, destination)
        rel = destination.relative_to(run_dir)
        records.append({
            "logical_name": spec.logical_name,
            "category": spec.category,
            "description": spec.description,
            "selected_source": str(source),
            "destination_relative_path": rel.as_posix(),
            "size_bytes": str(destination.stat().st_size),
            "sha256": compute_sha256(destination),
            "selected": "YES",
        })
        found_count += 1

    manifest_path = run_dir / "tables" / "MANIFEST.tsv"
    write_manifest(records, manifest_path)
    checksum_path = run_dir / "SHA256SUMS.txt"
    write_checksums(run_dir, checksum_path)
    write_readme(
        run_dir=run_dir,
        root=root,
        records=records,
        manifest_rel=manifest_path.relative_to(run_dir),
        checksum_rel=checksum_path.relative_to(run_dir),
        search_roots=search_roots,
    )

    current_pointer = bundle_parent / CURRENT_POINTER_NAME
    current_pointer.parent.mkdir(parents=True, exist_ok=True)
    current_pointer.write_text(str(run_dir) + "\n", encoding="utf-8")

    tar_path = maybe_make_tar(run_dir) if make_tar else None

    print("============================================================")
    print(f"FINAL MEDIA BUNDLE {VERSION} READY")
    print("============================================================")
    print(f"ROOT={root}")
    print(f"RUN_DIR={run_dir}")
    print(f"MANIFEST={manifest_path}")
    print(f"SHA256SUMS={checksum_path}")
    print(f"CURRENT_POINTER={current_pointer}")
    print(f"FOUND_ASSETS={found_count}/{len(SPECS)}")
    if tar_path is not None:
        print(f"BUNDLE_TAR_GZ={tar_path}")
    for record in records:
        prefix = "FOUND" if record["selected"] == "YES" else "MISSING"
        print(f"{prefix}_{record['logical_name'].upper()}={record['destination_relative_path'] or 'NONE'}")
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect ready-to-use visual media into one final bundle.")
    parser.add_argument("--root", type=Path, default=Path("${PROJECT_ROOT}"), help="Project root")
    parser.add_argument("--extra-search-root", type=Path, action="append", default=[], help="Additional directory to search")
    parser.add_argument("--out-root", type=Path, default=None, help="Custom output parent directory")
    parser.add_argument("--emit-tar", action="store_true", help="Also create a tar.gz archive of the collected bundle")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        return collect_bundle(root=args.root.resolve(), extra_roots=args.extra_search_root, out_root=args.out_root, make_tar=args.emit_tar)
    except BundleError as exc:
        print(f"ERROR={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

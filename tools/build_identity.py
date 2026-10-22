"""Deterministic identity of the code used for a build, separate from science IDs."""
import hashlib
import json
from pathlib import Path
import subprocess


def build_identity(root: Path):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)
    try:
        commit = git('rev-parse', 'HEAD').decode().strip()
        tree = git('rev-parse', 'HEAD^{tree}').decode().strip()
        diff = git('diff', '--binary', 'HEAD', '--')
        untracked = git('ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
        # Record only task source additions, never arbitrary ignored credentials.
        additions = {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
                     for p in sorted(untracked) if p and Path(p).parts[0] in
                     {'site', 'tools', 'tests', 'provenance', 'docs', '.github'} and (root / p).is_file()}
        return {'schema': 'proton-build-identity-v1', 'source_commit': commit, 'source_tree': tree,
                'working_copy_clean': not diff and not any(untracked),
                'untracked_file_count': sum(bool(p) for p in untracked),
                'tracked_diff_sha256': hashlib.sha256(diff).hexdigest() if diff else None,
                'untracked_source_sha256': additions,
                'scope': 'Website source identity; historical science and aggregate source IDs remain separate.'}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {'schema': 'proton-build-identity-v1', 'source_commit': None, 'source_tree': None,
                'working_copy_clean': None, 'scope': 'Git metadata unavailable; authenticate files with build-manifest.json.'}


def write_identity(root: Path, out: Path):
    identity = build_identity(root)
    (out / 'build-identity.json').write_text(json.dumps(identity, sort_keys=True, indent=2) + '\n')
    return identity

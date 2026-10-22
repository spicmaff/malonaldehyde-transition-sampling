"""Small static review refinements; no changes to scientific payloads or motion."""
from __future__ import annotations
from pathlib import Path

# Exact extension points fail closed when the underlying templates change.
NAMED_GROUPS = (
    ('class="image-strip js-control" aria-label=', 'class="image-strip js-control" role="group" aria-label='),
    ('class="atom-buttons js-control" aria-label=', 'class="atom-buttons js-control" role="group" aria-label='),
    ('class="opt-page-index" aria-label=', 'class="opt-page-index" role="navigation" aria-label='),
    ('class="opt-parameter-total" aria-label=', 'class="opt-parameter-total" role="group" aria-label='),
    ('data-opt-log-max="1" aria-label=', 'data-opt-log-max="1" role="group" aria-label='),
    ('class="opt-transaction" aria-label=', 'class="opt-transaction" role="group" aria-label='),
)
AVAILABILITY = (
    '<p id="opt-recovery-availability" class="opt-visible-limit" role="note">'
    '<strong>Evidence availability.</strong> The earlier review describes the complete '
    'private main4500 recovery bundle as currently unavailable after a failed persistent save '
    'and workspace reset. The incident itself is not independently established by the public '
    'files. This edition confirms the absence of the native recovery package from its public sources. '
    'The previously reviewed aggregate values and source hashes remain available; '
    'they do not replace the missing native arrays, model states or process receipts. '
    'This review verifies the public arithmetic and presentation, not a fresh native '
    'reproduction. T1 retains its separate synthetic-only scope.</p>'
)
ESSAY_LINK = '<a href="#longread">Read the full research essay →</a>'
NEXT_LINKS = (
    '<div class="review-note-links">' + ESSAY_LINK +
    '<a class="review-optimization-entry" href="#optimization">'
    'Next: inside the optimization <span aria-hidden="true">→</span></a></div>'
)


def replace_once(document: str, old: str, new: str) -> str:
    if document.count(old) != 1:
        raise ValueError('Presentation review anchor must occur exactly once: ' + old)
    return document.replace(old, new, 1)


def refine_document(document: str) -> str:
    """Keep diagrams and controls intact; correct names and disclose evidence loss."""
    for old, new in NAMED_GROUPS:
        document = replace_once(document, old, new)
    document = replace_once(document, '<i>J</i><br>from S0 to S2', '<i>J</i> <span class="review-ratio-context">from S0 to S2</span>')
    document = replace_once(document, ESSAY_LINK, NEXT_LINKS)
    document = replace_once(document, '<div class="opt-downloads">', AVAILABILITY + '<div class="opt-downloads">')
    document = replace_once(document, '</head>', '<link rel="stylesheet" href="presentation_review.css"></head>')
    # The original builder has already validated this public edition.
    import json
    from cinematic import refine_document as refine_cinematic
    payload = Path(__file__).resolve().parents[1] / 'data/optimization_story/v001/OPTIMIZATION_STORY.json'
    return refine_cinematic(document, json.loads(payload.read_text(encoding='utf-8')))


def copy_style(out: Path) -> None:
    (out / 'presentation_review.css').write_bytes(Path(__file__).with_suffix('.css').read_bytes())
    from cinematic import copy_assets
    copy_assets(out)


def verify_registered_assets(root: Path) -> int:
    """Check explicit review deltas without silently rewriting frozen provenance."""
    import csv
    import hashlib
    def records(name: str) -> list[dict[str, str]]:
        with (root / 'provenance' / name).open(encoding='utf-8', newline='') as stream:
            return list(csv.DictReader(stream, delimiter='\t'))
    original = records('PUBLIC_ASSET_MANIFEST.tsv')
    delta = records('PRESENTATION_REVIEW_DELTA.tsv')
    by_path = {r['repository_path']: r for r in original}
    if len(by_path) != len(original):
        raise ValueError('Duplicate original asset path')
    allowed_overrides = {'.github/workflows/research-site.yml', 'tools/build_research_site.py',
                         'tools/run_public_selftests.py'}
    additions = {'site/presentation_review.py', 'site/presentation_review.css',
                 'tests/test_presentation_review.py', 'tools/site/browser_review_test.mjs',
                 'docs/PRESENTATION_REVIEW.md', 'site/cinematic.py', 'site/cinematic.css',
                 'site/cinematic.mjs', 'tests/test_cinematic.py',
                 'tools/site/browser_cinematic_test.mjs', 'docs/CINEMATIC_REVIEW.md'}
    if {r['repository_path'] for r in delta} != allowed_overrides | additions or len(delta) != 14:
        raise ValueError('Unexpected presentation manifest scope')
    for r in delta:
        old = by_path.get(r['repository_path'])
        expected = old['repository_sha256'] if old else 'NEW'
        if r['previous_repository_sha256'] != expected:
            raise ValueError('Presentation manifest previous hash mismatch')
        by_path[r['repository_path']] = r
    # A new explicit layer preserves both older frozen manifests verbatim.
    editorial = records('EDITORIAL_REDESIGN_DELTA.tsv')
    if {r['repository_path'] for r in editorial} != EDITORIAL_ASSETS or len(editorial) != len(EDITORIAL_ASSETS):
        raise ValueError('Unexpected editorial manifest scope')
    for r in editorial:
        old = by_path.get(r['repository_path'])
        if r['previous_repository_sha256'] != (old['repository_sha256'] if old else 'NEW'):
            raise ValueError('Editorial manifest previous hash mismatch')
        by_path[r['repository_path']] = r
    independent_path = root / 'provenance/INDEPENDENT_REVIEW_DELTA.tsv'
    if independent_path.is_file():
        independent = records('INDEPENDENT_REVIEW_DELTA.tsv')
        if {r['repository_path'] for r in independent} != INDEPENDENT_ASSETS or len(independent) != len(INDEPENDENT_ASSETS):
            raise ValueError('Unexpected independent review manifest scope')
        for r in independent:
            old = by_path.get(r['repository_path'])
            if r['previous_repository_sha256'] != (old['repository_sha256'] if old else 'NEW'):
                raise ValueError('Independent review manifest previous hash mismatch')
            by_path[r['repository_path']] = r
    for relative, r in by_path.items():
        p = root / relative
        if not p.is_file() or p.is_symlink():
            raise ValueError('Missing registered asset: ' + relative)
        b = p.read_bytes()
        if hashlib.sha256(b).hexdigest() != r['repository_sha256'] or len(b) != int(r['size_bytes']):
            raise ValueError('Registered asset differs: ' + relative)
    return len(by_path)

# Source and interpretation changes only. No historical scientific arrays or models.
EDITORIAL_ASSETS = {
    '.github/workflows/research-site.yml', 'tools/build_research_site.py',
    'tools/run_public_selftests.py', 'site/presentation_review.py',
    'site/editorial.py', 'site/editorial.css', 'site/app.mjs', 'site/charts.mjs',
    'site/core.mjs', 'site/molecule.mjs', 'site/literature.json',
    'tests/test_presentation_review.py', 'tests/test_editorial.py', 'tests/test_offpath_extension.py',
    'tools/verify_editorial_findings.py', 'tools/site/test_editorial.mjs',
    'tools/site/browser_editorial_test.mjs', 'tools/site/browser_cinematic_test.mjs', 'docs/editorial-findings.json',
    'docs/EDITORIAL_RESEARCH_REVIEW_RU.md', 'docs/EDITORIAL_REDESIGN.md',
    'docs/RESEARCH_SITE.md',
}

# Explicit fourth layer; scientific arrays, models and earlier manifests are excluded.
INDEPENDENT_ASSETS = {
    'site/charts.mjs', 'site/editorial.css',
    '.github/workflows/independent-review.yml', '.github/workflows/research-site.yml',
    'site/app.mjs', 'site/editorial.py', 'site/presentation_review.py',
    'site/payload_validation.mjs', 'site/literature.json', 'site/molecule.mjs',
    'tools/build_research_site.py', 'tools/build_identity.py',
    'tools/audit_independent_science.py', 'tools/run_public_selftests.py',
    'tools/site/browser_cinematic_test.mjs', 'tools/site/browser_independent_test.mjs',
    'tools/site/test_payload_validation.mjs', 'tests/test_independent_review.py',
    'tests/test_presentation_review.py', 'tests/test_offpath_extension.py',
}

"""A narrowly scoped publication layer; earlier provenance stays immutable."""
import csv
import hashlib
from pathlib import Path

# Exact parents from the accepted public source 8df2c82d. Scientific files
# cannot be added to this layer by changing its manifest.
PARENTS = {
    'tools/audit_public_repo.py': 'ad0868ae5a59241ca7e5ad359c7a7390bc508ed8ec2642121fe0145eee38af31',
    'tools/site/browser_optimization_test.mjs': '40e0b41dc8e1a3e2b7c36f8f1373146827272d5dc52ebe5098db36d7f969c810',
    'tools/site/browser_review_test.mjs': '1a00e4c17cc388f27a7ea3687ab25e070180143b72b508c1e833eb624acdd16d',
    'tools/site/browser_finale_test.mjs': '756c2dff031ea2d3fc3d08311ed93489a27aef5f49f1f7728a36c2510fec026e',
    'site/presentation_review.py': '3dcb674fcef38cca2b066d96525747d2f93fd0f460ca073febd7f5a813db4161',
    'tools/run_public_selftests.py': '2db51684eff46e230ad7bd6e840048ec7317d4c2f2eb864850b56ed7e69b26c9',
    'tools/build_scientific_finale.py': 'a073d644918b97db9029653ce0e70fe8fcda654b9272d192709c95e1a241d06f',
    'tests/test_offpath_extension.py': '1bb21a4226364b59afaf0ff86adee1f5a35707cb57132f7e052bea8cab6a0d2d',
}


def load_metadata_overrides(root: Path) -> dict:
    from popular_publication import load_popular_overrides
    popular = load_popular_overrides(root)
    manifest = root / 'provenance/PUBLICATION_METADATA_DELTA.tsv'
    if not manifest.is_file():
        return {}
    with manifest.open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    if len(rows) != len(PARENTS) or {r['repository_path'] for r in rows} != set(PARENTS):
        raise ValueError('Unexpected publication metadata scope')
    for row in rows:
        relative = row['repository_path']
        if row['previous_repository_sha256'] != PARENTS[relative]:
            raise ValueError('Publication metadata parent mismatch: ' + relative)
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing publication metadata asset: ' + relative)
        current = popular.get(relative, row)
        if relative in popular and current['previous_repository_sha256'] != row['repository_sha256']:
            raise ValueError('Reading edition metadata chain mismatch: ' + relative)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != current['repository_sha256'] or len(data) != int(current['size_bytes']):
            raise ValueError('Publication metadata asset differs: ' + relative)
    combined = {r['repository_path']: r for r in rows}
    for relative, row in popular.items():
        # Existing callers check one edge against the frozen earlier manifests.
        # Validate the intermediate edge above, then return its composed record.
        current = dict(row)
        if relative in combined:
            current['previous_repository_sha256'] = combined[relative]['previous_repository_sha256']
        combined[relative] = current
    return combined


def effective_record(relative: str, previous: dict, overrides: dict) -> dict:
    if relative not in overrides:
        return previous
    row = overrides[relative]
    if row['previous_repository_sha256'] != previous['repository_sha256']:
        raise ValueError('Publication metadata chain mismatch: ' + relative)
    return row

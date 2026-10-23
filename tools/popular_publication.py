"""Explicit interface-only publication delta, rooted at the accepted 51c96a7 source."""
import csv
import hashlib
from pathlib import Path

PARENTS = {'.github/workflows/research-site.yml': 'b61b7ca75875f0142a234770093fb3df71fadcba6634a6d5fb16be0324ffb3da',
 'docs/POPULAR_READING_EDITION_RU.md': 'NEW',
 'site/app.mjs': '4d9b24e52393451d7a7ec14869dd0d2580ab20badb2e1b97085ba4165e105640',
 'site/editorial.py': 'b0f9920df09fa9809ab429088e0a32d17223dca897667a0e380dd34513a13567',
 'site/longread.en.md': '8a303cf859894d1da0b4c74ee95f716ddd5af60b1381efb79a78be992b9a40d3',
 'site/molecule.mjs': '61473ac24aefbc9c6da41773fdac3b1dc024ca2fc781eb701d85348f45438f69',
 'site/optimization.mjs': '2e72d99111a8f7cbe75fa62942e39529f69800140291bf95ab1075ff16b1d361',
 'site/pages.py': '1ff9c886cf26f5dbcb9844e4deaaa307c63783669196fbb39493507fd0030ac4',
 'site/popular.css': 'NEW',
 'site/popular.py': 'NEW',
 'tests/test_cinematic.py': 'ed90797a162f120b6752b90603ad8031697671d0c7f31d156f65570d6ccf29b2',
 'tests/test_editorial.py': '6a78c5b7d5d7a7cb160e70189b5656f3c80b4de701e8a76a8de6909706ce4a17',
 'tests/test_independent_review.py': 'cc5a81d03137ad61cd75a28f12afb4e4992c45f9931d679aea4a52298eb53046',
 'tests/test_offpath_extension.py': 'af749625e5080f08c907dd6d8bcfce7ff0b964d8e15a91e44397d2fa2c32d72a',
 'tests/test_popular.py': 'NEW',
 'tests/test_presentation_review.py': '0fd148f3115574117de39a60fbd9f3d327419f9c0f02e7202c135a7e5a29da2c',
 'tests/test_scientific_finale.py': '1eacc5da418303d9a977bab4caeeff36d4e74b2166c8d178437ff2bced076250',
 'tools/build_research_site.py': '1e94179d538545da837cbabdf9c6e2b1c2b67047b7878e78df859947f3594ea9',
 'tools/popular_publication.py': 'NEW',
 'tools/publication_metadata.py': '852a2a45df74e11142ba1072672379aeaa43662e4fd630eee1124a9c3ebf3e74',
 'tools/site/browser_cinematic_test.mjs': '22d62b9a9b1bd832a240a30357a75f5cdf7a8e1a36f269f4decc1f805daa7b7f',
 'tools/site/browser_editorial_test.mjs': '46fae068009f9a49adb18e7bfabb10154f861e8b7e96c6865f93623e5bcb62da',
 'tools/site/browser_finale_test.mjs': '990e482326eae42a0ba7ea5710cd935db0545a062b38a88d5ee742115dc08f44',
 'tools/site/browser_optimization_test.mjs': '5ca504b0d2eae9fdb38cc84ab95e3283b9b22168550c7d2e88c67b80bb3f5179',
 'tools/site/browser_popular_test.mjs': 'NEW',
 'tools/site/browser_review_test.mjs': '9aa2161dec906ca621f385a5fe0ca5b4ddbd5a3ffc9cf62fcf8ef637c0328ded',
 'tools/site/test_site.py': 'e13ef43daee0c5c246863aedeaf23d9fb9216906668b6679be2dc55562989b97'}


def load_popular_overrides(root: Path) -> dict:
    manifest = root / 'provenance/POPULAR_READING_DELTA.tsv'
    if not manifest.is_file():
        return {}
    with manifest.open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    if len(rows) != len(PARENTS) or {r['repository_path'] for r in rows} != set(PARENTS):
        raise ValueError('Unexpected reading edition scope')
    for row in rows:
        relative = row['repository_path']
        if row['previous_repository_sha256'] != PARENTS[relative]:
            raise ValueError('Reading edition parent mismatch: ' + relative)
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing reading edition asset: ' + relative)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['repository_sha256'] or len(data) != int(row['size_bytes']):
            raise ValueError('Reading edition asset differs: ' + relative)
    return {r['repository_path']: r for r in rows}

"""Static review contracts. Science exporters remain the original authorities."""
import sys
import tempfile
import unittest
import csv
from unittest.mock import patch
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'site'))
import build_research_site as build
import presentation_review as review


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class PresentationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name) / 'site'
        build.build(cls.out)
        cls.html = (cls.out / 'index.html').read_text()
        cls.tags = Tags()
        cls.tags.feed(cls.html)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_six_named_containers_have_valid_semantic_roles(self):
        for old, new in review.NAMED_GROUPS:
            self.assertNotIn(old, self.html)
            self.assertEqual(self.html.count(new), 1)

    def test_controls_not_hidden_inside_an_image_role(self):
        row = next(a for t, a in self.tags.tags if a.get('id') == 'opt-state-chart')
        self.assertEqual(row['role'], 'group')
        self.assertEqual(sum('data-opt-select' in a for _, a in self.tags.tags), 7)

    def test_published_aggregate_scope_is_visible_static_content(self):
        self.assertEqual(self.html.count(review.AVAILABILITY), 0)
        self.assertIn('Arithmetic from published summary values', self.html)
        self.assertIn('not a fresh native replay', self.html)

    def test_existing_essay_link_and_new_overview_entry_are_both_present(self):
        overview = self.html.split('id="overview"', 1)[1].split('</section>', 1)[0]
        self.assertIn('href="#longread"', overview)
        self.assertIn('href="#optimization"', self.html)

    def test_all_twelve_routes_are_preserved(self):
        self.assertEqual(sum('data-page' in a for _, a in self.tags.tags), 12)
        self.assertEqual(sum(a.get('data-route') == 'optimization' for _, a in self.tags.tags), 1)

    def test_style_is_copied_exactly_and_scoped(self):
        source = ROOT / 'site/presentation_review.css'
        self.assertEqual((self.out / source.name).read_bytes(), source.read_bytes())
        self.assertIn('max-width:420px', source.read_text())
        self.assertNotIn('!important', source.read_text())
        self.assertNotIn('font-face', source.read_text())

    def test_refinement_fails_on_missing_or_duplicated_anchor(self):
        with self.assertRaises(ValueError):
            review.replace_once('absent', 'target', 'new')
        with self.assertRaises(ValueError):
            review.replace_once('target target', 'target', 'new')
        with self.assertRaises(ValueError):
            review.refine_document(self.html)

    def test_public_optimization_bytes_are_not_rewritten(self):
        data = ROOT / 'data/optimization_story/v001'
        for p in data.iterdir():
            if p.is_file():
                self.assertEqual((self.out / 'data/optimization' / p.name).read_bytes(), p.read_bytes())

    def test_all_registered_assets_and_explicit_deltas_match(self):
        self.assertEqual(review.verify_registered_assets(ROOT), 318)

    def test_scientific_byte_tampering_is_rejected(self):
        original = Path.read_bytes
        target = ROOT / 'data/frozen_audit/neb9_energy_profiles_v005.tsv'
        with patch.object(Path, 'read_bytes', lambda p: original(p) + b'\n' if p == target else original(p)):
            with self.assertRaisesRegex(ValueError, 'Registered asset differs'):
                review.verify_registered_assets(ROOT)

    def test_delta_rejects_out_of_scope_and_wrong_previous_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'provenance').mkdir()
            for name in ('PUBLIC_ASSET_MANIFEST.tsv', 'PRESENTATION_REVIEW_DELTA.tsv'):
                (root / 'provenance' / name).write_bytes((ROOT / 'provenance' / name).read_bytes())
            delta = root / 'provenance/PRESENTATION_REVIEW_DELTA.tsv'
            saved = delta.read_text()
            delta.write_text(saved.replace('.github/workflows/research-site.yml', 'data/unauthorized.json', 1))
            with self.assertRaisesRegex(ValueError, 'Unexpected presentation manifest scope'):
                review.verify_registered_assets(root)
            entries = list(csv.DictReader(saved.splitlines(), delimiter='\t'))
            entries[0]['previous_repository_sha256'] = '0' * 64
            with delta.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, list(entries[0]), delimiter='\t', lineterminator='\n')
                writer.writeheader(); writer.writerows(entries)
            with self.assertRaisesRegex(ValueError, 'previous hash mismatch'):
                review.verify_registered_assets(root)

    def test_mobile_caption_keeps_a_word_boundary(self):
        self.assertIn('<i>J</i> <span class="review-ratio-context">from S0 to S2</span>', self.html)


if __name__ == '__main__':
    unittest.main()

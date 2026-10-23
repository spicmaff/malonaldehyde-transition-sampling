"""Reading-edition regressions: static truth, scientific scope and provenance."""
import csv
import hashlib
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'site')]
import build_research_site
from popular import Elements, fragment
from popular_publication import load_popular_overrides
from pages import fallback


class PopularTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name) / 'site'
        cls.data = build_research_site.build(cls.out)
        cls.html = (cls.out / 'index.html').read_text()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_static_force_geometry_score_and_atom_agree(self):
        f = next(f for f in self.data['forces'] if f['index'] == 145)
        stage = fragment(self.html, ident='force-molecule')
        self.assertIn(fallback(f['xyz'], 'Malonaldehyde, saved Replay 145 geometry'), stage)
        self.assertIn('Replay 145 geometry', stage)
        self.assertNotIn('central PBE', stage)
        self.assertIn(f'{f["rmse"]:.5f}', fragment(self.html, ident='selected-rmse'))
        self.assertIn('H2* · Replay 145', fragment(self.html, ident='force-selection'))
        options = fragment(self.html, ident='force-frame')
        self.assertIn('value="145" selected', options)
        self.assertIn('Original laboratory components', fragment(self.html, ident='force-components'))

    def test_fallback_labels_and_hydrogen_outlines(self):
        svg = fallback(self.data['molecule'][4]['xyz'], 'An explicitly selected geometry')
        tags = Elements(svg).elements
        self.assertIn('aria-label="An explicitly selected geometry"', svg)
        self.assertEqual(sum(n['tag'] == 'circle' for n in tags), 9)
        for n in tags:
            if n['tag'] == 'circle':
                self.assertEqual(n['attrs']['stroke'], 'var(--ink)')
        self.assertIn('H2*', svg)
        off = fragment(self.html, ident='offpath-molecule')
        self.assertNotIn('central PBE image', off)

    def test_overview_profiles_keep_all_supports_and_own_baselines(self):
        svg = fragment(self.html, cls='pop-profile')
        for name in ['PBE', 'Basin60', 'Targeted60']:
            g = next(n for n in Elements(svg).elements if n['attrs'].get('data-pop-profile') == name)
            markup = svg[g['start']:g['end']]
            self.assertEqual(len(Elements(markup).elements), 11)
            self.assertAlmostEqual(min(self.data['profiles'][name][0], self.data['profiles'][name][-1]), 0)
        self.assertGreater(self.data['profiles']['PBE'][4], 0)
        self.assertLess(self.data['profiles']['Basin60'][4], 0)
        self.assertIn('<rect ', svg); self.assertIn('<circle ', svg); self.assertIn('l4.4 4.4', svg)

    def test_public_copy_uses_evidence_scope_without_archive_inventory(self):
        essay = (self.out / 'longread.en.md').read_text()
        for term in ['missing-input recovery', 'private recovery', 'unavailable archive', 'Blind12', 'No authorization. No execution.']:
            self.assertNotIn(term, self.html)
            self.assertNotIn(term, essay)
        self.assertIn('published summary values', essay)
        self.assertIn('not a fresh native replay', self.html)
        self.assertIn('independent external testing', self.html)
        self.assertIn('parameterization', self.html)
        self.assertIn('fixed positive metric', self.html)
        self.assertNotIn('Only the placement of 24 examples changes.', self.html)
        self.assertIn('Initialization can change the outcome, too.', self.html)

    def test_study_specific_reconstruction_links(self):
        original = fragment(self.html, ident='landscape')
        self.assertIn('/tools/recompute_primary_metrics.py', original)
        self.assertNotIn('/tools/verify_train119_diagnostic.py', original)
        seeds = fragment(self.html, ident='seeds')
        self.assertIn('/tools/audit_independent_science.py', seeds)
        self.assertIn('/tools/verify_pbe14_offpath.py', fragment(self.html, ident='offpath'))

    def test_essay_download_and_page_are_from_one_shorter_source(self):
        from editorial import ESSAY_SCOPE
        self.assertEqual(self.html.count(ESSAY_SCOPE), 1)
        self.assertEqual((self.out / 'longread.en.md').read_text().count(ESSAY_SCOPE), 1)
        self.assertLess(len((ROOT / 'site/longread.en.md').read_text().split()), 2300)

    def reject_delta(self, mutate, pattern):
        manifest = ROOT / 'provenance/POPULAR_READING_DELTA.tsv'
        rows = list(csv.DictReader(manifest.read_text().splitlines(), delimiter='\t'))
        mutate(rows)
        out = StringIO(); writer = csv.DictWriter(out, rows[0].keys(), delimiter='\t')
        writer.writeheader(); writer.writerows(rows)
        original = Path.open
        def opening(path, *args, **kw):
            return StringIO(out.getvalue()) if path == manifest else original(path, *args, **kw)
        with patch.object(Path, 'open', opening), self.assertRaisesRegex(ValueError, pattern):
            load_popular_overrides(ROOT)

    def test_presentation_delta_cannot_override_a_scientific_array(self):
        self.reject_delta(lambda rows: rows[0].update(repository_path='data/frozen_models_v028/train_basin60_v028.cfg'), 'edition scope')

    def test_presentation_delta_cannot_erase_its_parent(self):
        self.reject_delta(lambda rows: rows[0].update(previous_repository_sha256='0'*64), 'parent mismatch')


if __name__ == '__main__':
    unittest.main()

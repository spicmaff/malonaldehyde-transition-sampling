"""Contract tests for new scientific interpretation and evidence boundaries."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'site')]
from verify_editorial_findings import verify
import build_research_site as builder
from editorial import Pages, ORDER


class EditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings = verify()
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name) / 'site'
        builder.build(cls.out)
        cls.html = (cls.out / 'index.html').read_text()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_checked_findings_match_live_recomputation(self):
        self.assertEqual(self.findings, json.loads((ROOT / 'docs/editorial-findings.json').read_text()))
        self.assertEqual(self.findings, json.loads((self.out / 'data/editorial.json').read_text()))

    def test_gap_comes_from_coordinates_not_rounded_table(self):
        g = self.findings['geometry']
        self.assertEqual(g['internal_images_below_training_range'], {'basin':list(range(2,9)), 'targeted':list(range(2,9))})
        self.assertAlmostEqual(g['OO_gap_below_training_minimum_A'], .08886882781974492, places=13)
        self.assertIn('aligned minima', self.html)
        self.assertIn('not established coverage', self.html)

    def test_primary_and_sensitivity_remain_distinct(self):
        off = self.findings['offpath']
        self.assertEqual(off['primary']['targeted_wins'], 4)
        self.assertAlmostEqual(off['primary']['mean_eV_A'], -.1461353992591766, places=13)
        self.assertEqual([r['targeted_win_count'] for r in off['leave_one_block_out']], [4,4,3,3])
        self.assertIn('predeclared four-block endpoint above remains the primary result', self.html)

    def test_q_arithmetic_and_candidate_boundary(self):
        opt = self.findings['optimization']
        self.assertGreater(float(opt['S1c_to_S2_row_deltas']['data_loss']), 0)
        self.assertLess(float(opt['S1c_to_S2_row_deltas']['Q']), 0)
        self.assertFalse(opt['COV']['candidate_coefficients_exported'])
        self.assertIn('Missing matrices, native model states', self.html)
        self.assertIn('parameterization', self.html)
        self.assertIn('new study ID', self.html)

    def test_editorial_order_and_static_coverage_survive_no_js(self):
        pages = Pages(self.html).spans
        self.assertEqual(list(pages), ORDER)
        self.assertEqual(self.html.count('ed-coverage-static'), 2)
        self.assertIn('2.479', self.html)
        self.assertIn('2.390', self.html)
        self.assertIn('Moment Tensor Potentials', self.html[:12000])
        self.assertIn('Hubert Beck', self.html)
        self.assertNotIn('Harald Beck', self.html)


if __name__ == '__main__':
    unittest.main()

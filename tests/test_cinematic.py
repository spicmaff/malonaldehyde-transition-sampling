"""Cinematic additions preserve source meaning and fail closed at extension points."""
import copy
import json
import math
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'site'), str(ROOT/'tools')]
import cinematic
import build_research_site

class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.tags=[]; self.feed(html)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

class CinematicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.out=Path(cls.temp.name)/'site'
        build_research_site.build(cls.out);cls.html=(cls.out/'index.html').read_text()
        cls.tags=Tags(cls.html).tags
        cls.data=json.loads((ROOT/'data/optimization_story/v001/OPTIMIZATION_STORY.json').read_text())
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def test_exact_source_partition(self):
        cells=[a['data-cin-cell'] for _,a in self.tags if 'data-cin-cell' in a]
        self.assertEqual(len(cells),self.data['theory']['architecture']['nominal_parameters'])
        for b in self.data['theory']['architecture']['parameter_blocks']:
            self.assertEqual(cells.count(b['id']),b['count'])
    def test_snapshot_positions_derive_from_exact_J(self):
        states={s['id']:s for s in self.data['theory']['main4500']['states']}
        marks=[a for _,a in self.tags if 'data-cin-snapshot' in a]
        self.assertEqual([a['data-cin-snapshot'] for a in marks],['S0','S2','S4'])
        for a in marks:
            v=float(a['data-cin-j']);self.assertEqual(v,states[a['data-cin-snapshot']]['native_J'])
            self.assertAlmostEqual(float(a['style'][5:-1]),(math.log10(v)+5)*50,places=10)
    def test_fixed_scale_and_snapshot_scope_are_visible(self):
        text=cinematic.snapshots(self.data['theory']['main4500'])
        for word in ['Fixed log','10⁻⁵','10⁻³','S1','S3 has no measured J']:
            self.assertIn(word,text)
    def test_snapshot_rejects_nonfinite_and_out_of_range(self):
        for value in [float('nan'),float('inf'),-1,0,1,'0.1']:
            e=copy.deepcopy(self.data['theory']['main4500']);e['states'][0]['native_J']=value
            with self.assertRaises(ValueError): cinematic.snapshots(e)
    def test_partition_change_fails_closed(self):
        a=copy.deepcopy(self.data['theory']['architecture']);a['parameter_blocks'][0]['count']+=1
        with self.assertRaises(ValueError): cinematic.atlas(a)
    def test_native_rail_is_not_diagnostic_reader_order(self):
        rail=[a for _,a in self.tags if 'data-cin-step' in a]
        self.assertEqual([a['data-cin-step'] for a in rail],self.data['theory']['main4500']['native_order'])
        self.assertIn('Not measured',cinematic.native_rail(self.data['theory']['main4500']))
    def test_new_controls_disabled_without_enhancement(self):
        controls=[a for _,a in self.tags if 'data-cin-step' in a or 'data-cin-group-select' in a]
        self.assertEqual(len(controls),9)
        self.assertTrue(all('disabled' in a for a in controls))
    def test_all_old_routes_and_measured_markers_remain(self):
        self.assertEqual(sum('data-page' in a for _,a in self.tags),12)
        self.assertEqual(sum('data-opt-select' in a for _,a in self.tags),7)
        self.assertEqual(sum('data-opt-mark' in a for _,a in self.tags),6)
    def test_no_duplicate_ids(self):
        ids=[a['id'] for _,a in self.tags if 'id' in a];self.assertEqual(len(ids),len(set(ids)))
    def test_transaction_has_alternative_outcomes(self):
        html=cinematic.transaction()
        for text in ['Two alternative outcomes','If qualified','Otherwise','Complete rollback']:
            self.assertIn(text,html)
    def test_math_and_evidence_limits_remain(self):
        self.assertIn(self.data['t1']['statuses']['visible_limit'],self.html)
        self.assertIn('currently unavailable after a failed persistent save',self.html)
        self.assertIn('not a parameter landscape',self.html)
    def test_assets_exactly_copied(self):
        for name in ['cinematic.css','cinematic.mjs']:
            self.assertEqual((ROOT/'site'/name).read_bytes(),(self.out/name).read_bytes())
    def test_extension_rejects_missing_and_duplicate_anchors(self):
        for document in ['','needle needle']:
            with self.assertRaises(ValueError):cinematic.replace_one(document,'needle','new')
        with self.assertRaises(ValueError):cinematic.refine_document(self.html,self.data)
    def test_no_new_runtime_fetch_or_solver(self):
        s=(ROOT/'site/cinematic.mjs').read_text()
        for forbidden in ['fetch(', 'setInterval(', 'eval(', 'new Function(']:self.assertNotIn(forbidden,s)
        self.assertIn('data-optimization-ready',s)
    def test_chapter_guide_has_six_real_targets(self):
        self.assertEqual(self.html.count('id="cin-reading-position"'), 1)
        self.assertIn('class="cin-chapter-map"', self.html)
        for target in ['opt-parameters','opt-episode','opt-checkpoints','opt-candidate','opt-evidence','opt-next-study']:
            self.assertEqual(self.html.count('id="'+target+'"'), 1)
            self.assertIn('href="#'+target+'"', self.html)
    def test_hero_ratio_is_explicit_after_over_before(self):
        self.assertIn('Ratio S2 / S0 · native training', self.html)
        self.assertNotIn('higher native training', self.html)
    def test_reading_compass_has_no_navigation_or_focus_side_effect(self):
        source=(ROOT/'site/cinematic.mjs').read_text().split('// Reading position is a quiet location cue.')[1]
        for forbidden in ['location.hash =', '.focus(', '.scrollIntoView(', 'setTimeout(', 'setInterval(', 'fetch(']:
            self.assertNotIn(forbidden,source)
        self.assertIn("{passive: true}",source)
        self.assertIn("attributeFilter: ['class']",source)
        self.assertIn("Math.max(documentPadding",source)
        self.assertIn("--cin-document-scroll-padding",source)
        self.assertIn("scroll-margin-top:max(0px",(ROOT/'site/cinematic.css').read_text())
    def test_keyboard_navigation_reveals_focused_not_only_active_link(self):
        source=(ROOT/'site/cinematic.mjs').read_text()
        self.assertIn("navigation.addEventListener('focusin'", source)
        self.assertIn("event.target.closest('a[data-route]')", source)
        helper=source.split('function revealNavigationLink(current) {',1)[1].split('\n}',1)[0]
        self.assertIn('navigation.scrollLeft', helper)
        for forbidden in ['.focus(', '.scrollIntoView(', 'location.hash']:
            self.assertNotIn(forbidden, helper)
    def test_five_public_payloads_remain_identical(self):
        for p in (ROOT/'data/optimization_story/v001').iterdir():
            if p.is_file():self.assertEqual(p.read_bytes(),(self.out/'data/optimization'/p.name).read_bytes())

if __name__=='__main__':unittest.main()

"""Offline regression tests for the English cinematic exhibit. No new physics."""
from __future__ import annotations
import ast
import hashlib
import json
import math
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import build_research_site as build
from verify_train119_diagnostic import force_metrics, terminal_pw

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.links=[]; self.language=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='html':self.language=a.get('lang')
        for key in ('src','href','poster'):
            if key in a:self.links.append((tag,key,a[key]))

class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.out=Path(cls.tmp.name)/'site'
        cls.data=build.build(cls.out)
        cls.html=(cls.out/'index.html').read_text()
        cls.parsed=Links();cls.parsed.feed(cls.html)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_expected_scientific_snapshot(self):
        self.assertEqual(self.data['science_commit'],'f44d28cc0b13defb747f625376b083055b577629')
    def test_original_metrics_preserved(self):
        self.assertAlmostEqual(self.data['metrics']['Basin60']['barrier_error'],35.245734070031176,9)
        self.assertAlmostEqual(self.data['metrics']['Targeted60']['force_rmse'],.07868490481909636,12)
    def test_geometry_supports(self):
        self.assertEqual(len(self.data['molecule']),9)
        self.assertEqual([m['image'] for m in self.data['molecule']],list(range(1,10)))
        for m in self.data['molecule']:
            x=m['xyz'];self.assertAlmostEqual(m['q'],math.dist(x[0],x[1])-math.dist(x[7],x[1]),12)
    def test_scaffold_contraction(self):
        d=self.data
        self.assertAlmostEqual(d['contraction_percent'],4.366068950778545,10)
        self.assertAlmostEqual(d['contraction_A'],d['molecule'][0]['roo']-d['molecule'][4]['roo'],12)
    def test_profiles_have_individual_lower_endpoint_zero(self):
        for values in self.data['profiles'].values():self.assertAlmostEqual(min(values[0],values[-1]),0,12)
    def test_profile_residual_is_not_barrier_error(self):
        m=self.data['metrics']['Train119']
        self.assertAlmostEqual(m['barrier_error'],.122995698802697,9)
        self.assertAlmostEqual(m['profile_max_abs_error'],.5040717755946389,9)
        self.assertGreater(m['profile_max_abs_error'],m['barrier_error'])
    def test_training_budget_and_roles(self):
        for branch,values in self.data['sampling'].items():
            self.assertEqual(len(values),60)
            self.assertEqual(sum(p['shared'] for p in values),36)
            self.assertEqual(len({p['id'] for p in values}),60)
    def test_all_paired_seed_strings(self):
        values=self.data['seeds'];self.assertEqual(len(values),10)
        both=0
        for i in range(5):
            b=next(r for r in values if r['index']==i and r['model']=='basin')
            t=next(r for r in values if r['index']==i and r['model']=='targeted')
            self.assertIsInstance(b['seed'],str);self.assertEqual(b['seed'],t['seed'])
            both+=t['barrier']<b['barrier'] and t['force']<b['force']
        self.assertEqual(both,3)
    def test_stop_and_crossings_preserved(self):
        self.assertEqual(self.data['stop'],1.0000012996964838)
        self.assertEqual([r['index'] for r in self.data['replay'] if r['gamma']>self.data['stop']],[143,144,145,146,147])
    def test_297_force_components_come_from_primary_output(self):
        self.assertEqual(len(self.data['forces']),11)
        for frame in self.data['forces']:
            p=ROOT/self.data['evidence'][frame['source_key']]['path']
            _,forces,_=terminal_pw(p.read_text())
            self.assertEqual(forces,frame['pbe'])
            error=[[b-a for a,b in zip(x,y)] for x,y in zip(frame['pbe'],frame['mtp'])]
            self.assertEqual(error,frame['error'])
            metric=force_metrics(frame['pbe'],frame['mtp'])['force_component_RMSE_eV_A']
            self.assertAlmostEqual(metric,frame['rmse'],13)
    def test_h2_and_c3_are_not_conflated(self):
        for f in self.data['forces']:
            self.assertEqual(f['elements'][1],'H');self.assertEqual(f['elements'][2],'C')
        self.assertIn('H2* is not C3.',self.html)
    def test_known_overlap_and_failures_preserved(self):
        self.assertEqual(len(self.data['overlaps']),2)
        self.assertEqual(self.data['boundaries']['Train119_status'],'STATIC_APPLICABILITY_FAIL')
        self.assertEqual(self.data['boundaries']['seed_status'],'SEED_SENSITIVE')
        self.assertFalse(self.data['boundaries']['MD'])
    def test_sources_are_pinned_and_have_real_hashes(self):
        for r in self.data['evidence'].values():
            self.assertIn('/blob/'+build.BASE+'/',r['url'])
            self.assertEqual(hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest(),r['sha256'])
    def test_english_only_visible_source(self):
        self.assertEqual(self.parsed.language,'en')
        self.assertIsNone(re.search('[\u0400-\u04ff]',self.html))
        for p in ['site/pages.py','site/app.mjs','site/longread.en.md']:
            self.assertIsNone(re.search('[\u0400-\u04ff]',(ROOT/p).read_text()),p)
        self.assertNotIn('hreflang="ru"',self.html)
        self.assertFalse((self.out/'longread.ru.md').exists())
    def test_old_russian_url_redirect_preserves_hash(self):
        s=(self.out/'ru.html').read_text()
        self.assertIn('location.hash',s);self.assertIn('lang="en"',s)
        self.assertLess(len(s),800);self.assertNotIn('<nav',s)
    def test_no_old_russian_media_in_build(self):
        self.assertFalse((self.out/'media').exists())
        self.assertNotIn('media/01_proton_path.mp4',self.html)
    def test_no_duplicate_dom_ids(self):
        self.assertEqual(len(self.parsed.ids),len(set(self.parsed.ids)))
    def test_local_links_and_anchors_exist(self):
        for tag,key,url in self.parsed.links:
            if url.startswith(('https:','http:','mailto:','data:')):continue
            if url.startswith('#'):
                self.assertIn(url[1:].split('?')[0],self.parsed.ids,url)
            elif url not in ('./',''):
                self.assertTrue((self.out/url.split('#')[0].split('?')[0]).is_file(),url)
    def test_longread_and_sources_readable_without_js(self):
        self.assertIn('Twenty-seven numbers',self.html)
        self.assertGreater(len(re.findall('<h2 id="read-',self.html)),9)
        self.assertGreater(self.html.count('<table>'),4)
        self.assertIn('No prospective final holdout',self.html)
    def test_curated_literature_has_complete_records(self):
        refs=build.literature();self.assertGreaterEqual(len(refs),12)
        for r in refs:
            self.assertTrue(r['url'].startswith('https://'));self.assertTrue(r['access']);self.assertTrue(r['limitation'])
        self.assertIn('2026',str(refs))
    def test_vendored_renderer_has_license_and_integrity(self):
        root=ROOT/'site/vendor/three';m=json.loads((root/'manifest.json').read_text())
        self.assertEqual(m['license'],'MIT')
        for row in m['files']:self.assertEqual(hashlib.sha256((root/row['path']).read_bytes()).hexdigest(),row['sha256'])
    def test_build_has_no_external_font_files(self):
        self.assertFalse(any(p.suffix.lower() in ('.ttf','.otf','.woff','.woff2') for p in self.out.rglob('*')))
    def test_generated_files_match_manifest(self):
        m=json.loads((self.out/'build-manifest.json').read_text())
        for name,sha in m.items():self.assertEqual(hashlib.sha256((self.out/name).read_bytes()).hexdigest(),sha,name)
    def test_repeat_build_is_identical(self):
        old=(self.out/'build-manifest.json').read_bytes();build.build(self.out)
        self.assertEqual(old,(self.out/'build-manifest.json').read_bytes())
    def test_unsafe_output_is_rejected(self):
        with self.assertRaises(ValueError):build.build(ROOT)
        with self.assertRaises(ValueError):build.build(ROOT/'site')
    def test_occupied_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'owner.txt').write_text('keep')
            with self.assertRaises(ValueError):build.build(p)
            self.assertEqual((p/'owner.txt').read_text(),'keep')
    def test_two_english_films_have_verified_sources(self):
        films=self.data.get('films',[])
        self.assertEqual(len(films),2)
        self.assertEqual(sum(f['frames'] for f in films),2520)
        for film in films:
            self.assertEqual(film['fps'],60)
            self.assertEqual(film['width'],1920);self.assertEqual(film['height'],1080)
            self.assertFalse(film['physical_time'])
            for key,sha in [('file','sha256'),('poster','poster_sha256'),('captions','captions_sha256')]:
                self.assertEqual(hashlib.sha256((self.out/film[key]).read_bytes()).hexdigest(),film[sha])
    def test_scene_captions_are_english(self):
        for f in self.data['films']:
            c=(self.out/f['captions']).read_text()
            self.assertTrue(c.startswith('WEBVTT'))
            self.assertIsNone(re.search('[\u0400-\u04ff]',c))
    def test_download_has_expanded_source_links(self):
        s=(self.out/'longread.en.md').read_text()
        self.assertNotIn('@sources:',s);self.assertNotIn('@papers:',s)
        self.assertIn('https://doi.org/',s)
    def test_python311_grammar(self):
        for p in ('site/pages.py','tools/build_research_site.py','tools/site/test_site.py'):
            ast.parse((ROOT/p).read_text(),feature_version=(3,11))

if __name__=='__main__':unittest.main(verbosity=2)

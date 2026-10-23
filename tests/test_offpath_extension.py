"""Invariants for additive publication/visual extension; all work uses stored data."""
import csv,hashlib,json,os,sys,tempfile,unittest,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'site')]
import build_research_site, build_offpath, offpath_page, render_completed_study_figures as figures
from verify_pbe14_offpath import verify

class ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.out=Path(cls.tmp.name)/'site'
        cls.old=build_research_site.build(cls.out)
        cls.new=json.loads((cls.out/'data/offpath.json').read_text())
        cls.html=(cls.out/'index.html').read_text()

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_namespace_cardinality(self):
        self.assertEqual(self.old['schema'],'proton-potential-cinematic-v2')
        self.assertEqual(len(self.old['forces']),11)
        self.assertEqual(self.new['schema'],'proton-offpath-v1')
        self.assertEqual(len(self.new['benchmark']['case_rows']),280)

    def test_all_historical_pages_and_aliases(self):
        for route in ['overview','molecule','sampling','landscape','seeds','train119','forces','story','longread','reproduce','offpath']:
            self.assertEqual(self.html.count('section id="'+route+'"'),1)
            self.assertEqual(self.html.count('data-route="'+route+'"'),1)
        self.assertIn("raw==='applicability'",(ROOT/'site/core.mjs').read_text())
        self.assertIn("raw.startsWith('read-')",(ROOT/'site/core.mjs').read_text())

    def test_preserved_science_meanings(self):
        self.assertIn('3 of 5',self.html)
        self.assertIn('The coverage criterion still fails.',self.html)
        self.assertEqual(self.old['boundaries']['Train119_status'],'STATIC_APPLICABILITY_FAIL')
        self.assertIn('SEED_SENSITIVE',self.html)
        self.assertEqual(self.new['benchmark']['primary']['targeted_better_count'],4)
        self.assertEqual(self.old['boundaries']['MD'],False)
        self.assertEqual(self.new['claims']['deployment_validated'],False)

    def test_fourteen_geometry_identity(self):
        ids=[g['id'] for g in self.new['benchmark']['geometries']]
        self.assertEqual(len(ids),14);self.assertEqual(len(set(ids)),14)
        self.assertNotIn('L04m',ids);self.assertNotIn('T04m',ids)

    def test_original_bytes_protected(self):
        m=json.loads((ROOT/'provenance/COMPLETED_EXTENSION_BASELINE.json').read_text())
        self.assertEqual(m['base_commit'],'83f52b0fc6dd1b8d5af7832c657fa5361887fe54')
        self.assertGreater(len(m['protected_files']),280)
        from presentation_review import verify_registered_assets
        verify_registered_assets(ROOT)
        delta={r['repository_path']:r for r in csv.DictReader((ROOT/'provenance/EDITORIAL_REDESIGN_DELTA.tsv').read_text().splitlines(),delimiter='\t')}
        independent={r['repository_path']:r for r in csv.DictReader((ROOT/'provenance/INDEPENDENT_REVIEW_DELTA.tsv').read_text().splitlines(),delimiter='\t')}
        acceptance={r['repository_path']:r for r in csv.DictReader((ROOT/'provenance/FINAL_ACCEPTANCE_DELTA.tsv').read_text().splitlines(),delimiter='\t')}
        from publication_metadata import load_metadata_overrides
        metadata=load_metadata_overrides(ROOT)
        interface={'site/app.mjs','site/charts.mjs','site/core.mjs','site/molecule.mjs','site/literature.json','docs/RESEARCH_SITE.md'}
        for p,h in m['protected_files'].items():
            if p in interface:
                self.assertEqual(delta[p]['previous_repository_sha256'],h,p)
                expected=delta[p]['repository_sha256']
            else:expected=h
            if p in independent:
                self.assertEqual(independent[p]['previous_repository_sha256'],expected,p)
                expected=independent[p]['repository_sha256']
            if p in acceptance:
                self.assertEqual(acceptance[p]['previous_repository_sha256'],expected,p)
                expected=acceptance[p]['repository_sha256']
            if p in metadata:
                self.assertEqual(metadata[p]['previous_repository_sha256'],expected,p)
                expected=metadata[p]['repository_sha256']
            self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),expected,p)

    def test_new_sources_exist_with_sha(self):
        for p,h in self.new['source_hashes'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h)
        self.assertEqual(len(self.new['nearest_geometry']),14)

    def test_source_ref_no_html_injection(self):
        previous=os.environ.get('PROTON_SOURCE_REF')
        try:
            os.environ['PROTON_SOURCE_REF']='bad<script>'
            with self.assertRaises(ValueError):build_offpath.payload()
        finally:
            if previous is None:os.environ.pop('PROTON_SOURCE_REF',None)
            else:os.environ['PROTON_SOURCE_REF']=previous

    def test_static_results_and_downloads(self):
        self.assertIn('−0.146135',self.html)
        self.assertIn('off-block-row',self.html)
        self.assertIn('All 280',self.html)
        self.assertEqual(len((self.out/'data/offpath/PER_GEOMETRY_280.tsv').read_text().strip().splitlines()),281)
        self.assertIn('independent',self.html.lower())

    def test_optional_diagnostic_not_new_primary(self):
        self.assertNotIn('END_MAIN',self.new['benchmark']['case_rows'][0])
        self.assertEqual(self.new['benchmark']['n_models'],20)
        self.assertEqual(self.new['optimizer']['model_count'],20)

    def test_literature_nearest_prior_art(self):
        refs=json.loads((ROOT/'site/literature.json').read_text())
        self.assertEqual(len(refs),21)
        self.assertTrue({'brezina2023','transition1x2022','landscape172026'}<={r['id'] for r in refs})
        self.assertTrue(all(r['access'] and r['limitation'] for r in refs))
        self.assertNotIn('@study:',(self.out/'longread.en.md').read_text())

    def test_vector_figures_rebuild_exactly(self):
        d=verify();rendered=figures.figures(d)
        self.assertEqual(len(rendered),4)
        for name,text in rendered.items():
            ET.fromstring(text)
            self.assertEqual(text,(ROOT/'figures/completed_studies_v001'/name).read_text())
        m=json.loads((ROOT/'figures/completed_studies_v001/FIGURE_MANIFEST.json').read_text())
        for name,h in m['figures'].items():self.assertEqual(hashlib.sha256((ROOT/'figures/completed_studies_v001'/name).read_bytes()).hexdigest(),h)

    def test_builder_deterministic_no_science(self):
        before=(self.out/'data/offpath.json').read_bytes()
        build_research_site.build(self.out)
        self.assertEqual(before,(self.out/'data/offpath.json').read_bytes())
        self.assertEqual(self.new['claims']['new_scientific_calls'],0)
        self.assertEqual(self.new['benchmark']['new_scientific_calls'],0)

if __name__=='__main__':unittest.main()

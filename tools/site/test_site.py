"""Scientific and publication regressions for the English cinematic exhibit."""
from __future__ import annotations
import ast, hashlib, json, math, re, sys, tempfile, unittest
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import build_research_site as build
from verify_train119_diagnostic import parse_cfg, terminal_pw, force_metrics
class Tags(HTMLParser):
 def __init__(self,text):super().__init__();self.ids=[];self.links=[];self.lang=[];self.feed(text)
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if 'id' in d:self.ids.append(d['id'])
  if tag=='html':self.lang.append(d.get('lang'))
  for k in ('href','src'):
   if k in d:self.links.append(d[k])
class SiteTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.out=Path(cls.tmp.name)/'site';cls.d=build.build(cls.out);cls.html=(cls.out/'index.html').read_text();cls.tags=Tags(cls.html)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_english_only_html(self):
  self.assertEqual(self.tags.lang,['en']);self.assertIsNone(re.search('[\u0400-\u04ff]',self.html));self.assertNotIn('hreflang',self.html);self.assertNotIn('longread.ru',self.html)
 def test_english_assets(self):
  for p in self.out.rglob('*'):
   if p.suffix in {'.html','.md','.json','.mjs','.css','.svg'}:self.assertIsNone(re.search('[\u0400-\u04ff]',p.read_text()),str(p))
 def test_no_language_runtime(self):
  self.assertNotIn('lang-switch',self.html);self.assertNotIn('ru.html#',self.html);self.assertFalse((self.out/'longread.ru.md').exists())
 def test_legacy_redirect(self):
  t=(self.out/'ru.html').read_text();self.assertLess(len(t),1000);self.assertIn('location.hash',t);self.assertIn('noindex',t);self.assertNotIn('app.mjs',t)
 def test_unique_ids(self):self.assertEqual(len(self.tags.ids),len(set(self.tags.ids)))
 def test_links(self):
  for u in self.tags.links:
   if u.startswith('#'):self.assertIn(u[1:],self.tags.ids)
   elif not u.startswith(('https:','http:','mailto:','data:')):self.assertTrue((self.out/u.split('#')[0]).is_file(),u)
 def test_nine_image_geometry(self):
  self.assertEqual(len(self.d['molecule']),9)
  for r in self.d['molecule']:
   self.assertEqual(len(r['xyz']),9);x=r['xyz'];self.assertAlmostEqual(r['q'],math.dist(x[0],x[1])-math.dist(x[7],x[1]),places=12)
 def test_original_barriers(self):
  self.assertAlmostEqual(self.d['metrics']['Basin60']['barrier_error'],35.245734070031176,places=8)
  self.assertAlmostEqual(self.d['metrics']['Targeted60']['barrier_error'],4.10039360394876,places=8)
 def test_original_force_metric(self):self.assertAlmostEqual(self.d['metrics']['Targeted60']['force_rmse'],.07868490481909636,places=12)
 def test_scaffold(self):self.assertAlmostEqual(self.d['scaffold']['contraction_percent'],4.366068950778546,places=10)
 def test_train119_not_mixed_budget(self):
  self.assertEqual(set(self.d['sampling']),{'basin','targeted'});self.assertIn('separate',self.html.lower());self.assertIn('adaptive',self.html.lower())
 def test_membership(self):
  for rows in self.d['sampling'].values():self.assertEqual(len(rows),60);self.assertEqual(sum(r['shared'] for r in rows),36)
 def test_projection_domain_contains_all_training_data(self):
  for rows in self.d['sampling'].values():
   for r in rows:self.assertTrue(-.65<=r['q']<=.65);self.assertTrue(2.47<=r['roo']<=2.55)
 def test_five_seed_pairs_no_precision_loss(self):
  self.assertEqual(len(self.d['seeds']),10)
  self.assertEqual({r['index'] for r in self.d['seeds']},set(range(5)))
  for r in self.d['seeds']:self.assertIsInstance(r['seed'],str);self.assertTrue(r['seed'].isdigit())
 def test_seed_results(self):
  wins=0
  for i in range(5):
   a=next(r for r in self.d['seeds'] if r['index']==i and r['model']=='basin');b=next(r for r in self.d['seeds'] if r['index']==i and r['model']=='targeted');wins+=b['barrier']<a['barrier'] and b['force']<a['force']
  self.assertEqual(wins,3)
 def test_force_frames_reparsed_from_primary_outputs(self):
  self.assertEqual(len(self.d['force_frames']),11)
  for frame in self.d['force_frames']:
   path=ROOT/build.DROOT/'references'/f"replay{frame['index']:03d}"/'pw.out';en,f,_=terminal_pw(path.read_text());self.assertEqual(frame['pbe'],f)
   res=force_metrics(f,frame['mtp']);self.assertAlmostEqual(res['force_component_RMSE_eV_A'],frame['rmse'],places=12)
   for i in range(9):
    for j in range(3):self.assertEqual(frame['difference'][i][j],frame['mtp'][i][j]-frame['pbe'][i][j])
 def test_force_source_hashes(self):
  for f in self.d['force_frames']:
   suffix=f"references/replay{f['index']:03d}/pw.out";entries=[v for v in self.d['evidence'].values() if v['path'].endswith(suffix)];self.assertEqual(len(entries),1)
 def test_metric_normalization(self):
  for k,v in self.d['profiles'].items():self.assertEqual(min(v[0],v[-1]),0)
  self.assertAlmostEqual(max(map(abs,self.d['residuals']['Train119'])),.504071777253,places=7)
 def test_two_endpoints(self):self.assertEqual(len(self.d['overlaps']),2);self.assertEqual([r['training_index'] for r in self.d['overlaps']],[9,10])
 def test_historical_statuses(self):
  self.assertEqual(self.d['boundaries']['seed_status'],'SEED_SENSITIVE');self.assertEqual(self.d['boundaries']['Train119_status'],'STATIC_APPLICABILITY_FAIL');self.assertFalse(self.d['boundaries']['MD'])
 def test_frozen_crossings(self):self.assertEqual([r['index'] for r in self.d['replay'] if r['gamma']>self.d['stop']],[143,144,145,146,147])
 def test_source_hashes(self):
  for r in self.d['evidence'].values():self.assertEqual(hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest(),r['sha256']);self.assertIn(build.BASE,r['url'])
 def test_eight_guided_sequences(self):
  for k in ['hero','molecule','sampling','landscape','seeds','train119','forces','story']:self.assertIn('play-'+k,self.tags.ids)
 def test_longread_and_literature(self):
  self.assertGreater(len((ROOT/'site/longread.en.md').read_text().split()),2500);self.assertGreaterEqual(len(self.d['literature']),18)
  for r in self.d['literature']:self.assertTrue(r['url'].startswith('https://'));self.assertIn('access',r);self.assertIn('note',r)
 def test_no_historical_russian_media_in_deployment(self):
  self.assertFalse((self.out/'media').exists());self.assertFalse((self.out/'assets').exists())
 def test_deterministic_rebuild(self):
  other=Path(self.tmp.name)/'second';build.build(other);self.assertEqual((self.out/'build-manifest.json').read_bytes(),(other/'build-manifest.json').read_bytes())
 def test_manifest_covers_output(self):
  manifest=json.loads((self.out/'build-manifest.json').read_text());files={p.relative_to(self.out).as_posix() for p in self.out.rglob('*') if p.is_file() and p.name!='build-manifest.json'};self.assertEqual(set(manifest),files)
  for rel,h in manifest.items():self.assertEqual(hashlib.sha256((self.out/rel).read_bytes()).hexdigest(),h)
 def test_no_network_or_scientific_calls_in_builder(self):
  tree=ast.parse((ROOT/'tools/build_research_site.py').read_text());imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]+[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names];self.assertFalse(set(imports)&{'requests','urllib.request','subprocess','socket'})
 def test_safe_build_directory(self):
  with self.assertRaises(ValueError):build.build(ROOT)
 def test_unknown_existing_directory_not_deleted(self):
  path=Path(self.tmp.name)/'unrelated';path.mkdir();(path/'keep.txt').write_text('keep')
  with self.assertRaises(ValueError):build.build(path)
  self.assertTrue((path/'keep.txt').exists())
 def test_saved_quantum_boundary(self):
  self.assertGreater(self.d['quantum_boundary']['E1_above_barrier_meV'],1.25)
  self.assertEqual(self.d['quantum_boundary']['classification'],'only_ground_state_below_barrier')
  self.assertFalse(self.d['quantum_boundary']['experimental_validation'])
 def test_english_cinema_hashes_and_scope(self):
  payload=json.loads((ROOT/'site/cinema/manifest.json').read_text())
  self.assertEqual(len(payload['films']),3)
  self.assertEqual(payload['new_physical_calls'],0)
  for film in payload['films']:
   self.assertEqual(film['fps'],60);self.assertEqual(film['width'],1920);self.assertTrue(film['english_on_frame_text'])
   self.assertEqual(hashlib.sha256((ROOT/'site/cinema'/film['file']).read_bytes()).hexdigest(),film['sha256'])
   self.assertEqual(hashlib.sha256((ROOT/'site/cinema'/film['poster']).read_bytes()).hexdigest(),film['poster_sha256'])
 def test_python311_source_grammar(self):
  for p in [ROOT/'site/pages.py',ROOT/'tools/build_research_site.py']:ast.parse(p.read_text(),feature_version=(3,11))
if __name__=='__main__':unittest.main(verbosity=2)

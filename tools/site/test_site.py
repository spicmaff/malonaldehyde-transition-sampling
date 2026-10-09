"""Offline scientific and publication regressions. Run from the repository root."""
import csv, hashlib, importlib.util, json, math, re, sys, tempfile, unittest
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import build_research_site as build
class Document(HTMLParser):
 def __init__(self):super().__init__();self.ids=[];self.links=[];self.sources=[];self.lang=None
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.append(a['id'])
  if tag=='html':self.lang=a.get('lang')
  if tag=='a' and 'href' in a:self.links.append(a['href'])
  if tag in ('script','source','img','link'):
   v=a.get('src') or (a.get('href') if tag=='link' and a.get('rel') in ('stylesheet','icon') else None)
   if v:self.sources.append(v)
class SiteTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.out=Path(cls.tmp.name)/'build';cls.d=build.build(cls.out)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_two_languages_have_all_ten_routes(self):
  for lang,f in [('en','index.html'),('ru','ru.html')]:
   p=Document();p.feed((self.out/f).read_text());self.assertEqual(p.lang,lang)
   self.assertEqual(len(p.ids),len(set(p.ids)))
   for r in ['overview','molecule','sampling','landscape','seeds','applicability','train119','story','longread','reproduce']:self.assertIn(r,p.ids)
 def test_local_assets_and_links_exist(self):
  for f in ['index.html','ru.html']:
   p=Document();p.feed((self.out/f).read_text())
   for ref in p.sources+p.links:
    if ref.startswith(('https:','http:')):continue
    name=ref.split('#')[0]
    if name:self.assertTrue((self.out/name).is_file(),ref)
    elif ref[1:].split('/')[0]:self.assertIn(ref[1:].split('/')[0],p.ids)
 def test_source_hashes(self):
  for x in self.d['evidence'].values():
   self.assertEqual(x['sha256'],hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest())
   self.assertIn(build.BASE,x['url'])
 def test_nine_geometries_qpt_from_positions(self):
  self.assertEqual(len(self.d['molecule']),9)
  for m in self.d['molecule']:
   self.assertEqual(len(m['xyz']),9)
   q=math.dist(m['xyz'][0],m['xyz'][1])-math.dist(m['xyz'][7],m['xyz'][1])
   self.assertAlmostEqual(m['q'],q,places=14)
 def test_original_metrics_unchanged(self):
  self.assertAlmostEqual(self.d['metrics']['Basin60']['barrier_error'],35.245734070031176,places=8)
  self.assertAlmostEqual(self.d['metrics']['Targeted60']['force_rmse'],.07868490481909636,places=12)
 def test_lower_endpoint_reference(self):
  for values in self.d['profiles'].values():self.assertEqual(min(values[0],values[-1]),0.)
  self.assertLess(min(self.d['profiles']['Basin60']),0.)
 def test_budget_and_shared_membership(self):
  for x in self.d['sampling'].values():
   self.assertEqual(len(x),60);self.assertEqual(sum(c['shared'] for c in x),36)
  a={r['id'] for r in self.d['sampling']['basin']};b={r['id'] for r in self.d['sampling']['targeted']};self.assertEqual(len(a&b),36)
 def test_five_seed_wins_and_exact_uint64(self):
  rows=self.d['seeds'];wins=[0,0,0]
  for i in range(5):
   a=next(r for r in rows if r['index']==i and r['model']=='basin');b=next(r for r in rows if r['index']==i and r['model']=='targeted')
   self.assertIsInstance(a['seed'],str);self.assertEqual(a['seed'],b['seed'])
   be=b['barrier']<a['barrier'];fe=b['force']<a['force'];wins=[wins[0]+be,wins[1]+fe,wins[2]+(be and fe)]
  self.assertEqual(wins,[4,3,3])
 def test_crossings_not_rounded_before_comparison(self):
  self.assertEqual([r['index'] for r in self.d['replay'] if r['gamma']>self.d['stop']],[143,144,145,146,147])
 def test_local_errors_and_scope(self):
  self.assertEqual(len(self.d['local']),11)
  self.assertTrue(all(r['force_component_RMSE_eV_A']<self.d['a2'] for r in self.d['local']))
  self.assertTrue(any(r['max_abs_component_eV_A']>self.d['a2'] for r in self.d['local']))
  self.assertEqual(self.d['boundaries']['Train119_status'],'STATIC_APPLICABILITY_FAIL')
  self.assertFalse(self.d['boundaries']['independent_Train119_test'])
 def test_endpoint_overlap_and_model_separation(self):
  self.assertEqual([r['training_index'] for r in self.d['overlaps']],[9,10])
  self.assertEqual(len(self.d['profiles']),4)
  for f in ['index.html','ru.html']:
   s=(self.out/f).read_text();section=s.split('id="landscape"',1)[1].split('</section>',1)[0]
   self.assertNotIn('data-series="Train119"',section)
 def test_longread_length_and_cited_chapters(self):
  for lang in ['en','ru']:
   raw=(ROOT/f'site/longread.{lang}.md').read_text()
   self.assertEqual(raw.count('\n## '),10);self.assertEqual(raw.count('@sources:'),10)
   self.assertGreater(len(raw.split()),1700)
   html=(self.out/('index.html' if lang=='en' else 'ru.html')).read_text()
   self.assertNotIn('@sources:',html);self.assertEqual(html.count('class="chapter-source"'),10)
 def test_media_identity(self):
  media=json.loads((ROOT/'site/media/manifest.json').read_text())
  self.assertEqual(len(media),5)
  for item in media:self.assertEqual(hashlib.sha256((self.out/'media'/item['file']).read_bytes()).hexdigest(),item['sha256'])
 def test_build_is_byte_deterministic(self):
  other=Path(self.tmp.name)/'second';build.build(other)
  self.assertEqual((self.out/'build-manifest.json').read_bytes(),(other/'build-manifest.json').read_bytes())
 def test_no_network_runtime_dependencies(self):
  for f in ['index.html','ru.html']:
   p=Document();p.feed((self.out/f).read_text());self.assertFalse(any(x.startswith(('http:','https:','//')) for x in p.sources))
 def test_no_blind_payload_or_private_paths(self):
  for p in self.out.rglob('*'):
   if not p.is_file():continue
   self.assertNotIn('blind12',p.name.lower())
   if p.suffix in ['.json','.html','.mjs','.css','.md','.txt']:
    s=p.read_text();self.assertIsNone(re.search(r'/home/(?!USER/)[^/\s]+/',s));self.assertNotIn('/mnt/c/Users/',s)
if __name__=='__main__':unittest.main(verbosity=2)

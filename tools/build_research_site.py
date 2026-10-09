#!/usr/bin/env python3
"""Build a English-only static research exhibit from the public, frozen evidence.
No network, inference, training, selectors or physical simulation. Python 3.11+.
"""
from __future__ import annotations
import argparse, csv, hashlib, html, json, math, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from verify_train119_diagnostic import parse_cfg, verify, force_metrics, STOP, A2
BASE = 'f44d28cc0b13defb747f625376b083055b577629'
REPO = 'https://github.com/spicmaff/malonaldehyde-transition-sampling'
DROOT = 'data/post_publication/train119_diagnostic_v001'
SOURCES = {
 'path': 'data/frozen_models_v028/frozen_audit21_labels_v029.cfg',
 'basin': 'data/frozen_models_v028/audit21_predictions_basin_v029.cfg',
 'targeted': 'data/frozen_models_v028/audit21_predictions_targeted_v029.cfg',
 'train_basin': 'data/frozen_models_v028/train_basin60_v028.cfg',
 'train_targeted': 'data/frozen_models_v028/train_targeted60_v028.cfg',
 'seeds': 'data/robustness/v028_seed_robustness_v001/ALL_METRICS.tsv',
 'replay': 'data/visual_story/v001/replay228_gamma.tsv',
 'train119': DROOT+'/OFFLINE_VERIFICATION.json',
 'train119_prediction': DROOT+'/predictions/AUDIT21_STATIC.cfg',
 'train119_manifest': DROOT+'/SOURCE_MANIFEST.json',
 'science': 'data/post_publication/FINAL_SCIENCE_STATUS.json',
 'methods': 'docs/METHODS.md', 'limits':'docs/LIMITATIONS.md',
 'corrections':'docs/TRAIN119_CORRECTIONS.md',
 'diagnostic':'docs/TRAIN119_LOCAL_DIAGNOSTIC.md',
 'roles':'provenance/TRAIN119_DATASET_ROLES.tsv',
 'geometry':'provenance/TRAIN119_GEOMETRY_RELATIONS.tsv',
 'randomness':'docs/TRAINING_RANDOMNESS.md',
 'continuation':'docs/POST_PUBLICATION_CONTINUATION.md',
 'old_story':'presentation/visual-story/v001/text/LONGREAD_FULL.md',
 'media':'docs/VISUAL_STORY.md',
}
def check(ok, message):
 if not ok: raise ValueError(message)
def rows(path):
 with (ROOT/path).open(encoding='utf-8', newline='') as f: return list(csv.DictReader(f,delimiter='\t'))
def cfg(path): return parse_cfg((ROOT/path).read_text(),labels=True)
def coords(c):
 x=c.xyz
 return {'q':math.dist(x[0],x[1])-math.dist(x[7],x[1]),'roo':math.dist(x[0],x[7]),'left':math.dist(x[0],x[1]),'right':math.dist(x[7],x[1])}
def scientific_data():
 verified=verify(ROOT/DROOT)
 check(verified['status']=='PASS_SAVED_PAYLOAD_NUMERICS_AND_MAPPING','Diagnostic verification failed')
 ref=cfg(SOURCES['path']); ii=[i for i,c in enumerate(ref) if c.features.get('audit_subset')=='neb9']
 check(len(ii)==9,'NEB membership')
 mol=[{'image':j+1,'xyz':ref[i].xyz,**coords(ref[i])} for j,i in enumerate(ii)]
 profiles={}; metrics={}
 for k in ('path','basin','targeted','train119_prediction'):
  name={'path':'PBE','basin':'Basin60','targeted':'Targeted60','train119_prediction':'Train119'}[k]
  cc=cfg(SOURCES[k]); es=[cc[i].energy for i in ii]; zero=min(es[0],es[-1])
  profiles[name]=[1000*(e-zero) for e in es]
  ctr=[i for i in ii if abs(coords(ref[i])['q'])<=.15]
  fr=math.sqrt(math.fsum(force_metrics(ref[i].forces,cc[i].forces)['force_component_RMSE_eV_A']**2 for i in ctr)/len(ctr))
  metrics[name]={'barrier':max(profiles[name]),'force_rmse':fr}
 for k,v in metrics.items():v['barrier_error']=abs(v['barrier']-metrics['PBE']['barrier'])
 check(abs(metrics['Basin60']['barrier_error']-35.245734070031176)<1e-8,'Basin metric')
 check(abs(metrics['Targeted60']['force_rmse']-.07868490481909636)<1e-12,'Targeted metric')
 sampling={}; ids={}
 for k in ('basin','targeted'):
  cc=cfg(SOURCES['train_'+k]);check(len(cc)==60,'Training budget')
  ids[k]={c.features.get('candidate_id') for c in cc}
 common=ids['basin'] & ids['targeted'];check(len(common)==36 and None not in common,'Shared set membership')
 for k in ('basin','targeted'):
  sampling[k]=[{'id':c.features['candidate_id'],'shared':c.features['candidate_id'] in common,**coords(c)} for c in cfg(SOURCES['train_'+k])]
 seeds=[]
 for row in rows(SOURCES['seeds']):
  seeds.append({'index':int(row['seed_index']),'seed':row['seed_u64'],'model':row['branch'],'barrier':float(row['lower_endpoint_barrier_abs_error_meV']),'force':float(row['transition_region_force_component_RMSE_eV_A'])})
 check(len(seeds)==10,'Seed cardinality')
 replay=[{'index':int(r['replay_index']),'gamma':float(r['gamma'])} for r in rows(SOURCES['replay'])]
 check([r['index'] for r in replay if r['gamma']>STOP]==[143,144,145,146,147],'Crossings')
 local=verified['local_results'];check(len(local)==11,'PBE comparisons')
 for row in local:check(abs(replay[row['replay_index']-1]['gamma']-row['gamma_saved'])<1e-12,'Saved gamma identity')
 evidence={k:{'path':p,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),'url':f'{REPO}/blob/{BASE}/{p}'} for k,p in SOURCES.items()}
 return {'schema':'malonaldehyde-research-site-v1','science_commit':BASE,'molecule':mol,'profiles':profiles,'metrics':metrics,'sampling':sampling,'seeds':seeds,'replay':replay,'local':local,'stop':STOP,'a2':A2,'static':verified['static'],'overlaps':verified['audit_train_overlap'],'evidence':evidence,'boundaries':{'MD':False,'independent_Train119_test':False,'seed_status':'SEED_SENSITIVE','Train119_status':'STATIC_APPLICABILITY_FAIL','new_scientific_calls':0}}
def md(text):
 """Small escaped Markdown subset used by the curated English longread."""
 out=[];paragraph=[]
 def flush():
  if paragraph:out.append('<p>'+html.escape(' '.join(paragraph))+'</p>');paragraph.clear()
 for line in text.splitlines():
  if line.startswith('## '):flush();out.append('<h2>'+html.escape(line[3:])+'</h2>')
  elif line.startswith('# '):flush()
  elif line.startswith('@sources:'):
   flush()
   keys=line.split(':',1)[1].split()
   check(all(k in SOURCES for k in keys),'Unknown article source')
   out.append('<p class="chapter-source">'+ ' · '.join('<a href="'+REPO+'/blob/'+BASE+'/'+SOURCES[k]+'">'+html.escape(SOURCES[k].split('/')[-1])+'</a>' for k in keys) +'</p>')
  elif not line.strip():flush()
  else:paragraph.append(line.strip())
 flush();return '\n'.join(out)
def build(out):
 data=scientific_data();out.mkdir(parents=True,exist_ok=True)
 (out/'data').mkdir(exist_ok=True)
 (out/'data/science.json').write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
 # Page module only renders project-owned editorial strings; all scientific data come from above.
 sys.path.insert(0,str(ROOT/'site'))
 from pages import render
 article=(ROOT/'site/longread.en.md').read_text()
 (out/'index.html').write_text(render(data,md(article)),encoding='utf-8')
 (out/'longread.en.md').write_text('\n'.join(('Sources: '+ ' · '.join('['+SOURCES[k].split('/')[-1]+']('+REPO+'/blob/'+BASE+'/'+SOURCES[k]+')' for k in line.split(':',1)[1].split())) if line.startswith('@sources:') else line for line in article.splitlines())+'\n')
 # This is a compatibility redirect, not a retained Russian-language edition.
 (out/'ru.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="canonical" href="https://spicmaff.github.io/malonaldehyde-transition-sampling/"><title>Continue to Proton / Potential</title><script src="redirect.mjs" type="module"></script></head><body><h1>This exhibit is now English-only.</h1><p><a href="index.html">Continue to Proton / Potential</a></p></body></html>')
 (out/'redirect.mjs').write_text("location.replace(new URL('index.html'+location.search+location.hash,location.href).href);\n")
 if (out/'longread.ru.md').exists():(out/'longread.ru.md').unlink()
 for name in ['style.css','app.mjs','core.mjs','favicon.svg','social-preview.svg','social-preview.png']:
  shutil.copyfile(ROOT/'site'/name,out/name)
 for dirname in ['assets','media']:
  shutil.copytree(ROOT/'site'/dirname,out/dirname,dirs_exist_ok=True)
 (out/'.nojekyll').write_text('')
 (out/'404.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Page not found</title><h1>Page not found</h1><p><a href="./">Return to the malonaldehyde exhibit</a></p></html>')
 (out/'README.txt').write_text('Malonaldehyde research exhibit. Serve this folder with: python3 -m http.server 8000\nOpen http://localhost:8000/ . Static text remains readable without JavaScript.\nScience: '+BASE+'\nSources and licences: https://github.com/spicmaff/malonaldehyde-transition-sampling/blob/main/docs/RESEARCH_SITE.md\n')
 (out/'build-manifest.json').write_text(json.dumps({p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='build-manifest.json'},sort_keys=True,indent=2)+'\n')
 return data
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,default=ROOT/'_site');args=a.parse_args()
 check(args.out.resolve()!=ROOT and args.out.resolve()!=ROOT/'site','Refuse overwriting repository or source')
 d=build(args.out)
 print(json.dumps({'status':'PASS_RESEARCH_SITE_BUILD','science_commit':BASE,'NEB_images':len(d['molecule']),'training_configurations':{k:len(v) for k,v in d['sampling'].items()},'paired_seeds':len(d['seeds'])//2,'local_PBE_comparisons':len(d['local']),'new_physical_calls':0}))

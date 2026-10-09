#!/usr/bin/env python3
"""Build an English-only cinematic research exhibit from the public, frozen evidence.
No network, inference, training, selectors or physical simulation. Python 3.11+.
"""
from __future__ import annotations
import argparse, csv, hashlib, html, json, math, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from verify_train119_diagnostic import parse_cfg, verify, force_metrics, terminal_pw, xml_reference, geometry_guard, STOP, A2
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
 'quantum':'data/quantum_audit/quantum_results_primary_v039.tsv',
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

def extended_data():
 data=scientific_data()
 check(data['boundaries']['Train119_status']=='STATIC_APPLICABILITY_FAIL','Historical outcome')
 data['residuals']={k:[a-b for a,b in zip(v,data['profiles']['PBE'])] for k,v in data['profiles'].items()}
 data['scaffold']={'left_OO_A':data['molecule'][0]['roo'],'central_OO_A':data['molecule'][4]['roo']}
 data['scaffold']['contraction_percent']=100*(1-data['scaffold']['central_OO_A']/data['scaffold']['left_OO_A'])
 data['force_frames']=[]
 for name,ids,infile in [('CHALLENGE4',range(93,97),'LOCAL_CHALLENGE4_REPLAY93_96_EXACT.cfg'),('CROSSING7',range(142,149),'CROSSING7_EXACT.cfg')]:
  inputs=parse_cfg((ROOT/DROOT/'inputs'/infile).read_text())
  predictions=parse_cfg((ROOT/DROOT/'predictions'/f'{name}.cfg').read_text(),labels=True)
  check(len(inputs)==len(predictions)==len(ids),'force cardinality')
  for idx,inp,pred in zip(ids,inputs,predictions):
   check(geometry_guard(inp,pred)['pass_guard'],'force input mapping')
   prefix=f'{DROOT}/references/replay{idx:03d}'
   en,forces,_=terminal_pw((ROOT/prefix/'pw.out').read_text())
   xml_reference((ROOT/prefix/'data-file-schema.xml').read_text(),inp)
   metrics=force_metrics(forces,pred.forces)
   saved=next(r for r in data['local'] if r['replay_index']==idx)
   check(abs(metrics['force_component_RMSE_eV_A']-saved['force_component_RMSE_eV_A'])<1e-12,'force summary')
   data['force_frames'].append({'index':idx,'group':name,'xyz':inp.xyz,'pbe':forces,'mtp':pred.forces,'difference':[[b-a for a,b in zip(r,p)] for r,p in zip(forces,pred.forces)],'rmse':metrics['force_component_RMSE_eV_A'],'gamma':saved['gamma_saved'],'source':f'{REPO}/blob/{BASE}/{prefix}/pw.out'})
   for rel in [prefix+'/pw.in',prefix+'/pw.out',prefix+'/data-file-schema.xml',f'{DROOT}/predictions/{name}.cfg',f'{DROOT}/inputs/{infile}']:
    data['evidence'][rel]={'path':rel,'sha256':hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(),'url':f'{REPO}/blob/{BASE}/{rel}'}
 quantum=next(r for r in rows(SOURCES['quantum']) if r['series']=='targeted' and r['isotope']=='H')
 data['quantum_boundary']={'source':SOURCES['quantum'],'E1_above_barrier_meV':1000*(float(quantum['e1_ev'])-float(quantum['barrier_ev'])),'classification':quantum['classification'],'experimental_validation':False}
 check(data['quantum_boundary']['E1_above_barrier_meV']>0,'Saved targeted-H level classification')
 data['literature']=json.loads((ROOT/'site/literature.json').read_text())
 return data

def md(text):
 """Small escaped editorial dialect: headings, source directives, verified citations."""
 out=[];paragraph=[]
 refs={r['id']:r for r in json.loads((ROOT/'site/literature.json').read_text())}
 def inline(value):
  import re
  value=html.escape(value)
  def link(m):
   key=m.group(1);check(key in refs,'Unknown literature key '+key)
   return '<a class="citation" href="'+refs[key]['url']+'" aria-label="Literature '+key+'">['+key+']</a>'
  return re.sub(r'\[(S\d+|V\d+)\]',link,value)
 def flush():
  if paragraph:out.append('<p>'+inline(' '.join(paragraph))+'</p>');paragraph.clear()
 for line in text.splitlines():
  if line.startswith('## '):flush();out.append('<h2>'+html.escape(line[3:])+'</h2>')
  elif line.startswith('# '):flush()
  elif line.startswith('@sources:'):
   flush();keys=line.split(':',1)[1].split();check(all(k in SOURCES for k in keys),'Unknown source')
   out.append('<p class="chapter-source">Project evidence: '+ ' · '.join('<a href="'+REPO+'/blob/'+BASE+'/'+SOURCES[k]+'">'+html.escape(SOURCES[k].split('/')[-1])+'</a>' for k in keys) +'</p>')
  elif not line.strip():flush()
  else:paragraph.append(line.strip())
 flush();return '\n'.join(out)

def build(out):
 out=Path(out).resolve()
 check(out not in (ROOT,ROOT/'site') and not ROOT.is_relative_to(out),'Unsafe build directory')
 if out.exists():
  check(not any(out.iterdir()) or (out/'build-manifest.json').is_file(),'Refuse clearing unknown output')
  shutil.rmtree(out)
 out.mkdir(parents=True)
 data=extended_data()
 (out/'data').mkdir()
 (out/'data/science.json').write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
 (out/'data/literature.json').write_text(json.dumps(data['literature'],indent=2,ensure_ascii=False)+'\n')
 sys.path.insert(0,str(ROOT/'site'))
 from pages import render
 article=(ROOT/'site/longread.en.md').read_text()
 (out/'index.html').write_text(render(data,md(article)),encoding='utf-8')
 import re
 export=[]
 refs={r['id']:r for r in data['literature']}
 for line in article.splitlines():
  if line.startswith('@sources:'):
   export.append('Project evidence: '+' · '.join('['+SOURCES[k].split('/')[-1]+']('+REPO+'/blob/'+BASE+'/'+SOURCES[k]+')' for k in line.split(':',1)[1].split()))
  else:
   export.append(re.sub(r'\[(S\d+|V\d+)\]',lambda m:'['+m.group(1)+']('+refs[m.group(1)]['url']+')',line))
 export += ['', '## Literature', ''] + ['['+r['id']+'] '+r['authors']+'. '+r['title']+'. '+str(r['year'])+'. '+r['url'] for r in data['literature']]
 (out/'longread.en.md').write_text('\n'.join(export)+'\n')
 shutil.copyfile(ROOT/'site/brief.en.md',out/'brief.en.md')
 (out/'ru.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Proton / Potential has moved</title><link rel="canonical" href="https://spicmaff.github.io/malonaldehyde-transition-sampling/"><script>location.replace("./"+location.hash)</script><h1>Proton / Potential is now English-only.</h1><p><a href="./">Continue to the research exhibit</a></p></html>')
 for name in ['style.css','app.mjs','core.mjs','molecule.mjs','charts.mjs','favicon.svg','social-preview.svg','social-preview.png']:
  shutil.copyfile(ROOT/'site'/name,out/name)
 # Only new English cinematic assets are deployed. Historical Russian films stay in Git/releases.
 if (ROOT/'site/cinema').exists():shutil.copytree(ROOT/'site/cinema',out/'cinema')
 (out/'.nojekyll').write_text('')
 (out/'404.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Page not found</title><h1>Page not found</h1><p><a href="/malonaldehyde-transition-sampling/">Return to Proton / Potential</a></p></html>')
 (out/'README.txt').write_text('Proton / Potential: English-only research exhibit. Serve with python3 -m http.server 8000 and open http://localhost:8000/ . Static prose and tables do not need JavaScript. Scientific snapshot: '+BASE+'\n')
 (out/'build-manifest.json').write_text(json.dumps({p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='build-manifest.json'},sort_keys=True,indent=2)+'\n')
 return data
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,default=ROOT/'_site');args=a.parse_args()
 d=build(args.out)
 print(json.dumps({'status':'PASS_CINEMATIC_ENGLISH_BUILD','science_commit':BASE,'NEB_images':len(d['molecule']),'force_frames_from_raw_PBE':len(d['force_frames']),'paired_seeds':len(d['seeds'])//2,'new_physical_calls':0}))

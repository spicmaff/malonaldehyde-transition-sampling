#!/usr/bin/env python3
"""Verify twenty saved finite-budget training logs; never run a training program."""
from __future__ import annotations
import argparse, json, math, re
from pathlib import Path
from verify_pbe14_offpath import SEEDS, digest, require, table, write_tsv
ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'data/studies/optimization_budget_v001'


def parse_log(text):
    pieces=re.split(r'BFGS iterations count set to (\d+)',text)
    require(len(pieces)==3,'One main-stage header required')
    cap=int(pieces[1]);require(cap in [2000,8000],'Supported historical cap')
    regex=r'BFGS iter (\d+): f=([-+0-9.eE]+)'
    pre=re.findall(regex,pieces[0]);main=re.findall(regex,pieces[2])
    require([int(i) for i,f in pre]==list(range(75)),'75 preliminary accepted steps')
    require([int(i) for i,f in main]==list(range(cap)),'Main accepted-step sequence')
    require(all(math.isfinite(float(f)) and float(f)>=0 for i,f in pre+main),'Finite objective')
    term=pieces[2].split('MTPR training ended',1)[0]
    require('step limit reached' in term and 'BFGS ended due to small decr.' not in term,'STEP_LIMIT, not convergence')
    require('Errors checked for 60 configurations' in pieces[2],'Saved-model Train60 footer')
    jump=[int(i) for (j,x),(i,y) in zip(main,main[1:]) if float(y)>float(x)]
    return {'cap':cap,'pretraining':pre,'main':main,'stop_reason':'STEP_LIMIT','upward_indices':jump,
            'last_printed_objective':float(main[-1][1]),'best_printed_objective':min(float(f) for i,f in main)}


def verify(root=DEFAULT,check_hashes=True):
    root=Path(root);manifest=json.loads((root/'INPUT_MANIFEST.json').read_text())
    if check_hashes:
        for name,h in manifest.items():require(digest(root/name)==h,'Budget input hash: '+name)
    rows=table(root/'MODEL_STOP_AND_SHA256.tsv')
    expected={(i,branch,cap) for i in range(5) for branch in ['basin','targeted'] for cap in [2000,8000]}
    require(len(rows)==20 and {(int(r['seed_index']),r['branch'],int(r['budget'])) for r in rows}==expected,'20 complete optimizer endpoints')
    require(len(list((root/'logs').glob('*.txt')))==20,'20 source logs')
    pbe=table(root.parent/'pbe14_mtp20_v001/MODELS_AND_PREDICTIONS_SHA256.tsv')
    pbe_ids={(int(r['seed_index']),r['branch'],int(r['budget'])):r for r in pbe}
    summary=[];parsed={}
    for row in rows:
        i=int(row['seed_index']);cap=int(row['budget']);key=(i,row['branch'],cap)
        require(row['seed_u64']==SEEDS[i] and row['model_sha256']==pbe_ids[key]['model_sha256'],'Seed/model correspondence across studies')
        text=(root/row['log_path']).read_text()
        if check_hashes:require(digest(root/row['log_path'])==row['log_sha256'],'Training log SHA')
        d=parse_log(text);require(d['cap']==cap,'Log cap versus manifest')
        parsed[key]=d
        summary.append({'seed_index':i,'seed_u64':SEEDS[i],'branch':row['branch'],'budget':cap,'model_sha256':row['model_sha256'],
                        'stop_reason':d['stop_reason'],'pretraining_accepted':len(d['pretraining']),'main_accepted':len(d['main']),
                        'last_printed_objective':d['last_printed_objective'],'best_printed_objective':d['best_printed_objective'],'positive_printed_jumps':len(d['upward_indices']),
                        'objective_scope':'Printed main BFGS objective before terminal model transformations'})
    prefixes=[]
    for i in range(5):
        for branch in ['basin','targeted']:
            s=parsed[(i,branch,2000)];l=parsed[(i,branch,8000)]
            require(s['pretraining']==l['pretraining'] and s['main']==l['main'][:2000],'Paired printed prefix mismatch')
            prefixes.append({'seed_index':i,'branch':branch,'pretraining_strings_equal':True,'first_2000_main_strings_equal':True})
    long_jumps=sum(len(v['upward_indices']) for k,v in parsed.items() if k[2]==8000)
    require(long_jumps==1163,'Recorded long-run visible jump count')
    require(all(j%50==0 for k,v in parsed.items() if k[2]==8000 for j in v['upward_indices']),'Jump phase outside 50-step boundaries')
    return {'schema':'optimizer-budget-verified-v1','status':'PASS_20_SAVED_STEP_LIMIT_ENDPOINTS','new_scientific_calls':0,
            'model_count':20,'total_printed_main_rows':sum(r['main_accepted'] for r in summary),'total_printed_pretraining_rows':1500,
            'visible_long_run_increases':long_jumps,'all_visible_increases_on_50_step_boundaries':True,'endpoints':summary,'matched_prefixes':prefixes,
            'interpretation':'Printed prefixes overlap. 100000 rows are not independent experiments. All endpoints are step-limited, not certified converged. These logs do not measure the objective of the subsequently saved terminal model.'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--data',type=Path,default=DEFAULT);ap.add_argument('--out',type=Path)
    a=ap.parse_args();r=verify(a.data)
    if a.out:
        a.out.mkdir(parents=True,exist_ok=True)
        (a.out/'VERIFICATION.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
        write_tsv(a.out/'ENDPOINTS_20.tsv',r['endpoints']);write_tsv(a.out/'PREFIX_CHECKS_10.tsv',r['matched_prefixes'])
    print(json.dumps({k:v for k,v in r.items() if k not in ['endpoints','matched_prefixes']},indent=2))

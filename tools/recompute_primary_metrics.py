#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math,re
from pathlib import Path

def blocks(path: Path):
    text=path.read_text()
    return re.findall(r'(?ms)^\s*BEGIN_CFG\s*\n(.*?)^\s*END_CFG\s*$',text)

def parse(path: Path):
    out=[]
    for raw in blocks(path):
        ls=[x.strip() for x in raw.splitlines() if x.strip()]
        b={'features':{}}
        i=0
        while i<len(ls):
            line=ls[i]
            if line=='Size':
                b['n']=int(ls[i+1]); i+=2; continue
            if line=='Supercell':
                b['cell']=[[float(v) for v in ls[i+j+1].split()] for j in range(3)]
                i+=4; continue
            if line.startswith('AtomData:'):
                keys=line.split(':',1)[1].split()
                atoms=[dict(zip(keys,row.split())) for row in ls[i+1:i+1+b['n']]]
                atoms.sort(key=lambda a:int(a['id']))
                b['types']=[int(a['type']) for a in atoms]
                b['pos']=[[float(a[k]) for k in ('cartes_x','cartes_y','cartes_z')] for a in atoms]
                b['forces']=[[float(a[k]) for k in ('fx','fy','fz')] for a in atoms]
                i+=1+b['n']; continue
            if line=='Energy':
                b['energy']=float(ls[i+1]); i+=2; continue
            if line.startswith('Feature'):
                f=line.split(None,2)
                if len(f)==3: b['features'][f[1]]=f[2]
            i+=1
        if b.get('n')!=9: raise RuntimeError(f'Unexpected atom count in {path}')
        out.append(b)
    return out

def pdist(pos):
    return [math.dist(pos[i],pos[j]) for i in range(len(pos)) for j in range(i+1,len(pos))]

def rmse_forces(ref,pred,indices):
    d=[pred[i]['forces'][a][c]-ref[i]['forces'][a][c] for i in indices for a in range(9) for c in range(3)]
    return math.sqrt(sum(x*x for x in d)/len(d))

def barrier(xs,neb):
    e=[xs[i]['energy'] for i in neb]
    return (max(e)-min(e[0],e[-1]))*1000.0

def main():
    ap=argparse.ArgumentParser(description='Recompute v030r primary metrics from frozen v029 CFG payloads.')
    ap.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data/frozen_models_v028')
    ns=ap.parse_args()
    d=ns.data_dir
    ref=parse(d/'frozen_audit21_labels_v029.cfg')
    pred={
        'basin':parse(d/'audit21_predictions_basin_v029.cfg'),
        'targeted':parse(d/'audit21_predictions_targeted_v029.cfg'),
    }
    train={
        'basin':parse(d/'train_basin60_v028.cfg'),
        'targeted':parse(d/'train_targeted60_v028.cfg'),
    }
    if len(ref)!=21 or any(len(v)!=21 for v in pred.values()) or any(len(v)!=60 for v in train.values()):
        raise RuntimeError('Frozen CFG cardinality mismatch')
    neb=[i for i,x in enumerate(ref) if x['features'].get('audit_subset')=='neb9'] or list(range(12,21))
    basin12=[i for i,x in enumerate(ref) if x['features'].get('audit_subset')=='basin12'] or list(range(12))
    q={}
    for i in neb:
        q[i]=float(ref[i]['features']['q_pt_A']) if 'q_pt_A' in ref[i]['features'] else math.dist(ref[i]['pos'][0],ref[i]['pos'][1])-math.dist(ref[i]['pos'][7],ref[i]['pos'][1])
    transition=[i for i in neb if abs(q[i])<=0.15]
    rb=barrier(ref,neb)
    metrics={}
    for branch,p in pred.items():
        pb=barrier(p,neb)
        metrics[branch]={
            'lower_endpoint_barrier_abs_error_meV':abs(pb-rb),
            'transition_force_component_RMSE_eV_A':rmse_forces(ref,p,transition),
            'basin12_force_component_RMSE_eV_A':rmse_forces(ref,p,basin12),
        }
    overlaps=[]
    for branch,tr in train.items():
        for ai,a in enumerate(ref,1):
            ad=pdist(a['pos'])
            for ti,t in enumerate(tr,1):
                if a['types']!=t['types'] or a['cell']!=t['cell']: continue
                delta=max(abs(x-y) for x,y in zip(ad,pdist(t['pos'])))
                if delta<=2.1e-6:
                    overlaps.append({'branch':branch,'audit_index_1based':ai,'audit_id':a['features'].get('audit_id',''),'training_index_1based':ti,'max_pair_distance_delta_A':delta})
    out={'DFT_barrier_meV':rb,'transition_audit_indices_1based':[i+1 for i in transition],'metrics':metrics,'audit21_train60_geometry_overlaps':overlaps,
         'scope':'Recomputed from saved reference/model-prediction CFG payloads; no DFT or MTP inference is executed.'}
    print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__': main()

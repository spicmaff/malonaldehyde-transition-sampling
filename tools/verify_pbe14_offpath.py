#!/usr/bin/env python3
"""Recompute the frozen PBE14 / MTP20 benchmark without QE or MLIP.
Standard library only. All results originate in saved reference/prediction arrays.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, math, re, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT/'data/studies/pbe14_mtp20_v001'
SEEDS = ['4172185641970229070','10780126852447763956','16937122512019790775','12250469658613881511','18149779474148714524']
ELEMENTS = ['O','H','C','H','C','H','C','O','H']
TYPES = [2,1,0,1,0,1,0,2,1]
MODES = ['OO_breathing','C_skeletal_bend','H_lateral','H_out_of_plane']
REGIONS = ['BASIN_LEFT','TRANSITION_CENTER']
IDS = [prefix+suffix for prefix in ['L','T'] for suffix in ['01m','01p','02m','02p','03m','03p','04p']]
RY_EV, BOHR_A = 13.605693122994, 0.529177210903
NUMERIC_TOL = 5e-13
COORD_TOL, PAIR_TOL = 1.1e-6, 2.1e-6


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def table(path):
    with Path(path).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def write_tsv(path, rows):
    require(bool(rows), 'Refuse an unexplained empty table')
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t',lineterminator='\n')
        w.writeheader();w.writerows(rows)


def finite(value):
    x=float(str(value).replace('D','E').replace('d','e'))
    require(math.isfinite(x), 'Nonfinite number')
    return x


def parse_cfg(text):
    chunks=re.findall(r'(?ms)^\s*BEGIN_CFG\s*\n(.*?)^\s*END_CFG\s*$',text)
    require(len(chunks)==len(re.findall(r'(?m)^\s*BEGIN_CFG\s*$',text))>0,'CFG block boundaries')
    require(len(chunks)==len(re.findall(r'(?m)^\s*END_CFG\s*$',text)),'Unmatched CFG end')
    out=[]
    for raw in chunks:
        lines=[x.strip() for x in raw.splitlines() if x.strip()]
        require(lines.count('Size')==1 and lines.count('Supercell')==1 and lines.count('Energy')==1,'CFG required fields')
        require(lines[lines.index('Size')+1]=='9','Nine atoms required')
        sc=lines.index('Supercell');cell=[[finite(x) for x in lines[sc+j].split()] for j in [1,2,3]]
        require(cell==[[16.,0.,0.],[0.,16.,0.],[0.,0.,16.]],'Frozen 16-A cell')
        heads=[i for i,s in enumerate(lines) if s.startswith('AtomData:')]
        require(len(heads)==1,'AtomData cardinality')
        i=heads[0];keys=lines[i].split(':',1)[1].split()
        require(len(keys)==len(set(keys)) and set(['id','type','cartes_x','cartes_y','cartes_z','fx','fy','fz'])<=set(keys),'CFG force columns')
        rows=[]
        for j in range(9):
            values=lines[i+1+j].split();require(len(values)==len(keys),'CFG row width')
            rows.append(dict(zip(keys,values)))
        require([int(a['id']) for a in rows]==list(range(1,10)),'Ordered atom IDs required; no silent sorting')
        require([int(a['type']) for a in rows]==TYPES,'Atom species/order')
        features={}
        for line in lines:
            if line.startswith('Feature '):
                q=line.split(None,2);require(len(q)==3 and q[1] not in features,'Feature cardinality');features[q[1]]=q[2]
        out.append({'xyz':[[finite(a[k]) for k in ['cartes_x','cartes_y','cartes_z']] for a in rows],
                    'forces':[[finite(a[k]) for k in ['fx','fy','fz']] for a in rows],
                    'energy':finite(lines[lines.index('Energy')+1]),'features':features})
    return out


def parse_qe(text):
    require('JOB DONE.' in text and 'convergence NOT achieved' not in text and 'Error in routine' not in text,'QE completion')
    require(re.search(r'Program PWSCF\s+v\.?\s*7\.5',text),'QE version 7.5')
    e=re.findall(r'(?m)^\s*!\s+total energy\s*=\s*([-+0-9.EeDd]+)\s+Ry',text)
    it=re.findall(r'convergence has been achieved in\s+(\d+)\s+iterations',text)
    acc=re.findall(r'estimated scf accuracy\s*<\s*([-+0-9.EeDd]+)\s+Ry',text)
    require(e and it and acc,'QE convergence records')
    require(int(it[-1])<=200 and 0<=finite(acc[-1])<=1e-8,'SCF acceptance')
    heads=list(re.finditer(r'Forces acting on atoms \(cartesian axes,\s*Ry/au\):',text))
    require(bool(heads),'Physical total-force heading absent')
    after=text[heads[-1].end():].lstrip('\r\n ')
    rows=after.splitlines()[:9]
    require(len(rows)==9,'Nine physical force rows')
    forces=[]
    for i,line in enumerate(rows):
        m=re.fullmatch(r'\s*atom\s+(\d+)\s+type\s+(\d+)\s+force\s*=\s*([-+0-9.EeDd]+)\s+([-+0-9.EeDd]+)\s+([-+0-9.EeDd]+)\s*',line)
        require(m is not None,'Physical force row malformed')
        require(int(m[1])==i+1 and int(m[2])==TYPES[i]+1,'QE atom identity')
        forces.append([finite(m[j]) for j in [3,4,5]])
    total=re.findall(r'Total force\s*=\s*([-+0-9.EeDd]+)\s+Total SCF correction\s*=\s*([-+0-9.EeDd]+)',text)
    require(total,'QE force norm/correction missing')
    require(abs(math.sqrt(math.fsum(x*x for row in forces for x in row))-finite(total[-1][0]))<=4e-5,'Wrong QE physical force block')
    require(0<=finite(total[-1][1])<=.001,'SCF force correction')
    return {'energy':finite(e[-1])*RY_EV,'forces':[[x*RY_EV/BOHR_A for x in row] for row in forces],
            'iterations':int(it[-1]),'scf_accuracy_Ry':finite(acc[-1]),'force_correction_Ry_bohr':finite(total[-1][1]),'physical_blocks':len(heads)}


def input_xyz(text):
    m=re.search(r'ATOMIC_POSITIONS\s+(?:\{)?angstrom(?:\})?\s*\n(.*?)K_POINTS\s+gamma',text,re.S)
    require(m is not None,'Frozen QE position/k-point convention')
    rows=[s.split() for s in m[1].splitlines() if s.strip()]
    require(len(rows)==9 and [r[0] for r in rows]==ELEMENTS and all(len(r)==4 for r in rows),'QE input atoms')
    for key,value in [('ecutwfc',80),('ecutrho',960),('nat',9),('ntyp',3)]:
        m=re.search(r'\b'+key+r'\s*=\s*([0-9.]+)',text,re.I)
        require(m and finite(m[1])==value,'QE input '+key)
    return [[finite(v) for v in row[1:]] for row in rows]


def maxdiff(a,b):
    return max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb))


def rmse(reference,prediction):
    ds=[b-a for ra,rb in zip(reference,prediction) for a,b in zip(ra,rb)]
    require(len(ds)==27 and all(math.isfinite(x) for x in ds),'27 finite force differences')
    return math.sqrt(math.fsum(x*x for x in ds)/27)


def aggregate(rows):
    """Equal within-block mean, then four equal block weights; never pooled RMSE."""
    blocks=[];regions=[]
    for i,seed in enumerate(SEEDS):
        for branch in ['basin','targeted']:
            for cap in [2000,8000]:
                for region in REGIONS:
                    values=[]
                    for mode in MODES:
                        rr=[r for r in rows if (r['seed_index'],r['branch'],r['budget'],r['region'],r['mode'])==(i,branch,cap,region,mode)]
                        require(len(rr)==(1 if mode=='H_out_of_plane' else 2),'Block sample count')
                        require(sorted(r['sign'] for r in rr)==([1] if mode=='H_out_of_plane' else [-1,1]),'Signed block membership')
                        value=math.fsum(r['force_RMSE_eV_A'] for r in rr)/len(rr);values.append(value)
                        blocks.append({'seed_index':i,'seed_u64':seed,'branch':branch,'budget':cap,'region':region,'mode':mode,'n_geometries':len(rr),'force_RMSE_eV_A':value})
                    regions.append({'seed_index':i,'seed_u64':seed,'branch':branch,'budget':cap,'region':region,'force_RMSE_eV_A':math.fsum(values)/4})
    contrasts=[]
    for i,seed in enumerate(SEEDS):
        selected={r['branch']:r['force_RMSE_eV_A'] for r in regions if r['seed_index']==i and r['budget']==8000 and r['region']=='TRANSITION_CENTER'}
        contrasts.append({'seed_index':i,'seed_u64':seed, 'basin':selected['basin'],'targeted':selected['targeted'],'targeted_minus_basin_eV_A':selected['targeted']-selected['basin']})
    means=[]
    for region in REGIONS:
        for cap in [2000,8000]:
            for branch in ['basin','targeted']:
                rr=[r['force_RMSE_eV_A'] for r in regions if r['region']==region and r['budget']==cap and r['branch']==branch]
                require(len(rr)==5,'Five seeds in each cell')
                means.append({'region':region,'budget':cap,'branch':branch,'force_RMSE_eV_A':statistics.mean(rr)})
    return blocks,regions,contrasts,means


def verify(root=DEFAULT, check_hashes=True):
    root=Path(root)
    manifest=json.loads((root/'INPUT_MANIFEST.json').read_text())
    if check_hashes:
        for name,h in manifest.items():
            require(not Path(name).is_absolute() and '..' not in Path(name).parts,'Unsafe manifest path')
            require(digest(root/name)==h,'Input checksum mismatch: '+name)
    lock=json.loads((root/'PROTOCOL_LOCK.json').read_text())
    require(lock['seeds']==SEEDS,'Frozen 64-bit seeds')
    require(lock['primary_endpoint']['budget']==8000 and lock['primary_endpoint']['region']=='TRANSITION_CENTER','Frozen primary endpoint')
    candidates=lock['candidates'];require([c['id'] for c in candidates]==IDS,'Candidate identity and order')
    roles=table(root/'GEOMETRY_ROLES.tsv')
    require([c['id'] for c in roles]==IDS,'Role identities')
    ref=parse_cfg((root/'references/PBE14_EXACT.cfg').read_text())
    require(len(ref)==14 and [c['features'].get('candidate_id') for c in ref]==IDS,'14 ordered reference configurations')
    qe=[]
    for c,role,r in zip(candidates,roles,ref):
        expected_mode=MODES[int(c['id'][1:3])-1];expected_region=REGIONS[int(c['id'][0]=='T')]
        require(c['mode']==role['mode']==expected_mode and c['region']==role['region']==expected_region,'Frozen mode/region semantics')
        require(c['block']==role['block']==expected_region+'__'+expected_mode,'Block labels')
        require(int(role['sign'])==c['sign']==(-1 if c['id'].endswith('m') else 1),'Signed displacement')
        require(maxdiff(c['xyz_A'],r['xyz'])<1e-11,'Reference versus geometry lock')
        require(r['features'].get('prospective_region')==expected_region and r['features'].get('physical_block')==c['block'],'Reference feature roles')
        x=input_xyz((root/f"qe/{c['id']}/pw.in").read_text())
        require(maxdiff(x,r['xyz'])<1e-11,'QE input geometry mismatch')
        q=parse_qe((root/f"qe/{c['id']}/pw.out").read_text())
        de=abs(q['energy']-r['energy']);df=maxdiff(q['forces'],r['forces'])
        require(de<1e-8 and df<1e-12,'QE raw/CFG conversion mismatch')
        qe.append({'id':c['id'],'energy_abs_residual_eV':de,'max_force_component_abs_residual_eV_A':df,'iterations':q['iterations'],'scf_accuracy_Ry':q['scf_accuracy_Ry'],'force_correction_Ry_bohr':q['force_correction_Ry_bohr']})
    models=table(root/'MODELS_AND_PREDICTIONS_SHA256.tsv')
    expected={(i,branch,cap) for i in range(5) for branch in ['basin','targeted'] for cap in [2000,8000]}
    identities=[(int(m['seed_index']),m['branch'],int(m['budget'])) for m in models]
    require(len(models)==20 and set(identities)==expected,'Exactly 20 distinct model roles')
    require(len(list((root/'predictions').glob('*.cfg')))==20,'19/21 prediction files forbidden')
    original=table(root/'provenance/ORIGINAL_PREDICTIONS_MANIFEST.tsv')
    source_identity={(int(m['seed_index']),m['branch'],int(m['budget'])):m for m in original}
    rows=[];maxcoord=0.;maxpair=0.
    for m,(i,branch,cap) in zip(models,identities):
        require(m['seed_u64']==SEEDS[i],'Seed/role mismatch')
        require(m['model_sha256']==source_identity[(i,branch,cap)]['model_sha256'],'Model SHA linkage')
        path=root/m['prediction_path']
        if check_hashes:require(digest(path)==m['prediction_sha256'],'Prediction checksum')
        pred=parse_cfg(path.read_text());require(len(pred)==14,'14 predictions per model')
        for c,r,q in zip(candidates,ref,pred):
            require(q['features'].get('candidate_id')==c['id'],'Prediction configuration order')
            dc=maxdiff(r['xyz'],q['xyz'])
            dp=max(abs(math.dist(r['xyz'][a],r['xyz'][b])-math.dist(q['xyz'][a],q['xyz'][b])) for a in range(9) for b in range(a))
            require(dc<=COORD_TOL and dp<=PAIR_TOL,'Prediction serialization geometry guard')
            maxcoord=max(maxcoord,dc);maxpair=max(maxpair,dp)
            ds=[y-x for a,b in zip(r['forces'],q['forces']) for x,y in zip(a,b)]
            rows.append({'seed_index':i,'seed_u64':SEEDS[i],'branch':branch,'budget':cap,'candidate_id':c['id'],'region':c['region'],'mode':c['mode'],'sign':c['sign'],'force_RMSE_eV_A':rmse(r['forces'],q['forces']),'max_component_abs_eV_A':max(map(abs,ds)),'energy_residual_eV':q['energy']-r['energy']})
    require(len(rows)==280,'280 model/geometry comparisons')
    blocks,regions,contrasts,means=aggregate(rows)
    saved=table(root/'provenance/ORIGINAL_280_METRICS.tsv')
    old={(int(r['seed_index']),r['branch'],int(r['budget']),r['candidate_id']):r for r in saved}
    require(len(old)==280 and len(saved)==280,'Original 280 row reference')
    error=max(abs(r['force_RMSE_eV_A']-finite(old[(r['seed_index'],r['branch'],r['budget'],r['candidate_id'])]['force_component_RMSE_eV_A'])) for r in rows)
    require(error<=NUMERIC_TOL,'Independent per-case arithmetic mismatch')
    expected_results=json.loads((root/'RESULTS_EXPECTED.json').read_text())
    deltas=[r['targeted_minus_basin_eV_A'] for r in contrasts]
    old_deltas=[r['primary_targeted_minus_basin_eV_A'] for r in expected_results['primary_signed_targeted_minus_basin']]
    require(len(old_deltas)==5 and max(abs(x-y) for x,y in zip(deltas,old_deltas))<=NUMERIC_TOL,'Signed primary contrasts differ')
    require(abs(statistics.mean(deltas)-expected_results['descriptive_summary']['mean'])<=NUMERIC_TOL,'Primary mean')
    for m in means:
        k=f"{m['region']}:{m['budget']}:{m['branch']}"
        require(abs(m['force_RMSE_eV_A']-expected_results['budget_region_cell_statistics'][k]['mean'])<=NUMERIC_TOL,'Cell mean '+k)
    direction_contributions=[]
    for mode in MODES:
        value=math.fsum(r['force_RMSE_eV_A']*(1 if r['branch']=='targeted' else -1) for r in blocks if r['region']=='TRANSITION_CENTER' and r['budget']==8000 and r['mode']==mode)/20
        direction_contributions.append({'mode':mode,'contribution_to_primary_mean':value,'fraction_of_signed_primary':value/statistics.mean(deltas)})
    return {'schema':'pbe14-mtp20-verified-v1','study_id':'pbe14_mtp20_v001','status':'PASS_SAVED_PBE14_MTP20_NUMERICS',
            'new_scientific_calls':0,'n_geometries':14,'n_models':20,'n_errors':280,'n_blocks_per_model':8,'n_seeds':5,
            'primary':{'budget':8000,'region':'TRANSITION_CENTER','definition':'Mean of four block means of per-geometry component RMSE; Targeted minus Basin',
                       'unit':'eV/angstrom','contrasts':contrasts,'mean':statistics.mean(deltas),'median':statistics.median(deltas),'targeted_better_count':sum(x<0 for x in deltas)},
            'cell_means':means,'block_rows':blocks,'region_rows':regions,'case_rows':rows,'qe_quality':qe,
            'direction_contributions':direction_contributions,'geometry_guard':{'max_coordinate_A':maxcoord,'max_pair_distance_A':maxpair,'coordinate_tolerance_A':COORD_TOL,'pair_tolerance_A':PAIR_TOL},
            'max_per_case_difference_from_original':error,
            'geometries':[{'id':c['id'],'region':c['region'],'mode':c['mode'],'sign':c['sign'],'anchor_image':c['neb_image'],'xyz':c['xyz_A'],'q':c['qPT_A'],'roo':c['OO_A'],'max_displacement_A':c['max_atom_displacement_A']} for c in candidates],
            'limitations':['Two fixed allocations; seeds vary initialization, not allocation','Four dependent local blocks per region, not independent geometries','PBE computational reference, not experimental accuracy','Prespecified for the original comparison; reused development data for later optimizer changes','All 20 endpoints STEP_LIMIT; no convergence certification','No reactive dynamics, Blind12 or universal allocation-policy inference']}


def deliver(result,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'VERIFICATION.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    for key,name in [('case_rows','PER_GEOMETRY_280.tsv'),('block_rows','PHYSICAL_BLOCKS_160.tsv'),('region_rows','REGION_MODELS_40.tsv'),('cell_means','BUDGET_REGION_MEANS.tsv'),('qe_quality','QE_QUALITY_14.tsv')]:write_tsv(out/name,result[key])
    write_tsv(out/'PRIMARY_PAIRED_SEEDS.tsv',result['primary']['contrasts'])


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--data',type=Path,default=DEFAULT);ap.add_argument('--out',type=Path)
    a=ap.parse_args();r=verify(a.data)
    if a.out:deliver(r,a.out)
    print(json.dumps({'status':r['status'],'models':r['n_models'],'errors':r['n_errors'],'primary_mean':r['primary']['mean'],'targeted_wins':r['primary']['targeted_better_count'],'new_scientific_calls':0},indent=2))

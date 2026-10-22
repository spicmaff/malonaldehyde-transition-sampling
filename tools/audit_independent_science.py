#!/usr/bin/env python3
"""Independent saved-evidence audit; does not import a project verifier or run physics.

Run: python3 tools/audit_independent_science.py --out independent-science.json
All force residuals use identical ordered atoms in their recorded laboratory frame.
Rigid-invariant distance fingerprints are used only to audit geometric overlap.
"""
from __future__ import annotations

import argparse
import ast
import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TYPES = [2, 1, 0, 1, 0, 1, 0, 2, 1]
ELEMENTS = ['O', 'H', 'C', 'H', 'C', 'H', 'C', 'O', 'H']
MODES = ['OO_breathing', 'C_skeletal_bend', 'H_lateral', 'H_out_of_plane']
REGIONS = ['BASIN_LEFT', 'TRANSITION_CENTER']
RY_EV, BOHR_A = 13.605693122994, 0.529177210903
SHA = {}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(relative):
    path = ROOT / relative
    payload = path.read_bytes()
    SHA[str(path.relative_to(ROOT))] = hashlib.sha256(payload).hexdigest()
    return payload.decode('utf-8')


def rows(relative):
    return list(csv.DictReader(io.StringIO(read(relative)), delimiter='\t'))


def number(text):
    value = float(text.replace('D', 'e').replace('d', 'e'))
    require(math.isfinite(value), 'Non-finite number')
    return value


def cfg(relative, labels=True):
    text = read(relative)
    result, inside, body = [], False, []
    for line in text.splitlines():
        token = line.strip()
        if token == 'BEGIN_CFG':
            require(not inside, 'Nested CFG start')
            inside, body = True, []
        elif token == 'END_CFG':
            require(inside, 'Unmatched CFG end')
            inside = False
            require(body.count('Size') == body.count('Supercell') == 1, 'CFG required field multiplicity')
            require(body[body.index('Size')+1] == '9', 'Nine atoms required')
            cell_at = body.index('Supercell')
            cell = [[number(v) for v in body[cell_at+k].split()] for k in (1, 2, 3)]
            require(cell == [[16.,0.,0.],[0.,16.,0.],[0.,0.,16.]], 'Cell changed')
            atom_at = [i for i,v in enumerate(body) if v.startswith('AtomData:')]
            require(len(atom_at) == 1, 'Exactly one atom table required')
            atom_at = atom_at[0]
            columns = body[atom_at].split(':', 1)[1].split()
            require(len(set(columns)) == len(columns), 'Duplicate atom column')
            required = ['id','type','cartes_x','cartes_y','cartes_z'] + (['fx','fy','fz'] if labels else [])
            require(set(required) <= set(columns), 'Missing atom columns')
            atoms = []
            for k in range(9):
                values = body[atom_at+k+1].split()
                require(len(values) == len(columns), 'Wrong atom table row size')
                atoms.append(dict(zip(columns, values)))
            require([int(a['id']) for a in atoms] == list(range(1,10)), 'Atom order is not 1..9; no silent sorting')
            require([int(a['type']) for a in atoms] == TYPES, 'Species/order mismatch')
            features = {}
            for v in body:
                if v.startswith('Feature '):
                    parts = v.split(None, 2)
                    require(len(parts) == 3 and parts[1] not in features, 'Malformed or duplicate feature')
                    features[parts[1]] = parts[2]
            entry = {'xyz': [[number(a[k]) for k in ('cartes_x','cartes_y','cartes_z')] for a in atoms], 'features': features}
            if labels:
                require(body.count('Energy') == 1, 'Exactly one energy required')
                entry.update(energy=number(body[body.index('Energy')+1]), forces=[[number(a[k]) for k in ('fx','fy','fz')] for a in atoms])
            result.append(entry)
        elif inside and token:
            body.append(token)
        else:
            require(not token, 'Unexpected content outside CFG')
    require(not inside and result, 'Incomplete or empty CFG')
    return result


def maxdiff(a, b):
    require(len(a) == len(b) and all(len(x) == len(y) for x,y in zip(a,b)), 'Array shape mismatch')
    return max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb))


def match_geometry(a, b, tolerance):
    difference = maxdiff(a['xyz'], b['xyz'])
    require(difference <= tolerance, 'Configuration mismatch in recorded laboratory frame')
    return difference


def fingerprint(entry):
    p = entry['xyz']
    return [math.dist(p[i], p[j]) for i in range(9) for j in range(i)]


def fingerprint_difference(a, b):
    return max(abs(x-y) for x,y in zip(fingerprint(a),fingerprint(b)))


def geometry(entry):
    p=entry['xyz']; a,b=math.dist(p[0],p[1]), math.dist(p[7],p[1])
    return {'qPT_A':a-b,'OO_A':math.dist(p[0],p[7]),'O1_H2_A':a,'H2_O8_A':b}


def error(reference, predicted):
    require(len(reference) == len(predicted) == 9, 'Nine force vectors required')
    delta = [y-x for a,b in zip(reference,predicted) for x,y in zip(a,b)]
    require(len(delta) == 27, '27 force components required')
    return {'RMSE_eV_A':math.sqrt(math.fsum(x*x for x in delta)/27), 'max_component_eV_A':max(abs(x) for x in delta)}


def combined_error(reference, predicted):
    require(len(reference) == len(predicted) > 0, 'Prediction/reference configuration count mismatch')
    squared=[error(a['forces'],b['forces'])['RMSE_eV_A']**2 for a,b in zip(reference,predicted)]
    return math.sqrt(statistics.fmean(squared))


def barrier(entries):
    e=[c['energy'] for c in entries]
    return 1000*(max(e)-min(e[0],e[-1]))


def qe(relative):
    text=read(relative)
    require('JOB DONE.' in text and 'convergence NOT achieved' not in text and 'Error in routine' not in text, 'QE run did not complete')
    energy=re.findall(r'(?m)^\s*!\s*total energy\s*=\s*([-+\d.EeDd]+)\s+Ry',text)
    heads=list(re.finditer(r'Forces acting on atoms \(cartesian axes,\s*Ry/au\):',text))
    require(energy and heads, 'QE energy or physical force block missing')
    forces=[]
    lines=text[heads[-1].end():].strip().splitlines()
    for i,line in enumerate(lines[:9]):
        m=re.fullmatch(r'\s*atom\s+(\d+)\s+type\s+(\d+)\s+force\s*=\s*([-+\d.EeDd]+)\s+([-+\d.EeDd]+)\s+([-+\d.EeDd]+)\s*',line)
        require(m is not None and int(m[1]) == i+1 and int(m[2]) == TYPES[i]+1, 'QE force atom/species order mismatch')
        forces.append([number(m[k])*RY_EV/BOHR_A for k in (3,4,5)])
    norm=re.findall(r'Total force\s*=\s*([-+\d.EeDd]+)\s+Total SCF correction\s*=\s*([-+\d.EeDd]+)',text)
    require(norm, 'QE force norm missing')
    require(abs(math.sqrt(math.fsum(x*x for row in forces for x in row))*BOHR_A/RY_EV-number(norm[-1][0]))<4e-5, 'Wrong force block selected')
    accuracy=re.findall(r'estimated scf accuracy\s*<\s*([-+\d.EeDd]+)\s+Ry',text)
    iterations=re.findall(r'convergence has been achieved in\s+(\d+)\s+iterations',text)
    require(accuracy and iterations, 'Missing SCF records')
    require(number(accuracy[-1])<=1e-8 and int(iterations[-1])<=200 and number(norm[-1][1])<=.001, 'SCF quality screen')
    return {'energy':number(energy[-1])*RY_EV,'forces':forces,'scf_accuracy_Ry':number(accuracy[-1]),'iterations':int(iterations[-1]),'force_correction_Ry_bohr':number(norm[-1][1])}


def qe_input(relative):
    text=read(relative)
    m=re.search(r'ATOMIC_POSITIONS\s+(?:\{)?angstrom(?:\})?\s*\n(.*?)K_POINTS\s+gamma',text,re.S)
    require(m is not None, 'QE input coordinate/k-point convention')
    atoms=[r.split() for r in m[1].splitlines() if r.strip()]
    require([r[0] for r in atoms]==ELEMENTS and all(len(r)==4 for r in atoms), 'QE input atoms')
    for key,expected in [('ecutwfc',80),('ecutrho',960),('conv_thr',1e-10),('nspin',1),('tot_charge',0)]:
        m=re.search(r'\b'+key+r'\s*=\s*([-+\d.EeDd]+)',text,re.I)
        require(m is not None and number(m[1])==expected, 'QE numerical setting changed: '+key)
    require("input_dft = 'PBE'" in text and "occupations = 'fixed'" in text, 'QE functional/occupations')
    return {'xyz':[[number(x) for x in r[1:]] for r in atoms]}


def original():
    root='data/frozen_models_v028/'
    audit=cfg(root+'frozen_audit21_labels_v029.cfg')
    require(len(audit)==21, 'Audit21 size')
    ids=[c['features']['audit_id'] for c in audit]
    require(len(set(ids))==21, 'Repeated audit ID')
    selected=[i for i,c in enumerate(audit) if c['features']['audit_subset']=='neb9']
    require(len(selected)==9, 'Nine NEB supports')
    neb=[audit[i] for i in selected]
    require([int(c['features']['audit_subset_index']) for c in neb]==list(range(1,10)), 'NEB order')
    central=[i for i in selected if abs(geometry(audit[i])['qPT_A'])<=.15]
    require(len(central)==3, 'Central region cardinality')
    training={b:cfg(root+f'train_{b}60_v028.cfg') for b in ('basin','targeted')}
    keyed={b:{c['features']['candidate_id']:c for c in cc} for b,cc in training.items()}
    require(all(len(cc)==len(keyed[b])==60 for b,cc in training.items()), 'Unique training IDs')
    common=set(keyed['basin'])&set(keyed['targeted'])
    require(len(common)==36, 'Shared36 identity')
    shared_xyz=max(match_geometry(keyed['basin'][i],keyed['targeted'][i],0) for i in common)
    profiles, metrics, prediction_geometry = {}, {}, {}
    for branch in ('basin','targeted'):
        pred=cfg(root+f'audit21_predictions_{branch}_v029.cfg')
        require(len(pred)==21 and [c['features']['audit_id'] for c in pred]==ids, 'Prediction configuration mapping')
        prediction_geometry[branch]=max(match_geometry(a,b,1.1e-6) for a,b in zip(audit,pred))
        pn=[pred[i] for i in selected]
        offset=min(pn[0]['energy'],pn[-1]['energy'])
        profiles[branch]=[1000*(c['energy']-offset) for c in pn]
        metrics[branch]={'barrier_meV':barrier(pn),'barrier_abs_error_meV':abs(barrier(pn)-barrier(neb)), 'central_force_component_RMSE_eV_A':combined_error([audit[i] for i in central],[pred[i] for i in central])}
    ranges={b:[min(geometry(c)['OO_A'] for c in cc),max(geometry(c)['OO_A'] for c in cc)] for b,cc in training.items()}
    overlap=[]
    for b,cc in training.items():
        for i,c in enumerate(neb,1):
            for j,t in enumerate(cc,1):
                d=fingerprint_difference(c,t)
                if d<=2.1e-6:
                    overlap.append({'branch':b,'NEB_image':i,'training_index':j,'max_ordered_pair_distance_delta_A':d})
    below={b:[i for i,c in enumerate(neb,1) if geometry(c)['OO_A']<ranges[b][0]] for b in training}
    require(all(v==list(range(2,9)) for v in below.values()), 'Seven internal supports below training floor')
    seeds=rows('data/robustness/v028_seed_robustness_v001/ALL_METRICS.tsv')
    require(len(seeds)==10, 'Seed table size')
    pairs=[]
    for i in range(5):
        pair={r['branch']:r for r in seeds if int(r['seed_index'])==i}
        require(set(pair)=={'basin','targeted'} and pair['basin']['seed_u64']==pair['targeted']['seed_u64'],'Paired seed identity')
        outcomes={k:float(pair['targeted'][column])<float(pair['basin'][column]) for k,column in [('barrier_win','lower_endpoint_barrier_abs_error_meV'),('force_win','transition_region_force_component_RMSE_eV_A')]}
        pairs.append({'index':i,'seed':pair['basin']['seed_u64'],**outcomes,'joint_win':all(outcomes.values())})
    generator='scripts/core_pipeline/step28_fresh_tube_active_selection_v026.py'
    source=read(generator);tree=ast.parse(source)
    function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='generate_tube')
    base=next(x for x in ast.walk(function) if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='base' for t in x.targets))
    source_base=ast.get_source_segment(source,base)
    require(source_base=='base = (1.0 - item["s"]) * left + item["s"] * right_aligned','Generator is no longer endpoint-linear; inspect before interpreting')
    central_training=[geometry(c)['OO_A'] for c in training['targeted'] if abs(geometry(c)['qPT_A'])<=.15]
    return {'evidence_class':'PRIMARY_CFG_RECOMPUTATION','PBE_barrier_meV':barrier(neb),'PBE_endpoint_asymmetry_meV':1000*abs(neb[0]['energy']-neb[-1]['energy']), 'path':[{'image':i,**geometry(c)} for i,c in enumerate(neb,1)],'metrics':metrics,'central_Audit21_indices_1based':[i+1 for i in central], 'shared_training_ids':len(common),'shared_training_max_xyz_difference_A':shared_xyz,'prediction_max_xyz_difference_A':prediction_geometry, 'training_OO_ranges_A':ranges,'internal_images_below_training_floor':below,'central_OO_gap_A':ranges['targeted'][0]-geometry(neb[4])['OO_A'],'central_targeted_count':len(central_training),'central_targeted_OO_range_A':[min(central_training),max(central_training)],'training_endpoint_overlaps':overlap,'generator':{'path':generator,'line':base.lineno,'expression':source_base,'interpretation':'Perturbation around aligned-endpoint interpolation; not around relaxed NEB supports.'},'seed_robustness':{'evidence_class':'PUBLISHED_METRIC_TABLE_ARITHMETIC','pairs':pairs,'barrier_wins':sum(p['barrier_win'] for p in pairs),'force_wins':sum(p['force_win'] for p in pairs),'joint_wins':sum(p['joint_win'] for p in pairs),'scope':'The ten seed Audit21 prediction arrays are not distributed in this subtree; no independent force/barrier recomputation of these ten fits.'},'geometry_scope':'Ordered pair distances are rigid invariant. This is a qPT/OO projection finding, not an MTP feature-space extrapolation certificate.'}


def pbe14():
    root='data/studies/pbe14_mtp20_v001/'
    lock=json.loads(read(root+'PROTOCOL_LOCK.json'))
    refs=cfg(root+'references/PBE14_EXACT.cfg')
    roles=rows(root+'GEOMETRY_ROLES.tsv');rolemap={r['id']:r for r in roles}
    require(len(refs)==len(roles)==len(rolemap)==14, 'PBE14 sizes')
    ids=[c['features']['candidate_id'] for c in refs]
    require(ids==[r['id'] for r in roles]==[c['id'] for c in lock['candidates']], 'Frozen PBE14 order')
    qe_rows=[]
    for ref in refs:
        name=ref['features']['candidate_id'];r=rolemap[name]
        physical=qe(root+f'qe/{name}/pw.out');qin=qe_input(root+f'qe/{name}/pw.in')
        require(match_geometry(qin,ref,1.1e-11)<=1.1e-11,'QE input geometry mismatch')
        require(abs(physical['energy']-ref['energy'])<2e-9 and maxdiff(physical['forces'],ref['forces'])<2e-12,'QE labels differ from reference CFG')
        qe_rows.append({'id':name,'mode':r['mode'],'sign':int(r['sign']),'region':r['region'],'energy_delta_eV':physical['energy']-ref['energy'],'max_force_delta_eV_A':maxdiff(physical['forces'],ref['forces']),'scf_accuracy_Ry':physical['scf_accuracy_Ry'],'iterations':physical['iterations']})
    models=rows(root+'MODELS_AND_PREDICTIONS_SHA256.tsv')
    expected={(s,b,c) for s in range(5) for b in ('basin','targeted') for c in (2000,8000)}
    require({(int(m['seed_index']),m['branch'],int(m['budget'])) for m in models}==expected and len(models)==20,'20 unique model cells')
    case=[];coordmax=0
    for model in models:
        pred=cfg(root+model['prediction_path'])
        require(SHA[root+model['prediction_path']]==model['prediction_sha256'],'Prediction hash registry')
        require(len(pred)==14 and [c['features']['candidate_id'] for c in pred]==ids,'14 ordered predictions')
        require(model['seed_u64']==lock['seeds'][int(model['seed_index'])],'Frozen seed identity')
        for ref,p in zip(refs,pred):
            coordmax=max(coordmax,match_geometry(ref,p,1.1e-6))
            name=ref['features']['candidate_id'];r=rolemap[name]
            require(p['features']['physical_block']==r['block'] and p['features']['prospective_region']==r['region'],'Prediction region/block map')
            case.append({'seed_index':int(model['seed_index']),'branch':model['branch'],'budget':int(model['budget']),'id':name,'region':r['region'],'mode':r['mode'],'sign':int(r['sign']),'energy_residual_eV':p['energy']-ref['energy'],**error(ref['forces'],p['forces'])})
    blocks={};region={}
    for s,b,cap in sorted(expected):
        for r in REGIONS:
            for mode in MODES:
                v=[x for x in case if (x['seed_index'],x['branch'],x['budget'],x['region'],x['mode'])==(s,b,cap,r,mode)]
                require(sorted(x['sign'] for x in v)==([1] if mode=='H_out_of_plane' else [-1,1]),'Physical signed block definition')
                blocks[s,b,cap,r,mode]=statistics.fmean(x['RMSE_eV_A'] for x in v)
            region[s,b,cap,r]=statistics.fmean(blocks[s,b,cap,r,mode] for mode in MODES)
    require(len(case)==280 and len(blocks)==160 and len(region)==40,'All cases/blocks/regions accounted for')
    means={(r,cap,b):statistics.fmean(region[s,b,cap,r] for s in range(5)) for r in REGIONS for cap in (2000,8000) for b in ('basin','targeted')}
    contrasts=[region[s,'targeted',8000,'TRANSITION_CENTER']-region[s,'basin',8000,'TRANSITION_CENTER'] for s in range(5)]
    primary=statistics.fmean(contrasts)
    contribution=[];delete=[]
    for mode in MODES:
        d=[blocks[s,'targeted',8000,'TRANSITION_CENTER',mode]-blocks[s,'basin',8000,'TRANSITION_CENTER',mode] for s in range(5)]
        contribution.append({'mode':mode,'mean_mode_contrast_eV_A':statistics.fmean(d),'signed_primary_contribution_eV_A':statistics.fmean(d)/4,'fraction_of_signed_primary':statistics.fmean(d)/4/primary,'paired_contrasts_eV_A':d})
        keep=[m for m in MODES if m!=mode]
        d=[statistics.fmean(blocks[s,'targeted',8000,'TRANSITION_CENTER',m]-blocks[s,'basin',8000,'TRANSITION_CENTER',m] for m in keep) for s in range(5)]
        delete.append({'omitted':mode,'mean_eV_A':statistics.fmean(d),'paired_contrasts_eV_A':d,'Targeted_wins':sum(x<0 for x in d)})
    equal_case=[]
    for s in range(5):
        m={b:statistics.fmean(x['RMSE_eV_A'] for x in case if (x['seed_index'],x['branch'],x['budget'],x['region'])==(s,b,8000,'TRANSITION_CENTER')) for b in ('basin','targeted')}
        equal_case.append(m['targeted']-m['basin'])
    change={b:means['TRANSITION_CENTER',8000,b]-means['TRANSITION_CENTER',2000,b] for b in ('basin','targeted')}
    growth=change['basin']-change['targeted']
    published_cases=rows(root+'results/PER_GEOMETRY_280.tsv')
    key=lambda x:(int(x['seed_index']),x['branch'],int(x['budget']),x.get('candidate_id',x.get('id')))
    published_by_id={key(x):x for x in published_cases}
    require(len(published_cases)==len(published_by_id)==280 and set(published_by_id)=={key(x) for x in case},'Published per-geometry table identity')
    published_difference={'per_geometry_RMSE_eV_A':0.,'per_geometry_max_component_eV_A':0.,'energy_residual_eV':0.,'block_RMSE_eV_A':0.,'region_RMSE_eV_A':0.,'primary_contrast_eV_A':0.,'cell_mean_RMSE_eV_A':0.}
    for c in case:
        p=published_by_id[key(c)]
        require((p['region'],p['mode'],int(p['sign']))==(c['region'],c['mode'],c['sign']),'Published role map differs')
        for name,computed,saved in [('per_geometry_RMSE_eV_A','RMSE_eV_A','force_RMSE_eV_A'),('per_geometry_max_component_eV_A','max_component_eV_A','max_component_abs_eV_A'),('energy_residual_eV','energy_residual_eV','energy_residual_eV')]:
            published_difference[name]=max(published_difference[name],abs(c[computed]-float(p[saved])))
    for filename,target,columns,name,count in [('PHYSICAL_BLOCKS_160.tsv',blocks,['seed_index','branch','budget','region','mode'],'block_RMSE_eV_A',160),('REGION_MODELS_40.tsv',region,['seed_index','branch','budget','region'],'region_RMSE_eV_A',40),('BUDGET_REGION_MEANS.tsv',means,['region','budget','branch'],'cell_mean_RMSE_eV_A',8)]:
        records=rows(root+'results/'+filename)
        require(len(records)==count,'Published aggregate count')
        seen=set()
        for p in records:
            k=tuple(int(p[c]) if c in ('seed_index','budget') else p[c] for c in columns)
            require(k not in seen and k in target,'Published aggregate identity');seen.add(k)
            published_difference[name]=max(published_difference[name],abs(target[k]-float(p['force_RMSE_eV_A'])))
    published_primary=rows(root+'results/PRIMARY_PAIRED_SEEDS.tsv')
    require([int(p['seed_index']) for p in published_primary]==list(range(5)),'Published primary seed order')
    published_difference['primary_contrast_eV_A']=max(abs(v-float(p['targeted_minus_basin_eV_A'])) for v,p in zip(contrasts,published_primary))
    require(max(published_difference.values())<5e-13,'Published table differs from independent recomputation')
    return {'evidence_class':'RAW_QE_FORCE_BLOCK_AND_CFG_RECOMPUTATION','reference_count':14,'model_count':20,'case_count':280,'block_count':160,'region_count':40,'maximum_prediction_xyz_difference_A':coordmax,'published_table_max_abs_differences':published_difference,'QE_checks':qe_rows,'primary':{'definition':lock['primary_endpoint'],'mean_eV_A':primary,'median_eV_A':statistics.median(contrasts),'paired_contrasts_eV_A':contrasts,'Targeted_wins':sum(x<0 for x in contrasts)},'means':[{'region':r,'budget':cap,'branch':b,'RMSE_eV_A':v} for (r,cap,b),v in means.items()], 'budget_arithmetic':{'Basin_error_change_eV_A':change['basin'],'Targeted_error_change_eV_A':change['targeted'],'Basin_minus_Targeted_gap_growth_eV_A':growth,'Basin_fraction_of_gap_growth':change['basin']/growth,'interpretation':'Arithmetic accounting, not a causal mechanism of optimization.'},'exploratory':{'mode_contributions':contribution,'leave_one_block_out':delete,'equal_geometry_weights':{'mean_eV_A':statistics.fmean(equal_case),'paired_contrasts_eV_A':equal_case},'scope':'These sensitivity summaries are additional analyses and do not replace the locked primary endpoint.'},'all_cases':case,'all_physical_blocks':[{'seed_index':s,'branch':b,'budget':cap,'region':r,'mode':m,'mean_RMSE_eV_A':v} for (s,b,cap,r,m),v in blocks.items()]}


def train119():
    root='data/post_publication/train119_diagnostic_v001/'
    audit=cfg(root+'inputs/AUDIT21_REFERENCE_EXACT.cfg')
    pred=cfg(root+'predictions/AUDIT21_STATIC.cfg')
    require(len(audit)==len(pred)==21,'Train119 Audit21 size')
    require([c['features']['audit_id'] for c in audit]==[c['features']['audit_id'] for c in pred], 'Train119 Audit21 configuration IDs')
    for a,b in zip(audit,pred):match_geometry(a,b,1.1e-6)
    path_indices=[i for i,c in enumerate(audit) if c['features'].get('audit_subset')=='neb9']
    require(len(path_indices)==9,'Train119 NEB membership')
    neb=[audit[i] for i in path_indices];pn=[pred[i] for i in path_indices]
    central=[i for i in path_indices if abs(geometry(audit[i])['qPT_A'])<=.15]
    refzero=min(neb[0]['energy'],neb[-1]['energy']);pzero=min(pn[0]['energy'],pn[-1]['energy'])
    residuals=[1000*((p['energy']-pzero)-(a['energy']-refzero)) for a,p in zip(neb,pn)]
    replay=cfg(root+'inputs/REPLAY228_EXACT.cfg',False);train=cfg(root+'inputs/TRAIN119_EXACT.cfg')
    require(len(replay)==228 and len(train)==119,'Train119/Replay228 size')
    local=[]
    for group,input_file,indexes in [('CROSSING7','CROSSING7_EXACT.cfg',list(range(142,149))),('CHALLENGE4','LOCAL_CHALLENGE4_REPLAY93_96_EXACT.cfg',list(range(93,97)))]:
        cc=cfg(root+'inputs/'+input_file,False);pp=cfg(root+'predictions/'+group+'.cfg')
        require(len(cc)==len(pp)==len(indexes), 'Local diagnostic counts')
        for c,p,index in zip(cc,pp,indexes):
            require(c['features']['candidate_id']==p['features']['candidate_id']==replay[index-1]['features']['candidate_id'],'Replay ID mapping')
            match_geometry(c,replay[index-1],0);match_geometry(c,p,1.1e-6)
            q=qe(root+f'references/replay{index:03d}/pw.out')
            match_geometry(c,qe_input(root+f'references/replay{index:03d}/pw.in'),1.1e-11)
            xml=ET.fromstring(read(root+f'references/replay{index:03d}/data-file-schema.xml'))
            require(xml.attrib['Units']=='Hartree atomic units','XML units')
            output=xml.find('output');atoms=output.find('atomic_structure/atomic_positions').findall('atom')
            require([a.attrib['name'] for a in atoms]==ELEMENTS and [int(a.attrib['index']) for a in atoms]==list(range(1,10)),'XML atom identity')
            x=[[number(v)*BOHR_A for v in a.text.split()] for a in atoms]
            require(maxdiff(x,c['xyz'])<3e-9,'XML coordinate geometry')
            xf=[number(x)*2*RY_EV/BOHR_A for x in output.find('forces').text.split()]
            require(len(xf)==27 and max(abs(a-b) for a,b in zip(xf,[x for row in q['forces'] for x in row]))<1.3e-7,'XML/stdout force parity')
            require(abs(number(output.find('total_energy/etot').text)*2*RY_EV-q['energy'])<7e-8,'XML/stdout energy parity')
            local.append({'group':group,'replay_index':index,'candidate_id':c['features']['candidate_id'],**geometry(c),**error(q['forces'],p['forces'])})
    valid=cfg(root+'inputs/VALIDATION11_EXACT.cfg');vp=cfg(root+'predictions/VALIDATION11_QUALIFICATION.cfg')
    require(len(valid)==len(vp)==11,'Validation11 count')
    vr=[]
    for c,p in zip(valid,vp):
        match_geometry(c,p,1.1e-6);vr.append(error(c['forces'],p['forces'])['RMSE_eV_A'])
    gamma=rows('data/visual_story/v001/replay228_gamma.tsv')
    require([int(r['replay_index']) for r in gamma]==list(range(1,229)),'Replay gamma mapping')
    stop=1.0000012996964838
    crossing=[int(r['replay_index']) for r in gamma if float(r['gamma'])>stop]
    endpoint_overlap=[]
    for i,c in enumerate(neb,1):
        for j,t in enumerate(train,1):
            d=fingerprint_difference(c,t)
            if d<=2.1e-6:endpoint_overlap.append({'NEB_image':i,'training_index':j,'max_pair_distance_difference_A':d})
    return {'evidence_class':'SAVED_QE_XML_AND_CFG_RECOMPUTATION','barrier_meV':barrier(pn),'barrier_abs_error_meV':abs(barrier(pn)-barrier(neb)),'central_force_component_RMSE_eV_A':combined_error([audit[i] for i in central],[pred[i] for i in central]),'maximum_relative_profile_residual_meV':max(map(abs,residuals)),'local_cases':local,'local_group_maxima_eV_A':{g:max(c['RMSE_eV_A'] for c in local if c['group']==g) for g in ('CROSSING7','CHALLENGE4')},'Validation11_RMSE_eV_A':vr,'all_local_and_validation_below_A2':all(x['RMSE_eV_A']<=.09 for x in local) and all(v<=.09 for v in vr),'saved_gamma_stop':stop,'saved_crossings':crossing,'Train119_NEb9_pair_distance_overlaps':endpoint_overlap,'scope':'Frames and selected datasets are development diagnostics; saved gamma is re-thresholded, not independently recomputed from an absent live selector.'}


def training_logs():
    root='data/studies/optimization_budget_v001/'
    register=rows(root+'MODEL_STOP_AND_SHA256.tsv')
    require(len(register)==20,'Training log registry count')
    parsed={};summary=[]
    for row in register:
        s,b,cap=int(row['seed_index']),row['branch'],int(row['budget'])
        text=read(root+row['log_path'])
        require(SHA[root+row['log_path']]==row['log_sha256'],'Training log hash registry')
        require(text.count('Pre-training started')==text.count('Pre-training ended')==1,'Exactly one pretraining stage')
        pre,main=text.split('Pre-training ended')
        pattern=r'(?m)^BFGS iter (\d+): f=([-+\d.eE]+)\s*$'
        pre_values=re.findall(pattern,pre);main_values=re.findall(pattern,main)
        require([int(i) for i,v in pre_values]==list(range(75)),'75 ordered pretraining rows')
        require([int(i) for i,v in main_values]==list(range(cap)),'Ordered main rows and cap')
        require('BFGS iterations count set to '+str(cap) in main,'Declared cap disagrees')
        require(main.count('step limit reached')==1 and 'MTPR training ended' in main,'Main stop is not STEP_LIMIT')
        values=[Decimal(v) for i,v in main_values]
        increases=[i for i in range(1,len(values)) if values[i]>values[i-1]]
        parsed[s,b,cap]=(pre_values,main_values)
        summary.append({'seed_index':s,'branch':b,'budget':cap,'main_rows':len(main_values),'pretraining_rows':len(pre_values),'stop':'STEP_LIMIT','first_main_J_printed':str(values[0]),'last_main_J_printed':str(values[-1]),'visible_increases':len(increases),'increases_at_multiple_of_50':all(i%50==0 for i in increases)})
    prefixes=[]
    for s in range(5):
        for b in ('basin','targeted'):
            short,long=parsed[s,b,2000],parsed[s,b,8000]
            require(short[0]==long[0] and short[1]==long[1][:2000],'Printed shared prefix mismatch')
            prefixes.append({'seed_index':s,'branch':b,'pretraining_printed_prefix_equal':True,'first_2000_main_printed_prefix_equal':True})
    return {'evidence_class':'SAVED_TRAINING_LOG_RECOMPUTATION','models':summary,'paired_prefix_checks':prefixes,'total_printed_main_rows':sum(r['main_rows'] for r in summary),'visible_long_run_increases':sum(r['visible_increases'] for r in summary if r['budget']==8000),'all_increases_at_multiple_of_50':all(r['increases_at_multiple_of_50'] for r in summary),'scope':'Counts compare printed decimal objectives, not hidden optimizer state, convergence, or a causal decomposition of the force-error change.'}


def optimization():
    p=json.loads(read('data/optimization_story/v001/OPTIMIZATION_STORY.json'))
    theory=p['theory'];states={s['id']:s for s in theory['main4500']['states']}
    native_closure={k:s['native_J']-s['physical_data_loss']-s['radial_penalty'] for k,s in states.items() if s['native_J'] is not None}
    require(max(map(abs,native_closure.values()))<2e-15, 'Reported native J does not close at published precision')
    with localcontext() as ctx:
        ctx.prec=120
        table={r['state']:r for r in theory['linear_system']['row_loss_table']}
        closure={k:str(Decimal(r['Q_fixed_D'])-Decimal(r['data_loss'])-Decimal(r['ridge_penalty'])) for k,r in table.items()}
        require(all(abs(Decimal(v))<Decimal('1e-98') for v in closure.values()),'Q loss/penalty closure')
        delta={f:str(Decimal(table['S2'][f])-Decimal(table['S1c'][f])) for f in ('data_loss','ridge_penalty','Q_fixed_D')}
        balance=theory['linear_system']['signed_ridge_balance']
        rhs=-Decimal(balance['regularized_improvement_from_compensated'])+Decimal(balance['ridge_tradeoff'])+Decimal(balance['effective_native_solver_row_gap'])
        require(abs(rhs-Decimal(delta['data_loss']))<Decimal('1e-98'),'Signed ridge balance')
        reduction=str(100*(1-Decimal(table['S2']['Q_fixed_D'])/Decimal(table['S1c']['Q_fixed_D'])))
    cov=theory['COV']
    decrease=cov['data_loss_incumbent']-cov['candidate_data_loss_saved_matrix_only']
    require(abs(decrease-cov['data_loss_decrease'])<1e-19,'COV reported data-loss difference')
    require(abs(100*decrease/cov['data_loss_incumbent']-cov['percent_of_total_data_loss_removed'])<1e-12,'COV reported percentage')
    require(abs(decrease-cov['descent_expression'])<1e-19,'COV reported descent identity')
    require(states['S3']['native_J'] is None and not cov['candidate_coefficients_exported'] and cov['candidate_native_EF_or_gradient']=='NOT_EVALUATED','Evidence boundary changed')
    return {'evidence_class':'PUBLISHED_AGGREGATE_ARITHMETIC_ONLY','Q_closures':closure,'S1c_to_S2_changes':delta,'Q_reduction_percent':reduction,'native_J_minus_data_loss_minus_radial_penalty':native_closure,'native_J_S2_over_S0':states['S2']['native_J']/states['S0']['native_J'],'native_J_S2q_minus_S2':states['S2q']['native_J']-states['S2']['native_J'],'COV_data_loss_decrease':decrease,'COV_percent_of_data_loss_removed':100*decrease/cov['data_loss_incumbent'],'COV_reported_descent_expression_residual':decrease-cov['descent_expression'],'reported_COV_coefficient_increment_l2':cov['coefficient_increment_l2'],'reported_COV_regularized_stack_condition_number':cov['regularized_stack_condition_number'],'candidate_exported':cov['candidate_coefficients_exported'],'candidate_native_EF_or_gradient':cov['candidate_native_EF_or_gradient'],'scope':'Missing native states, A/r/D/transforms and process records prevent matrix re-solve, native parity or external-accuracy qualification. Decimal closure is not an independent native reconstruction.'}


def audit():
    a=original();b=pbe14();c=train119();d=optimization();e=training_logs()
    git=lambda *args:subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    return {'schema':'independent-science-audit-v1','status':'PASS_SAVED_PRIMARY_ARRAYS_AND_AGGREGATE_ARITHMETIC','scientific_executions':0,'source_commit':git('rev-parse','HEAD'),'source_tree':git('rev-parse','HEAD^{tree}'),'working_tree_status':git('status','--porcelain=v1'),'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'definitions':{'force_error':'MTP minus PBE in the identical recorded laboratory frame; per-geometry RMSE = sqrt(sum over 27 Cartesian squared differences / 27).','original_primary':'Combined force components over three central images, equivalently sqrt(mean of squared per-geometry RMSE) because each has nine atoms.','PBE14_primary':'Mean per-geometry RMSE within each +/- physical block, then equal mean over four blocks, then paired Targeted minus Basin per seed, then mean of five seeds.','alignment':'No force-vector alignment or atom permutation is fitted to reduce error. Ordered pair distances alone audit rigid-invariant overlap with 2.1e-6 A tolerance.'},'original':a,'PBE14':b,'Train119':c,'optimization':d,'training_logs':e,'source_SHA256':dict(sorted(SHA.items()))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=audit()
    serialized=json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(serialized)
        print(json.dumps({'status':result['status'],'out':str(args.out),'PBE14_primary_eV_A':result['PBE14']['primary']['mean_eV_A'],'source_files':len(SHA)},indent=2))
    else:print(serialized,end='')


if __name__=='__main__':main()

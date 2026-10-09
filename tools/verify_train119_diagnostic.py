#!/usr/bin/env python3
"""Read-only verification of a selected, already computed Train119 diagnostic.

No subprocesses, network, model inference, training, DFT or dynamics. Numerical
PASS below is a payload/metric verdict, never deployment acceptance.
Requires Python 3.11+. Uses the standard library only. The separate endpoint
alignment check in the owner audit uses NumPy, not this validator.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

RY_EV = 13.605693122994
BOHR_A = 0.529177210903
MODEL_SHA = '6eb35503605214a886f3e3d884e93743d66bcaaec05ae58a30111c8c55de2df6'
TRAIN_SOURCE_SHA = '2d3018b9db5fb17fd24546820c25a986a3db174a7724a8fa4d004997d3d7e665'
TYPES = (2, 1, 0, 1, 0, 1, 0, 2, 1)
ELEMENT = {0: 'C', 1: 'H', 2: 'O'}
STOP = 1.0000012996964838
A2 = 0.09

class AuditError(ValueError):
    pass

def require(test: bool, message: str) -> None:
    if not test:
        raise AuditError(message)

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def number(token: str) -> float:
    x = float(token.replace('D', 'E').replace('d', 'e'))
    require(math.isfinite(x), 'Non-finite value')
    return x

@dataclass
class Configuration:
    ids: tuple[int, ...]
    types: tuple[int, ...]
    xyz: list[list[float]]
    cell: list[list[float]]
    energy: float | None
    forces: list[list[float]] | None
    features: dict[str, str]

def parse_cfg(text: str, *, labels: bool = False) -> list[Configuration]:
    """Strict framing/cardinality parser; refuses duplicate IDs and missing fields."""
    chunks: list[list[str]] = []
    active: list[str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == 'BEGIN_CFG':
            require(active is None, 'Nested BEGIN_CFG')
            active = []
        elif line == 'END_CFG':
            require(active is not None, 'Unmatched END_CFG')
            chunks.append(active)
            active = None
        else:
            require(active is not None, 'Text outside CFG blocks')
            active.append(line)
    require(active is None and len(chunks) > 0, 'Truncated or empty CFG')
    result = []
    for lines in chunks:
        require(lines.count('Size') == 1 and lines.count('Supercell') == 1, 'Size/cell cardinality')
        ni = lines.index('Size')
        n = int(lines[ni + 1])
        require(n == 9, 'Expected nine atoms')
        ci = lines.index('Supercell')
        cell = [[number(s) for s in row.split()] for row in lines[ci+1:ci+4]]
        require(len(cell) == 3 and all(len(r) == 3 for r in cell), 'Cell shape')
        require(cell == [[16.,0.,0.],[0.,16.,0.],[0.,0.,16.]], 'Unexpected source cell')
        headers = [i for i,s in enumerate(lines) if s.startswith('AtomData:')]
        require(len(headers) == 1, 'AtomData header cardinality')
        ai = headers[0]
        keys = lines[ai].split(':',1)[1].split()
        require(len(keys) == len(set(keys)), 'Duplicate atom columns')
        require(set(('id','type','cartes_x','cartes_y','cartes_z')).issubset(keys), 'Missing atom columns')
        rows = [row.split() for row in lines[ai+1:ai+1+n]]
        require(len(rows)==n and all(len(row)==len(keys) for row in rows), 'Atom row cardinality')
        if ai+1+n < len(lines):
            require(not re.match(r'^[-+]?\d+\s+[-+]?\d+\s+',lines[ai+1+n]),'Extra atom row after declared cardinality')
        atoms = [dict(zip(keys,row)) for row in rows]
        ids = tuple(int(a['id']) for a in atoms)
        types = tuple(int(a['type']) for a in atoms)
        require(ids == tuple(range(1,10)), 'Atom IDs/order changed')
        require(types == TYPES, 'Atom types/order changed')
        xyz = [[number(a[k]) for k in ('cartes_x','cartes_y','cartes_z')] for a in atoms]
        fk = [k in keys for k in ('fx','fy','fz')]
        require(all(fk) or not any(fk), 'Incomplete force columns')
        forces = [[number(a[k]) for k in ('fx','fy','fz')] for a in atoms] if all(fk) else None
        require(lines.count('Energy') <= 1, 'Duplicate energy field')
        energy = number(lines[lines.index('Energy')+1]) if 'Energy' in lines else None
        require(not labels or (energy is not None and forces is not None), 'Missing labels')
        features = {}
        for line in lines:
            if line.startswith('Feature'):
                f = line.split(None,2)
                require(len(f)==3 and f[1] not in features, 'Malformed/duplicate feature')
                features[f[1]] = f[2]
        result.append(Configuration(ids,types,xyz,cell,energy,forces,features))
    return result

def maxdelta(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> float:
    require(len(a)==len(b)>0 and all(len(x)==len(y)>0 for x,y in zip(a,b)), 'Array shape mismatch')
    return max(abs(x-y) for r,s in zip(a,b) for x,y in zip(r,s))

def distances(xyz: Sequence[Sequence[float]]) -> list[float]:
    return [math.dist(xyz[i],xyz[j]) for i in range(9) for j in range(i+1,9)]

def geometry_guard(a: Configuration, b: Configuration) -> dict[str, float | bool]:
    require(a.ids == b.ids and a.types == b.types, 'Atom mapping changed')
    direct = maxdelta(a.xyz,b.xyz)
    cell = maxdelta(a.cell,b.cell)
    pair = max(abs(x-y) for x,y in zip(distances(a.xyz),distances(b.xyz)))
    return dict(direct_A=direct,cell_A=cell,pair_A=pair,
                pass_guard=direct<=5.1e-7 and cell<=1e-12 and pair<=1.1e-6)

def force_metrics(reference: Sequence[Sequence[float]], predicted: Sequence[Sequence[float]]) -> dict[str, Any]:
    require(len(reference)==len(predicted)==9, 'Force atom count')
    require(all(len(r)==3 for r in list(reference)+list(predicted)), 'Force component count')
    errors = [[number(str(b))-number(str(a)) for a,b in zip(r,p)] for r,p in zip(reference,predicted)]
    flat = [x for row in errors for x in row]
    rmse = math.sqrt(math.fsum(x*x for x in flat)/27)
    return dict(force_component_RMSE_eV_A=rmse,max_abs_component_eV_A=max(map(abs,flat)),
                proton_H2_y_error_eV_A=errors[1][1],crossing_component_C3_y_error_eV_A=errors[2][1],
                proton_H2_vector_error_eV_A=math.sqrt(math.fsum(x*x for x in errors[1])),
                atom_vector_RMSE_eV_A=math.sqrt(3)*rmse,A2_pass=rmse<=A2)

def terminal_pw(text: str) -> tuple[float,list[list[float]],dict[str, Any]]:
    """For this single-SCF payload require exactly one completed official force block.
    Contribution blocks after its nine rows are not reference forces.
    """
    require(text.count('JOB DONE.')==1, 'Missing/ambiguous JOB DONE')
    require('convergence has been achieved' in text and 'convergence NOT achieved' not in text, 'SCF not converged')
    header = 'Forces acting on atoms (cartesian axes, Ry/au):'
    require(text.count(header)==1, 'Official force block cardinality')
    before,after = text.split(header)
    es = re.findall(r'^\s*!\s+total energy\s*=\s*([-+\d.EeDd]+)\s+Ry',before,re.M)
    require(len(es)==1, 'Terminal energy cardinality')
    pattern = re.compile(r'\s*atom\s+(\d+)\s+type\s+(\d+)\s+force\s*=\s*(\S+)\s+(\S+)\s+(\S+)\s*$')
    rows = []
    for line in after.splitlines():
        if not line.strip() and not rows:
            continue
        m = pattern.fullmatch(line)
        if m is None:
            break
        rows.append((int(m[1]),int(m[2]),[number(m[k]) for k in (3,4,5)]))
    require(len(rows)==9, 'Incomplete/extra official forces')
    require([r[0] for r in rows]==list(range(1,10)), 'QE atom IDs/order changed')
    require([r[1] for r in rows]==[x+1 for x in TYPES], 'QE species mapping changed')
    force = [[x*RY_EV/BOHR_A for x in r[2]] for r in rows]
    return number(es[0])*RY_EV,force,dict(official_block_count=1,job_done=True)

def pw_input_declaration(text: str, input_cfg: Configuration) -> dict[str,Any]:
    """Validate the declared single-point setup and numeric input geometry.
    This does not re-hash the external pseudopotential files used by QE.
    """
    clean='\n'.join(line.split('!',1)[0] for line in text.splitlines())
    blocks=re.findall(r'^\s*&(\w+)(.*?)^\s*/\s*$',clean,re.M|re.S)
    nl={}
    for title,body in blocks:
        title=title.lower();require(title not in nl,'Duplicate QE namelist')
        items=re.findall(r"(\w+)\s*=\s*('[^']*'|\"[^\"]*\"|[^,\s]+)",body)
        fields={k.lower():x.strip("'\"").lower() for k,x in items}
        require(len(fields)==len(items),'Duplicate QE namelist key');nl[title]=fields
    control=nl.get('control',{});system=nl.get('system',{});electrons=nl.get('electrons',{})
    require(control.get('calculation')=='scf' and control.get('tprnfor')=='.true.','Not the declared force single point')
    for key,value in [('ibrav',0),('nat',9),('ntyp',3),('ecutwfc',80),('ecutrho',960),('tot_charge',0),('nspin',1)]:
        require(key in system and number(system[key])==value,'QE setup mismatch: '+key)
    require(system.get('input_dft')=='pbe' and system.get('occupations')=='fixed','QE functional/occupation mismatch')
    require(system.get('nosym')=='.true.' and system.get('noinv')=='.true.','QE symmetry setting mismatch')
    require('conv_thr' in electrons and 0<number(electrons['conv_thr'])<=1e-10,'QE SCF tolerance mismatch')
    lines=[x.strip() for x in clean.splitlines() if x.strip()]
    def card(name: str) -> tuple[int,list[str]]:
        hits=[i for i,x in enumerate(lines) if x.split()[0].upper()==name]
        require(len(hits)==1,'QE card cardinality: '+name)
        return hits[0],lines[hits[0]].split()
    ci,ch=card('CELL_PARAMETERS');pi,ph=card('ATOMIC_POSITIONS');ki,kh=card('K_POINTS');si,sh=card('ATOMIC_SPECIES')
    require(len(ch)==len(ph)==len(kh)==2 and ch[1].strip('{}()').lower()==ph[1].strip('{}()').lower()=='angstrom' and kh[1].lower()=='gamma','QE units/k-point mismatch')
    cell=[[number(v) for v in x.split()] for x in lines[ci+1:ci+4]]
    atoms=[x.split() for x in lines[pi+1:pi+10]]
    require(len(atoms)==9 and all(len(x)==4 for x in atoms),'QE position rows')
    require([x[0] for x in atoms]==[ELEMENT[t] for t in TYPES],'QE position species order')
    xyz=[[number(v) for v in x[1:]] for x in atoms]
    require(maxdelta(cell,input_cfg.cell)<=1e-12 and maxdelta(xyz,input_cfg.xyz)<=2e-12,'QE input/CFG geometry mismatch')
    species=[x.split() for x in lines[si+1:si+4]]
    require(len(species)==3 and all(len(x)==3 for x in species),'QE species rows')
    actual={x[0]:x[2] for x in species}
    expected={'C':'C.pbe-n-kjpaw_psl.1.0.0.UPF','H':'H.pbe-kjpaw_psl.1.0.0.UPF','O':'O.pbe-n-kjpaw_psl.1.0.0.UPF'}
    require(actual==expected,'Pseudopotential name mismatch')
    return dict(declared_setup_pass=True,pseudopotential_files_rehashed=False)


def xml_reference(text: str, input_cfg: Configuration) -> tuple[float,list[list[float]]]:
    root = ET.fromstring(text)
    for el in root.iter():
        el.tag=el.tag.split('}')[-1]
    output = root.find('output')
    require(output is not None, 'Missing XML output')
    require((output.findtext('convergence_info/scf_conv/convergence_achieved') or '').strip().lower() == 'true', 'XML SCF not converged')
    structure=output.find('atomic_structure')
    require(structure is not None, 'Missing XML geometry')
    atoms=structure.findall('atomic_positions/atom')
    require(len(atoms)==9 and [a.get('name') for a in atoms]==[ELEMENT[t] for t in TYPES], 'XML species/count')
    xyz=[[number(x)*BOHR_A for x in (a.text or '').split()] for a in atoms]
    cell=[[number(x)*BOHR_A for x in (structure.findtext('cell/'+k) or '').split()] for k in ('a1','a2','a3')]
    require(maxdelta(xyz,input_cfg.xyz)<=2e-12 and maxdelta(cell,input_cfg.cell)<=2e-12, 'XML/input geometry mismatch')
    ef=output.findtext('total_energy/etot')
    require(ef is not None, 'Missing XML energy')
    vals=[number(x) for x in (output.findtext('forces') or '').split()]
    require(len(vals)==27, 'XML force count')
    forces=[[x*2*RY_EV/BOHR_A for x in vals[i:i+3]] for i in range(0,27,3)]
    return number(ef)*2*RY_EV,forces

def static_metrics(ref: list[Configuration], pred: list[Configuration]) -> dict[str,Any]:
    require(len(ref)==len(pred)==21, 'Audit21 cardinality')
    for a,b in zip(ref,pred):
        require(geometry_guard(a,b)['pass_guard'], 'Audit geometry guard')
        require(a.features.get('audit_id')==b.features.get('audit_id'), 'Audit ID mismatch')
    indices=[i for i,a in enumerate(ref) if a.features.get('audit_subset')=='neb9']
    require(len(indices)==9 and [int(ref[i].features['audit_subset_index']) for i in indices]==list(range(1,10)), 'NEB membership/order')
    for i in indices:
        qcalc=math.dist(ref[i].xyz[0],ref[i].xyz[1])-math.dist(ref[i].xyz[7],ref[i].xyz[1])
        require(abs(qcalc-number(ref[i].features['q_pt_A']))<=1e-9,'qPT geometry/metadata mismatch')
    transition=[i for i in indices if abs(number(ref[i].features['q_pt_A']))<=.15]
    require(len(transition)==3, 'Transition definition mismatch; no fallback ranking allowed')
    def barrier(xs: list[Configuration]) -> float:
        es=[xs[i].energy for i in indices]
        require(all(e is not None and math.isfinite(e) for e in es), 'Invalid barrier energy')
        return (max(es)-min(es[0],es[-1]))*1000
    def combined(ii: list[int]) -> float:
        require(bool(ii), 'Empty subset')
        return math.sqrt(math.fsum(force_metrics(ref[i].forces,pred[i].forces)['force_component_RMSE_eV_A']**2 for i in ii)/len(ii))
    return dict(reference_barrier_meV=barrier(ref),Train119_barrier_meV=barrier(pred),
                barrier_abs_error_meV=abs(barrier(pred)-barrier(ref)),transition_force_RMSE_eV_A=combined(transition),
                basin12_force_RMSE_eV_A=combined([i for i,a in enumerate(ref) if a.features.get('audit_subset')=='basin12']),
                NEB9_force_RMSE_eV_A=combined(indices),transition_indices_1based=[i+1 for i in transition],
                independent_holdout=False,formal_energy_pass_defined=False)

def overlap_review(query: list[Configuration], train: list[Configuration]) -> list[dict[str,Any]]:
    require(len(train)==119, 'Train119 cardinality')
    td=[distances(c.xyz) for c in train]; out=[]
    for qi,q in enumerate(query,1):
        ds=distances(q.xyz); candidates=[]
        for ti,(t,d) in enumerate(zip(train,td),1):
            if q.types!=t.types or q.cell!=t.cell: continue
            dif=[a-b for a,b in zip(ds,d)]
            candidates.append((max(map(abs,dif)),math.sqrt(math.fsum(z*z for z in dif)/36),ti))
        candidates.sort()
        for mx,rms,ti in candidates:
            if mx <= 2.1e-6:
                out.append(dict(query_index=qi,query_id=q.features.get('audit_id',q.features.get('candidate_id','')),
                    training_index=ti,pair_max_A=mx,pair_RMS_A=rms,strict_1e_12=mx<=1e-12,screen_2p1e_6=True,
                    interpretation='Known-order distance screen; not by itself force-vector mapping or statistical independence'))
    return out

def verify(root: Path) -> dict[str,Any]:
    root=root.resolve()
    manifest=json.loads((root/'SOURCE_MANIFEST.json').read_text())
    seen=set()
    for r in manifest['files']:
        rel=r['public_path']; p=(root/rel).resolve()
        require(p.is_relative_to(root) and rel not in seen, 'Unsafe/duplicate manifest path');seen.add(rel)
        require(p.is_file() and sha256(p.read_bytes())==r['public_sha256'],'Manifest mismatch: '+rel)
    generated={'SOURCE_MANIFEST.json','OFFLINE_VERIFICATION.json','EXPORT_STATUS.json'}
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    require(actual <= seen|generated,'Unmanifested files in selected data root')
    model=root/'inputs/TRAIN119_MODEL_EXACT.mtp'
    require(sha256(model.read_bytes())==MODEL_SHA, 'Wrong learned model')
    trrec=next((r for r in manifest['files'] if r['public_path']=='inputs/TRAIN119_EXACT.cfg'),None)
    require(trrec is not None and trrec['source_sha256']==TRAIN_SOURCE_SHA, 'Wrong training source')
    read=lambda p,lab=False:parse_cfg((root/p).read_text(),labels=lab)
    train=read('inputs/TRAIN119_EXACT.cfg',True)
    replay=read('inputs/REPLAY228_EXACT.cfg')
    require(len(replay)==228,'Replay228 cardinality')
    allrows=[]
    with (root/'historical/PER_CONFIGURATION_METRICS.tsv').open(encoding='utf-8',newline='') as stream:
        table_rows=list(csv.DictReader(stream,delimiter='\t'))
    table={int(r['replay_index']):r for r in table_rows}
    require(len(table_rows)==len(table)==11 and set(table)==set(range(93,97))|set(range(142,149)), 'Local table identity/cardinality')
    for name,ids,input_name in [('CHALLENGE4',list(range(93,97)),'LOCAL_CHALLENGE4_REPLAY93_96_EXACT.cfg'),('CROSSING7',list(range(142,149)),'CROSSING7_EXACT.cfg')]:
        inp=read('inputs/'+input_name);pred=read('predictions/'+name+'.cfg',True)
        require(len(inp)==len(pred)==len(ids), 'Diagnostic cardinality')
        for i,a,b in zip(ids,inp,pred):
            require(geometry_guard(a,b)['pass_guard'], 'Diagnostic geometry guard')
            require(maxdelta(a.xyz,replay[i-1].xyz)<=1e-12 and a.types==replay[i-1].types,'Wrong Replay228 input frame')
            require(a.features.get('candidate_id')==b.features.get('candidate_id'), 'Diagnostic ID changed')
            d=root/f'references/replay{i:03d}'
            pw_input_declaration((d/'pw.in').read_text(),a)
            e,f,_=terminal_pw((d/'pw.out').read_text())
            xe,xf=xml_reference((d/'data-file-schema.xml').read_text(),a)
            # stdout prints energy and force components to eight decimal places.
            require(abs(e-xe)<=0.5e-8*RY_EV+2e-11 and maxdelta(f,xf)<=0.5e-8*RY_EV/BOHR_A+2e-11, 'QE stdout/XML unit disagreement')
            metrics=force_metrics(f,b.forces)
            saved=table[i]
            require(abs(metrics['force_component_RMSE_eV_A']-float(saved['RMSE_F_eV_A']))<=1e-12, 'Saved metric mismatch')
            g=number(saved['gamma_saved']); require(number(saved['old_stop'])==STOP,'Historical stop changed')
            allrows.append(dict(replay_index=i,role=name,gamma_saved=g,above_stop=g>STOP,energy_error_eV=b.energy-e,**metrics))
    require(sum(row['above_stop'] for row in allrows)==5,'Expected five saved crossings')
    require(all(row['A2_pass'] for row in allrows),'Local A2 not satisfied')
    ref=read('inputs/AUDIT21_REFERENCE_EXACT.cfg',True);pred=read('predictions/AUDIT21_STATIC.cfg',True)
    static=static_metrics(ref,pred)
    require(abs(static['barrier_abs_error_meV']-.122995698802697)<=1e-8, 'Static barrier mismatch')
    require(abs(static['transition_force_RMSE_eV_A']-.01383398828876731)<=1e-12,'Static force mismatch')
    vi=read('inputs/VALIDATION11_EXACT.cfg',True);vp=read('predictions/VALIDATION11_QUALIFICATION.cfg',True)
    require(len(vi)==len(vp)==11, 'Validation11 cardinality')
    validation=[]
    for a,b in zip(vi,vp):
        require(geometry_guard(a,b)['pass_guard'], 'New precision-output guard failed')
        validation.append(force_metrics(a.forces,b.forces))
    ledger=json.loads((root/'historical/SCIENTIFIC_CALL_LEDGER.json').read_text())
    calls=ledger['calls']
    require(len(calls)==11 and all(c.get('status')=='COMPLETED' and c.get('returncode')==0 for c in calls), 'Call record status/count')
    require([c.get('role') for c in calls if c.get('kind')=='MTP_EVALUATION']==['VALIDATION11_QUALIFICATION','CHALLENGE4','CROSSING7','AUDIT21_STATIC'],'MTP call order')
    require([c.get('role') for c in calls if c.get('kind')=='PBE_PW_X']==[f'CROSSING_REFERENCE_{i}' for i in range(142,149)],'PBE call order')
    return dict(status='PASS_SAVED_PAYLOAD_NUMERICS_AND_MAPPING',local_results=allrows,static=static,
                validation11=validation,audit_train_overlap=overlap_review(ref,train),
                validation_train_overlap=overlap_review(vi,train),
                scientific_scope='Development diagnostics; no independent final test, no new threshold calibration',
                deployment_ready=False,blind_payload_read=False,new_scientific_calls=0,
                overlap_scope='Known-order screen only; an exhaustive equivalent-atom permutation audit is not claimed.')

def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data',type=Path,required=True)
    ap.add_argument('--report',type=Path)
    ns=ap.parse_args()
    try: result=verify(ns.data)
    except (OSError,ValueError,KeyError,StopIteration,ET.ParseError) as e:
        print(json.dumps(dict(status='FAIL',error=str(e)),indent=2),file=sys.stderr); return 1
    output=json.dumps(result,indent=2)+'\n'
    if ns.report:
        require(not ns.report.exists(),'Refuse to overwrite report')
        ns.report.parent.mkdir(parents=True,exist_ok=True);ns.report.write_text(output)
    else: print(output,end='')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

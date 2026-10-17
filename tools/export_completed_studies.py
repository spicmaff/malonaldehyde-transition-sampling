#!/usr/bin/env python3
"""Allowlisted publication export of completed studies. Reads saved files only.
No electronic-structure, model evaluation, training or selection is executed.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, re
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_tsv(path):
    return list(csv.DictReader(path.open(encoding='utf-8'), delimiter='\t'))


def tsv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    return out.getvalue()


def sanitized(text):
    # Only owner-specific path prefixes; all numerical tokens stay unchanged.
    text = re.sub(r'/home/[^/\s"\']+/', 'OWNER_HOME/', text)
    text = re.sub(r'/mnt/c/' + r'Users/[^/\s"\']+/', 'OWNER_WINDOWS/', text)
    return text


def export(pbe: Path, budget: Path, audit: Path, repo: Path):
    roots = {'PBE14_RECOVERY': pbe, 'OPTIMIZATION_BUDGET': budget, 'INDEPENDENT_AUDIT': audit}
    p = repo/'data/studies/pbe14_mtp20_v001'
    b = repo/'data/studies/optimization_budget_v001'
    require(not p.exists() and not b.exists(), 'Refuse an existing publication destination')
    p.mkdir(parents=True); b.mkdir(parents=True)
    source_maps = {p: [], b: []}
    protected = []

    def copy(alias, relative, dest, group):
        source = roots[alias]/relative
        raw = source.read_bytes(); text = raw.decode('utf-8')
        clean = sanitized(text).encode('utf-8')
        require(re.findall(rb'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', raw) ==
                re.findall(rb'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', clean),
                'Numerical token changed by sanitization: '+relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(clean)
        protected.append((source, sha(raw)))
        source_maps[group].append({'study_id': group.name, 'role': dest.parent.name,
            'public_path': dest.relative_to(group).as_posix(), 'source_alias': alias,
            'source_relative_path': relative, 'source_sha256': sha(raw), 'source_bytes': len(raw),
            'public_sha256': sha(clean), 'public_bytes': len(clean),
            'transformation': 'OWNER_PATH_PREFIX_ONLY' if raw != clean else 'BYTE_IDENTICAL',
            'publication_scope': 'Project-owned generated data; no external code, binary or UPF'})
        return sha(clean)

    lock_rel = '01_FROZEN_EXECUTION_PROTOCOL/EXECUTION_PROTOCOL_LOCK.json'
    lock = json.loads((pbe/lock_rel).read_text())
    copy('PBE14_RECOVERY', lock_rel, p/'PROTOCOL_LOCK.json', p)
    ref_rel = '05_FROZEN_PBE_LABELS/PROSPECTIVE_PBE_LABELS.cfg'
    require(sha((pbe/ref_rel).read_bytes()) == 'c5faaa3764e7d86af34e1172fce7bae0a8147c27cef684734a52ca9c28879dde', 'PBE reference differs')
    copy('PBE14_RECOVERY', ref_rel, p/'references/PBE14_EXACT.cfg', p)
    for rel, name in [
        ('01_FROZEN_EXECUTION_PROTOCOL/RECOVERY_ADDENDUM.json','provenance/RECOVERY_ADDENDUM.json'),
        ('05_FROZEN_PBE_LABELS/PBE_REFERENCE_MANIFEST.json','provenance/PBE_REFERENCE_MANIFEST.json'),
        ('05_FROZEN_PBE_LABELS/FREEZE_EVENT.json','provenance/LABEL_FREEZE_EVENT.json'),
        ('06_FROZEN_MTP_EVALUATION/MTP_PREDICTIONS_MANIFEST.tsv','provenance/ORIGINAL_PREDICTIONS_MANIFEST.tsv'),
        ('08_STATISTICAL_ANALYSIS/PRIMARY_ENDPOINT_RESULTS.json','RESULTS_EXPECTED.json'),
        ('07_NUMERICAL_ANALYSIS/ALL_OFFPATH_METRICS.tsv','provenance/ORIGINAL_280_METRICS.tsv'),
        ('01_FROZEN_EXECUTION_PROTOCOL/QE_BINARY_AND_PSEUDO_MANIFEST.tsv','provenance/EXTERNAL_SOFTWARE_IDENTITIES.tsv')]:
        copy('PBE14_RECOVERY',rel,p/name,p)
    copy('INDEPENDENT_AUDIT','evidence/INDEPENDENT_14_GEOMETRY_NEAREST.tsv',p/'provenance/HISTORICAL_NEAREST_GEOMETRIES.tsv',p)
    copy('INDEPENDENT_AUDIT','evidence/PROSPECTIVE_PRIMARY_INDEPENDENT_VALIDATION.json',p/'provenance/INDEPENDENT_PRIMARY_VALIDATION.json',p)
    roles = []
    require(len(lock['candidates']) == 14, '14 candidates required')
    for c in lock['candidates']:
        roles.append({k:c[k] for k in ['id','region','neb_image','mode','sign','block','amplitude_A','max_atom_displacement_A']})
        for suffix in ['in','out']:
            rel = f"03_PBE_SINGLE_POINTS/{c['id']}/pw.{suffix}"
            copy('PBE14_RECOVERY', rel, p/f"qe/{c['id']}/pw.{suffix}", p)
    (p/'GEOMETRY_ROLES.tsv').write_text(tsv(roles), encoding='utf-8')

    models = read_tsv(pbe/'06_FROZEN_MTP_EVALUATION/MTP_PREDICTIONS_MANIFEST.tsv')
    model_sources = read_tsv(pbe/'01_FROZEN_EXECUTION_PROTOCOL/MODEL_SHA256_MANIFEST.tsv')
    require(len(models)==20 and len(model_sources)==20, '20 saved model identities required')
    records=[]; stops=[]
    for row, source in zip(models,model_sources):
        key=[row[k] for k in ['seed_index','seed_u64','branch','budget']]
        require(key==[source[k] for k in ['seed_index','seed_u64','branch','budget']], 'Model identity ordering')
        require(row['model_sha256']==source['sha256'], 'Model source digest mismatch')
        model=Path(source['source_path'])
        require(model.is_file() and sha(model.read_bytes())==row['model_sha256'], 'Frozen model SHA mismatch')
        protected.append((model,row['model_sha256']))
        rel=row['predictions_file'];raw=(pbe/rel).read_bytes()
        require(sha(raw)==row['prediction_sha256'],'Prediction source SHA mismatch')
        name=f"seed_{int(row['seed_index']):02d}_{row['branch']}_{row['budget']}"
        public_hash=copy('PBE14_RECOVERY',rel,p/f'predictions/{name}.cfg',p)
        records.append({k:row[k] for k in ['seed_index','seed_u64','branch','budget','model_sha256']} |
                       {'prediction_path':f'predictions/{name}.cfg','prediction_sha256':public_hash,
                        'source_prediction_sha256':row['prediction_sha256']})
        if row['budget']=='2000':
            log=f"02_SOURCE_SNAPSHOTS/baseline2000/seed_{int(row['seed_index']):02d}_{row['seed_u64']}/{row['branch']}/training.stdout.txt"
        else:
            log=f"03_TRAINING_8000/seed_{int(row['seed_index']):02d}_{row['branch']}/stdout.txt"
        loghash=copy('OPTIMIZATION_BUDGET',log,b/f'logs/{name}.txt',b)
        stops.append({k:row[k] for k in ['seed_index','seed_u64','branch','budget','model_sha256']} |
                     {'log_path':f'logs/{name}.txt','log_sha256':loghash,'expected_stop':'STEP_LIMIT'})
    (p/'MODELS_AND_PREDICTIONS_SHA256.tsv').write_text(tsv(records),encoding='utf-8')
    (b/'MODEL_STOP_AND_SHA256.tsv').write_text(tsv(stops),encoding='utf-8')
    copy('OPTIMIZATION_BUDGET','01_FROZEN_PROTOCOL/PROTOCOL_LOCK.json',b/'PROTOCOL_LOCK.json',b)
    for name in ['ALL_METRICS_2000_VS_8000.tsv','PAIRED_DIFFERENCES.tsv','TRAINING_CONVERGENCE_COMPARISON.tsv','ANALYSIS_SUMMARY.json']:
        copy('OPTIMIZATION_BUDGET','06_NUMERICAL_ANALYSIS/'+name,b/'historical_analysis'/name,b)
    for group in [p,b]:
        (group/'SOURCE_TO_PUBLIC_MANIFEST.tsv').write_text(tsv(source_maps[group]),encoding='utf-8')
        manifest={f.relative_to(group).as_posix():sha(f.read_bytes()) for f in sorted(group.rglob('*')) if f.is_file()}
        (group/'INPUT_MANIFEST.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    require(all(sha(path.read_bytes())==h for path,h in protected),'Source changed during publication export')
    return {'status':'ALLOWLIST_EXPORT_PASS','model_identities':len(records),'geometries':len(roles),
            'protected_source_reads':len(protected),'source_bytes_unchanged':True,
            'new_scientific_calls':0,'published_model_binaries':0,'new_data_bytes':sum(f.stat().st_size for x in [p,b] for f in x.rglob('*') if f.is_file())}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ['pbe','budget','audit','repo']:ap.add_argument('--'+key,type=Path,required=True)
    args=ap.parse_args()
    print(json.dumps(export(args.pbe,args.budget,args.audit,args.repo),indent=2))

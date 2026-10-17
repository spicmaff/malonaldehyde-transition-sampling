"""A separate payload for completed off-path studies, never a replacement for science.json."""
from __future__ import annotations
import hashlib,json,os,re,shutil,subprocess
from pathlib import Path
from verify_pbe14_offpath import verify,table,require
from verify_optimizer_budget import verify as verify_budget
ROOT=Path(__file__).resolve().parents[1]
STUDY='data/studies/pbe14_mtp20_v001'
REPO='https://github.com/spicmaff/malonaldehyde-transition-sampling'


def payload():
    result=verify();budget=verify_budget()
    stored=json.loads((ROOT/STUDY/'results/VERIFICATION.json').read_text())
    require(result==stored,'Committed derived PBE14 results differ from raw recomputation')
    require(budget==json.loads((ROOT/'data/studies/optimization_budget_v001/results/VERIFICATION.json').read_text()),'Committed budget results differ')
    source_ref=os.environ.get('PROTON_SOURCE_REF','')
    if not source_ref:
        try:source_ref=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
        except (subprocess.CalledProcessError,FileNotFoundError):source_ref=(ROOT/'provenance/COMPLETED_STUDY_SOURCE_COMMIT.txt').read_text().strip()
    require(re.fullmatch(r'[A-Za-z0-9_./-]+',source_ref) is not None,'Invalid source ref')
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/STUDY/'INPUT_MANIFEST.json',ROOT/STUDY/'results/VERIFICATION.json',ROOT/'data/studies/optimization_budget_v001/INPUT_MANIFEST.json']}
    nearest=table(ROOT/STUDY/'provenance/HISTORICAL_NEAREST_GEOMETRIES.tsv')
    return {'schema':'proton-offpath-v1','study_id':'pbe14_mtp20_v001','source_ref':source_ref,
            'source_commit_pinned':bool(re.fullmatch('[0-9a-f]{40}',source_ref)),
            'source_url':f'{REPO}/tree/{source_ref}/{STUDY}',
            'source_hashes':hashes,'benchmark':result,'optimizer':budget,'nearest_geometry':nearest,
            'claims':{'original_both_neb_metrics_wins':3,'new_pbe14_transition_cap8000_wins':4,
                      'separate_studies':True,'new_scientific_calls':0,'deployment_validated':False}}


def build(out):
    out=Path(out);p=payload()
    (out/'data').mkdir(exist_ok=True)
    (out/'data/offpath.json').write_text(json.dumps(p,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
    downloads=out/'data/offpath';downloads.mkdir(exist_ok=True)
    for source in sorted((ROOT/STUDY/'results').glob('*.tsv')):shutil.copyfile(source,downloads/source.name)
    for name in ['offpath.mjs','offpath.css']:
        shutil.copyfile(ROOT/'site'/name,out/name)
    return p

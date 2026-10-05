#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math,subprocess,sys
from pathlib import Path

STATUS="PASS_PUBLIC_REPOSITORY_SELFTESTS_V003"
REQUIRED=(
 "provenance/CURRENT_CANONICAL_LEDGER.json","provenance/PROJECT_CANONICAL_LEDGER_V005.tsv","tools/check_ledger_semantics.py",
 "README.md","CITATION.cff","environment.yml","requirements.txt",
 "docs/METHODS.md","docs/LIMITATIONS.md","docs/PIPELINE.md","docs/REPRODUCIBILITY_STATUS.md",
 "docs/EXECUTION_BOUNDARY.md","docs/CI_SCOPE.md","docs/SOFTWARE_PROVENANCE.md",
 "docs/TRAINING_RANDOMNESS.md","docs/POST_PUBLICATION_CONTINUATION.md",
 "scripts/SCRIPT_INDEX.tsv","scripts/core_pipeline/CORE_PIPELINE_MANIFEST.tsv",
 "provenance/PUBLIC_ASSET_MANIFEST.tsv","provenance/PUBLIC_CLAIM_LEDGER.tsv","reports/REPRODUCIBILITY_MATRIX.tsv",
 "data/publication_source_v005/PUBLICATION_SOURCE_MANIFEST.tsv",
 "data/frozen_models_v028/MANIFEST.tsv",
 "data/robustness/v028_seed_robustness_v001/MANIFEST.tsv","data/post_publication/MANIFEST.tsv",
 "tools/audit_public_repo.py","tools/run_public_selftests.py","tools/recompute_primary_metrics.py",
 ".github/workflows/audit.yml",".github/workflows/selftest.yml","reproduce/run_repository_selftests.sh",
)
DEPRECATED=("scripts/stage62_frozen_path_1d_tunneling_audit_v003.py","scripts/render_stage63_supplementary_figure_s3_quantum_audit_v005.py")
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def rows(p):
 with Path(p).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f,delimiter='\t'))
def manifest_bool(value):
 raw=str(value).strip().lower()
 if raw in {'true','1','yes'}:return True
 if raw in {'false','0','no'}:return False
 raise ValueError(f'Invalid manifest boolean: {value!r}')
def close(a,b,tol=1e-9):return math.isfinite(float(a)) and abs(float(a)-float(b))<=tol
def main():
 ap=argparse.ArgumentParser();ap.add_argument('root',nargs='?',type=Path,default=Path('.'));root=ap.parse_args().root.resolve()
 failures=[];checks={}
 miss=[x for x in REQUIRED if not (root/x).is_file()]
 if miss:failures.append(f"Missing required files: {miss}")
 checks['required_files']=len(REQUIRED)-len(miss)
 for x in DEPRECATED:
  if (root/x).exists():failures.append(f"Deprecated duplicate exists: {x}")
 cp=subprocess.run([sys.executable,'-m','compileall','-q','scripts','tools'],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if cp.returncode:failures.append("Python compilation failed:\n"+cp.stdout)
 checks['python_compile']=cp.returncode==0

 core=rows(root/'scripts/core_pipeline/CORE_PIPELINE_MANIFEST.tsv')
 if len(core)!=12:failures.append(f"Expected 12 core scripts, found {len(core)}")
 seen=set()
 for r in core:
  rel=r['repository_path'];p=root/rel
  if rel in seen:failures.append(f"Duplicate core path: {rel}")
  seen.add(rel)
  if not p.is_file():failures.append(f"Missing core script: {rel}")
  elif sha(p)!=r['repository_sha256']:failures.append(f"Core checksum mismatch: {rel}")
 checks['core_manifest_entries']=len(core)

 idxrows=rows(root/'scripts/SCRIPT_INDEX.tsv');index={r['repository_path']:r for r in idxrows}
 actual={p.relative_to(root).as_posix():p for p in sorted((root/'scripts').rglob('*.py'))}
 if set(index)!=set(actual):failures.append(f"SCRIPT_INDEX mismatch missing={sorted(set(actual)-set(index))} extra={sorted(set(index)-set(actual))}")
 for rel,p in actual.items():
  r=index.get(rel)
  if r and (r['sha256']!=sha(p) or r['size_bytes']!=str(p.stat().st_size)):failures.append(f"Script-index metadata mismatch: {rel}")
 checks['script_index_entries']=len(index)

 asset=rows(root/'provenance/PUBLIC_ASSET_MANIFEST.tsv');names=set();paths=set()
 for r in asset:
  rel=r['repository_path'];p=root/rel
  if r['logical_name'] in names:failures.append(f"Duplicate public asset logical name: {r['logical_name']}")
  if rel in paths:failures.append(f"Duplicate public asset path: {rel}")
  names.add(r['logical_name']);paths.add(rel)
  if not p.is_file():failures.append(f"Missing public asset: {rel}");continue
  if sha(p)!=r['repository_sha256']:failures.append(f"Public asset checksum mismatch: {rel}")
  if p.stat().st_size!=int(r['size_bytes']):failures.append(f"Public asset size mismatch: {rel}")
  try:sanitized=manifest_bool(r.get('sanitized',''))
  except ValueError as e:failures.append(f"Public asset {rel}: {e}");sanitized=False
  if r.get('source_sha256') and r['source_sha256']!=r['repository_sha256'] and not sanitized:
   failures.append(f"Public asset source/repository hash differs without sanitized=TRUE: {rel}")
 checks['public_asset_manifest_entries']=len(asset)

 data_specs=[
  ('data/publication_source_v005/PUBLICATION_SOURCE_MANIFEST.tsv','relative_path','data/publication_source_v005'),
  ('data/frozen_models_v028/MANIFEST.tsv','repository_path','data/frozen_models_v028'),
  ('data/robustness/v028_seed_robustness_v001/MANIFEST.tsv','relative_path','data/robustness/v028_seed_robustness_v001'),
  ('data/post_publication/MANIFEST.tsv','relative_path','data/post_publication'),
 ]
 for manifest,field,subtree in data_specs:
  rr=rows(root/manifest);seen=set();manifested=set()
  for r in rr:
   rel=r[field];repo_rel=(f"{subtree}/{rel}" if field=='relative_path' else rel)
   if repo_rel in seen:failures.append(f"Duplicate data-manifest path: {repo_rel}")
   seen.add(repo_rel);manifested.add(repo_rel);p=root/repo_rel
   if not p.is_file():failures.append(f"Missing data-manifest file: {repo_rel}");continue
   if sha(p)!=r['repository_sha256']:failures.append(f"Data-manifest checksum mismatch: {repo_rel}")
   if p.stat().st_size!=int(r['repository_bytes']):failures.append(f"Data-manifest size mismatch: {repo_rel}")
   try:sanitized=manifest_bool(r.get('sanitized',''))
   except ValueError as e:failures.append(f"Data manifest {repo_rel}: {e}");sanitized=False
   if r.get('source_sha256') and r['source_sha256']!=r['repository_sha256'] and not sanitized:
    failures.append(f"Data source/repository hash differs without sanitized=TRUE: {repo_rel}")
   if r.get('source_bytes') and int(r['source_bytes'])!=int(r['repository_bytes']) and not sanitized:
    failures.append(f"Data source/repository size differs without sanitized=TRUE: {repo_rel}")
  actual={x.relative_to(root).as_posix() for x in (root/subtree).rglob('*') if x.is_file() and x.relative_to(root).as_posix()!=manifest}
  if manifested!=actual:
   failures.append(f"Data-manifest coverage mismatch for {subtree}: missing={sorted(actual-manifested)} extra={sorted(manifested-actual)}")
 checks['data_manifests']=True

 pr=subprocess.run([sys.executable,'tools/recompute_primary_metrics.py'],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if pr.returncode:failures.append("Primary recomputation failed:\n"+pr.stderr)
 else:
  try:
   x=json.loads(pr.stdout);m=x['metrics']
   exp={'basin':(35.245734070031176,0.1760826457854536),'targeted':(4.10039360394876,0.07868490481909636)}
   for b,(eb,ef) in exp.items():
    if not close(m[b]['lower_endpoint_barrier_abs_error_meV'],eb):failures.append(f"Primary barrier mismatch {b}")
    if not close(m[b]['transition_force_component_RMSE_eV_A'],ef):failures.append(f"Primary force mismatch {b}")
   if len(x['audit21_train60_geometry_overlaps'])!=4:failures.append("Expected two endpoint overlaps in each Train60 branch")
   checks['primary_recompute']=True
  except Exception as e:failures.append(f"Primary recomputation parse failure: {e}")

 env=(root/'environment.yml').read_text().lower();req=(root/'requirements.txt').read_text().lower()
 for token,text,name in [('pillow',env,'environment.yml'),('ffmpeg',env,'environment.yml'),('pillow',req,'requirements.txt')]:
  if token not in text:failures.append(f"{token} missing from {name}")
 docs='\n'.join((root/x).read_text(errors='replace').lower() for x in ['README.md','docs/METHODS.md','docs/PIPELINE.md','docs/LIMITATIONS.md'])
 if 'same independent nine-image pbe neb path' in docs:failures.append("Obsolete whole-NEB independence claim remains")
 if '24 candidates' not in (root/'README.md').read_text().lower():failures.append("README lacks 24-candidate/K=24 sampling caveat")
 if 'training randomness' not in (root/'README.md').read_text().lower():failures.append("README lacks training-randomness caveat")
 renderers=sorted((root/'scripts/figures').glob('*.py'))+[root/'scripts/tables/build_supplementary_table_s1_complete_numerical_audit_v023.py']+sorted((root/'scripts/videos').glob('*.py'))+[root/'scripts/quantum/stage62_frozen_path_1d_tunneling_audit_v003.py',root/'scripts/quantum/render_stage63_supplementary_figure_s3_quantum_audit_v005.py']
 for script in renderers:
  if '--source-root' not in script.read_text(errors='replace'):failures.append(f"Renderer lacks explicit --source-root: {script.relative_to(root)}")
 checks['source_root_cli_scripts']=len(renderers)
 workflow=(root/'.github/workflows/selftest.yml').read_text()
 if 'run_public_selftests.py' not in workflow or 'recompute_primary_metrics.py' not in workflow:failures.append("Selftest workflow lacks required checks")
 if 'render_all_figures.sh' not in workflow or 'build_supplementary_table_s1.sh' not in workflow:failures.append("Reproduction-smoke workflow does not perform actual figure/table render")
 audit=subprocess.run([sys.executable,'tools/audit_public_repo.py','.'],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if audit.returncode:failures.append("Public repository audit failed:\n"+audit.stdout)
 checks['public_audit']=audit.returncode==0
 semantic=subprocess.run([sys.executable,'tools/check_ledger_semantics.py'],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if semantic.returncode:failures.append('Ledger semantic review failed:\n'+semantic.stdout)
 checks['ledger_source_semantics_and_mutations']=semantic.returncode==0
 result={'status':STATUS if not failures else 'FAIL','root':str(root),'checks':checks,'failure_count':len(failures),'failures':failures}
 print(json.dumps(result,indent=2));return 0 if not failures else 1
if __name__=='__main__':raise SystemExit(main())

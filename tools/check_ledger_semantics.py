#!/usr/bin/env python3
"""Check source-bound ledger interpretation independently of its private builder."""
from pathlib import Path
import csv, json, hashlib, copy, sys

def read_tsv(path):
    with path.open(newline='',encoding='utf-8') as handle:
        return list(csv.DictReader(handle,delimiter='\t'))

def check_ledger(root, records=None):
    pointer=json.loads((root/'provenance/CURRENT_CANONICAL_LEDGER.json').read_text())
    ledger_path=root/pointer['canonical_ledger']
    rows=records if records is not None else read_tsv(ledger_path)
    old=read_tsv(root/pointer['historical_v004'])
    frozen=json.loads((root/pointer['semantic_adjudication']).read_text())
    source_data=json.loads((root/pointer['source_excerpts']).read_text())
    src={x['record_identity']:x for x in source_data['records']}
    expected={x['record_identity']:x for x in frozen['adjudications']}
    failures=[]
    def require(ok,message):
        if not ok:failures.append(message)
    ident=lambda x:x['stage_or_version']+'|'+x['attempt']
    ids=[ident(x) for x in rows]
    require(len(rows)==290 and len(set(ids))==290,'Record cardinality/identity uniqueness')
    require(ids==[ident(x) for x in old],'Historical record sequence changed')
    require(hashlib.sha256((root/pointer['historical_v004']).read_bytes()).hexdigest()==pointer['historical_v004_repository_sha256'],'Historical V004 bytes changed')
    if records is None:
        require(hashlib.sha256(ledger_path.read_bytes()).hexdigest()==pointer['canonical_ledger_repository_sha256'],'Current ledger digest')
    for i,row in enumerate(rows):
        key=ident(row);e=expected.get(key);s=src.get(key)
        if e is None:
            require(i<len(old) and row['status_class']==old[i]['status_class'] and row['authority']=='NO_TERMINAL_RECORD_LOCATED' and row['stage_own_status']=='UNKNOWN_NO_TERMINAL_SOURCE',f'Unbound record promoted: {key}')
        else:
            require(row['status_class']==e['expected_class'],f'Source-adjudicated class: {key}')
            require(row['authority']==e['source_path'] and row['authority_sha256']==e['source_sha256'],f'Authority binding: {key}')
            require(s is not None and s['source_sha256']==row['authority_sha256'],f'Source excerpt binding: {key}')
            require(row['stage_own_status']==str(e['stage_own_status']) and row['preserved_scientific_outcome']==e['preserved_scientific_outcome'],f'Stage/previous outcome separation: {key}')
    def case(i):
        if i>=len(rows):return {},{}
        row=rows[i];return row,src.get(ident(row),{}).get('fields',{})
    row,d=case(56);require(d.get('status')=='FAIL_NEB_PROCESS_v024' and d.get('returncode')==137 and row.get('status_class')=='TECHNICAL_FAIL','Failed NEB process incorrectly promoted')
    row,d=case(157);require(d.get('status')=='PASS_STAGE76E_READ_ONLY_GATE1_FAILURE_POSTMORTEM_EXECUTION' and d.get('failure_class') is None and d.get('technical_grade_replay_pass') is True and row.get('status_class')=='AUTHORITATIVE_WITH_CAVEAT','Successful postmortem confused with historical Gate1 failure')
    for i,prefix in [(230,'PASS_STAGE89T_R1_'),(232,'PASS_STAGE89U_')]:
        row,d=case(i);require(str(d.get('status','')).startswith(prefix) and d.get('scientific_failure_established') is False and row.get('status_class')=='AUTHORITATIVE_WITH_CAVEAT',f'Successful technical recovery review/closure {i}')
    row,d=case(246);require(d.get('error')=="Stop('Train115 selector calibration failed')" and row.get('status_class')=='TECHNICAL_FAIL','Stage90I partial technical failure lost')
    row,d=case(247);require(str(d.get('status','')).startswith('PASS_STAGE90J_') and d.get('scientific_execution_performed_by_reviewer') is False and d.get('A2_adjudication_performed') is False and d.get('gamma_adjudication_performed') is False and row.get('status_class')=='AUTHORITATIVE_WITH_CAVEAT','Stage90J FAIL substring in FAILURE regression')
    row,d=case(248);require(str(d.get('status','')).startswith('PASS_STAGE90K_') and d.get('root_cause_class')=='OBSOLETE_STAGE85B_TRAIN92_CARDINALITY_GUARD_AFTER_COMPLETE_CALIBRATION_TSV_EMISSION' and d.get('model_evaluations')==0 and row.get('status_class')=='AUTHORITATIVE_WITH_CAVEAT','Stage90K successful technical closure regression')
    row,d=case(254);require('validation11 pair-distance serialization drift' in str(d.get('error','')) and row.get('status_class')=='TECHNICAL_FAIL','Stage90Q serialization failure lost')
    row,d=case(282);require(d.get('status')=='TECHNICAL_SERIALIZATION_NONCONFORMANCE_AFTER_COMPLETE_VALIDATION11_CALC_EFS' and d.get('validation11_serialization_guard',{}).get('pair_pass') is False and d.get('validation11_raw_all_11_A2_pass') is True and row.get('status_class')=='TECHNICAL_FAIL','Stage91J serialization/A2 distinction lost')
    row,d=case(284);require(d.get('primary_classification')=='STATIC_APPLICABILITY_FAIL' and d.get('Train119_force_accuracy_failure_established') is False and row.get('status_class')=='SCIENTIFIC_FAIL','Stage91L negative scientific outcome lost')
    row,d=case(154);require(d.get('failure_class')=='GENUINE_SCIENTIFIC_GATE1_FAIL' and row.get('status_class')=='SCIENTIFIC_FAIL','Genuine Gate1 FAIL erased')
    row,d=case(218);require(str(d.get('scientific_interpretation','')).startswith('CONFIRMED_LOCAL_APPLICABILITY_COVERAGE_DEFICIENCY') and row.get('status_class')=='SCIENTIFIC_FAIL','PASS closure incorrectly implies scientific PASS')
    row,d=case(234);require(d.get('readiness_classification')=='NOT_READY_FOR_GATE1' and d.get('readiness_checks',{}).get('STAGE89G_REPLAY228_all_gamma_le_proposed_stop') is False and row.get('status_class')=='SCIENTIFIC_FAIL','PASS execution incorrectly implies readiness PASS')
    row,d=case(190);require(row.get('status_class')=='SUPERSEDED' and 'v085b2_' in row.get('superseded_by',''),'Superseded Stage85B revived')
    return failures

def run_regressions(root):
    p=json.loads((root/'provenance/CURRENT_CANONICAL_LEDGER.json').read_text())
    rows=read_tsv(root/p['canonical_ledger']);tests=[]
    # Mutate the actual accepted records, including positive reviews and real negative outcomes.
    for i in [56,143,150,154,157,190,218,230,231,232,234,246,247,248,254,282,284]:
        mutated=copy.deepcopy(rows)
        mutated[i]['status_class']='SCIENTIFIC_FAIL' if rows[i]['status_class']!='SCIENTIFIC_FAIL' else 'AUTHORITATIVE'
        if not check_ledger(root,mutated):raise AssertionError(f'Undetected class mutation {i}')
        tests.append(f'reject_wrong_class_{i}')
    for label,mutation in [('missing_record',rows[:-1]),('duplicate_record',rows[:-1]+[rows[0]])]:
        if not check_ledger(root,mutation):raise AssertionError(label)
        tests.append(label)
    mutated=copy.deepcopy(rows);mutated[247]['authority_sha256']='0'*64
    if not check_ledger(root,mutated):raise AssertionError('Bad source binding')
    tests.append('reject_corrupt_source_binding')
    return tests

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parents[1]).resolve()
    errors=check_ledger(root)
    if errors:
        print(json.dumps({'status':'FAIL','failures':errors},indent=2));return 1
    tests=run_regressions(root)
    print(json.dumps({'status':'PASS','records':290,'source_bound_records':235,'inventory_only_records':55,'regression_mutations_rejected':len(tests),'tests':tests,'boundary':'Source-bound compact governance review; no scientific rerun.'},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())

#!/usr/bin/env python3
"""Public-only finale derivative. Decimal arithmetic; no native models or solvers."""
from __future__ import annotations
import argparse
import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'data/optimization_story/v001/OPTIMIZATION_STORY.json'
SOURCE_SHA = '91ba4b11b43a6966b2e1cc4ef43eef765bedd58a7de1f0975ae14b2550185131'
SOURCE_REF = 'd713f60a3050f6a7b27a0d3e679e0bf58b93ddf0'
VISIBLE_LIMIT = 'Engineered and checked on synthetic runs. Not yet demonstrated to be a better real-data optimizer.'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError('Scientific finale: ' + message)


def dec(value) -> Decimal:
    require(not isinstance(value, bool), 'boolean is not a measurement')
    d = Decimal(str(value))
    require(d.is_finite(), 'nonfinite number')
    return d


def derive(payload: dict) -> dict:
    """Validate semantics and derive only scalars from the reviewed public export."""
    t = payload['theory']; episode = t['main4500']; linear = t['linear_system']
    require(payload['schema'] == 'proton-optimization-v1', 'source schema')
    require(episode['native_order'] == ['S0','S1','S2','S3','S4'], 'native versus diagnostic order')
    states = {s['id']: s for s in episode['states']}
    require(states['S3']['native_J'] is None and states['S3']['status'] == 'NOT_MEASURED', 'S3 is unmeasured')
    require(not states['S1c']['native_trajectory'] and not states['S2q']['native_trajectory'], 'copies are branches')
    systems = linear['systems']
    require({s['id'] for s in systems} == {'ROW_EXACT_FIXED_D','CAPTURE_G_PLUS_EXACT_D','ACTUAL_K_CAPTURE'}, 'three distinct systems')
    require([s['id'] for s in systems if s['new_S2q_physical_target']] == ['ROW_EXACT_FIXED_D'], 'S2q target')
    require(linear['signed_ridge_balance']['normalization'] == 60, 'row normalization')
    require(payload['scope']['new_scientific_calls_by_site_build'] == 0, 'no new science')
    require(payload['scope']['COV_real_data_optimizer_superiority_proven'] is False, 'no optimizer superiority')
    require(payload['scope']['T2_executed'] is False and payload['scope']['T2_authorized'] is False, 'T2 unexecuted')
    require(payload['t1']['statuses']['T1'] == 'T1_PASS_ENGINEERING_SYNTHETIC_ONLY', 'synthetic T1 only')
    require(payload['t1']['statuses']['T2'] == 'T2_NOT_AUTHORIZED_NOT_EXECUTED', 'future status is not a result')
    require(payload['t1']['statuses']['visible_limit'] == VISIBLE_LIMIT, 'visible qualification')
    cov = t['COV']
    require(cov['candidate_native_EF_or_gradient'] == 'NOT_EVALUATED' and cov['candidate_coefficients_exported'] is False, 'no evaluated COV model')
    require('32x30' in cov['feasible_space'] and 'chosen' in cov['covariance_scope'], 'fixed feasible space and chosen metric')
    with localcontext() as ctx:
        ctx.prec = 140
        rows = {r['state']: r for r in linear['row_loss_table']}
        for r in rows.values():
            require(abs(dec(r['data_loss']) + dec(r['ridge_penalty']) - dec(r['Q_fixed_D'])) < Decimal('1e-95'), 'Q must equal ell + R')
        a,b = rows['S1c'], rows['S2']
        delta = {k: dec(b[k])-dec(a[k]) for k in ('data_loss','ridge_penalty','Q_fixed_D')}
        require(delta['data_loss'] > 0 and delta['ridge_penalty'] < 0 and delta['Q_fixed_D'] < 0, 'tradeoff signs')
        balance = linear['signed_ridge_balance']
        require(abs(delta['data_loss'] - dec(balance['data_change_S2_minus_S1c'])) < Decimal('1e-95'), 'balance data binding')
        residual = (-dec(balance['regularized_improvement_from_compensated']) + dec(balance['ridge_tradeoff']) + dec(balance['effective_native_solver_row_gap']) - delta['data_loss'])
        require(abs(residual) < Decimal('1e-95'), 'signed balance closes')
        p = t['prediction_prox']; direction = p['native_ridge_direction']
        l0 = dec(p['data_loss_incumbent']); slope = dec(direction['derivative_at_zero']); curvature = dec(direction['second_derivative'])
        require(slope > 0 and curvature > 0 and dec(direction['best_alpha_on_0_1']) == 0, 'no positive descent along this direction')
        require(abs(-slope/curvature - dec(direction['unconstrained_alpha'])) < Decimal('1e-15'), 'stationary alpha')
        # Rounded direction scalars and the high-precision row table are separate records.
        require(abs(l0-dec(a['data_loss'])) < Decimal('1e-16'), 'direction starts at compensated incumbent')
        require(abs(l0+slope+curvature/2-dec(b['data_loss'])) < Decimal('1e-15'), 'rounded curve endpoint agrees within declared tolerance')
        j0,j2,j2q = (dec(states[s]['native_J']) for s in ('S0','S2','S2q'))
        require(abs(j2/j0-dec(episode['S2_to_S0_ratio'])) < Decimal('1e-12'), 'native ratio binding')
        require(abs(j2q-j2-dec(episode['S2q_minus_S2_native_J'])) < Decimal('1e-18'), 'native precision contrast')
        short = payload['observer']['short_main50']
        require(dec(short['base_change_J']) < 0, 'main50 counterexample stays')
        cov_start,cov_end = dec(cov['data_loss_incumbent']),dec(cov['candidate_data_loss_saved_matrix_only'])
        cov_percent = 100*(cov_start-cov_end)/cov_start
        require(abs(cov_percent-dec(cov['percent_of_total_data_loss_removed'])) < Decimal('1e-11'), 'COV denominator')
        result = {
            'schema':'proton-scientific-finale-v1',
            'source':{'file':SOURCE,'sha256':SOURCE_SHA,'ref':SOURCE_REF},
            'evidence':'DERIVED_SAVED_ARITHMETIC',
            'normalization':60,'system':'ROW_EXACT_FIXED_D',
            'rows':[{ 'state':r['state'], 'ell':str(r['data_loss']), 'R':str(r['ridge_penalty']), 'Q':str(r['Q_fixed_D']) } for r in (a,b)],
            'delta':{'ell':str(delta['data_loss']),'R':str(delta['ridge_penalty']),'Q':str(delta['Q_fixed_D'])},
            'q_drop_percent':float(-100*delta['Q_fixed_D']/dec(a['Q_fixed_D'])),
            'axis_max':0.004,
            'native':{'S0':float(j0),'S2':float(j2),'S2q':float(j2q),'S3':None,'ratio':float(j2/j0),'S2q_minus_S2':float(j2q-j2),'target':'ROW_EXACT_FIXED_D'},
            'direction':{'l0':float(l0),'a':float(slope),'b':float(curvature),'alpha_min':0,'alpha_max':1,'minimum_on_domain':0,'endpoint_tolerance':1e-15,'kind':'DERIVED_QUADRATIC_NOT_PHYSICAL_TRAJECTORY','origin':'S1c compensated incumbent','scope':'Fixed A, y and radial block; direction toward native ridge coefficients. Not damping of the full S0-to-S4 operation.'},
            'counterexample':{'iteration':short['main_iteration'],'delta_J':short['base_change_J'],'evidence':'REPORTED_SAVED_SUMMARY_NOT_NEW_REPLAY'},
            'cov':{'percent':float(cov_percent),'origin':'S1c','metric':'saved-row data loss','native_evaluated':False,'superiority':False},
            'metric_transport':{'formula':'D_prime = T D T_transpose','one_chosen_metric':True,'global_gauge_invariance':False},
            'limits':{'private_recovery_available':False,'T2_executed':False,'causes_prior_seed_results':False,'regularization_always_harmful':False,'T1':'SYNTHETIC_ONLY','visible':VISIBLE_LIMIT},
            'source_fields':['$.theory.linear_system.row_loss_table','$.theory.linear_system.signed_ridge_balance','$.theory.main4500.states','$.theory.prediction_prox.native_ridge_direction','$.theory.prediction_prox.data_loss_incumbent','$.theory.COV','$.observer.short_main50','$.scope','$.t1.statuses']
        }
    return result


FILES = ('site/scientific_finale.py','site/scientific_finale.css','site/scientific_finale.mjs',
         'tools/build_scientific_finale.py','tests/test_scientific_finale.py',
         'tools/site/browser_finale_test.mjs','docs/SCIENTIFIC_FINALE.md')

def verify_manifest(root: Path = ROOT) -> None:
    import csv
    with (root/'provenance/SCIENTIFIC_FINALE_MANIFEST.tsv').open(encoding='utf-8',newline='') as stream:
        rows=list(csv.DictReader(stream,delimiter='\t'))
    require(len(rows)==len(FILES) and {r['path'] for r in rows}==set(FILES), 'finale asset scope')
    from publication_metadata import load_metadata_overrides, effective_record
    overrides=load_metadata_overrides(root)
    for r in rows:
        p=root/r['path'];require(p.is_file() and not p.is_symlink(), 'missing finale asset')
        b=p.read_bytes()
        current=effective_record(r['path'], {'repository_sha256':r['sha256'],'size_bytes':r['bytes']}, overrides)
        require(hashlib.sha256(b).hexdigest()==current['repository_sha256'] and len(b)==int(current['size_bytes']), 'finale asset identity: '+r['path'])


def load(root: Path = ROOT) -> dict:
    verify_manifest(root)
    b = (root/SOURCE).read_bytes()
    require(hashlib.sha256(b).hexdigest() == SOURCE_SHA, 'unreviewed source bytes')
    return derive(json.loads(b))


def write(out: Path, data: dict) -> None:
    (out/'data').mkdir(parents=True,exist_ok=True)
    (out/'data/finale.json').write_text(json.dumps(data,ensure_ascii=True,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path);args=ap.parse_args()
    d=load()
    if args.out: write(args.out,d)
    print(json.dumps({'status':'PASS_FINALE_SAVED_ARITHMETIC','source_sha256':SOURCE_SHA,'q_drop_percent':d['q_drop_percent'],'new_scientific_calls':0,'private_sources_opened':0}))

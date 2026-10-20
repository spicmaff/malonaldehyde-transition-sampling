#!/usr/bin/env python3
"""Validate and copy the reviewed optimization chapter's public aggregate subset.

Standard library only. Reads public saved files and aggregates; never imports a
private-source reader or executes training, inference, or a numerical solver.
Restricted source hashes identify an audited input, not a public reproduction.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path, PurePosixPath

from verify_optimizer_budget import parse_log
from verify_pbe14_offpath import parse_cfg, rmse, maxdiff, COORD_TOL, PAIR_TOL

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'data/optimization_story/v001'
BUNDLE_FILES = ('OPTIMIZATION_STORY.json', 'CLAIM_DATA_MAP.tsv', 'PROVENANCE.json',
                'README.md', 'PUBLICATION_ALLOWLIST.json')
# This edition contains only the G1-reviewed public derivative. Updating a local
# manifest is not authorization to publish different provenance or claim tiers.
REVIEWED_SHA256 = {
    'OPTIMIZATION_STORY.json': '91ba4b11b43a6966b2e1cc4ef43eef765bedd58a7de1f0975ae14b2550185131',
    'CLAIM_DATA_MAP.tsv': '4456e169d82a0c12079e5e21f4a2d4c0dfd6d5576ca7078e076eb94b729719f9',
    'PROVENANCE.json': 'fa5d7b72d0bdd9a94536c0e3cd4c6e5cdd20cebf53d5120b68d999db066c29bc',
    'README.md': '46ffbe8b8610c82d1845cf570fcaf91fa13842c6e8470419c9e0d3e9bd23e64f',
    'PUBLICATION_ALLOWLIST.json': 'ccc5b4b8bf5c8d0b04b228d083cd5e9f12da8180bbf9c5a4385bcd604c33ec2c',
}
SOURCE_BASE = 'f5f4784d7cc186ae9cfcacbd97117b5dabbffb30'
REPO = 'https://github.com/spicmaff/malonaldehyde-transition-sampling'
EVIDENCE_CLASSES = {'PUBLIC_RECOMPUTABLE', 'MEASURED_SAVED_PHYSICAL',
    'DERIVED_SAVED_ARITHMETIC', 'THEOREM_UNDER_ASSUMPTIONS',
    'SYNTHETIC_ENGINEERING_PASS', 'FUTURE_UNTESTED', 'KNOWN_LIMITATION',
    'SOURCE_CODE_VERIFIED'}
CLAIM_FIELDS = ('claim_id', 'section', 'claim', 'source_id', 'source_file',
    'source_sha256', 'source_field', 'data_field', 'definition_unit', 'status',
    'verification_status', 'source_access', 'public_source_url',
    'additional_source_ids', 'additional_source_fields', 'visualization', 'reviewer_check')
VISIBLE_LIMIT = ('Engineered and checked on synthetic runs. Not yet demonstrated '
                 'to be a better real-data optimizer.')
SHA = re.compile(r'[0-9a-f]{64}')
LOG_PATH = re.compile(r'data/studies/optimization_budget_v001/logs/seed_0[0-4]_(basin|targeted)_(2000|8000)\.txt')
PUBLIC_SPECIAL = {
    'theory.public_template': 'data/frozen_models_v028/locked_untrained_l12_v028.mtp',
    'OBS_PUBLIC_PBE14_REFERENCES': 'data/studies/pbe14_mtp20_v001/references/PBE14_EXACT.cfg',
    'OBS_PUBLIC_H_PREDICTIONS': 'data/studies/pbe14_mtp20_v001/predictions/seed_03_basin_8000.cfg',
}
FORBIDDEN_KEYS = {'D0_binary64', 'fixed_D_binary64', 'optimum_coefficients',
    'singular_values', 'weighted_design', 'weighted_targets', 'regression_coeffs',
    'linear_mults', 'gradient', 'energies', 'forces', 'checkpoint_payload',
    'state_bytes', 'model_coefficients', 'private_matrix', 'private_checkpoint_blob'}
FORBIDDEN_TEXT = ('/workspace/', '/mnt/', '/home/', '/root/', 'C:\\',
                  'BEGIN PRIVATE KEY', 'BEGIN RSA PRIVATE KEY')


def require(ok, message):
    """Validation must work unchanged with Python assertions disabled."""
    if not ok:
        raise ValueError('Optimization story: ' + message)


def strict_json(text):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'duplicate JSON key: ' + key)
            out[key] = value
        return out
    def constant(value):
        raise ValueError('Optimization story: nonfinite JSON constant ' + value)
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Optimization story: invalid JSON') from exc


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def keys(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected), label + ' schema fields')


def number(value, label, nonnegative=False):
    require(type(value) in (int, float) and math.isfinite(value), label + ' finite number')
    require(not nonnegative or value >= 0, label + ' nonnegative number')
    return value


def dec(value):
    require(not isinstance(value, bool), 'boolean used as a numeric value')
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Optimization story: invalid decimal') from exc
    require(d.is_finite(), 'nonfinite decimal')
    return d


def close(actual, expected, label, tol='5e-13'):
    a, b = dec(actual), dec(expected)
    require(abs(a - b) <= Decimal(tol) * max(Decimal(1), abs(a), abs(b)), label)


def safe_tree(value, path='payload'):
    if isinstance(value, dict):
        require(not (set(value) & FORBIDDEN_KEYS), 'private array/blob key at ' + path)
        for key, child in value.items():
            require(isinstance(key, str), 'non-string key')
            safe_tree(child, path + '/' + key)
    elif isinstance(value, list):
        require(len(value) <= 100, 'unexpected large array at ' + path)
        if value and all(type(v) in (int, float) for v in value):
            require(len(value) <= 4, 'raw numeric vector at ' + path)
        for i, child in enumerate(value):
            safe_tree(child, path + '/' + str(i))
    elif isinstance(value, float):
        require(math.isfinite(value), 'nonfinite number at ' + path)
    elif isinstance(value, str):
        require(not any(t in value for t in FORBIDDEN_TEXT), 'private path/token at ' + path)
        require(value not in ('NaN', 'Infinity', '-Infinity', 'nan', 'inf', '-inf'), 'nonfinite numeric string')
    else:
        require(value is None or type(value) in (int, bool), 'unsupported value at ' + path)


def source_registry(payload, repository_root):
    sources = payload['sources']
    require(isinstance(sources, list) and len(sources) == 71, '71 source records')
    by_id = {}
    root = Path(repository_root).resolve()
    public_count = 0
    for row in sources:
        keys(row, ('access', 'bytes', 'file', 'id', 'locator_type', 'scope',
                   'sha256', 'source_access', 'url'), 'source')
        require(isinstance(row['id'], str) and row['id'] not in by_id, 'unique source id')
        require(type(row['bytes']) is int and row['bytes'] > 0, 'source byte count')
        require(SHA.fullmatch(row['sha256']) is not None, 'source SHA format')
        rel = PurePosixPath(row['file'])
        require(not rel.is_absolute() and '..' not in rel.parts and '\\' not in row['file'], 'source locator')
        if row['source_access'] == 'PUBLIC':
            public_count += 1
            allowed = PUBLIC_SPECIAL.get(row['id']) == row['file']
            if LOG_PATH.fullmatch(row['file']):
                allowed = row['id'] == 'OBS_LOG_' + rel.stem
            require(allowed, 'unapproved public source path/id')
            require(row['locator_type'] == 'repository_path', 'public locator type')
            require(row['url'] == f'{REPO}/blob/{SOURCE_BASE}/{row["file"]}', 'public source URL')
            path = root / row['file']
            require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root), 'public source file')
            require(path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], 'public source checksum: ' + row['file'])
        else:
            require(row['source_access'] == 'RESTRICTED' and row['url'] is None,
                    'restricted source must not have a public raw URL')
            require(row['locator_type'] == 'restricted_audit_relative_locator', 'restricted locator type')
            # Deliberately do not resolve or open this locator.
        by_id[row['id']] = row
    require(public_count == 23, '23 public source records')
    return by_id


def validate_theory(theory):
    keys(theory, ('COV', 'architecture', 'linear_system', 'main4500',
                  'prediction_prox', 'proof_scope', 'transport'), 'theory')
    a = theory['architecture']
    require((a['atoms'], a['cartesian_coordinates'], a['generic_internal_coordinates']) == (9, 27, 21), 'geometry dimensions')
    require([r['count'] for r in a['parameter_blocks']] == [216, 29, 3] and
            sum(r['count'] for r in a['parameter_blocks']) == a['nominal_parameters'] == 248, 'architecture blocks')
    require(a['linear_parameters'] == 32 and a['physical_rank_240_asserted'] is False, 'linear dimension / physical rank caveat')
    require(a['regular_radial_flag_dimension'] == 216 - 6 == 210 and a['known_quotient_dimension'] == 248 - 6 - 2 == 240, 'conditional quotient counts')
    o = a['objective']
    require((o['native_symbol'], o['row_symbol'], o['inner_symbol']) == ('J', 'ell', 'Q_D'), 'separate objective definitions')
    require((o['normalization_configurations'], o['energy_rows'], o['force_rows'], o['weighted_rows']) == (60, 60, 1620, 1680), 'weighted row normalization')
    require('not force RMSE' in o['unit'] and '10^−9 P(Theta)' in o['native_formula'] and 'k<l' in o['radial_penalty_formula'], 'native objective/penalty convention')
    m = theory['main4500']
    require(m['boundary'] == {'session': 2, 'cap': 8000, 'iteration': 4500, 'refit': 244}, 'main4500 boundary')
    states = m['states']
    require([r['id'] for r in states] == ['S0', 'S1', 'S1c', 'S2', 'S2q', 'S3', 'S4'], 'state sequence')
    by = {r['id']: r for r in states}
    require(m['native_order'] == ['S0', 'S1', 'S2', 'S3', 'S4'] and
            m['diagnostic_branches'] == [{'from': 'S1', 'to': 'S1c'}, {'from': 'S2', 'to': 'S2q'}], 'diagnostic branches are not native transitions')
    for role, row in by.items():
        require(row['native_trajectory'] is (role not in ('S1c', 'S2q')), 'state trajectory classification')
        require(row['separate_live_objective_parity'] is (role in ('S0', 'S2', 'S4')), 'live versus detached objective')
        if role == 'S3':
            require(row['status'] == 'NOT_MEASURED' and all(row[k] is None for k in ('native_J', 'physical_data_loss', 'radial_penalty')), 'S3 objective must remain unmeasured')
        else:
            expected = 'NEW_DERIVED_DETACHED_EVALUATION' if role in ('S1c', 'S2q') else 'LIVE_STATE_DETACHED_EVALUATION'
            require(row['status'] == expected, 'state evidence classification')
            for k in ('native_J', 'physical_data_loss', 'radial_penalty'):
                number(row[k], role + ' ' + k, True)
            close(row['native_J'], dec(row['physical_data_loss']) + dec(row['radial_penalty']), role + ' objective components')
    require('log10' in m['plot_scale'] and 'weighted native J' in m['unit'], 'fixed labeled native objective axis')
    require(m['original_archive_restored'] is False and m['evidence_mode'] == 'NEW_DIAGNOSTIC_NOT_ORIGINAL_M01', 'recovery provenance')
    for name, end, start in [('S0_to_S2', 'S2', 'S0'), ('S2_to_S4', 'S4', 'S2'), ('S0_to_S4', 'S4', 'S0')]:
        close(m['native_telescope'][name], dec(by[end]['native_J']) - dec(by[start]['native_J']), 'native telescope ' + name)
    close(m['S2_to_S0_ratio'], dec(by['S2']['native_J']) / dec(by['S0']['native_J']), 'refit ratio')
    close(m['S2q_minus_S2_native_J'], dec(by['S2q']['native_J']) - dec(by['S2']['native_J']), 'new S2q contrast', '1e-16')
    require(by['S1']['native_J'] > by['S2']['native_J'] > by['S4']['native_J'] > by['S0']['native_J'], 'one-boundary ordering')
    require(abs(by['S2q']['native_J'] - by['S2']['native_J']) < 1e-8 * by['S2']['native_J'], 'stable row solve barely changes physical J')
    tr = theory['transport']
    require((tr['exact_identities'], tr['formal_monomials'], tr['nonzero_transport_entries'], tr['group_law_entries_verified']) == (29, 134, 43, 841), 'finite graph identity counts')
    require(tr['physical_EF_all_components_pass'] is True and tr['physical_EF']['full_J_gauge_equality_required'] is False, 'E/F transport is not full-J gauge equality')
    ls = theory['linear_system']
    require([r['id'] for r in ls['systems'] if r['new_S2q_physical_target']] == ['ROW_EXACT_FIXED_D'], 'new S2q fixed system')
    require({r['id'] for r in ls['systems']} == {'ROW_EXACT_FIXED_D', 'CAPTURE_G_PLUS_EXACT_D', 'ACTUAL_K_CAPTURE'}, 'three numerical systems')
    require(ls['precision_digits'] == [85, 110] and ls['interval_certificate'] is False and ls['physical_model_accuracy_inferred'] is False, 'high precision scope')
    require(len(ls['verification']) == 3, 'three solve checks')
    for row in ls['verification']:
        require(0 <= dec(row['cross_precision_relative_solution']) < Decimal('1e-60') and
                0 <= dec(row['LU_Cholesky_relative_solution']) < Decimal('1e-70') and
                0 <= dec(row['normalized_backward_error']) < Decimal('1e-90'), 'saved high precision bounds')
    with localcontext() as context:
        context.prec = 140
        balance = ls['signed_ridge_balance']
        require(balance['normalization'] == 60 and balance['system'] == 'ROW_EXACT_FIXED_D' and balance['physical_causal_percentages'] is False, 'fixed-D signed balance scope')
        residual = (-dec(balance['regularized_improvement_from_compensated']) + dec(balance['ridge_tradeoff']) +
                    dec(balance['effective_native_solver_row_gap']) - dec(balance['data_change_S2_minus_S1c']))
        # The published 100+-digit scalars are rounded; this is a scalar readback,
        # not an interval certificate or repetition of the private matrix solve.
        require(abs(residual) < Decimal('1e-98') and abs(dec(balance['closure'])) < Decimal('1e-98'), 'signed fixed-D balance')
        rows = {r['state']: r for r in ls['row_loss_table']}
        require(set(rows) == {'S1', 'S1c', 'S2', 'S2q'}, 'row-loss table states')
        for row in rows.values():
            require(abs(dec(row['Q_fixed_D']) - dec(row['data_loss']) - dec(row['ridge_penalty'])) < Decimal('1e-98'), 'Q = data + fixed-D ridge, divided by 60')
        require(abs(dec(rows['S2']['data_loss']) - dec(rows['S1c']['data_loss']) - dec(balance['data_change_S2_minus_S1c'])) < Decimal('1e-98'), 'ridge balance endpoint difference')
    for field in ('COV', 'prediction_prox'):
        candidate = theory[field]
        require(candidate['candidate_coefficients_exported'] is False and candidate['candidate_native_EF_or_gradient'] == 'NOT_EVALUATED' and candidate['off_training_accuracy'] == 'NOT_QUALIFIED', 'saved-row candidate physical scope')
    cov = theory['COV']
    before, after = dec(cov['data_loss_incumbent']), dec(cov['candidate_data_loss_saved_matrix_only'])
    require(0 < after < before and cov['full_unprojected_stationarity_required'] is False, 'constrained COV descent')
    close(cov['data_loss_decrease'], before - after, 'COV data decrease')
    close(cov['percent_of_total_data_loss_removed'], 100 * (before - after) / before, 'COV total-loss percentage')
    require(cov['regularized_stack_shape'] == [1712, 30] and 'delta=T_g z' in cov['feasible_space'] and 'M=B^T B=T D0 T^T' in cov['penalty_orientation'], 'COV projected space and metric orientation')
    require('not native captured D0' in cov['D0_origin'] and '/60' in cov['descent_identity'], 'COV metric origin and normalization')
    require(0 <= cov['projected_stationarity_normalized'] < 1e-12 and
            0 <= cov['descent_identity_absolute_residual'] < 1e-12 and
            0 <= cov['QR_SVD_prediction_maxabs'] < 1e-12, 'saved COV numerical checks')
    pred = theory['prediction_prox']
    pb, pa, pm = map(dec, (pred['data_loss_incumbent'], pred['data_loss_candidate_saved_matrix_only'], pred['data_loss_reduced_row_subspace_minimum_estimate']))
    require(pm < pa < pb and pred['lambda'] == 1 and pred['rank'] == 30, 'prediction proximal scope')
    close(pred['fraction_of_available_gap_removed'], (pb - pa) / (pb - pm), 'prediction available-gap denominator')
    close(pred['percent_of_total_data_loss_removed'], 100 * (pb - pa) / pb, 'prediction total-loss denominator')
    direction = pred['native_ridge_direction']
    require(direction['derivative_at_zero'] > 0 and direction['second_derivative'] > 0 and direction['unconstrained_alpha'] < 0 and direction['best_alpha_on_0_1'] == 0, 'fixed-row native ridge direction')


def validate_t1(t1):
    keys(t1, ('checkpoint_example', 'qualification', 'scope', 'statuses'), 'T1')
    q, status = t1['qualification'], t1['statuses']
    require(q['status'] == status['T1'] == 'T1_PASS_ENGINEERING_SYNTHETIC_ONLY', 'T1 synthetic-only status')
    require(q['evidence_status'] == 'SYNTHETIC_ENGINEERING_PASS' and status['visible_limit'] == VISIBLE_LIMIT, 'visible T1 scope')
    require(status['T2'] == 'T2_NOT_AUTHORIZED_NOT_EXECUTED' and status['T2_authorized'] is False and status['T2_executed'] is False, 'T2 unexecuted and unauthorized')
    require(status['PBE14_role'] == 'development' and status['independent_physical_validation'] == 'VALIDATION_NOT_AVAILABLE_YET', 'PBE14 not a blind validation')
    require(q['fixture']['configurations'] == 60 and q['fixture']['atoms_per_configuration'] == 9 and q['fixture']['coordinates_and_labels'] == 'synthetic', 'synthetic fixture')
    require(q['inherited_assertions'] + q['additional_assertions'] == q['native_core_assertions'] == 94, '94 unique assertions')
    p = q['pipeline']
    require(p['arms'] == ['CONTROL_A', 'COV_A'] and p['pretraining_accepted'] == 75 and p['main_accepted'] == 150 and p['accepted_per_arm'] == 225 and p['candidate_prefix_equal'] == 125, 'T1 lifecycle counts')
    require([r['iteration'] for r in p['cov_boundaries']] == [50, 100], 'synthetic candidate boundaries')
    for row in p['cov_boundaries']:
        require(row['decision'] == 'ACCEPT' and 0 < row['J_after'] < row['J_before'] and row['metric'] == 'native_synthetic_J' and row['unit'] == 'weighted_native_objective', 'synthetic acceptance quantities')
    parity = q['baseline_parity']
    require(parity['accepted_states'] == 225 and parity['objective_gradient_parameters_bitwise'] is True and parity['saved_BFGS_snapshots_bitwise'] is True, 'T1 control parity')
    reload = q['reload']
    require(reload['processes'] == 12 and reload['scope'] == 'RELOAD_FOR_EVALUATION_ONLY' and reload['full_BFGS_resume_qualified'] is False, 'reload evaluation-only scope')
    require(reload['objective_max_abs_error'] == reload['gradient_max_abs_error'] == 0 and 'not force RMSE' in reload['weighted_EF_definition'], 'reload units')
    fault, san = q['faults'], q['sanitizers']
    require((fault['unique_file_error_points'], fault['unique_signal_crash_cases']) == (21, 9) and fault['power_loss_tested'] is False and fault['hardware_replica_independence'] is False, 'file/process fault scope')
    require(all(san[k] is True for k in ('ASan', 'UBSan', 'LeakSanitizer')) and san['diagnostic_count'] == 0 and san['external_BLAS_LAPACK_Fortran_instrumented'] is False, 'sanitizer scope')
    example = t1['checkpoint_example']
    require(example['metric'] == 'native_synthetic_J' and example['unit'] == 'weighted_native_objective' and example['same_policy_for_both_arms'] is True, 'synthetic checkpoint metric')
    require([r['arm'] for r in example['rows']] == ['CONTROL_A', 'COV_A'], 'checkpoint arms')
    for row in example['rows']:
        require(row['TERMINAL_J'] < row['END_MAIN_J'] and row['BEST_role'] == 'TERMINAL' and row['BEST_J'] == row['TERMINAL_J'] and row['BEST_sequence'] == row['captures'] == 228, 'opposite synthetic terminal example')
    scope = t1['scope']
    require(scope['optimizer_superiority_proven'] is False, 'no real optimizer superiority')
    require(all(scope['historical_t1'][k] == 0 for k in ('new_real_train60_fits', 'new_real_replays', 'new_DFT', 'new_MD', 'Blind12_read')), 'historical T1 real-call scope')
    r = scope['separate_missing_input_recovery']
    require((r['training_processes'], r['detached_physical_replay_processes'], r['T2_runs']) == (1, 6, 0), 'separate necessary recovery')
    future = status['future_design']
    require(future['status'] == 'FUTURE_UNTESTED' and future['proposed_training_count'] == len(future['methods']) * future['fixed_Train60_allocations'] * future['fixed_seeds'] == 20, 'future design is not an executed result')


def validate_observer(observer, sources, repository_root):
    keys(observer, ('end_terminal', 'long_boundaries', 'recovery', 'short_main50'), 'observer')
    root = Path(repository_root)
    long = observer['long_boundaries']
    require(len(long['rows']) == long['long_logs'] == 10 and long['boundary_period'] == 50, 'long log count')
    expected_pairs = {(seed, branch) for seed in range(5) for branch in ('basin', 'targeted')}
    require({(row['seed'], row['branch']) for row in long['rows']} == expected_pairs,
            'ten distinct optimizer seed/allocation pairs')
    total, prefix_total = 0, 0
    for row in long['rows']:
        for key, cap in (('source_id', 8000), ('short_source_id', 2000)):
            expected_id = f'OBS_LOG_seed_{row["seed"]:02d}_{row["branch"]}_{cap}'
            require(row[key] == expected_id and expected_id in sources and
                    sources[expected_id]['source_access'] == 'PUBLIC' and
                    LOG_PATH.fullmatch(sources[expected_id]['file']) is not None,
                    'public log source binding before open')
        l = parse_log((root / sources[row['source_id']]['file']).read_text())
        s = parse_log((root / sources[row['short_source_id']]['file']).read_text())
        require(l['cap'] == 8000 and s['cap'] == 2000 and l['pretraining'] == s['pretraining'] and l['main'][:2000] == s['main'], 'exact paired printed prefixes')
        # Compare the saved decimal strings, independently of the legacy float count.
        upward = [int(i) for (_, a), (i, b) in zip(l['main'], l['main'][1:]) if dec(b) > dec(a)]
        short_upward = [int(i) for (_, a), (i, b) in zip(s['main'], s['main'][1:]) if dec(b) > dec(a)]
        require(len(upward) == row['positive_printed_increases'] and len(short_upward) == row['duplicate_short_prefix_increases'], 'printed jump recount')
        require(all(i % 50 == 0 for i in upward) and row['short_prefix_exact'] is True and row['all_increases_at_multiples_of_50'] is True, 'boundary phase and prefix scope')
        total += len(upward); prefix_total += len(short_upward)
    require(total == long['positive_printed_increases'] == 1163 and prefix_total == long['duplicate_short_prefix_increases'] == 60, '1163 long increases; duplicated 60 excluded')
    require(long['HABC']['independent_scientific_replicates'] == 1, 'H/A/B/C are not independent replicates')
    short = observer['short_main50']; by = {r['state']: r['native_J'] for r in short['states']}
    require(set(by) == {'S0', 'S2', 'S4'} and by['S0'] > by['S2'] > by['S4'], 'opposite short refit example')
    for field, end, start in [('base_change_J', 'S2', 'S0'), ('search_change_J', 'S4', 'S2'), ('logged_change_J', 'S4', 'S0')]:
        close(short[field], dec(by[end]) - dec(by[start]), 'short boundary ' + field)
    end = observer['end_terminal']; require(end['cost_scope']['cost_matched'] is False and end['cost_scope']['paired_seed_and_data_cases'] == 1, 'one cost-unmatched pair')
    require(end['historical_status']['XI_T_P1_runtime_capture'] == 'FAIL_STOP_NO_RETRY' and end['historical_status']['XI_training_event_journal'] == 'MISSING' and end['historical_status']['new_recovery_repairs_historical_XI_chronology'] is False, 'historical negative evidence preserved')
    native = {r['state']: r for r in end['native_rows']}; require(set(native) == {'END_MAIN', 'TERMINAL'}, 'native pair roles')
    for row in native.values():
        close(row['native_J'], sum((dec(row[k]) for k in ('energy_loss', 'force_loss', 'radial_penalty')), Decimal(0)), 'XI native components')
    close(end['terminal_over_end_main'], dec(native['TERMINAL']['native_J']) / dec(native['END_MAIN']['native_J']), 'terminal/end ratio')
    close(end['terminal_minus_end_main_J'], dec(native['TERMINAL']['native_J']) - dec(native['END_MAIN']['native_J']), 'terminal/end difference')
    pbe = end['pbe14']
    require(pbe['unit'] == 'eV/angstrom' and pbe['role'] == 'PREVIOUSLY_USED_DEVELOPMENT_NOT_INDEPENDENT_HOLDOUT', 'PBE14 unit and development role')
    require(pbe['evidence_by_model']['TERMINAL'] == 'SAVED_14_CASE_ERROR_SCORES_REAGGREGATED_RAW_PREDICTIONS_MISSING', 'terminal raw-vector limitation')
    cases = pbe['case_scores']; blocks = pbe['block_rows']; regions = pbe['regional_rows']
    require(len(cases) == pbe['configurations'] == 14 and len(blocks) == pbe['blocks'] == 8 and len(regions) == 2, 'PBE14 table cardinalities')
    require(len({r['candidate_id'] for r in cases}) == 14 and {r['region'] for r in cases} == {'BASIN_LEFT', 'TRANSITION_CENTER'}, 'PBE14 identities')
    for block in blocks:
        selected = [r for r in cases if (r['block'], r['region']) == (block['block'], block['region'])]
        require(len(selected) == block['configurations'] == (1 if block['block'].endswith('H_out_of_plane') else 2), 'physical block membership')
        for model in ('END_MAIN', 'TERMINAL', 'HISTORICAL_H'):
            close(block[model], sum((dec(r[model]) for r in selected), Decimal(0)) / len(selected), 'case to block arithmetic')
    for region in regions:
        selected = [r for r in blocks if r['region'] == region['region']]
        require(len(selected) == 4, 'four equal physical blocks')
        for model in ('END_MAIN', 'TERMINAL', 'HISTORICAL_H'):
            close(region[model], sum((dec(r[model]) for r in selected), Decimal(0)) / 4, 'equal-block region arithmetic')
    require(sum(r['END_MAIN'] < r['TERMINAL'] for r in cases) == pbe['end_better_cases'] == 12 and
            sum(r['END_MAIN'] < r['TERMINAL'] for r in blocks) == pbe['end_better_blocks'] == 8, '12/14 cases and 8/8 blocks')
    require(sorted(r['candidate_id'] for r in cases if r['END_MAIN'] > r['TERMINAL']) == pbe['end_worse_cases'] == ['L01m', 'L03m'], 'retain two opposite case results')
    refs = parse_cfg((root / sources['OBS_PUBLIC_PBE14_REFERENCES']['file']).read_text())
    preds = parse_cfg((root / sources['OBS_PUBLIC_H_PREDICTIONS']['file']).read_text())
    require(len(refs) == len(preds) == 14, 'public H prediction cardinality')
    scoremap = {r['candidate_id']: r for r in cases}
    for ref, pred in zip(refs, preds):
        cid = ref['features']['candidate_id']
        require(pred['features']['candidate_id'] == cid and cid in scoremap, 'public H geometry identity')
        coordinate_error = maxdiff(ref['xyz'], pred['xyz'])
        pair_error = max(abs(math.dist(ref['xyz'][a], ref['xyz'][b]) -
                             math.dist(pred['xyz'][a], pred['xyz'][b]))
                         for a in range(9) for b in range(a))
        require(coordinate_error <= COORD_TOL and pair_error <= PAIR_TOL,
                'public H prediction serialization geometry guard')
        close(scoremap[cid]['HISTORICAL_H'], rmse(ref['forces'], pred['forces']), 'public H force-component reconstruction')
    rec = observer['recovery']
    require((rec['scientific_processes'], rec['real_diagnostic_training_runs'], rec['detached_physical_replays']) == (7, 1, 6), 'necessary recovery counts')
    require(rec['training_pretraining_steps'] + rec['training_main_steps'] == rec['training_printed_rows'] == 8075 and rec['historical_live_result_byte_matches'] == 4, 'recovered training and live result scope')
    require(all(rec[k] == 0 for k in ('new_T2_runs', 'new_DFT_runs', 'new_MD_runs', 'new_protected_holdout_model_evaluations', 'new_COV_candidate_physical_evaluations', 'retries')), 'recovery execution boundary')
    require(rec['new_counterfactuals_claim_original_bytes'] is False and rec['original_M01_archive_restored'] is False and rec['original_historical_raw_journal_restored'] is False, 'original archive remains absent')
    return {'public_training_logs': 20, 'long_printed_increases': total,
            'duplicate_short_prefix_increases': prefix_total, 'public_H_force_cases': 14,
            'paired_case_scores_reaggregated': 14, 'paired_blocks_reaggregated': 8,
            'paired_regions_reaggregated': 2}


def validate_payload(payload, repository_root=ROOT):
    keys(payload, ('edition', 'evidence_taxonomy', 'limitations', 'observer', 'schema',
                   'scope', 'sources', 'subtitle', 't1', 'theory', 'title'), 'payload')
    require(payload['schema'] == 'proton-optimization-v1', 'payload schema version')
    require(set(payload['evidence_taxonomy']) == EVIDENCE_CLASSES, 'evidence taxonomy')
    safe_tree(payload)
    scope = payload['scope']
    require(all(scope[k] is False for k in ('T2_authorized', 'T2_executed', 'COV_real_data_optimizer_superiority_proven', 'COV_candidate_physical_evaluated_in_recovery')), 'unexecuted scientific claims')
    require(scope['PBE14_role'] == 'development' and scope['historical_negative_receipts_preserved'] is True and scope['new_scientific_calls_by_site_build'] == 0, 'site and development scope')
    registry = source_registry(payload, repository_root)
    validate_theory(payload['theory']); validate_t1(payload['t1'])
    counts = validate_observer(payload['observer'], registry, repository_root)
    # Cross-links must identify an audited record, not an invented source.
    def references(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k in ('source_id', 'aggregate_source_id'):
                    require(v in registry, 'unknown nested source id')
                elif k in ('source_ids',):
                    require(all(s in registry for s in v), 'unknown nested source ids')
                else:
                    references(v)
        elif isinstance(value, list):
            for v in value:
                references(v)
    for key in ('theory', 't1', 'observer'):
        references(payload[key])
    return {'status': 'PASS_OPTIMIZATION_PUBLIC_SUBSET', 'source_records': len(registry),
            'public_source_hashes': 23, 'restricted_sources_opened': 0,
            'new_scientific_calls': 0, 'native_models_executed': 0, **counts}


def read_bundle(source_dir=DEFAULT, repository_root=ROOT):
    directory = Path(source_dir)
    require(directory.is_dir() and not directory.is_symlink(), 'bundle directory')
    require({p.name for p in directory.iterdir()} == set(BUNDLE_FILES), 'only the five publication files are allowed')
    for name in BUNDLE_FILES:
        require((directory / name).is_file() and not (directory / name).is_symlink(), 'regular allowlisted file: ' + name)
    manifest = strict_json((directory / 'PUBLICATION_ALLOWLIST.json').read_text())
    keys(manifest, ('excluded', 'files', 'license_scope', 'schema', 'self', 'self_digest_rule'), 'allowlist')
    safe_tree(manifest)
    require(manifest['schema'] == 'proton-optimization-publication-allowlist-v1' and manifest['self'] == 'PUBLICATION_ALLOWLIST.json', 'allowlist schema')
    entries = manifest['files']
    require(len(entries) == 4 and {r['path'] for r in entries} == set(BUNDLE_FILES) - {'PUBLICATION_ALLOWLIST.json'}, 'exact publication allowlist')
    for row in entries:
        keys(row, ('bytes', 'path', 'sha256'), 'allowlist entry')
        require(row['path'] in BUNDLE_FILES and SHA.fullmatch(row['sha256']) is not None, 'safe allowlist path/checksum')
        p = directory / row['path']
        require(type(row['bytes']) is int and p.stat().st_size == row['bytes'] and digest(p) == row['sha256'], 'publication checksum: ' + row['path'])
    data = strict_json((directory / 'OPTIMIZATION_STORY.json').read_text())
    provenance = strict_json((directory / 'PROVENANCE.json').read_text())
    keys(provenance, ('canonical_payload', 'canonical_payload_sha256', 'claim_count',
                     'claim_map', 'contribution_sha256', 'extraction', 'permission_scope',
                     'public_baseline_commit', 'publication_mode', 'restricted_locator_note',
                     'review', 'schema', 'source_count', 'sources'), 'provenance')
    safe_tree(provenance)
    safe_tree((directory / 'README.md').read_text(), 'public README')
    require(provenance['schema'] == 'proton-optimization-provenance-v1' and provenance['canonical_payload'] == 'OPTIMIZATION_STORY.json' and provenance['claim_map'] == 'CLAIM_DATA_MAP.tsv', 'provenance schema')
    require(provenance['canonical_payload_sha256'] == digest(directory / 'OPTIMIZATION_STORY.json') and provenance['sources'] == data['sources'] and provenance['source_count'] == 71, 'provenance payload binding')
    require(provenance['public_baseline_commit'] == SOURCE_BASE, 'public baseline commit')
    with (directory / 'CLAIM_DATA_MAP.tsv').open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(tuple(reader.fieldnames or ()) == CLAIM_FIELDS, 'claim map columns')
        claims = list(reader)
    require(len(claims) == provenance['claim_count'] == 90 and len({r['claim_id'] for r in claims}) == 90, '90 unique claims')
    registry = {r['id']: r for r in data['sources']}
    for row in claims:
        require(None not in row and row['section'] in ('theory', 't1', 'observer') and row['status'] in EVIDENCE_CLASSES, 'claim schema / evidence class')
        require(all(row[k] for k in ('claim', 'source_id', 'source_field', 'definition_unit', 'verification_status', 'visualization', 'reviewer_check')), 'complete claim evidence')
        require(row['source_id'] in registry, 'claim source id')
        source = registry[row['source_id']]
        require((row['source_file'], row['source_sha256'], row['source_access'], row['public_source_url']) ==
                (source['file'], source['sha256'], source['source_access'], source['url'] or ''), 'claim source binding')
        require(all(s.strip() in registry for s in row['additional_source_ids'].split(';') if s.strip()), 'additional claim source id')
        safe_tree(row, 'claim')
    summary = validate_payload(data, repository_root)
    for name in BUNDLE_FILES:
        require(digest(directory / name) == REVIEWED_SHA256[name], 'reviewed v001 content changed: ' + name)
    summary.update({'claim_rows': len(claims), 'payload_sha256': digest(directory / 'OPTIMIZATION_STORY.json'),
                    'publication_files': len(BUNDLE_FILES)})
    return data, summary


def load_payload(source_dir=DEFAULT, repository_root=ROOT):
    return read_bundle(source_dir, repository_root)[0]


def verify(source_dir=DEFAULT, repository_root=ROOT):
    return read_bundle(source_dir, repository_root)[1]


def build(out, source_dir=DEFAULT):
    data, _ = read_bundle(source_dir)
    out = Path(out)
    require(not out.is_symlink(), 'output directory symlink')
    out = out.resolve()
    require(out != ROOT and not ROOT.is_relative_to(out), 'unsafe output root')
    require(not any(out.is_relative_to(ROOT / d) for d in ('site', 'tools', 'tests', 'data', 'docs', 'provenance', 'figures', '.github')), 'refuse source overwrite')
    for directory in (out, out / 'data', out / 'data/optimization'):
        require(not directory.is_symlink(), 'output directory symlink')
        directory.mkdir(parents=True, exist_ok=True)
    targets = [(Path(source_dir) / name, out / 'data/optimization' / name) for name in BUNDLE_FILES]
    targets += [(Path(source_dir) / 'OPTIMIZATION_STORY.json', out / 'data/optimization.json')]
    targets += [(ROOT / 'site' / name, out / name) for name in ('optimization.css', 'optimization.mjs')]
    for source, target in targets:
        require(source.is_file() and not source.is_symlink(), 'missing chapter asset: ' + source.name)
        require(not target.is_symlink() and target.resolve().is_relative_to(out), 'output file symlink')
    for source, target in targets:
        shutil.copyfile(source, target)
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='Validate the public bundle without writing a site.')
    parser.add_argument('--data', type=Path, default=DEFAULT)
    parser.add_argument('--out', type=Path, help='Copy chapter assets and data into this site output.')
    args = parser.parse_args()
    require(not (args.verify and args.out), 'choose --verify or --out')
    if args.out:
        build(args.out, args.data)
    print(json.dumps(verify(args.data), sort_keys=True, indent=2))

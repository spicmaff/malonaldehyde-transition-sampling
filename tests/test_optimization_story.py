"""Public-only scientific gates and adversarial publication-boundary tests.

No native model executable is available to this test module. Rechecksummed
mutations deliberately exercise semantic validation rather than only SHA checks.
"""
from __future__ import annotations
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_optimizer_story as story


class OptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = story.load_payload()

    def mutated(self, mutation):
        value = copy.deepcopy(self.data)
        mutation(value)
        return value

    def reject(self, mutation, pattern=None):
        with self.assertRaisesRegex(ValueError, pattern or 'Optimization story:'):
            story.validate_payload(self.mutated(mutation))

    def stage_bundle(self, directory, mutation=None):
        """Refresh payload, provenance and allowlist hashes for a semantic attack."""
        directory = Path(directory)
        for name in story.BUNDLE_FILES:
            (directory / name).write_bytes((story.DEFAULT / name).read_bytes())
        if mutation:
            value = self.mutated(mutation)
            (directory / 'OPTIMIZATION_STORY.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            provenance = json.loads((directory / 'PROVENANCE.json').read_text())
            provenance['canonical_payload_sha256'] = story.digest(directory / 'OPTIMIZATION_STORY.json')
            provenance['sources'] = value['sources']
            (directory / 'PROVENANCE.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
        manifest = json.loads((directory / 'PUBLICATION_ALLOWLIST.json').read_text())
        for row in manifest['files']:
            p = directory / row['path']
            row['bytes'] = p.stat().st_size
            row['sha256'] = story.digest(p)
        (directory / 'PUBLICATION_ALLOWLIST.json').write_text(json.dumps(manifest, indent=2) + '\n')
        return directory

    def test_public_reconstruction_counts(self):
        result = story.verify()
        self.assertEqual(result['status'], 'PASS_OPTIMIZATION_PUBLIC_SUBSET')
        self.assertEqual((result['source_records'], result['public_source_hashes'], result['claim_rows']), (71, 23, 90))
        self.assertEqual((result['public_training_logs'], result['long_printed_increases'], result['duplicate_short_prefix_increases']), (20, 1163, 60))
        self.assertEqual((result['public_H_force_cases'], result['paired_case_scores_reaggregated'], result['paired_blocks_reaggregated'], result['paired_regions_reaggregated']), (14, 14, 8, 2))
        self.assertEqual((result['restricted_sources_opened'], result['new_scientific_calls'], result['native_models_executed']), (0, 0, 0))

    def test_frozen_bundle_is_not_modified(self):
        before = {n: story.digest(story.DEFAULT / n) for n in story.BUNDLE_FILES}
        story.load_payload()
        self.assertEqual(before, {n: story.digest(story.DEFAULT / n) for n in story.BUNDLE_FILES})

    def test_rechecksummed_t2_execution_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = self.stage_bundle(temp, lambda d: d['scope'].__setitem__('T2_executed', True))
            with self.assertRaisesRegex(ValueError, 'unexecuted scientific claims'):
                story.load_payload(stage)

    def test_rechecksummed_blind_test_claim_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = self.stage_bundle(temp, lambda d: d['scope'].__setitem__('PBE14_role', 'independent_blind_test'))
            with self.assertRaisesRegex(ValueError, 'development scope'):
                story.load_payload(stage)

    def test_t1_cannot_authorize_t2_or_optimizer_superiority(self):
        self.reject(lambda d: d['t1']['statuses'].__setitem__('T2_authorized', True))
        self.reject(lambda d: d['t1']['scope'].__setitem__('optimizer_superiority_proven', True))
        self.reject(lambda d: d['scope'].__setitem__('COV_real_data_optimizer_superiority_proven', True))

    def test_private_file_cannot_be_added_to_updated_allowlist(self):
        with tempfile.TemporaryDirectory() as temp:
            p = self.stage_bundle(temp)
            secret = p / 'private_checkpoint.bin'
            secret.write_bytes(b'not a public artifact')
            m = json.loads((p / 'PUBLICATION_ALLOWLIST.json').read_text())
            m['files'].append({'path': secret.name, 'sha256': story.digest(secret), 'bytes': secret.stat().st_size})
            (p / 'PUBLICATION_ALLOWLIST.json').write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, 'only the five'):
                story.load_payload(p)

    def test_allowlist_traversal_is_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as temp:
            p = self.stage_bundle(temp)
            m = json.loads((p / 'PUBLICATION_ALLOWLIST.json').read_text())
            m['files'][0]['path'] = '../private_checkpoint.bin'
            (p / 'PUBLICATION_ALLOWLIST.json').write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, 'exact publication allowlist'):
                story.load_payload(p)

    def test_allowlist_file_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p = self.stage_bundle(temp)
            f = p / 'README.md'; f.unlink(); f.symlink_to(story.DEFAULT / 'README.md')
            with self.assertRaisesRegex(ValueError, 'regular allowlisted file'):
                story.load_payload(p)

    def test_checksum_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p = self.stage_bundle(temp)
            with (p / 'README.md').open('a') as stream:
                stream.write('unreviewed alteration\n')
            with self.assertRaisesRegex(ValueError, 'publication checksum'):
                story.load_payload(p)

    def test_public_source_checksum_still_checked_after_bundle_rechecksum(self):
        def mutate(d):
            next(s for s in d['sources'] if s['source_access'] == 'PUBLIC')['sha256'] = '0' * 64
        # Direct semantic validation avoids stopping first at the unchanged claim map.
        self.reject(mutate, 'public source checksum')

    def test_restricted_source_cannot_have_fake_public_link(self):
        self.reject(lambda d: next(s for s in d['sources'] if s['source_access'] == 'RESTRICTED').__setitem__('url', 'https://example.com/raw.json'), 'restricted source')

    def test_log_reference_cannot_open_a_restricted_source(self):
        value = self.mutated(lambda d: d['observer']['long_boundaries']['rows'][0].__setitem__(
            'source_id', next(s['id'] for s in d['sources'] if s['source_access'] == 'RESTRICTED')))
        # Hash verification uses read_bytes. No parser read is allowed before
        # rejecting this first log's unapproved reference.
        with mock.patch.object(Path, 'read_text', side_effect=AssertionError('unexpected parser read')):
            with self.assertRaisesRegex(ValueError, 'public log source binding before open'):
                story.validate_payload(value)

    def test_rechecksummed_claim_tier_change_requires_a_reviewed_edition(self):
        with tempfile.TemporaryDirectory() as temp:
            p = self.stage_bundle(temp)
            claim_map = p / 'CLAIM_DATA_MAP.tsv'
            text = claim_map.read_text()
            self.assertIn('MEASURED_SAVED_PHYSICAL', text)
            claim_map.write_text(text.replace('MEASURED_SAVED_PHYSICAL', 'PUBLIC_RECOMPUTABLE', 1))
            manifest = json.loads((p / 'PUBLICATION_ALLOWLIST.json').read_text())
            row = next(r for r in manifest['files'] if r['path'] == claim_map.name)
            row.update(bytes=claim_map.stat().st_size, sha256=story.digest(claim_map))
            (p / 'PUBLICATION_ALLOWLIST.json').write_text(json.dumps(manifest, indent=2) + '\n')
            with self.assertRaisesRegex(ValueError, 'reviewed v001 content changed'):
                story.load_payload(p)

    def test_private_absolute_paths_and_raw_arrays_are_rejected(self):
        self.reject(lambda d: d['theory']['proof_scope'].__setitem__('private_checkpoint_blob', 'abc'))
        self.reject(lambda d: d['theory']['COV'].__setitem__('weighted_design', [[1.0] * 32] * 60))
        self.reject(lambda d: d['theory']['proof_scope'].__setitem__('source', '/home/' + 'private/model.mtp'))

    def test_nonfinite_numeric_and_duplicate_json_keys_are_rejected(self):
        self.reject(lambda d: d['theory']['COV'].__setitem__('data_loss_incumbent', float('nan')), 'nonfinite')
        self.reject(lambda d: d['theory']['linear_system'].__setitem__('K_condition_2', 'Infinity'), 'nonfinite')
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(ValueError):
                story.strict_json(raw)

    def test_rechecksummed_null_s3_cannot_be_a_measurement(self):
        def mutation(d):
            next(r for r in d['theory']['main4500']['states'] if r['id'] == 'S3')['native_J'] = 0.0
        with tempfile.TemporaryDirectory() as temp:
            stage = self.stage_bundle(temp, mutation)
            with self.assertRaisesRegex(ValueError, 'S3 objective'):
                story.load_payload(stage)

    def test_counterfactual_cannot_be_a_native_training_transition(self):
        self.reject(lambda d: next(r for r in d['theory']['main4500']['states'] if r['id'] == 'S1c').__setitem__('native_trajectory', True), 'trajectory classification')

    def test_new_s2q_cannot_be_relabeled_captured_native_k(self):
        def mutation(d):
            for row in d['theory']['linear_system']['systems']:
                row['new_S2q_physical_target'] = row['id'] == 'ACTUAL_K_CAPTURE'
        self.reject(mutation, 'S2q fixed system')

    def test_native_j_row_loss_and_force_rmse_units_are_distinct(self):
        self.reject(lambda d: d['theory']['main4500'].__setitem__('unit', 'force RMSE eV/angstrom'), 'objective axis')
        self.reject(lambda d: d['observer']['end_terminal']['pbe14'].__setitem__('unit', 'native J'), 'PBE14 unit')
        self.reject(lambda d: d['theory']['architecture']['objective'].__setitem__('normalization_configurations', 1620), 'row normalization')

    def test_fixed_d_q_and_signed_balance_are_recomputed(self):
        self.reject(lambda d: d['theory']['linear_system']['row_loss_table'][1].__setitem__('Q_fixed_D', '0.0036'), 'Q = data')
        self.reject(lambda d: d['theory']['linear_system']['signed_ridge_balance'].__setitem__('ridge_tradeoff', '0.001'), 'signed fixed-D balance')

    def test_negative_error_diagnostics_cannot_pass_one_sided_bounds(self):
        self.reject(lambda d: d['theory']['linear_system']['verification'][0].__setitem__('normalized_backward_error', '-1'), 'saved high precision bounds')
        self.reject(lambda d: d['theory']['linear_system']['signed_ridge_balance'].__setitem__('closure', '-1'), 'signed fixed-D balance')
        self.reject(lambda d: d['theory']['COV'].__setitem__('projected_stationarity_normalized', -1.0), 'saved COV numerical checks')

    def test_causal_percentages_and_exact_rank_overclaims_are_rejected(self):
        self.reject(lambda d: d['theory']['architecture'].__setitem__('physical_rank_240_asserted', True), 'physical rank caveat')
        self.reject(lambda d: d['theory']['linear_system']['signed_ridge_balance'].__setitem__('physical_causal_percentages', True), 'signed balance scope')

    def test_cov_percentage_and_physical_scope_are_checked(self):
        self.reject(lambda d: d['theory']['COV'].__setitem__('percent_of_total_data_loss_removed', 75.0), 'COV total-loss percentage')
        self.reject(lambda d: d['theory']['COV'].__setitem__('candidate_native_EF_or_gradient', 'PASS'), 'candidate physical scope')
        self.reject(lambda d: d['theory']['COV'].__setitem__('full_unprojected_stationarity_required', True), 'constrained COV')

    def test_prediction_prox_does_not_remove_75_percent_of_total_loss(self):
        self.reject(lambda d: d['theory']['prediction_prox'].__setitem__('percent_of_total_data_loss_removed', 75.0), 'prediction total-loss denominator')
        self.reject(lambda d: d['theory']['prediction_prox'].__setitem__('fraction_of_available_gap_removed', 0.5), 'prediction available-gap denominator')

    def test_synthetic_terminal_counterexample_is_preserved(self):
        self.reject(lambda d: d['t1']['checkpoint_example']['rows'][0].__setitem__('BEST_role', 'END_MAIN'), 'opposite synthetic terminal')

    def test_reload_and_hardware_safety_overclaims_are_rejected(self):
        self.reject(lambda d: d['t1']['qualification']['reload'].__setitem__('full_BFGS_resume_qualified', True), 'reload evaluation-only')
        self.reject(lambda d: d['t1']['qualification']['faults'].__setitem__('power_loss_tested', True), 'fault scope')
        self.reject(lambda d: d['t1']['qualification']['sanitizers'].__setitem__('external_BLAS_LAPACK_Fortran_instrumented', True), 'sanitizer scope')

    def test_long_jump_prefixes_cannot_be_double_counted(self):
        self.reject(lambda d: d['observer']['long_boundaries'].__setitem__('positive_printed_increases', 1223), '1163 long increases')

    def test_short_decreasing_example_cannot_be_reversed(self):
        self.reject(lambda d: d['observer']['short_main50']['states'][1].__setitem__('native_J', 1.0), 'opposite short refit')

    def test_case_block_and_region_means_are_independently_checked(self):
        self.reject(lambda d: d['observer']['end_terminal']['pbe14']['block_rows'][0].__setitem__('END_MAIN', .5), 'case to block')
        self.reject(lambda d: d['observer']['end_terminal']['pbe14']['regional_rows'][0].__setitem__('TERMINAL', .5), 'equal-block region')

    def test_consistent_but_false_h_table_fails_against_public_force_vectors(self):
        def mutation(d):
            pbe = d['observer']['end_terminal']['pbe14']
            for key in ('case_scores', 'block_rows', 'regional_rows'):
                for row in pbe[key]:
                    row['HISTORICAL_H'] *= 2
        self.reject(mutation, 'public H force-component reconstruction')

    def test_terminal_missing_raw_tier_cannot_be_upgraded(self):
        self.reject(lambda d: d['observer']['end_terminal']['pbe14']['evidence_by_model'].__setitem__('TERMINAL', 'PUBLIC_RAW_VECTORS_VERIFIED'), 'terminal raw-vector limitation')

    def test_prior_failed_runtime_receipt_cannot_be_rewritten(self):
        self.reject(lambda d: d['observer']['end_terminal']['historical_status'].__setitem__('XI_T_P1_runtime_capture', 'PASS'), 'negative evidence preserved')

    def test_recovery_is_not_counted_as_t1_or_new_t2(self):
        self.reject(lambda d: d['observer']['recovery'].__setitem__('new_T2_runs', 1), 'recovery execution boundary')
        self.reject(lambda d: d['t1']['scope']['historical_t1'].__setitem__('new_real_train60_fits', 1), 'historical T1 real-call scope')

    def test_public_loader_never_opens_restricted_locators(self):
        original = Path.open
        opened = []
        def guarded(path, *args, **kwargs):
            opened.append(str(path))
            self.assertNotIn('audit_sources', path.parts)
            self.assertNotIn('audit', path.parts)
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'open', guarded):
            story.load_payload()
        self.assertGreaterEqual(len(opened), 45)

    def test_builder_copies_only_named_sources_and_preserves_payload_bytes(self):
        # Isolated stand-in CSS/ESM exercise the export boundary without depending
        # on browser rendering; full site/visual tests cover actual frontend assets.
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); repository = base / 'repo'; (repository / 'site').mkdir(parents=True)
            for name in ('optimization.css', 'optimization.mjs'):
                (repository / 'site' / name).write_text('/* exporter fixture */\n')
            out = base / 'out'
            with mock.patch.object(story, 'ROOT', repository):
                returned = story.build(out)
            self.assertEqual(returned, self.data)
            self.assertEqual((out / 'data/optimization.json').read_bytes(), (story.DEFAULT / 'OPTIMIZATION_STORY.json').read_bytes())
            expected = {'data/optimization.json', 'optimization.css', 'optimization.mjs'} | {'data/optimization/' + n for n in story.BUNDLE_FILES}
            self.assertEqual({p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}, expected)
            self.assertFalse(any(p.suffix in ('.mtp', '.cfg', '.bin', '.zip') for p in out.rglob('*')))

    def test_output_cannot_overwrite_sources(self):
        for directory in (ROOT, ROOT / 'site', ROOT / 'data/optimization_story', ROOT / 'tools'):
            with self.subTest(directory=directory), self.assertRaisesRegex(ValueError, 'output root|source overwrite'):
                story.build(directory)

    def test_output_symlink_is_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); target = base / 'target'; target.mkdir()
            out = base / 'out'; out.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'output directory symlink'):
                story.build(out)
            self.assertEqual(list(target.iterdir()), [])

    def test_essay_marker_is_rendered_without_claiming_private_raw_reproduction(self):
        import build_research_site
        rendered = build_research_site.article_html('## The fit\n@study: optimization\n', {'evidence': {}}, [])
        self.assertIn('href="#optimization"', rendered)
        self.assertIn('reviewed aggregates', rendered)
        self.assertNotIn('@study:', rendered)


if __name__ == '__main__':
    unittest.main()

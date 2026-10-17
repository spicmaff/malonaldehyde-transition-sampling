"""Positive and adversarial saved-data tests; no scientific executable is launched."""
import copy, csv, io, json, math, shutil, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import verify_pbe14_offpath as pbe
import verify_optimizer_budget as budget

class PBE14Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=pbe.verify();cls.cfg=(pbe.DEFAULT/'references/PBE14_EXACT.cfg').read_text()
        cls.qe=(pbe.DEFAULT/'qe/L01m/pw.out').read_text()

    def mutate(self,rel,fn):
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/'pbe14_mtp20_v001';shutil.copytree(pbe.DEFAULT,dst)
            p=dst/rel;p.write_text(fn(p.read_text()))
            with self.assertRaises((ValueError,FileNotFoundError)):pbe.verify(dst,check_hashes=False)

    def test_positive_full_count_and_primary(self):
        r=self.result
        self.assertEqual((len(r['case_rows']),len(r['block_rows']),len(r['region_rows'])),(280,160,40))
        self.assertAlmostEqual(r['primary']['mean'],-.1461353992591766,14)
        self.assertEqual(r['primary']['targeted_better_count'],4)
        self.assertEqual(len(r['qe_quality']),14)

    def test_ids_and_units(self):
        r=pbe.parse_cfg(self.cfg)
        self.assertEqual([x['features']['candidate_id'] for x in r],pbe.IDS)
        self.assertLess(max(x['max_force_component_abs_residual_eV_A'] for x in self.result['qe_quality']),1e-12)

    def test_missing_geometry(self):
        self.mutate('references/PBE14_EXACT.cfg',lambda s:s[:s.rfind('BEGIN_CFG')])

    def test_swapped_atoms(self):
        s=self.cfg.splitlines();i=next(i for i,l in enumerate(s) if 'AtomData:' in l)
        s[i+1],s[i+2]=s[i+2],s[i+1]
        with self.assertRaises(ValueError):pbe.parse_cfg('\n'.join(s))

    def test_nan(self):
        s=self.cfg.replace('-0.367026806384638','NaN',1)
        self.assertNotEqual(s,self.cfg)
        with self.assertRaises(ValueError):pbe.parse_cfg(s)

    def test_infinite_energy(self):
        with self.assertRaises(ValueError):pbe.parse_cfg(self.cfg.replace('-1949.641354812907139','Infinity',1))

    def test_wrong_species(self):
        with self.assertRaises(ValueError):pbe.parse_cfg(self.cfg.replace('1 2 6.487','1 0 6.487',1))

    def test_seed_mapping(self):
        self.mutate('MODELS_AND_PREDICTIONS_SHA256.tsv',lambda s:s.replace(pbe.SEEDS[0],pbe.SEEDS[1],1))

    def test_cap_mapping(self):
        self.mutate('MODELS_AND_PREDICTIONS_SHA256.tsv',lambda s:s.replace('\t2000\t','\t8000\t',1))

    def test_nineteen_models(self):
        self.mutate('MODELS_AND_PREDICTIONS_SHA256.tsv',lambda s:'\n'.join(s.splitlines()[:-1])+'\n')

    def test_twenty_one_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/'data';shutil.copytree(pbe.DEFAULT,dst)
            first=next((dst/'predictions').glob('*.cfg'));shutil.copyfile(first,dst/'predictions/extra.cfg')
            with self.assertRaises(ValueError):pbe.verify(dst,check_hashes=False)

    def test_force_corruption_not_just_hash(self):
        model=pbe.table(pbe.DEFAULT/'MODELS_AND_PREDICTIONS_SHA256.tsv')[0]
        def f(s):
            ls=s.splitlines();i=next(i for i,l in enumerate(ls) if 'AtomData:' in l)
            keys=ls[i].split(':',1)[1].split();v=ls[i+1].split();v[keys.index('fx')]=str(float(v[keys.index('fx')])+.125)
            ls[i+1]=' '.join(v);return '\n'.join(ls)+'\n'
        self.mutate(model['prediction_path'],f)

    def test_reference_region_inversion(self):
        self.mutate('GEOMETRY_ROLES.tsv',lambda s:s.replace('BASIN_LEFT','TRANSITION_CENTER',1))

    def test_singleton_duplication(self):
        rows=copy.deepcopy(self.result['case_rows']);rows.append(copy.deepcopy(next(r for r in rows if r['mode']=='H_out_of_plane')))
        with self.assertRaises(ValueError):pbe.aggregate(rows)

    def test_wrong_sign_membership(self):
        rows=copy.deepcopy(self.result['case_rows']);rows[0]['sign']=1
        with self.assertRaises(ValueError):pbe.aggregate(rows)

    def test_not_pooled_rmse(self):
        r=[r for r in self.result['case_rows'] if r['seed_index']==2 and r['branch']=='basin' and r['budget']==8000 and r['region']=='TRANSITION_CENTER']
        pooled=math.sqrt(sum(x['force_RMSE_eV_A']**2 for x in r)/len(r))
        actual=next(x['force_RMSE_eV_A'] for x in self.result['region_rows'] if x['seed_index']==2 and x['branch']=='basin' and x['budget']==8000 and x['region']=='TRANSITION_CENTER')
        self.assertGreater(abs(pooled-actual),1e-3)

    def test_no_best_seed_filter(self):
        self.assertEqual([r['seed_index'] for r in self.result['primary']['contrasts']],list(range(5)))
        self.assertGreater(self.result['primary']['contrasts'][3]['targeted_minus_basin_eV_A'],0)

    def test_primary_sign_inversion(self):
        def f(s):
            d=json.loads(s)
            for r in d['primary_signed_targeted_minus_basin']:r['primary_targeted_minus_basin_eV_A']*=-1
            return json.dumps(d)
        self.mutate('RESULTS_EXPECTED.json',f)

    def test_qe_missing_total_heading(self):
        with self.assertRaises(ValueError):pbe.parse_qe(self.qe.replace('Forces acting on atoms','A later component term'))

    def test_qe_wrong_force_component_block(self):
        text=self.qe;head=text.index('Forces acting on atoms')
        start=text.index('atom',head);end=text.index('\n',text.index('atom    9',start))
        before=text[:start];after=text[end:]
        wrong='\n'.join(f'atom {i+1} type {t+1} force = 0.0 0.0 0.0' for i,t in enumerate(pbe.TYPES))
        with self.assertRaises(ValueError):pbe.parse_qe(before+wrong+after)

    def test_qe_not_done(self):
        with self.assertRaises(ValueError):pbe.parse_qe(self.qe.replace('JOB DONE.','JOB ABORTED.'))

    def test_manifest_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/'data';shutil.copytree(pbe.DEFAULT,dst)
            p=dst/'GEOMETRY_ROLES.tsv';p.write_text(p.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'checksum'):pbe.verify(dst)

class BudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=budget.verify()
        cls.log=(budget.DEFAULT/'logs/seed_00_basin_2000.txt').read_text()

    def test_all_twenty_stops(self):
        self.assertEqual(len(self.result['endpoints']),20)
        self.assertEqual({r['stop_reason'] for r in self.result['endpoints']},{'STEP_LIMIT'})
        self.assertEqual(self.result['visible_long_run_increases'],1163)
        self.assertEqual(len(self.result['matched_prefixes']),10)

    def test_missing_stop(self):
        with self.assertRaises(ValueError):budget.parse_log(self.log.replace('step limit reached','supposed convergence'))

    def test_wrong_cap(self):
        with self.assertRaises(ValueError):budget.parse_log(self.log.replace('BFGS iterations count set to 2000','BFGS iterations count set to 8000'))

    def test_missing_iteration(self):
        with self.assertRaises(ValueError):budget.parse_log(self.log.replace('BFGS iter 1500:','missing 1500:'))

    def test_stopping_not_saved_model_objective(self):
        self.assertTrue(all('before terminal' in r['objective_scope'] for r in self.result['endpoints']))

if __name__=='__main__':unittest.main()

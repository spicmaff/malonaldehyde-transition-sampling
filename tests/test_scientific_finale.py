"""Arithmetic, scope and static-fallback tests for the scientific conclusion."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from decimal import Decimal, localcontext
from fractions import Fraction as F
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'site')]
import build_scientific_finale as f
import scientific_finale as view
import build_research_site as site

class Tags(HTMLParser):
    def __init__(self,s):
        super().__init__();self.tags=[];self.feed(s)
    def handle_starttag(self,t,a):self.tags.append((t,dict(a)))

class FinaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=json.loads((ROOT/f.SOURCE).read_text());cls.data=f.load()
        cls.tmp=tempfile.TemporaryDirectory();cls.out=Path(cls.tmp.name)/'site';site.build(cls.out)
        cls.html=(cls.out/'index.html').read_text();cls.tags=Tags(cls.html).tags
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def reject(self,modify):
        p=copy.deepcopy(self.raw);modify(p)
        with self.assertRaises((ValueError,KeyError,TypeError)):f.derive(p)
    def test_registered_finale_assets(self):f.verify_manifest()
    def test_false_t2_status_rejected(self):self.reject(lambda p:p['t1']['statuses'].update(T2='PASS'))
    def test_source_pin(self):self.assertEqual(hashlib.sha256((ROOT/f.SOURCE).read_bytes()).hexdigest(),f.SOURCE_SHA)
    def test_q_equals_sum(self):
        with localcontext() as ctx:
            ctx.prec=140
            for r in self.data['rows']:self.assertLess(abs(Decimal(r['ell'])+Decimal(r['R'])-Decimal(r['Q'])),Decimal('1e-95'))
    def test_independent_signed_tradeoff(self):
        a,b=self.data['rows'];D=lambda r,k:Decimal(r[k])
        self.assertGreater(D(b,'ell')-D(a,'ell'),0);self.assertLess(D(b,'R')-D(a,'R'),0)
        self.assertAlmostEqual(float(100*(D(a,'Q')-D(b,'Q'))/D(a,'Q')),28.64275976971342,places=12)
    def test_native_ratio_is_not_row_ratio(self):
        n=self.data['native'];r=self.data['rows']
        self.assertAlmostEqual(n['ratio'],n['S2']/n['S0'],places=12)
        self.assertGreater(abs(n['ratio']-float(r[1]['ell'])/float(r[0]['ell'])),1e-5)
    def test_curve_independent_alpha_zero_and_one(self):
        q=self.data['direction'];p=lambda a:q['l0']+q['a']*a+q['b']*a*a/2
        self.assertEqual(p(0),q['l0']);self.assertLess(abs(p(1)-float(self.data['rows'][1]['ell'])),1e-15)
        self.assertTrue(all(p(i/100)>p((i-1)/100) for i in range(1,101)))
        self.assertEqual(q['minimum_on_domain'],0)
    def test_counterexample_is_negative(self):self.assertLess(self.data['counterexample']['delta_J'],0)
    def test_s3_rejects_invented_measurement(self):
        self.reject(lambda p:next(s for s in p['theory']['main4500']['states'] if s['id']=='S3').update(native_J=0))
    def test_wrong_q_rejected(self):self.reject(lambda p:p['theory']['linear_system']['row_loss_table'][1].update(Q_fixed_D='0'))
    def test_ridge_sign_rejected(self):self.reject(lambda p:p['theory']['linear_system']['row_loss_table'][2].update(ridge_penalty='-1'))
    def test_normalization_rejected(self):self.reject(lambda p:p['theory']['linear_system']['signed_ridge_balance'].update(normalization=1680))
    def test_j_ratio_rejected(self):self.reject(lambda p:p['theory']['main4500'].update(S2_to_S0_ratio=18))
    def test_branch_as_native_rejected(self):self.reject(lambda p:next(s for s in p['theory']['main4500']['states'] if s['id']=='S1c').update(native_trajectory=True))
    def test_s2q_wrong_problem_rejected(self):self.reject(lambda p:p['theory']['linear_system']['systems'][0].update(new_S2q_physical_target=False))
    def test_direction_negative_slope_rejected(self):self.reject(lambda p:p['theory']['prediction_prox']['native_ridge_direction'].update(derivative_at_zero=-1))
    def test_direction_wrong_endpoint_rejected(self):self.reject(lambda p:p['theory']['prediction_prox']['native_ridge_direction'].update(second_derivative=1))
    def test_wrong_cov_denominator_rejected(self):self.reject(lambda p:p['theory']['COV'].update(percent_of_total_data_loss_removed=75))
    def test_cov_physical_claim_rejected(self):self.reject(lambda p:p['theory']['COV'].update(candidate_native_EF_or_gradient='PASS'))
    def test_t2_execution_rejected(self):self.reject(lambda p:p['scope'].update(T2_executed=True))
    def test_real_data_superiority_rejected(self):self.reject(lambda p:p['scope'].update(COV_real_data_optimizer_superiority_proven=True))
    def test_nonfinite_rejected(self):self.reject(lambda p:p['theory']['prediction_prox']['native_ridge_direction'].update(derivative_at_zero=float('nan')))
    def test_metric_transport_exact_rational_example(self):
        # An algebraic fixture, not an MTP experiment. T=[[2,0],[1,1]].
        beta=[F(3),F(2)];prime=[F(1,2),F(2)];T=[[F(2),F(0)],[F(1),F(1)]]
        newD=[[sum(T[i][k]*T[j][k] for k in range(2)) for j in range(2)] for i in range(2)]
        old=sum(x*x for x in beta);new=sum(prime[i]*newD[i][j]*prime[j] for i in range(2) for j in range(2))
        self.assertEqual(old,new);self.assertNotEqual(old,sum(x*x for x in prime))
    def test_increment_descent_identity_exact_fixture(self):
        a,r,m=F(2),F(3),F(5);delta=-a*r/(a*a+m)
        self.assertEqual(r*r-(r+a*delta)**2,delta*delta*(a*a+2*m));self.assertGreater(r*r-(r+a*delta)**2,0)
    def test_twelve_routes_and_old_ids_retained(self):
        self.assertEqual(sum('data-page' in a for _,a in self.tags),12)
        ids=[a['id'] for _,a in self.tags if 'id' in a];self.assertEqual(len(ids),len(set(ids)))
        for target in ['opt-parameters','opt-episode','opt-checkpoints','opt-candidate','opt-evidence','opt-next-study','opt-sources']:
            self.assertIn(target,ids)
    def test_source_anchors_exist(self):
        ids={a['id'] for _,a in self.tags if 'id' in a}
        for _,a in self.tags:
            href=a.get('href','')
            if href.startswith('#opt-'):self.assertIn(href[1:],ids)
    def test_new_controls_disabled_without_js(self):
        controls=[a for t,a in self.tags if 'data-sf-step' in a or a.get('id') in ['sf-play','sf-prev','sf-next','sf-reset','sf-alpha']]
        self.assertEqual(len(controls),11);self.assertTrue(all('disabled' in a for a in controls))
    def test_static_table_is_data_bound(self):
        cells=[a for _,a in self.tags if 'data-sf-exact' in a];self.assertEqual(len(cells),6)
        for a in cells:
            state,key=a['data-sf-exact'].split('-');row=next(r for r in self.data['rows'] if r['state']==state)
            self.assertEqual(a['data-value'],row[key])
    def test_export_and_public_source_bytes(self):
        self.assertEqual(json.loads((self.out/'data/finale.json').read_text()),self.data)
        for p in (ROOT/'data/optimization_story/v001').iterdir():
            if p.is_file():self.assertEqual(p.read_bytes(),(self.out/'data/optimization'/p.name).read_bytes())
    def test_no_new_route_or_physical_evaluation(self):
        self.assertIn('not a new experiment',self.html);self.assertIn('not a new least-squares solve',self.html)
        self.assertIn('T2_NOT_AUTHORIZED_NOT_EXECUTED',self.html)
    def test_wrong_template_and_double_extension_fail(self):
        with self.assertRaises(ValueError):view.refine_document('bad',self.data)
        with self.assertRaises(ValueError):view.refine_document(self.html,self.data)
    def test_visual_scales_and_conclusion_visible(self):
        self.assertIn('fixed linear scale',self.html);self.assertIn('The improvement was real.',self.html)
        self.assertIn('not a demonstrated repair of S2',self.html)
        self.assertIn(f.VISIBLE_LIMIT,self.html)
    def test_runtime_has_no_unbounded_clock(self):
        script=(ROOT/'site/scientific_finale.mjs').read_text()
        self.assertNotIn('setInterval(',script);self.assertIn('visibilitychange',script);self.assertIn('prefers-reduced-motion',script)
    def test_assets_in_build(self):
        for name in ['scientific_finale.css','scientific_finale.mjs']:
            self.assertEqual((ROOT/'site'/name).read_bytes(),(self.out/name).read_bytes())

if __name__=='__main__':unittest.main()

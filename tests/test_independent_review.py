"""Evidence boundaries, build identity and preservation of prior provenance."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'site')]
import build_research_site
import build_identity
import editorial
import presentation_review


class IndependentReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.out=Path(cls.temp.name)/'site'
        build_research_site.build(cls.out)
        cls.html=(cls.out/'index.html').read_text()

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_download_and_page_share_the_scientific_scope(self):
        self.assertIn(editorial.ESSAY_SCOPE,(self.out/'longread.en.md').read_text())
        self.assertIn(editorial.ESSAY_SCOPE,self.html)
        self.assertNotIn('Everything displayed here can be reconstructed',self.html)
        self.assertIn('nonnegative and vanishes at zero',self.html)
        self.assertIn('An approximate numerical solution must verify',self.html)

    def test_evidence_disclosure_precedes_the_sticky_map(self):
        self.assertEqual(self.html.count('class="ed-evidence-limit"'),1)
        self.assertLess(self.html.index('class="ed-evidence-limit"'),self.html.index('class="cin-chapter-map"'))

    def test_build_identity_is_a_hash_bound_output_separate_from_science(self):
        identity=json.loads((self.out/'build-identity.json').read_text())
        self.assertEqual(identity['source_commit'],subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
        manifest=json.loads((self.out/'build-manifest.json').read_text())
        self.assertEqual(manifest['build-identity.json'],hashlib.sha256((self.out/'build-identity.json').read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.out/'data/science.json').read_text())['science_commit'],'f44d28cc0b13defb747f625376b083055b577629')

    def test_independent_manifest_rejects_scientific_override_and_wrong_parent(self):
        real=Path.open
        manifest=ROOT/'provenance/INDEPENDENT_REVIEW_DELTA.tsv'
        saved=manifest.read_text()
        from io import StringIO
        def opening(path,*a,**kw):
            if path==manifest:return StringIO(saved.replace('site/app.mjs','data/frozen_models_v028/train_basin60_v028.cfg',1))
            return real(path,*a,**kw)
        with patch.object(Path,'open',opening),self.assertRaisesRegex(ValueError,'Unexpected independent review manifest scope'):
            presentation_review.verify_registered_assets(ROOT)
        rows=list(csv.DictReader(saved.splitlines(),delimiter='\t'))
        rows[0]['previous_repository_sha256']='0'*64
        bad=StringIO();w=csv.DictWriter(bad,rows[0].keys(),delimiter='\t');w.writeheader();w.writerows(rows)
        def wrong_parent(path,*a,**kw):return StringIO(bad.getvalue()) if path==manifest else real(path,*a,**kw)
        with patch.object(Path,'open',wrong_parent),self.assertRaisesRegex(ValueError,'Independent review manifest previous hash mismatch'):
            presentation_review.verify_registered_assets(ROOT)

    def test_identity_detects_dirty_source_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def git(*args):subprocess.run(['git','-C',directory,*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            git('init');git('config','user.name','Build identity test');git('config','user.email','identity@example.invalid')
            (root/'source.txt').write_text('one\n');git('add','source.txt');git('commit','-m','Fixture')
            a=build_identity.build_identity(root)
            self.assertTrue(a['working_copy_clean']);self.assertEqual(a,build_identity.build_identity(root))
            (root/'source.txt').write_text('two\n')
            b=build_identity.build_identity(root)
            self.assertFalse(b['working_copy_clean']);self.assertEqual(a['source_commit'],b['source_commit']);self.assertIsNotNone(b['tracked_diff_sha256'])
            (root/'tools').mkdir();(root/'tools/check.py').write_text('pass\n')
            self.assertIn('tools/check.py',build_identity.build_identity(root)['untracked_source_sha256'])

    def test_final_acceptance_cannot_override_science_or_erase_its_parent(self):
        from io import StringIO
        manifest=ROOT/'provenance/FINAL_ACCEPTANCE_DELTA.tsv'
        saved=manifest.read_text();real=Path.open
        cases=[
            (saved.replace('site/editorial.py','data/frozen_models_v028/train_targeted60_v028.cfg',1),
             'Unexpected final acceptance manifest scope'),
            (saved.replace('NEW','0'*64,1),'Final acceptance manifest previous hash mismatch'),
        ]
        for altered,message in cases:
            def opening(path,*a,**kw):return StringIO(altered) if path==manifest else real(path,*a,**kw)
            with patch.object(Path,'open',opening),self.assertRaisesRegex(ValueError,message):
                presentation_review.verify_registered_assets(ROOT)


if __name__=='__main__':unittest.main()

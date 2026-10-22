"""Installed browser QA dependencies must not change the source identity."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_identity import build_identity


class PublicationIdentityTests(unittest.TestCase):
    def test_locked_qa_install_is_ignored_but_source_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                subprocess.run(['git', '-C', directory, *args], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            git('init')
            git('config', 'user.name', 'Publication identity fixture')
            git('config', 'user.email', 'identity@example.invalid')
            (root / '.gitignore').write_bytes((ROOT / '.gitignore').read_bytes())
            dependency_ignore = root / 'tools/site/.gitignore'
            dependency_ignore.parent.mkdir(parents=True)
            dependency_ignore.write_bytes((ROOT / 'tools/site/.gitignore').read_bytes())
            (root / 'source.txt').write_text('saved source\n')
            git('add', '.gitignore', 'tools/site/.gitignore', 'source.txt')
            git('commit', '-m', 'Fixture')
            before = build_identity(root)
            installed = root / 'tools/site/node_modules/fixture/index.js'
            installed.parent.mkdir(parents=True)
            installed.write_text('export default 1;\n')
            self.assertEqual(before, build_identity(root))
            self.assertTrue(before['working_copy_clean'])

            source = root / 'site/unregistered.mjs'
            source.parent.mkdir()
            source.write_text('export default 2;\n')
            self.assertFalse(build_identity(root)['working_copy_clean'])
            self.assertIn('site/unregistered.mjs', build_identity(root)['untracked_source_sha256'])
            source.unlink()
            (root / 'source.txt').write_text('changed source\n')
            self.assertIsNotNone(build_identity(root)['tracked_diff_sha256'])


if __name__ == '__main__':
    unittest.main()

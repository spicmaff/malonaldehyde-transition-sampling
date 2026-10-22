"""Publication cleanup must preserve scientific and secret-scanning guards."""
import csv
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import audit_public_repo
from publication_metadata import load_metadata_overrides


class PublicationMetadataTests(unittest.TestCase):
    def reject_manifest(self, change, message):
        manifest = ROOT / 'provenance/PUBLICATION_METADATA_DELTA.tsv'
        rows = list(csv.DictReader(manifest.read_text().splitlines(), delimiter='\t'))
        change(rows)
        stream = StringIO()
        writer = csv.DictWriter(stream, rows[0].keys(), delimiter='\t')
        writer.writeheader(); writer.writerows(rows)
        original = Path.open
        def opening(path, *args, **kwargs):
            return StringIO(stream.getvalue()) if path == manifest else original(path, *args, **kwargs)
        with patch.object(Path, 'open', opening), self.assertRaisesRegex(ValueError, message):
            load_metadata_overrides(ROOT)

    def test_scientific_override_is_rejected(self):
        self.reject_manifest(lambda rows: rows[0].update(repository_path='data/frozen_models_v028/train_basin60_v028.cfg'), 'metadata scope')

    def test_wrong_parent_is_rejected(self):
        self.reject_manifest(lambda rows: rows[0].update(previous_repository_sha256='0' * 64), 'parent mismatch')

    def test_provider_secret_detection_remains_active(self):
        patterns = dict(audit_public_repo.SECRET_PATTERNS)
        self.assertIsNotNone(patterns['provider_api_key'].search('sk-' + 'a' * 30))
        self.assertIsNone(patterns['provider_api_key'].search('ordinary publication text'))


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Offline rejection tests: corruption, forged success, changed trust root, unsafe output."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import za


class RejectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / 'reference'
        self.reference.mkdir()
        self.generated = self.root / 'generated'
        self.generated.mkdir()
        self.lock_path = self.root / 'lock.json'
        refs = {}
        files = {}
        for key, name in [('pie', 'llvm-pie.elf'), ('eboot', 'eboot.bin')]:
            p = self.reference / name
            p.write_bytes((key + '-original').encode())
            (self.generated / name).write_bytes(p.read_bytes())
            refs[key] = str(p)
            files[str(p)] = dict(size=p.stat().st_size, sha256=za.sha(p))
        self.lock = dict(schema=1, shared=[], profiles=dict(test=dict(
            tree=str(self.reference), inputs=list(refs.values()), references=refs,
            delivered_eboot=refs['eboot'])), files=files)
        self.lock_path.write_text(json.dumps(self.lock))
        self.proof_path = self.generated / 'proof.json'
        self.proof = dict(profile='test', status='passed',
                          profile_lock_sha256=za.sha(self.lock_path),
                          method='relink-frozen-objects-and-convert-sign')
        self.write_proof()

    def write_proof(self):
        self.proof_path.write_text(json.dumps(self.proof))

    def check(self):
        with patch.object(za, 'LOCK', self.lock_path):
            return za.check_proof(self.lock, self.proof_path)

    def test_valid_actual_bytes_pass(self):
        self.assertEqual(self.check()['status'], 'passed')

    def test_generated_same_size_corruption_rejected(self):
        p = self.generated / 'eboot.bin'
        p.write_bytes(b'X' * p.stat().st_size)
        with self.assertRaisesRegex(za.ZaError, 'Generated output'):
            self.check()

    def test_reference_same_size_corruption_rejected(self):
        p = self.reference / 'llvm-pie.elf'
        p.write_bytes(b'X' * p.stat().st_size)
        with self.assertRaisesRegex(za.ZaError, 'Reference'):
            self.check()
        report = za.check_files(self.lock, ['test'])
        self.assertFalse(report['ok'])
        self.assertEqual(report['errors'][0]['error'], 'SHA-256 mismatch')

    def test_forged_success_without_output_rejected(self):
        (self.generated / 'eboot.bin').unlink()
        with self.assertRaisesRegex(za.ZaError, 'Generated output'):
            self.check()

    def test_failed_receipt_rejected_even_if_bytes_match(self):
        self.proof['status'] = 'failed'
        self.write_proof()
        with self.assertRaisesRegex(za.ZaError, 'did not pass'):
            self.check()

    def test_changed_lock_rejected(self):
        self.lock_path.write_text(self.lock_path.read_text() + '\n')
        with self.assertRaisesRegex(za.ZaError, 'different profile lock'):
            self.check()

    def test_unknown_method_rejected(self):
        self.proof['method'] = 'copy-old-eboot'
        self.write_proof()
        with self.assertRaisesRegex(za.ZaError, 'Unknown proof method'):
            self.check()

    def test_unknown_profile_rejected(self):
        with self.assertRaisesRegex(za.ZaError, 'Unknown profile'):
            za.selection(self.lock, '../r28')

    def test_output_under_original_tree_rejected(self):
        with self.assertRaisesRegex(za.ZaError, 'protected input tree'):
            za.new_root(self.reference / 'candidate', self.lock)
        self.assertFalse((self.reference / 'candidate').exists())

    def test_existing_output_and_reports_preserved(self):
        with self.assertRaises(FileExistsError):
            za.new_root(self.generated, self.lock)
        with self.assertRaises(FileExistsError):
            za.atomic_json(self.proof_path, dict(status='replacement'))
        self.assertEqual(json.loads(self.proof_path.read_text()), self.proof)

    def test_build_missing_builder_stops(self):
        with patch.object(za, 'REPO', self.root), patch.object(za.sys, 'argv',
                ['za', 'build', 'r29-ui', '--out', '/tmp/r29ui-new']):
            with self.assertRaisesRegex(za.ZaError, 'builder is not present'):
                za.dispatch()

    def test_build_preserves_builder_failure(self):
        script = self.root / 'port/ui-v2/tools/build-r29-ui.py'
        script.parent.mkdir(parents=True)
        script.write_text('raise SystemExit(9)\n')
        with patch.object(za, 'REPO', self.root), patch.object(za.sys, 'argv',
                ['za', 'build', 'r29-ui', '--out', '/tmp/r29ui-new']):
            self.assertEqual(za.dispatch(), 9)

    def _release_dir(self, profile_name='rel'):
        releases = self.root / 'releases'
        releases.mkdir(exist_ok=True)
        base = dict(schema=1, method='m', profiles={}, files={}, shared=[], sdk_shared_libraries=[])
        self.lock_path.write_text(json.dumps(base))
        rel = dict(schema=1, shared=[], sdk_shared_libraries=[], files=dict(self.lock['files']),
                   profiles={profile_name: dict(self.lock['profiles']['test'])})
        path = releases / (profile_name + '.lock.json')
        path.write_text(json.dumps(rel))
        return releases, path

    def test_release_lock_merged_with_its_own_lock_sha(self):
        releases, path = self._release_dir()
        with patch.object(za, 'LOCK', self.lock_path), patch.object(za, 'RELEASES', releases):
            lock = za.read_lock()
            self.assertIn('rel', lock['profiles'])
            self.assertEqual(za.lock_path(lock, 'rel'), path)
            self.proof.update(profile='rel', profile_lock_sha256=za.sha(path))
            self.write_proof()
            self.assertEqual(za.check_proof(lock, self.proof_path)['status'], 'passed')
            self.proof['profile_lock_sha256'] = za.sha(self.lock_path)  # base lock is not the trust root
            self.write_proof()
            with self.assertRaisesRegex(za.ZaError, 'different profile lock'):
                za.check_proof(lock, self.proof_path)

    def test_release_lock_conflicting_pin_rejected(self):
        self.lock_path.write_text(json.dumps(self.lock))
        releases = self.root / 'releases'
        releases.mkdir()
        ref = str(self.reference / 'eboot.bin')
        (releases / 'x.lock.json').write_text(json.dumps(dict(
            schema=1, shared=[], sdk_shared_libraries=[], profiles={},
            files={ref: dict(size=1, sha256='0' * 64)})))
        base = dict(self.lock, sdk_shared_libraries=[])
        self.lock_path.write_text(json.dumps(base))
        with patch.object(za, 'LOCK', self.lock_path), patch.object(za, 'RELEASES', releases):
            with self.assertRaisesRegex(za.ZaError, 'pins'):
                za.read_lock()

    def test_windows_argument_translation(self):
        self.assertEqual(za.cli_path('C:\\ZA test\\new'), '/mnt/c/ZA test/new')
        self.assertEqual(za.cli_path('/home/tomer/r29ui-new'), '/home/tomer/r29ui-new')


if __name__ == '__main__':
    unittest.main()

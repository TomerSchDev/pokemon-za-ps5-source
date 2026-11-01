"""Synthetic filesystem/integration regressions; no game, compiler, queue or console."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_cleanup as cleanup
import za


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / 'output'
        self.output.mkdir()
        self.references = self.root / 'references'
        self.references.mkdir()
        self.lock_path = self.root / 'lock.json'
        self.lock_path.write_text('{}')
        refs = {}
        files = {}
        comparisons = {}
        for key, name in (('pie', 'llvm-pie.elf'), ('eboot', 'eboot.bin')):
            reference = self.references / name
            reference.write_bytes(('retained-' + name).encode())
            output = self.output / name
            output.write_bytes(reference.read_bytes())
            digest = za.sha(output)
            refs[key] = str(reference)
            files[str(reference)] = {'size': reference.stat().st_size, 'sha256': digest}
            comparisons[key] = {'file': name, 'size': output.stat().st_size,
                                'expected_sha256': digest, 'actual_sha256': digest,
                                'sha256_matches': True, 'byte_for_byte_equal': True}
        self.lock = {'schema': 1, 'method': 'm', 'files': files, 'shared': [],
                     'profiles': {'p': {'tree': str(self.references), 'inputs': list(refs.values()),
                                        'references': refs, 'delivered_eboot': refs['eboot']}}}
        self.proof = {'profile': 'p', 'status': 'passed', 'method': 'relink-frozen-objects-and-convert-sign',
                      'profile_lock_sha256': za.sha(self.lock_path), 'inputs_after': {'ok': True},
                      'outputs': comparisons}
        (self.output / 'proof.json').write_text(json.dumps(self.proof))
        for name in cleanup.INTERMEDIATES:
            (self.output / name).write_bytes(('temporary-' + name).encode())

    def invoke(self, **kwargs):
        return cleanup.cleanup_conversion_intermediates(self.output, **kwargs)

    def assert_kept(self):
        self.assertTrue(all((self.output / n).is_file() for n in cleanup.INTERMEDIATES))

    def symlink(self, source, target, directory=False):
        try:
            source.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            self.skipTest('symlink creation unavailable: ' + str(exc))

    def test_cleanup_preserves_existing_check_proof_and_unrelated_files(self):
        extra = self.output / 'do-not-delete.o'
        extra.write_bytes(b'input')
        original_proof = (self.output / 'proof.json').read_bytes()
        result = self.invoke(protected_paths=self.references.iterdir())
        self.assertEqual(result['status'], 'cleaned')
        self.assertEqual({r['file'] for r in result['deleted']}, set(cleanup.INTERMEDIATES))
        self.assertFalse(any((self.output / n).exists() for n in cleanup.INTERMEDIATES))
        self.assertEqual(extra.read_bytes(), b'input')
        self.assertEqual((self.output / 'proof.json').read_bytes(), original_proof)
        with patch.object(za, 'LOCK', self.lock_path):
            self.assertEqual(za.check_proof(self.lock, self.output / 'proof.json')['status'], 'passed')
        stored = json.loads(Path(result['receipt']).read_text())
        self.assertEqual(stored, result)
        self.assertIsNone(result['physical_reclaimed_bytes'])

    def test_already_clean_is_idempotent_and_does_not_replace_prior_receipt(self):
        first = self.invoke()
        first_bytes = Path(first['receipt']).read_bytes()
        second = self.invoke()
        self.assertEqual(second['status'], 'already_clean')
        self.assertEqual(second['logical_bytes_removed'], 0)
        self.assertNotEqual(second['receipt'], first['receipt'])
        self.assertEqual(Path(first['receipt']).read_bytes(), first_bytes)

    def test_debug_retention_has_reason_and_no_deletion(self):
        result = self.invoke(keep_reason='Inspect a conversion failure from an adjacent candidate')
        self.assertEqual(result['status'], 'kept_for_debug')
        self.assertEqual(result['deleted'], [])
        self.assert_kept()
        with self.assertRaises(ValueError):
            self.invoke(keep_reason='   ')

    def test_failed_or_incomplete_proof_preserves_both_intermediates(self):
        for mutation in ({'status': 'failed'}, {'inputs_after': {'ok': False}}, {'outputs': {}}):
            with self.subTest(mutation=mutation):
                (self.output / 'proof.json').write_text(json.dumps({**self.proof, **mutation}))
                result = self.invoke()
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['deleted'], [])
                self.assert_kept()

    def test_missing_required_pie_does_not_weaken_proof(self):
        (self.output / 'llvm-pie.elf').unlink()
        self.assertEqual(self.invoke()['status'], 'error')
        self.assert_kept()
        with patch.object(za, 'LOCK', self.lock_path), self.assertRaises(za.ZaError):
            za.check_proof(self.lock, self.output / 'proof.json')

    def test_symlink_target_preflight_prevents_any_delete(self):
        candidate = self.output / 'eboot.elf'
        candidate.unlink()
        external = self.root / 'external.elf'
        external.write_bytes(b'protected')
        self.symlink(candidate, external)
        self.assertEqual(self.invoke()['status'], 'error')
        self.assertTrue((self.output / 'title-stripped.elf').is_file())
        self.assertEqual(external.read_bytes(), b'protected')

    def test_symlink_parent_cannot_escape_output(self):
        alias = self.root / 'alias'
        self.symlink(alias, self.output, directory=True)
        with self.assertRaises(ValueError):
            cleanup.cleanup_conversion_intermediates(alias)
        self.assert_kept()

    def test_hardlinked_intermediate_preserves_all_links(self):
        extra = self.root / 'external-link.elf'
        extra.hardlink_to(self.output / 'eboot.elf')
        self.assertEqual(self.invoke()['status'], 'error')
        self.assert_kept()
        self.assertTrue(extra.is_file())

    def test_protected_input_overlap_rejected(self):
        with self.assertRaises(ValueError):
            self.invoke(protected_paths=[self.output / 'eboot.elf'])
        self.assert_kept()

    def test_unlink_denial_is_error_not_claimed_success(self):
        original = Path.unlink
        def denied(path, *args, **kwargs):
            if path == self.output / 'title-stripped.elf':
                raise PermissionError('synthetic sharing denial')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', denied):
            result = self.invoke()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['deleted'], [])
        self.assert_kept()

    def test_changed_identity_is_error_before_unlink(self):
        original = cleanup._identity
        calls = 0
        def changed(path):
            nonlocal calls
            result = original(path)
            if path == self.output / 'title-stripped.elf':
                calls += 1
                if calls == 2:
                    result = {**result, 'size': result['size'] + 1}
            return result
        with patch.object(cleanup, '_identity', changed):
            result = self.invoke()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['deleted'], [])
        self.assert_kept()

    def test_partial_io_failure_retains_exact_successful_unlink_evidence(self):
        original = Path.unlink
        def denied(path, *args, **kwargs):
            if path == self.output / 'eboot.elf':
                raise PermissionError('synthetic second-file sharing denial')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', denied):
            result = self.invoke()
        self.assertEqual(result['status'], 'error')
        self.assertEqual([r['file'] for r in result['deleted']], ['title-stripped.elf'])
        self.assertFalse((self.output / 'title-stripped.elf').exists())
        self.assertTrue((self.output / 'eboot.elf').exists())
        self.assertEqual(json.loads(Path(result['receipt']).read_text()), result)

    def test_changed_root_identity_is_error_without_unlink(self):
        original = cleanup._identity
        calls = 0
        def replaced(path):
            nonlocal calls
            result = original(path)
            if path == self.output:
                calls += 1
                if calls > 1:
                    result = {**result, 'inode': result['inode'] + 1}
            return result
        with patch.object(cleanup, '_identity', replaced), self.assertRaisesRegex(ValueError, 'root identity changed'):
            self.invoke()
        self.assert_kept()

    def test_reproduction_failure_never_calls_cleanup(self):
        out = self.root / 'failed-build'
        with patch.object(za, 'LOCK', self.lock_path), patch.object(za, 'check_files', return_value={'ok': True}), \
                patch.object(za, 'relink', return_value={'profile': 'p', 'status': 'failed'}), \
                patch.object(za, 'cleanup_profiles') as invoke:
            result = za.reproduce(self.lock, ['p'], out)
        invoke.assert_not_called()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['cleanup']['status'], 'not_run_failed_build')

    def test_successful_reproduce_cleans_only_after_last_profile_gate(self):
        out = self.root / 'completed-build'
        def relink(_lock, _name, directory):
            for name in (*cleanup.RETAINED, *cleanup.INTERMEDIATES):
                (directory / name).write_bytes((self.output / name).read_bytes())
            return dict(self.proof)
        with patch.object(za, 'LOCK', self.lock_path), patch.object(za, 'check_files', return_value={'ok': True}), \
                patch.object(za, 'relink', side_effect=relink):
            result = za.reproduce(self.lock, ['p'], out)
            self.assertEqual(za.check_proof(self.lock, out / 'p/proof.json')['status'], 'passed')
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['cleanup']['p']['status'], 'cleaned')
        self.assertFalse((out / 'p/eboot.elf').exists())
        self.assertTrue((out / 'p/llvm-pie.elf').is_file())
        self.assertEqual(json.loads((out / 'summary.json').read_text()), result)

    def test_later_profile_failure_keeps_earlier_profile_diagnostics(self):
        lock = {**self.lock, 'profiles': {**self.lock['profiles'], 'q': self.lock['profiles']['p']}}
        out = self.root / 'multi-build'
        def relink(_lock, name, directory):
            for filename in (*cleanup.RETAINED, *cleanup.INTERMEDIATES):
                (directory / filename).write_bytes((self.output / filename).read_bytes())
            return {'profile': name, 'status': 'passed' if name == 'p' else 'failed'}
        with patch.object(za, 'LOCK', self.lock_path), patch.object(za, 'check_files', return_value={'ok': True}), \
                patch.object(za, 'relink', side_effect=relink), patch.object(za, 'cleanup_profiles') as invoke:
            result = za.reproduce(lock, ['p', 'q'], out)
        invoke.assert_not_called()
        self.assertEqual(result['status'], 'failed')
        self.assertTrue((out / 'p/eboot.elf').is_file())

    def test_cli_debug_option_requires_reason_and_rejects_other_builder(self):
        for argv in (['za', 'reproduce', 'p', '--out', 'x', '--keep-intermediates', ' '],
                     ['za', 'build', 'r29-ui', '--out', 'x', '--keep-intermediates', 'debug']):
            with self.subTest(argv=argv), patch.object(za.sys, 'argv', argv):
                with self.assertRaises(za.ZaError):
                    za.dispatch()

    def test_package_failure_defers_and_never_calls_cleanup(self):
        args = argparse.Namespace(out=str(self.output), package=None, keep_intermediates=None)
        with patch.object(za, 'read_lock', return_value=self.lock), patch.object(za, 'main_profile', return_value='p'), \
                patch.object(za, 'reproduce', return_value={'status': 'passed'}) as reproduce, \
                patch.object(za, 'check_package', return_value={'ok': False}), patch.object(za, 'cleanup_profiles') as invoke:
            self.assertEqual(za.build_main(args), 2)
        self.assertTrue(reproduce.call_args.kwargs['defer_cleanup'])
        invoke.assert_not_called()
        self.assert_kept()

    def test_successful_package_copy_precedes_cleanup(self):
        package = self.root / 'package'
        package.mkdir()
        (package / 'eboot.bin').write_bytes(b'pinned-final')
        (package / 'extra.txt').write_bytes(b'asset')
        sums = package / 'SHA256SUMS.json'
        sums.write_text(json.dumps({'eboot.bin': za.sha(package / 'eboot.bin'), 'extra.txt': za.sha(package / 'extra.txt')}))
        profile = {**self.lock['profiles']['p'], 'package_sums': str(sums)}
        lock = {**self.lock, 'profiles': {'p': profile}}
        generated = self.output / 'p'
        generated.mkdir()
        (generated / 'eboot.bin').write_bytes(b'pinned-final')
        destination = self.root / 'published'
        def clean(*_args):
            self.assertEqual((destination / 'eboot.bin').read_bytes(), b'pinned-final')
            self.assertEqual((destination / 'extra.txt').read_bytes(), b'asset')
            return {'p': {'status': 'cleaned'}}
        args = argparse.Namespace(out=str(self.output), package=str(destination), keep_intermediates=None)
        with patch.object(za, 'read_lock', return_value=lock), patch.object(za, 'main_profile', return_value='p'), \
                patch.object(za, 'reproduce', return_value={'status': 'passed'}), \
                patch.object(za, 'check_package', return_value={'ok': True}), patch.object(za, 'cleanup_profiles', side_effect=clean):
            self.assertEqual(za.build_main(args), 0)

    def test_cleanup_error_makes_overall_build_nonzero(self):
        args = argparse.Namespace(out=str(self.output), package=None, keep_intermediates=None)
        with patch.object(za, 'read_lock', return_value=self.lock), patch.object(za, 'main_profile', return_value='p'), \
                patch.object(za, 'reproduce', return_value={'status': 'passed'}), \
                patch.object(za, 'check_package', return_value=None), \
                patch.object(za, 'cleanup_profiles', return_value={'p': {'status': 'error', 'deleted': [], 'errors': ['denied']}}):
            self.assertEqual(za.build_main(args), 2)
        result = json.loads((self.output / 'build-main.json').read_text())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['reproduce']['status'], 'passed')

    def test_package_copy_exception_cannot_trigger_cleanup(self):
        package = self.root / 'package'
        package.mkdir()
        (package / 'SHA256SUMS.json').write_text(json.dumps({'eboot.bin': 'unused-in-test'}))
        profile = {**self.lock['profiles']['p'], 'package_sums': str(package / 'SHA256SUMS.json')}
        lock = {**self.lock, 'profiles': {'p': profile}}
        args = argparse.Namespace(out=str(self.output), package=str(self.root / 'publish'), keep_intermediates=None)
        with patch.object(za, 'read_lock', return_value=lock), patch.object(za, 'main_profile', return_value='p'), \
                patch.object(za, 'reproduce', return_value={'status': 'passed'}), \
                patch.object(za, 'check_package', return_value={'ok': True}), \
                patch.object(za.shutil, 'copyfile', side_effect=OSError('synthetic copy failure')), \
                patch.object(za, 'cleanup_profiles') as invoke:
            with self.assertRaisesRegex(OSError, 'copy failure'):
                za.build_main(args)
        invoke.assert_not_called()
        self.assert_kept()


if __name__ == '__main__':
    unittest.main()

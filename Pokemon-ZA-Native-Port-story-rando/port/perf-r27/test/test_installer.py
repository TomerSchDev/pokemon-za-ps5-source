"""Offline transaction guards; never opens a console connection or real save."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

MODULE = Path(__file__).resolve().parents[1] / 'install_r27.py'
spec = importlib.util.spec_from_file_location('r27_install_test', MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RecoveryGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.original = b'test-owned original executable'
        self.candidate = b'test-owned candidate executable'
        self.old = hashlib.sha256(self.original).hexdigest()
        self.new = hashlib.sha256(self.candidate).hexdigest()
        (self.out / 'original').mkdir()
        (self.out / 'original/eboot.bin').write_bytes(self.original)
        self.state = dict(initial_eboot_sha256=self.old, requested_sha256=self.new)
        for target, name, value in ((m, 'BASE_SHA', self.old), (m.h, 'OUT', self.out)):
            p = patch.object(target, name, value, create=True); p.start(); self.addCleanup(p.stop)
        self.console = Mock()

    def test_recovery_does_not_require_candidate_or_package(self):
        m.configure_rollback(self.state)
        self.assertEqual(m.i.OLD, self.old)
        self.assertEqual(m.i.NEW, self.new)
        self.assertFalse((self.out / 'package').exists())

    def test_corrupt_backup_rejected_before_any_network(self):
        (self.out / 'original/eboot.bin').write_bytes(b'changed')
        with self.assertRaises(AssertionError): m.rollback(self.console, self.state, 'test')
        self.assertFalse(self.console.mock_calls)

    def test_unknown_installed_binary_never_restored_over(self):
        self.console.sha256.return_value = 'a' * 64
        with patch.object(m.i, 'rollback') as restore:
            with self.assertRaises(AssertionError): m.rollback(self.console, self.state, 'test')
            restore.assert_not_called()
        self.assertEqual(len(self.console.mock_calls), 1)

    def test_known_candidate_can_enter_owned_recovery(self):
        self.console.sha256.return_value = self.new
        with patch.object(m.i, 'rollback') as restore:
            m.rollback(self.console, self.state, 'test')
            restore.assert_called_once_with(self.console, self.state, 'test')

    def test_recheck_rejects_changed_target_even_after_preflight(self):
        m.configure_rollback(self.state)
        with patch.object(m, 'base_replace') as replace:
            with self.assertRaises(AssertionError):
                m.strict_replace(self.console, 'eboot.bin', self.original, 'b' * 64, 'rollback-test')
            replace.assert_not_called()

    def test_rollback_cannot_use_candidate_as_original(self):
        m.configure_rollback(self.state)
        with patch.object(m, 'base_replace') as replace:
            with self.assertRaises(AssertionError):
                m.strict_replace(self.console, 'eboot.bin', self.candidate, self.new, 'rollback-test')
            replace.assert_not_called()

    def test_only_eboot_can_be_replaced(self):
        m.configure_rollback(self.state)
        with patch.object(m, 'base_replace') as replace:
            with self.assertRaises(AssertionError):
                m.strict_replace(self.console, 'save/main', self.original, self.new, 'rollback-test')
            replace.assert_not_called()


if __name__ == '__main__': unittest.main()

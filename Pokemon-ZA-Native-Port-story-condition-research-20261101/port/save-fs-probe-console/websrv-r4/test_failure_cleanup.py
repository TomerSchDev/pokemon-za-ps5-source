"""Bounded fake-API tests; never execute an ELF or contact the console."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
REPO = None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data), encoding='utf-8')


def proof(path):
    return {'path': str(path), 'sha256': sha(path)}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.helper = module('tested_failure_cleanup', HERE / 'failure_cleanup.py')
        self.q = module('cleanup_real_evidence', REPO / 'tools/console-install-queue/console_queue.py')
        self.payload = self.out / 'close-failed-side.elf'
        self.payload.write_bytes(b'synthetic NONEXECUTABLE ELF fixture')
        source = self.out / 'source.c'; source.write_text('synthetic source only', encoding='utf-8')
        self.manifest = self.out / 'cleanup-manifest.json'
        self.record = {'title': 'PPSA91780', 'dynamic_identity': True, 'app_id': None, 'pid': None,
                       'payload': proof(self.payload), 'source': proof(source)}
        write(self.manifest, self.record)
        self.config = {'cleanup_manifest': proof(self.manifest)}
        self.app = '/data/homebrew/PPSA91780'; self.sandbox = '/mnt/sandbox/PPSA91780_000'
        self.param = json.dumps({'titleId': 'PPSA91780'}).encode()
        self.launch = b'sceLncUtilLaunchApp rc=0x00004018\n'
        self.procs = [{'pid': 101, 'name': 'eboot.bin'}]
        self.hashes = {self.app + '/eboot.bin': 'd' * 64, self.app + '/close-failed-side.elf': sha(self.payload)}
        self.job = {'external_dependencies': [self.config['cleanup_manifest']],
                    'artifacts': [{'remote_path': self.app + '/eboot.bin', 'path': 'synthetic', 'sha256': 'd' * 64},
                                  {'remote_path': self.app + '/sce_sys/param.json', 'path': 'synthetic',
                                   'sha256': hashlib.sha256(self.param).hexdigest()},
                                  {'remote_path': self.app + '/close-failed-side.elf', **proof(self.payload)}]}
        self.prefix = b'old unrelated backlog\n'
        self.current = b'titleId[PPSA91780]\nappId={0x00004018}\n<101> EXEC /app0/eboot.bin native\nPRX_SCE_MODULE_LOAD_ERROR\n'
        (self.out / 'probe.klog.log').write_bytes(self.prefix + self.current)
        self.sent = []
        def send(path, out, expected, identity_args=(), **kwargs):
            self.sent.append((str(path), expected, identity_args, kwargs))
            self.procs = []
            return {'http_status': 200, 'payload_sha256': expected}
        self.driver = SimpleNamespace(APP=self.app, SANDBOX=self.sandbox, TITLE='PPSA91780',
             read=lambda p: json.loads(Path(p).read_text(encoding='utf-8')),
             load_sender=lambda config: SimpleNamespace(send_websrv_payload=send))
        api = SimpleNamespace(eboot_processes=lambda: self.procs, process_pid=lambda p: p['pid'], utc_now=lambda: 'synthetic-time')
        self.inst = SimpleNamespace(api=api, queue=self.q, m=SimpleNamespace(proof=proof, write=write))
        self.c = SimpleNamespace(read=lambda path, limit: self.param if path.endswith('param.json') else self.launch,
                                 sha256=lambda path: self.hashes[path])
        self.lease = SimpleNamespace(check=lambda: None)

    def identify(self):
        return self.helper.identify(self.c, self.config, self.driver, self.inst, self.job, self.out, len(self.prefix))

    def test_exact_failed_launch_sends_app_id_then_pid_once(self):
        ident = self.identify()
        self.helper.close(self.c, self.config, self.driver, self.inst, self.job, ident, self.lease, self.out)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][2], (0x4018, 101))
        self.assertEqual(self.sent[0][3], {'allowed_names': ('close-failed-side.elf',)})
        self.assertTrue(json.loads((self.out / 'failed-closed.json').read_text())['game_closed'])

    def test_changed_pid_is_never_closed(self):
        ident = self.identify(); self.procs = [{'pid': 999, 'name': 'eboot.bin'}]
        with self.assertRaises(RuntimeError): self.helper.close(self.c, self.config, self.driver, self.inst, self.job, ident, self.lease, self.out)
        self.assertEqual(self.sent, [])

    def test_other_mounted_title_is_rejected(self):
        self.param = json.dumps({'titleId': 'PPSA91762'}).encode()
        with self.assertRaises(RuntimeError): self.identify()
        self.assertEqual(self.sent, [])

    def test_changed_mounted_param_is_rejected(self):
        self.param = json.dumps({'titleId': 'PPSA91780', 'extra': 'changed'}).encode()
        with self.assertRaises(RuntimeError): self.identify()

    def test_changed_installed_eboot_is_rejected(self):
        self.hashes[self.app + '/eboot.bin'] = 'e' * 64
        with self.assertRaises(RuntimeError): self.identify()

    def test_missing_positive_original_app_id_is_not_guessed(self):
        self.launch = b'sceLncUtilLaunchApp rc=0x80000001\n'
        with self.assertRaises(RuntimeError): self.identify()

    def test_no_prx_failure_does_not_authorize_force_close(self):
        (self.out / 'probe.klog.log').write_bytes(self.prefix + self.current.replace(b'PRX_SCE_MODULE_LOAD_ERROR', b'healthy report pending'))
        with self.assertRaises(RuntimeError): self.identify()
        self.assertEqual(self.sent, [])

    def test_legacy91990_helper_is_rejected_before_process_control(self):
        self.record['title'] = 'PPSA91990'; write(self.manifest, self.record)
        self.config['cleanup_manifest'] = proof(self.manifest)
        self.job['external_dependencies'] = [self.config['cleanup_manifest']]
        with self.assertRaises(ValueError): self.identify()
        self.assertEqual(self.sent, [])

    def test_changed_snapshot_breaks_identity_proof(self):
        ident = self.identify()
        Path(ident['startup_log']['path']).write_bytes(b'changed')
        with self.assertRaises(self.q.QueueError): self.helper.verify(self.c, ident, self.driver, self.inst)

    def test_changed_installed_cleanup_payload_is_not_sent(self):
        ident = self.identify(); self.hashes[self.app + '/close-failed-side.elf'] = 'f' * 64
        with self.assertRaises(RuntimeError): self.helper.close(self.c, self.config, self.driver, self.inst, self.job, ident, self.lease, self.out)
        self.assertEqual(self.sent, [])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--repo', type=Path, required=True)
    args, rest = parser.parse_known_args(); REPO = args.repo.resolve()
    q = module('cleanup_pc_turn', REPO / 'tools/console-install-queue/console_queue.py')
    q.Board(resource='pc').check(*(os.environ.get('PC_TEST_' + k, '') for k in ('AGENT', 'TICKET', 'TOKEN')))
    unittest.main(argv=[__file__, *rest])

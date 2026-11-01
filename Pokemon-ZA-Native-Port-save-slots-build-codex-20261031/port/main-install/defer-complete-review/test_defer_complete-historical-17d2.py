"""Synthetic transaction tests of the exact AST-extracted bundle_main candidate.

Real canonical offline install_policy/evidence validation; in-memory FTP and
fake Board/Console prevent every hardware or production queue operation.
The harness itself requires a canonical PC lease before executing tests.
"""
import argparse
import ast
import ftplib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data) + '\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def reference(path):
    return {'path': str(path), 'sha256': digest(path)}


def real_queue(repo):
    source = repo / 'tools/console-install-queue/console_queue.py'
    spec = importlib.util.spec_from_file_location('synthetic_defer_real_policy', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Scenario:
    def __init__(self, root, repo, candidate, corrupt=False):
        self.root, self.corrupt = root, corrupt
        self.files, self.uploads, self.readbacks, self.emitted = {}, [], [], []
        self.closed, self.owner, self.complete_calls = False, True, 0
        self.guard_calls = {'authenticate': 0, 'authorize': 0, 'heartbeat': 0, 'check': 0, 'install_policy': 0}
        self.title = 'PPSA91990'
        app = '/data/homebrew/' + self.title
        payload, param, metadata = root / 'new.bin', root / 'param.json', root / 'manifest.json'
        payload.write_bytes(b'new synthetic candidate')
        write(param, {'titleId': self.title})
        write(metadata, {'scope': 'synthetic fixture, no real game data'})
        self.job = {'console': '192.168.1.135', 'title_id': self.title, 'name': 'synthetic',
                    'deployment': {'mode': 'side_app'}, 'expected_base': [],
                    'artifacts': [{**reference(payload), 'remote_path': app + '/eboot.bin'},
                                  {**reference(param), 'remote_path': app + '/sce_sys/param.json'}]}
        self.ready, self.handoff = root / 'ready.json', root / 'handoff.json'
        write(self.ready, {'save_backup': {'fresh': True, 'readback_verified': True}})
        write(self.handoff, {'name': 'synthetic', 'preserved_features': ['synthetic'],
                             'rebuild_instructions': 'synthetic source', 'manifest': reference(metadata)})
        queue_module = real_queue(repo)
        self.real_queue = queue_module
        queue_api = SimpleNamespace(**{name: getattr(queue_module, name) for name in dir(queue_module) if not name.startswith('__')})
        scenario = self

        class Board:
            def __init__(self, unused=None): self.root = root
            def load(self): return {'synthetic': True}
            def authenticate(self, state, agent, ticket, token, **kwargs):
                scenario.guard_calls['authenticate'] += 1
                assert (agent, ticket, token) == ('synthetic-defer', '00000001', 'not-a-production-token')
                return {'lease_id': 'synthetic'}, {'job': scenario.job}
            def expired(self, active): return False
            def authorize_install(self, *args): scenario.guard_calls['authorize'] += 1
            def heartbeat(self, *args, **kwargs): scenario.guard_calls['heartbeat'] += 1
            def check(self, *args): scenario.guard_calls['check'] += 1
            def complete(self, agent, ticket, token, receipt):
                scenario.complete_calls += 1
                scenario.final_receipt = read(receipt)
                assert scenario.final_receipt['console_handoff_complete'] is True
                scenario.owner = False
                return {'ticket': ticket, 'state': 'completed'}

        queue_api.Board = Board
        original_policy = queue_api.install_policy

        def policy(*args, **kwargs):
            scenario.guard_calls['install_policy'] += 1
            return original_policy(*args, **kwargs)
        queue_api.install_policy = policy

        class FTP:
            def mkd(self, path): pass
            def storbinary(self, command, source, size, callback):
                path = command.removeprefix('STOR ')
                data = source.read()
                scenario.files[path] = data
                scenario.uploads.append(path)
                callback(data)
            def rename(self, source, target): scenario.files[target] = scenario.files.pop(source)

        class Console:
            def __init__(self): self.ftp = FTP()
            def listing(self, path): return []
            def chmod(self, path, mode): pass
            def sha256(self, path):
                return hashlib.sha256(scenario.files[path]).hexdigest() if path in scenario.files else None
            def close(self): scenario.closed = True

        def bounded_file(console, path, destination, lease, limit=512 << 20):
            lease.check()
            data = scenario.files[path]
            if scenario.corrupt and '.new-' in path: data += b'CORRUPT'
            if len(data) > limit: raise RuntimeError('Synthetic bounded readback limit exceeded')
            destination.write_bytes(data)
            scenario.readbacks.append(path)
            return reference(destination)

        tree = ast.parse(candidate.read_text(encoding='utf-8'))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and
                     node.name in ('base_readback_limits', 'bundle_main')]
        assert len(functions) == 2
        namespace = {'argparse': argparse, 'Path': Path, 'os': os, 'uuid': uuid, 'ftplib': ftplib, 'time': time,
                     'queue': queue_api, 'read': read, 'write': write, 'proof': reference,
                     'emit': self.emitted.append, 'api': SimpleNamespace(Console=Console, eboot_processes=lambda: []),
                     'm': SimpleNamespace(bounded_file=bounded_file)}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(candidate), 'exec'), namespace)
        self.run_candidate = namespace['bundle_main']

    def run(self, defer=False):
        argv = ['install', '--console-ok', '--out', str(self.root / 'output'),
                '--readiness', str(self.ready), '--handoff', str(self.handoff)]
        if defer: argv.append('--defer-complete')
        with patch.dict(os.environ, {'CONSOLE_INSTALL_AGENT': 'synthetic-defer', 'CONSOLE_INSTALL_TICKET': '00000001',
                                     'CONSOLE_INSTALL_TOKEN': 'not-a-production-token'}, clear=False):
            return self.run_candidate(argv)


class DeferCompleteTests(unittest.TestCase):
    def scenario(self, corrupt=False):
        temporary = tempfile.TemporaryDirectory(prefix='za-defer-unit-')
        self.addCleanup(temporary.cleanup)
        return Scenario(Path(temporary.name), REPO, CANDIDATE, corrupt=corrupt)

    def assert_guards_and_transfer(self, s):
        self.assertEqual(s.guard_calls['authenticate'], 1)
        self.assertEqual(s.guard_calls['authorize'], 1)
        self.assertEqual(s.guard_calls['install_policy'], 1)
        self.assertGreater(s.guard_calls['heartbeat'], 0)
        self.assertGreater(s.guard_calls['check'], 0)
        self.assertEqual(len(s.uploads), 2)
        self.assertEqual(len(s.readbacks), 4)
        self.assertTrue(s.closed)

    def test_default_completes_once_after_verified_readbacks(self):
        s = self.scenario()
        self.assertEqual(s.run(), 0)
        self.assert_guards_and_transfer(s)
        self.assertEqual(s.complete_calls, 1)
        self.assertFalse(s.owner)
        self.assertTrue(s.final_receipt['console_handoff_complete'])
        self.assertEqual(s.emitted[-1]['state'], 'completed')

    def test_defer_retains_owner_and_pending_receipt(self):
        s = self.scenario()
        self.assertEqual(s.run(defer=True), 0)
        self.assert_guards_and_transfer(s)
        self.assertEqual(s.complete_calls, 0)
        self.assertTrue(s.owner)
        self.assertFalse(read(s.root / 'output/receipt.json')['console_handoff_complete'])
        self.assertEqual(s.emitted[-1]['state'], 'installed_verified_awaiting_handoff')

    def test_readback_failure_never_completes_either_mode(self):
        for defer in (False, True):
            with self.subTest(defer=defer):
                s = self.scenario(corrupt=True)
                with self.assertRaisesRegex(RuntimeError, 'Staged readback mismatch'):
                    s.run(defer=defer)
                self.assertEqual(s.complete_calls, 0)
                self.assertTrue(s.owner)
                self.assertTrue(s.closed)
                self.assertFalse((s.root / 'output/receipt.json').exists())
                self.assertFalse(read(s.root / 'output/error.json')['queue_released'])
                self.assertNotIn('/data/homebrew/PPSA91990/eboot.bin', s.files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    REPO, CANDIDATE = args.repo.resolve(), args.candidate.resolve()
    owner, ticket = (os.environ.get('PC_TEST_' + key) for key in ('AGENT', 'TICKET'))
    if not owner or not ticket or not os.environ.get('PC_TEST_TOKEN'):
        parser.error('canonical PC turn required, no production console token needed')
    checked = subprocess.run([sys.executable, '-I', str(REPO / 'workbench/zw.py'), 'pc-queue', 'check',
                              '--agent', owner, '--ticket', ticket], capture_output=True, check=True)
    if not json.loads(checked.stdout)['ok']:
        parser.error('PC turn unavailable')
    unittest.main(argv=[sys.argv[0]], verbosity=2)

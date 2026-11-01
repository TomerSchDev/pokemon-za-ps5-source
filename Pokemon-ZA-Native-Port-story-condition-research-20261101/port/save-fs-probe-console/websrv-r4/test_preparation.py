"""Prepared synthetic safety cases. Requires a canonical PC turn in main.

Executes the actual source backup() function with in-memory FTP data and
temporary host files. No live Console, launch, mount, observer write or install.
"""
import argparse
import ast
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest

CURRENT = '36b3d5d650bd1a8171c39a788785678fa395ab5c0043d6b02a0d028946944699'
LEGACY = '65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568'
HERE = Path(__file__).resolve().parent
REPO = BACKUP = None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value), encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def proof(path):
    return {'path': str(path), 'sha256': sha(path)}


class BackupFixture:
    def __init__(self, folder, initial=CURRENT, identity=CURRENT, remote=CURRENT):
        self.folder, self.closed, self.install_called = Path(folder), 0, False
        self.folder.mkdir(parents=True, exist_ok=True)
        self.initial_file = self.folder / 'initial.bin'
        self.initial_file.write_bytes(b'synthetic initial image, never a game image')
        self.initial_sha = initial
        self.remote_base = remote
        self.runs = ['r%08x-%08x' % (i + 1, i + 30) for i in range(18)]
        self.identity = {'pid': 321, 'session': '0123456789abcdef', 'run': self.runs[0],
                         'title': 'PPSA91762', 'eboot_sha256': identity, 'at': self.now(), 'label': 'synthetic'}
        self.data = '/synthetic/main/rando'
        self.eboot = '/synthetic/main/eboot.bin'
        self.contents = {self.data + '/active.json': json.dumps({'id': self.runs[0]}).encode()}
        self.names = ['save/save_0/main', 'settings.json', 'meta.json', 'a.txt', 'b.txt', 'c.txt', 'd.txt']
        for run in self.runs:
            for name in self.names:
                self.contents[self.data + '/' + run + '/' + name] = ('synthetic:' + run + '/' + name).encode()
        write(self.folder / 'initial-probe.json', {'base_sha256': initial, 'second_readback_verified': True,
                                                  'readback_path': str(self.initial_file)})
        fixture = self
        class Capture:
            def __init__(self, *args, **kwargs): pass
            def start(self): pass
            def stop(self): pass
        def local_sha(path):
            return fixture.initial_sha if Path(path) == fixture.initial_file else sha(path)
        def listing(c, path):
            assert path == fixture.data
            return [('active.json', {'type': 'file'})] + [(n, {'type': 'dir'}) for n in fixture.runs]
        def inventory(c, path):
            assert path.rsplit('/', 1)[1] in fixture.runs
            return list(fixture.names)
        def bounded(c, remote_path, path, lease, limit):
            lease.check()
            data = fixture.contents[remote_path]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(data)
            return {'remote_path': remote_path, **proof(path), 'bytes': len(data)}
        def close(c, ident, lease, out, label):
            assert ident == fixture.identity
            fixture.closed += 1
            write(out / (label + '-close.json'), {'identity': ident, 'at': fixture.now(), 'response': {'ok': True}})
        tree = ast.parse(Path(BACKUP).read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'backup')
        self.namespace = {'BASE': LEGACY, 're': re, 'read': read, 'write': write, 'sha': local_sha,
             'Path': Path, 'DATA': self.data, 'EBOOT': self.eboot,
             'api': SimpleNamespace(KlogCapture=Capture, utc_now=self.now), 'listing': listing,
             'inventory': inventory, 'owned': lambda c, ident: fixture.runs[0], 'bounded_file': bounded,
             'close_owned': close, 'emit': lambda *a: None,
             'mount_at_menu': lambda *a: (_ for _ in ()).throw(AssertionError('No implicit mount')),
             'install': lambda *a: (_ for _ in ()).throw(AssertionError('No installation in backup'))}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(BACKUP), 'exec'), self.namespace)
        self.c = SimpleNamespace(sha256=lambda path: self.remote_base if path == self.eboot
                                 else hashlib.sha256(self.contents[path]).hexdigest())
        self.lease = SimpleNamespace(check=lambda: None)
        self.driver = SimpleNamespace(read=read, sha=local_sha, fresh=self.fresh)

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def fresh(value):
        age = datetime.now(timezone.utc) - datetime.fromisoformat(value)
        if not -30 <= age.total_seconds() <= 300:
            raise ValueError('stale')

    def run(self, explicit=True, expected=CURRENT):
        kwargs = {'resume_identity': self.identity}
        if explicit:
            kwargs['expected_base_sha'] = expected
        self.namespace['backup'](self.c, self.lease, self.folder, **kwargs)

    def seal(self):
        self.run()
        session = self.identity['session']
        (self.folder / 'startup.log').write_text('main reached; ' + session, encoding='utf-8')
        write(self.folder / 'identity.json', self.identity)
        write(self.folder / 'closed.json', {'at': self.now(), 'game_closed': True, 'processes': [],
                                          'main_eboot_sha256': CURRENT})
        backup_sha = sha(BACKUP)
        self.config = {'main_eboot_sha256': CURRENT,
                       'helper_sha256': {'port/r28b-dlc-dex/install-r28b.py': backup_sha}}
        self.record = {'schema': 'fs-pre-enrollment-owned-backup-1', 'method': 'existing_m.backup_resume_identity',
                       'console': '192.168.1.135', 'closed_at': self.now(), 'save_files_written': False,
                       'main_eboot_sha256': CURRENT, 'backup_helper_sha256': backup_sha,
                       'backup_manifest': proof(self.folder / 'save-backup-manifest.json'),
                       'owned_close': proof(self.folder / 'original-save-backup-close.json'),
                       'closed_state': proof(self.folder / 'closed.json'),
                       'menu_identity': proof(self.folder / 'identity.json'),
                       'startup_log': proof(self.folder / 'startup.log'),
                       'initial_probe': proof(self.folder / 'initial-probe.json')}
        self.seal_path = self.folder / 'verified-backup.json'
        write(self.seal_path, self.record)
        q = module('preparation_real_evidence', REPO / 'tools/console-install-queue/console_queue.py')
        self.installer = SimpleNamespace(m=SimpleNamespace(api=SimpleNamespace(HOST='192.168.1.135')), queue=q)
        return self

    def change(self, field, update):
        path = Path(self.record[field]['path'])
        data = read(path)
        update(data)
        write(path, data)
        self.record[field] = proof(path)
        write(self.seal_path, self.record)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prep = module('reviewed_fs_preparation', HERE / 'preparation.py')

    def fixture(self, **kwargs):
        return BackupFixture(self.tmp.name, **kwargs)

    def test_current36_explicit_parameter_reads_all_runs_and_closes_only_owned_menu(self):
        f = self.fixture(); f.run()
        record = read(f.folder / 'save-backup-manifest.json')
        self.assertEqual((len(record['runs']), len(record['files']), f.closed), (18, 127, 1))
        self.assertTrue(record['all_runs'] and record['double_read_verified'])
        self.assertEqual(f.namespace['BASE'], LEGACY)

    def test_legacy_default_unchanged(self):
        f = self.fixture(initial=LEGACY, identity=LEGACY, remote=LEGACY); f.run(explicit=False)
        self.assertEqual(f.closed, 1)

    def test_current36_without_explicit_parameter_fails_before_close(self):
        f = self.fixture()
        with self.assertRaises(AssertionError): f.run(explicit=False)
        self.assertEqual(f.closed, 0)

    def test_wrong_explicit_base_fails_before_close(self):
        f = self.fixture()
        with self.assertRaises(AssertionError): f.run(expected='7' * 64)
        self.assertEqual(f.closed, 0)

    def test_malformed_explicit_base_fails_before_read_or_close(self):
        f = self.fixture()
        with self.assertRaises(ValueError): f.run(expected='unknown')
        self.assertEqual(f.closed, 0)

    def test_wrong_remote_image_fails_before_close(self):
        f = self.fixture(remote='7' * 64)
        with self.assertRaises(AssertionError): f.run()
        self.assertEqual(f.closed, 0)

    def test_fresh_complete_backup_with_actual_close_proof_is_consumable(self):
        f = self.fixture().seal()
        _, saved = self.prep.validated_backup(f.config, f.seal_path, f.driver, f.installer)
        self.assertEqual(len(saved['files']), 127)

    def test_stale_backup_is_never_retimed(self):
        f = self.fixture().seal()
        f.change('backup_manifest', lambda x: x.update(at=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()))
        with self.assertRaises(ValueError): self.prep.validated_backup(f.config, f.seal_path, f.driver, f.installer)

    def test_wrong_owned_close_pid_is_rejected(self):
        f = self.fixture().seal()
        f.change('owned_close', lambda x: x['identity'].update(pid=999))
        with self.assertRaises(ValueError): self.prep.validated_backup(f.config, f.seal_path, f.driver, f.installer)

    def test_open_main_cannot_be_claimed_closed(self):
        f = self.fixture().seal()
        f.change('closed_state', lambda x: x.update(processes=[{'pid': 321}], game_closed=False))
        with self.assertRaises(ValueError): self.prep.validated_backup(f.config, f.seal_path, f.driver, f.installer)

    def test_changed_backup_bytes_are_rejected(self):
        f = self.fixture().seal()
        saved = read(f.record['backup_manifest']['path'])
        Path(saved['files'][0]['path']).write_bytes(b'changed after verification')
        with self.assertRaises(ValueError): self.prep.validated_backup(f.config, f.seal_path, f.driver, f.installer)

    def test_wrong_main_title_is_rejected(self):
        f = self.fixture().seal()
        f.change('menu_identity', lambda x: x.update(title='PPSA91761'))
        with self.assertRaises(ValueError): self.prep.validated_backup(f.config, f.seal_path, f.driver, f.installer)

    def test_active_other_owner_blocks_before_connect(self):
        calls = []
        api = SimpleNamespace(Console=lambda: calls.append('connected'))
        inst = SimpleNamespace(m=SimpleNamespace(api=api), queue=SimpleNamespace(
            Board=lambda: SimpleNamespace(load=lambda: {'active': {'ticket': 'other'}})))
        with self.assertRaises(RuntimeError): self.prep.connection(inst)
        self.assertEqual(calls, [])

    def test_owner_appearing_on_read_aborts_and_restores_http_wrapper(self):
        state = {'active': None}
        def receive(command, callback, *args, **kwargs):
            state['active'] = {'ticket': 'other'}
            callback(b'not consumed')
        original_http = lambda *args, **kwargs: {'synthetic': True}
        fake = SimpleNamespace(ftp=SimpleNamespace(retrbinary=receive, mlsd=lambda: [], cwd=lambda *a: None), close=lambda: None)
        api = SimpleNamespace(Console=lambda: fake, http_json=original_http)
        inst = SimpleNamespace(m=SimpleNamespace(api=api), queue=SimpleNamespace(
            Board=lambda: SimpleNamespace(load=lambda: state)))
        c, _, _, _ = self.prep.connection(inst)
        consumed = []
        try:
            with self.assertRaises(RuntimeError): c.ftp.retrbinary('RETR synthetic', consumed.append)
        finally:
            c.close()
        self.assertEqual(consumed, [])
        self.assertIs(api.http_json, original_http)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--backup-source', type=Path, required=True)
    args, rest = parser.parse_known_args()
    REPO, BACKUP = args.repo.resolve(), args.backup_source.resolve()
    q = module('preparation_pc_turn', REPO / 'tools/console-install-queue/console_queue.py')
    q.Board(resource='pc').check(*(os.environ.get('PC_TEST_' + k, '') for k in ('AGENT', 'TICKET', 'TOKEN')))
    unittest.main(argv=[__file__, *rest])

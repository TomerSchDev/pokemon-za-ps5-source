"""No hardware: real policy/queue/FTP guard + synthetic artifacts, transport and clock."""
import importlib.util
import io
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result

fixtures = module('enforcement_fixtures', HERE / 'test_console_queue.py')
q = fixtures.q
guard = module('enforcement_guard', HERE / 'install_guard.py')


class Enforcement(unittest.TestCase):
    setUp = fixtures.QueueTests.setUp
    tearDown = fixtures.QueueTests.tearDown
    file = fixtures.QueueTests.file
    write_json = fixtures.QueueTests.write_json
    ready = fixtures.QueueTests.ready
    receipt = fixtures.QueueTests.receipt
    handoff = fixtures.QueueTests.handoff
    submit = fixtures.QueueTests.submit

    def observation(self, ticket, lease, state):
        return self.write_json('connection-' + state + '.json', {'console': q.CONSOLE,
            'ticket': ticket, 'lease_id': lease['lease_id'], 'state': state,
            'observed_at': self.clock[0], 'detail': 'Synthetic FTP handshake ' + state})

    def test_main_without_report_is_blocked_before_install_phase(self):
        document = q.read_json(self.job); document.pop('deployment')
        self.job.write_text(json.dumps(document))
        ticket = self.submit(); lease = self.board.claim('owner')
        with self.assertRaises(q.QueueError): self.board.authorize_install('owner', ticket, lease['token'])
        with self.assertRaises(q.QueueError):
            self.board.heartbeat('owner', ticket, lease['token'], begin_install=self.ready(ticket))
        self.assertEqual(self.board.status()['active']['phase'], 'reserved')

    def test_report_rejects_wrong_build_failed_test_and_tampered_log(self):
        document = q.read_json(self.job)
        reference = Path(document['deployment']['test_report']['path'])
        original = q.read_json(reference)
        for change in ('wrong-build', 'failed-test', 'missing-tests'):
            with self.subTest(change=change):
                report = json.loads(json.dumps(original))
                if change == 'wrong-build': report['candidate_sha256'] = '0' * 64
                if change == 'failed-test': report['tests'][0]['result'] = 'failed'
                if change == 'missing-tests': report['tests'] = []
                reference.write_text(json.dumps(report))
                document['deployment']['test_report'] = self.file(reference)
                with self.assertRaises(q.QueueError): q.install_policy(document)
        reference.write_text(json.dumps(original)); document['deployment']['test_report'] = self.file(reference)
        self.proof.write_text('Evidence changed after the reported test')
        with self.assertRaises(q.QueueError): q.install_policy(document)

    def side_job(self):
        title = 'PPSA91990'
        param = self.write_json('side-param.json', {'titleId': title})
        return {'console': q.CONSOLE, 'title_id': title, 'name': 'isolated side candidate',
            'deployment': {'mode': 'side_app'}, 'expected_base': [],
            'artifacts': [{**self.file(self.artifact), 'remote_path': '/data/homebrew/' + title + '/eboot.bin'},
                          {**self.file(param), 'remote_path': '/data/homebrew/' + title + '/sce_sys/param.json'}]}

    def test_unproven_side_allowed_but_title_metadata_and_paths_cannot_alias_main(self):
        side = self.side_job()
        self.assertEqual(q.install_policy(side)['mode'], 'side_app')
        for target in (q.MAIN_TITLE, 'PPSA91761'):
            with self.subTest(target=target):
                bad = self.side_job(); bad['title_id'] = target
                for item in bad['artifacts']: item['remote_path'] = item['remote_path'].replace('PPSA91990', target)
                with self.assertRaises(q.QueueError): q.install_policy(bad)
        bad = self.side_job(); bad['artifacts'][0]['remote_path'] = self.remote
        with self.assertRaises(q.QueueError): q.install_policy(bad)

    def test_side_policy_cache_never_skips_stream_hash_or_main_evidence(self):
        self.clock[0]=time.time()
        side=self.side_job(); self.job.write_text(json.dumps(side))
        ticket=self.submit(); lease=self.board.claim('owner')
        raw=MemoryFTP({}); ftp=guard.GuardedFTP(raw)
        env={'CONSOLE_INSTALL_STATE':str(self.root),'CONSOLE_INSTALL_AGENT':'owner',
             'CONSOLE_INSTALL_TICKET':ticket,'CONSOLE_INSTALL_TOKEN':lease['token']}
        target=side['artifacts'][0]['remote_path']+'.new-test'
        with patch.dict(os.environ,env), patch.object(guard.q,'install_policy',wraps=guard.q.install_policy) as policy:
            ftp.storbinary('STOR '+target,io.BytesIO(self.artifact.read_bytes()),1024,lambda _:None)
            ftp.storbinary('STOR '+target,io.BytesIO(self.artifact.read_bytes()),1024,lambda _:None)
            self.assertEqual(policy.call_count,1)
            with self.assertRaises(guard.q.QueueError):
                ftp.storbinary('STOR '+target,io.BytesIO(b'changed bytes'),1024,lambda _:None)
            self.assertEqual(raw.files[target],self.artifact.read_bytes())
            bad=json.loads(json.dumps(side));bad['title_id']='PPSA91762';bad['deployment']={'mode':'main_update'}
            with self.assertRaises(guard.q.QueueError):ftp.validate_policy(bad,self.root)
            self.assertEqual(policy.call_count,2)
            drift=json.loads(json.dumps(side));drift['artifacts'][0]['remote_path']=self.remote
            with self.assertRaises(guard.q.QueueError):ftp.validate_policy(drift,self.root)
        bad = self.side_job()
        param = Path(bad['artifacts'][1]['path']); param.write_text('{"titleId":"PPSA91762"}')
        bad['artifacts'][1] = {**self.file(param), 'remote_path': bad['artifacts'][1]['remote_path']}
        with self.assertRaises(q.QueueError): q.install_policy(bad)

    def test_noncanonical_remote_paths_are_rejected(self):
        for path in ('/data/homebrew/PPSA91990/../PPSA91762/eboot.bin', '//data/homebrew/PPSA91762/eboot.bin',
                     '/data/homebrew/PPSA91990/./eboot.bin', '/data/homebrew/PPSA91990/x\r\nDELE /main',
                     '/data/homebrew/PPSA91990\\..\\PPSA91762/eboot.bin'):
            with self.assertRaises(q.QueueError): q.remote_path(path)

    def test_disconnect_freezes_deadline_lease_and_queue_until_same_owner_reconnects(self):
        ticket = self.submit(); lease = self.board.claim('owner')
        second = self.submit('waiting')
        self.clock[0] += 100
        self.board.connection('owner', ticket, lease['token'], 'offline', self.observation(ticket, lease, 'offline'))
        self.clock[0] += 36000
        active = self.board.status()['active']
        self.assertTrue(active['paused']); self.assertFalse(active['expired'])
        self.assertEqual(active['seconds_to_yield'], 500)
        self.assertFalse(active['must_yield'])
        self.board.heartbeat('owner', ticket, lease['token'])
        with self.assertRaises(q.Busy): self.board.claim('next')
        with self.assertRaises(q.Busy): self.board.release('owner', ticket, lease['token'], reason='timeout')
        with self.assertRaises(q.Busy): self.board.complete('owner', ticket, lease['token'], self.receipt(ticket))
        with self.assertRaises(q.LostLease): self.board.connection('imposter', ticket, lease['token'], 'online', self.observation(ticket, lease, 'online'))
        self.board.connection('owner', ticket, lease['token'], 'online', self.observation(ticket, lease, 'online'))
        self.assertEqual(self.board.status()['active']['yield_by'], self.clock[0] + 500)
        self.assertEqual(self.board.status()['jobs'][1]['ticket'], second)

    def test_first_waiter_during_outage_gets_full_window_only_on_reconnection(self):
        ticket = self.submit(); lease = self.board.claim('owner')
        self.board.connection('owner', ticket, lease['token'], 'offline', self.observation(ticket, lease, 'offline'))
        self.clock[0] += 7000; self.submit('waiter')
        self.clock[0] += 7000
        self.assertEqual(self.board.status()['active']['seconds_to_yield'], 600)
        self.board.connection('owner', ticket, lease['token'], 'online', self.observation(ticket, lease, 'online'))
        self.assertEqual(self.board.status()['active']['yield_by'], self.clock[0] + 600)

    def test_user_connection_report_preserves_other_agents_ownership(self):
        ticket = self.submit(); lease = self.board.claim('owner')
        self.board.connection('owner', ticket, lease['token'], 'offline', self.observation(ticket, lease, 'offline'))
        before = self.board.load()['active'].copy()
        self.clock[0] += 1200
        path = self.observation(ticket, lease, 'online')
        record = q.read_json(path)
        record.update(source='user_message', reported_by='Tomer', quote='הקונסולה מחוברת,סמן בתור')
        path.write_text(json.dumps(record))
        self.board.connection('Tomer', ticket, '', 'online', path, user_report=True)
        after = self.board.load()['active']
        for key in ('ticket', 'agent', 'lease_id', 'token_hash', 'acquired_at'):
            self.assertEqual(after[key], before[key])
        self.assertFalse(self.board.status()['active']['paused'])
        self.assertTrue(self.board.status()['jobs'][0]['events'][-1]['user_report'])

    def test_user_report_rejects_missing_quote_or_changed_lease(self):
        ticket = self.submit(); lease = self.board.claim('owner')
        path = self.observation(ticket, lease, 'online')
        with self.assertRaises(q.QueueError): self.board.connection('Tomer', ticket, '', 'online', path, user_report=True)
        record = q.read_json(path)
        record.update(source='user_message', reported_by='Tomer', quote='connected', lease_id='another-lease')
        path.write_text(json.dumps(record))
        with self.assertRaises(q.QueueError): self.board.connection('Tomer', ticket, '', 'online', path, user_report=True)
        self.assertEqual(self.board.status()['active']['lease_id'], lease['lease_id'])

    def test_outage_detected_after_deadline_does_not_forfeit_turn(self):
        ticket = self.submit(); lease = self.board.claim('owner')
        self.submit('waiter'); self.clock[0] += 900
        self.board.connection('owner', ticket, lease['token'], 'offline', self.observation(ticket, lease, 'offline'))
        self.clock[0] += 8000
        self.board.connection('owner', ticket, lease['token'], 'online', self.observation(ticket, lease, 'online'))
        self.assertEqual(self.board.status()['active']['ticket'], ticket)
        self.assertEqual(self.board.status()['active']['seconds_to_yield'], 600)

    def test_ftp_guard_refuses_unproven_main_and_changed_upload_bytes_before_transport(self):
        self.clock[0] = time.time()
        ticket = self.submit(); lease = self.board.claim('owner')
        env = {'CONSOLE_INSTALL_STATE': str(self.root), 'CONSOLE_INSTALL_AGENT': 'owner',
               'CONSOLE_INSTALL_TICKET': ticket, 'CONSOLE_INSTALL_TOKEN': lease['token']}
        class Raw:
            calls = 0
            def storbinary(self, *args, **kwargs): self.calls += 1
        raw = Raw(); ftp = guard.GuardedFTP(raw)
        with patch.dict(os.environ, env):
            ftp.storbinary('STOR ' + self.remote + '.new-test', io.BytesIO(self.artifact.read_bytes()))
            self.assertEqual(raw.calls, 1)
            with self.assertRaises(guard.q.QueueError): ftp.storbinary('STOR ' + self.remote, io.BytesIO(b'other-build'))
            with self.assertRaises(guard.q.QueueError): ftp.storbinary('STOR /data/homebrew/PPSA91761/eboot.bin', io.BytesIO(b'anything'))
            with self.board.transaction('test') as state:
                state['jobs'][0]['job'].pop('deployment'); self.board.save(state)
            with self.assertRaises(guard.q.QueueError): ftp.storbinary('STOR ' + self.remote, io.BytesIO(self.artifact.read_bytes()))
        self.assertEqual(raw.calls, 1)

    def test_transport_failure_automatically_pauses_and_successful_probe_resumes(self):
        self.clock[0] = time.time()
        ticket = self.submit(); lease = self.board.claim('owner')
        env = {'CONSOLE_INSTALL_STATE': str(self.root), 'CONSOLE_INSTALL_AGENT': 'owner',
               'CONSOLE_INSTALL_TICKET': ticket, 'CONSOLE_INSTALL_TOKEN': lease['token']}
        class Raw:
            def retrbinary(self, *args): raise ConnectionResetError('synthetic disconnect')
        with patch.dict(os.environ, env):
            with self.assertRaises(ConnectionResetError): guard.GuardedFTP(Raw()).retrbinary('RETR /anything', lambda _: None)
            self.assertTrue(self.board.status()['active']['paused'])
            guard.observe_connection('online', 'Synthetic successful FTP handshake')
            self.assertFalse(self.board.status()['active']['paused'])
        self.assertEqual(self.board.status()['active']['ticket'], ticket)

    def bundle(self, side=False, with_native_module=False):
        self.clock[0] = time.time()
        if side:
            job=self.side_job()
            if with_native_module:
                native=self.base/'libc.prx';native.write_bytes(b'synthetic owned native shared module')
                job['artifacts'].append({**self.file(native),'remote_path':'/data/homebrew/PPSA91990/sce_module/libc.prx'})
            self.job.write_text(json.dumps(job))
        ticket = self.submit(); lease = self.board.claim('owner')
        ready = self.ready(ticket)
        data = q.read_json(ready)
        if side: data['base_readbacks'] = []
        ready.write_text(json.dumps(data))
        handoff = self.write_json('handoff.json', self.handoff())
        installer = module('synthetic_bundle_installer', HERE.parents[1] / 'port/main-install/install-main.py')
        raw = MemoryFTP({} if side else {self.remote: self.old.read_bytes()})
        console = MemoryConsole(raw)
        env = {'CONSOLE_INSTALL_STATE': str(self.root), 'CONSOLE_INSTALL_AGENT': 'owner',
               'CONSOLE_INSTALL_TICKET': ticket, 'CONSOLE_INSTALL_TOKEN': lease['token']}
        with patch.dict(os.environ, env), patch.object(installer.api, 'Console', return_value=console), patch.object(installer.api, 'eboot_processes', return_value=[]):
            code = installer.bundle_main(['install', '--out', str(self.base / 'install'), '--readiness', str(ready),
                                          '--handoff', str(handoff), '--console-ok'])
        self.assertEqual(code, 0)
        self.assertIsNone(self.board.status()['active'])
        for artifact in q.read_json(self.job)['artifacts']:
            self.assertEqual(raw.files[artifact['remote_path']], Path(artifact['path']).read_bytes())
        return raw

    def test_real_bundle_installer_side_flow_never_writes_main(self):
        raw = self.bundle(side=True)
        self.assertTrue(all('/PPSA91990/' in path for path in raw.files))

    def test_native_module_is_executable_after_guarded_stage_and_publish(self):
        raw=self.bundle(side=True,with_native_module=True)
        module='/data/homebrew/PPSA91990/sce_module/libc.prx'
        self.assertEqual(raw.modes[module],'755')
        self.assertEqual(raw.modes['/data/homebrew/PPSA91990/eboot.bin'],'755')
        self.assertEqual(raw.modes['/data/homebrew/PPSA91990/sce_sys/param.json'],'644')

    def test_fragmented_transfer_keeps_bounded_checks_and_twenty_second_heartbeat(self):
        installer=module('fragmented_bundle_lease',HERE.parents[1]/'port/main-install/install-main.py')
        from unittest.mock import Mock
        board=Mock();clock=[10.0]
        lease=installer.BundleTransferLease(board,'owner','ticket','private',clock=lambda:clock[0])
        for _ in range(10000):lease.check()
        self.assertEqual(board.check.call_count,1);board.heartbeat.assert_not_called()
        clock[0]+=.5;lease.check();self.assertEqual(board.check.call_count,2)
        clock[0]=30;lease.check();board.heartbeat.assert_called_once_with('owner','ticket','private')

    def test_fragmented_transfer_stops_on_next_poll_when_ownership_changes(self):
        installer=module('fragmented_bundle_lost',HERE.parents[1]/'port/main-install/install-main.py')
        from unittest.mock import Mock
        board=Mock();clock=[10.0]
        lease=installer.BundleTransferLease(board,'owner','ticket','private',clock=lambda:clock[0])
        lease.check();board.check.side_effect=installer.queue.LostLease('owned lease ended')
        clock[0]+=.5
        with self.assertRaises(installer.queue.LostLease):lease.check()

    def test_large_base_bounds_are_explicit_and_cannot_add_paths(self):
        installer=module('bundle_base_bounds',HERE.parents[1]/'port/main-install/install-main.py')
        side=self.side_job();remote=side['artifacts'][0]['remote_path']
        side['expected_base']=[{'remote_path':remote,'sha256':side['artifacts'][0]['sha256']}]
        side['deployment']['base_sizes']={remote:6_000_000_000}
        self.assertEqual(installer.base_readback_limits(side)[remote],6_000_000_000)
        for size in (-1,True,'6000000000',17<<30):
            side['deployment']['base_sizes']={remote:size}
            with self.assertRaises(ValueError):installer.base_readback_limits(side)
        side['deployment']['base_sizes']={'/data/homebrew/PPSA91762/eboot.bin':100}
        with self.assertRaises(ValueError):installer.base_readback_limits(side)

    def test_journal_retries_transient_smb_reader_without_losing_old_record(self):
        installer=module('journal_retry_test',HERE.parents[1]/'port/main-install/install-main.py')
        path=self.base/'journal.json';path.write_text('{"old":true}')
        original=installer.m.os.replace;failure=PermissionError('synthetic SMB sharing');failure.winerror=5
        with patch.object(installer.m.os,'replace',side_effect=[failure,None]) as replace:
            installer.m.write(path,{'new':True})
            self.assertEqual(replace.call_count,2)
            temporary=Path(replace.call_args[0][0]);self.assertEqual(q.read_json(path),{'old':True})
        original(temporary,path);self.assertEqual(q.read_json(path),{'new':True})

    def test_journal_persistent_access_denied_preserves_original_and_failed_evidence(self):
        installer=module('journal_denied_test',HERE.parents[1]/'port/main-install/install-main.py')
        path=self.base/'journal.json';path.write_text('{"old":true}')
        failure=PermissionError('synthetic persistent denial');failure.winerror=5
        with patch.object(installer.m.os,'replace',side_effect=failure),patch.object(installer.m.time,'monotonic',side_effect=[0,4]):
            with self.assertRaises(PermissionError):installer.m.write(path,{'new':True})
        self.assertEqual(q.read_json(path),{'old':True})
        self.assertEqual(len(list(self.base.glob('journal.json.tmp-*'))),1)

    def test_actual_stream_comparison_reads_every_byte_without_duplicate_files(self):
        installer=module('stream_compare_test',HERE.parents[1]/'port/main-install/install-main.py')
        reference=self.base/'reference.bin';reference.write_bytes(b'one two three')
        class Lease:
            def check(self):pass
        class FTP:
            def retrbinary(self,command,callback,blocksize):
                for part in (b'one ',b'two ',b'three'):callback(part)
        before=set(self.base.iterdir())
        record=installer.m.compare_readback(type('C',(),{'ftp':FTP()})(),'/side/file',reference,Lease())
        self.assertEqual(record['sha256'],q.digest(reference));self.assertEqual(record['bytes'],13)
        self.assertEqual(record['readback_method'],'full_byte_comparison');self.assertEqual(set(self.base.iterdir()),before)

    def test_stream_comparison_rejects_corrupt_short_and_long_console_data(self):
        installer=module('stream_compare_bad',HERE.parents[1]/'port/main-install/install-main.py')
        reference=self.base/'reference.bin';reference.write_bytes(b'expected bytes')
        class Lease:
            def check(self):pass
        for data in (b'wrong bytes',b'expected',b'expected bytes extra'):
            class FTP:
                def retrbinary(self,command,callback,blocksize):callback(data)
            with self.assertRaises(RuntimeError):installer.m.compare_readback(type('C',(),{'ftp':FTP()})(),'/side/file',reference,Lease())

    def test_http_application_error_is_not_a_console_outage(self):
        installer=module('http_status_test',HERE.parents[1]/'port/main-install/install-main.py')
        api=installer.api
        error=api.urllib.error.HTTPError('http://console/route',400,'Bad Request',{},None)
        with patch.object(api.urllib.request,'urlopen',side_effect=error),patch.object(api,'install_guard') as guard_factory:
            with self.assertRaises(api.urllib.error.HTTPError):api.http_text('http://console/route')
            with self.assertRaises(api.urllib.error.HTTPError):api.http_json('/route')
            guard_factory.assert_not_called()

    def test_real_bundle_installer_main_flow_requires_proof_and_preserves_rollback(self):
        raw = self.bundle()
        backups = [data for path, data in raw.files.items() if '.before-' in path]
        self.assertEqual(backups, [self.old.read_bytes()])

    def test_real_bundle_installer_blocks_missing_report_before_connect(self):
        self.clock[0] = time.time()
        doc = q.read_json(self.job); doc.pop('deployment'); self.job.write_text(json.dumps(doc))
        ticket = self.submit(); lease = self.board.claim('owner')
        installer = module('blocked_bundle_installer', HERE.parents[1] / 'port/main-install/install-main.py')
        env = {'CONSOLE_INSTALL_STATE': str(self.root), 'CONSOLE_INSTALL_AGENT': 'owner',
               'CONSOLE_INSTALL_TICKET': ticket, 'CONSOLE_INSTALL_TOKEN': lease['token']}
        with patch.dict(os.environ, env), patch.object(installer.api, 'Console') as connect:
            with self.assertRaises(installer.queue.QueueError):
                installer.bundle_main(['install', '--out', str(self.base / 'blocked'), '--readiness', str(self.ready(ticket)),
                    '--handoff', str(self.write_json('handoff.json', self.handoff())), '--console-ok'])
            connect.assert_not_called()


class MemoryFTP:
    def __init__(self, files):
        self.files = files; self.dirs = {'/data/homebrew', '/data/homebrew/PPSA91762'};self.modes={}
    def storbinary(self, command, source, blocksize, callback):
        data = source.read(); callback(data); self.files[command[5:]] = data
    def retrbinary(self, command, callback, blocksize): callback(self.files[command[5:]])
    def rename(self, old, new):
        self.files[new] = self.files.pop(old)
        if old in self.modes:self.modes[new]=self.modes.pop(old)
    def mkd(self, path): self.dirs.add(path)
    def sendcmd(self, command):
        if command.startswith('SITE CHMOD '):
            _,_,mode,path=command.split(' ',3);self.modes[path]=mode
        return '200 synthetic command'


class MemoryConsole:
    def __init__(self, raw): self.raw = raw; self.ftp = guard.GuardedFTP(raw)
    def sha256(self, path): return q.hashlib.sha256(self.raw.files[path]).hexdigest() if path in self.raw.files else None
    def listing(self, path):
        return sorted({p[len(path) + 1:].split('/')[0] for p in self.raw.files if p.startswith(path + '/')})
    def chmod(self, path, mode): self.ftp.sendcmd('SITE CHMOD ' + mode + ' ' + path)
    def close(self): pass


if __name__ == '__main__': unittest.main(verbosity=2)

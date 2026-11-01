"""PPSA91780 only: offline plan, then declared install/probe/owned close/handoff.

Reuses the canonical installer, transport, bounded readback and close helpers.
No enqueue/claim, payload build, save writes, restore, RMD or registration writes.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import ftplib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import sys
from types import SimpleNamespace

# Standard-library/runtime distribution is measured separately. Project modules
# must come from the reviewed source, never an ad-hoc old worktree .pyc cache.
SOURCE_ONLY_CACHE = Path(__file__).resolve().with_name('source-only-cache-unused')
if SOURCE_ONLY_CACHE.exists():
    raise ValueError('Source-only cache sentinel must not exist')
sys.pycache_prefix = str(SOURCE_ONLY_CACHE)
sys.dont_write_bytecode = True

TITLE = 'PPSA91780'
APP = '/data/homebrew/' + TITLE
SANDBOX = '/mnt/sandbox/' + TITLE + '_000'
DATA = SANDBOX + '/download0'
MOUNT = '/user/app/' + TITLE + '/mount.lnk'
REPORT = re.compile(r'za-save-fs-probe-91780-([0-9]+)-[0-9]+-[0-9]+')
# Root reviewed696→72f25: optional compare-readbacks added, default bounded/defer
# path unchanged. This driver never supplies --compare-readbacks. Repeat the
# existing defer regressions against72f25 before any console execution.
INSTALLER_SHA = '62fff3843658c59dc524808e2384cf9aa9bc56396f3d54ad3ad6b4ec18f62eb7'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def fresh(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None or not -30 <= time.time() - stamp.timestamp() <= 300:
        raise ValueError('Live preparation/backup expired; withdraw and refresh BEFORE enrollment')


def local_evidence(path):
    path = path.resolve()
    if path.drive.upper() != 'C:':
        raise ValueError('Private live readbacks must stay on local C:, never NAS/mapped shares')
    return path


def helpers(config):
    # All executable helpers are pinned before importing any of them.
    root = Path(config['repo']).resolve()
    required = ['port/main-install/install-main.py', 'port/r28b-dlc-dex/install-r28b.py',
                'run_r3.py', 'port/perf-r24/observer/client.py',
                'tools/console-install-queue/console_queue.py',
                'tools/console-install-queue/install_guard.py',
                'port/hebrew-rtl/console-choice.py', 'port/perf-r24/observer/analyze.py']
    pins = config['helper_sha256']
    if set(pins) != set(required):
        raise ValueError('Exact canonical helper pin allowlist required')
    for name in required:
        if sha(root / name) != pins[name]:
            raise ValueError('Helper changed; review outside queue: ' + name)
    if pins[required[0]] != INSTALLER_SHA:
        raise ValueError('Expected reviewed deferred-completion installer')
    return load('fs_probe_canonical_installer', root / required[0])


def context():
    return SimpleNamespace(**globals())


def scoped(config, name):
    if name not in ('preparation', 'failure_cleanup'):
        raise ValueError('Unexpected scoped helper')
    item = config['scoped_helpers'][name]
    path = Path(item['path']).resolve()
    if path != Path(__file__).resolve().with_name(name + '.py') or sha(path) != item['sha256']:
        raise ValueError('Reviewed scoped helper changed')
    return load('fs_' + name, path)


def load_sender(config):
    relative = 'port/hebrew-rtl/console-choice.py'
    path = Path(config['repo']) / relative
    if sha(path) != config['helper_sha256'][relative]:
        raise ValueError('Canonical sender changed before import')
    # Import defines side-QA functions and a separate helper module only. It does
    # not call side_client(), mutate observer title/session, or contact console.
    return load('fs_probe_canonical_websrv', path)


def launch_declared(api, sender, launcher, out):
    """One POST of the exact declared ELF; no retry or alternate transport."""
    source = Path(launcher['path']).resolve()
    if source.name != 'launch.elf' or launcher['remote_path'] != APP + '/launch.elf':
        raise ValueError('Only the declared FS launcher is accepted')
    if sha(source) != launcher['sha256']:
        raise ValueError('Declared local launcher changed')
    try:
        result = sender.send_websrv_payload(source, out, launcher['sha256'], allowed_names=('launch.elf',))
    except urllib.error.HTTPError:
        # A response is an application rejection, never an observed outage.
        raise
    except OSError as error:
        # The reused helper also reads the local ELF/writes a local log. Those
        # filesystem failures are not evidence of a disconnected console.
        if isinstance(error, (urllib.error.URLError, ConnectionError, TimeoutError)):
            api.install_guard().observe_connection('offline', 'HTTP: ' + str(error))
        raise
    if result.get('http_status') != 200 or result.get('payload_sha256') != launcher['sha256']:
        raise RuntimeError('Websrv did not confirm the exact declared ELF')
    return result


def job_scope(job, policy):
    if (job['title_id'] != TITLE or policy['mode'] != 'side_app'
            or job['expected_base'] or len(job['artifacts']) != 9):
        raise ValueError('Only the new nine-file PPSA91780 side bundle is accepted')
    expected = {'eboot.bin', 'launch.elf', 'close-failed-side.elf', 'sce_module/libc.prx', 'sce_sys/param.json',
                'sce_sys/icon0.png', 'sce_sys/pic0.dds', 'sce_sys/pic1.dds', 'sce_sys/snd0.at9'}
    actual = {r['remote_path'][len(APP) + 1:] for r in job['artifacts']}
    if actual != expected or any(not r['remote_path'].startswith(APP + '/') for r in job['artifacts']):
        raise ValueError('Unexpected side artifact or path')


def offline(config):
    installer = helpers(config)
    m, q = installer.m, installer.queue
    jobpath = Path(config['job']['path'])
    q.evidence_file(config['job'], jobpath.parent)
    job = q.normalized_job(jobpath)
    policy = q.install_policy(job, jobpath.parent)
    job_scope(job, policy)
    original = {**job, 'artifacts': [r for r in job['artifacts'] if r['remote_path'] != APP + '/close-failed-side.elf']}
    if q.candidate_hash(original) != config['original_eight_file_sha256']:
        raise ValueError('The original eight-file probe subidentity changed')
    if q.candidate_hash(job) != config['candidate_sha256']:
        raise ValueError('Candidate fingerprint differs')
    q.evidence_file(config['pc_component_proof'], jobpath.parent)
    pc = read(config['pc_component_proof']['path'])
    if pc.get('host_sentinels_unchanged') is not True or pc.get('title_id') != TITLE:
        raise ValueError('Exact host-tested probe component proof required; not whole failed prep proof')
    eboot = next(r for r in job['artifacts'] if r['remote_path'] == APP + '/eboot.bin')
    if eboot['sha256'] != pc.get('eboot_sha256'):
        raise ValueError('Host-tested probe binary differs')
    scoped(config, 'failure_cleanup').manifest(config, context(), installer, job)
    return installer, job, policy


def prepared(config, path, m):
    """Consume real pre-enrollment observations. This does not collect or retime them."""
    p = read(path)
    if p.get('status') != 'PREPARED_NOT_ENQUEUED':
        raise ValueError('Preparation did not finish')
    fresh(p['checked_at'])
    if p.get('console') != m.api.HOST or p.get('game_closed') is not True or p.get('processes') != []:
        raise ValueError('Fresh observed closed-console preparation required')
    if p.get('candidate_sha256') != config['candidate_sha256']:
        raise ValueError('Prepared candidate differs')
    for folder in ('/data/homebrew', '/user/app', '/mnt/sandbox'):
        names = p['listings'][folder]
        if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
            raise ValueError('Actual directory observations required')
        if any(n == TITLE or n.startswith(TITLE + '_') for n in names):
            raise ValueError('Side title/data/registration collision; never adopt it')
    if p.get('mount_link') is not None or p.get('data_root') is not None:
        raise ValueError('New side mount and data must be observed absent')
    m.queue.evidence_file(p['external_handoff'], Path(path).parent)
    m.queue.evidence_file(p['save_backup'], Path(path).parent)
    backup = read(p['save_backup']['path'])
    fresh(backup['at'])
    if not all(backup.get(k) is True for k in ('fresh', 'all_runs', 'double_read_verified')):
        raise ValueError('Historical backup alone is not fresh all-runs evidence')
    if len(backup['runs']) < 18 or len(backup['files']) < 122:
        raise ValueError('Previous18runs/122files must be covered, not silently omitted')
    for row in backup['files']:
        if sha(row['path']) != row['sha256'] or row.get('second_readback_sha256') != row['sha256']:
            raise ValueError('Verified backup file missing/different: ' + row['relative'])
    rows = p['main_readbacks']
    if (len({r['remote_path'] for r in rows}) != len(rows)
            or {r['remote_path'] for r in rows} != set(config['protected_main_paths'])):
        raise ValueError('All exact nine protected main readbacks required')
    m.queue.evidence_file(p['verified_backup'], Path(path).parent)
    _, authorized = scoped(config, 'preparation').validated_backup(config, p['verified_backup']['path'],
                                                context(), SimpleNamespace(m=m, queue=m.queue))
    if backup != authorized:
        raise ValueError('Prepared backup was changed or retimed after the owned backup helper')
    for row in rows:
        if not row['remote_path'].startswith('/data/homebrew/PPSA91762/'):
            raise ValueError('Protected-main readback path differs')
        m.queue.evidence_file(row, Path(path).parent)
    if not any(r['remote_path'] == m.EBOOT and r['sha256'] == config['main_eboot_sha256'] for r in rows):
        raise ValueError('Current main eboot proof absent')
    return p


def prepare_live(args, config, installer):
    return scoped(config, 'preparation').prepare_live(args, config, context(), installer)


def backup_menu(args, config, installer):
    return scoped(config, 'preparation').backup_menu(args, config, context(), installer)


def own(c, identity, m):
    procs = m.api.eboot_processes()
    if len(procs) != 1 or m.api.process_pid(procs[0]) != identity['pid']:
        raise RuntimeError('Own PID changed; no unknown process will be closed')
    param = c.read(SANDBOX + '/app0/sce_sys/param.json', 65536)
    if param is None or hashlib.sha256(param).hexdigest() != identity['param_sha256'] or json.loads(param)['titleId'] != TITLE:
        raise RuntimeError('Owned mounted title changed')
    match = REPORT.fullmatch(identity.get('report_folder', ''))
    if not match or int(match[1]) != identity['pid'] or identity['report_folder'] not in c.listing(DATA):
        raise RuntimeError('Fresh report-directory PID chain is missing')
    if c.sha256(APP + '/eboot.bin') != identity['eboot_sha256']:
        raise RuntimeError('Owned executable changed')
    sandboxes = c.listing('/mnt/sandbox')
    if [n for n in sandboxes if re.match(r'^(PPSA|CUSA|FAKE).+_[0-9]{3}$', n)] != [TITLE + '_000']:
        raise RuntimeError('Another mounted title exists; refuse process control')


def selftest(args, installer):
    """Focused synthetic refusal checks only; canonical PC turn is still required."""
    agent, ticket, token = (os.environ.get('PC_TEST_' + k, '') for k in ('AGENT', 'TICKET', 'TOKEN'))
    if not all((agent, ticket, token)):
        raise ValueError('selftest needs a canonical PC turn; no test was executed')
    installer.queue.Board(resource='pc').check(agent, ticket, token)
    names = ['eboot.bin', 'launch.elf', 'close-failed-side.elf', 'sce_module/libc.prx', 'sce_sys/param.json',
             'sce_sys/icon0.png', 'sce_sys/pic0.dds', 'sce_sys/pic1.dds', 'sce_sys/snd0.at9']
    good = {'title_id': TITLE, 'expected_base': [], 'artifacts': [{'remote_path': APP + '/' + n} for n in names]}
    job_scope(good, {'mode': 'side_app'})
    cases = []
    def reject(name, fn):
        try:
            fn()
        except (RuntimeError, ValueError):
            cases.append({'name': name, 'result': 'passed'})
        else:
            raise AssertionError('Unsafe case was accepted: ' + name)
    reject('protected_main_title', lambda: job_scope({**good, 'title_id': 'PPSA91762'}, {'mode': 'side_app'}))
    badpath = json.loads(json.dumps(good))
    badpath['artifacts'][0]['remote_path'] = '/data/homebrew/PPSA91762/eboot.bin'
    reject('foreign_artifact_path', lambda: job_scope(badpath, {'mode': 'side_app'}))
    param = json.dumps({'titleId': TITLE}).encode()
    identity = {'pid': 123, 'param_sha256': hashlib.sha256(param).hexdigest(),
                'eboot_sha256': 'a' * 64, 'report_folder': 'za-save-fs-probe-91780-123-1-2'}
    class FakeConsole:
        pid, binary, title = 123, 'a' * 64, param
        sandbox = [TITLE + '_000']
        def read(self, *a): return self.title
        def sha256(self, *a): return self.binary
        def listing(self, path): return self.sandbox if path == '/mnt/sandbox' else [identity['report_folder']]
    c = FakeConsole()
    api = SimpleNamespace(eboot_processes=lambda: [{'pid': c.pid}], process_pid=lambda row: row['pid'])
    m = SimpleNamespace(api=api)
    own(c, identity, m)
    cases.append({'name': 'matching_pid_param_eboot_report_chain', 'result': 'passed'})
    c.pid = 999
    reject('foreign_pid', lambda: own(c, identity, m))
    c.pid = 123
    c.title = b'{"titleId":"PPSA91762"}'
    reject('foreign_mounted_param', lambda: own(c, identity, m))
    c.title = param
    reject('report_folder_wrong_pid', lambda: own(c, {**identity, 'report_folder': 'za-save-fs-probe-91780-999-1-2'}, m))
    c.binary = 'b' * 64
    reject('changed_eboot', lambda: own(c, identity, m))
    c.binary = identity['eboot_sha256']
    c.sandbox = [TITLE + '_000', 'PPSA91762_000']
    reject('another_mounted_title', lambda: own(c, identity, m))
    installer.queue.Board(resource='pc').check(agent, ticket, token)
    result = {'result': 'passed', 'kind': 'synthetic_identity_guards_only', 'cases': cases,
              'driver_sha256': sha(__file__), 'installer_sha256': INSTALLER_SHA,
              'console_access': False, 'hardware_tested': False}
    if args.out.exists():
        raise FileExistsError(args.out)
    installer.write(args.out, result)
    return result


def verification(args, installer, config):
    if args.verification is None or not args.verification_sha256 or sha(args.verification) != args.verification_sha256:
        raise ValueError('Reviewed current-driver and current-installer test proof required before console access')
    evidence = read(args.verification)
    if evidence.get('schema') != 'fs-driver-verification-1':
        raise ValueError('Unexpected verification schema')
    for name in ('identity_tests', 'defer_tests', 'transport_tests'):
        installer.queue.evidence_file(evidence[name], args.verification.parent)
    identity = read(evidence['identity_tests']['path'])
    expected = {'protected_main_title', 'foreign_artifact_path', 'matching_pid_param_eboot_report_chain',
                'foreign_pid', 'foreign_mounted_param', 'report_folder_wrong_pid', 'changed_eboot', 'another_mounted_title'}
    if (identity.get('result') != 'passed' or identity.get('driver_sha256') != sha(__file__)
            or identity.get('installer_sha256') != INSTALLER_SHA
            or {r.get('name') for r in identity.get('cases', [])} != expected
            or not all(r.get('result') == 'passed' for r in identity['cases'])):
        raise ValueError('Identity refusal tests do not prove this exact driver')
    defer = read(evidence['defer_tests']['path'])
    if (defer.get('status') != 'PASS' or defer.get('candidate_sha256') != INSTALLER_SHA
            or defer.get('tests') != 3 or defer.get('scenarios') != 4):
        raise ValueError('Current deferred-install regressions have not passed')
    transport = read(evidence['transport_tests']['path'])
    source = config['transport_tests_source']
    installer.queue.evidence_file(source, Path(config['repo']))
    if (transport.get('status') != 'PASS' or transport.get('tests') != 10
            or transport.get('driver_sha256') != sha(__file__)
            or transport.get('sender_sha256') != config['helper_sha256']['port/hebrew-rtl/console-choice.py']
            or transport.get('test_sha256') != source['sha256'] or transport.get('console_access') is not False):
        raise ValueError('Exact current single-POST transport tests have not passed')
    for field in ('stdout', 'stderr'):
        installer.queue.evidence_file(transport[field], args.verification.parent)
    for key, module in (('preparation_tests', 'preparation'), ('cleanup_tests', 'failure_cleanup')):
        installer.queue.evidence_file(evidence[key], args.verification.parent)
        checked = read(evidence[key]['path'])
        if (checked.get('status') != 'PASS' or checked.get('driver_sha256') != sha(__file__)
                or checked.get('helper_sha256') != config['scoped_helpers'][module]['sha256']
                or checked.get('tests') != config['new_test_counts'][key]
                or checked.get('backup_helper_sha256') != config['helper_sha256']['port/r28b-dlc-dex/install-r28b.py']
                or checked.get('console_access') is not False):
            raise ValueError('Current preparation/cleanup safety checks have not passed')
        for field in ('stdout', 'stderr'):
            installer.queue.evidence_file(checked[field], args.verification.parent)




def execute(args, config, installer, job):
    m, q, api = installer.m, installer.queue, installer.api
    if not args.console_ok or not all((args.prepared, args.readiness, args.handoff)):
        raise ValueError('run requires coordinated --console-ok and prepared/readiness/handoff')
    if os.environ.get('CONSOLE_INSTALL_STATE'):
        raise ValueError('Use the canonical production queue only')
    agent, ticket, token = (os.environ.get('CONSOLE_INSTALL_' + k, '') for k in ('AGENT', 'TICKET', 'TOKEN'))
    if not all((agent, ticket, token)):
        raise ValueError('A coordinated active canonical console lease is required')
    board = q.Board()
    _, row = board.authenticate(board.load(), agent, ticket, token)
    timing = board.check(agent, ticket, token)
    if timing.get('seconds_to_yield') is not None and timing['seconds_to_yield'] < 240:
        raise ValueError('Prepared240second execution/cleanup budget does not fit; no console operation started')
    if row['job']['title_id'] != TITLE or q.candidate_hash(row['job']) != config['candidate_sha256']:
        raise ValueError('Active immutable job is not this prepared side candidate')
    prep = prepared(config, args.prepared, m)
    if prep.get('previous_main_handoff') != board.load().get('baselines', {}).get('PPSA91762'):
        raise ValueError('Main resource handoff changed while waiting; withdraw/merge/refresh outside queue')
    ready = read(args.readiness)
    if ready['save_backup'].get('evidence') != prep['save_backup']:
        raise ValueError('Readiness must bind the same fresh pre-enrollment backup')
    out = local_evidence(args.out)
    out.mkdir(parents=True, exist_ok=False)
    m.AGENT = agent
    # Lease/token are deliberately outside evidence and source-deliverable directories.
    with tempfile.TemporaryDirectory(prefix='za-fs-91780-private-') as private:
        state = Path(private)
        m.write(state / '.lease.json', {'ticket': ticket, 'token': token})
        with m.Lease(state) as lease:
            c = api.Console()
            identity, capture, receipt = None, None, None
            result = {'title': TITLE, 'at': api.utc_now(), 'result': 'INCOMPLETE', 'hardware_safe': False}
            try:
                m.idle()
                # Short time-of-use refusal checks; no backup/setup work in this turn.
                if TITLE in c.listing('/data/homebrew') or TITLE in c.listing('/user/app') or c.read(MOUNT, 4096) is not None:
                    raise RuntimeError('Side target/registration appeared after preparation')
                if any(n.startswith(TITLE + '_') for n in c.listing('/mnt/sandbox')):
                    raise RuntimeError('Side data/mount appeared after preparation')
                c.close(); c = None
                installer.bundle_main(['install', '--out', str(out / 'install'), '--readiness', str(args.readiness),
                                       '--handoff', str(args.handoff), '--console-ok', '--defer-complete'])
                receipt = m.read(out / 'install/receipt.json')
                c = api.Console()
                deadline = time.monotonic() + 55
                while True:
                    lease.check()
                    link = c.read(MOUNT, 4096)
                    if link is not None:
                        if link.decode('utf-8').rstrip('\r\n') != APP:
                            raise RuntimeError('Registration points elsewhere')
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Automatic ShadowMount registration did not arrive within55s')
                    time.sleep(2)
                m.idle()
                if any(re.match(r'^(PPSA|CUSA|FAKE).+_[0-9]{3}$', n) for n in c.listing('/mnt/sandbox')):
                    raise RuntimeError('A title sandbox appeared before launch; no automatic folder cleanup')
                before = set(c.listing(DATA)) if TITLE + '_000' in c.listing('/mnt/sandbox') else set()
                capture = api.KlogCapture(out / 'probe.klog.log', backlog_seconds=0)
                capture.start()
                wait_capture = time.monotonic() + 6
                while not capture.connected and capture.error is None and time.monotonic() < wait_capture:
                    lease.check()
                    time.sleep(.1)
                if not capture.connected:
                    raise RuntimeError('Passive klog capture failed before launcher: ' + str(capture.error))
                lease.check()
                # Exact declared prebuilt launcher only; no payload upload/registration writes.
                launcher = next(r for r in job['artifacts'] if r['remote_path'] == APP + '/launch.elf')
                if c.sha256(launcher['remote_path']) != launcher['sha256']:
                    raise RuntimeError('Declared launcher changed')
                sender = load_sender(config)
                lease.check()
                m.idle()
                if c.read(APP + '/launch.log', 65536) is not None:
                    raise RuntimeError('Unexpected old FS launcher log; no launch')
                startup_offset = (out / 'probe.klog.log').stat().st_size
                result['startup_offset'] = startup_offset
                result['launch_response'] = launch_declared(api, sender, launcher, out)
                deadline = time.monotonic() + 60
                report = None
                while time.monotonic() < deadline:
                    lease.check()
                    procs = api.eboot_processes()
                    param = c.read(SANDBOX + '/app0/sce_sys/param.json', 65536)
                    if procs and len(procs) != 1:
                        raise RuntimeError('Multiple/unknown processes after launch')
                    if len(procs) == 1 and param is not None and json.loads(param).get('titleId') == TITLE:
                        pin = next(r['sha256'] for r in job['artifacts'] if r['remote_path'] == APP + '/sce_sys/param.json')
                        if hashlib.sha256(param).hexdigest() != pin:
                            raise RuntimeError('Mounted param differs from declared title')
                        candidate = {'pid': api.process_pid(procs[0]), 'param_sha256': pin,
                                     'eboot_sha256': next(r['sha256'] for r in job['artifacts'] if r['remote_path'] == APP + '/eboot.bin')}
                        if identity is not None and candidate['pid'] != identity['pid']:
                            raise RuntimeError('Launched identity changed')
                        try:
                            report_names = c.listing(DATA)
                        except ftplib.error_perm as error:
                            result['pending_data_listing_error'] = str(error)
                            report_names = []
                        for name in report_names:
                            match = REPORT.fullmatch(name)
                            if not match or name in before or int(match[1]) != candidate['pid']:
                                continue
                            identity = {**candidate, 'report_folder': name}
                            own(c, identity, m)
                            m.write(out / 'identity.json', identity)
                            raw = c.read(DATA + '/' + name + '/report.json', 1 << 20)
                            if not raw:
                                continue
                            try:
                                candidate_report = json.loads(raw)
                            except ValueError:  # The probe publishes an append-only in-progress file.
                                continue
                            if candidate_report.get('schema') != 'za-save-fs-probe-1' or candidate_report.get('title') != TITLE or candidate_report.get('mode') != 'native-side-title':
                                raise RuntimeError('Fresh report identity/schema differs')
                            if candidate_report.get('game_access') is not False or candidate_report.get('recursive_cleanup') is not False:
                                raise RuntimeError('Probe reports forbidden game access/cleanup')
                            if not isinstance(candidate_report.get('rows'), list) or not candidate_report['rows']:
                                raise RuntimeError('Probe report has no actual observations')
                            (out / 'report.json').write_bytes(raw)
                            result['remote_report'] = DATA + '/' + name + '/report.json'
                            report = candidate_report
                            break
                    if report is not None:
                        break
                    time.sleep(1)
                if report is None:
                    # Recognize only the proved same-platform PRX failure. The
                    # absence of a report alone never authorizes process control.
                    failure = scoped(config, 'failure_cleanup')
                    failed_identity = failure.identify(c, config, context(), installer, job, out, startup_offset)
                    failure.close(c, config, context(), installer, job, failed_identity, lease, out)
                    result['failed_launch_closed'] = True
                    identity = None
                    raise RuntimeError('Known PRX load failed; exact owned side app closed; FS APIs untested')
                counts = Counter(r.get('result', 'MISSING_RESULT') for r in report['rows'])
                unsafe = report.get('sentinels_unchanged') is not True or any('UNSAFE' in k for k in counts)
                unsupported = any('UNSUPPORTED' in k or 'DENIED' in k for k in counts)
                result.update(result='UNSAFE' if unsafe else 'OBSERVED_WITH_UNSUPPORTED_OR_DENIED' if unsupported else 'OBSERVED_NOT_A_GENERAL_SAFETY_PROOF',
                              row_results=dict(counts), sentinels_unchanged=report.get('sentinels_unchanged'))
            except Exception as error:
                result['error'] = str(error)
            finally:
                if c is not None and identity is not None:
                    # Reuse established kill/poll20s implementation with only its identity callback adapted.
                    original_owned = m.owned
                    m.owned = lambda console, ident: own(console, ident, m)
                    try:
                        m.close_owned(c, identity, lease, out, 'probe')
                    except Exception as error:
                        result['owned_close_error'] = str(error)
                    finally:
                        m.owned = original_owned
                if capture is not None:
                    capture.stop()
                if c is not None:
                    c.close()
            m.write(out / 'result.json', result)
            if receipt is None:
                raise RuntimeError('Install incomplete; retain lease and transaction evidence, no fabricated completion')
            m.idle()
            # Every immutable side file is read again after own application closes.
            c = api.Console()
            try:
                final = []
                receipts_by_path = {r['remote_path']: r for r in receipt['readbacks']}
                for index, artifact in enumerate(job['artifacts']):
                    rec = m.bounded_file(c, artifact['remote_path'], out / ('final-side-%02d.bin' % index), lease)
                    if rec['sha256'] != artifact['sha256']:
                        raise RuntimeError('Immutable side file changed; do not complete')
                    final.append({'remote_path': artifact['remote_path'], 'evidence': m.proof(rec['path'])})
                    receipts_by_path[artifact['remote_path']]['installed'] = m.proof(rec['path'])
                protected = []
                for index, old in enumerate(prep['main_readbacks']):
                    rec = m.bounded_file(c, old['remote_path'], out / ('final-main-%02d.bin' % index), lease)
                    if rec['sha256'] != old['sha256']:
                        raise RuntimeError('Main changed; no automatic restore or false handoff')
                    protected.append({'remote_path': old['remote_path'], **m.proof(rec['path'])})
                m.idle()
                # Existing backup files remain verified; this probe never launched MAIN or wrote its data.
                q.evidence_file(prep['save_backup'], args.prepared.parent)
                for backup_row in read(prep['save_backup']['path'])['files']:
                    lease.check()
                    if sha(backup_row['path']) != backup_row['sha256']:
                        raise RuntimeError('Backup bytes changed before final handoff')
                m.write(out / 'final-manifest.json', {'at': api.utc_now(), 'side_files': final,
                        'main_unchanged_readbacks': protected, 'game_closed': True, 'probe_result': m.proof(out / 'result.json'),
                        'save_backup': prep['save_backup'], 'scope': 'PPSA91780 only; no main/vanilla/save writes; untested APIs never inferred safe'})
                receipt['console_handoff_complete'] = True
                receipt['baseline_handoff'].update(readbacks=final, manifest=m.proof(out / 'final-manifest.json'))
                m.write(out / 'receipt.json', receipt)
                lease.heartbeat()
                m.emit(board.complete(agent, ticket, token, out / 'receipt.json'))
            finally:
                c.close()
            return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=('plan', 'selftest', 'prepare-live', 'backup-menu', 'run'))
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--config-sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--prepared', type=Path)
    p.add_argument('--verified-backup', type=Path)
    p.add_argument('--owned-menu-close-ok', action='store_true')
    p.add_argument('--coordination', type=Path)
    p.add_argument('--readiness', type=Path)
    p.add_argument('--handoff', type=Path)
    p.add_argument('--verification', type=Path)
    p.add_argument('--verification-sha256')
    p.add_argument('--console-ok', action='store_true')
    args = p.parse_args()
    if sha(args.config) != args.config_sha256:
        raise ValueError('Reviewed configuration changed')
    config = read(args.config)
    if sha(__file__) != config['driver_sha256']:
        raise ValueError('Reviewed driver changed')
    installer, job, policy = offline(config)
    if args.operation in ('prepare-live', 'backup-menu', 'run'):
        verification(args, installer, config)
    if args.operation == 'plan':
        if args.out.exists():
            raise FileExistsError(args.out)
        result = {**policy, 'files': 9, 'console_access': False, 'enqueue_performed': False,
                  'live_preparation_validated': False, 'status': 'OFFLINE_ARTIFACTS_READY_ONLY',
                  'budgets_seconds': {'automatic_registration': 55, 'probe_report': 60, 'owned_close': 20,
                                      'total_with_install_readbacks_and_handoff': 240},
                  'required_before_enrollment': ['fresh closed/side-collision observations', 'fresh double verified all-runs backup',
                                               'actual protected-main readbacks', 'external coordinated handoff', 'prepared/readiness/handoff JSON'],
                  'prohibitions': ['no unknown close', 'no unsupported→safe inference', 'no main/vanilla/save writes',
                                   'no automatic rollback over changed state', 'no cleanup of unknown folders'],
                  'next_command': 'zw save-fs-console run --config CONFIG --config-sha256 SHA --prepared PREPARED --readiness READINESS --handoff HANDOFF --out NEW --console-ok'}
        installer.write(args.out, result)
    elif args.operation == 'selftest':
        result = selftest(args, installer)
    elif args.operation == 'prepare-live':
        result = prepare_live(args, config, installer)
    elif args.operation == 'backup-menu':
        result = backup_menu(args, config, installer)
    else:
        result = execute(args, config, installer, job)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

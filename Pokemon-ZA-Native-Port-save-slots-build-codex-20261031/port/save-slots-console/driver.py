"""DRAFT PPSA91781 physical-controller test observer. Not install-ready.

Never installs, injects controller/mailbox commands, writes saves, registers a
baseline, enqueues or releases a resource. Root owns the separately prepared
canonical install-only step and the final inspected handoff.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error

TITLE = 'PPSA91781'
APP = '/data/homebrew/' + TITLE
SANDBOX = '/mnt/sandbox/' + TITLE + '_000'
RUN_ROOT = SANDBOX + '/download0/zarecomp/rando'
EBOOT_SHA = '81e264c8991f5ba86870a7fd89fe13765a07eb0ae9f240047ccea656baaf25fe'
PARAM_SHA = 'ef08948495c2f469b3f9c4edc3a023743ac608eccdd46aaeaf617274c7928c6a'
HELPERS = ('port/main-install/install-main.py', 'port/r28b-dlc-dex/install-r28b.py',
           'run_r3.py', 'port/perf-r24/observer/client.py', 'port/perf-r24/observer/analyze.py',
           'tools/console-install-queue/console_queue.py', 'tools/console-install-queue/install_guard.py',
           'port/hebrew-rtl/console-choice.py')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def components(config):
    """Pin all project code before dynamic imports; no old worktree fallback."""
    root = Path(config['repo']).resolve()
    if os.environ.get('CONSOLE_INSTALL_STATE') or os.environ.get('PC_TEST_STATE'):
        raise ValueError('Private queue state overrides are forbidden')
    if set(config['helper_sha256']) != set(HELPERS):
        raise ValueError('Exact canonical project import closure required')
    for name in HELPERS:
        if sha(root / name) != config['helper_sha256'][name]:
            raise ValueError('Canonical source changed; review and refresh outside queue: ' + name)
    here = Path(__file__).resolve().parent
    cache_prefix = here / '.source-only-no-bytecode-consumption'
    if cache_prefix.exists():
        raise ValueError('Source-only cache prefix must remain absent')
    sys.pycache_prefix = str(cache_prefix)
    sys.dont_write_bytecode = True
    if set(config['local_source_sha256']) != {'driver.py', 'slot_format.py', 'observations.py'}:
        raise ValueError('Exact watcher source closure required')
    for name, expected in config['local_source_sha256'].items():
        if sha(here / name) != expected:
            raise ValueError('Watcher source changed: ' + name)
    # This selects only host read paths. It is not a native environment bridge.
    if os.environ.get('ZA_OBSERVER_TITLE') not in (None, TITLE):
        raise ValueError('Inherited foreign observer target')
    os.environ['ZA_OBSERVER_TITLE'] = TITLE
    installer = load('slots_canonical_installer', root / HELPERS[0])
    if installer.m.observer.TITLE != TITLE or installer.m.observer.COMMAND != APP + '/observer-command.txt':
        raise ValueError('Canonical observer import is not confined to the side title')
    return (installer, load('slots_format', here / 'slot_format.py'),
            load('slots_observations', here / 'observations.py'))


def check_input(args, config):
    if sha(args.input_check) != args.input_check_sha256:
        raise ValueError('Reviewed scoped input-check changed')
    record = read(args.input_check)
    if (record.get('status') != 'READY_FOR_SCOPED_BUILD' or record.get('allowed_to_start') is not True
            or record.get('operation') != 'existing-81e2-python-watcher'
            or record.get('config_sha256') != sha(args.config)):
        raise ValueError('Scoped closure is not ready for this exact configuration')
    if sha(Path(config['repo']) / 'docs/testing/BUILD_DEPENDENCY_MAP.json') != record['map_sha256']:
        raise ValueError('Dependency map changed; refresh outside queue before execution')
    for row in record['runtime_files']:
        if sha(row['path']) != row['sha256']:
            raise ValueError('Python runtime/transitive stdlib input changed')


def baseline_scope(board, q, row, config):
    state = board.load()
    registered = state.get('baselines', {}).get(TITLE)
    if sha(config['full_bundle']['path']) != config['full_bundle']['sha256']:
        raise ValueError('Existing full runtime bundle manifest changed')
    # normalized_job rehashes every game input. Existing PC proof owns those
    # expensive identities; a per-poll guard reads only the pinned manifest.
    full = read(config['full_bundle']['path'])
    wanted = {r['remote_path']: r['sha256'] for r in full['artifacts']}
    core = {**full, 'artifacts': [r for r in full['artifacts'] if r['remote_path'] != config['cleanup']['remote_path']]}
    if (full['title_id'] != TITLE or len(wanted) != 1713 or full['expected_base']
            or len(core['artifacts']) != 1712
            or q.candidate_hash(core) != '09acf28cb67135e8f753901bdce2be14fb038c714e9a4b902e3b5b18b9eaf606'
            or wanted.get(config['cleanup']['remote_path']) != config['cleanup']['sha256']
            or config['cleanup']['remote_path'] != APP + '/close-failed-side.elf'
            or wanted.get(APP + '/eboot.bin') != EBOOT_SHA
            or wanted.get(APP + '/sce_sys/param.json') != PARAM_SHA
            or not registered or registered['files'] != wanted):
        raise ValueError('Exact1712-file core plus own cleanup helper must be fully installed/registered before UX testing')
    if row['job']['title_id'] != TITLE:
        raise ValueError('Active immutable test job has another title')
    if {r['remote_path']: r['sha256'] for r in row['job']['expected_base']} != wanted:
        raise ValueError('UX job must preserve the complete current side baseline')
    actual = {r['remote_path']: r['sha256'] for r in row['job']['artifacts']}
    expected = {p: wanted[p] for p in (APP + '/eboot.bin', APP + '/sce_sys/param.json')}
    if actual != expected:
        raise ValueError('UX job may only declare the real eboot/param identity pair; no bundle upload here')
    board.check_baseline(state, row)
    main = state.get('baselines', {}).get('PPSA91762')
    if main is None or main['files'].get('/data/homebrew/PPSA91762/eboot.bin') != config['main_eboot_sha256']:
        raise ValueError('Protected MAIN baseline changed; withdraw and refresh')
    q.evidence_file(registered['manifest'], Path(config['repo']))
    return registered


def full_readback(args, config, m, c, check):
    """Actual remote byte comparison of ALL1712+cleanup immutable files.

    No new baseline, no upload, no duplicate GB-sized evidence. The manifest
    states streaming comparison and references the installed baseline honestly.
    """
    m.idle()
    rows = []
    for artifact in read(config['full_bundle']['path'])['artifacts']:
        check()
        compare_lease = type('ReadLease', (), {'check': staticmethod(check)})()
        result = m.compare_readback(c, artifact['remote_path'], artifact['path'], compare_lease)
        if result['sha256'] != artifact['sha256']:
            raise RuntimeError('Installed immutable side file differs; retain lease for safe reconciliation')
        rows.append(result)
    m.idle()
    return {'schema': 'slots-full-immutable-readback-1', 'title': TITLE, 'checked_at': m.api.utc_now(),
            'full_bundle': config['full_bundle'], 'files': rows, 'game_closed': True,
            'method': 'All remote bytes streamed and compared with exact pinned local artifacts',
            'scope': 'side app only; no baseline registration or MAIN promotion'}


def safe_output(path):
    path = path.resolve()
    if path.drive.upper() != 'C:' or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Private runtime evidence must stay on local C without symlink escapes')
    path.mkdir(parents=True, exist_ok=False)
    return path


def consume_preflight(args, config, installer, board, row):
    """Consume preparation, never perform/retime backups while queued."""
    q = installer.queue
    q.evidence_file({'path': str(args.prepared), 'sha256': args.prepared_sha256}, args.prepared.parent)
    prepared = read(args.prepared)
    if (prepared.get('schema') != 'slots-pre-enrollment-1'
            or prepared.get('status') != 'PREPARED_NOT_ENQUEUED'
            or prepared.get('title') != TITLE or prepared.get('game_closed') is not True
            or prepared.get('processes') != []):
        raise ValueError('Actual complete closed-console preparation required before enrollment')
    checked = datetime.fromisoformat(prepared['checked_at'].replace('Z', '+00:00'))
    if checked.tzinfo is None or not -5 <= row['enqueued_at'] - checked.timestamp() <= 300:
        raise ValueError('Preparation must be fresh BEFORE enrollment; no refresh while queued')
    main = board.load().get('baselines', {}).get('PPSA91762')
    if hashlib.sha256(q.canonical(main)).hexdigest() != prepared['main_handoff_sha256']:
        raise ValueError('MAIN handoff changed after preparation')
    q.evidence_file(prepared['all_side_readbacks'], args.prepared.parent)
    proof = read(prepared['all_side_readbacks']['path'])
    wanted = {r['remote_path']: r['sha256'] for r in read(config['full_bundle']['path'])['artifacts']}
    observed = {r['remote_path']: r['sha256'] for r in proof['files']}
    if (proof.get('schema') != 'slots-full-immutable-readback-1' or proof.get('title') != TITLE
            or proof.get('game_closed') is not True or observed != wanted
            or len(proof['files']) != len(wanted) or proof.get('full_bundle') != config['full_bundle']
            or not all(r.get('readback_method') == 'full_byte_comparison' for r in proof['files'])):
        raise ValueError('All1712 core files plus cleanup need actual pre-enrollment byte comparisons')
    proof_at = datetime.fromisoformat(proof['checked_at'].replace('Z', '+00:00'))
    if proof_at.tzinfo is None or not 0 <= checked.timestamp() - proof_at.timestamp() <= 300:
        raise ValueError('Full side readback must itself be fresh, not a retimed historical manifest')
    q.evidence_file(prepared['save_backup'], args.prepared.parent)
    backup = read(prepared['save_backup']['path'])
    backup_at = datetime.fromisoformat(backup['at'].replace('Z', '+00:00'))
    if backup_at.tzinfo is None or not 0 <= checked.timestamp() - backup_at.timestamp() <= 300:
        raise ValueError('Backup observation itself must be fresh before enrollment')
    if not all(backup.get(k) is True for k in ('fresh', 'all_runs', 'double_read_verified')):
        raise ValueError('Actual fresh complete double-read all-runs backup required')
    if not backup.get('files') or len({r['relative'] for r in backup['files']}) != len(backup['files']):
        raise ValueError('Backup must cover a complete unique actual file inventory')
    for entry in backup['files']:
        if sha(entry['path']) != entry['sha256'] or entry['second_readback_sha256'] != entry['sha256']:
            raise ValueError('Verified private backup bytes unavailable/changed')
    q.evidence_file(config['fs_required_api_verdict'], Path(config['repo']))
    verdict = read(config['fs_required_api_verdict']['path'])
    if (verdict.get('status') != 'REQUIRED_SLOT_APIS_OBSERVED_PASS'
            or verdict.get('tested_title') != 'PPSA91780'
            or verdict.get('sentinels_unchanged') is not True):
        raise ValueError('FS required-API hardware verdict not ready; unsupported never means safe')
    return prepared


def launch(args, config, installer, lease, c, out, check):
    m, api = installer.m, installer.api
    check()
    if api.eboot_processes():
        raise RuntimeError('A game is running; no launch or unknown process control')
    if any(re.fullmatch(r'(?:PPSA|CUSA|FAKE).+_[0-9]{3}', n) for n in c.listing('/mnt/sandbox')):
        raise RuntimeError('An existing sandbox prevents launcher; never remove it automatically')
    link = c.read('/user/app/' + TITLE + '/mount.lnk', 4096)
    if link is None or link.decode('utf-8', errors='strict').rstrip('\r\n') != APP:
        raise RuntimeError('Automatic side-title registration does not point to own app')
    check()
    if c.sha256(APP + '/eboot.bin') != EBOOT_SHA:
        raise RuntimeError('Installed exact target changed')
    check()
    sender = load('slots_canonical_sender', Path(config['repo']) / 'port/hebrew-rtl/console-choice.py')
    launcher = config['launcher']
    path = Path(launcher['path']).resolve()
    if (path.name != 'launch.elf' or launcher['remote_path'] != APP + '/launch.elf'
            or sha(path) != launcher['sha256'] or c.sha256(launcher['remote_path']) != launcher['sha256']):
        raise ValueError('Exact declared prebuilt own-title launcher required')
    check()
    try:
        response = sender.send_websrv_payload(path, out, launcher['sha256'], allowed_names=('launch.elf',))
    except urllib.error.HTTPError:
        raise
    except OSError as error:
        if isinstance(error, (urllib.error.URLError, ConnectionError, TimeoutError)):
            api.install_guard().observe_connection('offline', 'HTTP: ' + str(error))
        raise
    if response.get('http_status') != 200 or response.get('payload_sha256') != launcher['sha256']:
        raise RuntimeError('No exact launcher success; no alternate transport/retry')
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        check()
        procs = api.eboot_processes()
        raw = c.read(SANDBOX + '/app0/sce_sys/param.json', 65536)
        if len(procs) > 1:
            raise RuntimeError('Unknown/multiple processes after own launcher')
        if len(procs) == 1 and raw is not None:
            if hashlib.sha256(raw).hexdigest() != PARAM_SHA or json.loads(raw).get('titleId') != TITLE:
                raise RuntimeError('Actual mounted title differs')
            receipt = {'schema': 'slots-owned-launch-1', 'title': TITLE, 'pid': api.process_pid(procs[0]),
                       'ticket': os.environ['CONSOLE_INSTALL_TICKET'], 'before_processes': [],
                       'eboot_sha256': EBOOT_SHA, 'param_sha256': PARAM_SHA,
                       'driver_sha256': sha(__file__), 'launched_at': api.utc_now(), 'transport': response,
                       'session_pending_until_first_run': True}
            m.write(out / 'launch.json', receipt)
            return receipt
        time.sleep(1)
    raise RuntimeError('No unique own mounted process within60s; retain ownership, physical safe-close if identity is ambiguous')


def acquire(args, m, c, out, check, obs):
    m.queue.evidence_file({'path': str(args.launch_receipt), 'sha256': args.launch_sha256}, args.launch_receipt.parent)
    receipt = read(args.launch_receipt)
    if (receipt.get('schema') != 'slots-owned-launch-1' or receipt.get('driver_sha256') != sha(__file__)
            or receipt.get('ticket') != os.environ['CONSOLE_INSTALL_TICKET']
            or receipt.get('title') != TITLE or receipt.get('before_processes') != []):
        raise ValueError('Fresh exact-driver launch chain in this active test turn required')
    check()
    info = m.observer.status(c.ftp)
    identity = {**receipt, 'session': info['session']}
    obs.own(c, identity, m, check)
    m.write(out / 'identity.json', identity)
    return identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=('launch', 'list', 'snapshot', 'writer', 'close', 'final-baseline'))
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--config-sha256', required=True)
    p.add_argument('--input-check', type=Path, required=True)
    p.add_argument('--input-check-sha256', required=True)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--prepared-sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--launch-receipt', type=Path)
    p.add_argument('--launch-sha256')
    p.add_argument('--run')
    p.add_argument('--before', type=Path)
    p.add_argument('--before-sha256')
    p.add_argument('--seconds', type=int, default=90)
    p.add_argument('--console-ok', action='store_true')
    args = p.parse_args()
    if not args.console_ok or sha(args.config) != args.config_sha256:
        raise ValueError('Coordinated console authorization and exact reviewed config required')
    config = read(args.config)
    check_input(args, config)
    installer, fmt, obs = components(config)
    m, q = installer.m, installer.queue
    agent, ticket, token = (os.environ.get('CONSOLE_INSTALL_' + k, '') for k in ('AGENT', 'TICKET', 'TOKEN'))
    if not all((agent, ticket, token)):
        raise ValueError('Active canonical coordinated console turn required')
    board = q.Board()
    _, row = board.authenticate(board.load(), agent, ticket, token)
    baseline_scope(board, q, row, config)
    consume_preflight(args, config, installer, board, row)
    if args.operation not in ('launch', 'final-baseline') and not all((args.launch_receipt, args.launch_sha256)):
        raise ValueError('Exact fresh own-launch proof required')
    if args.operation in ('snapshot', 'writer'):
        obs.run_id(args.run)
    if args.operation == 'writer' and (not all((args.before, args.before_sha256)) or not 5 <= args.seconds <= 120):
        raise ValueError('Actual pre-Save snapshot and bounded5..120s writer phase required')
    out = safe_output(args.out)
    m.AGENT = agent
    with tempfile.TemporaryDirectory(prefix='za-slots-private-') as private:
        m.write(Path(private) / '.lease.json', {'ticket': ticket, 'token': token})
        with m.Lease(Path(private)) as lease:
            def check():
                lease.check()
                remaining = board.check(agent, ticket, token).get('seconds_to_yield')
                if args.operation != 'close' and remaining is not None and remaining < 45:
                    raise RuntimeError('Stop new work:45s reserved for proven OWNclose and inspected handoff')
                baseline_scope(board, q, row, config)
            c = m.api.Console()
            try:
                check()
                if args.operation == 'final-baseline':
                    result = full_readback(args, config, m, c, check)
                elif args.operation == 'launch':
                    result = launch(args, config, installer, lease, c, out, check)
                else:
                    identity = acquire(args, m, c, out, check, obs)
                    if args.operation == 'close':
                        original = m.owned
                        m.owned = lambda console, ident: obs.own(console, ident, m, lease.check)
                        try:
                            m.close_owned(c, identity, lease, out, 'slots')
                        finally:
                            m.owned = original
                        result = {'result': 'OWN_PROCESS_CLOSED', 'hardware_safe_handoff': 'REQUIRES_ROOT_INSPECTION'}
                    elif args.operation == 'list':
                        result = obs.run_inventory(c, m, check)
                    else:
                        capture = None
                        if args.operation == 'writer':
                            q.evidence_file({'path': str(args.before), 'sha256': args.before_sha256}, args.before.parent)
                            capture = m.api.KlogCapture(out / 'fresh-writer.klog.log', backlog_seconds=0)
                            capture.start()
                            try:
                                connecting = time.monotonic() + 6
                                while not capture.connected and capture.error is None and time.monotonic() < connecting:
                                    check()
                                    time.sleep(.1)
                                if not capture.connected:
                                    raise RuntimeError('No writer capture connection before physical Save')
                                print(json.dumps({'state': 'READY_FOR_PHYSICAL_IN_GAME_SAVE', 'seconds': args.seconds,
                                                  'run': args.run, 'title': TITLE}), flush=True)
                                deadline = time.monotonic() + args.seconds
                                while time.monotonic() < deadline:
                                    check()
                                    if capture.error:
                                        raise RuntimeError('Writer klog failed: ' + str(capture.error))
                                    time.sleep(.5)
                            finally:
                                capture.stop()
                            if not capture.connected or capture.error:
                                raise RuntimeError('No fresh connected writer capture')
                        obs.own(c, identity, m, check)
                        result, private_bytes = obs.run_snapshot(c, args.run, fmt.parse_slot, check)
                        result['inventory'] = obs.run_inventory(c, m, check)
                        if result['inventory']['active'] != args.run:
                            raise ValueError('Snapshot is not the actually selected active run')
                        for name, raw in private_bytes.items():
                            (out / ('PRIVATE-' + name)).write_bytes(raw)
                        m.write(out / 'snapshot.json', result)
                        if args.operation == 'writer':
                            result = obs.writer_roundtrip(read(args.before), result,
                                        (out / 'fresh-writer.klog.log').read_text(encoding='utf-8', errors='strict'))
                m.write(out / 'result.json', result)
                # No test result can complete/release a resource or promote MAIN.
                print(json.dumps(result, ensure_ascii=False))
            except Exception as error:
                m.write(out / 'FAILED.json', {'title': TITLE, 'error': str(error),
                        'queue_released': False, 'handoff_confirmed': False,
                        'next': 'Retain canonical ownership; close only proven own process and inspect safe handoff'})
                raise
            finally:
                c.close()


if __name__ == '__main__':
    main()

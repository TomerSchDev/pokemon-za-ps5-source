"""FS-only pre-enrollment preparation using existing console and backup APIs.

No install, launch, mount, observer mailbox command, save write or queue claim.
The sole mutation is closing an explicitly authorized, freshly identified main
menu after the existing all-runs backup has verified every file.
"""
import ftplib
import json
import os
from pathlib import Path
import re
import time


def connection(installer):
    m, q = installer.m, installer.queue
    if any(os.environ.get('CONSOLE_INSTALL_' + k) for k in ('AGENT', 'TICKET', 'TOKEN', 'STATE')):
        raise ValueError('Pre-enrollment preparation must not inherit a console lease')
    board = q.Board()
    def check():
        if board.load().get('active') is not None:
            raise RuntimeError('Console owner appeared; stop coordinated preparation')
    class PreparationLease:
        def check(self):
            check()
        def heartbeat(self, *args):
            check()
        def authorize_install(self):
            raise RuntimeError('Preparation never authorizes installation')
    check()
    c = m.api.Console()
    original_json, original_close = m.api.http_json, c.close
    def guarded_json(*args, **kwargs):
        check()
        result = original_json(*args, **kwargs)
        check()
        return result
    def close():
        try:
            original_close()
        finally:
            if m.api.http_json is guarded_json:
                m.api.http_json = original_json
    m.api.http_json, c.close = guarded_json, close
    retr, mlsd, cwd = c.ftp.retrbinary, c.ftp.mlsd, c.ftp.cwd
    def guarded_retr(command, callback, *args, **kwargs):
        check()
        def chunk(data):
            check()
            callback(data)
        result = retr(command, chunk, *args, **kwargs)
        check()
        return result
    def guarded_mlsd(*args, **kwargs):
        check()
        for row in mlsd(*args, **kwargs):
            check()
            yield row
        check()
    def guarded_cwd(*args, **kwargs):
        check()
        result = cwd(*args, **kwargs)
        check()
        return result
    c.ftp.retrbinary, c.ftp.mlsd, c.ftp.cwd = guarded_retr, guarded_mlsd, guarded_cwd
    return c, board, check, PreparationLease()


def coordination(args, driver, *, menu=False):
    if not args.console_ok or args.coordination is None:
        raise ValueError('Actual coordinated human handoff required')
    record = driver.read(args.coordination)
    if record.get('approved_by') != 'Tomer' or not record.get('quote') or record.get('game_closed') is not True:
        raise ValueError('Known closed entry-state handoff required')
    expected = 'coordinated_pre_enrollment_backup' if menu else 'read_only_console_preparation'
    if record.get('scope') != expected:
        raise ValueError('Coordination scope differs')
    if menu and (not args.owned_menu_close_ok or record.get('owned_menu_close_authorized') is not True):
        raise ValueError('Known main-menu close must be explicitly coordinated')
    return record


def validated_backup(config, proof_path, driver, installer):
    """A fresh helper-produced manifest plus actual owned-close evidence."""
    m, q = installer.m, installer.queue
    proof = driver.read(proof_path)
    if (proof.get('schema') != 'fs-pre-enrollment-owned-backup-1'
            or proof.get('method') != 'existing_m.backup_resume_identity'
            or proof.get('main_eboot_sha256') != config['main_eboot_sha256']
            or proof.get('backup_helper_sha256') != config['helper_sha256']['port/r28b-dlc-dex/install-r28b.py']
            or proof.get('console') != m.api.HOST or proof.get('save_files_written') is not False):
        raise ValueError('Backup provenance or exact main identity differs')
    driver.fresh(proof['closed_at'])
    for field in ('backup_manifest', 'owned_close', 'closed_state', 'menu_identity', 'startup_log', 'initial_probe'):
        q.evidence_file(proof[field], Path(proof_path).parent)
    saved = driver.read(proof['backup_manifest']['path'])
    driver.fresh(saved['at'])
    if (not all(saved.get(k) is True for k in ('fresh', 'all_runs', 'double_read_verified'))
            or saved.get('save_files_written') is not False
            or len(saved.get('runs', [])) < 18 or len(saved.get('files', [])) < 122):
        raise ValueError('Fresh complete all-runs backup required')
    identity = driver.read(proof['menu_identity']['path'])
    closed = driver.read(proof['owned_close']['path'])
    state = driver.read(proof['closed_state']['path'])
    initial = driver.read(proof['initial_probe']['path'])
    if (identity.get('title') != 'PPSA91762' or type(identity.get('pid')) is not int or identity['pid'] <= 1
            or identity.get('eboot_sha256') != config['main_eboot_sha256']
            or identity.get('run') != saved.get('active_run')
            or closed.get('identity') != identity
            or state.get('processes') != [] or state.get('game_closed') is not True
            or state.get('main_eboot_sha256') != config['main_eboot_sha256']
            or initial.get('base_sha256') != config['main_eboot_sha256']
            or initial.get('second_readback_verified') is not True
            or driver.sha(initial['readback_path']) != config['main_eboot_sha256']):
        raise ValueError('Verified backup menu/owned close/initial readback differ')
    driver.fresh(closed['at'])
    driver.fresh(state['at'])
    log = Path(proof['startup_log']['path']).read_text(encoding='utf-8', errors='replace')
    if (not isinstance(identity.get('session'), str)
            or re.fullmatch('[0-9a-f]{16}', identity['session']) is None or identity['session'] not in log):
        raise ValueError('Backup session absent from its new startup log')
    relatives = [row['relative'] for row in saved['files']]
    if len(relatives) != len(set(relatives)):
        raise ValueError('Duplicate backup file records')
    for row in saved['files']:
        if driver.sha(row['path']) != row['sha256'] or row.get('second_readback_sha256') != row['sha256']:
            raise ValueError('Verified backup bytes changed')
    return proof, saved


def backup_menu(args, config, driver, installer):
    """Arm passive capture, await Tomer's manual menu open, then reuse backup."""
    coordination(args, driver, menu=True)
    m = installer.m
    out = driver.local_evidence(args.out)
    out.mkdir(parents=True, exist_ok=False)
    c, board, check, lease = connection(installer)
    capture = None
    try:
        check()
        if m.api.eboot_processes():
            raise RuntimeError('Entry game is not closed; no unknown app is controlled')
        if m.observer.TITLE != 'PPSA91762':
            raise ValueError('Main observer target changed')
        baseline = board.load().get('baselines', {}).get('PPSA91762')
        first = m.bounded_file(c, m.EBOOT, out / 'original-eboot.bin', lease)
        second = c.sha256(m.EBOOT)
        if first['sha256'] != config['main_eboot_sha256'] or second != first['sha256']:
            raise RuntimeError('Current main differs before manual menu; no launch or backup')
        m.write(out / 'initial-probe.json', {'at': m.api.utc_now(), 'base_sha256': first['sha256'],
                'readback_path': first['path'], 'second_readback_verified': True})
        check()
        if m.api.eboot_processes():
            raise RuntimeError('Game opened before capture armed; obtain a new coordinated start')
        log_path = out / 'manual-main-startup.klog.log'
        capture = m.api.KlogCapture(log_path, backlog_seconds=2)
        capture.start()
        deadline = time.monotonic() + 6
        while not capture.connected and capture.error is None and time.monotonic() < deadline:
            check(); time.sleep(.1)
        if not capture.connected:
            raise RuntimeError('Passive collector failed before the manual open')
        drain = time.monotonic() + 2.25
        while time.monotonic() < drain:
            check(); time.sleep(.1)
        check()
        if m.api.eboot_processes():
            raise RuntimeError('Manual open preceded the armed handoff')
        m.write(out / 'MENU-ARMED.json', {'at': m.api.utc_now(), 'console': m.api.HOST,
                'action': 'Tomer may manually open MAIN to its initial randomizer menu only',
                'expected_main_sha256': first['sha256'], 'automatic_launch_performed': False})
        deadline = time.monotonic() + 240
        identity = None
        stable = None
        while time.monotonic() < deadline:
            check()
            procs = m.api.eboot_processes()
            if len(procs) > 1:
                raise RuntimeError('Multiple/unknown processes; never close them')
            if procs:
                try:
                    param = c.read('/mnt/sandbox/PPSA91762_000/app0/sce_sys/param.json', 65536)
                    if param is not None and json.loads(param).get('titleId') != 'PPSA91762':
                        raise RuntimeError('Manual open is not MAIN')
                    status = m.observer.status(c.ftp)
                    text = log_path.read_text(encoding='utf-8', errors='replace')
                    if param is not None and all(marker in text for marker in ('main reached', *installer.READY, status['session'])):
                        candidate = {'pid': m.api.process_pid(procs[0]), 'session': status['session'],
                                     'run': None, 'title': 'PPSA91762', 'at': m.api.utc_now(),
                                     'eboot_sha256': first['sha256'], 'label': 'manual-main-menu-backup'}
                        candidate['run'] = m.owned(c, candidate)
                        key = (candidate['pid'], candidate['session'], candidate['run'])
                        if stable is not None and stable[0] == key and time.monotonic() - stable[1] >= 2:
                            identity = candidate
                            break
                        if stable is None or stable[0] != key:
                            stable = (key, time.monotonic())
                except (ftplib.error_perm, ValueError, KeyError):
                    pass
            time.sleep(.5)
        if identity is None:
            raise RuntimeError('No fresh identified MAIN menu; do not close any unknown process')
        m.write(out / 'menu-identity.json', identity)
        capture.stop(); capture = None  # existing backup starts the only next collector
        check()
        m.backup(c, lease, out, resume_identity=identity, expected_base_sha=config['main_eboot_sha256'])
        check()
        processes = m.api.eboot_processes()
        check()
        if processes or board.load().get('baselines', {}).get('PPSA91762') != baseline:
            raise RuntimeError('Game/baseline changed after owned backup close')
        m.write(out / 'closed-state.json', {'at': m.api.utc_now(), 'processes': [], 'game_closed': True,
                'main_eboot_sha256': first['sha256']})
        proof = {'schema': 'fs-pre-enrollment-owned-backup-1', 'method': 'existing_m.backup_resume_identity',
                 'console': m.api.HOST, 'closed_at': m.api.utc_now(), 'save_files_written': False,
                 'main_eboot_sha256': first['sha256'],
                 'backup_helper_sha256': config['helper_sha256']['port/r28b-dlc-dex/install-r28b.py'],
                 'backup_manifest': m.proof(out / 'save-backup-manifest.json'),
                 'owned_close': m.proof(out / 'original-save-backup-close.json'),
                 'closed_state': m.proof(out / 'closed-state.json'), 'menu_identity': m.proof(out / 'menu-identity.json'),
                 'startup_log': m.proof(log_path), 'initial_probe': m.proof(out / 'initial-probe.json')}
        m.write(out / 'verified-backup.json', proof)
        validated_backup(config, out / 'verified-backup.json', driver, installer)
        return {'status': 'BACKED_UP_AND_KNOWN_MENU_CLOSED', 'verified_backup': m.proof(out / 'verified-backup.json')}
    except Exception as error:
        m.write(out / 'NOT-READY.json', {'status': 'NOT_READY', 'error': str(error), 'automatic_launch_performed': False})
        raise
    finally:
        if capture is not None:
            capture.stop()
        c.close()


def prepare_live(args, config, driver, installer):
    """Closed observations after the explicitly verified backup, never remount."""
    coordination(args, driver)
    if args.verified_backup is None:
        raise ValueError('Fresh verified-backup proof required; closed main saves are normally unmounted')
    _, saved = validated_backup(config, args.verified_backup, driver, installer)
    out = driver.local_evidence(args.out)
    out.mkdir(parents=True, exist_ok=False)
    m = installer.m
    c, board, check, lease = connection(installer)
    result = {'console': m.api.HOST, 'status': 'NOT_READY', 'console_writes': False}
    try:
        check()
        if m.api.eboot_processes():
            raise RuntimeError('Game is not closed after backup')
        baseline = board.load().get('baselines', {}).get('PPSA91762')
        listings = {}
        for folder in ('/data/homebrew', '/user/app', '/mnt/sandbox'):
            listings[folder] = c.listing(folder)
            if any(n == driver.TITLE or n.startswith(driver.TITLE + '_') for n in listings[folder]):
                raise RuntimeError('Side target/registration/data collision')
        if any(re.match(r'^(PPSA|CUSA|FAKE).+_[0-9]{3}$', n) for n in listings['/mnt/sandbox']):
            raise RuntimeError('Existing title sandbox; never remove it automatically')
        if c.read(driver.MOUNT, 4096) is not None:
            raise RuntimeError('Side mount link exists')
        main = [m.bounded_file(c, path, out / ('main-%02d.bin' % i), lease)
                for i, path in enumerate(config['protected_main_paths'])]
        validated_backup(config, args.verified_backup, driver, installer)  # freshness still holds after readbacks
        check()
        if m.api.eboot_processes() or board.load().get('baselines', {}).get('PPSA91762') != baseline:
            raise RuntimeError('Game/baseline changed during preparation')
        m.write(out / 'save-backup-manifest.json', saved)  # unchanged timestamp/content, never retimed
        result.update(status='PREPARED_NOT_ENQUEUED', checked_at=m.api.utc_now(), game_closed=True,
                      processes=[], listings=listings, mount_link=None, data_root=None,
                      candidate_sha256=config['candidate_sha256'], main_readbacks=main,
                      previous_main_handoff=baseline, external_handoff=m.proof(args.coordination),
                      save_backup=m.proof(out / 'save-backup-manifest.json'), verified_backup=m.proof(args.verified_backup))
        m.write(out / 'candidate-prepared.json', result)
        driver.prepared(config, out / 'candidate-prepared.json', m)
        os.replace(out / 'candidate-prepared.json', out / 'prepared.json')
        return result
    except Exception as error:
        result['error'] = str(error)
        m.write(out / 'NOT-READY.json', result)
        raise
    finally:
        c.close()

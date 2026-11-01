"""Install the validated r27 package over r26p1, changing only PPSA91762/eboot.bin.

The console must be idle. Existing proven backup/observer/transaction routines
are reused; version checks and acceptance records are specific to r27.
No operation writes a gameplay save or replaces an older save over progress.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'port/perf-r26'))
import install_r26p as i
h = i.h
BASE_SHA = 'c382275b90704d50e50e57875116bd69341e6c6b9c9c4e4d43223b367e19f7fa'
base_replace = i.replace


def strict_replace(c, name, data, expected_old, tag):
    assert name == 'eboot.bin' and expected_old in (i.OLD, i.NEW)
    wanted = i.OLD if tag.startswith('rollback-') else i.NEW
    assert i.hw.digest(data) == wanted, 'Replacement binary does not match the pinned transaction'
    return base_replace(c, name, data, expected_old, tag)


i.replace = strict_replace


def configure_rollback(state):
    # Recovery depends on the verified backup and transaction record, never on
    # the new package still being present or its proof files being readable.
    assert state['initial_eboot_sha256'] == BASE_SHA
    assert re.fullmatch('[0-9a-f]{64}', state['requested_sha256'])
    assert i.hw.digest((h.OUT / 'original/eboot.bin').read_bytes()) == BASE_SHA
    i.OLD, i.NEW, i.CHANGED = BASE_SHA, state['requested_sha256'], ('eboot.bin',)


def rollback(c, state, reason):
    configure_rollback(state)
    actual = c.sha256(h.APP + '/eboot.bin')
    assert actual in (i.OLD, i.NEW), 'Unknown installed binary; automatic rollback refused'
    i.rollback(c, state, reason)


def configure(package):
    package = package.resolve()
    receipt = json.loads((package / 'r27-package-verification.json').read_text(encoding='utf-8'))
    assert receipt['pc_money_proof_accepted'] is True
    assert receipt['base_eboot_sha256'] == BASE_SHA
    assert receipt['version'] in ('r27-play', 'r27b-play')
    candidate = package / 'PPSA91762/eboot.bin'
    assert i.hw.digest(candidate.read_bytes()) == receipt['eboot_sha256']
    i.OLD, i.NEW = BASE_SHA, receipt['eboot_sha256']
    i.SOURCE, i.CHANGED = candidate.parent, ('eboot.bin',)
    i.startup = startup
    return receipt


def init(c, package_receipt):
    h.idle(); h.title(c)
    assert not (h.OUT / 'state.json').exists()
    configs = {n: c.read(h.APP + '/' + n, 4096) for n in (*h.CONFIGS, 'perf-r24-options.txt')}
    assert configs['performance-options.txt'] == b'optimized\n'
    assert all(b is not None for b in configs.values())
    original = c.read(h.APP + '/eboot.bin', 512 << 20)
    assert i.hw.digest(original) == i.OLD and c.sha256(h.APP + '/eboot.bin') == i.OLD
    dest = h.OUT / 'original'; dest.mkdir()
    (dest / 'eboot.bin').write_bytes(original)
    for name, data in configs.items(): (dest / name).write_bytes(data)
    state = dict(at=h.r.utc_now(), initial_eboot_sha256=i.OLD, requested_sha256=i.NEW,
                 initial_configs={n: b.decode() for n, b in configs.items()}, boots=[], phases=[],
                 nas=str(i.hw.NAS), package_verification=package_receipt)
    i.save(state)
    for f in dest.iterdir(): i.nas_copy(f)
    # The title mounts its latest save in its own launcher menu. It is not
    # continued into gameplay; no previous backup is used as a replacement.
    i.hw.launch(c, state, 'r26p1-latest-save-backup')
    cur = h.owned(c, state); extras = {}
    paths = [('active.json', h.DATA + '/active.json'),
             ('cheats.txt', h.DATA + '/' + cur['run'] + '/cheats.txt'),
             ('player-name.txt', h.DATA + '/player-name.txt')]
    for name, remote in paths:
        data = c.read(remote, 65536)
        extras[name] = None if data is None else dict(bytes=len(data), sha256=i.hw.digest(data))
        if data is not None:
            assert c.read(remote, 65536) == data
            f = h.OUT / 'save-backup' / name; f.write_bytes(data); i.nas_copy(f)
    state['save_extras'] = extras; i.save(state)
    h.write(h.OUT / 'save-backup/extras.json', extras); i.nas_copy(h.OUT / 'save-backup/extras.json')
    i.hw.close(c, state)
    i.emit(dict(stage='latest save and r26p1 backed up; title closed; ready for r27 binary-only update', run=cur['run']))


def startup(state):
    # These are the same play settings as r26p1. No new performance policy is
    # enabled as a side effect of installing names or MONEY.
    i.hw.save_bootlogs(state)
    log = i.hw.bootlog(state)
    assert '[za-r25] submit=thread requested' in log and '[za-r25] submission: thread' in log
    assert 'renderer CPU profile (LARECOMP_VK_PROF): off' in log
    assert '[post] 1920x1080 fsr1 -> 3840x2160' in log
    assert not re.search(r'\[za-r24-options\] force60=1', log)
    slots = re.findall(r'\[za-r23-slots\] active=(\d+)', log)
    assert slots and int(slots[-1]) in (8, 64)
    counter = re.findall(r'\[za-cheats\].*fps_counter=([01])', log)
    assert counter  # A user's saved OFF preference is valid and stays OFF.
    version = state['package_verification']['version']
    assert 'randomizer-' + version in log
    assert 'r27: FPS counter and FPS TRIAL preserved' in log
    assert 'r27 MONEY live-object hook; one request at a time' in log
    h.write(h.OUT / 'startup-verification.json', dict(at=h.r.utc_now(), version=version,
            effective_slots=int(slots[-1]), fps_counter_setting=int(counter[-1]), force60_off=True,
            notes=[line for line in log.splitlines() if re.search(r'\[za-r26p\]|\[za-r25\]|\[za-cheats\]', line)]))


def launch_new(c, state):
    h.idle(); h.title(c)
    assert c.sha256(h.APP + '/eboot.bin') == i.NEW
    out = h.OUT / 'r26p-first-boot'; out.mkdir(exist_ok=False)  # inherited observer helper label
    try: prior = h.client.status(c.ftp)['session']
    except h.ftplib.error_perm: prior = None
    offset = (h.OUT / 'all.klog.log').stat().st_size
    h.idle()
    response = h.r.http_text(h.r.PAYLOAD_MANAGER + '/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf')
    i.emit(dict(stage='r27 launched', response=response))
    deadline = time.monotonic() + 85; last = None; stable = 0
    while time.monotonic() < deadline:
        try:
            status = h.client.status(c.ftp); procs = h.r.eboot_processes()
            active = c.read(h.DATA + '/active.json', 4096)
            log = (h.OUT / 'all.klog.log').read_bytes()[offset:]
            if len(procs) == 1 and active and status['session'] != prior and b'main reached' in log:
                session = status['session']; stable = stable + 1 if session == last else 0; last = session
                if stable >= 2: break
        except h.ftplib.error_perm: pass
        time.sleep(.5)
    else: raise RuntimeError('r27 did not reach stable observer')
    cur = dict(label='r26p-first-boot', pid=h.r.process_pid(procs[0]), session=session,
               run=json.loads(active)['id'], sha256=i.NEW, seq=0, klog_offset=offset,
               at=h.r.utc_now(), options=state['initial_configs']['perf-r24-options.txt'], backup_verified=True)
    state['current'] = cur; state['boots'].append(cur.copy()); i.save(state)
    h.write(out / 'identity.json', cur); h.verify_save(c, state); i.hw.guard(state)


def install(c, state):
    h.idle(); h.title(c)
    assert 'current' not in state and (h.OUT / 'save-backup/verification.json').exists()
    data = (i.SOURCE / 'eboot.bin').read_bytes()
    assert i.hw.digest(data) == i.NEW
    for name, content in state['initial_configs'].items():
        assert c.read(h.APP + '/' + name, 4096) == content.encode(), name
    state['transaction_started_at'] = h.r.utc_now(); i.save(state)
    receipt = i.replace(c, 'eboot.bin', data, i.OLD, h.r.stamp())
    state['replacements'] = [receipt]; i.save(state)
    h.write(h.OUT / 'transaction.json', dict(at=h.r.utc_now(), files=[receipt], only_files=['eboot.bin']))
    for name, content in state['initial_configs'].items():
        assert c.read(h.APP + '/' + name, 4096) == content.encode(), name
    launch_new(c, state)


def complete(c, state):
    h.owned(c, state)
    assert state['smoke_test_passed'] and not state.get('rolled_back')
    assert c.sha256(h.APP + '/eboot.bin') == i.NEW
    for name, content in state['initial_configs'].items():
        assert c.read(h.APP + '/' + name, 4096) == content.encode(), name
    assert c.read(i.hw.INI, 65536) == (None if state['initial_ini'] is None else state['initial_ini'].encode())
    for name, remote in [('active.json', h.DATA + '/active.json'),
                         ('cheats.txt', h.DATA + '/' + state['current']['run'] + '/cheats.txt'),
                         ('player-name.txt', h.DATA + '/player-name.txt')]:
        data = c.read(remote, 65536); expected = state['save_extras'][name]
        assert (None if data is None else i.hw.digest(data)) == (None if expected is None else expected['sha256']), name
    checks = h.verify_save(c, state); startup(state)
    result = dict(at=h.r.utc_now(), installed=True, version=state['package_verification']['version'], installed_sha256=i.NEW,
                  only_replaced=['eboot.bin'], save_check=checks, configs_unchanged=True,
                  ini_unchanged=True, active_run_and_preferences_unchanged=True,
                  smoke_test=json.loads((h.OUT / '30fps-verification.json').read_text()),
                  pc_money_proof=state['package_verification'],
                  console_feature_checks='new-run name and MONEY interactions require separate evidence',
                  application_running=True, nas=str(i.hw.NAS))
    h.write(h.OUT / 'installation.json', result)
    dest = h.OUT / 'installed/PPSA91762/eboot.bin'; dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(i.SOURCE / 'eboot.bin', dest); i.nas_copy(dest)
    state['installation_complete'] = True; i.save(state)
    for name in ('installation.json', 'transaction.json', 'startup-verification.json',
                 '30fps-verification.json', 'state.json'): i.nas_copy(h.OUT / name)
    i.emit(dict(stage='r27 installed; existing save and options unchanged; NAS copies verified', sha256=i.NEW))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--package', type=Path, default=ROOT / 'artifacts/randomizer-r27b-play')
    p.add_argument('op', choices=('log', 'init', 'install', 'ready', 'measure', 'complete', 'rollback'))
    p.add_argument('--reason', default='Requested r27 rollback')
    a = p.parse_args()
    h.OUT = a.out.resolve(); h.OUT.mkdir(parents=True, exist_ok=True)
    i.hw.NAS = Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port') / h.OUT.name
    if a.op == 'log':
        i.hw.logger(h.OUT); return
    if a.op == 'rollback':
        configure_rollback(i.readstate())
        receipt = None
    else:
        receipt = configure(a.package)
    c = h.r.Console()
    try:
        if a.op == 'init': init(c, receipt)
        else:
            state = i.readstate()
            assert state['requested_sha256'] == i.NEW and state['initial_eboot_sha256'] == i.OLD
            if a.op == 'install': install(c, state)
            elif a.op == 'ready': i.ready(c, state)
            elif a.op == 'measure': i.measure(c, state)
            elif a.op == 'complete': complete(c, state)
            elif a.op == 'rollback': rollback(c, state, a.reason)
    except Exception as error:
        h.write(h.OUT / ('error-' + h.r.stamp() + '.json'),
                dict(at=h.r.utc_now(), op=a.op, type=type(error).__name__, error=str(error)))
        # A failed acceptance never authorizes killing an unrelated application.
        # The inherited rollback checks exact PID/session ownership first.
        if (h.OUT / 'state.json').exists():
            state = i.readstate()
            if state.get('transaction_started_at') and not state.get('installation_complete') and a.op not in ('complete', 'rollback'):
                rollback(c, state, str(error))
        raise
    finally: c.close()


if __name__ == '__main__': main()

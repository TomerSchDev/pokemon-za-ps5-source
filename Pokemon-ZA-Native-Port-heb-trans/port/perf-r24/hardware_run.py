"""Scoped hardware measurements requested by HANDOFF-r24-perf-HE.md."""
import argparse
import ftplib
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'port/perf-r24/observer'))
import run_r3 as r
import client
import analyze_r24

APP = '/data/homebrew/PPSA91762'
SANDBOX = '/mnt/sandbox/PPSA91762_000'
DATA = SANDBOX + '/download0/zarecomp/rando'
BUILDS = {
    'r23c': ('randomizer-r23c-slot-depth', 'dd1df4862a08eab80a19790bb2b65b351adb8ff1fc3ce893def4a91417786677'),
    'r24': ('randomizer-r24-perf', 'a7890eca75127adcdb9c464cdeb03e9c1d143fe099fbf853500a9349c56a5610'),
}
CONFIGS = ('performance-options.txt', 'performance-profile.txt', 'observer-enable.txt',
           'local-shader-options.txt', 'submission-options.txt', 'slot-depth-options.txt')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def idle():
    assert not r.eboot_processes(), 'Console occupied'


def title(c):
    assert json.loads(c.read(APP + '/sce_sys/param.json'))['titleId'] == 'PPSA91762'
    assert c.read('/user/app/PPSA91762/mount.lnk') == APP.encode()


def put(c, name, data):
    idle(); title(c)
    old = c.read(APP + '/' + name, 4096)
    if old == data:
        return
    target = APP + '/' + name
    stage = target + '.r24-stage-' + str(time.time_ns())
    c.store(stage, data)
    assert c.read(stage, 4096) == data
    idle()
    if old is not None:
        c.ftp.rename(target, target + '.before-r24-' + str(time.time_ns()))
    c.ftp.rename(stage, target)
    assert c.read(target, 4096) == data


def owned(c, state):
    current = state['current']
    ps = r.eboot_processes()
    assert len(ps) == 1 and r.process_pid(ps[0]) == current['pid'], ps
    assert client.status(c.ftp)['session'] == current['session']
    title(c)
    assert json.loads(c.read(DATA + '/active.json', 4096))['id'] == current['run']
    return current


def collect(c, sid, seq, out, expected, **kwargs):
    deadline = time.monotonic() + 25
    while True:
        try:
            rec = client.collect(c.ftp, sid, seq, out, **kwargs)
            ack = rec.get('ack', rec)
            if ack['result'] in expected:
                return rec
            if ack['result'] != 'settling':
                raise RuntimeError(json.dumps(ack))
        except ftplib.error_perm as ex:
            if not str(ex).startswith('550'):
                raise
        if time.monotonic() > deadline:
            raise TimeoutError('No completed observer receipt')
        time.sleep(.3)


def command(c, state, out, op, arg=None, frames=None, expected=None, **kwargs):
    cur = owned(c, state)
    seq = cur['seq'] + 1
    cur['seq'] = seq
    write(OUT / 'state.json', state)
    client.issue(c.ftp, cur['session'], seq, op, arg, frames)
    if op == 'measure':
        print(json.dumps({'stage': 'measuring', 'seconds': arg, 'label': out.name, 'seq': seq}), flush=True)
        # No FTP, screenshots or commands inside the recorder window.
        time.sleep(arg + 3)
    rec = collect(c, cur['session'], seq, out, expected or {'applied'}, **kwargs)
    owned(c, state)
    return rec


def backup(c, run, out):
    files = []
    for name in ('report.json', 'save/save_0/main'):
        remote = DATA + '/' + run + '/' + name
        data = c.read(remote, 16 << 20)
        assert data and c.read(remote, 16 << 20) == data
        local = out / name
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        files.append(dict(path=name, bytes=len(data), sha256=sha(data)))
    rec = dict(at=r.utc_now(), run=run, files=files, double_read_verified=True)
    write(out / 'verification.json', rec)
    return rec


def verify_save(c, state):
    cur = owned(c, state)
    info = json.loads((OUT / 'save-backup/verification.json').read_text())
    assert cur['run'] == info['run']
    checks = []
    for f in info['files']:
        actual = c.sha256(DATA + '/' + cur['run'] + '/' + f['path'])
        checks.append(dict(path=f['path'], sha256=actual, unchanged=actual == f['sha256']))
    assert all(x['unchanged'] for x in checks), checks
    return checks


def retire(c, state, rec, out):
    for f in rec['files']:
        assert f['name'].endswith('.png') and f['readback_verified']
        assert sha((out / f['name']).read_bytes()) == f['sha256']
        remote = client.BASE + '/session_' + state['current']['session'] + '/' + f['name']
        assert c.sha256(remote) == f['sha256']
        target = f"{state['current']['session']}:{rec['ack']['seq']}"
        command(c, state, out, 'retire_capture', target, expected={'retired'}, expected_retire_capture=target)


def main(a):
    statefile = OUT / 'state.json'
    state = json.loads(statefile.read_text()) if statefile.exists() else {'boots': [], 'phases': []}
    if a.op == 'log':
        cap = r.KlogCapture(OUT / 'all.klog.log'); cap.start()
        print('logger started', flush=True)
        try:
            while not (OUT / 'stop-logger').exists() and cap.is_alive():
                time.sleep(.25)
        finally:
            cap.stop()
        write(OUT / 'logger.json', dict(lines=cap.lines, error=cap.error))
        return
    c = r.Console()
    try:
        if a.op == 'launch':
            idle(); title(c)
            label = a.label
            assert re.fullmatch('[a-zA-Z0-9_-]+', label)
            out = OUT / label; out.mkdir(exist_ok=False)
            if 'initial_configs' not in state:
                initial = {}
                for name in (*CONFIGS, 'perf-r24-options.txt'):
                    data = c.read(APP + '/' + name, 4096)
                    initial[name] = data.decode() if data is not None else None
                assert initial['performance-options.txt'] == 'optimized\n'
                assert initial['slot-depth-options.txt'] == '16\n'
                state['initial_configs'] = initial
                write(statefile, state)
            for name in CONFIGS:
                assert c.read(APP + '/' + name, 4096).decode() == state['initial_configs'][name]
            folder, wanted = BUILDS[a.build]
            source = ROOT / 'artifacts' / folder / 'PPSA91762/eboot.bin'
            assert sha(source.read_bytes()) == wanted
            old = c.sha256(APP + '/eboot.bin')
            assert old in {v[1] for v in BUILDS.values()}, old
            if old != wanted:
                stage = APP + '/eboot.bin.r24-stage-' + r.stamp()
                c.store(stage, source.read_bytes()); c.chmod(stage, '755')
                assert c.sha256(stage) == wanted
                idle(); title(c)
                assert c.sha256(APP + '/eboot.bin') == old
                previous = APP + '/eboot.bin.before-r24-' + r.stamp()
                c.ftp.rename(APP + '/eboot.bin', previous)
                try:
                    c.ftp.rename(stage, APP + '/eboot.bin')
                except Exception:
                    c.ftp.rename(previous, APP + '/eboot.bin'); raise
                assert c.sha256(APP + '/eboot.bin') == wanted
                write(out / 'deploy.json', dict(old_sha256=old, new_sha256=wanted, remote_backup=previous, verified=True))
            options = 'gaps=1\ndcache=' + a.dcache + '\nprof=' + str(a.prof) + '\n'
            if a.mode:
                options += 'mode=' + a.mode + '\n'
            if a.build == 'r24':
                put(c, 'perf-r24-options.txt', options.encode())
            idle()
            try:
                prior_session = client.status(c.ftp)['session']
            except ftplib.error_perm:
                prior_session = None
            offset = (OUT / 'all.klog.log').stat().st_size
            response = r.http_text(r.PAYLOAD_MANAGER + '/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf')
            print(json.dumps({'stage': 'launched', 'label': label, 'response': response}), flush=True)
            deadline = time.monotonic() + 75
            while True:
                try:
                    status = client.status(c.ftp)
                    procs = r.eboot_processes()
                    active = c.read(DATA + '/active.json', 4096)
                    boot_log = (OUT / 'all.klog.log').read_bytes()[offset:]
                    if len(procs) == 1 and active and status['session'] != prior_session and b'main reached' in boot_log:
                        break
                except ftplib.error_perm:
                    pass
                assert time.monotonic() < deadline, 'Launch did not reach observer'
                time.sleep(.5)
            run = json.loads(active)['id']
            if not (OUT / 'save-backup/verification.json').exists():
                backup(c, run, OUT / 'save-backup')
            cur = dict(label=label, build=a.build, sha256=wanted, session=status['session'], pid=r.process_pid(procs[0]),
                       run=run, options=options, seq=0, klog_offset=offset, at=r.utc_now(), backup_verified=True)
            state['current'] = cur; state['boots'].append(cur)
            write(statefile, state); write(out / 'identity.json', cur)
            verify_save(c, state)
            print(json.dumps(cur), flush=True)
        elif a.op == 'continue':
            cur = owned(c, state); verify_save(c, state)
            out = OUT / cur['label']
            rec = command(c, state, out, 'continue', cur['run'], expected={'continue_requested'})
            print(json.dumps(rec), flush=True)
        elif a.op == 'ready':
            cur = owned(c, state); verify_save(c, state)
            out = OUT / cur['label']
            command(c, state, out, 'continue', cur['run'], expected={'continue_requested'})
            print('Waiting for the title screen', flush=True)
            time.sleep(12)
            command(c, state, out, 'input', 'A', 1, expected={'input_armed'})
            print('Loading the unchanged save and warming shaders', flush=True)
            time.sleep(35)
            rec = command(c, state, out, 'snapshot', expected={'saved'})
            retire(c, state, rec, out)
            print(json.dumps(rec), flush=True)
        elif a.op == 'input':
            cur = owned(c, state)
            print(json.dumps(command(c, state, OUT / cur['label'], 'input', a.action, a.frames, expected={'input_armed'})), flush=True)
        elif a.op == 'snapshot':
            cur = owned(c, state)
            rec = command(c, state, OUT / cur['label'], 'snapshot', expected={'saved'})
            print(json.dumps(rec), flush=True)
        elif a.op == 'sample':
            cur = owned(c, state)
            out = OUT / cur['label'] / a.label; out.mkdir(exist_ok=False)
            if a.slots:
                transition = command(c, state, out, 'slot_depth', a.slots,
                                     expected={'applied', 'memory_gate', 'preflight_failed', 'drain_failed', 'incompatible_profile'},
                                     expected_slot_depth=a.slots)
                write(out / 'transition.json', transition)
                if transition['ack']['result'] != 'applied':
                    print(json.dumps(transition), flush=True); return
            command(c, state, out, 'fps', 0, expected={'requested'})
            before = command(c, state, out, 'snapshot', expected={'saved'})
            retire(c, state, before, out)
            rec = command(c, state, out, 'measure', 20, expected={'complete'})
            after = command(c, state, out, 'snapshot', expected={'saved'})
            retire(c, state, after, out)
            csvfile = out / rec['files'][0]['name']
            timing = json.loads((out / (csvfile.stem + '-analysis.json')).read_text())
            assert timing['fps_modes'] == [0] and not timing['capture_inside_window']
            assert timing['all_intervals']['duration_s'] >= 19.85
            # A separate slice binds counter windows to this exact launch, avoiding frame-ID collisions.
            logbytes = (OUT / 'all.klog.log').read_bytes()[cur['klog_offset']:]
            log = OUT / cur['label'] / 'boot.klog.log'; log.write_bytes(logbytes)
            first, last = analyze_r24.csv_frames(csvfile)
            perf = analyze_r24.summarize(analyze_r24.parse(log, first, last))
            write(out / 'r24-counters.json', perf)
            phase = dict(label=a.label, boot=cur['label'], build=cur['build'], options=cur['options'], slots=a.slots or 16,
                         csv=str(csvfile.relative_to(OUT)), timing=timing, perf=perf,
                         before=before['files'], after=after['files'], save_check=verify_save(c, state))
            state['phases'].append(phase); write(out / 'phase.json', phase)
            print(json.dumps({'boot': cur['label'], 'label': a.label, 'timing': timing['all_intervals'], 'perf': perf}), flush=True)
        elif a.op == 'close':
            cur = owned(c, state); checks = verify_save(c, state)
            response = r.http_json('/process_kill?pid=' + str(cur['pid']))
            deadline = time.monotonic() + 15
            while r.eboot_processes():
                assert time.monotonic() < deadline, 'Owned title did not close'
                time.sleep(.5)
            logbytes = (OUT / 'all.klog.log').read_bytes()[cur['klog_offset']:]
            (OUT / cur['label'] / 'boot.klog.log').write_bytes(logbytes)
            write(OUT / cur['label'] / 'close.json', dict(at=r.utc_now(), response=response, pid=cur['pid'], save_check=checks))
            del state['current']
            print(json.dumps({'closed': cur['label'], 'save_unchanged': True}), flush=True)
        elif a.op == 'inspect':
            cur = owned(c, state)
            print(json.dumps({'current': cur, 'status': client.status(c.ftp), 'save_check': verify_save(c, state)}), flush=True)
        elif a.op == 'restore-config':
            idle(); title(c)
            previous = state['initial_configs']['perf-r24-options.txt']
            remote = APP + '/perf-r24-options.txt'
            actual = c.read(remote, 4096)
            if previous is None and actual is not None:
                c.ftp.rename(remote, remote + '.measurement-' + r.stamp())
            elif previous is not None:
                put(c, 'perf-r24-options.txt', previous.encode())
            assert c.read(remote, 4096) == (previous.encode() if previous is not None else None)
            for name in CONFIGS:
                assert c.read(APP + '/' + name, 4096).decode() == state['initial_configs'][name]
            state['configs_restored_at'] = r.utc_now()
            print('Original configuration restored and verified', flush=True)
        else:
            raise ValueError(a.op)
        write(statefile, state)
    finally:
        c.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('op', choices=('launch', 'continue', 'ready', 'input', 'sample', 'snapshot', 'close', 'inspect', 'restore-config', 'log'))
    p.add_argument('--label')
    p.add_argument('--build', choices=BUILDS, default='r24')
    p.add_argument('--dcache', choices=('tls', 'cpu'), default='tls')
    p.add_argument('--prof', type=int, choices=(0, 1), default=0)
    p.add_argument('--mode', choices=('1920x1080',))
    p.add_argument('--slots', type=int, choices=(8, 16, 32, 64))
    p.add_argument('--action', choices=client.ACTIONS)
    p.add_argument('--frames', type=int, choices=range(1, 121), default=1)
    args = p.parse_args(); OUT = args.out.resolve(); OUT.mkdir(parents=True, exist_ok=True)
    main(args)

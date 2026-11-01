"""Bounded compiler test in PPSA91760. Closes only its nonce/PID-verified probe."""
from __future__ import annotations
import ftplib
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import run_r3 as r

APP = '/data/homebrew/PPSA91760'
NEW = 'f0cb28b0d4939a4c363b317e22524d1da3c36317bdd1cf03e60fb5deb9d909d4'
OLD = '5de2a972b169b81a816524908c30e9142726f4f9a4e51b26e97fd7a5b64e4de3'
LIBC = 'e6ff45d16adf687855cc3b33b0c8a4132b6504360b221e0a34c7e99fb3ba0036'
CAPTURE = ROOT / 'evidence/randomizer-shaders-20261028-041124Z'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def idle():
    processes = r.eboot_processes()
    if processes:
        raise RuntimeError('Console occupied; not closing any title: ' + json.dumps(processes))

def main():
    idle()
    run = r.stamp().lower()
    out = ROOT / 'evidence/shader-probe-r18b' / run
    out.mkdir(parents=True, exist_ok=False)
    journal = dict(run=run, started=r.utc_now(), installed=False, restored=False)
    def save():
        (out/'hardware.json').write_text(json.dumps(journal, indent=2)+'\n')
    save()
    payload = (ROOT/'artifacts/shader-probe-r18b/eboot.bin').read_bytes()
    assert sha(payload) == NEW
    manifest = json.loads((CAPTURE/'manifest.json').read_text())
    c = r.Console()
    capture = None
    backup = APP + '/eboot.bin.before-shader-probe-' + run
    staged = APP + '/eboot.bin.shader-probe-' + run
    remote = '/mnt/sandbox/PPSA91760_000/download0/za-shader-probe-r18b/' + run
    try:
        assert json.loads(c.read(APP+'/sce_sys/param.json'))['titleId'] == 'PPSA91760'
        assert c.read('/user/app/PPSA91760/mount.lnk') == APP.encode()
        assert c.sha256(APP+'/sce_module/libc.prx') == LIBC
        assert c.sha256(APP+'/eboot.bin') == OLD
        original = c.read(APP+'/eboot.bin', 256 << 20)
        assert sha(original) == OLD
        (out/'original-eboot.bin').write_bytes(original)
        journal['original_sha256'] = OLD
        journal['candidate_sha256'] = NEW
        journal['remote_backup'] = backup
        save()
        inputs = APP + '/shader-probe-r18b'
        try:
            c.ftp.mkd(inputs)
        except ftplib.error_perm:
            assert 'shader-probe-r18b' in c.listing(APP)
        for entry in manifest:
            name = entry['source']
            assert re.fullmatch(r'[0-9a-f]{16}\.(vert|frag)', name)
            data = (CAPTURE/name).read_bytes()
            assert sha(data) == entry['source_sha256']
            c.store(inputs+'/'+name, data)
            assert c.sha256(inputs+'/'+name) == sha(data)
        c.store(inputs+'/run-id.txt', run.encode('ascii'))
        assert c.read(inputs+'/run-id.txt') == run.encode('ascii')
        c.store(staged, payload)
        c.chmod(staged, '755')
        assert c.sha256(staged) == NEW
        idle()
        c.ftp.rename(APP+'/eboot.bin', backup)
        journal['original_moved'] = True
        save()
        c.ftp.rename(staged, APP+'/eboot.bin')
        journal['installed'] = True
        save()
        assert c.sha256(APP+'/eboot.bin') == NEW
        capture = r.KlogCapture(out/'console.klog.log')
        capture.start()
        time.sleep(2.5)
        idle()
        journal['launch'] = r.http_text(r.LAUNCHER_URL)
        journal['launch_at'] = r.utc_now()
        save()
        print('Launched compiler probe '+run, flush=True)
        deadline = time.monotonic() + 110
        samples = []
        complete = False
        seen_process = False
        while time.monotonic() < deadline:
            processes = r.eboot_processes()
            if processes:
                seen_process = True
                samples.append(dict(at=r.utc_now(), processes=processes))
            data = c.read(remote+'/results.jsonl', 1 << 20)
            if data:
                (out/'results.jsonl').write_bytes(data)
                complete = b'"type":"complete"' in data
            if complete or (seen_process and not processes):
                break
            time.sleep(1)
        journal['samples'] = samples
        journal['completed'] = complete
        journal['processes_after'] = r.eboot_processes()
        save()
        try:
            names = c.listing(remote)
        except ftplib.error_perm:
            names = []
        outputs = []
        for name in names:
            if not re.fullmatch(r'(results\.jsonl|[0-9]{2}-[a-z0-9.]+\.spv)', name):
                continue
            data = c.read(remote+'/'+name, 16 << 20)
            assert data is not None
            (out/name).write_bytes(data)
            outputs.append(dict(name=name, bytes=len(data), sha256=sha(data)))
        journal['outputs'] = outputs
        expected = {f'{i:02d}-{entry["source"]}.spv': entry['spv_sha256']
                    for i in range(3) for entry in manifest}
        got = {entry['name']: entry['sha256'] for entry in outputs}
        journal['captured_spirv_match'] = {
            name: got.get(name) == digest for name, digest in expected.items()}
        journal['smoke_recovery_match'] = bool(got.get('00-smoke.comp.spv')) and (
            got.get('00-smoke.comp.spv') == got.get('00-recovery.comp.spv'))
        journal['output_hashes_passed'] = all(journal['captured_spirv_match'].values()) and journal['smoke_recovery_match']
        save()
        print('Collected '+str(len(outputs))+' files; complete='+str(complete), flush=True)
        if complete:
            rows = [json.loads(line) for line in (out/'results.jsonl').read_text().splitlines()]
            start = rows[0]
            assert start['type'] == 'start' and start['build'] == 'r18b'
            # A fresh, unique run directory binds this PID to the exact probe.
            assert c.sha256(APP+'/eboot.bin') == NEW
            assert c.read(inputs+'/run-id.txt') == run.encode('ascii')
            processes = r.eboot_processes()
            assert len(processes) == 1 and r.process_pid(processes[0]) == start['pid']
            journal['controlled_close'] = r.http_json('/process_kill?pid='+str(start['pid']))
            save()
            for _ in range(20):
                if not r.eboot_processes():
                    break
                time.sleep(.5)
    finally:
        if capture:
            capture.stop()
            journal['klog_error'] = capture.error
        # Never overwrite a running executable, even after a failed test.
        if journal.get('original_moved'):
            try:
                idle()
                assert c.sha256(backup) == OLD
                installed = c.sha256(APP+'/eboot.bin')
                assert installed in (NEW, None), installed
                if installed == NEW:
                    c.ftp.rename(APP+'/eboot.bin', APP+'/eboot.bin.shader-probe-finished-'+run)
                c.ftp.rename(backup, APP+'/eboot.bin')
                assert c.sha256(APP+'/eboot.bin') == OLD
                journal['restored'] = True
            except Exception as error:
                journal['restore_error'] = str(error)
        journal['finished'] = r.utc_now()
        save()
        c.close()
        print(json.dumps(dict(evidence=str(out), complete=journal.get('completed'),
                              restored=journal['restored'], restore_error=journal.get('restore_error'))), flush=True)

if __name__ == '__main__':
    main()

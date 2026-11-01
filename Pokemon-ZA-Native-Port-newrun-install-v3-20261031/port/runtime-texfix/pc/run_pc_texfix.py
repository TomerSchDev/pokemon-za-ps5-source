"""One bounded scripted PC session for the r28a texfix (hebrew-lab/tools/run_poc.py's pattern, another runtime copy).

    py -3 run_pc_texfix.py <name> --exe <runtime copy>/lasrecomp.exe --runs <dir> --save-src <dir with save_0/main>
                           --seconds N [--input ...] [--shot-at ...] [--env K=V ...]

A data root of its own (<runs>/<name>, the runtime's working directory), a fresh copy of the test save, its own
settings file, scripted input (LARECOMP_INPUT), no user input, captures at fixed frames (LARECOMP_SHOT_AT), the process
(this child only) ended after the budget. The game files are passed by absolute path and only read. The runtime copy is
a folder of its own (never hebrew-lab/runtime). Writes <run>/run.json with the [za-texguard] lines found in the log.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

GAME = Path(r'C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc'
            r'\update-2.0.2-20261025\game')
FORBIDDEN_EXE_DIRS = ('hebrew-lab', 'pokeza-pc')  # (the PC runtime in use and the game folder: never run from there)


def sha256(p):
    with open(p, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('name')
    p.add_argument('--exe', type=Path, required=True)
    p.add_argument('--runs', type=Path, required=True)
    p.add_argument('--save-src', type=Path, required=True)
    p.add_argument('--seconds', type=int, required=True)
    p.add_argument('--input', default='')
    p.add_argument('--shot-at', default='')
    p.add_argument('--env', nargs='*', default=[])
    a = p.parse_args()
    exe = a.exe.resolve()
    if any(part in exe.parts for part in FORBIDDEN_EXE_DIRS):
        p.error('run a copy of the runtime, not %s' % exe)
    root = (a.runs / a.name).resolve()
    if root.exists():
        p.error('run exists: %s' % root)
    root.mkdir(parents=True)
    (root / 'build').mkdir()
    save = root / 'save'
    shutil.copytree(a.save_src / 'save_0', save / 'save_0')
    for f in save.rglob('*'):
        if f.is_file():
            os.chmod(f, 0o666)
    (root / 'larecomp.ini').write_text(
        'aspect = original\nfullscreen = 0\nvolume = 0\nshow_fps = 0\nfps60 = 0\nresolution = 1x\n'
        'dynamic_res = off\ntex_hd = 0\nantialias = smaa\nupscaler = fsr1\nlanguage = en-US\nmouse_camera = off\n'
        'prompts = nintendo\n', encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LARECOMP_', 'POKELAB_'))}
    env.update(LARECOMP_DATA_ROOT=str(root), LARECOMP_NO_UPDATE_CHECK='1', LARECOMP_REEXEC='20',
               LARECOMP_SAVE_DIR=str(save), LARECOMP_SETTINGS=str(root / 'larecomp.ini'), LARECOMP_WAIT_DUMP='10',
               LARECOMP_SKIP_WHY='1', LARECOMP_KBD_AUTO='Test', LARECOMP_NO_USER_INPUT='1')
    if a.input:
        env['LARECOMP_INPUT'] = a.input
    if a.shot_at:
        env['LARECOMP_SHOT_AT'] = a.shot_at
    for kv in a.env:
        k, v = kv.split('=', 1)
        env[k] = v
    sv = save / 'save_0' / 'main'
    record = dict(name=a.name, started_utc=datetime.now(timezone.utc).isoformat(), budget_seconds=a.seconds,
                  exe=str(exe), exe_sha256=sha256(exe), game=str(GAME), input_script=a.input, shot_at=a.shot_at,
                  save_source=str(a.save_src), save_before=dict(bytes=sv.stat().st_size, sha256=sha256(sv)),
                  extra_env={k: env[k] for k in env if k.startswith('LARECOMP_')}, address_collisions=0)
    for attempt in range(4):
        start = time.monotonic()
        with (root / 'stdout.log').open('wb') as out, (root / 'stderr.log').open('wb') as err:
            proc = subprocess.Popen([str(exe), str(GAME), '--play'], cwd=root, env=env, stdout=out, stderr=err)
            record['pid'] = proc.pid
            (root / 'run.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
            print(json.dumps(dict(run=a.name, pid=proc.pid)), flush=True)
            try:
                record['exit_code'] = proc.wait(timeout=a.seconds)
                record['terminated_by_harness'] = False
            except subprocess.TimeoutExpired:
                proc.terminate()  # (this child only)
                record['exit_code'] = proc.wait(timeout=15)
                record['terminated_by_harness'] = True
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        early = not record['terminated_by_harness'] and time.monotonic() - start < 10
        if early and b'guest address range' in (root / 'stderr.log').read_bytes():
            record['address_collisions'] += 1
            (root / 'stderr.log').replace(root / ('stderr-collision-%d.log' % (attempt + 1)))
            continue
        break
    record['elapsed_seconds'] = round(time.monotonic() - start, 3)
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    record['captured_files'] = sorted(str(f.relative_to(root)) for f in root.rglob('*.png') if f.stat().st_size)
    record['save_after'] = dict(bytes=sv.stat().st_size, sha256=sha256(sv))
    record['save_source_unchanged'] = sha256(a.save_src / 'save_0' / 'main') == record['save_before']['sha256']
    log = (root / 'stderr.log').read_text(encoding='utf-8', errors='replace')
    record['texguard_lines'] = [ln for ln in log.splitlines() if '[za-texguard]' in ln]
    fps = re.findall(r'\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps', log)
    record['frames'] = int(fps[-1][1]) if fps else 0
    record['fps_samples'] = len(fps)
    record['faults'] = [ln for ln in log.splitlines() if re.search(r'signal|FATAL|fault|device lost|Assertion', ln, re.I)][:20]
    (root / 'run.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({k: record[k] for k in ('exit_code', 'terminated_by_harness', 'elapsed_seconds', 'frames',
                                             'texguard_lines', 'faults', 'captured_files')}, indent=1), flush=True)


if __name__ == '__main__':
    main()

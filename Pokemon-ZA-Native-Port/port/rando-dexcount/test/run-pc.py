"""One bounded PC run of Z-A 2.0.2 for the dex-count proof.

Own data root (the run folder becomes the runtime's working directory), a fresh copy of a TEST save, its own
settings file, optional LayeredFS mod folder, optional scripted input (LARECOMP_INPUT) and the diagnostic
controller command file (ZA_DEXCOUNT_PC_CONTROL, only understood by the diagnostic DLL). Only this script's own
child process is ever stopped. The game files are passed by absolute path and only read. No console access.
"""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, time
from datetime import datetime, timezone

GAME = Path(r'C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc'
            r'\update-2.0.2-20261025\game')
REAL_SAVE_MARKERS = ('PPSA91762', 'PPSA91761', 'Downloads')


def sha(p):
    with open(p, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--exe', type=Path, required=True)
    p.add_argument('--dll', type=Path, help='diagnostic game library (default: the stock one in the game folder)')
    p.add_argument('--save', type=Path, required=True, help='TEST save file (copied, never written)')
    p.add_argument('--out', type=Path, required=True, help='new run folder')
    p.add_argument('--mods', type=Path, help='folder of mod folders, copied to <run>/mods')
    p.add_argument('--cache', type=Path, help='earlier run whose cache/ seeds this one')
    p.add_argument('--seconds', type=int, default=120)
    p.add_argument('--input', default='')
    p.add_argument('--shots', default='')
    p.add_argument('--control', action='store_true', help='enable the diagnostic controller command file')
    p.add_argument('--every', type=int, default=0, help='LARECOMP_SCREENSHOT_EVERY (frames), 0 = off')
    p.add_argument('--env', nargs='*', default=[])
    a = p.parse_args()
    assert 10 <= a.seconds <= 3600
    src = a.save.resolve()
    assert not any(m in str(src) for m in REAL_SAVE_MARKERS), 'refusing a save that may be a real one'
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'save/save_0').mkdir(parents=True)
    (out / 'build').mkdir()
    shutil.copy2(src, out / 'save/save_0/main')
    os.chmod(out / 'save/save_0/main', 0o666)
    if a.mods:
        shutil.copytree(a.mods, out / 'mods')
    if a.cache and (a.cache / 'cache').is_dir():
        shutil.copytree(a.cache / 'cache', out / 'cache')
    (out / 'larecomp.ini').write_text(
        'aspect = original\nfullscreen = 0\nvolume = 0\nshow_fps = 0\nfps60 = 0\nresolution = 1x\n'
        'dynamic_res = off\ntex_hd = 0\nantialias = smaa\nupscaler = fsr1\nlanguage = en-US\nmouse_camera = off\n'
        'prompts = nintendo\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LARECOMP_', 'POKELAB_', 'ZA_'))}
    env.update(PATH='C:/msys64/ucrt64/bin;' + env['PATH'], LARECOMP_DATA_ROOT=str(out), LARECOMP_NO_UPDATE_CHECK='1',
               LARECOMP_REEXEC='20', LARECOMP_SAVE_DIR=str(out / 'save'), LARECOMP_SETTINGS=str(out / 'larecomp.ini'),
               LARECOMP_SCREENSHOT_EVERY=str(a.every), LARECOMP_WAIT_DUMP='10', LARECOMP_SKIP_WHY='1',
               LARECOMP_KBD_AUTO='Test', LARECOMP_NO_USER_INPUT='1',
               LARECOMP_INPUT=a.input or '999999999:A:1')
    if a.dll:
        env['LARECOMP_GAME_LIB'] = str(a.dll.resolve())
    if a.shots:
        env['LARECOMP_SHOT_AT'] = a.shots
    if a.control:
        env['ZA_DEXCOUNT_PC_CONTROL'] = str(out / 'control.txt')
    for kv in a.env:
        k, v = kv.split('=', 1)
        env[k] = v
    dll = a.dll.resolve() if a.dll else GAME / 'lasgame.dll'
    record = dict(started_utc=datetime.now(timezone.utc).isoformat(), game=str(GAME), runtime_sha256=sha(a.exe),
                  dll=str(dll), dll_sha256=sha(dll), fixture=str(src), source_save_sha256=sha(src),
                  copy_before_sha256=sha(out / 'save/save_0/main'), seconds=a.seconds, input=a.input, shots=a.shots,
                  control=a.control, mods=sorted(str(f.relative_to(out)) for f in (out / 'mods').rglob('*')
                                                 if f.is_file()) if a.mods else [],
                  mod_sha256={str(f.relative_to(out)): sha(f) for f in (out / 'mods').rglob('*') if f.is_file()}
                  if a.mods else {}, extra_env=a.env)
    record['address_collisions'] = 0
    for attempt in range(4):
        started = time.monotonic()
        with (out / 'stdout.log').open('wb') as so, (out / 'stderr.log').open('wb') as se:
            proc = subprocess.Popen([str(a.exe.resolve()), str(GAME), '--play'], cwd=out, env=env, stdout=so, stderr=se)
            record['pid'] = proc.pid
            (out / 'run.json').write_text(json.dumps(record, indent=2))
            print(json.dumps(dict(pid=proc.pid, run=str(out))), flush=True)
            try:
                while proc.poll() is None:
                    if time.monotonic() - started >= a.seconds:
                        raise subprocess.TimeoutExpired(proc.args, a.seconds)
                    if (out / 'STOP').exists():
                        raise subprocess.TimeoutExpired(proc.args, 0)
                    try:
                        proc.wait(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        pass
                record['exit_code'] = proc.returncode
                record['terminated_by_harness'] = False
            except subprocess.TimeoutExpired:
                proc.terminate()  # this child only
                record['exit_code'] = proc.wait(timeout=15)
                record['terminated_by_harness'] = True
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        if time.monotonic() - started < 10 and b'guest address range' in (out / 'stderr.log').read_bytes():
            record['address_collisions'] += 1
            (out / 'stderr.log').rename(out / ('collision-%d.log' % attempt))
            continue
        break
    record.update(finished_utc=datetime.now(timezone.utc).isoformat(), elapsed=round(time.monotonic() - started, 3),
                  copy_after_sha256=sha(out / 'save/save_0/main'), source_unchanged=sha(src) == record['source_save_sha256'],
                  captured=sorted(str(f.relative_to(out)) for f in out.rglob('*.png') if f.stat().st_size))
    (out / 'run.json').write_text(json.dumps(record, indent=2))
    print(json.dumps({k: record[k] for k in ('pid', 'exit_code', 'elapsed', 'copy_before_sha256', 'copy_after_sha256',
                                             'source_unchanged')}, indent=2))


if __name__ == '__main__':
    main()

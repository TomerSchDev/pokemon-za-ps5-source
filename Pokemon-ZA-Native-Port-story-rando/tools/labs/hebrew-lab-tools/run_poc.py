"""One bounded run of the PC build for the Hebrew proof of concept.

Same pattern as research/pokeza-pc/run_probe.py (play mode) and pc-perf-c2/scripts/run_game.py: a data root of its
own (hebrew-lab/runs/<name>, which becomes the runtime's working directory), a fresh copy of a test save, its own
settings file, scripted input (LARECOMP_INPUT), no user input, captures at fixed frames (LARECOMP_SHOT_AT), and the
process terminated after the budget. The game files are passed by absolute path and only read.
Additions for this lab: a mods/ folder copied into the data root (runtime/services/fs.c LayeredFS), the settings'
text language, and LARECOMP_FONT (runtime/hle/pl.c: the system font the game's Korean / Chinese fonts resolve to).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
GAME = Path(r'C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc'
            r'\update-2.0.2-20261025\game')
EXE = LAB / 'runtime' / 'lasrecomp.exe'


def sha256(p):
    with open(p, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('name')
    p.add_argument('--game',type=Path,default=GAME,help='Read-only compiled game directory')
    p.add_argument('--save-src', type=Path, help='folder holding save_0/main (copied)')
    p.add_argument('--seconds', type=int, required=True)
    p.add_argument('--input', default='')
    p.add_argument('--shot-at', default='')
    p.add_argument('--capture-every', type=int, default=0)
    p.add_argument('--language', default='en-US')
    p.add_argument('--font', type=Path, help='LARECOMP_FONT')
    p.add_argument('--mods', type=Path, help='folder of mod folders, copied to <data root>/mods')
    p.add_argument('--cache-src', type=Path, help='a previous run whose cache/ seeds this one')
    p.add_argument('--env', nargs='*', default=[])
    a = p.parse_args()
    game=a.game.resolve()
    if not (game/'lasgame.dll').is_file() or not (game/'romfs.bin').is_file():
        p.error('Compiled game directory must contain lasgame.dll and romfs.bin')
    root = LAB / 'runs' / a.name
    if root.exists():
        p.error('run exists: %s' % root)
    root.mkdir(parents=True)
    (root / 'build').mkdir()
    save = root / 'save'
    if a.save_src:
        shutil.copytree(a.save_src / 'save_0', save / 'save_0')
        for f in save.rglob('*'):
            if f.is_file():
                os.chmod(f, 0o666)
    else:
        save.mkdir()
    if a.mods:
        shutil.copytree(a.mods, root / 'mods')
    if a.cache_src and (LAB / 'runs' / a.cache_src / 'cache').is_dir():
        shutil.copytree(LAB / 'runs' / a.cache_src / 'cache', root / 'cache')
    (root / 'larecomp.ini').write_text(
        'aspect = original\nfullscreen = 0\nvolume = 0\nshow_fps = 0\nfps60 = 0\nresolution = 1x\n'
        'dynamic_res = off\ntex_hd = 0\nantialias = smaa\nupscaler = fsr1\nlanguage = %s\nmouse_camera = off\n'
        'prompts = nintendo\n' % a.language, encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LARECOMP_', 'POKELAB_'))}
    env.update(LARECOMP_DATA_ROOT=str(root), LARECOMP_NO_UPDATE_CHECK='1', LARECOMP_REEXEC='20',
               LARECOMP_SAVE_DIR=str(save), LARECOMP_SETTINGS=str(root / 'larecomp.ini'),
               LARECOMP_SCREENSHOT_EVERY=str(a.capture_every), LARECOMP_WAIT_DUMP='10', LARECOMP_SKIP_WHY='1',
               LARECOMP_KBD_AUTO='Test', LARECOMP_NO_USER_INPUT='1')
    if a.input:
        env['LARECOMP_INPUT'] = a.input
    if a.shot_at:
        env['LARECOMP_SHOT_AT'] = a.shot_at
    if a.font:
        env['LARECOMP_FONT'] = str(a.font.resolve())
    for kv in a.env:
        k, v = kv.split('=', 1)
        env[k] = v
    record = dict(name=a.name, started_utc=datetime.now(timezone.utc).isoformat(), budget_seconds=a.seconds,
                  input_script=a.input, shot_at=a.shot_at, language=a.language, game=str(game),
                  runtime_sha256=sha256(EXE), font=str(a.font) if a.font else None,
                  font_sha256=sha256(a.font) if a.font else None,
                  mods=sorted(str(f.relative_to(root)) for f in (root / 'mods').rglob('*') if f.is_file())
                  if a.mods else [], extra_env={k: env[k] for k in env if k.startswith('LARECOMP_')})
    sv = save / 'save_0' / 'main'
    if sv.exists():
        record['save_before'] = dict(bytes=sv.stat().st_size, sha256=sha256(sv))
    record['address_collisions'] = 0
    for attempt in range(4):
        start = time.monotonic()
        with (root / 'stdout.log').open('wb') as out, (root / 'stderr.log').open('wb') as err:
            proc = subprocess.Popen([str(EXE), str(game), '--play'], cwd=root, env=env, stdout=out, stderr=err)
            record['pid'] = proc.pid
            (root / 'run.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
            print(json.dumps(dict(run=a.name, pid=proc.pid)), flush=True)
            try:
                record['exit_code'] = proc.wait(timeout=a.seconds)
                record['terminated_by_harness'] = False
            except subprocess.TimeoutExpired:
                proc.terminate()          # (this child only)
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
    if sv.exists():
        record['save_after'] = dict(bytes=sv.stat().st_size, sha256=sha256(sv))
    log = (root / 'stderr.log').read_text(encoding='utf-8', errors='replace')
    record['log_lines'] = [ln for ln in log.splitlines() if ln.startswith(('[fs] mod', '[fs] arc/data.trpfd',
                           '[fs] %d' % 0, '[pl]', '[fs] 1', '[fs] 2', '[fs] 3', '[fs] 4', '[fs] 5', '[fs] 6',
                           '[fs] 7', '[fs] 8', '[fs] 9')) and 'romfs reads' not in ln]
    (root / 'run.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({k: record[k] for k in ('exit_code', 'terminated_by_harness', 'elapsed_seconds',
                                             'captured_files', 'log_lines')}, indent=1), flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Bounded proof of the real UI-v2 Vulkan launcher, handoff and overlay, using an isolated data/save root.

Run on Windows with Python 3.12; --out must be a new directory. The game and fixture are only read.
The harness terminates only the child process it creates. Screenshots and the exact command/environment are retained.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('exe', 'game', 'dll', 'assets', 'save', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--seconds', type=int, default=100)
    parser.add_argument('--launcher-only', action='store_true')
    args = parser.parse_args()
    assert 1 <= args.seconds <= 180
    for path in (args.exe, args.dll, args.save, args.assets / 'v3.json', args.game / 'exefs/main'):
        assert path.is_file(), path
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shots = out / 'shots'
    shots.mkdir()
    (out / 'build').mkdir()
    (out / 'larecomp.ini').write_text('aspect = original\nfullscreen = 0\nvolume = 0\nshow_fps = 0\nfps60 = 0\n'
        'resolution = 1x\ndynamic_res = off\ntex_hd = 0\nantialias = smaa\nupscaler = fsr1\nlanguage = en-US\n'
        'mouse_camera = off\nprompts = nintendo\n', encoding='ascii')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LARECOMP_', 'ZA_UI_', 'ZA_MONEY_', 'ZA_PERF_'))}
    # A real Controller sequence: change levels/Alpha, inspect Wild, confirm a new run, and enter the game.
    script = '10:R1,20:DOWN,25:RIGHT,30:DOWN,35:DOWN,40:RIGHT,60:CIRCLE,70:DOWN,75:CROSS,85:CROSS'
    env.update(LARECOMP_DATA_ROOT=str(out), LARECOMP_SETTINGS=str(out / 'larecomp.ini'),
               LARECOMP_GAME_LIB=str(args.dll.resolve()), LARECOMP_PS5_LAUNCHER='1', LARECOMP_NO_UPDATE_CHECK='1',
               LARECOMP_NO_USER_INPUT='1', LARECOMP_REEXEC='20', LARECOMP_SCREENSHOT_EVERY='0',
               LARECOMP_SHOT_AT='120,550,650', LARECOMP_MENU_AT='500', LARECOMP_WINDOW_SHOT='550',
               LARECOMP_INPUT='240:A:8,420:A:8', ZA_UI_ASSETS=str(args.assets.resolve()), ZA_UI_DATA_ROOT=str(out),
               ZA_UI_SCRIPT=script, ZA_UI_SHOT_DIR=str(shots), ZA_UI_SHOT_FRAMES='5,50,80,95',
               ZA_UI_OVERLAY_SCRIPT='600:R1,620:DOWN,640:RIGHT', ZA_UI_EXIT_AFTER_LAUNCHER='1' if args.launcher_only else '0')
    command = [str(args.exe.resolve()), str(args.game.resolve())]
    record = {'command': command, 'exe_sha256': sha(args.exe), 'dll_sha256': sha(args.dll),
              'fixture_sha256_before': sha(args.save), 'fixture_used_as_input': False,
              'environment': {k: env[k] for k in env if k.startswith(('LARECOMP_', 'ZA_UI_'))},
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'seconds': args.seconds}
    started = time.monotonic()
    with (out / 'stdout.log').open('wb') as stdout, (out / 'stderr.log').open('wb') as stderr:
        proc = subprocess.Popen(command, cwd=out, env=env, stdout=stdout, stderr=stderr)
        record['pid'] = proc.pid
        (out / 'run.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        try:
            record['exit_code'] = proc.wait(timeout=args.seconds)
            record['terminated_by_harness'] = False
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                record['exit_code'] = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                record['exit_code'] = proc.wait()
            record['terminated_by_harness'] = True
    log = (out / 'stderr.log').read_text(errors='replace')
    record.update(elapsed_seconds=round(time.monotonic() - started, 3), fixture_sha256_after=sha(args.save),
                  fixture_unchanged=sha(args.save) == record['fixture_sha256_before'],
                  screenshots=[str(p.relative_to(out)) for p in sorted(out.rglob('*.png'))],
                  launcher_entered='launcher starting inside the game window' in log,
                  launcher_completed='handing the window to the game' in log,
                  overlay_presented='overlay: first game frame presented' in log,
                  fade_completed='launcher frame faded out' in log,
                  fatal_lines=[line for line in log.splitlines() if 'FATAL' in line or line.startswith('*** ')])
    reports = list((out / 'rando').glob('*/report.json')) if (out / 'rando').exists() else []
    record['created_reports'] = [str(p.relative_to(out)) for p in reports]
    for path in reports:
        report = json.loads(path.read_text(encoding='utf-8'))
        record['v3_algorithm'] = report.get('v3_algorithm')
        record['ui_options'] = report.get('ui_options')
    record['ok'] = (record['fixture_unchanged'] and record['launcher_completed'] and not record['fatal_lines'] and
                    record.get('v3_algorithm') == 'za202-randomizer-v3' and bool(record['screenshots']) and
                    (args.launcher_only or record['overlay_presented'] and record['fade_completed']))
    (out / 'run.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in record.items() if k not in ('environment', 'command')}, indent=2))
    return 0 if record['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

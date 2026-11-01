"""One bounded PC run of Pokemon Legends Z-A for the music-randomizer proof (no console, no real save).

Same pattern as hebrew-lab/tools/run_poc.py: a data root of its own (music-lab/runs/<name>, the runtime's working
directory), a COPY of a test save (by default the randomizer's own city template, never a player save), its own
settings file, scripted input, captures at fixed frames, and the process terminated after the budget. Game files are
passed by absolute path and only read. Additions for music:
  --rando-run DIR   copies a generated randomizer run folder to <root>/rando/<id> and sets LARECOMP_RANDO_SEED=<id>
                    (the runtime's rando_seed_dir: <id>/romfs is the first LayeredFS layer, exactly as on PS5);
                    the save is then that run's own starting save copy unless --save-src is given.
  --mods DIR        a folder of mod folders, copied to <root>/mods (LayeredFS), for isolated experiments.
  LARECOMP_LOG_READS=<root>/reads.log   every RomFS read (path, offset, size): Stream.pck reads identify music media.
  LARECOMP_AUDOUT_WAV=<root>/audio.wav  the game's mixed audout output (LARECOMP_NO_AUDIO=1: nothing to speakers).
The music-lab runtime is a byte-identical copy of hebrew-lab/runtime (never modified).
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

LAB = Path(r'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\music-lab')
GAME = Path(r'C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc'
            r'\update-2.0.2-20261025\game')
TEMPLATE = Path(r'C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc'
                r'\ingame-randomizer\prepared-streamed\city-save.bin')
EXE = LAB / 'runtime' / 'lasrecomp.exe'
RUNTIME_SHA256 = 'c74c94359182e6749b92eab82c066b6963dd33c25b0d0314e2a3667e1623e7fc'
TEMPLATE_SHA256 = 'f5c64116c3fa0c39b407272b0646212c7bb27fdbb5bfbbf3601e232ecebd3c27'


def sha256(p):
    with open(p, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('name')
    p.add_argument('--seconds', type=int, required=True)
    p.add_argument('--input', default='240:A:8,420:A:8')
    p.add_argument('--shot-at', default='')
    p.add_argument('--rando-run', type=Path)
    p.add_argument('--save-src', type=Path, help='a save_0/main file to copy (default: the run, else the template)')
    p.add_argument('--mods', type=Path)
    p.add_argument('--cache-src', type=Path, help='a previous music-lab run whose cache/ seeds this one')
    p.add_argument('--env', nargs='*', default=[])
    a = p.parse_args()
    assert sha256(EXE) == RUNTIME_SHA256, 'unexpected runtime'
    root = LAB / 'runs' / a.name
    if root.exists():
        p.error('run exists: %s' % root)
    root.mkdir(parents=True)
    (root / 'build').mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LARECOMP_', 'POKELAB_'))}
    record = dict(name=a.name, started_utc=datetime.now(timezone.utc).isoformat(), budget_seconds=a.seconds,
                  input_script=a.input, shot_at=a.shot_at, game=str(GAME), runtime_sha256=RUNTIME_SHA256)
    save_src = a.save_src
    if a.rando_run:
        rid = a.rando_run.name
        shutil.copytree(a.rando_run, root / 'rando' / rid)
        env['LARECOMP_RANDO_SEED'] = rid
        record['rando_run'] = rid
        report = json.loads((root / 'rando' / rid / 'report.json').read_text(encoding='utf-8'))
        record['rando_report_music'] = report.get('music')
        record['rando_files'] = {str(f.relative_to(root / 'rando' / rid)).replace('\\', '/'): sha256(f)
                                 for f in sorted((root / 'rando' / rid / 'romfs').rglob('*')) if f.is_file()}
        if save_src is None:
            save_src = root / 'rando' / rid / 'save' / 'save_0' / 'main'
    if save_src is None:
        save_src = TEMPLATE
        assert sha256(TEMPLATE) == TEMPLATE_SHA256
    save = root / 'save'
    (save / 'save_0').mkdir(parents=True)
    shutil.copyfile(save_src, save / 'save_0' / 'main')
    os.chmod(save / 'save_0' / 'main', 0o666)
    record['save_source'] = str(save_src)
    record['save_before'] = sha256(save / 'save_0' / 'main')
    if a.mods:
        shutil.copytree(a.mods, root / 'mods')
        record['mods'] = {str(f.relative_to(root / 'mods')).replace('\\', '/'): sha256(f)
                          for f in sorted((root / 'mods').rglob('*')) if f.is_file()}
    if a.cache_src and (LAB / 'runs' / a.cache_src / 'cache').is_dir():
        shutil.copytree(LAB / 'runs' / a.cache_src / 'cache', root / 'cache')
    (root / 'larecomp.ini').write_text(
        'aspect = original\nfullscreen = 0\nvolume = 100\nshow_fps = 0\nfps60 = 0\nresolution = 1x\n'
        'dynamic_res = off\ntex_hd = 0\nantialias = smaa\nupscaler = fsr1\nlanguage = en-US\nmouse_camera = off\n'
        'prompts = nintendo\n', encoding='utf-8')
    env.update(LARECOMP_DATA_ROOT=str(root), LARECOMP_NO_UPDATE_CHECK='1', LARECOMP_REEXEC='20',
               LARECOMP_SAVE_DIR=str(save), LARECOMP_SETTINGS=str(root / 'larecomp.ini'),
               LARECOMP_SCREENSHOT_EVERY='0', LARECOMP_WAIT_DUMP='10', LARECOMP_SKIP_WHY='1',
               LARECOMP_KBD_AUTO='Test', LARECOMP_NO_USER_INPUT='1', LARECOMP_NO_AUDIO='1',
               LARECOMP_LOG_READS=str(root / 'reads.log'), LARECOMP_AUDOUT_WAV=str(root / 'audio.wav'))
    if a.input:
        env['LARECOMP_INPUT'] = a.input
    if a.shot_at:
        env['LARECOMP_SHOT_AT'] = a.shot_at
    for kv in a.env:
        k, v = kv.split('=', 1)
        env[k] = v
    record['extra_env'] = {k: env[k] for k in env if k.startswith('LARECOMP_')}
    record['address_collisions'] = 0
    for attempt in range(4):
        start = time.monotonic()
        with (root / 'stdout.log').open('wb') as out, (root / 'stderr.log').open('wb') as err:
            proc = subprocess.Popen([str(EXE), str(GAME), '--play'], cwd=root, env=env, stdout=out, stderr=err)
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
            for f in ('reads.log', 'audio.wav'):
                if (root / f).exists():
                    (root / f).unlink()
            continue
        break
    record['elapsed_seconds'] = round(time.monotonic() - start, 3)
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    record['captured_files'] = sorted(str(f.relative_to(root)) for f in root.rglob('*.png') if f.stat().st_size)
    record['save_after'] = sha256(save / 'save_0' / 'main')
    log = (root / 'stderr.log').read_text(encoding='utf-8', errors='replace')
    record['log_lines'] = [ln for ln in log.splitlines()
                           if ln.startswith(('[fs] mod', '[fs] arc/data.trpfd', '[rando]')) or
                           ('romfs files replaced' in ln) or ('new romfs files' in ln)]
    record['crash_markers'] = [ln for ln in log.splitlines()
                               if any(k in ln for k in ('FATAL', 'abort', 'Abort', 'fault', 'crash', 'panic'))][:20]
    (root / 'run.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({k: record.get(k) for k in ('exit_code', 'terminated_by_harness', 'elapsed_seconds',
                                                 'captured_files', 'log_lines', 'crash_markers')}, indent=1),
          flush=True)


if __name__ == '__main__':
    main()

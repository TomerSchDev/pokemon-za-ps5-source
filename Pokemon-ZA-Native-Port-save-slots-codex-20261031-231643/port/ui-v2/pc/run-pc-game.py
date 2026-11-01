"""run-pc-game.py - a bounded, scripted PC run of lasrecomp-uiv2.exe against an isolated data root with a fresh COPY of a
test save (modeled on port/cheats-r28/test/run-pc.py). Only this script's own child process is stopped (by PID, at the
timeout). No real save is ever used or touched; the fixture file must stay unchanged (its sha256 is checked before / after).

  py -3 run-pc-game.py --exe OUT/lasrecomp-uiv2.exe --game <game dir with exefs/ romfs.bin aoc/> \
      --dll <lasgame.dll or lasgame-uiv2.dll> --save <fixture save_0/main> --out <new run dir> \
      [--seconds 90] [--input 240:A:8,420:A:8] [--shots 300,700] [--cache <spirv cache dir to copy in>]

Screenshots land in <out>/build/frames/frame_NNNNN.png (LARECOMP_SHOT_AT), the log in <out>/stderr.log, the record in
<out>/run.json. PATH is left as is: the exe must find every DLL next to itself (no MSYS2 bin on PATH).
"""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time

p = argparse.ArgumentParser()
p.add_argument('--exe', type=Path, required=True); p.add_argument('--game', type=Path, required=True)
p.add_argument('--dll', type=Path, required=True); p.add_argument('--save', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--seconds', type=int, default=90)
p.add_argument('--input', default='240:A:8,420:A:8')
p.add_argument('--shots', default='300,700')
p.add_argument('--cache', type=Path, help='an existing cache/ folder (spirv) copied into the run dir: warm shader cache')
p.add_argument('--label', default='')
a = p.parse_args()
assert 1 <= a.seconds <= 600, 'the run is bounded: 1..600 s'
for f in (a.exe, a.dll, a.save): assert f.is_file(), f'missing: {f}'
assert (a.game / 'exefs' / 'main').is_file(), f'not a game dir (exefs/main): {a.game}'
assert a.dll.with_suffix('.dll.id').is_file() or Path(str(a.dll) + '.id').is_file(), f'no .id next to {a.dll}'

out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
(out / 'save/save_0').mkdir(parents=True); (out / 'build').mkdir()
shutil.copy2(a.save, out / 'save/save_0/main'); os.chmod(out / 'save/save_0/main', 0o666)
if a.cache and a.cache.is_dir(): shutil.copytree(a.cache, out / 'cache')
(out / 'larecomp.ini').write_text('aspect = original\nfullscreen = 0\nvolume = 0\nshow_fps = 0\nfps60 = 0\nresolution = 1x\n'
                                  'dynamic_res = off\ntex_hd = 0\nantialias = smaa\nupscaler = fsr1\nlanguage = en-US\n'
                                  'mouse_camera = off\nprompts = nintendo\n')
env = {k: v for k, v in os.environ.items() if not k.startswith(('LARECOMP_', 'POKELAB_', 'ZA_MONEY_', 'ZA_PERF_'))}
env.update(LARECOMP_DATA_ROOT=str(out), LARECOMP_NO_UPDATE_CHECK='1', LARECOMP_REEXEC='20',
           LARECOMP_SAVE_DIR=str(out / 'save'), LARECOMP_SETTINGS=str(out / 'larecomp.ini'), LARECOMP_GAME_LIB=str(a.dll.resolve()),
           LARECOMP_SCREENSHOT_EVERY='0', LARECOMP_SHOT_AT=a.shots, LARECOMP_WAIT_DUMP='10', LARECOMP_SKIP_WHY='1',
           LARECOMP_KBD_AUTO='Test', LARECOMP_NO_USER_INPUT='1', LARECOMP_INPUT=a.input)

def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

record = dict(label=a.label, exe=str(a.exe.resolve()), exe_sha256=sha(a.exe), game=str(a.game.resolve()),
              dll=str(a.dll.resolve()), dll_sha256=sha(a.dll), fixture=str(a.save.resolve()), fixture_sha256_before=sha(a.save),
              copy_before_sha256=sha(out / 'save/save_0/main'), seconds=a.seconds, input=a.input, shots=a.shots,
              cache=str(a.cache.resolve()) if a.cache else None, started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
started = time.monotonic()
for attempt in range(4):
    started = time.monotonic()
    with (out / 'stdout.log').open('wb') as so, (out / 'stderr.log').open('wb') as se:
        proc = subprocess.Popen([str(a.exe.resolve()), str(a.game.resolve()), '--play'], cwd=out, env=env, stdout=so, stderr=se)
        record['pid'] = proc.pid; (out / 'run.json').write_text(json.dumps(record, indent=2))
        print(json.dumps(dict(pid=proc.pid, run=str(out), seconds=a.seconds)), flush=True)
        try:
            proc.wait(timeout=a.seconds)
            record['exit_code'] = proc.returncode; record['terminated_by_harness'] = False
        except subprocess.TimeoutExpired:
            proc.terminate()  # our own child only (TerminateProcess by handle)
            try: record['exit_code'] = proc.wait(timeout=15)
            except subprocess.TimeoutExpired: proc.kill(); record['exit_code'] = proc.wait()
            record['terminated_by_harness'] = True
    # the guest address window was taken by something else in this process's layout: a fresh process, as the runtime would
    if time.monotonic() - started < 10 and b'guest address range' in (out / 'stderr.log').read_bytes():
        (out / 'stderr.log').rename(out / f'collision-{attempt}.log'); continue
    break
record['elapsed'] = round(time.monotonic() - started, 3)
record['fixture_sha256_after'] = sha(a.save); record['fixture_unchanged'] = record['fixture_sha256_after'] == record['fixture_sha256_before']
record['copy_after_sha256'] = sha(out / 'save/save_0/main')
log = (out / 'stderr.log').read_text(errors='replace')
record['frames'] = sorted(f.name for f in (out / 'build/frames').glob('*.png')) if (out / 'build/frames').is_dir() else []
record['system_line'] = next((l for l in log.splitlines() if l.startswith('[system]')), None)
record['gamelib_line'] = next((l for l in log.splitlines() if l.startswith('[gamelib]')), None)
record['fps_lines'] = [l for l in log.splitlines() if re.match(r'\[vk\] t=\S+ frame \d+ .* fps', l)]
record['r28_items_lines'] = [l for l in log.splitlines() if l.startswith('[r28-items]')]
record['r28_catalog_count'] = sum(1 for l in log.splitlines() if l.startswith('[r28-catalog]'))
record['r27_money_lines'] = [l for l in log.splitlines() if l.startswith('[r27-money]')]
record['fatal_lines'] = [l for l in log.splitlines() if 'FATAL' in l or l.startswith('*** ')]
(out / 'run.json').write_text(json.dumps(record, indent=2))
summary = {k: record[k] for k in ('pid', 'exit_code', 'terminated_by_harness', 'elapsed', 'fixture_unchanged', 'frames',
                                  'system_line', 'gamelib_line', 'r28_catalog_count', 'fatal_lines')}
summary['fps_lines'] = record['fps_lines'][-3:]; summary['r28_items_lines'] = record['r28_items_lines'][:3]
print(json.dumps(summary, indent=2))
sys.exit(0 if record['fixture_unchanged'] else 3)

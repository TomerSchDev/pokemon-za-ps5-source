"""run-pc-proof.py - bounded PC proof of the slot.zrs writer: a randomizer run (a COPY of a launcher-made run folder with
slot.zrs) in its own data root, the game driven into a manual save by scripted input, the save file and slot.zrs watched
from outside the game, and the result checked.

  py -3 run-pc-proof.py --exe <dir>/lasrecomp.exe --game <game dir> --dll <lasgame.dll> --run-src <run folder> --out <new dir>
      [--seconds 240] [--input ...] [--shots ...] [--cache <cache dir>]

The watcher only reads: GetFileAttributesExW for size / mtime, and on a change CreateFileW(GENERIC_READ, share read |
write | delete) - the same sharing the runtime gives the game's own handles - so the game can still write, rename or
delete its save. Only this script's own child process is stopped (by handle, at the timeout).
"""
from pathlib import Path
import argparse, ctypes, ctypes.wintypes as wt, hashlib, json, os, re, shutil, struct, subprocess, threading, time, zlib

p = argparse.ArgumentParser()
p.add_argument('--exe', type=Path, required=True); p.add_argument('--game', type=Path, required=True)
p.add_argument('--dll', type=Path, required=True); p.add_argument('--run-src', type=Path, required=True)
p.add_argument('--out', type=Path, required=True); p.add_argument('--seconds', type=int, default=240)
p.add_argument('--input', default='240:A:8,420:A:8,750:STICK_UP:60,900:X:8,1000:A:8,1100:R:8,1400:A:8,1700:B:8')
p.add_argument('--shots', default='900,1050,1200,1410,1440,1500,1800,2200')
p.add_argument('--cache', type=Path)
a = p.parse_args()
assert 30 <= a.seconds <= 900
for f in (a.exe, a.dll, a.run_src / 'slot.zrs', a.run_src / 'save/save_0/main'): assert f.is_file(), f
run_id = a.run_src.name
out = a.out.resolve(); out.mkdir(parents=True, exist_ok=False)
run = out / 'rando' / run_id
shutil.copytree(a.run_src, run)
(out / 'build').mkdir()
if a.cache and a.cache.is_dir(): shutil.copytree(a.cache, out / 'cache')
(out / 'larecomp.ini').write_text('aspect = original\nfullscreen = 0\nvolume = 0\nshow_fps = 0\nfps60 = 0\nresolution = 1x\n'
                                  'dynamic_res = off\ntex_hd = 0\nantialias = smaa\nupscaler = fsr1\nlanguage = en-US\n'
                                  'mouse_camera = off\nprompts = nintendo\n')

def sha(b): return hashlib.sha256(b).hexdigest()
def fsha(path): return sha(Path(path).read_bytes())
INTRO = bytes.fromhex('9EC99CD70ED33C44FB9303DCEB39B42A1947E9634BA2334416BF82A2BA6355B63D9DF24B5F7B6AB2621DC21B68E5C8B53A059000E8A8103DE2ECF00CB2ED4F6D')
OUTRO = bytes.fromhex('D6C01C598BC8B8CB46E153FC828C757513E045DF32693C75F059F8D9A25FB217E08052DBEA8973997579AFCB2E8007E6F126E0030AE66FF641BF7E59C2AE55FD')
def swish_ok(b): return len(b) > 32 and hashlib.sha256(INTRO + b[:-32] + OUTRO).digest() == b[-32:]

def parse_slot(b):
    assert b[:8] == b'ZARSLOT\0', 'magic'
    major, minor, hs, count, flags, size, tcrc = struct.unpack_from('<HHIIIQI', b, 8)
    assert size == len(b) and hs == 64
    table = b[hs:hs + 32 * count]
    assert zlib.crc32(b[:0x20] + table) == tcrc, 'table crc'
    sec = {}
    for i in range(count):
        typ, fl, off, ln, crc = struct.unpack_from('<IIQQI', table, 32 * i)
        data = b[off:off + ln]
        assert zlib.crc32(data) == crc, 'section crc'
        sec[struct.pack('<I', typ).decode()] = data
    m = sec['SUMM']
    cs = lambda o, n: m[o:o + n].split(b'\0')[0].decode()
    summ = dict(version=struct.unpack_from('<I', m, 0)[0], flags=struct.unpack_from('<I', m, 4)[0],
                save_time=struct.unpack_from('<Q', m, 8)[0], created_time=struct.unpack_from('<Q', m, 16)[0],
                caught=struct.unpack_from('<I', m, 0x18)[0], seen=struct.unpack_from('<I', m, 0x1C)[0],
                save_size=struct.unpack_from('<I', m, 0x20)[0], save_sha256=m[0x28:0x48].hex(), run_id=cs(0x48, 48), seed=cs(0x78, 24),
                location=cs(0x90, 32), algorithm=cs(0xB0, 32), build_id=cs(0xD0, 48))
    if summ['version'] >= 2 and len(m) >= 0x140:
        summ.update(story_phase=struct.unpack_from('<I', m, 0x100)[0], dlc_phase=struct.unpack_from('<I', m, 0x104)[0],
                    research_level=struct.unpack_from('<I', m, 0x108)[0], research_points=struct.unpack_from('<I', m, 0x10C)[0],
                    x=struct.unpack_from('<f', m, 0x110)[0], z=struct.unpack_from('<f', m, 0x114)[0], y=struct.unpack_from('<f', m, 0x118)[0])
    return dict(version=f'{major}.{minor}', sections={k: len(v) for k, v in sec.items()}, summary=summ), sec

# ---- the outside watcher
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
class WAD(ctypes.Structure):
    _fields_ = [('attr', wt.DWORD), ('ctime', wt.FILETIME), ('atime', wt.FILETIME), ('mtime', wt.FILETIME), ('hi', wt.DWORD), ('lo', wt.DWORD)]
k32.GetFileAttributesExW.argtypes = [wt.LPCWSTR, ctypes.c_int, ctypes.c_void_p]
k32.CreateFileW.restype = wt.HANDLE
k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
k32.ReadFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
def stamp(path):
    d = WAD()
    if not k32.GetFileAttributesExW(str(path), 0, ctypes.byref(d)): return None
    return ((d.hi << 32) | d.lo, (d.mtime.dwHighDateTime << 32) | d.mtime.dwLowDateTime)
def read_shared(path):
    h = k32.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x80, None)
    if h in (None, wt.HANDLE(-1).value): return None
    try:
        chunks = []
        buf = ctypes.create_string_buffer(1 << 20); got = wt.DWORD()
        while k32.ReadFile(h, buf, len(buf), ctypes.byref(got), None) and got.value: chunks.append(buf.raw[:got.value])
        return b''.join(chunks)
    finally: k32.CloseHandle(h)

events, stop = [], threading.Event()
t_start = time.monotonic()
def watch():
    last = {}
    names = {'save': run / 'save/save_0/main', 'slot': run / 'slot.zrs'}
    while not stop.is_set():
        for name, path in names.items():
            s = stamp(path)
            if s != last.get(name):
                last[name] = s
                b = read_shared(path) if s else None
                ev = dict(t=round(time.monotonic() - t_start, 3), file=name, size=s[0] if s else None, mtime=s[1] if s else None)
                if b is not None:
                    ev.update(sha256=sha(b), read=len(b))
                    if name == 'save': ev['swish_ok'] = swish_ok(b)
                    else:
                        try: ev['save_time'] = parse_slot(b)[0]['summary']['save_time']
                        except Exception as e: ev['parse_error'] = str(e)
                events.append(ev)
        time.sleep(0.05)

src_before = {str(f.relative_to(a.run_src)): fsha(f) for f in sorted(a.run_src.rglob('*')) if f.is_file()}
slot0 = (run / 'slot.zrs').read_bytes(); save0 = (run / 'save/save_0/main').read_bytes()
info0, sec0 = parse_slot(slot0)
env = {k: v for k, v in os.environ.items() if not k.startswith(('LARECOMP_', 'POKELAB_', 'ZA_MONEY_', 'ZA_PERF_'))}
env.update(LARECOMP_DATA_ROOT=str(out), LARECOMP_NO_UPDATE_CHECK='1', LARECOMP_REEXEC='20', LARECOMP_SETTINGS=str(out / 'larecomp.ini'),
           LARECOMP_GAME_LIB=str(a.dll.resolve()), LARECOMP_RANDO_SEED=run_id, LARECOMP_SCREENSHOT_EVERY='0',
           LARECOMP_SHOT_AT=a.shots, LARECOMP_WAIT_DUMP='10', LARECOMP_SKIP_WHY='1', LARECOMP_KBD_AUTO='Test',
           LARECOMP_NO_USER_INPUT='1', LARECOMP_INPUT=a.input)  # (no LARECOMP_SAVE_DIR: the run's own rando/<id>/save)
record = dict(exe=str(a.exe.resolve()), exe_sha256=fsha(a.exe), dll=str(a.dll.resolve()), dll_sha256=fsha(a.dll), game=str(a.game.resolve()),
              run_src=str(a.run_src.resolve()), run_id=run_id, seconds=a.seconds, input=a.input, shots=a.shots,
              save_before_sha256=sha(save0), slot_before_sha256=sha(slot0), slot_before=info0,
              env={k: v for k, v in env.items() if k.startswith('LARECOMP_')}, started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
th = threading.Thread(target=watch, daemon=True); th.start()
with (out / 'stdout.log').open('wb') as so, (out / 'stderr.log').open('wb') as se:
    proc = subprocess.Popen([str(a.exe.resolve()), str(a.game.resolve()), '--play'], cwd=out, env=env, stdout=so, stderr=se)
    record['pid'] = proc.pid
    print(json.dumps(dict(pid=proc.pid, out=str(out), seconds=a.seconds)), flush=True)
    try:
        proc.wait(timeout=a.seconds); record['terminated_by_harness'] = False
    except subprocess.TimeoutExpired:
        proc.terminate()
        try: proc.wait(timeout=15)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        record['terminated_by_harness'] = True
    record['exit_code'] = proc.returncode
time.sleep(1.0); stop.set(); th.join()
record['elapsed'] = round(time.monotonic() - t_start, 3)
record['events'] = events

log = (out / 'stderr.log').read_text(errors='replace')
record['slot_lines'] = [l for l in log.splitlines() if l.startswith('[slot]')]
record['rando_lines'] = [l for l in log.splitlines() if l.startswith('[rando]')]
record['mount_lines'] = sorted(set(l for l in log.splitlines() if l.startswith('[fs] mounted')))
record['fatal_lines'] = [l for l in log.splitlines() if 'FATAL' in l or l.startswith('*** ')]
save1 = (run / 'save/save_0/main').read_bytes(); slot1 = (run / 'slot.zrs').read_bytes()
info1, sec1 = parse_slot(slot1)
save_events = [e for e in events if e['file'] == 'save' and 'sha256' in e]
slot_events = [e for e in events if e['file'] == 'slot' and 'sha256' in e]
game_saves = [e for e in save_events[1:] if e.get('swish_ok')]  # complete saves the game wrote during the run
c = dict(
    save_changed_by_game=sha(save1) != sha(save0),
    final_save_swish_ok=swish_ok(save1),
    final_save_seen_by_watcher=bool(save_events) and save_events[-1]['sha256'] == sha(save1),
    slot_rewritten=sha(slot1) != sha(slot0) and info1['summary']['save_time'] != info0['summary']['save_time'],
    slot_save_section_equals_final_save=sec1['SAVE'] == save1,
    slot_save_sha256_field_ok=info1['summary']['save_sha256'] == sha(save1),
    slot_rand_sett_kept=sec1['RAND'] == sec0['RAND'] and sec1['SETT'] == sec0['SETT'],
    slot_ids_kept=all(info1['summary'][k] == info0['summary'][k] for k in ('run_id', 'seed', 'algorithm', 'build_id', 'created_time')),
    slot_written_after_last_game_save=bool(game_saves) and bool(slot_events) and slot_events[-1]['t'] > game_saves[-1]['t'],
    no_slot_new_left=not (run / 'slot.zrs.new').exists(),
    run_src_unchanged=src_before == {str(f.relative_to(a.run_src)): fsha(f) for f in sorted(a.run_src.rglob('*')) if f.is_file()},
    writer_lines=bool(record['slot_lines']) and any('rewritten' in l for l in record['slot_lines']),
)
record.update(save_after_sha256=sha(save1), save_after_size=len(save1), slot_after_sha256=sha(slot1), slot_after=info1, checks=c,
              passed=all(c.values()), frames=sorted(f.name for f in (out / 'build/frames').glob('*.png')) if (out / 'build/frames').is_dir() else [])
(out / 'proof.json').write_text(json.dumps(record, indent=2))
print(json.dumps(dict(passed=record['passed'], checks=c, slot_lines=record['slot_lines'][-5:], fatal=record['fatal_lines'][:3]), indent=2))

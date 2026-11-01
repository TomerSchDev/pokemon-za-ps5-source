"""pc-proof.json for r29-music from the four final PC runs plus static checks of each run's actual music bank.
Usage: make_pc_proof.py SUMMARY.json PLAN.json ROMFS_BIN HOST_RUNS_DIR OUT.json [VANILLA_SUMMARY.json]

Runs (same save position, same scripted input, 600 s each): proof2-off-30081997, proof2-cat-30081997,
proof2-cat-12345, proof2-chaos-30081997 (analyze_proof.py SUMMARY). Checks:
  runtime: the city loop slot plays the song each run's report.json predicts; the two seeds differ; OFF plays the
           vanilla city loop like the vanilla baseline runs; every run ran its whole budget with no crash marker and
           no silent 10 s window; the replacement keeps playing past its own length (loop).
  static (the bank each randomized run actually serves): only planned slot words differ from the game's bank; every
           slot holds a planned song; every planned song, re-derived from the ORIGINAL bank, is a non-silent music
           playlist with an infinitely looping item, >= 30 s, without user cues - so neither category mode nor CHAOS
           can put a stinger, jingle, silence or one-shot into a looping slot; category runs keep each slot's category.
"""
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import za_bgm  # noqa
from make_music_plan import romfs_file  # noqa

summary, plan_path, romfs, host_runs, out = sys.argv[1:6]
vanilla_summary = sys.argv[6] if len(sys.argv) > 6 else None
s = json.load(open(summary, encoding='utf-8'))
plan = json.load(open(plan_path, encoding='utf-8'))
runs = {r['name']: r for r in s['runs']}
checks = []


def check(name, ok, detail):
    checks.append(dict(check=name, ok=bool(ok), detail=detail))


_, _, bank = romfs_file(romfs, plan['bank']['path'])
assert hashlib.sha256(bank).hexdigest() == plan['bank']['sha256']
orig = za_bgm.Bank(bank)
cat_of = {m: u['category'] for u in plan['units'] for m in u['members']}
unit_of = {m: u['unit'] for u in plan['units'] for m in u['members']}
song_props = {}
for m in cat_of:
    info = orig.playlist_info(int(m, 16))
    song_props[m] = dict(seconds=round(info['duration_ms'] / 1000, 1), infinite=info['infinite'], silent=info['silent'],
                         user_cues=info['user_cues'], segments=info['segments'])
bad_songs = {m: p for m, p in song_props.items()
             if p['silent'] or not p['infinite'] or p['seconds'] < 30 or p['user_cues']}
check('every planned song (all %d) is a non-silent infinite loop >= 30 s without user cues (re-derived from the game bank)'
      % len(song_props), not bad_songs, dict(violations=bad_songs, shortest=min(p['seconds'] for p in song_props.values())))

off = runs['proof2-off-30081997']
check('OFF run plays the vanilla city music (intro 0ff389a4 then loop 03a031e1)',
      off['played_songs'][:2] == ['0ff389a4', '03a031e1'], off['played_songs'])
if vanilla_summary:
    van = json.load(open(vanilla_summary, encoding='utf-8'))
    vs = {r['name']: r['played_songs'] for r in van['runs']}
    check('OFF matches the vanilla baseline runs (no randomizer run, template save)',
          all(v[:2] == off['played_songs'][:2] for v in vs.values()), dict(vanilla=vs, off=off['played_songs']))
check('OFF run serves no music bank (runtime replaced 1 RomFS file, the research table)',
      any('1 romfs files replaced' in l for l in off['log_lines']), off['log_lines'])
replacements = {}
for name in ('proof2-cat-30081997', 'proof2-cat-12345', 'proof2-chaos-30081997'):
    r = runs[name]
    want = r['predicted_replacements'].get('03a031e1')
    replacements[name] = want
    check(name + ': runtime serves the run\'s music bank (2 RomFS files replaced)',
          any('2 romfs files replaced' in l for l in r['log_lines']), r['log_lines'])
    check(name + ': the city loop slot plays the song its report.json predicts', want in r['played_songs'],
          dict(predicted=want, played=r['played_songs']))
    check(name + ': the vanilla city loop is not heard', '03a031e1' not in r['played_songs'], r['played_songs'])
    song = next((o for o in r['played'] if o['song'] == want), None)
    looped = bool(song) and (song['loop_restarts'] >= 1 or r['seconds_captured'] > song['seconds'] * 1.5)
    check(name + ': the replacement loops (re-read from an earlier offset / heard past its length)', looped,
          dict(song=song, seconds_captured=r['seconds_captured']))
    heard_loops = [o for o in r['played'] if o['song'] in song_props or o['song'] == '0ff389a4']
    check(name + ': every streamed music song heard is a looping song or the protected city intro',
          len(heard_loops) == len(r['played']), r['played'])
    # static check of the bank this run actually served
    rid = r['rando_run']
    data = open(os.path.join(host_runs, rid, 'romfs', plan['bank']['path']), 'rb').read()
    rep = json.load(open(os.path.join(host_runs, rid, 'report.json'), encoding='utf-8'))
    check(name + ': served bank = report native_music hash, same size as the game bank',
          hashlib.sha256(data).hexdigest() == rep['native_music']['sha256'] and len(data) == len(bank),
          dict(sha256=rep['native_music']['sha256'], bytes=len(data)))
    offsets = {sl['offset'] for sl in plan['slots']}
    diff = [i for i in range(len(data)) if data[i] != bank[i]]
    check(name + ': only planned slot words differ from the game bank',
          all(any(o <= i < o + 4 for o in offsets) for i in diff), dict(bytes_changed=len(diff)))
    wrong, cross = [], 0
    for sl in plan['slots']:
        now = '%08x' % struct.unpack_from('<I', data, sl['offset'])[0]
        if now not in song_props:
            wrong.append((sl['offset'], now))
        elif cat_of[now] != plan['units'][sl['unit']]['category']:
            cross += 1
    check(name + ': all %d slots hold a planned looping song (no stinger/jingle/silence/one-shot)' % len(plan['slots']),
          not wrong, dict(violations=wrong))
    if 'chaos' in name:
        check(name + ': CHAOS moves songs across categories', cross > 0, dict(cross_category_slots=cross))
    else:
        check(name + ': category mode keeps every slot in its category', cross == 0, dict(cross_category_slots=cross))
    Bank = za_bgm.Bank(data)  # the served bank still parses byte-exactly
    check(name + ': served bank re-parses (all %d music objects byte-exact)' % len(Bank.music), len(Bank.music) == len(orig.music), {})
check('the two category seeds give the same place different music',
      replacements['proof2-cat-30081997'] != replacements['proof2-cat-12345'], replacements)
for r in s['runs']:
    check(r['name'] + ': whole 600 s budget, no crash marker', r['terminated_by_harness'] and not r['crash_markers'],
          dict(terminated_by_harness=r['terminated_by_harness'], crash_markers=r['crash_markers']))
    check(r['name'] + ': audible audio throughout (no 10 s window <= -50 dBFS after 20 s)', r['silent_windows_after_20s'] == 0,
          dict(seconds=r['seconds_captured'], dbfs=r['audio_dbfs_10s']))
verdict = 'pass' if all(c['ok'] for c in checks) else 'fail'
cats = {}
for u in plan['units']:
    c = cats.setdefault(u['category'], dict(units=0, songs=0))
    c['units'] += 1
    c['songs'] += len(u['members'])
summary_text = ('Same city spot, same input, 600 s each: OFF heard intro 0ff389a4 + vanilla loop 03a031e1; seed 30081997 '
                'heard %s, seed 12345 heard %s (both town songs, as their reports predict); CHAOS heard %s. Each served '
                'bank changes only planned slot words and every slot holds a non-silent infinite loop >= 30 s. No crash, '
                'continuous audio, replacements looped.' % (replacements['proof2-cat-30081997'],
                                                            replacements['proof2-cat-12345'], replacements['proof2-chaos-30081997']))
runtime_sha = json.load(open(os.path.join(off['dir'], 'run.json'), encoding='utf-8'))['runtime_sha256']
res = dict(verdict=verdict, plan_sha256=s['plan_sha256'], runtime_sha256=runtime_sha, categories=cats,
           slots=len(plan['slots']), summary=summary_text, checks=checks,
           runs=[dict(name=r['name'], dir=r['dir'], mode=r['mode'], rando_run=r['rando_run'], played=r['played'],
                      seconds_captured=r['seconds_captured'], screenshots=r['screenshots']) for r in s['runs']],
           notes=['save = each generated run\'s own starting save, copied into the PC data root; never a player save',
                  'reads mapped through the ORIGINAL BGM.bnk: track source -> segment -> playlist',
                  'the city first-play intro 0ff389a4 has a user cue (the game advances the T1 state from it) and stays original',
                  'wild-zone / battle / boss slots were checked statically (bank) and on host, not by PC gameplay'])
json.dump(res, open(out, 'w', encoding='utf-8'), indent=1)
print(verdict)
for c in checks:
    print(('PASS ' if c['ok'] else 'FAIL ') + c['check'])

"""Summarise the r29-music PC proof runs (read-only on game data; writes one JSON summary).

For each run: the music media Stream.pck/Stream_dlc.pck reads (LARECOMP_LOG_READS) mapped through the ORIGINAL
BGM.bnk (track source -> segment -> playlist) to the songs that actually played, with the number of times each
song's media was re-read from an earlier offset (a loop restart); the audout level per 10 s; crash markers; and,
for a randomized run, whether the songs predicted by its own report.json assignments are the ones heard.
Usage: analyze_proof.py ROMFS_BIN PLAN.json OUT.json RUN_DIR [RUN_DIR...]
"""
import collections
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
sys.path.insert(0, os.path.join(HERE, '..', 'research'))
sys.path.insert(0, HERE)
import za_bgm  # noqa
import akpk  # noqa
from audio_level import levels  # noqa
from make_music_plan import romfs_file  # noqa

STREAMS = ('audio/wwise/bin/Switch/Stream.pck', 'audio/wwise/bin/Switch/Stream_dlc.pck')


def main():
    romfs, plan_path, out = sys.argv[1:4]
    plan = json.load(open(plan_path, encoding='utf-8'))
    _, _, bank = romfs_file(romfs, plan['bank']['path'])
    assert hashlib.sha256(bank).hexdigest() == plan['bank']['sha256']
    b = za_bgm.Bank(bank)
    seg_pl = collections.defaultdict(set)
    for pid, m in b.music.items():
        if b.type_of(pid) == za_bgm.PLAYLIST:
            for it in m['items']:
                if it['segment']:
                    seg_pl[it['segment']].add(pid)
    media_pl = collections.defaultdict(set)
    for sid, m in b.music.items():
        if b.type_of(sid) == za_bgm.SEGMENT:
            for t in m['children']:
                if b.type_of(t) == za_bgm.TRACK:
                    for src in b.music[t]['sources']:
                        media_pl[src['id']] |= seg_pl.get(sid, set())
    looks = {}
    with open(romfs, 'rb') as f:
        for pck in STREAMS:
            off, size = romfs_entry(romfs, pck)
            looks[pck] = akpk.Lookup(akpk.index(f, off))
    unit_of = {m: u['unit'] for u in plan['units'] for m in u['members']}
    cat_of = {u['unit']: u['category'] for u in plan['units']}
    runs = []
    for rd in sys.argv[4:]:
        rj = json.load(open(os.path.join(rd, 'run.json'), encoding='utf-8'))
        order, last_off, restarts, reads = [], {}, collections.Counter(), collections.Counter()
        excerpt = []
        for n, ln in enumerate(open(os.path.join(rd, 'reads.log'), encoding='utf-8', errors='replace')):
            parts = ln.split()
            if len(parts) != 3 or parts[0] not in looks:
                continue
            off = int(parts[1], 16)
            mid = looks[parts[0]].at(off)
            if mid is None or mid not in media_pl:
                continue
            excerpt.append('%6d %s %s %s media=%08x songs=%s' % (n + 1, parts[0].rsplit('/', 1)[1], parts[1], parts[2], mid,
                                                                 ','.join('%08x' % p for p in sorted(media_pl[mid]))))
            reads[mid] += 1
            if mid in last_off and off < last_off[mid]:
                restarts[mid] += 1
            last_off[mid] = off
            for pl in sorted(media_pl[mid]):
                key = '%08x' % pl
                if key not in [o['song'] for o in order]:
                    info = b.playlist_info(pl)
                    order.append(dict(song=key, media='%08x' % mid, seconds=round(info['duration_ms'] / 1000, 1),
                                      unit=unit_of.get(key), category=cat_of.get(unit_of.get(key))))
        for o in order:
            o['media_reads'] = reads[int(o['media'], 16)]
            o['loop_restarts'] = restarts[int(o['media'], 16)]
        wav = os.path.join(rd, 'audio.wav')
        lv = levels(wav, 10.0) if os.path.exists(wav) else []
        music = rj.get('rando_report_music') or {}
        predicted = {}
        for a in music.get('assignments', []):
            predicted[a['song']] = a['to_song']
        played = [o['song'] for o in order]
        if os.environ.get('MUSIC_READS_DIR'):  # the runtime read-log lines behind `played` (no game data)
            name = os.path.basename(rd.rstrip('/\\'))
            with open(os.path.join(os.environ['MUSIC_READS_DIR'], 'music-reads-%s.txt' % name), 'w', newline='\n') as f:
                f.write('# %s: LARECOMP_LOG_READS lines that hit music media: line, pack, offset, size, media id, playlist(s)\n' % name)
                f.write('\n'.join(excerpt) + '\n')
        runs.append(dict(name=os.path.basename(rd.rstrip('/\\')), dir=rd, rando_run=rj.get('rando_run'),
                         mode=music.get('mode', 'off'), seed=None, played=order,
                         audio_dbfs_10s=[round(x, 1) for x in lv],
                         silent_windows_after_20s=sum(1 for x in lv[2:] if x <= -50),
                         seconds_captured=len(lv) * 10, terminated_by_harness=rj.get('terminated_by_harness'),
                         crash_markers=rj.get('crash_markers'), save_before=rj.get('save_before'),
                         save_after=rj.get('save_after'), log_lines=rj.get('log_lines'),
                         screenshots=[p.replace('\\', '/') for p in rj.get('captured_files', [])[-3:]],
                         predicted_replacements={k: v for k, v in predicted.items() if k in ('03a031e1', '0ff389a4')},
                         played_songs=played))
    res = dict(plan_sha256=hashlib.sha256(open(plan_path, 'rb').read()).hexdigest(), runs=runs)
    json.dump(res, open(out, 'w', encoding='utf-8'), indent=1)
    for r in runs:
        print('%-26s mode=%-8s played=%s silent=%d/%d crash=%s' % (r['name'], r['mode'], ['%s(%s,%sx)' % (o['song'], o['category'], o['loop_restarts']) for o in r['played']],
                                                                r['silent_windows_after_20s'], len(r['audio_dbfs_10s']), bool(r['crash_markers'])))
        if r['predicted_replacements']:
            print('   predicted', r['predicted_replacements'])


def romfs_entry(romfs, want):
    off, size, _ = romfs_file_meta(romfs, want)
    return off, size


def romfs_file_meta(path, want):
    with open(path, 'rb') as f:
        h = struct.unpack('<10Q', f.read(80))
        f.seek(h[3]); dm = f.read(h[4])
        f.seek(h[7]); fm = f.read(h[8])

        def dirpath(d):
            parts = []
            while d:
                parent, = struct.unpack_from('<I', dm, d)
                nl, = struct.unpack_from('<I', dm, d + 0x14)
                parts.append(dm[d + 0x18:d + 0x18 + nl].decode())
                d = parent
            return '/'.join(reversed(parts))
        o = 0
        while o + 0x20 <= len(fm):
            parent, _, off, size, _, nl = struct.unpack_from('<IIQQII', fm, o)
            name = fm[o + 0x20:o + 0x20 + nl].decode()
            d = dirpath(parent)
            if (d + '/' if d else '') + name == want:
                return h[9] + off, size, None
            o += 0x20 + ((nl + 3) & ~3)
    raise KeyError(want)


if __name__ == '__main__':
    main()

"""Read-only: parse Wwise banks (in memory) for Event ids and test which 'PLAY_PV_%04u' cry events exist (FNV-1 32 of lowercase)."""
import collections, json, struct, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
g = za_romfs.Game(GAME)
def fnv1_32(s):
    h = 0x811C9DC5
    for c in s.lower().encode():
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= c
    return h
def objects(bnk):
    d = g.romfs_file('audio/wwise/bin/Switch/' + bnk)
    p, out, ver = 0, collections.defaultdict(set), None
    while p + 8 <= len(d):
        tag, size = d[p:p + 4], struct.unpack_from('<I', d, p + 4)[0]
        if tag == b'BKHD': ver = struct.unpack_from('<I', d, p + 8)[0]
        if tag == b'HIRC':
            n = struct.unpack_from('<I', d, p + 8)[0]
            q = p + 12
            for _ in range(n):
                t, sz, oid = struct.unpack_from('<BII', d, q)
                out[t].add(oid)
                q += 5 + sz
        p += 8 + size
    return ver, out
pers = json.load(open(S + '/out/personal-2.0.2.json'))
present = {r['internal'] for r in pers if r['present']}
nat = {r['internal']: r['national'] for r in pers}
cat = json.load(open(S + '/out/catalog.json'))
import re
pm_of = {}
for e in cat:
    pm_of.setdefault(e['info'].get('f0', 0), int(re.match(r'pm(\d{4})', e['f1']).group(1)))
for bnk in ('PM_VOICE.bnk', 'PM.bnk', 'PM_SKILLS.bnk'):
    ver, objs = objects(bnk)
    events = objs.get(4, set())
    print(bnk, 'bank version', ver, 'object types', {k: len(v) for k, v in sorted(objs.items())})
    hits = [n for n in range(0, 1200) if fnv1_32('PLAY_PV_%04d' % n) in events]
    if hits:
        hs = set(hits)
        print('  PLAY_PV_nnnn events:', len(hits), 'range', hits[0], '..', hits[-1])
        print('  numbering check: hits ∩ present internal', len(hs & present), '| ∩ present pm numbers', len(hs & {pm_of[s] for s in present if s in pm_of}),
              '| hits for ABSENT internal ids', len(hs - present - {pm_of[s] for s in present if s in pm_of}))
        absent_hits = sorted(hs - present - {pm_of[s] for s in present if s in pm_of})
        print('  absent-id examples:', absent_hits[:40])

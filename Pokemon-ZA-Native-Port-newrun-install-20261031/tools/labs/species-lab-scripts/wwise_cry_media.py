"""Read-only: for PLAY_PV_<species> events in PM_VOICE.bnk, follow Event -> Action -> Sound/Container -> source media id,
and check whether that media id exists in the bank's DIDX or in Stream.pck / Stream_dlc.pck file tables. In memory only."""
import collections, struct, sys, json
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
g = za_romfs.Game(GAME)
def fnv1_32(s):
    h = 0x811C9DC5
    for c in s.lower().encode():
        h = (h * 0x01000193) & 0xFFFFFFFF; h ^= c
    return h
d = g.romfs_file('audio/wwise/bin/Switch/PM_VOICE.bnk')
objs, didx = {}, set()
p = 0
while p + 8 <= len(d):
    tag, size = d[p:p + 4], struct.unpack_from('<I', d, p + 4)[0]
    if tag == b'DIDX':
        for q in range(p + 8, p + 8 + size, 12): didx.add(struct.unpack_from('<I', d, q)[0])
    if tag == b'HIRC':
        n = struct.unpack_from('<I', d, p + 8)[0]; q = p + 12
        for _ in range(n):
            t, sz, oid = struct.unpack_from('<BII', d, q)
            objs[oid] = (t, d[q + 9:q + 5 + sz]); q += 5 + sz
    p += 8 + size
def event_actions(body):
    # v145: action count as variable-length int (7-bit), then u32 ids
    n, shift, i = 0, 0, 0
    while True:
        b = body[i]; i += 1; n |= (b & 0x7F) << shift; shift += 7
        if not b & 0x80: break
    return [struct.unpack_from('<I', body, i + 4 * k)[0] for k in range(n)]
def action_target(body):
    atype, target = struct.unpack_from('<HI', body, 0)
    return atype, target
def sound_source(body):
    plugin, stype, src, memsize = struct.unpack_from('<IBII', body, 0)
    return stype, src
def children(body, depth=0, seen=None):
    # containers: any u32 (at any byte offset) that is a HIRC object id; recurse through non-sound objects
    seen = seen if seen is not None else set()
    out = []
    for i in range(0, len(body) - 3):
        x = struct.unpack_from('<I', body, i)[0]
        if x in objs and x not in seen:
            seen.add(x)
            t = objs[x][0]
            if t == 2: out.append(x)
            elif t in (5, 6, 7, 9, 10, 11, 12, 13) and depth < 4: out += children(objs[x][1], depth + 1, seen)
    return out
def media_for_event(name):
    eid = fnv1_32(name)
    if eid not in objs: return None
    out = set()
    for a in event_actions(objs[eid][1]):
        if a not in objs: continue
        atype, tgt = action_target(objs[a][1])
        if tgt not in objs: continue
        t, body = objs[tgt]
        snds = [tgt] if t == 2 else children(body)
        for s in snds:
            stype, src = sound_source(objs[s][1])
            out.add((stype, src))
    return out
def pck_ids(path):
    ids = set()
    off, size = g.entries[path]
    head = bytes(g.m[off:off + 8])
    assert head[:4] == b'AKPK'
    data = bytes(g.m[off:off + 8 + struct.unpack_from('<I', head, 4)[0]])  # header + tables only
    hsize, ver, lang, banks, streams = struct.unpack_from('<5I', data, 4)
    ext = struct.unpack_from('<I', data, 24)[0] if hsize > 24 else 0
    base = 28 if hsize > 24 else 24
    base += lang
    for tsize, wide in ((banks, False), (streams, False), (ext, True)):
        if tsize < 4: base += tsize; continue
        n = struct.unpack_from('<I', data, base)[0]
        ent = (tsize - 4) // n if n else 0
        for k in range(n):
            e = base + 4 + ent * k
            ids.add(struct.unpack_from('<Q' if ent == 24 else '<I', data, e)[0])
        base += tsize
    return ids, ver
stream, v1 = pck_ids('audio/wwise/bin/Switch/Stream.pck')
stream_dlc, v2 = pck_ids('audio/wwise/bin/Switch/Stream_dlc.pck')
print('PM_VOICE objects', len(objs), 'DIDX media', len(didx), '| Stream.pck ids', len(stream), '| Stream_dlc.pck ids', len(stream_dlc))
res = collections.Counter(); detail = {}
for sp in [25, 448, 652] + [235, 311, 312, 313, 314, 351, 926, 927, 932, 933, 934, 935, 936, 937, 944, 945, 957, 958, 959, 996, 997, 998, 999]:
    m = media_for_event('PLAY_PV_%04d' % sp)
    if m is None: detail[sp] = 'no event'; continue
    st = []
    for stype, src in sorted(m):
        where = 'bank' if src in didx else 'Stream.pck' if src in stream else 'Stream_dlc.pck' if src in stream_dlc else 'MISSING'
        st.append((stype, where))
    detail[sp] = st
for k, v in detail.items(): print(k, v)

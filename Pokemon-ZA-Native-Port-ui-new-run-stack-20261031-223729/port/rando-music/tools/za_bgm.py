"""Wwise v145 (2022.1) sound bank reader for Pokemon Legends: Z-A 2.0.2 BGM.bnk. Read-only, in memory.

Parses the bank sections, the HIRC object list, events and actions, and the four music object types (segment, track,
switch container, playlist container) completely: every music object must be consumed byte-exactly, otherwise
parsing raises. This exact-consumption check over all 2,026 music objects of the 2.0.2 bank is what pins the layout.
"""
import struct

HIRC_TYPES = {1: 'State', 2: 'Sound', 3: 'Action', 4: 'Event', 5: 'RanSeq', 6: 'Switch', 7: 'ActorMixer', 8: 'Bus',
              9: 'Layer', 10: 'MusicSegment', 11: 'MusicTrack', 12: 'MusicSwitch', 13: 'MusicRanSeq',
              14: 'Attenuation', 15: 'DialogueEvent', 16: 'FxShareSet', 17: 'FxCustom', 18: 'AuxBus', 19: 'LFO',
              20: 'Envelope', 21: 'AudioDevice', 22: 'TimeMod'}
SEGMENT, TRACK, SWITCH, PLAYLIST, EVENT, ACTION = 10, 11, 12, 13, 4, 3
SILENCE_PLUGIN = 0x00650002  # Wwise Silence source
ACTION_KINDS = {0x01: 'Stop', 0x02: 'Pause', 0x03: 'Resume', 0x04: 'Play', 0x12: 'SetState', 0x19: 'SetSwitch',
                0x1E: 'Seek', 0x21: 'PlayEvent'}


def fnv1_32(name):
    """Wwise short ID of a name (FNV-1 32 of the lower-cased name)."""
    h = 0x811C9DC5
    for c in name.lower().encode():
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= c
    return h


class _R:
    def __init__(self, b):
        self.b, self.i = b, 0

    def u8(self):
        v = self.b[self.i]
        self.i += 1
        return v

    def u16(self):
        v = struct.unpack_from('<H', self.b, self.i)[0]
        self.i += 2
        return v

    def u32(self):
        v = struct.unpack_from('<I', self.b, self.i)[0]
        self.i += 4
        return v

    def s32(self):
        v = struct.unpack_from('<i', self.b, self.i)[0]
        self.i += 4
        return v

    def f64(self):
        v = struct.unpack_from('<d', self.b, self.i)[0]
        self.i += 8
        return v

    def f32(self):
        v = struct.unpack_from('<f', self.b, self.i)[0]
        self.i += 4
        return v

    def skip(self, unit, count):
        self.i += unit * count

    def var(self):
        n = shift = 0
        while True:
            c = self.u8()
            n |= (c & 0x7F) << shift
            shift += 7
            if not c & 0x80:
                return n


def _node_base(r):
    out = {}
    r.u8()
    nfx = r.u8()
    if nfx:
        r.u8()
        for _ in range(nfx):
            r.u8(); r.u32(); r.u8(); r.u8()
    r.u8()
    for _ in range(r.u8()):
        r.u8(); r.u32(); r.u8()
    r.u8()
    out['bus'] = r.u32()
    out['parent'] = r.u32()
    r.u8()
    n = r.u8()
    r.i += n + 4 * n
    n = r.u8()
    r.i += n + 8 * n
    pos = r.u8()
    if pos & 1 and (pos >> 1) & 1:
        r.u8()
        if (pos >> 5) & 3:
            r.u8(); r.s32()
            r.skip(16, r.u32())
            npl = r.u32()
            r.i += 20 * npl
    if r.u8() & 0x08:
        r.i += 16
    r.u32()
    r.u8(); r.u8(); r.u16(); r.u8(); r.u8()
    for _ in range(r.var()):
        r.var(); r.u8(); r.u8()
    out['state_groups'] = []
    for _ in range(r.var()):
        g = r.u32()
        r.u8()
        out['state_groups'].append((g, [(r.u32(), r.u32()) for _ in range(r.var())]))
    out['rtpc'] = []
    for _ in range(r.u16()):
        rid = r.u32(); r.u8(); r.u8(); pid = r.var(); r.u32(); r.u8()
        r.skip(12, r.u16())
        out['rtpc'].append((rid, pid))
    return out


def _music_node(r):
    r.u8()
    base = _node_base(r)
    children = [r.u32() for _ in range(r.u32())]
    r.f64(); r.f64(); r.f32(); r.u8(); r.u8(); r.u8()
    r.skip(24, r.u32())
    return dict(base=base, children=children)


def _trans_node(r):
    m = _music_node(r)
    rules = []
    for _ in range(r.u32()):
        src = [r.s32() for _ in range(r.u32())]
        dst = [r.s32() for _ in range(r.u32())]
        r.i += 21 + 26
        seg = None
        if r.u8():
            seg = r.u32()
            r.i += 26
        rules.append(dict(src=src, dst=dst, transition_segment=seg))
    m['rules'] = rules
    return m


def parse_segment(body):
    r = _R(body)
    m = _music_node(r)
    m['duration_ms'] = r.f64()
    m['markers'] = []
    for _ in range(r.u32()):
        mid, pos = r.u32(), r.f64()
        end = body.index(0, r.i)
        m['markers'].append((mid, pos, bytes(body[r.i:end]).decode('latin-1')))
        r.i = end + 1
    if r.i != len(body):
        raise ValueError('segment layout: %d of %d bytes' % (r.i, len(body)))
    return m


def parse_track(body):
    r = _R(body)
    t = {'flags': r.u8(), 'sources': []}
    for _ in range(r.u32()):
        t['sources'].append(dict(plugin=r.u32(), stream=r.u8(), id=r.u32(), mem=r.u32(), bits=r.u8()))
    npl = r.u32()
    t['playlist'] = []
    for _ in range(npl):
        tid, sid, cache = r.u32(), r.u32(), r.u32()
        t['playlist'].append(dict(source=sid, play_at=r.f64(), begin_trim=r.f64(), end_trim=r.f64(), src_dur=r.f64()))
    if npl:
        r.u32()
    for _ in range(r.u32()):
        r.u32(); r.u32()
        r.skip(12, r.u32())
    t['base'] = _node_base(r)
    t['type'] = r.u8()
    if t['type'] == 3:
        r.u8(); r.u32(); r.u32()
        r.skip(4, r.u32())
        r.i += 32
    r.s32()
    if r.i != len(body):
        raise ValueError('track layout: %d of %d bytes' % (r.i, len(body)))
    return t


def parse_switch(body):
    r = _R(body)
    m = _trans_node(r)
    m['continue'] = r.u8()
    depth = r.u32()
    m['depth'] = depth
    m['groups'] = [r.u32() for _ in range(depth)]
    m['group_types'] = [r.u8() for _ in range(depth)]
    size = r.u32()
    m['mode'] = r.u8()
    m['tree_off'] = r.i
    if size % 12:
        raise ValueError('decision tree size')
    m['nodes'] = [struct.unpack_from('<IIHH', body, r.i + 12 * k) for k in range(size // 12)]
    r.i += size
    if r.i != len(body):
        raise ValueError('switch layout: %d of %d bytes' % (r.i, len(body)))
    return m


def parse_playlist(body):
    r = _R(body)
    m = _trans_node(r)
    m['items'] = []
    for _ in range(r.u32()):
        seg, iid, nch, rs, loop, lmin, lmax, w, avoid, usew, shuf = struct.unpack_from('<IIIIhhhIHBB', body, r.i)
        r.i += 30
        m['items'].append(dict(segment=seg, children=nch, rstype=rs, loop=loop))
    if r.i != len(body):
        raise ValueError('playlist layout: %d of %d bytes' % (r.i, len(body)))
    return m


def switch_leaves(sw):
    """[(keys per tree level below the root, audio node id, body offset of that id)]; key 0 = any."""
    nodes, depth, out = sw['nodes'], sw['depth'], []

    def walk(idx, level, keys):
        key, x, _, _ = nodes[idx]
        if level == depth:
            out.append((tuple(keys[1:] + [key]) if depth else (), x, sw['tree_off'] + 12 * idx + 4))
            return
        first, count = x & 0xFFFF, x >> 16
        if first + count > len(nodes):
            raise ValueError('decision tree child range')
        for c in range(first, first + count):
            walk(c, level + 1, keys + [key])
    walk(0, 0, [])
    return out


class Bank:
    """A parsed BGM bank. objects: id -> (type, file offset of the body, body bytes)."""

    def __init__(self, data):
        self.data = bytes(data)
        self.objects, self.order = {}, []
        self.hirc_range = None
        p = 0
        while p + 8 <= len(self.data):
            tag, size = self.data[p:p + 4], struct.unpack_from('<I', self.data, p + 4)[0]
            if tag == b'BKHD':
                self.version, self.bank_id = struct.unpack_from('<II', self.data, p + 8)
            if tag == b'HIRC':
                self.hirc_range = (p + 8, p + 8 + size)
                n = struct.unpack_from('<I', self.data, p + 8)[0]
                q = p + 12
                for _ in range(n):
                    t, sz, oid = struct.unpack_from('<BII', self.data, q)
                    if oid in self.objects:
                        raise ValueError('duplicate HIRC id %08x' % oid)
                    self.objects[oid] = (t, q + 9, self.data[q + 9:q + 5 + sz])
                    self.order.append(oid)
                    q += 5 + sz
                if q != p + 8 + size:
                    raise ValueError('HIRC size')
            p += 8 + size
        if p != len(self.data) or self.hirc_range is None or self.version != 145:
            raise ValueError('not a v145 bank with HIRC')
        self.music = {}
        parsers = {SEGMENT: parse_segment, TRACK: parse_track, SWITCH: parse_switch, PLAYLIST: parse_playlist}
        for oid in self.order:
            t, off, body = self.objects[oid]
            if t in parsers:
                self.music[oid] = parsers[t](body)
        self.events = {}
        for oid in self.order:
            t, off, body = self.objects[oid]
            if t != EVENT:
                continue
            r = _R(body)
            ids = [r.u32() for _ in range(r.var())]
            acts = []
            for a in ids:
                if a in self.objects and self.objects[a][0] == ACTION:
                    acts.append(self.action(a))
            self.events[oid] = acts

    def type_of(self, oid):
        o = self.objects.get(oid)
        return o[0] if o else None

    def action(self, aid):
        t, off, b = self.objects[aid]
        atype, target, _ = struct.unpack_from('<HIB', b, 0)
        i = 7
        n = b[i]
        i += 1 + 5 * n
        n = b[i]
        i += 1 + 9 * n
        r = dict(id=aid, kind=ACTION_NAMES(atype), target=target)
        if r['kind'] in ('SetState', 'SetSwitch'):
            r['group'], r['state'] = struct.unpack_from('<II', b, i)
        return r

    def playlist_info(self, pid):
        """structure of a playlist: segment count, loop vector, total segment duration, silent, media ids"""
        pl = self.music[pid]
        segs = [it['segment'] for it in pl['items'] if it['segment']]
        dur, silent, media, missing, cues = 0.0, True, [], False, 0
        for s in segs:
            if self.type_of(s) != SEGMENT:
                missing = True
                continue
            sg = self.music[s]
            dur += sg['duration_ms']
            # entry and exit cues are the first and last markers; anything else (or any named marker) is a user cue
            cues += max(0, len(sg['markers']) - 2) + sum(1 for m in sg['markers'] if m[2])
            for t in sg['children']:
                if self.type_of(t) != TRACK:
                    continue
                for src in self.music[t]['sources']:
                    if src['plugin'] != SILENCE_PLUGIN:
                        silent = False
                        media.append(src['id'])
        return dict(segments=len(segs), loops=[it['loop'] for it in pl['items']],
                    infinite=any(it['loop'] == 0 for it in pl['items']), duration_ms=dur, silent=silent,
                    media=sorted(set(media)), missing=missing, user_cues=cues)

    def parent_chain(self, oid):
        chain = []
        while oid and oid in self.music and oid not in chain:
            chain.append(oid)
            oid = self.music[oid]['base']['parent']
        return chain


def ACTION_NAMES(atype):
    return ACTION_KINDS.get(atype >> 8, 'Other%02x' % (atype >> 8))

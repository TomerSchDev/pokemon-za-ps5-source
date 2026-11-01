"""Strict, schema-guided FlatBuffers editing for the Z-A ik_event tables (no .bfbs exists for them).

parse(buf, pos, type)  -> Tab tree. Every field present in a vtable must be declared in SCHEMA, else ValueError
                          (so nothing can be silently dropped). Scalars stay as the table's original inline bytes.
Writer(buf).put(node)  -> appends a deep copy of node after the current end of buf (all uoffsets forward), returns
                          its position. With an empty buf + root=True it builds a whole new file.
set_str(buf, slot, s)  -> make the uoffset at SLOT point to string s (in place if same length and unshared,
                          otherwise a new string appended at the end).
Field kinds: 'raw' scalar | 'str' | 'vstr' vector of strings | 'T:Name' table | 'VT:Name' vector of tables.
"""
import struct

SCHEMA = {
    # phase.bin / dlc_phase.bin
    'PhaseRoot': {0: 'VT:Phase'},
    'Phase': {0: 'raw', 1: 'VT:CondGroup', 2: 'VT:Cmd'},
    'CondGroup': {0: 'VT:Cond'},
    'Cond': {0: 'str', 1: 'raw', 2: 'vstr'},
    'Cmd': {0: 'raw', 1: 'vstr'},
    # trigger_*.bin
    'TrigRoot': {0: 'VT:TrigWrap'},
    'TrigWrap': {0: 'T:Trigger'},
    'Trigger': {0: 'raw', 1: 'vstr', 2: 'VT:Case'},
    'Case': {0: 'VT:CondGroup', 1: 'VT:CmdGroup'},
    'CmdGroup': {0: 'VT:Cmd'},
}


class Str:
    __slots__ = ('b',)
    def __init__(s, b): s.b = b if isinstance(b, bytes) else b.encode()
    def text(s): return s.b.decode('utf-8', 'replace')
    def __repr__(s): return 'Str(%r)' % s.text()


class Vec:
    __slots__ = ('items', 'kind')
    def __init__(s, items, kind): s.items = items; s.kind = kind


class Tab:
    __slots__ = ('type', 'pos', 'offs', 'tsize', 'inline', 'kids')
    def __init__(s, typ, pos, offs, tsize, inline, kids):
        s.type, s.pos, s.offs, s.tsize, s.inline, s.kids = typ, pos, offs, tsize, bytearray(inline), kids

    def i32(s, f):
        o = s.offs[f] if f < len(s.offs) else 0
        return struct.unpack_from('<i', s.inline, o)[0] if o else None

    def set_i32(s, f, v):
        struct.pack_into('<i', s.inline, s.offs[f], v)

    def clone(s):
        return Tab(s.type, s.pos, list(s.offs), s.tsize, bytes(s.inline), {k: clone(v) for k, v in s.kids.items()})


def clone(n):
    if isinstance(n, Tab): return n.clone()
    if isinstance(n, Vec): return Vec([clone(x) for x in n.items], n.kind)
    return Str(n.b)


def u32(d, p): return struct.unpack_from('<I', d, p)[0]
def i32(d, p): return struct.unpack_from('<i', d, p)[0]
def u16(d, p): return struct.unpack_from('<H', d, p)[0]


def read_str(d, p):
    n = u32(d, p)
    return Str(bytes(d[p + 4:p + 4 + n]))


def parse(d, t, typ):
    sch = SCHEMA[typ]
    v = t - i32(d, t)
    vs, ts = u16(d, v), u16(d, v + 2)
    offs = [u16(d, v + 4 + 2 * i) for i in range((vs - 4) // 2)]
    kids = {}
    for f, o in enumerate(offs):
        if not o: continue
        if f not in sch: raise ValueError('%s @%d: undeclared field %d (offset %d)' % (typ, t, f, o))
        k = sch[f]
        if k == 'raw': continue
        q = t + o
        p = q + u32(d, q)
        if k == 'str': kids[f] = read_str(d, p)
        elif k == 'vstr': kids[f] = Vec([read_str(d, e + u32(d, e)) for e in (p + 4 + 4 * i for i in range(u32(d, p)))], 'str')
        elif k.startswith('T:'): kids[f] = parse(d, p, k[2:])
        elif k.startswith('VT:'): kids[f] = Vec([parse(d, e + u32(d, e), k[3:]) for e in (p + 4 + 4 * i for i in range(u32(d, p)))], k[3:])
        else: raise ValueError(k)
    return Tab(typ, t, offs, ts, d[t:t + ts], kids)


def root(d, typ):
    return parse(d, u32(d, 0), typ)


class Writer:
    def __init__(s, buf=None):
        s.b = bytearray(buf) if buf is not None else bytearray()

    def align(s, a, rem=0):
        while len(s.b) % a != rem: s.b.append(0)

    def put(s, n, root=False):
        if root:
            assert not s.b
            s.b += b'\0' * 4
        else:
            s.align(8)
        p = s._node(n)
        if root: struct.pack_into('<I', s.b, 0, p)
        return p

    def _node(s, n):
        if isinstance(n, Str):
            s.align(4)
            p = len(s.b)
            s.b += struct.pack('<I', len(n.b)) + n.b + b'\0'
            return p
        if isinstance(n, Vec):
            s.align(4)
            p = len(s.b)
            s.b += struct.pack('<I', len(n.items)) + b'\0' * (4 * len(n.items))
            for i, x in enumerate(n.items):
                c = s._node(x)
                slot = p + 4 + 4 * i
                struct.pack_into('<I', s.b, slot, c - slot)
            return p
        # table: vtable first (lower address), then the table at the same address mod 8 as the original
        s.align(2)
        vt = struct.pack('<HH', 4 + 2 * len(n.offs), n.tsize) + b''.join(struct.pack('<H', o) for o in n.offs)
        vp = len(s.b)
        s.b += vt
        s.align(8, n.pos % 8 if n.pos % 4 == 0 else 0)
        while len(s.b) % 4: s.b.append(0)
        p = len(s.b)
        s.b += n.inline
        struct.pack_into('<i', s.b, p, p - vp)
        for f in sorted(n.kids):
            c = s._node(n.kids[f])
            slot = p + n.offs[f]
            struct.pack_into('<I', s.b, slot, c - slot)
        return p


def str_refs(d, sp):
    """aligned uoffset slots in d that point at position sp"""
    return [q for q in range(0, len(d) - 3, 4) if u32(d, q) and q + u32(d, q) == sp]


def set_str(w, slot, text, refcache=None):
    """w: Writer over the file. Point SLOT at string TEXT (in place when safe, else appended)."""
    d = w.b
    sp = slot + u32(d, slot)
    old = bytes(d[sp + 4:sp + 4 + u32(d, sp)])
    new = text.encode()
    if old == new: return 'same'
    refs = refcache[sp] if refcache is not None and sp in refcache else str_refs(d, sp)
    if len(old) == len(new) and refs == [slot]:
        d[sp + 4:sp + 4 + len(new)] = new
        return 'inplace'
    np_ = w.put(Str(new))
    struct.pack_into('<I', d, slot, np_ - slot)
    return 'appended'


def to_py(n):
    """plain python view (for oracles / diffs)"""
    if isinstance(n, Str): return n.text()
    if isinstance(n, Vec): return [to_py(x) for x in n.items]
    out = {'$type': n.type}
    for f, o in enumerate(n.offs):
        if not o: continue
        if f in n.kids: out[f] = to_py(n.kids[f])
        else:
            w = (min([x for x in n.offs if x > o] + [n.tsize]) - o)
            out[f] = struct.unpack_from('<i', n.inline, o)[0] if w >= 4 else int.from_bytes(n.inline[o:o + w], 'little')
    return out

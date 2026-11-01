"""Schema-less heuristic FlatBuffers dumper -> nested python (dict of field idx -> value)."""
import struct, sys, json


class FB:
    def __init__(s, d): s.d = d; s.n = len(d)
    def u32(s, p): return struct.unpack_from('<I', s.d, p)[0]
    def i32(s, p): return struct.unpack_from('<i', s.d, p)[0]
    def u16(s, p): return struct.unpack_from('<H', s.d, p)[0]

    def is_str(s, p):
        if p < 0 or p + 4 > s.n or p % 4: return None
        n = s.u32(p)
        if n == 0:
            return '' if p + 4 < s.n and s.d[p + 4] == 0 else None
        if n > 4096 or p + 4 + n >= s.n or s.d[p + 4 + n] != 0: return None
        b = s.d[p + 4:p + 4 + n]
        try:
            t = b.decode('utf-8')
        except UnicodeDecodeError:
            return None
        if any(ord(c) < 32 for c in t): return None
        return t

    def table_ok(s, p):
        if p < 0 or p + 4 > s.n or p % 4: return False
        v = p - s.i32(p)
        if v < 0 or v + 4 > s.n or v % 2: return False
        vs, ts = s.u16(v), s.u16(v + 2)
        if not (4 <= vs <= 256 and vs % 2 == 0 and 4 <= ts <= 8192 and v + vs <= s.n and p + ts <= s.n): return False
        for i in range((vs - 4) // 2):
            o = s.u16(v + 4 + 2 * i)
            if o and (o < 4 or o >= ts): return False
        return True

    def fields(s, p):
        v = p - s.i32(p); vs, ts = s.u16(v), s.u16(v + 2)
        offs = [s.u16(v + 4 + 2 * i) for i in range((vs - 4) // 2)]
        return offs, ts


def dump(d, maxdepth=30):
    fb = FB(d)
    seen = set()
    forced_int = set()

    def node(p, depth):
        if depth > maxdepth: return '<depth>'
        offs, ts = fb.fields(p)
        present = sorted(o for o in offs if o)
        out = {}
        tg = {}
        for o in present:
            q = p + o
            if q % 4 == 0 and q + 4 <= fb.n:
                tg.setdefault(q + fb.u32(q), []).append(q)
        for k, qs in tg.items():
            if len(qs) > 1:
                for q in sorted(qs)[:-1]: forced_int.add(q)
        for i, o in enumerate(offs):
            if not o: continue
            q = p + o
            nxt = min([x for x in present if x > o] + [ts])
            width = nxt - o
            out[i] = val(q, width, depth, p + ts)
        return out

    def val(q, width, depth, tend=0):
        if width >= 4 and q % 4 == 0:
            r = fb.u32(q)
            t = q + r
            if r >= 4 and r < fb.n and t < fb.n and t >= tend and q not in forced_int:
                st = fb.is_str(t)
                if st is not None and st != '':
                    return st
                # vector?
                if t % 4 == 0 and t + 4 <= fb.n:
                    cnt = fb.u32(t)
                    if 0 < cnt < 50000 and t + 4 + 4 * cnt <= fb.n:
                        # vector of tables / strings
                        els = []
                        okall = True
                        for k in range(cnt):
                            e = t + 4 + 4 * k
                            tt = e + fb.u32(e)
                            if tt >= fb.n: okall = False; break
                            sv = fb.is_str(tt)
                            if sv is not None: els.append(sv); continue
                            if fb.table_ok(tt) and tt not in seen:
                                els.append(('T', tt)); continue
                            okall = False; break
                        if okall and not fb.table_ok(t):
                            res = []
                            for e in els:
                                if isinstance(e, tuple):
                                    seen.add(e[1]); res.append(node(e[1], depth + 1))
                                else:
                                    res.append(e)
                            return res
                if fb.table_ok(t) and t not in seen:
                    seen.add(t)
                    return node(t, depth + 1)
                if st == '':
                    return ''
        if width >= 8 and q % 8 == 0 and width == 8:
            return struct.unpack_from('<q', fb.d, q)[0]
        if width >= 4:
            v = fb.i32(q)
            return v
        if width == 2: return fb.u16(q)
        return fb.d[q]

    root = fb.u32(0)
    return node(root, 0)


if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    r = dump(d)
    json.dump(r, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

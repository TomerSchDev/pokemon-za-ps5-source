"""Heuristic schema-less FlatBuffers walker (read-only), for exploring Trinity files.
Usage: fbwalk.py <file> [max_depth] [max_vec]"""
import struct, sys

def u32(d, p): return struct.unpack_from('<I', d, p)[0]
def i32(d, p): return struct.unpack_from('<i', d, p)[0]
def u16(d, p): return struct.unpack_from('<H', d, p)[0]

def try_string(d, p):
    if p + 4 > len(d): return None
    n = u32(d, p)
    if n > 4096 or p + 4 + n >= len(d): return None
    if d[p + 4 + n] != 0: return None
    s = d[p + 4:p + 4 + n]
    if n == 0 or all(32 <= c < 127 for c in s):
        return s.decode('ascii')
    return None

def try_table(d, p):
    if p + 4 > len(d) or p % 4: return None
    vt = p - i32(d, p)
    if vt < 0 or vt + 4 > len(d) or vt % 2: return None
    vsz, tsz = u16(d, vt), u16(d, vt + 2)
    if vsz < 4 or vsz % 2 or vsz > 200 or tsz < 4 or tsz > 4096 or vt + vsz > len(d): return None
    offs = [u16(d, vt + 4 + 2 * i) for i in range((vsz - 4) // 2)]
    if any(o and (o < 4 or o >= tsz) for o in offs): return None
    return offs, tsz

def field_sizes(offs, tsz):
    present = sorted(o for o in offs if o)
    size = {}
    for i, o in enumerate(present):
        nxt = present[i + 1] if i + 1 < len(present) else tsz
        size[o] = nxt - o
    return size

def walk(d, p, depth, maxd, maxv, ind=''):
    t = try_table(d, p)
    if not t:
        print(ind + '<not a table @%x>' % p); return
    offs, tsz = t
    sz = field_sizes(offs, tsz)
    for i, o in enumerate(offs):
        if not o:
            continue
        fp = p + o
        s = sz[o]
        desc = None
        if s >= 4 and fp % 4 == 0:
            tgt = fp + u32(d, fp)
            st = try_string(d, tgt) if tgt < len(d) else None
            if st is not None:
                print(f'{ind}f{i}: str "{st}"'); continue
            if tgt < len(d) and tgt % 4 == 0 and depth < maxd:
                n = u32(d, tgt) if tgt + 4 <= len(d) else None
                # vector of offsets to tables/strings?
                if n is not None and 0 < n < 100000 and tgt + 4 + 4 * n <= len(d):
                    e0 = tgt + 4 + u32(d, tgt + 4)
                    if e0 < len(d) and (try_table(d, e0) or try_string(d, e0) is not None):
                        print(f'{ind}f{i}: vec[{n}]')
                        for k in range(min(n, maxv)):
                            ep = tgt + 4 + 4 * k
                            ep += u32(d, ep)
                            st = try_string(d, ep)
                            if st is not None:
                                print(f'{ind}  [{k}] "{st}"')
                            else:
                                print(f'{ind}  [{k}] table')
                                walk(d, ep, depth + 1, maxd, maxv, ind + '    ')
                        continue
                if try_table(d, tgt):
                    print(f'{ind}f{i}: table')
                    walk(d, tgt, depth + 1, maxd, maxv, ind + '    ')
                    continue
                if n is not None and n < 4096 and tgt + 4 + n <= len(d):
                    raw = d[tgt + 4:tgt + 4 + min(n * 4, 64)]
                    print(f'{ind}f{i}: vec?[{n}] raw {raw.hex()}'); continue
        raw = d[fp:fp + min(s, 16)]
        vals = []
        if s >= 4: vals.append('u32=%d f=%.4g' % (u32(d, fp), struct.unpack_from('<f', d, fp)[0]))
        if s == 2 or s == 3: vals.append('u16=%d' % u16(d, fp))
        if s == 1: vals.append('u8=%d' % d[fp])
        print(f'{ind}f{i}: scalar({s}) {raw.hex()} ' + ' '.join(vals))

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    maxd = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    maxv = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    root = u32(d, 0)
    print('size', len(d), 'root @%x' % root, 'ident', d[4:8])
    walk(d, root, 0, maxd, maxv)

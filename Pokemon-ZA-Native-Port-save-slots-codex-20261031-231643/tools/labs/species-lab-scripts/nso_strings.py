"""Read-only: decompress the 2.0.2 exefs/main NSO in memory (pure-Python LZ4) and list strings matching a regex.
Usage: nso_strings.py <regex> [limit]    (nothing written to disk)"""
import re, struct, sys
MAIN = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/exefs/main'

def lz4_block(src, size):
    dst = bytearray()
    i, n = 0, len(src)
    while i < n:
        tok = src[i]; i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1; lit += b
                if b != 255: break
        dst += src[i:i + lit]; i += lit
        if i >= n: break
        off = src[i] | (src[i + 1] << 8); i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]; i += 1; ml += b
                if b != 255: break
        ml += 4
        start = len(dst) - off
        if off >= ml:
            dst += dst[start:start + ml]
        else:
            for k in range(ml): dst.append(dst[start + k])
    assert len(dst) == size, (len(dst), size)
    return bytes(dst)

def image():
    raw = open(MAIN, 'rb').read()
    assert raw[:4] == b'NSO0'
    flags = struct.unpack_from('<I', raw, 0xC)[0]
    segs = []
    for i in range(3):
        fo, mo, ds = struct.unpack_from('<III', raw, 0x10 + i * 0x10)
        cs = struct.unpack_from('<I', raw, 0x60 + i * 4)[0]
        d = raw[fo:fo + cs]
        if flags & (1 << i): d = lz4_block(d, ds)
        segs.append((mo, d))
    return segs

if __name__ == '__main__':
    pat = re.compile(sys.argv[1].encode())
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    segs = image()
    out = []
    for si, (mo, d) in enumerate(segs):
        if si == 0: continue  # code
        for m in re.finditer(rb'[ -~]{4,}', d):
            if pat.search(m.group()): out.append((mo + m.start(), m.group().decode()))
    print('matches', len(out))
    for off, s in out[:limit]: print('%08x %s' % (off, s))

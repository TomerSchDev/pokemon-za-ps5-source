"""Read-only audit of the 2.0.2 main NSO behind the static findings in analysis/dynamic-timing-design-HE.md.

  python3 -I audit_nso.py <exefs/main>      (needs liblz4.so.1 or the lz4 module; prints JSON, writes nothing)

Reproduces: the duration table; every adrp-materialisation of the table page (offsets 0xe18..0xe48) and every
relocation pointing into the table; the three step-holder vtables and their GOT slots; the GOT slot of the
0x610b900 singleton; the strings the consumers use; the RC3 data/flag addresses' segments.
"""
import json
import struct
import sys
from pathlib import Path


def lz4_decompress(data, size):
    try:
        import lz4.block
        return lz4.block.decompress(data, uncompressed_size=size)
    except ImportError:
        import ctypes
        import ctypes.util
        lib = ctypes.CDLL(ctypes.util.find_library('lz4') or 'liblz4.so.1')
        lib.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        lib.LZ4_decompress_safe.restype = ctypes.c_int
        out = ctypes.create_string_buffer(size)
        assert lib.LZ4_decompress_safe(data, out, len(data), size) == size
        return out.raw


def load(path):
    raw = Path(path).read_bytes()
    assert raw[:4] == b'NSO0'
    flags = struct.unpack_from('<I', raw, 0xC)[0]
    segs = []
    for i in range(3):
        fo, mo, size = struct.unpack_from('<III', raw, 0x10 + 0x10 * i)
        comp = struct.unpack_from('<I', raw, 0x60 + 4 * i)[0]
        data = raw[fo:fo + comp]
        segs.append((mo, lz4_decompress(data, size) if flags & (1 << i) else data))
    bss = struct.unpack_from('<I', raw, 0x3C)[0]
    img = bytearray((segs[2][0] + len(segs[2][1]) + bss + 0xFFF) & ~0xFFF)
    for mo, data in segs:
        img[mo:mo + len(data)] = data
    return raw[0x40:0x60].rstrip(b'\0').hex(), segs, img


def relocs(img):
    u32 = lambda o: struct.unpack_from('<I', img, o)[0]
    u64 = lambda o: struct.unpack_from('<Q', img, o)[0]
    mod0 = u32(4)
    rel = lambda i: mod0 + struct.unpack_from('<i', img, mod0 + 4 + 4 * i)[0]
    dyn, o = {}, rel(0)
    while True:
        tag, val = u64(o), u64(o + 8)
        o += 16
        if tag == 0:
            break
        dyn.setdefault(tag, val)
    out = []
    relr, where = dyn.get(36, 0), 0  # DT_RELR (packed R_AARCH64_RELATIVE; the word holds the addend)
    for i in range(dyn.get(35, 0) // 8):
        e = u64(relr + 8 * i)
        if not e & 1:
            out.append((e, 1027, u64(e)))
            where = e + 8
            continue
        for b in range(1, 64):
            if (e >> b) & 1:
                out.append((where + (b - 1) * 8, 1027, u64(where + (b - 1) * 8)))
        where += 63 * 8
    for bt, st in ((7, 8), (23, 2)):  # DT_RELA/RELASZ, DT_JMPREL/PLTRELSZ
        if bt in dyn:
            for i in range(dyn[st] // 24):
                ro, ri, ra = struct.unpack_from('<QQq', img, dyn[bt] + 24 * i)
                out.append((ro, ri & 0xffffffff, ra))
    return out, (rel(1), rel(2))


def cstr(img, off):
    return img[off:img.index(b'\0', off)].decode('utf-8', 'replace')


def main(path):
    build, segs, img = load(path)
    w = lambda a: struct.unpack_from('<I', img, a)[0]
    text_end = segs[0][0] + len(segs[0][1])
    rl, bss = relocs(img)
    rel = {o: a for o, t, a in rl if t == 1027}
    out = {'build_id': build,
           'segments': [[hex(m), hex(m + len(d))] for m, d in segs], 'bss': [hex(bss[0]), hex(bss[1])],
           'table_0x3393e20': list(struct.unpack_from('<5Q', img, 0x3393e20)),
           'table_page_refs': [], 'relocs_into_table': [], 'holders': {}, 'strings': {}}
    for a in range(0, text_end - 4, 4):  # every adrp to page 0x3393000, then its user with offset 0xe18..0xe48
        x = w(a)
        if (x & 0x9f000000) != 0x90000000:
            continue
        imm = ((((x >> 5) & 0x7ffff) << 2) | ((x >> 29) & 3)) << 12
        if imm & (1 << 32):
            imm -= 1 << 33
        if ((a & ~0xfff) + imm) & 0xffffffffffff != 0x3393000:
            continue
        rd = x & 31
        for k in range(1, 12):
            y = w(a + 4 * k)
            if (y >> 5) & 31 != rd:
                continue
            if (y & 0xff800000) == 0x91000000:
                off = (y >> 10) & 0xfff
            elif (y & 0xffc00000) in (0xf9400000, 0xfd400000):
                off = ((y >> 10) & 0xfff) * 8
            else:
                continue
            if 0xe18 <= off <= 0xe48:
                out['table_page_refs'].append({'adrp': hex(a), 'offset': hex(off), 'insn': '%08x' % y})
            break
    out['relocs_into_table'] = [[hex(o), hex(a)] for o, a in rel.items() if 0x3393e18 <= a <= 0x3393e48]
    for name, vt in (('2-slot', 0x3c1a138), ('vector', 0x3c1cbf8), ('11-slot', 0x3d84a40)):
        out['holders'][name] = {'vptr': hex(vt), 'slots': [hex(rel.get(vt + 8 * i, 0)) for i in range(4)],
                                'got': [hex(o) for o, a in rel.items() if a == vt - 0x10]}
    out['flag_singleton_got'] = [hex(o) for o, a in rel.items() if a == 0x610b900]
    for a in (0x3393df8, 0x3393e0b, 0x32281ca, 0x328b74e, 0x31bb20f):
        out['strings'][hex(a)] = cstr(img, a)
    out['rc3_scratch_0x617a700'] = 'beyond BSS end' if 0x617a700 >= bss[1] else 'inside BSS'
    out['flag_0x610b980'] = 'BSS' if bss[0] <= 0x610b980 < bss[1] else 'other'
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])

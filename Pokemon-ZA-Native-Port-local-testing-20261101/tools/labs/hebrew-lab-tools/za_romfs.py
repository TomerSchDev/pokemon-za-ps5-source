"""Read-only access to Pokemon Legends Z-A game files: RomFS image -> arc/data.trpfs (ONEPACK) -> files by path.

Never writes to the game files. Output goes only where the caller asks (inside hebrew-lab).
Based on the layouts in pokeza-recomp tools/za/trinity.py and prompt_textures.py.
"""
import ctypes
import mmap
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
OOZ = os.path.join(HERE, 'bin', 'ooz.dll')


def fnv1a64(s):
    h = 0xCBF29CE484222645
    for c in (s.encode('utf-8') if isinstance(s, str) else s):
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


class FB:  # minimal flatbuffers reader
    def __init__(s, m): s.m = m
    def u32(s, p): return struct.unpack_from('<I', s.m, p)[0]
    def u64(s, p): return struct.unpack_from('<Q', s.m, p)[0]

    def table(s, p):
        vt = p - struct.unpack_from('<i', s.m, p)[0]
        n = (struct.unpack_from('<H', s.m, vt)[0] - 4) // 2
        out = []
        for i in range(n):
            o = struct.unpack_from('<H', s.m, vt + 4 + 2 * i)[0]
            out.append(p + o if o else None)
        return out

    def vec(s, fp):
        v = fp + s.u32(fp)
        return s.u32(v), v + 4

    def string(s, p):
        p += s.u32(p)
        n = s.u32(p)
        return bytes(s.m[p + 4:p + 4 + n]).decode('utf-8')


class Oodle:
    def __init__(self, path=OOZ):
        os.add_dll_directory(os.path.dirname(os.path.abspath(path)))
        self.lib = ctypes.CDLL(os.path.abspath(path))
        self.lib.ooz_decompress.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]

    def unpack(self, comp, size, raw):
        if comp == 0xFF or size == len(raw):
            return bytes(raw)
        out = ctypes.create_string_buffer(size + 64)
        if self.lib.ooz_decompress(bytes(raw), len(raw), out, size) != size:
            raise ValueError('ooz')
        return out.raw[:size]


class Game:
    """romfs.bin (read-only) with its ONEPACK."""

    def __init__(self, romfs_bin):
        self.f = open(romfs_bin, 'rb')
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        h = struct.unpack_from('<10Q', self.m, 0)
        assert h[0] == 0x50, 'not a RomFS image'
        dm = memoryview(self.m)[h[3]:h[3] + h[4]]
        fm = memoryview(self.m)[h[7]:h[7] + h[8]]

        def dir_path(d):
            parts = []
            while d:
                parent, = struct.unpack_from('<I', dm, d)
                nl, = struct.unpack_from('<I', dm, d + 0x14)
                parts.append(bytes(dm[d + 0x18:d + 0x18 + nl]).decode())
                d = parent
            return '/'.join(reversed(parts))

        self.entries = {}
        o = 0
        while o + 0x20 <= len(fm):
            parent, _, off, size, _, nl = struct.unpack_from('<IIQQII', fm, o)
            name = bytes(fm[o + 0x20:o + 0x20 + nl]).decode()
            d = dir_path(parent)
            self.entries[(d + '/' if d else '') + name] = (h[9] + off, size)
            o += 0x20 + ((nl + 3) & ~3)
        self.oodle = Oodle()
        start, size = self.entries['arc/data.trpfs']
        self.pack = memoryview(self.m)[start:start + size]
        self.fb = FB(self.pack)
        assert bytes(self.pack[:8]) == b'ONEPACK\0'
        rt = self.fb.u64(8)
        t = self.fb.table(rt + self.fb.u32(rt))
        n, hp = self.fb.vec(t[0])
        n2, op = self.fb.vec(t[1])
        assert n == n2
        trpfd = FB(self.romfs_file('arc/data.trpfd'))
        dt = trpfd.table(trpfd.u32(0))
        nn, np_ = trpfd.vec(dt[1])
        self.pack_names = [trpfd.string(np_ + 4 * i) for i in range(nn)]
        byhash = {fnv1a64(s): s for s in self.pack_names}
        self.packs = []      # [(name, [record...])]
        self.files = {}      # file hash -> record
        for i in range(n):
            off = self.fb.u64(op + 8 * i)
            ph = self.fb.u64(hp + 8 * i)
            name = byhash.get(ph, 'unknown-%016x' % ph)
            pt = self.fb.table(off + self.fb.u32(off))
            nf, fh = self.fb.vec(pt[0])
            nf2, fp = self.fb.vec(pt[1])
            assert nf == nf2
            recs = []
            for j in range(nf):
                e = fp + 4 * j
                ft = self.fb.table(e + self.fb.u32(e))
                nbytes, dp = self.fb.vec(ft[4])
                comp = self.pack[ft[1]] if len(ft) > 1 and ft[1] else 0xFF
                size = self.fb.u64(ft[3]) if len(ft) > 3 and ft[3] else nbytes
                r = dict(hash=self.fb.u64(fh + 8 * j), data=dp, csize=nbytes, size=size, comp=comp, pack=name)
                recs.append(r)
                self.files.setdefault(r['hash'], r)
            self.packs.append((name, recs))

    def romfs_file(self, path):
        off, size = self.entries[path]
        return bytes(self.m[off:off + size])

    def unpack(self, r):
        return self.oodle.unpack(r['comp'], r['size'], self.pack[r['data']:r['data'] + r['csize']])

    def has(self, path):
        return fnv1a64(path) in self.files

    def read(self, path):
        """a file by its game path: the RomFS's own, else the packed one"""
        if path in self.entries:
            return self.romfs_file(path)
        r = self.files.get(fnv1a64(path))
        if r is None:
            raise KeyError(path)
        return self.unpack(r)


def pack_name_for(path):
    """arc/<path without slashes>.trpak: how data.trpfd names a pack after its (first) file"""
    return 'arc/' + path.replace('/', '') + '.trpak'

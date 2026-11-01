"""Read supplied Violet ONEPACK and Arceus/Sword GFPAK assets without unpacking entire games.

Layout references: pkZukan/PokeDocs and KillzXGaming/Switch-Toolbox GFPAK.cs.
The supplied games are always opened read-only. No keys or executable code are loaded from them.
"""
from pathlib import Path
import mmap
import struct
import sys
import zlib

BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE / 'hebrew-lab' / 'tools'))
from za_romfs import FB, Oodle, fnv1a64


class TrinitySource:
    def __init__(self, root):
        self.root = Path(root)
        self.handle = (self.root / 'arc/data.trpfs').open('rb')
        self.mapping = mmap.mmap(self.handle.fileno(), 0, access=mmap.ACCESS_READ)
        self.pack = memoryview(self.mapping)
        self.oodle = Oodle()
        fb = FB(self.pack)
        if self.pack[:8] != b'ONEPACK\0':
            raise ValueError('Not ONEPACK')
        root_at = fb.u64(8)
        table = fb.table(root_at + fb.u32(root_at))
        n, hashes = fb.vec(table[0])
        n2, offsets = fb.vec(table[1])
        if n != n2:
            raise ValueError('ONEPACK index count mismatch')
        fd = FB((self.root / 'arc/data.trpfd').read_bytes())
        fields = fd.table(fd.u32(0))
        count, ptr = fd.vec(fields[1])
        self.pack_names = [fd.string(ptr + i * 4) for i in range(count)]
        names = {fnv1a64(name): name for name in self.pack_names}
        self.files, self.packs = {}, []
        for i in range(n):
            off = fb.u64(offsets + 8 * i)
            name = names.get(fb.u64(hashes + 8 * i), f'unknown-{i}')
            fields = fb.table(off + fb.u32(off))
            count, hp = fb.vec(fields[0])
            count2, fp = fb.vec(fields[1])
            if count != count2:
                raise ValueError('TRPAK index count mismatch')
            records = []
            for j in range(count):
                entry = fp + j * 4
                fs = fb.table(entry + fb.u32(entry))
                length, at = fb.vec(fs[4])
                record = dict(hash=fb.u64(hp + j * 8), data=at, csize=length,
                              size=fb.u64(fs[3]) if len(fs) > 3 and fs[3] else length,
                              comp=self.pack[fs[1]] if len(fs) > 1 and fs[1] else 0xFF, pack=name)
                if at + length > len(self.pack):
                    raise ValueError('TRPAK payload outside source file')
                self.files.setdefault(record['hash'], record)
                records.append(record)
            self.packs.append((name, records))

    def has(self, path):
        return (self.root / path).is_file() or fnv1a64(path) in self.files

    def unpack(self, record):
        raw = self.pack[record['data']:record['data'] + record['csize']]
        return self.oodle.unpack(record['comp'], record['size'], raw)

    def read(self, path):
        physical = self.root / path
        if physical.is_file():
            return physical.read_bytes()
        return self.unpack(self.files[fnv1a64(path)])

    def close(self):
        self.pack.release()
        self.mapping.close()
        self.handle.close()


def lz4_block(raw, size):
    """Bounded LZ4 raw block decoder, avoiding an extra installed dependency."""
    out, at = bytearray(), 0
    while at < len(raw):
        token = raw[at]
        at += 1
        n = token >> 4
        if n == 15:
            while True:
                extension = raw[at]
                at += 1
                n += extension
                if extension != 255:
                    break
        out += raw[at:at + n]
        at += n
        if at == len(raw):
            break
        offset = struct.unpack_from('<H', raw, at)[0]
        at += 2
        n = (token & 15) + 4
        if (token & 15) == 15:
            while True:
                extension = raw[at]
                at += 1
                n += extension
                if extension != 255:
                    break
        if not offset or offset > len(out) or len(out) + n > size:
            raise ValueError('Invalid LZ4 match')
        for _ in range(n):
            out.append(out[-offset])
    if len(out) != size:
        raise ValueError(f'LZ4 output size mismatch: {len(out)} vs {size}')
    return bytes(out)


class Gfpak:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        d = self.data
        if d[:8] != b'GFLXPACK':
            raise ValueError('Not GFPAK: ' + str(path))
        self.version, _, count, folders = struct.unpack_from('<4I', d, 8)
        info, hashes, folder_array = struct.unpack_from('<3Q', d, 0x18)
        self.files = []
        self.oodle = None
        # FolderArrayOffset is the first folder section; older versions also have an offset table.
        folder_names = {}
        candidates = [folder_array]
        if folder_array + 8 <= len(d):
            candidates.append(struct.unpack_from('<Q', d, folder_array)[0])
        for candidate in candidates:
            try:
                pos, mapping = candidate, {}
                for _ in range(folders):
                    folder_hash, number, _pad = struct.unpack_from('<QII', d, pos)
                    pos += 16
                    if number > count:
                        raise ValueError('bad folder count')
                    for _ in range(number):
                        file_hash, index, _pad = struct.unpack_from('<QII', d, pos)
                        pos += 16
                        if index >= count:
                            raise ValueError('bad index')
                        mapping[index] = (folder_hash, file_hash)
                if len(mapping) == count:
                    folder_names = mapping
                    break
            except (ValueError, struct.error):
                continue
        for i in range(count):
            level, comp, size, csize, _pad, offset = struct.unpack_from('<HHIIIQ', d, info + i * 24)
            if offset + csize > len(d):
                raise ValueError('GFPAK payload outside archive')
            folder_hash, filename_hash = folder_names.get(i, (0, 0))
            self.files.append(dict(hash=struct.unpack_from('<Q', d, hashes + i * 8)[0],
                                   filename_hash=filename_hash, folder_hash=folder_hash,
                                   size=size, csize=csize, comp=comp, data=offset))

    def unpack(self, record):
        d = self.data[record['data']:record['data'] + record['csize']]
        if record['comp'] == 0:
            result = d
        elif record['comp'] == 1:
            result = zlib.decompress(d)
        elif record['comp'] == 2:
            result = lz4_block(d, record['size'])
        elif record['comp'] == 3:
            self.oodle = self.oodle or Oodle()
            result = self.oodle.unpack(3, record['size'], d)
        else:
            raise ValueError('Unknown GFPAK compression')
        if len(result) != record['size']:
            raise ValueError('GFPAK decompression size mismatch')
        return result

    def read_name(self, name):
        hash_value = fnv1a64(name)
        matches = [r for r in self.files if hash_value in (r['hash'], r['filename_hash'])]
        if len(matches) != 1:
            raise KeyError(name)
        return self.unpack(matches[0])

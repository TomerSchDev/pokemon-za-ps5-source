#!/usr/bin/env python3
"""Check that conversion retains runtime registration and initialization data."""
import json
import pathlib
import struct
import sys

class Elf:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.f = self.path.open('rb')
        h = struct.unpack('<16sHHIQQQIHHHHHH', self.f.read(64))
        assert h[0][:6] == b'\x7fELF\x02\x01', path
        self.phdr = []
        for i in range(h[10]):
            self.f.seek(h[5] + i * h[9])
            p = struct.unpack('<IIQQQQQQ', self.f.read(56))
            if p[0] == 1:
                self.phdr.append(p)
        self.sections = {}
        if h[12]:
            self.f.seek(h[6] + h[13] * h[11])
            nameshdr = struct.unpack('<IIQQQQIIQQ', self.f.read(64))
            self.f.seek(nameshdr[4])
            names = self.f.read(nameshdr[5])
            for i in range(h[12]):
                self.f.seek(h[6] + i * h[11])
                s = struct.unpack('<IIQQQQIIQQ', self.f.read(64))
                name = names[s[0]:].split(b'\0', 1)[0].decode()
                self.sections[name] = s

    def bytes_at(self, addr, size):
        for p in self.phdr:
            if p[3] <= addr and addr + size <= p[3] + p[5]:
                self.f.seek(p[2] + addr - p[3])
                return self.f.read(size)
        raise ValueError(f'{self.path}: range {addr:x}+{size:x} absent from file-backed PT_LOAD')

source, converted = map(Elf, sys.argv[1:3])
results = []
for name in ('hle_impls', 'services', 'resets', '.init_array', '.data.rel.ro'):
    s = source.sections[name]
    assert s[5] > 0, f'empty registration section {name}'
    a = source.bytes_at(s[3], s[5])
    b = converted.bytes_at(s[3], s[5])
    assert a == b, f'conversion changed {name}'
    results.append({'section': name, 'address': hex(s[3]), 'bytes': s[5], 'preserved': True})
tables = []
if len(sys.argv) > 3:
    symbols = {}
    for line in pathlib.Path(sys.argv[3]).read_text().splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in ('main_fn_count', 'sdk_fn_count', 'main_fn_addrs', 'sdk_fn_addrs'):
            symbols[fields[2]] = int(fields[0], 16)
    for prefix in ('main', 'sdk'):
        count = struct.unpack('<Q', source.bytes_at(symbols[prefix + '_fn_count'], 8))[0]
        assert count > 1000, f'{prefix} has an incomplete game table'
        addr = symbols[prefix + '_fn_addrs']
        a = source.bytes_at(addr, count * 8)
        assert a == converted.bytes_at(addr, count * 8), f'{prefix} address table changed during conversion'
        guest = struct.unpack(f'<{count}Q', a)
        assert all(x % 4 == 0 for x in guest), f'{prefix}: unaligned ARM64 address'
        assert all(x < y for x, y in zip(guest, guest[1:])), f'{prefix}: table not strictly sorted'
        tables.append({'module': prefix, 'functions': count, 'first': hex(guest[0]), 'last': hex(guest[-1]), 'preserved': True})
print(json.dumps({'source': str(source.path), 'converted': str(converted.path),
                  'preserved_sections': results, 'game_tables': tables}, indent=2))

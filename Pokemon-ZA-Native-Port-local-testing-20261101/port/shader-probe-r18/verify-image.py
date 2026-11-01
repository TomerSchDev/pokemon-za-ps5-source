"""Verify constructor, constant and code bytes survive native title conversion."""
import json
import pathlib
import struct
import sys

class Elf:
    def __init__(self, path):
        self.data = pathlib.Path(path).read_bytes()
        h = struct.unpack_from('<16sHHIQQQIHHHHHH', self.data)
        assert h[0][:6] == b'\x7fELF\x02\x01'
        self.loads = [struct.unpack_from('<IIQQQQQQ', self.data, h[5]+i*h[9]) for i in range(h[10])]
        self.loads = [p for p in self.loads if p[0] == 1]
        self.sections = {}
        if h[12]:
            names = struct.unpack_from('<IIQQQQIIQQ', self.data, h[6]+h[13]*h[11])
            names = self.data[names[4]:names[4]+names[5]]
            for i in range(h[12]):
                section = struct.unpack_from('<IIQQQQIIQQ', self.data, h[6]+i*h[11])
                name = names[section[0]:].split(b'\0', 1)[0].decode()
                self.sections[name] = section

    def at(self, address, size):
        for p in self.loads:
            if p[3] <= address and address+size <= p[3]+p[5]:
                offset = p[2]+address-p[3]
                return self.data[offset:offset+size]
        raise ValueError('Address absent from load segments')

def main():
    source, converted = map(Elf, sys.argv[1:3])
    results = []
    for name in ('.init_array', '.data.rel.ro', '.text', '.rodata'):
        s = source.sections[name]
        assert s[5] > 0, name
        assert source.at(s[3], s[5]) == converted.at(s[3], s[5]), name
        results.append(dict(section=name, bytes=s[5], preserved=True))
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()

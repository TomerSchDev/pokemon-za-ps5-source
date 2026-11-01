"""Game Freak message files (Gen 8/9 Switch games; same layout in Pokemon Legends Z-A):

  <name>.dat  UTF-16LE lines, each XOR-obfuscated with a rolling 16-bit key (pkNX TextFile layout)
  <name>.tbl  AHTB label table: u32 count, then (u64 FNV-1a-64 of the label, u16 length incl. NUL, label bytes)

Lines are decoded to a token form that round-trips exactly:
  plain text, '\\n' = U+000A, and control sequences as {VAR xxxx:aaaa,bbbb} (0x0010, count, type, args...).
The original code units are kept, so encode(decode(x)) == x byte for byte.
"""
import struct

KEY_BASE = 0x7C89
KEY_ADVANCE = 0x2983
VAR = 0x0010


def _xor_line(units, key):
    out = []
    for u in units:
        out.append(u ^ key)
        key = ((key << 3) | (key >> 13)) & 0xFFFF
    return out


class MsgFile:
    def __init__(self, data):
        sections, nlines, total, initial_key, sec_off = struct.unpack_from('<HHIII', data, 0)
        assert sections == 1, 'expected one section'
        self.initial_key = initial_key
        self.header_extra = data[0x10:sec_off]
        sec_len, = struct.unpack_from('<I', data, sec_off)
        self.lines = []      # list of lists of u16 (without the NUL terminator), decrypted
        self.params = []     # per-line u16 (the table's 2nd field after the length)
        key = KEY_BASE
        for i in range(nlines):
            off, length, param = struct.unpack_from('<IHH', data, sec_off + 4 + 8 * i)
            raw = struct.unpack_from('<%dH' % length, data, sec_off + off)
            units = _xor_line(raw, key)
            key = (key + KEY_ADVANCE) & 0xFFFF
            if units and units[-1] == 0:
                units = units[:-1]
            else:
                raise ValueError('line %d not NUL terminated' % i)
            self.lines.append(units)
            self.params.append(param)

    def encode(self):
        n = len(self.lines)
        table = bytearray()
        body = bytearray()
        key = KEY_BASE
        pos = 4 + 8 * n
        for units, param in zip(self.lines, self.params):
            u = list(units) + [0]
            enc = _xor_line(u, key)
            key = (key + KEY_ADVANCE) & 0xFFFF
            b = struct.pack('<%dH' % len(enc), *enc)
            if len(u) % 2:          # 4-byte alignment of each line (as the game's files do)
                b += b'\0\0'
            table += struct.pack('<IHH', pos + len(body), len(u), param)
            body += b
        section = struct.pack('<I', 4 + len(table) + len(body)) + table + body
        sec_off = 0x10 + len(self.header_extra)
        head = struct.pack('<HHIII', 1, n, len(section), self.initial_key, sec_off) + self.header_extra
        return bytes(head + section)


def decode_units(units):
    """u16 list -> token string"""
    out = []
    i = 0
    while i < len(units):
        u = units[i]
        if u == VAR and i + 2 <= len(units):
            count = units[i + 1]
            args = units[i + 2:i + 2 + count]
            out.append('{VAR ' + ':'.join(['%04X' % args[0]] + ([','.join('%04X' % a for a in args[1:])] if len(args) > 1 else [])) + '}')
            i += 2 + count
            continue
        if u == 0x7B or u == 0x7D:      # literal braces, escaped
            out.append('{{' if u == 0x7B else '}}')
        elif u == 0x0A:
            out.append('\n')
        elif 0xD800 <= u < 0xDC00 and i + 1 < len(units):
            out.append(chr(0x10000 + ((u - 0xD800) << 10) + (units[i + 1] - 0xDC00)))
            i += 1
        else:
            out.append(chr(u))
        i += 1
    return ''.join(out)


def encode_text(s):
    """token string -> u16 list"""
    units = []
    i = 0
    while i < len(s):
        if s.startswith('{{', i):
            units.append(0x7B); i += 2; continue
        if s.startswith('}}', i):
            units.append(0x7D); i += 2; continue
        if s.startswith('{VAR ', i):
            j = s.index('}', i)
            body = s[i + 5:j]
            parts = body.split(':')
            args = [int(parts[0], 16)] + ([int(x, 16) for x in parts[1].split(',')] if len(parts) > 1 and parts[1] else [])
            units += [VAR, len(args)] + args
            i = j + 1
            continue
        c = ord(s[i])
        if c >= 0x10000:
            c -= 0x10000
            units += [0xD800 + (c >> 10), 0xDC00 + (c & 0x3FF)]
        else:
            units.append(c)
        i += 1
    return units


def read_tbl(data):
    assert data[:4] == b'AHTB'
    n, = struct.unpack_from('<I', data, 4)
    p = 8
    out = []
    for _ in range(n):
        h, ln = struct.unpack_from('<QH', data, p)
        p += 10
        name = data[p:p + ln - 1].decode('utf-8')
        p += ln
        out.append((h, name))
    return out


def fnv1a64(s):
    h = 0xCBF29CE484222645
    for c in s.encode('utf-8'):
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h

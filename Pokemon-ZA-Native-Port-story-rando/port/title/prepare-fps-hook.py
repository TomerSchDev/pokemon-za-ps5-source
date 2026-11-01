"""Verify 2.0.2 and patch one isolated translated unit. Original AOT stays intact."""
from pathlib import Path
import hashlib, json, struct, sys

source, nso_path, out = map(Path, sys.argv[1:])
raw = nso_path.read_bytes()
assert raw[:4] == b'NSO0'
assert raw[0x40:0x60].rstrip(b'\0').hex() == 'b1f12fd919eae86ab8a978317677e64bce443d1f'
# Inspect only the compressed text segment: no game data is modified.
file_off, mem_off, text_size = struct.unpack_from('<III', raw, 0x10)
size = struct.unpack_from('<I', raw, 0x60)[0]
code = raw[file_off:file_off+size]
if struct.unpack_from('<I', raw, 0xC)[0] & 1:
    try:
        import lz4.block
        code = lz4.block.decompress(code, uncompressed_size=text_size)
    except ImportError:
        import ctypes
        assert 0 < text_size < 256 * 1024 * 1024
        lib = ctypes.CDLL('liblz4.so.1')
        lib.LZ4_decompress_safe.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        lib.LZ4_decompress_safe.restype = ctypes.c_int
        dest = ctypes.create_string_buffer(text_size)
        assert lib.LZ4_decompress_safe(code, dest, len(code), text_size) == text_size
        code = dest.raw
assert struct.unpack_from('<I', code, 0x1b296d8-mem_off)[0] == 0x39c08134
data = source.read_bytes()
assert hashlib.sha256(data).hexdigest() == '6023cb91e1283a959791f350e8c523394f8d4be31a5b50d27cb85890aacdab68'
before = ('L_7001b296d4:;\n'
    '    { uint64_t ea = c->x[19] + 0x40ull; uint64_t v = LD64(ea); c->x[9] = (uint64_t)(v); }\n'
    '    { uint64_t ea = c->x[9] + 0x20ull; uint64_t v = (uint64_t)(int64_t)(int8_t)LD8(ea); c->x[20] = (uint32_t)(v); }')
after = before[:before.rfind('\n')] + ('\n    { extern int32_t za_title_frame_cfg(int32_t); '
    'c->x[20] = (uint32_t)za_title_frame_cfg((int8_t)LD8(c->x[9] + 0x20)); }')
s = data.decode().replace("\r\n", "\n")
assert s.count(before) == 1
patched = s.replace(before, after).encode()
out.mkdir(parents=True, exist_ok=True)
target = out/'main_660.c'
if target.exists(): assert target.read_bytes() == patched
else: target.write_bytes(patched)
record = dict(build_id=raw[0x40:0x60].hex(), address='0x7001b296d8', instruction='0x39c08134',
              source_sha256=hashlib.sha256(data).hexdigest(), patched_sha256=hashlib.sha256(patched).hexdigest(),
              original_unchanged=True, changed_units=1, behavior='original config unless 60-auto profile enabled')
(out/'hook-manifest.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))

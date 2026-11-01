"""Verify (and optionally prepare) the five translated-C hook sites of the dynamic frame timing for Z-A 2.0.2.

Read-only by default: checks the NSO build ID, the ARM instruction at every site, the duration table, the
SHA-256 of every generated unit and that every replaced statement occurs exactly once. With --out DIR it writes
patched COPIES of main_660.c / main_665.c / main_1049.c and hook-manifest.json into DIR (never into the AOT tree),
like port/title/prepare-fps-hook.py does for the single static-60 site. --syntax DIR_WITH_cpu.h additionally runs
`clang -fsyntax-only` on the patched copies with the units' own flags.

  python3 prepare-dynamic-hooks.py <aot/main dir> <exefs/main NSO> [--out DIR] [--syntax RUNTIME_DIR] [--anim]

The hooks (za_dyn_glue.c provides the functions):
  H1 0x1b296d8 ldrsb w20,[x9,#0x20]      f_7001b29660  main_660.c   za_dt_frame_cfg(cfg+0x20, cfg+0x21, clock)
  H2 0x1b296f0 mov w1,w20                f_7001b29660  main_660.c   za_dt_present_mode(w20) -> f_70017fafd4
  H3 0x1b2a0ec ldr x2,[x8,w2,sxtw #3]    f_7001b2a0e4  main_660.c   za_dt_step_ns(mode, table[mode])
  H4 0x1b54084 ldr x2,[x8,w2,sxtw #3]    f_7001b5407c  main_665.c   (same)
  H5 0x29f421c ldr x2,[x8,w2,sxtw #3]    f_70029f4214  main_1049.c  (same)
With --anim also the optional diagnostic/experiment hooks on the animation play-rate denominators:
  H6 0x101537c ldr x8,[x8,x21,lsl #3]    f_7001015260  main_467.c   za_dt_anim_table_ns(mode, table[mode])
  H7 0x10274e0 ldr x8,[x8,x9,lsl #3]     f_70010273f0  main_468.c   (same; the table address comes from the GOT)
"""
import ctypes
import ctypes.util
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

BUILD_ID = 'b1f12fd919eae86ab8a978317677e64bce443d1f'
TABLE = (0x3393e20, [16666667, 33333334, 50000000, 66666667, 83333334])
UNITS = {  # SHA-256 of the unmodified generated units (update-2.0.2-20261025/aot/main)
    'main_660.c': '6023cb91e1283a959791f350e8c523394f8d4be31a5b50d27cb85890aacdab68',
    'main_665.c': '0672449fd9b8967b6f98af12e9954de38a962555df08fa2fc5e2a92c89fadb25',
    'main_1049.c': '056944531f2b20f4786ba8d1adb9040ff779248c147329dfc53f898374896723',
}
WORDS = {  # main-relative address -> (expected instruction word, meaning)
    0x1b296d4: (0xf9402269, 'ldr x9, [x19, #0x40]          (config object)'),
    0x1b296d8: (0x39c08134, 'ldrsb w20, [x9, #0x20]        H1 frame mode'),
    0x1b296dc: (0x39408529, 'ldrb w9, [x9, #0x21]          variable-step flag'),
    0x1b296e0: (0x7100013f, 'cmp w9, #0                    (RC3 helper entry)'),
    0x1b296f0: (0x2a1403e1, 'mov w1, w20                   H2 present mode'),
    0x1b296f4: (0x97f34638, 'bl f_70017fafd4               gfx+0x140 = w1'),
    0x1b2a0e4: (0xb000c348, 'adrp x8, 0x3393000'),
    0x1b2a0e8: (0x91388108, 'add x8, x8, #0xe20'),
    0x1b2a0ec: (0xf862d902, 'ldr x2, [x8, w2, sxtw #3]     H3'),
    0x1b5407c: (0xf000c1e8, 'adrp x8, 0x3393000'),
    0x1b54080: (0x91388108, 'add x8, x8, #0xe20'),
    0x1b54084: (0xf862d902, 'ldr x2, [x8, w2, sxtw #3]     H4'),
    0x29f4214: (0xf0004ce8, 'adrp x8, 0x3393000'),
    0x29f4218: (0x91388108, 'add x8, x8, #0xe20'),
    0x29f421c: (0xf862d902, 'ldr x2, [x8, w2, sxtw #3]     H5'),
}
ANIM_UNITS = {
    'main_467.c': 'e7418e3ae90d67a9c0201b9e9e2c6cb64073eb580005999b74a356b3fd412e61',
    'main_468.c': '164f4d9097fa82746d09642f2a7c3a74316c220e84f30f26a16c84600e3c876b',
}
ANIM_WORDS = {
    0x1015370: (0xd0011be8, 'adrp x8, 0x3393000'),
    0x1015374: (0x91388108, 'add x8, x8, #0xe20'),
    0x101537c: (0xf8757908, 'ldr x8, [x8, x21, lsl #3]     H6'),
    0x10274d8: (0xf944bd08, 'ldr x8, [x8, #0x978]          (GOT entry of the table)'),
    0x10274dc: (0xb9804a69, 'ldrsw x9, [x19, #0x48]        (mode)'),
    0x10274e0: (0xf8697908, 'ldr x8, [x8, x9, lsl #3]      H7'),
}

LDRSB = '    { uint64_t ea = c->x[9] + 0x20ull; uint64_t v = (uint64_t)(int64_t)(int8_t)LD8(ea); c->x[20] = (uint32_t)(v); }'
MOVW1 = '    c->x[1] = (uint32_t)(0u | (uint32_t)c->x[20]);'
LDRX2 = ('    { uint64_t ea = c->x[8] + ((uint64_t)(int64_t)(int32_t)c->x[2] << 3); uint64_t v = LD64(ea); '
         'c->x[2] = (uint64_t)(v); }')
STEP = ('    { extern uint64_t za_dt_step_ns(int32_t, uint64_t); '
        'uint64_t ea = c->x[8] + ((uint64_t)(int64_t)(int32_t)c->x[2] << 3); uint64_t v = LD64(ea); '
        'c->x[2] = za_dt_step_ns((int32_t)c->x[2], v); }  /* dynamic timing H{n} */')


def thunk(addr):
    return ('void f_%x(Cpu *c) {\n    FN_ENTER(0x%xull);\nL_%x:;\n'
            '    c->x[8] = (uint64_t)(0x7003393000ull);\n    c->x[8] = (uint64_t)(c->x[8] + 0xe20ull);\n' % (addr, addr, addr))


SITES = [  # (unit, hook, unique 'before' text, 'after' text)
    ('main_660.c', 'H1',
     'L_7001b296d4:;\n    { uint64_t ea = c->x[19] + 0x40ull; uint64_t v = LD64(ea); c->x[9] = (uint64_t)(v); }\n' + LDRSB,
     'L_7001b296d4:;\n    { uint64_t ea = c->x[19] + 0x40ull; uint64_t v = LD64(ea); c->x[9] = (uint64_t)(v); }\n'
     '    { extern int32_t za_dt_frame_cfg(int32_t, uint32_t, uint64_t); '
     'c->x[20] = (uint32_t)za_dt_frame_cfg((int8_t)LD8(c->x[9] + 0x20), LD8(c->x[9] + 0x21), c->x[19]); }'
     '  /* dynamic timing H1 */'),
    ('main_660.c', 'H2',
     '    c->x[30] = 0x7001b296ecull; f_7000113488(c);\n'
     '    { uint64_t ea = c->x[0] + 0x0ull; uint64_t v = LD64(ea); c->x[0] = (uint64_t)(v); }\n' + MOVW1 +
     '\n    c->x[30] = 0x7001b296f8ull; f_70017fafd4(c);',
     '    c->x[30] = 0x7001b296ecull; f_7000113488(c);\n'
     '    { uint64_t ea = c->x[0] + 0x0ull; uint64_t v = LD64(ea); c->x[0] = (uint64_t)(v); }\n'
     '    { extern uint32_t za_dt_present_mode(uint32_t); '
     'c->x[1] = (uint32_t)za_dt_present_mode((uint32_t)c->x[20]); }  /* dynamic timing H2 */'
     '\n    c->x[30] = 0x7001b296f8ull; f_70017fafd4(c);'),
    ('main_660.c', 'H3', thunk(0x7001b2a0e4) + LDRX2, thunk(0x7001b2a0e4) + STEP.replace('{n}', '3')),
    ('main_665.c', 'H4', thunk(0x7001b5407c) + LDRX2, thunk(0x7001b5407c) + STEP.replace('{n}', '4')),
    ('main_1049.c', 'H5', thunk(0x70029f4214) + LDRX2, thunk(0x70029f4214) + STEP.replace('{n}', '5')),
]
ANIM = '{ extern uint64_t za_dt_anim_table_ns(int32_t, uint64_t); '
ANIM_SITES = [
    ('main_467.c', 'H6',
     'L_700101536c:;\n    { uint64_t ea = c->x[8] + 0x0ull; c->v[0] = LD64(ea); }\n'
     '    c->x[8] = (uint64_t)(0x7003393000ull);\n    c->x[8] = (uint64_t)(c->x[8] + 0xe20ull);\n'
     '    { uint64_t ea = c->x[19] + 0x278ull; uint64_t v = LD64(ea); c->x[20] = (uint64_t)(v); }\n'
     '    { uint64_t ea = c->x[8] + (c->x[21] << 3); uint64_t v = LD64(ea); c->x[8] = (uint64_t)(v); }',
     'L_700101536c:;\n    { uint64_t ea = c->x[8] + 0x0ull; c->v[0] = LD64(ea); }\n'
     '    c->x[8] = (uint64_t)(0x7003393000ull);\n    c->x[8] = (uint64_t)(c->x[8] + 0xe20ull);\n'
     '    { uint64_t ea = c->x[19] + 0x278ull; uint64_t v = LD64(ea); c->x[20] = (uint64_t)(v); }\n'
     '    ' + ANIM + 'uint64_t ea = c->x[8] + (c->x[21] << 3); uint64_t v = LD64(ea); '
     'c->x[8] = za_dt_anim_table_ns((int32_t)c->x[21], v); }  /* dynamic timing H6 */'),
    ('main_468.c', 'H7',
     '    { uint64_t ea = c->x[8] + 0x978ull; uint64_t v = LD64(ea); c->x[8] = (uint64_t)(v); }\n'
     '    { uint64_t ea = c->x[19] + 0x48ull; uint64_t v = (uint64_t)(int64_t)(int32_t)LD32(ea); c->x[9] = (uint64_t)(v); }\n'
     '    { uint64_t ea = c->x[8] + (c->x[9] << 3); uint64_t v = LD64(ea); c->x[8] = (uint64_t)(v); }',
     '    { uint64_t ea = c->x[8] + 0x978ull; uint64_t v = LD64(ea); c->x[8] = (uint64_t)(v); }\n'
     '    { uint64_t ea = c->x[19] + 0x48ull; uint64_t v = (uint64_t)(int64_t)(int32_t)LD32(ea); c->x[9] = (uint64_t)(v); }\n'
     '    ' + ANIM + 'uint64_t ea = c->x[8] + (c->x[9] << 3); uint64_t v = LD64(ea); '
     'c->x[8] = za_dt_anim_table_ns((int32_t)c->x[9], v); }  /* dynamic timing H7 */'),
]


def lz4_decompress(data, size):
    try:
        import lz4.block
        return lz4.block.decompress(data, uncompressed_size=size)
    except ImportError:
        lib = ctypes.CDLL(ctypes.util.find_library('lz4') or 'liblz4.so.1')
        lib.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        lib.LZ4_decompress_safe.restype = ctypes.c_int
        out = ctypes.create_string_buffer(size)
        assert lib.LZ4_decompress_safe(data, out, len(data), size) == size, 'lz4'
        return out.raw


def load_nso(path):
    raw = Path(path).read_bytes()
    assert raw[:4] == b'NSO0', 'not an NSO'
    build = raw[0x40:0x60].rstrip(b'\0').hex()
    assert build == BUILD_ID, 'build %s is not 2.0.2' % build
    flags = struct.unpack_from('<I', raw, 0xC)[0]
    image = {}
    for i in range(3):
        fo, mo, size = struct.unpack_from('<III', raw, 0x10 + 0x10 * i)
        comp = struct.unpack_from('<I', raw, 0x60 + 4 * i)[0]
        data = raw[fo:fo + comp]
        image[i] = (mo, lz4_decompress(data, size) if flags & (1 << i) else data)
    return image


def read(image, addr, n):
    for mo, data in image.values():
        if mo <= addr and addr + n <= mo + len(data):
            return data[addr - mo:addr - mo + n]
    raise KeyError(hex(addr))


def main(argv):
    opt = {argv[i]: argv[i + 1] for i in range(len(argv) - 1) if argv[i] in ('--out', '--syntax')}
    args = [a for i, a in enumerate(argv) if not a.startswith('--') and (i == 0 or argv[i - 1] not in opt)]
    aot, nso = Path(args[0]), Path(args[1])
    if '--anim' in argv:  # (module-level tables: extend them once for this run)
        UNITS.update(ANIM_UNITS)
        WORDS.update(ANIM_WORDS)
        SITES.extend(ANIM_SITES)
    image = load_nso(nso)
    report = {'build_id': BUILD_ID, 'words': {}, 'units': {}, 'sites': []}
    for addr, (word, what) in sorted(WORDS.items()):
        got = struct.unpack('<I', read(image, addr, 4))[0]
        assert got == word, '%#x: %08x != %08x (%s)' % (addr, got, word, what)
        report['words'][hex(addr)] = '%08x %s' % (got, what)
    table = list(struct.unpack('<5Q', read(image, TABLE[0], 40)))
    assert table == TABLE[1], table
    report['table'] = table
    texts = {}
    for unit, sha in UNITS.items():
        data = (aot / unit).read_bytes()
        got = hashlib.sha256(data).hexdigest()
        assert got == sha, '%s: sha256 %s != %s (regenerated AOT?)' % (unit, got, sha)
        texts[unit] = data.decode('utf-8').replace('\r\n', '\n')
        report['units'][unit] = {'sha256': sha}
    for unit, hook, before, after in SITES:
        n = texts[unit].count(before)
        assert n == 1, '%s %s: the statement occurs %d times' % (unit, hook, n)
        texts[unit] = texts[unit].replace(before, after)
        report['sites'].append({'hook': hook, 'unit': unit, 'occurrences': n})
    for unit in UNITS:
        report['units'][unit]['patched_sha256'] = hashlib.sha256(texts[unit].encode()).hexdigest()
    if '--out' in opt:
        out = Path(opt['--out']).resolve()
        assert aot.resolve() not in out.parents and out != aot.resolve(), 'refusing to write into the AOT tree'
        out.mkdir(parents=True, exist_ok=True)
        for unit in UNITS:
            (out / unit).write_bytes(texts[unit].encode())
        (out / 'hook-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
        if '--syntax' in opt:
            runtime = Path(opt['--syntax'])
            cc = os.environ.get('CC', 'clang-21')
            for unit in UNITS:
                cmd = [cc, '-fsyntax-only', '-O1', '-DGUEST_VOLATILE', '-fno-strict-aliasing', '-Wno-return-type',
                       '-Wno-unused-label', '-march=x86-64-v3', '-DZA_PS5', '-I', str(runtime), str(out / unit)]
                r = subprocess.run(cmd, capture_output=True, text=True)
                assert r.returncode == 0, '%s: %s' % (unit, r.stderr[-2000:])
                report['units'][unit]['syntax'] = 'ok'
            (out / 'hook-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main(sys.argv[1:])

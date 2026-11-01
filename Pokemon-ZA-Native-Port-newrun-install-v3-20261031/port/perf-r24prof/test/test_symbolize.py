"""Host test of symbolize_samples.py: a synthetic PIE (out/synthetic.elf, built by test.sh from fake/) and a
synthetic sample file in the r24-prof layout; also reads back out/c-sample.bin, written by test_core.c's C writer,
so the C writer and the Python reader agree on one layout."""
import json
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import symbolize_samples as sz  # noqa: E402

NM = '/usr/lib/llvm-21/bin/llvm-nm'
OUT = HERE / 'out'


def addrs(pie):
    out = subprocess.run([NM, '--defined-only', pie], capture_output=True, text=True, check=True).stdout
    return {l.split()[2]: int(l.split()[0], 16) for l in out.splitlines() if len(l.split()) == 3}


def write_samples(path, base, a):
    threads = [(0, 1, 0x58, 0x7100abc000, 0x1000, 0x9000, 44, 'g58'), (1, 0, 0x59, 0x7100def000, 0, 0, 44, 'g59')]
    records = []
    records += [(0, 7, base + a['exec_fake_draw'] + 4, base + a['f_7100001000'] + 8)] * 50
    records += [(0, 5, base + a['radv_fake_submit'] + 4, 0)] * 30
    records += [(0, 4, 0x7FFFF000, 0)] * 20
    records += [(1, 5, base + a['f_7100001000'] + 4, 0)] * 40
    head = bytearray(128)
    head[:8] = b'ZAPROF1\0'
    struct.pack_into('<II', head, 8, 1, 128 + len(threads) * 96)
    struct.pack_into('<7Q', head, 16, 3, 9, 5_000_000_000, 25_000_000_000, base + a['za_prof_anchor'], base, base + 0x100000)
    struct.pack_into('<9I', head, 72, 1000, len(threads), len(records), 0, 0, 0, 0, len(records), 0)
    body = bytearray()
    for index, kind, gid, entry, lo, hi, prio, name in threads:
        t = bytearray(96)
        struct.pack_into('<IIQQQQiIII', t, 0, index, kind, gid, entry, lo, hi, prio, 0, 0, 0)
        t[56:56 + len(name)] = name.encode()
        body += t
    for thread, flags, rip, caller in records:
        body += struct.pack('<HHIQQ', thread, flags, 0, rip, caller)
    path.write_bytes(bytes(head) + bytes(body))


def main():
    pie = str(OUT / 'synthetic.elf')
    a = addrs(pie)
    base = 0x4000_0000
    sample = OUT / 'synthetic-samples.bin'
    write_samples(sample, base, a)
    result = OUT / 'synthetic-report.json'
    subprocess.run([sys.executable, str(HERE.parent / 'symbolize_samples.py'), '--pie', pie, str(sample),
                    '--json', str(result)], check=True, capture_output=True, text=True)
    r = json.loads(result.read_text())
    assert r['total_samples'] == 140 and not r['notes'], r['notes']
    g = r['all']['groups']
    assert g == {'runtime': 50, 'radv': 30, 'ext': 20, 'game': 40}, g
    render = next(t for t in r['threads'] if t['name'] == 'g58')
    assert render['kind'] == 'render' and render['samples'] == 100
    top = render['functions'][0]
    assert top['name'] == 'exec_fake_draw' and top['group'] == 'runtime/nvn/vulkan/exec_fake.c' and top['samples'] == 50, top
    assert {'caller': 'f_7100001000', 'function': 'exec_fake_draw', 'samples': 50} in render['pairs']
    assert any(f['name'] == 'radv_fake_submit' and f['group'] == 'radv' for f in render['functions'])
    assert any(f['name'] == '<ext>' and f['group'].startswith('ext') for f in render['functions'])
    guest = next(t for t in r['threads'] if t['name'] == 'g59')
    assert guest['functions'][0]['group'] == 'game (translated code)' and guest['samples'] == 40
    # time filter: a window outside the range leaves nothing
    p = subprocess.run([sys.executable, str(HERE.parent / 'symbolize_samples.py'), '--pie', pie, str(sample),
                        '--from-ns', '30000000000'], capture_output=True, text=True)
    assert p.returncode != 0 and 'no sample file in range' in p.stderr
    # the C writer's file (test_core.c) reads back with the same parser
    c = sz.parse_file(OUT / 'c-sample.bin')
    assert (c['boot'], c['window'], c['period_us'], c['sent'], c['dropped'], c['skipped'], c['kill_errors']) == (7, 42, 1000, 1000, 4, 5, 6)
    assert c['anchor'] == 0x400000 + 0x1230 and c['text'] == (0x400000, 0x500000) and c['render_slot'] == 0
    assert [t['name'] for t in c['threads'].values()] == ['g58', 'radv-kick']
    assert c['threads'][0]['kind'] == 'render' and c['threads'][0]['samples'] == 900 and c['threads'][1]['kind'] == 'radv-kick'
    assert c['records'][0] == (0, 7, 0x401100, 0x401200) and c['records'][2] == (1, 4, 0x7fff0000, 0)
    print('PASS test_symbolize: synthetic PIE groups (game/runtime file/radv/ext), callers, threads, time filter; '
          'C-written file parsed')


if __name__ == '__main__':
    main()

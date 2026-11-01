"""Independent Python oracle for the r29-music shuffle (no shared code with za_music.cpp).

Usage: oracle_music.py PLAN.json ROMFS_BIN OUT_DIR
- recomputes every seed/mode the C++ test wrote (OUT_DIR/seeds.json, sha-<mode>-<seed>.txt) from the plan's
  rules (domain-separated SHA-256 choice, Fisher-Yates, fixed-point swap, unit member alignment) and compares
  the SHA-256 of the whole output bank;
- fully parses the written sample banks (music-*.bnk) with tools/za_bgm.py (every music object byte-exact), checks
  that every decision-tree leaf of every music switch still names an object of the bank, that only planned slot
  words differ from the game's bank, and that each slot holds a planned song of the right category.
"""
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import za_bgm  # noqa

ALG = 'za202-bgm-leaf-shuffle-v1'
BUILD = 'b1f12fd919eae86ab8a978317677e64bce443d1f'
CATS = ['town', 'zone', 'battle', 'boss']


def choose(seed, mode, scope, step, bound):
    rem = ((2 ** 64 - 1) % bound + 1) % bound
    for attempt in range(1000):
        text = json.dumps([ALG, BUILD, seed, mode, scope, step, attempt], separators=(',', ':'))
        word = int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)
        if not rem or word <= 2 ** 64 - 1 - rem:
            return word % bound
    raise RuntimeError('no choice')


def derange(n, seed, mode, scope):
    p = list(range(n))
    for i in range(n - 1, 0, -1):
        j = choose(seed, mode, scope, i, i + 1)
        p[i], p[j] = p[j], p[i]
    if n > 1:
        for i in range(n):
            if p[i] == i:
                k = (i + 1) % n
                p[i], p[k] = p[k], p[i]
    return p


def expected(plan, bank, seed, mode):
    units = plan['units']
    target = [None] * len(units)
    if mode == 'category':
        for c in CATS:
            lst = [u['unit'] for u in units if u['category'] == c]
            p = derange(len(lst), seed, mode, c)
            for i, u in enumerate(lst):
                target[u] = lst[p[i]]
    else:
        p = derange(len(units), seed, mode, 'all')
        target = p
    out = bytearray(bank)
    for s in plan['slots']:
        a = units[s['unit']]['members']
        b = units[target[s['unit']]]['members']
        m = a.index(s['song'])
        struct.pack_into('<I', out, s['offset'], int(b[m % len(b)], 16))
    return bytes(out), target


def main():
    plan_path, romfs, out = sys.argv[1:4]
    plan = json.load(open(plan_path, encoding='utf-8'))
    with open(romfs, 'rb') as f:
        f.seek(plan['bank']['romfs_image_offset'])
        bank = f.read(plan['bank']['bytes'])
    assert hashlib.sha256(bank).hexdigest() == plan['bank']['sha256']
    seeds = json.load(open(os.path.join(out, 'seeds.json')))
    compared = 0
    for mode in ('category', 'chaos'):
        for seed in seeds:
            data, _ = expected(plan, bank, seed, mode)
            want = open(os.path.join(out, 'sha-%s-%s.txt' % (mode, seed))).read().strip()
            assert hashlib.sha256(data).hexdigest() == want, (mode, seed)
            compared += 1
    slot_offsets = {s['offset'] for s in plan['slots']}
    unit_of = {int(m, 16): u['unit'] for u in plan['units'] for m in u['members']}
    cat_of = {u['unit']: u['category'] for u in plan['units']}
    parsed = 0
    for name in sorted(os.listdir(out)):
        if not (name.startswith('music-') and name.endswith('.bnk')):
            continue
        data = open(os.path.join(out, name), 'rb').read()
        mode, seed = name[len('music-'):-len('.bnk')].split('-', 1)
        exp, target = expected(plan, bank, seed, mode)
        assert data == exp, name
        b = za_bgm.Bank(data)  # every music object must still parse byte-exactly
        assert len(b.music) == plan['bank']['music_objects']
        for sid, m in b.music.items():
            # (a depth-0 switch has no decision: its single root node is not an audio-node leaf)
            if b.type_of(sid) == za_bgm.SWITCH and m['depth'] > 0:
                for keys, x, off in za_bgm.switch_leaves(m):
                    assert x == 0 or x in b.objects, (name, hex(sid), hex(x))
        diff = [i for i in range(len(data)) if data[i] != bank[i]]
        assert all(any(o <= i < o + 4 for o in slot_offsets) for i in diff), name
        for s in plan['slots']:
            now = struct.unpack_from('<I', data, s['offset'])[0]
            assert now in unit_of and b.type_of(now) == za_bgm.PLAYLIST
            if mode == 'category':
                assert cat_of[unit_of[now]] == cat_of[s['unit']]
        parsed += 1
    print('PASS: oracle matches %d C++ outputs byte-for-byte (SHA-256); %d sample banks fully re-parsed, leaves valid, '
          'only planned slot words changed' % (compared, parsed))


if __name__ == '__main__':
    main()

"""Dex struct (index u16, group u8) of 2.0.2 personal rows: present vs absent; plus TM/reminder/egg vectors presence."""
import json, struct, sys, collections
sys.path.insert(0, r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/randomizer-lab')
from reflection_reader import Buffer
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
P = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port/save-workbench/deps/PKHeX/PKHeX.Core'
names = open(P + '/Resources/text/other/en/text_Species_en.txt', encoding='utf-8-sig').read().splitlines()
raw = open(S + '/samples/avalon/data/personal_array.bin', 'rb').read()
b = Buffer(raw)
groups = collections.Counter()
ex = collections.defaultdict(list)
vecs = collections.Counter()
for p in b.tables(b.scalar(0, 'I'), 0):
    internal, form, national = struct.unpack_from('<HHH', raw, b.field(p, 0))
    present = bool(b.value(p, 1, '?'))
    q = b.field(p, 2)
    idx, grp = (struct.unpack_from('<HB', raw, q) if q is not None else (0, 0))
    groups[(present, grp, idx > 0)] += 1
    if len(ex[(present, grp)]) < 6 and idx:
        ex[(present, grp)].append((national, form, names[national], idx))
    for fi, nm in ((22, 'tm'), (23, 'egg'), (24, 'reminder'), (25, 'learn'), (21, 'evo')):
        q = b.field(p, fi)
        n = len(b.vector(q, 2 if fi in (22, 23, 24) else 16 if fi == 21 else 4)) if q is not None else 0
        vecs[(present, nm, n > 0)] += 1
print('(present, dex group, has index) -> rows')
for k, v in sorted(groups.items()): print(' ', k, v)
for k, v in sorted(ex.items()): print(' examples', k, v)
print('vectors (present, kind, nonempty) -> rows')
for k, v in sorted(vecs.items()): print(' ', k, v)

"""Decode Z-A 2.0.2 avalon/data/personal_array.bin (layout per pkNX ZA PersonalTable.fbs, as used by randomizer-lab).
Answers: does the table hold rows for all species (with a present flag) or only Z-A's set? Do absent rows carry data?"""
import json, struct, sys, collections
sys.path.insert(0, r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/randomizer-lab')
from reflection_reader import Buffer

S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
P = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port/save-workbench/deps/PKHeX/PKHeX.Core'
names = open(P + '/Resources/text/other/en/text_Species_en.txt', encoding='utf-8-sig').read().splitlines()
raw = open(S + '/samples/avalon/data/personal_array.bin', 'rb').read()
b = Buffer(raw)
rows = []
for p in b.tables(b.scalar(0, 'I'), 0):
    fl = b.fields(p)
    q = b.field(p, 0)
    internal, form, national = struct.unpack_from('<HHH', raw, q)
    learn = []
    q = b.field(p, 25)
    if q is not None:
        learn = [struct.unpack_from('<Hbb', raw, v) for v in b.vector(q, 4)]
    evo = []
    q = b.field(p, 21)
    if q is not None:
        for v in b.vector(q, 16):
            level, method, arg, _, _, _, species, eform = struct.unpack_from('<8H', raw, v)
            evo.append((method, arg, level, species, eform))
    stats = None
    nfields = sum(x is not None for x in fl)
    rows.append(dict(internal=internal, form=form, national=national, name=names[national] if national < len(names) else '?',
                     present=bool(b.value(p, 1, '?')), dex=b.value(p, 2, 'H'), type1=b.value(p, 3, 'B'), type2=b.value(p, 4, 'B'),
                     nfields=nfields, nlearn=len(learn), nevo=len(evo), learn=learn[:6], evo=evo))
print('rows', len(rows), 'vtable field slots (max)', max(r['nfields'] for r in rows))
nat = sorted({r['national'] for r in rows})
print('national species covered:', len(nat), 'min', nat[0], 'max', nat[-1])
print('internal max', max(r['internal'] for r in rows))
pres = [r for r in rows if r['present']]
print('present rows', len(pres), 'present species (national)', len({r['national'] for r in pres}))
absent = [r for r in rows if not r['present']]
print('absent rows', len(absent))
# do absent rows carry learnsets/evolutions/types?
print('absent rows with learnset', sum(r['nlearn'] > 0 for r in absent), 'with evo', sum(r['nevo'] > 0 for r in absent),
      'with type1!=0', sum(r['type1'] != 0 for r in absent), 'fields hist', collections.Counter(r['nfields'] for r in absent).most_common(5))
print('present rows fields hist', collections.Counter(r['nfields'] for r in pres).most_common(5))
missing_nat = [s for s in range(1, 1026) if s not in nat]
print('national 1..1025 with NO row at all:', len(missing_nat), missing_nat[:10], '...', missing_nat[-10:])
for want in (10, 37, 58, 133, 245, 448, 925, 1001, 1024):
    for r in rows:
        if r['national'] == want and r['form'] == 0:
            print(' sample', want, {k: r[k] for k in ('internal', 'name', 'present', 'dex', 'type1', 'type2', 'nfields', 'nlearn', 'nevo')}, r['learn'][:4], r['evo'][:2])
json.dump(rows, open(S + '/out/personal-2.0.2.json', 'w'))

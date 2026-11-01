"""Rank absent species as pilot candidates: personal row data, SV Paldea-dex leftover index, behaviour file, cry event."""
import json, struct, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/randomizer-lab')
from reflection_reader import Buffer
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
raw = open(S + '/samples/avalon/data/personal_array.bin', 'rb').read()
b = Buffer(raw)
files = json.load(open(S + '/out/species-data-files.json'))
beh = {int(x[:4]) for x in files['behavior']}
cry_absent = {235, 311, 312, 313, 314, 351, 926, 927, 932, 933, 934, 935, 936, 937, 944, 945, 957, 958, 959, 996, 997, 998, 999}
pers = json.load(open(S + '/out/personal-2.0.2.json'))
rows = {}
for p in b.tables(b.scalar(0, 'I'), 0):
    internal, form, national = struct.unpack_from('<HHH', raw, b.field(p, 0))
    q = b.field(p, 2)
    idx, grp = struct.unpack_from('<HB', raw, q) if q is not None else (0, 0)
    rows[(internal, form)] = (national, bool(b.value(p, 1, '?')), idx, grp)
names = {r['internal']: r['name'] for r in pers if r['form'] == 0}
learn = {(r['internal'], r['form']): r['nlearn'] for r in pers}
evo = {(r['internal'], r['form']): r['evo'] for r in pers}
present = {k for k, v in rows.items() if v[1]}
present_sp = {k[0] for k in present}
out = []
for (sp, fo), (nat, pres, idx, grp) in sorted(rows.items()):
    if fo or sp == 0 or sp in present_sp: continue
    evo_to_present = any(e[3] in present_sp for e in evo[(sp, fo)])
    evo_from_present = any(any(e[3] == sp for e in evo[k]) for k in present)
    out.append(dict(internal=sp, national=nat, name=names.get(sp), sv_dex=idx if grp else 0, behaviour=sp in beh,
                    cry_event=sp in cry_absent, learnset=learn[(sp, fo)], evolves_into_present=evo_to_present,
                    evolves_from_present=evo_from_present))
print('absent base species with a personal row:', len(out))
print('  with SV-dex leftover index:', sum(1 for o in out if o['sv_dex']))
print('  with behaviour file:', sum(o['behaviour'] for o in out), '| with cry event:', sum(o['cry_event'] for o in out))
print('  evolution link to a present species:', sum(o['evolves_into_present'] or o['evolves_from_present'] for o in out))
best = [o for o in out if o['cry_event']]
for o in best: print('  cry-ready:', o)
json.dump(out, open(S + '/out/absent-species.json', 'w'), indent=0)

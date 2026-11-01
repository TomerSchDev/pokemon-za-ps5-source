"""Read-only: existence + species coverage of further per-species tables named by a community Z-A mod (Ansha pack file list):
poke_model_param, poke_movement_param, cafe_poke_size_data, chara_anime/NNNN_FF_VV. Extracts small samples (+bfbs) to samples/."""
import json, os, sys, collections
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
sys.path.insert(0, r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/randomizer-lab')
import za_romfs
from reflection_reader import Schema
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
g = za_romfs.Game(GAME)
pers = json.load(open(S + '/out/personal-2.0.2.json'))
present = {r['internal'] for r in pers if r['present']}
def save(p, data):
    dst = os.path.join(S, 'samples', *p.split('/')); os.makedirs(os.path.dirname(dst), exist_ok=True); open(dst, 'wb').write(data)
cands = ['param_chr/data/pokemon/poke_model_param/poke_model_param_array',
         'param_chr/data/pokemon/poke_movement_param/poke_movement_param_array',
         'param_chr/data/pokemon/poke_movement_param_array/poke_movement_param_array',
         'param_chr/data/character/pokemon/poke_movement_param/poke_movement_param_array',
         'ik_event/bin/cafe_poke_size_data', 'ik_event/bin/cafe_poke_size_data/cafe_poke_size_data']
for stem in cands:
    have = {ext: g.has(stem + ext) for ext in ('.bin', '.bfbs')}
    print(stem, have)
    if have['.bin'] and have['.bfbs']:
        sch = g.read(stem + '.bfbs'); dat = g.read(stem + '.bin'); save(stem + '.bfbs', sch); save(stem + '.bin', dat)
        s = Schema(sch)
        print('   root', s.root, [(o['name'].split('.')[-1], [f['name'] for f in o['fields']][:12]) for o in s.objects][:6])
        d = s.decode(dat, offsets=False)
        txt = json.dumps(d)
        print('   sample:', txt[:400])
        # species coverage: collect ints in fields named like dev/monsno/species
        ids = collections.Counter()
        def walk(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    if k.lower() in ('devno', 'devid', 'monsno', 'species', 'pokeno', 'speciesid', 'dev_no') and isinstance(x, int): ids[x] += 1
                    walk(x)
            elif isinstance(v, list):
                for x in v: walk(x)
        walk(d)
        if ids:
            ks = set(ids)
            print('   species ids', len(ks), 'present', len(ks & present), 'absent', len(ks - present), sorted(ks - present)[:20])
# chara_anime per-species files: enumerate NNNN_FF_VV
M = 0xFFFFFFFFFFFFFFFF
def cont(h, b):
    for c in b: h = ((h ^ c) * 0x100000001B3) & M
    return h
base = cont(0xCBF29CE484222645, b'param_chr/data/character/anime/chara_anime/')
found = []
for n in range(1200):
    hn = cont(base, f'{n:04d}'.encode())
    for f in range(20):
        for v in (0, 1):
            if cont(hn, f'_{f:02d}_{v:02d}.bin'.encode()) in g.files: found.append((n, f, v))
ns = {x[0] for x in found}
print('chara_anime files', len(found), 'distinct NNNN', len(ns), 'present', len(ns & present), 'absent', len(ns - present), sorted(ns - present)[:20])
if found:
    p = 'param_chr/data/character/anime/chara_anime/%04d_%02d_%02d' % found[25]
    if g.has(p + '.bfbs'):
        s = Schema(g.read(p + '.bfbs')); d = s.decode(g.read(p + '.bin'), offsets=False)
        print('   chara_anime sample', p, s.root, json.dumps(d)[:500])

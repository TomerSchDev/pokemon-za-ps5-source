"""Read-only: enumerate exact NNNN_FF_VV names of per-species data files (behavior / collision / wild_single params)
by brute-force hash matching (NNNN 0..1199, FF 0..99, VV 0..99). Names only."""
import collections, json, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
g = za_romfs.Game(GAME)
M = 0xFFFFFFFFFFFFFFFF
def cont(h, b):
    for c in b: h = ((h ^ c) * 0x100000001B3) & M
    return h
dirs = {
    'behavior': ('world/ik_data/pokemon/ai/pokemon_species_behavior_data/', '.bin'),
    'collision': ('world/ik_data/pokemon/collision/pokemon_collision_unique_data/', '.bin'),
    'wild_single': ('param_chr/data/character/pokemon/wild_single/', '.bin'),
}
tails = [(f'_{f:02d}_{v:02d}').encode() for f in range(100) for v in range(100)]
out = {}
for kind, (d, ext) in dirs.items():
    h0 = cont(0xCBF29CE484222645, d.encode())
    found = []
    e = ext.encode()
    for n in range(1200):
        hn = cont(h0, f'{n:04d}'.encode())
        for t in tails:
            if cont(cont(hn, t), e) in g.files:
                found.append(f'{n:04d}{t.decode()}')
    out[kind] = found
    sp = collections.Counter(x[:4] for x in found)
    print(kind, 'files', len(found), 'distinct NNNN', len(sp), 'max NNNN', max(sp) if sp else None)
    print('   FF_VV kinds:', collections.Counter(x[5:] for x in found).most_common(12))
json.dump(out, open(S + '/out/species-data-files.json', 'w'))

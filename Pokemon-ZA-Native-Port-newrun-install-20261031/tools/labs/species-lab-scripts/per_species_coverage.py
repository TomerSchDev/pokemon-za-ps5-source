"""Read-only: for every personal row (species/form), which per-species data files exist (present vs absent species)."""
import collections, json, re, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
g = za_romfs.Game(GAME)
pers = json.load(open(S + '/out/personal-2.0.2.json'))
cat = json.load(open(S + '/out/catalog.json'))
pm_of = {}
for e in cat:
    sp = e['info'].get('f0', 0)
    m = re.match(r'pm(\d{4})/', e['f1'])
    pm_of.setdefault(sp, int(m.group(1)))
templates = {
    'behavior': 'world/ik_data/pokemon/ai/pokemon_species_behavior_data/{n:04d}_{f:02d}_{v:02d}.bin',
    'collision': 'world/ik_data/pokemon/collision/pokemon_collision_unique_data/{n:04d}_{f:02d}_{v:02d}.bin',
    'wild_single': 'param_chr/data/character/pokemon/wild_single/{n:04d}_{f:02d}_{v:02d}.bin',
}
res = collections.Counter()
numbering = collections.Counter()
examples = collections.defaultdict(list)
for r in pers:
    nums = {'national': r['national'], 'internal': r['internal'], 'pm': pm_of.get(r['internal'], r['internal'])}
    for kind, t in templates.items():
        hit = None
        for nk, n in nums.items():
            for v in (0, 1):
                p = t.format(n=n, f=r['form'], v=v)
                if g.has(p):
                    hit = nk; break
            if hit: break
        res[(kind, r['present'], hit is not None)] += 1
        if hit:
            numbering[(kind, hit, r['national'] == r['internal'] == nums['pm'])] += 1
            if not r['present'] and len(examples[kind]) < 8:
                examples[kind].append((r['national'], r['form'], r['name']))
for k, v in sorted(res.items(), key=str): print(k, v)
print('numbering used (kind, scheme, all-equal):', dict(numbering))
print('absent rows that still have files:', dict(examples))
# total files in the per-kind packs
for name, recs in g.packs:
    if 'pokemon_species_behavior_data' in name or 'pokemon_collision_unique_data' in name:
        print(name, len(recs))

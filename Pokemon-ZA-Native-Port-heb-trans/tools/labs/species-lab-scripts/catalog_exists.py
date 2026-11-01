"""Read-only: which catalog-referenced paths (prefixed with ik_pokemon/data/) exist in the 2.0.2 pack index, per extension."""
import collections, json, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
g = za_romfs.Game(GAME)
cat = json.load(open(S + '/out/catalog.json'))
stat = collections.Counter()
missing = collections.defaultdict(list)
for e in cat:
    paths = [e.get(k) for k in ('f1', 'f2', 'f3', 'f6', 'f7', 'f8') if e.get(k)]
    for k in ('f4', 'f5'):
        for it in e.get(k, []):
            paths += [v for v in it.values() if isinstance(v, str)]
    for p in paths:
        ext = p.rsplit('.', 1)[-1] if '_defence' not in p else 'defence.hkx'
        if '_0000' in p and p.endswith('.trskl'): ext = 'trskl(set)'
        ok = g.has('ik_pokemon/data/' + p)
        stat[(ext, ok)] += 1
        if not ok and len(missing[ext]) < 4: missing[ext].append(p)
for k, v in sorted(stat.items()): print(k, v)
print(dict(missing))

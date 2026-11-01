"""Read-only: find a model folder's animation-config (.tracn) / skeleton-set / icon paths, and probe animation file names
(.tranm/.traef) built from the animation ids seen in pack names. Names and sizes only."""
import collections, json, os, re, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
folder = sys.argv[1] if len(sys.argv) > 1 else 'pm0025/pm0025_00_00'
pm, stem = folder.split('/')
g = za_romfs.Game(GAME)
roots = ['ik_pokemon/data/', 'ik_pokemon/', 'pokemon/data/', 'ik_pokemon/anm/', 'ik_pokemon/anim/', 'ik_pokemon/data/anm/']
subs = ['', 'anm/', 'anim/', 'tracn/', 'icon/', 'config/', 'mdl/']
hits = {}
for r in roots:
    for sub in subs:
        for name in (f'{stem}.tracn', f'{stem}_00000.trskl', f'{stem}_10000.trskl', f'{stem}_20000.trskl', f'{stem}_00.bntx',
                     f'{stem}_00_0.bntx', f'{stem}_00_1.bntx', f'{stem}_00_00_0.bntx', f'{stem}_00_00_1.bntx'):
            p = f'{r}{pm}/{stem}/{sub}{name}'
            if g.has(p):
                hits[p] = g.files[za_romfs.fnv1a64(p)]['size']
print('config/skeleton/icon hits:', hits)
# animation ids/names from all pack names
ids = set()
for name, recs in g.packs:
    m = re.search(r'pm\d{4}_\d\d_\d\d_(\d{5}_[a-z0-9_]+?)\.(traef|tranm)\.trpak$', name)
    if m: ids.add(m.group(1))
print('distinct anim ids seen in pack names:', len(ids))
found = {}
for a in sorted(ids):
    for sub in ('', 'anm/', 'anim/'):
        for ext in ('tranm', 'traef'):
            p = f'ik_pokemon/data/{pm}/{stem}/{sub}{stem}_{a}.{ext}'
            if g.has(p): found[p] = g.files[za_romfs.fnv1a64(p)]['size']
print('probed animation files found:', len(found))
for p in sorted(found)[:60]: print('  ', p, found[p])
# extract the tracn if small, and harvest names from it
for p in hits:
    if p.endswith('.tracn'):
        data = g.read(p)
        dst = os.path.join(S, 'samples', *p.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data)
        names = sorted({m.group().decode() for m in re.finditer(rb'[ -~]{4,}', data)})
        print('tracn strings', len(names), names[:80])

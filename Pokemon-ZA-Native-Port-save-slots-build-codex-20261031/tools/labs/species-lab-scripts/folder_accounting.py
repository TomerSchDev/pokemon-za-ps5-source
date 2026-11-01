"""Read-only: account for every file hash in a model folder's pack using names from the folder's own _base.tracr / _base.tracn
plus the model files found by model_pack.py (out/folder-<stem>.json). Usage: folder_accounting.py pm0025/pm0025_00_00 ..."""
import json, re, sys, collections
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
g = za_romfs.Game(GAME)
for folder in sys.argv[1:]:
    pm, stem = folder.split('/')
    base = f'ik_pokemon/data/{pm}/{stem}/'
    names = set(json.load(open(f'{S}/out/folder-{stem}.json')))
    for f in (f'{stem}_base.tracr', f'{stem}_base.tracn'):
        p = base + f
        if not g.has(p): continue
        names.add(p)
        for s in re.findall(rb'[ -~]{4,}', g.read(p)):
            s = s.decode()
            if re.fullmatch(r'[\w.-]+\.tr[a-z]+', s): names.add(base + s)
    hit = {n for n in names if g.has(n)}
    packs = collections.Counter(g.files[za_romfs.fnv1a64(n)]['pack'] for n in hit)
    main = max(packs, key=packs.get)
    total = next(len(r) for nm, r in g.packs if nm == main)
    inpack = [n for n in hit if g.files[za_romfs.fnv1a64(n)]['pack'] == main]
    ext = collections.Counter(n.rsplit('.', 1)[1] for n in inpack)
    print(folder, 'pack', main.split('/')[-1], 'files', total, 'named', len(inpack), 'unnamed', total - len(inpack))
    print('   by ext', dict(sorted(ext.items())))

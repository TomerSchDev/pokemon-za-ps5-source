"""Read-only: inventory of one Pokemon model folder (default pm0025_00_00): which packs hold its files, resolve
file names by probing candidate paths (taken from strings inside the folder's own config files), extension stats.
Writes only names/sizes to out/, and small config files (<512 KB) to samples/ for format inspection."""
import collections, json, os, re, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs

GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
folder = sys.argv[1] if len(sys.argv) > 1 else 'pm0025/pm0025_00_00'
base = 'ik_pokemon/data/' + folder
stem = folder.split('/')[-1]
g = za_romfs.Game(GAME)

def strings(b):
    return {m.group().decode() for m in re.finditer(rb'[ -~]{5,}', b)}

known = {}
queue = [f'{base}/{stem}{x}' for x in ('.trmdl', '.trmmt', '.trpokecfg', '.tracn', '_00000.trskl', '_10000.trskl', '_20000.trskl',
                                         '_00.bntx', '_defence.hkx', '_base.trmdt', '_base.trslp', '_base.trbsm', '_base.trslt')]
seen = set()
while queue:
    p = queue.pop()
    if p in seen: continue
    seen.add(p)
    h = za_romfs.fnv1a64(p)
    if h not in g.files: continue
    r = g.files[h]
    known[p] = (r['size'], r['pack'])
    if r['size'] < (4 << 20):
        data = g.read(p)
        if r['size'] < (512 << 10) and not p.endswith(('.bntx', '.tranm', '.trmbf')):
            dst = os.path.join(S, 'samples', *p.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(data)
        for s in strings(data):
            for cand in re.findall(r'[\w./-]+\.[a-z0-9]{2,9}', s):
                for c in (cand, f'{base}/{cand}', f'{base}/{os.path.basename(cand)}', 'ik_pokemon/data/' + cand,
                          f'{base}/anm/{os.path.basename(cand)}', f'{base}/anim/{os.path.basename(cand)}'):
                    if c not in seen: queue.append(c)
# which packs contain this folder's files and how many hashes are in them
packs = collections.Counter(v[1] for v in known.values())
total = {name: len(recs) for name, recs in g.packs if name in packs}
ext = collections.Counter(os.path.splitext(p)[1] for p in known)
print('resolved files', len(known), 'by ext', dict(ext))
for name, c in packs.items():
    print('pack', name, 'resolved', c, 'of', total[name])
json.dump(known, open(os.path.join(S, 'out', 'folder-' + stem + '.json'), 'w'), indent=1)
for p in sorted(known)[:400]:
    print(' ', p[len(base) + 1:], known[p][0])

"""Read-only: list RomFS loose files and Trinity pack names of Z-A 2.0.2 (no game bytes written, names only)."""
import json, os, re, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs

GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
OUT = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/out'

g = za_romfs.Game(GAME)
loose = sorted(g.entries)
packs = [(n, len(r), sum(x['size'] for x in r)) for n, r in g.packs]
json.dump({'romfs_loose_files': [(p, g.entries[p][1]) for p in loose],
           'pack_count': len(packs), 'file_hash_count': len(g.files),
           'packs': packs}, open(os.path.join(OUT, 'pack-names.json'), 'w'), indent=0)
print('loose', len(loose), 'packs', len(packs), 'hashes', len(g.files))
for p in loose:
    print('  loose:', p, g.entries[p][1])
pk = [p for p in packs if re.search(r'pokemon|pm\d{4}', p[0], re.I)]
print('pokemon-ish packs', len(pk))
for p in pk[:80]:
    print('  ', p)

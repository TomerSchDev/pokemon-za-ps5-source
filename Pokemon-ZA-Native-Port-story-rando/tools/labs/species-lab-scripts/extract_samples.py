"""Read-only: extract a few small Z-A 2.0.2 files (by game path) into species-lab/samples for local analysis.
Usage: extract_samples.py <game path> [<game path> ...]   (each written under samples/<game path>)"""
import os, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs

GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
SAMPLES = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/samples'
MAX = 8 << 20  # small samples only

g = za_romfs.Game(GAME)
for path in sys.argv[1:]:
    if not g.has(path):
        print('MISSING', path)
        continue
    r = g.files[za_romfs.fnv1a64(path)]
    if r['size'] > MAX:
        print('TOO BIG (skipped)', path, r['size'])
        continue
    data = g.read(path)
    dst = os.path.join(SAMPLES, *path.split('/'))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'wb') as f:
        f.write(data)
    print('ok', path, len(data), 'pack', r['pack'])

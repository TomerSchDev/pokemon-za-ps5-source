"""Assemble a local playable folder, with an explicit allowlist and no keys/caches."""
from pathlib import Path
import shutil
import hashlib
import json

root = Path(__file__).resolve().parent
dest = root.parent.parent / 'deliverables/Pokemon-ZA-PC-v0.1.4-20261024'
rel = root / 'release-v0.1.4/ZA Recomp'
game = root / 'game-v1.0.0/extracted'
files = [(p, dest / 'runtime' / p.name) for p in rel.iterdir()
         if p.is_file() and (p.suffix.lower() in ['.exe', '.dll', '.ttf', '.png']
                           or p.name in ['LICENSE', 'Baloo2-OFL.txt', 'README.md'])]
files += [(game / n, dest / 'game' / n) for n in ['romfs.bin', 'lasgame.dll', 'lasgame.dll.id']]
files += [(p, dest / 'game/exefs' / p.name) for p in (game / 'exefs').iterdir() if p.is_file()]
manifest = []
for src, dst in files:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise RuntimeError('Refusing to overwrite an existing package: ' + str(dst))
    shutil.copy2(src, dst)
    with src.open('rb') as f: a = hashlib.file_digest(f, 'sha256').hexdigest()
    with dst.open('rb') as f: b = hashlib.file_digest(f, 'sha256').hexdigest()
    if a != b: raise RuntimeError('copy verification failed: ' + dst.name)
    manifest.append(dict(path=dst.relative_to(dest).as_posix(), bytes=dst.stat().st_size, sha256=b))
    print(dst.relative_to(dest), flush=True)
(dest / 'asset-manifest.json').write_text(json.dumps(manifest, indent=2))
print('Verified local package:', dest, flush=True)

"""Golden PNG check: compares a fresh render of the mockups (mockups_main -> a scratch dir) with the pinned SHA-256 list
mockups/SHA256SUMS.txt. Every mockup is rendered by the real rasterizer, model and screen code, so an unintended change
to any of them shows up as a changed image; an intended change is accepted by re-pinning (--pin).
Usage: check-goldens.py <pinned SHA256SUMS.txt> <fresh render dir> [--pin]"""
import hashlib
import sys
from pathlib import Path

pinned_path, fresh = Path(sys.argv[1]), Path(sys.argv[2])
pin = '--pin' in sys.argv
pinned = {}
if pinned_path.is_file():
    for line in pinned_path.read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) == 2:
            pinned[parts[1]] = parts[0]
fresh_sums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(fresh.glob('*.png'))}
changed = sorted(n for n in fresh_sums if n in pinned and pinned[n] != fresh_sums[n])
added = sorted(n for n in fresh_sums if n not in pinned)
missing = sorted(n for n in pinned if n not in fresh_sums)
print('goldens: %d pinned, %d rendered, %d changed, %d new, %d missing' % (len(pinned), len(fresh_sums), len(changed), len(added), len(missing)))
for n in changed:
    print('  changed %s' % n)
for n in added:
    print('  new     %s' % n)
for n in missing:
    print('  missing %s' % n)
if pin:
    pinned_path.write_text(''.join('%s  %s\n' % (fresh_sums[n], n) for n in sorted(fresh_sums)), encoding='utf-8', newline='\n')
    print('pinned %d goldens into %s' % (len(fresh_sums), pinned_path))
    sys.exit(0)
sys.exit(1 if changed or added or missing else 0)

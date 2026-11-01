"""Mod-order gate: model the runtime's LayeredFS (runtime/services/fs.c layer_init) on a local mods folder.

    python mod_order.py MODS_DIR [--text-layer 0-hebrew] [--names a,b,c]   (--names: folder names only, e.g. the console's)
Rules modelled: a run's romfs comes first; then mods/<name>/romfs in strcmp order, names starting '_' or '.' are off,
at most 15 enabled folders (readdir order decides which when there are more); the FIRST layer holding a file wins.
Decision (release 1.1.0): the Hebrew text layer is named `0-hebrew`. '0','-' sorts before every '00-*' / '000-*' name
the other branches use, so Hebrew wins every shared text file. A later Hebrew add-on (species names for new species)
ships as `0-0-hebrew-<topic>` holding ONLY merged superset tables built from the same Hebrew release (it then sorts
before 0-hebrew). Fails if: >15 enabled, any enabled layer sorts before the text layer without the `0-0-hebrew-`
prefix, or a shared ik_message/ or ui/font/ file is won by a non-Hebrew layer.
"""
import argparse, sys
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('mods', nargs='?')
ap.add_argument('--text-layer', default='0-hebrew')
ap.add_argument('--names', help='comma list of folder names to check by name only')
a = ap.parse_args()
names = a.names.split(',') if a.names else [p.name for p in Path(a.mods).iterdir() if (p / 'romfs').is_dir()]
enabled = sorted(n for n in names if n[:1] not in ('_', '.'))
problems = []
if len(enabled) > 15:
    problems.append(f'{len(enabled)} enabled mod folders; the runtime takes at most 15 (readdir order)')
hebrew = [n for n in enabled if n == a.text_layer or n.startswith('0-0-hebrew-')]
for n in enabled:
    if n < a.text_layer and not n.startswith('0-0-hebrew-'):
        problems.append(f'{n} sorts before {a.text_layer} and would win shared text files')
print('layer order:', ' > '.join(enabled) or '(none)')
if a.mods and not a.names:
    root = Path(a.mods); seen = {}
    for n in enabled:
        for f in (root / n / 'romfs').rglob('*'):
            if f.is_file():
                seen.setdefault(f.relative_to(root / n / 'romfs').as_posix(), []).append(n)
    shared = {k: v for k, v in seen.items() if len(v) > 1}
    print(f'files: {len(seen)}  shared between layers: {len(shared)}')
    for k, v in sorted(shared.items()):
        text = k.startswith(('ik_message/', 'ui/font/'))
        if text and v[0] not in hebrew:
            problems.append(f'{k}: won by {v[0]}, not the Hebrew layer ({v})')
        elif text:
            print(f'  {k}: {v[0]} wins over {v[1:]}')
for p in problems:
    print('FAIL', p)
print('PASS' if not problems else 'FAIL')
sys.exit(1 if problems else 0)

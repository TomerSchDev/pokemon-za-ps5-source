import json
from pathlib import Path
import sys
from source_archives import TrinitySource, Gfpak

ROOT = Path(r'C:\Users\Tomer\Downloads\Pokemon\Extracted-20261030')
if sys.argv[1] == 'violet':
    g = TrinitySource(ROOT / 'Pokemon-Violet_01008f6008c5e000_v720896/romfs')
    print(json.dumps(dict(packs=len(g.packs), files=len(g.files), catalog_packs=[(name, len(records)) for name, records in g.packs if 'trpmcatalog' in name], examples=[name for name in g.pack_names if 'pm10' in name][:12]), indent=2))
else:
    directory = ROOT / sys.argv[1] / 'romfs/bin/archive/pokemon'
    p = next(directory.glob('pm0025*.gfpak'))
    g = Gfpak(p)
    print(p, hex(g.version), len(g.files))
    for r in g.files[:6]:
        d = g.unpack(r)
        print({k:v for k,v in r.items() if k!='data'}, len(d), d[:16].hex())

from pathlib import Path
import json
import sys
from source_archives import TrinitySource
from folder_assets import extract_folder
from catalog_inventory import VIOLET,LAB,Z
from fbcodec import Schema

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'work/smoliv-source'
game=TrinitySource(VIOLET)
result=extract_folder(game,'pm1039/pm1039_00_00',out)
(ROOT/'evidence/smoliv-source.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='dependencies'},indent=2),flush=True)
base=out/'pokemon/data/pm1039/pm1039_00_00'
for ext in ('trmdl','trmtr','trmmt','trskl','trpokecfg'):
    schema=Schema.from_bfbs((ROOT/f'ref/SV/Flatbuffers/model/{ext}.bfbs').read_bytes())
    file=base/f'pm1039_00_00.{ext}'
    if not file.exists():
        continue
    try:
        value=schema.decode(file.read_bytes())
        (ROOT/f'evidence/smoliv-{ext}.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
        print(ext,str(value)[:2000],flush=True)
    except Exception as ex:
        print(ext,'SCHEMA ERROR',ex,flush=True)

from pathlib import Path
import json
import re
from catalog_inventory import LAB
from fbcodec import Schema

ROOT=Path(__file__).resolve().parents[1]
donor=LAB/'pilot/build/step1/species-pilot/romfs/ik_pokemon/data/pm0935/pm0935_00_00'
for ext in ('trmtr','trmdl','trmsh'):
    s=Schema.from_bfbs((ROOT/f'ref/SV/Flatbuffers/model/{ext}.bfbs').read_bytes())
    path=donor/f'pm0935_00_00.{ext}'
    value=s.decode(path.read_bytes())
    (ROOT/f'evidence/za-donor-{ext}.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
    if ext=='trmtr':
        for material in value['materials']:
            print(material['name'],[s['shader_name'] for s in material['shaders']],flush=True)
            print('TEXTURES',material['textures'],flush=True)
            print('FLOAT4',[p.get('color_name') for p in material.get('float4_parameter',[])],flush=True)
    else:
        print(ext,str(value)[:1200],flush=True)

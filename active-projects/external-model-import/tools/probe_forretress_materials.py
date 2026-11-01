"""Read-only material/mesh diagnostic for the visually incomplete PC body."""
import json
from build_smoliv_model import ROOT,schema

folder=ROOT/'build/violet-model-candidates-r1/romfs/ik_pokemon/data/pm2205/pm2205_00_00'
result={}
for ext in ('trmdl','trmsh','trmtr'):
    result[ext]=schema(ext).decode((folder/('pm2205_00_00.'+ext)).read_bytes())
path=ROOT/'qa/all-pokemon-20261030-r2/forretress-material-diagnostic.json'
path.write_text(json.dumps(result,indent=1),encoding='utf-8')
for material in result['trmtr']['materials']:
    print(material['name'],json.dumps({k:v for k,v in material.items() if k not in ('textures','float4_parameter')},ensure_ascii=True))
print('MODEL',json.dumps(result['trmdl']))
print('MESH',json.dumps(result['trmsh']))

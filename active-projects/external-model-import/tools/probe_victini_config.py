import json,struct
from pathlib import Path
from build_smoliv_model import ROOT
from source_archives import FB

qa=ROOT/'qa/all-pokemon-20261030-r2/victini-20261031-r1'
value=json.loads((ROOT/'build/all-species-r1/integration.json').read_text(encoding='utf-8'))
print('Integration keys',list(value))
records=value.get('models',[])
rec=next(r for r in records if r.get('national')==494)
print('VICTINI INTEGRATION',json.dumps({k:v for k,v in rec.items() if k not in ('sha256','motion_mapping','mapping')}))
folder=ROOT/'build/all-species-r1/all-models/romfs/ik_pokemon/data/pm2494/pm2494_00_00'
files=list(folder.glob('*.trpokecfg'));result=[]
for path in files:
    raw=path.read_bytes();fb=FB(raw);fields=fb.table(fb.u32(0))
    values={str(i):struct.unpack_from('<f',raw,field)[0] for i,field in enumerate(fields) if field and 1<=i<=12}
    result.append({'file':path.name,'field_count':len(fields),'float_fields':values})
print('CONFIG',json.dumps(result))
(qa/'placement-diagnostic.json').write_text(json.dumps({'integration':rec,'configs':result},indent=1),encoding='utf-8')

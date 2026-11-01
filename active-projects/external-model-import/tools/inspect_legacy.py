import json
from pathlib import Path
import sys
from catalog_inventory import ARCEUS,SWORD,LAB
from source_archives import Gfpak
from fbcodec import Schema

ROOT=Path(__file__).resolve().parents[1]
catalogues=json.loads((ROOT/'evidence/source-catalogues.json').read_text(encoding='utf-8'))
game=sys.argv[1]
species=int(sys.argv[2])
row=next(r for r in catalogues[game] if r['national_species']==species and not r['info'].get('shiny'))
path=(SWORD/row['archive']) if game=='sword' else (ARCEUS/'bin/archive/pokemon'/(Path(row['model']).stem+'.gfpak'))
archive=Gfpak(path)
data=archive.read_name(row['model'])
schema_path=ROOT/('ref/SWSH/Flatbuffers/Model/gfbmdl.bfbs' if game=='sword' else 'ref/LA/Flatbuffers/Model/trmdl.bfbs')
schema=Schema.from_bfbs(schema_path.read_bytes())
model=schema.decode(data)
print('CATALOGUE',row,flush=True)
if game=='sword':
    summary={k:(len(v) if isinstance(v,list) else v) for k,v in model.items()}
    print('MODEL',summary,flush=True)
    print('MESH',model.get('mesh',[])[:2],flush=True)
    print('BONE',model.get('skeleton',[])[:2],flush=True)
    print('SHAPE', [{k:v for k,v in shape.items() if k!='vertices' and k!='polygons'} for shape in model['shapes'][:2]],flush=True)
    print('MATERIAL',str(model.get('materials',[])[:1])[:3000],flush=True)
else:
    print('MODEL',model,flush=True)
    for ext in ('trmsh','trmbf','trmtr','trskl'):
        rel=str(Path(row['model']).with_suffix('.'+ext)).replace('\\','/')
        try:
            raw=archive.read_name(rel)
            schema=Schema.from_bfbs((ROOT/f'ref/LA/Flatbuffers/Model/{ext}.bfbs').read_bytes())
            value=schema.decode(raw)
            print(ext,str(value)[:3000],flush=True)
        except Exception as ex:
            print(ext,'ERROR',ex,flush=True)

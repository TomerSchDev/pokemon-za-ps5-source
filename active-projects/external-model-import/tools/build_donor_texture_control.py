"""Isolate mesh/skeleton compatibility from source shader/texture conversion."""
from pathlib import Path
import copy
import shutil
import sys
from build_smoliv_model import schema,encode_checked,DONOR,SRC,STEM

ROOT=Path(__file__).resolve().parents[1]
out=Path(sys.argv[1])
shutil.copytree(ROOT/'build/smoliv-real-r3/mods',out/'mods')
folder=out/'mods/smoliv-real-model/romfs/ik_pokemon/data/pm0935/pm0935_00_00'
s=schema('trmtr')
source=s.decode((SRC/'pm1039_00_00.trmtr').read_bytes())
native=s.decode((DONOR/(STEM+'.trmtr')).read_bytes())
materials=[]
for material in source['materials']:
    template=next((m for m in native['materials'] if m['name']==material['name']),None)
    if template is None:
        template=next(m for m in native['materials'] if ('eye' in m['name'])==('eye' in material['name']))
    converted=copy.deepcopy(template)
    converted['name']=material['name']
    if '--source-albedo' in sys.argv:
        albedo=next(t for t in material['textures'] if t['texture_name']=='BaseColorMap')
        next(t for t in converted['textures'] if t['texture_name']=='BaseColorMap')['texture_file']=albedo['texture_file'].replace('pm1039','pm0935')
    materials.append(converted)
for suffix in ('.trmtr','_rare.trmtr'):
    (folder/(STEM+suffix)).write_bytes(encode_checked(s,{'materials':materials}))
for file in DONOR.glob('*.bntx'):
    shutil.copy2(file,folder/file.name)
print('Mesh compatibility control built',flush=True)

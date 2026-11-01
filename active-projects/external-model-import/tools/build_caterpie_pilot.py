import copy
import json
from pathlib import Path
import shutil
import sys
from catalog_inventory import SWORD,LAB,Z
from sword_geometry import convert_sword_model
from sword_assets import normalize_materials,animations,choose_motion
from source_archives import Gfpak
from build_smoliv_model import schema,encode_checked,material_bridge,DONOR,STEM

ROOT=Path(__file__).resolve().parents[1]
out=Path(sys.argv[1])
shutil.copytree(ROOT/'build/smoliv-real-r6/mods',out/'mods')
romfs=out/'mods/smoliv-real-model/romfs'
dest=romfs/'ik_pokemon/data/pm0935/pm0935_00_00'
rows=json.loads((ROOT/'evidence/source-catalogues.json').read_text(encoding='utf-8'))['sword']
row=next(r for r in rows if r['national_species']==10 and not r['info'].get('shiny'))
path=SWORD/row['archive']
archive=Gfpak(path)
files,model,report=convert_sword_model(path,row)
model_stem=Path(row['model']).stem
for filename,data in files.items():
    (dest/filename).write_bytes(data)
for filename in model['textureFiles']:
    if not filename.endswith('.bntx'):
        filename+='.bntx'
    (dest/filename).write_bytes(archive.read_name(filename))
native=schema('trmtr').decode((DONOR/(STEM+'.trmtr')).read_bytes())['materials']
material,mapping=material_bridge(normalize_materials(model),native,'pm0010','pm0010',STEM)
for m in material['materials']:
    for texture in m['textures']:
        filename=texture['texture_file']
        if filename.startswith('../') or (dest/filename).exists():
            continue
        source=DONOR/filename
        if not source.is_file():
            raise ValueError('Missing legacy material texture '+filename)
        shutil.copy2(source,dest/filename)
(dest/(model_stem+'.trmtr')).write_bytes(encode_checked(schema('trmtr'),material))
animation_files,source_tracks,animation_report=animations(archive,row)
for filename,data in animation_files.items():
    (dest/filename).write_bytes(data)
tracks_schema=schema('tracr','ZA/Flatbuffers')
tracks=tracks_schema.decode((dest/(STEM+'_base.tracr')).read_bytes())
for track in tracks['track_list']['list']:
    choice=choose_motion(track['track_name'],source_tracks)
    track['track_resource']['animation']=source_tracks[choice]['animation']
    track['track_resource'].pop('material',None)
(dest/(STEM+'_base.tracr')).write_bytes(encode_checked(tracks_schema,tracks))
cat=Z.catalog_schema().decode((romfs/Z.CATALOG).read_bytes())
entry=next(e for e in cat['table'] if e['species_info']=={'species':179})
entry['model_path']='pm0935/pm0935_00_00/'+model_stem+'.trmdl'
entry['material_table_path']='pm0935/pm0935_00_00/'+model_stem+'.trmmt'
(dest/(model_stem+'.trmmt')).write_bytes(encode_checked(schema('trmmt'),{'material':[]}))
(romfs/Z.CATALOG).write_bytes(encode_checked(Z.catalog_schema(),cat))
report.update(materials=mapping,animations=animation_report,material_animation_converted=False,runtime_tested=False)
(out/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Real Sword Caterpie render pilot built',flush=True)

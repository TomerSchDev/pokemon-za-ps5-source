import json
from pathlib import Path
import shutil
import sys
from catalog_inventory import ARCEUS,Z
from legacy_geometry import convert_arceus_model
from source_archives import Gfpak
from build_smoliv_model import schema,encode_checked,material_bridge,motion_match,DONOR,STEM

ROOT=Path(__file__).resolve().parents[1]
out=Path(sys.argv[1]);shutil.copytree(ROOT/'build/smoliv-real-r6/mods',out/'mods')
romfs=out/'mods/smoliv-real-model/romfs';dest=romfs/'ik_pokemon/data/pm0935/pm0935_00_00'
rows=json.loads((ROOT/'evidence/source-catalogues.json').read_text())['arceus']
row=next(r for r in rows if r['national_species']==201 and r['info'].get('form',0)==0)
stem=Path(row['model']).stem;path=ARCEUS/'bin/archive/pokemon'/(stem+'.gfpak');archive=Gfpak(path)
files,materials,report=convert_arceus_model(path,row)
for filename,data in files.items():(dest/filename).write_bytes(data)
native=schema('trmtr').decode((DONOR/(STEM+'.trmtr')).read_bytes())['materials']
for filename,value in materials.items():
    result,mapping=material_bridge(value,native,'pm0201','pm0201',STEM)
    for material in result['materials']:
        for texture in material['textures']:
            name=texture['texture_file']
            if not name.startswith('../') and not (dest/name).exists():
                source=DONOR/name
                if not source.is_file():raise ValueError('Missing mapped texture '+name)
                shutil.copy2(source,dest/name)
    (dest/filename).write_bytes(encode_checked(schema('trmtr'),result))
tracks_schema=schema('tracr','ZA/Flatbuffers')
raw=archive.read_name(stem+'_base.tracr')
source_tracks=tracks_schema.decode(raw)
available={t['track_name']:t for t in source_tracks['track_list']['list']}
tracks=tracks_schema.decode((dest/(STEM+'_base.tracr')).read_bytes())
mapping=[]
for track in tracks['track_list']['list']:
    choice,method=motion_match(track['track_name'],available)
    for key in ('animation','material'):
        resource=available[choice]['track_resource'].get(key)
        if resource:
            filename=resource['filename'];(dest/filename).write_bytes(archive.read_name(filename))
            track['track_resource'][key]=resource
        else:track['track_resource'].pop(key,None)
    mapping.append(dict(target=track['track_name'],source=choice,method=method))
(dest/(STEM+'_base.tracr')).write_bytes(encode_checked(tracks_schema,tracks))
cat=Z.catalog_schema().decode((romfs/Z.CATALOG).read_bytes())
entry=next(e for e in cat['table'] if e['species_info']=={'species':179})
entry['model_path']='pm0935/pm0935_00_00/'+stem+'.trmdl'
entry['material_table_path']='pm0935/pm0935_00_00/'+stem+'.trmmt'
(romfs/Z.CATALOG).write_bytes(encode_checked(Z.catalog_schema(),cat))
report.update(animation_mapping=mapping,runtime_tested=False)
(out/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Real Arceus Unown render pilot built',flush=True)

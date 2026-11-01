"""Apply runtime-proven Sword skinning fixes and complete material-table dependencies."""
import hashlib
import json
from pathlib import Path
import re
from catalog_inventory import ARCEUS,SWORD
from legacy_geometry import convert_arceus_model
from sword_geometry import convert_sword_model
from build_smoliv_model import schema,encode_checked
from source_archives import Gfpak

ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'build/legacy-model-candidates-r1'
catalogues=json.loads((ROOT/'evidence/source-catalogues.json').read_text())
document=json.loads((output/'conversion.json').read_text())
for i,record in enumerate(document['models'],1):
    source=record['source'];row=next(r for r in catalogues[source] if r['model']==record['source_model'])
    old=re.search(r'pm\d{4}',row['model']).group();new=record['target_folder'].split('/')[0]
    dest=output/'romfs/ik_pokemon/data'/record['target_folder']
    if source=='sword':
        files,model,details=convert_sword_model(SWORD/row['archive'],row)
        for name,data in files.items():(dest/name.replace(old,new)).write_bytes(data.replace(old.encode(),new.encode()))
        stem=Path(row['model']).stem.replace(old,new)
        meshes=schema('trmsh').decode((dest/(stem+'.trmsh')).read_bytes())['meshes']
        material=dict(material=[dict(name='rare',material_name=[stem+'_rare.trmtr'],
            material_switches=[dict(material_name=m['mesh_shape_name'],material_flag=1) for m in meshes],material_properties=[])])
        if not (dest/(stem+'_rare.trmtr')).exists():material={'material':[]}
        (dest/(stem+'.trmmt')).write_bytes(encode_checked(schema('trmmt'),material))
        record['geometry_details']=details
        record['source_motion_tracks']=json.loads(json.dumps(record.get('source_motion_tracks',{})).replace(old,new))
        record['runtime_family_reference']='Caterpie: qa/runs/caterpie-r6 (source geometry/bone animation rendered); final placement QA separate'
    else:
        path=ARCEUS/'bin/archive/pokemon'/(Path(row['model']).stem+'.gfpak')
        archive=Gfpak(path)
        (dest/Path(row['materials']).name.replace(old,new)).write_bytes(archive.read_name(row['materials']).replace(old.encode(),new.encode()))
        record['runtime_family_reference']='Unown: qa/runs/unown-r1 (source geometry/bone animation rendered)'
    record['sha256']={str(p.relative_to(output)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file()}
    if i%20==0:print('REPAIRED',i,'/',len(document['models']),flush=True)
document['repairs']=['Sword native vertex input layout','Sword rig_offset=0','Sword per-mesh bone influence summaries','Sword external placement parent for below-origin source bounds','Older material-table dependencies']
(output/'conversion.json').write_text(json.dumps(document,indent=1),encoding='utf-8')
print('Legacy geometry repair complete',flush=True)

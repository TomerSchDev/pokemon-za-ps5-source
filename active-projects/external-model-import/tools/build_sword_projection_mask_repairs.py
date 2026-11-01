"""Remove conditional Sword battle projections from static ZA material masks."""
from pathlib import Path
import hashlib,json,os
from build_smoliv_model import schema,encode_checked
from run_pc_gallery import ROOT,QA,WORK

inventory=json.loads((QA/'inventory-v4.json').read_text(encoding='utf-8'))['targets']
folders={Path(t['model_path']).parent.as_posix():t['key'] for t in inventory if t['source']=='sword'}
base=ROOT/'build/all-species-r1/all-models/romfs/ik_pokemon/data'
destination=QA/'sword-projection-mask-repairs-r1';repairs=[]
for folder,key in folders.items():
    for source in (base/folder).glob('*.trmtr'):
        value=schema('trmtr').decode(source.read_bytes());changed=[]
        for material in value['materials']:
            for texture in material['textures']:
                if texture['texture_name']=='LayerMaskMap' and Path(texture['texture_file']).name in ('projection_effect_col.bntx','dummy_col.bntx'):
                    changed.append({'material':material['name'],'old':texture['texture_file']})
                    texture['texture_file']=Path(folder).name+'_black_msk.bntx'
        if not changed:continue
        payload=encode_checked(schema('trmtr'),value);relative=Path('ik_pokemon/data')/folder/source.name
        target=destination/'romfs'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert target.read_bytes()==payload
        else:target.write_bytes(payload)
        repairs.append({'relative':relative.as_posix(),'keys':[key],'materials':changed,'sha256':hashlib.sha256(payload).hexdigest()})
destination.mkdir(exist_ok=True)
result={'repairs':repairs,'models_affected':sorted({k for r in repairs for k in r['keys']}),'source_build_unchanged':True,'runtime_validation':'pending'}
(destination/'projection-mask-repairs.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
cache=WORK/'render-fixes';certificate=cache/'verified-hashes.json';hashes=json.loads(certificate.read_text(encoding='utf-8'))
for row in repairs:
    relative='mods/00-auto-material-fixes/romfs/'+row['relative'];target=cache/relative
    payload=(destination/'romfs'/row['relative']).read_bytes();target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():assert target.read_bytes()==payload,'Unexpected cross-repair material conflict.'
    else:
        temporary=target.with_name(target.name+'.qa-new');temporary.write_bytes(payload);os.replace(temporary,target)
    hashes[relative]=row['sha256']
temporary=certificate.with_suffix('.qa-new');temporary.write_text(json.dumps(hashes),encoding='utf-8');os.replace(temporary,certificate)
print(json.dumps({'files':len(repairs),'models':len(result['models_affected']),'keys':result['models_affected']}),flush=True)

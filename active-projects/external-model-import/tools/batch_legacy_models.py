"""Convert all staged older-game geometry/materials, with explicit per-model failures and QA state."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sys
from catalog_inventory import ARCEUS,SWORD
from legacy_geometry import convert_arceus_model
from sword_geometry import convert_sword_model
from sword_assets import normalize_materials,animations
from source_archives import Gfpak
from build_smoliv_model import schema,encode_checked,material_bridge,DONOR,STEM

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    bank=json.loads((ROOT/'source-bank/source-bank.json').read_text(encoding='utf-8'))
    native=schema('trmtr').decode((DONOR/(STEM+'.trmtr')).read_bytes())['materials']
    neutral=ROOT/'build/smoliv-real-r6/mods/smoliv-real-model/romfs/ik_pokemon/data/pm0935/pm0935_00_00'
    records=[]
    for entry in bank['models']:
        game=entry['source']
        if game=='violet':continue
        unique={r['model']:r for r in entry['catalogue_entries'] if not r['info'].get('shiny')}
        for row in unique.values():
            species=row['national_species'];stem=Path(row['model']).stem
            old_pm=re.search(r'pm\d{4}',stem).group()
            new_pm=f'pm{2000+species:04d}'
            new_stem=stem.replace(old_pm,new_pm)
            folder_stem=new_stem if len(new_stem)==12 else new_stem+'_00'
            target=out/'romfs/ik_pokemon/data'/new_pm/folder_stem
            rec=dict(source=game,national_species=species,source_model=row['model'],target_folder=f'{new_pm}/{folder_stem}',
                     runtime_tested=False,gameplay_configuration_complete=False,status='candidate')
            try:
                if target.exists():raise ValueError('Variant namespace collision')
                target.mkdir(parents=True)
                root=ARCEUS if game=='arceus' else SWORD
                archive_path=root/entry['archive']
                archive=Gfpak(archive_path)
                if game=='arceus':
                    files,material_sets,details=convert_arceus_model(archive_path,row)
                else:
                    files,model,details=convert_sword_model(archive_path,row)
                    material_sets={stem+'.trmtr':normalize_materials(model)}
                    rare=next((r for r in entry['catalogue_entries'] if r['info'].get('shiny') and r['info'].get('gender',0)==row['info'].get('gender',0)),None)
                    texture_names=set(model['textureFiles'])
                    if rare:
                        value=schema('gfbmdl','SWSH/Flatbuffers/Model').decode(archive.read_name(rare['model']))
                        material_sets[stem+'_rare.trmtr']=normalize_materials(value)
                        texture_names.update(value['textureFiles'])
                    for name in texture_names:
                        if not name.endswith('.bntx'):name+='.bntx'
                        files[name]=archive.read_name(name)
                    motion_files,tracks,motion_info=animations(archive,row)
                    files.update(motion_files)
                    rec['source_motion_tracks']=tracks
                    rec['animation_conversion']=motion_info
                for name,data in files.items():
                    dest=target/name.replace(old_pm,new_pm);dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.write_bytes(data.replace(old_pm.encode(),new_pm.encode()))
                rec['materials']={}
                for name,value in material_sets.items():
                    converted,mapping=material_bridge(value,native,old_pm,new_pm,folder_stem)
                    for material in converted['materials']:
                        for texture in material['textures']:
                            name2=texture['texture_file']
                            if name2.startswith('../') or (target/name2).exists() or name2 in (folder_stem+'_white_msk.bntx',folder_stem+'_black_msk.bntx'):continue
                            source=DONOR/name2
                            if not source.is_file():raise ValueError('Missing mapped texture '+name2)
                            fallback=folder_stem+'_native_'+source.name
                            (target/fallback).write_bytes(source.read_bytes());texture['texture_file']=fallback
                    (target/name.replace(old_pm,new_pm)).write_bytes(encode_checked(schema('trmtr'),converted))
                    rec['materials'][name]=mapping
                for suffix in ('_white_msk.bntx','_black_msk.bntx'):
                    if len(folder_stem)!=len(STEM):raise ValueError('Unexpected legacy variant stem length')
                    (target/(folder_stem+suffix)).write_bytes((neutral/(STEM+suffix)).read_bytes().replace(STEM.encode(),folder_stem.encode()))
                rec['geometry_details']=details
                rec['status']='geometry_materials_converted'
                rec['files']=sum(p.is_file() for p in target.rglob('*'))
                rec['sha256']={str(p.relative_to(out)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file()}
            except Exception as ex:
                rec['status']='conversion_failed';rec['error']=str(ex)
            records.append(rec)
            if len(records)%10==0:print('LEGACY',len(records),dict(collections.Counter(r['status'] for r in records)),flush=True)
    summary=dict(models=len(records),status=dict(collections.Counter(r['status'] for r in records)),species_activated=0,installable_gameplay_mod=False)
    (out/'conversion.json').write_text(json.dumps(dict(summary=summary,models=records),indent=1),encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()

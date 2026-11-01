"""Recover native ZA transparency semantics without modifying converted geometry."""
from pathlib import Path
import collections,hashlib,json,os,re
from build_smoliv_model import ROOT,schema,encode_checked,material_bridge
from run_pc_gallery import QA,WORK

def main():
    native=json.loads((QA/'native-blend-materials.json').read_text(encoding='utf-8'))
    templates=[]
    for key in ('0517-00-0','0608-00-0','0475-01-0'):
        row=next(r for r in native['matches'] if r['key']==key)
        assert len(row['materials'])==1
        templates.append({'source_native_key':key,'source_path':row['path'],'material':row['materials'][0]})
    reference=ROOT/'ref/ZA/material-templates/transparency-native.json';reference.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps({'templates':templates,'source_game_unchanged':True},indent=1)
    if reference.exists() and reference.read_text(encoding='utf-8')!=data:
        backup=reference.with_name('transparency-native.before-add-preset.json')
        assert not backup.exists();backup.write_bytes(reference.read_bytes())
        reference.write_text(data,encoding='utf-8')
    elif not reference.exists():reference.write_text(data,encoding='utf-8')
    audit=json.loads((QA/'lost-transparency-audit.json').read_text(encoding='utf-8'))
    inventory=json.loads((QA/'inventory-v4.json').read_text(encoding='utf-8'))['targets']
    registered={Path(t['model_path']).parent.as_posix():[] for t in inventory if t['imported']}
    for t in inventory:
        if t['imported']:registered[Path(t['model_path']).parent.as_posix()].append(t['key'])
    grouped=collections.defaultdict(list)
    for row in audit['materials']:
        if row['folder'] in registered:grouped[(row['build'],row['folder'],row['material_file'])].append(row)
    bank=None;archives={};repairs=[];failures=[];destination=QA/'transparency-repairs-r1'
    for (build,folder,filename),rows in grouped.items():
        try:
            new_pm,stem=folder.split('/')
            if build.startswith('violet'):
                source_folder=ROOT/'source-bank/violet/pokemon/data'/rows[0]['source_folder']
                old_pm=rows[0]['source_folder'].split('/')[0]
                original=schema('trmtr').decode((source_folder/filename).read_bytes())
            else:
                from catalog_inventory import ARCEUS
                from source_archives import Gfpak
                from legacy_geometry import arceus_materials
                if bank is None:bank=json.loads((ROOT/'source-bank/source-bank.json').read_text(encoding='utf-8'))['models']
                model=next(m for m in json.loads((ROOT/'build'/build/'conversion.json').read_text(encoding='utf-8'))['models'] if m['target_folder']==folder)
                assert model['source']=='arceus','Only the audited Arceus transparent legacy material is expected.'
                entry=next(e for e in bank if e['source']=='arceus' and any(c['model']==model['source_model'] for c in e['catalogue_entries']))
                if entry['archive'] not in archives:archives[entry['archive']]=Gfpak(ARCEUS/entry['archive'])
                original=arceus_materials(schema('trmtr','LA/Flatbuffers/Model').decode(archives[entry['archive']].read_name(filename)))
                old_pm=re.search(r'pm\d{4}',filename).group()
            new_filename=filename.replace(old_pm,new_pm)
            relative=Path('ik_pokemon/data')/folder/new_filename
            base=QA/'material-name-repairs-r1/romfs'/relative
            if not base.exists():base=ROOT/'build/all-species-r1/all-models/romfs'/relative
            converted=schema('trmtr').decode(base.read_bytes());changed=[]
            for row in rows:
                source=next(m for m in original['materials'] if m['name']==row['material'])
                fixed,_=material_bridge({'materials':[source]},[],old_pm,new_pm,stem)
                material=fixed['materials'][0]
                before=next(m for m in converted['materials'] if m['name']==material['name'])
                # Reuse a pre-existing authenticated fallback for a source with
                # no native normal/AO texture rather than introducing donor data.
                for texture in material['textures']:
                    filename2=texture['texture_file']
                    if filename2.startswith('../'):continue
                    available=ROOT/'build/all-species-r1/all-models/romfs'/relative.parent/filename2
                    if not available.exists() and filename2 not in (stem+'_white_msk.bntx',stem+'_black_msk.bntx'):
                        match=next(t for t in before['textures'] if t['texture_name']==texture['texture_name'])
                        texture['texture_file']=match['texture_file']
                converted['materials'][converted['materials'].index(before)]=material
                changed.append({'name':material['name'],'source_alpha':source.get('alpha_type'),'target_alpha':material['alpha_type'],'native_shaders':[s['shader_name'] for s in material['shaders']]})
            payload=encode_checked(schema('trmtr'),converted)
            output=destination/'romfs'/relative;output.parent.mkdir(parents=True,exist_ok=True)
            if output.exists():assert output.read_bytes()==payload
            else:output.write_bytes(payload)
            repairs.append({'relative':relative.as_posix(),'keys':registered[folder],'materials':changed,'sha256':hashlib.sha256(payload).hexdigest()})
        except Exception as error:failures.append({'folder':folder,'file':filename,'error':str(error)})
    result={'repairs':repairs,'failures':failures,'models_affected':sorted({k for r in repairs for k in r['keys']}),
            'source_game_and_original_build_unchanged':True,'native_transparent_templates':templates,'runtime_validation':'pending'}
    destination.mkdir(exist_ok=True);(destination/'transparency-repairs.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({'files':len(repairs),'models':len(result['models_affected']),'failures':failures}),flush=True)
    assert not failures,'Incomplete transparency staging; nothing published to the PC cache.'
    cache=WORK/'render-fixes';certificate=cache/'verified-hashes.json';hashes=json.loads(certificate.read_text(encoding='utf-8'))
    for row in repairs:
        relative='mods/00-auto-material-fixes/romfs/'+row['relative']
        payload=(destination/'romfs'/row['relative']).read_bytes();assert hashlib.sha256(payload).hexdigest()==row['sha256']
        target=cache/relative;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert target.read_bytes()==payload
        else:
            temporary=target.with_name(target.name+'.qa-new');temporary.write_bytes(payload);os.replace(temporary,target)
        hashes[relative]=row['sha256']
    temporary=certificate.with_suffix('.qa-new');temporary.write_text(json.dumps(hashes),encoding='utf-8');os.replace(temporary,certificate)
    print('Published certified native-transparency PC overlay.',flush=True)

if __name__=='__main__':main()

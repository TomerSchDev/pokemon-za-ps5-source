"""Give each converted source model native ZA controls in its own namespace.

Immutable geometry is hardlinked. Generated control files use atomic replacement,
so neither source-bank files nor converter output can be modified through a link.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import re
import sys
from catalog_inventory import ARCEUS,SWORD,Z
from source_archives import Gfpak,FB
from build_smoliv_model import schema,encode_checked,motion_match
from native_donors import node_names,choose
from sword_assets import choose_motion
from retarget_layer_channels import retarget,root_names
from native_controller_modules import strip_missing_optional_modules
import za_folder

from storage_paths import data_root
ROOT=data_root()
CONTROL={'.trpokecfg','.tracn','.tracl','.tracp','.tracs','.tralk','.trssp','.trmdt','.trslp','.trmdd','.traef','.trcrv','.hkx'}
TEMPLATES={}


def read_motion_list(data,s):
    """Read only TrackList.list, never serialize an incomplete source controller.

    Some SV species have additional state groups beyond ZA's schema. The full
    source controller stays in source-controllers, while native ZA owns states.
    Each individual motion/resource is still decoded strictly.
    """
    fb=FB(data);root=fb.table(fb.u32(0));at=root[0]+fb.u32(root[0]);fields=fb.table(at)
    count,vec=fb.vec(fields[0]);tracks=[]
    for i in range(count):
        ptr=vec+i*4;tracks.append(s._table(data,ptr+fb.u32(ptr),'Titan.Animation.Track'))
    extensions=[i for i,v in enumerate(fields) if i>1 and v]
    return tracks,extensions


def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.new')
    temp.write_bytes(data)
    temp.replace(path)


def linked(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():target.unlink()
    os.link(source,target)


def renamed(data,donor,folder,internal):
    pm,stem=folder.split('/')
    oldpm=donor['folder'].split('/')[0]
    return data.replace(donor['stem'].encode(),stem.encode()).replace(oldpm.encode(),pm.encode()).replace(
        ('PLAY_PV_%04d'%donor['species']).encode(),('PLAY_PV_%04d'%internal).encode())


def build_one(rec,bank,personal,donors,out):
    folder=rec['target_folder'];pm,stem=folder.split('/')
    game=rec.get('source','violet')
    converted=ROOT/'build'/('violet-model-candidates-r1' if game=='violet' else 'legacy-model-candidates-r1')
    source=converted/'romfs/ik_pokemon/data'/folder
    target=out/'all-models/romfs/ik_pokemon/data'/folder
    target.mkdir(parents=True,exist_ok=True)
    for path in source.rglob('*'):
        if path.is_file():linked(path,target/path.relative_to(source))
    model=next(target.glob('*.trmdl'))
    skeleton=next(p for p in target.glob('*.trskl') if p.stem==model.stem)
    donor=choose(personal,node_names(skeleton.read_bytes()),donors)
    oldbase='ik_pokemon/data/'+donor['folder']+'/'
    g=za_folder.game()
    if donor['folder'] not in TEMPLATES:
        names,_,_=za_folder.folder_files(donor['folder'])
        TEMPLATES[donor['folder']]={}
        for path in names:
            if not path.startswith(oldbase):continue
            rel=Path(path[len(oldbase):])
            if rel.suffix in CONTROL or ('locators' in rel.parts and rel.suffix=='.trskl'):
                TEMPLATES[donor['folder']][rel]=g.read(path)
    for rel,payload in TEMPLATES[donor['folder']].items():
        renamed_rel=renamed(rel.as_posix().encode(),donor,folder,personal['Info']['SpeciesInternal']).decode()
        atomic(target/renamed_rel,renamed(payload,donor,folder,personal['Info']['SpeciesInternal']))
    tracks_schema=schema('tracr','ZA/Flatbuffers')
    tracks=tracks_schema.decode(renamed(g.read(oldbase+donor['stem']+'_base.tracr'),donor,folder,personal['Info']['SpeciesInternal']))
    if game=='violet':
        source_raw=(source/(stem+'_base.tracr')).read_bytes()
        atomic(target/'source-controllers'/(stem+'_base.tracr'),source_raw)
        source_tracks,extensions=read_motion_list(source_raw,tracks_schema)
        available={t['track_name']:t['track_resource'] for t in source_tracks}
    elif game=='sword':available=rec['source_motion_tracks'];extensions=[]
    else:
        archive=Gfpak(ARCEUS/bank['archive'])
        old_stem=Path(rec['source_model']).stem
        oldpm=re.search(r'pm\d{4}',old_stem).group()
        source_raw=archive.read_name(old_stem+'_base.tracr')
        atomic(target/'source-controllers'/(old_stem+'_base.tracr'),source_raw)
        source_tracks,extensions=read_motion_list(source_raw,tracks_schema)
        available={t['track_name']:t['track_resource'] for t in source_tracks}
        for resources in available.values():
            for kind in ('animation','material'):
                if kind in resources:
                    filename=resources[kind]['filename']
                    newname=filename.replace(oldpm,pm)
                    atomic(target/newname,archive.read_name(filename).replace(oldpm.encode(),pm.encode()))
                    resources[kind]['filename']=newname
    mapping=[]
    for track in tracks['track_list']['list']:
        if game=='sword':
            choice=choose_motion(track['track_name'],available)
            method='legacy action-category mapping; visual QA required'
        else:choice,method=motion_match(track['track_name'],available)
        for kind in ('animation','material'):
            if kind in available[choice]:track['track_resource'][kind]=copy.deepcopy(available[choice][kind])
            else:track['track_resource'].pop(kind,None)
        mapping.append(dict(target=track['track_name'],source=choice,method=method))
    atomic(target/(stem+'_base.tracr'),encode_checked(tracks_schema,tracks))
    # A prefix rename cannot add the target's absent limbs to a donor's explicit
    # bone channel mask. Retain all native opaque fields and append target nodes.
    layer_names=root_names((source/(stem+'_base.tracl')).read_bytes()) if game=='violet' else node_names(skeleton.read_bytes())
    layer_path=target/(stem+'_base.tracl')
    layer_payload,channel_changes=retarget(layer_path.read_bytes(),layer_names)
    atomic(layer_path,layer_payload)
    module_path=target/(stem+'_base.tracn')
    module_payload,removed_modules=strip_missing_optional_modules(module_path.read_bytes(),set(os.listdir(target)),schema('tracn','SV/Flatbuffers/animation'))
    if removed_modules:atomic(module_path,module_payload)
    missing=[]
    for track in tracks['track_list']['list']:
        for resource in track['track_resource'].values():
            if not (target/resource['filename']).is_file():missing.append(resource['filename'])
    for matfile in target.glob('*.trmtr'):
        for mat in schema('trmtr').decode(matfile.read_bytes())['materials']:
            for texture in mat.get('textures',[]):
                name=texture['texture_file']
                if not name.startswith('../') and not (target/name).is_file():missing.append(name)
    if missing:raise ValueError('Missing payloads: '+str(sorted(set(missing))))
    catalog=json.loads(renamed(json.dumps(donor['catalog']).encode(),donor,folder,personal['Info']['SpeciesInternal']))
    catalog['model_path']=folder+'/'+model.name
    catalog['material_table_path']=folder+'/'+model.stem+'.trmmt'
    catalog['config_path']=folder+'/'+stem+'.trpokecfg'
    icon=next((p for p in (target/'icon').glob('*.bntx')),None)
    if icon:
        for rare in (0,1):atomic(target/'icon'/(stem+'_00_'+str(rare)+'.bntx'),icon.read_bytes())
        catalog['icon_path']=folder+'/'+stem+'_00.bntx'
    else:catalog.pop('icon_path',None)
    for field in ('model_path','material_table_path','config_path'):
        if not (out/'all-models/romfs/ik_pokemon/data'/catalog[field]).is_file():raise ValueError('Catalog path missing: '+catalog[field])
    return dict(source=game,national=personal['Info']['SpeciesNational'],internal=personal['Info']['SpeciesInternal'],
        form=personal['Info'].get('Form',0),folder=folder,catalog=catalog,donor_species=donor['species'],
        target_bone_channels=channel_changes,missing_optional_donor_modules_removed=removed_modules,
        animation_mapping=mapping,source_animations=len(available),icon_authentic=bool(icon),
        source_controller_extra_groups_not_imported=extensions,
        shiny_icon_distinct=False,legacy_material_animation_converted=game!='sword',
        files=sum(p.is_file() for p in target.rglob('*')),runtime_tested=False,
        warnings=['Native donor AI, collision and effect timing require per-species QA'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('out',type=Path);p.add_argument('--species',default='all');args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    selected=None if args.species=='all' else {int(v) for v in args.species.split(',')}
    bank=json.loads((ROOT/'source-bank/source-bank.json').read_text())['models']
    donors=json.loads((ROOT/'evidence/native-control-donors.json').read_text())['donors']
    personal=Z.personal_schema().decode(Z.read(Z.PERSONAL))['Table']
    bynational={(r['Info']['SpeciesNational'],r['Info'].get('Form',0)):r for r in personal if r['Info'].get('SpeciesNational')}
    natives={r['Info']['SpeciesNational'] for r in personal if r.get('IsPresentInGame')}
    records=[]
    for kind in ('violet','legacy'):
        file=ROOT/f'build/{"violet" if kind=="violet" else "legacy"}-model-candidates-r1/conversion.json'
        if file.exists():records+=json.loads(file.read_text())['models']
        else:records += [json.loads(f.read_text())['record'] for f in sorted((file.parent/'progress').glob('*.json'))]
    result=[];errors=[];skipped=[]
    for rec in records:
        n=rec['national_species']
        if n in natives or (selected is not None and n not in selected):continue
        if rec['status']!='geometry_materials_converted':
            errors.append(dict(national=n,folder=rec['target_folder'],error=rec.get('error',rec['status'])));continue
        game=rec.get('source','violet')
        if game=='violet':
            b=next(b for b in bank if b['source']==game and b['folder']==rec['source_folder'])
            row=b['catalogue_entries'][0]
        else:
            b=next(b for b in bank if b['source']==game and any(r['model']==rec['source_model'] for r in b['catalogue_entries']))
            row=next(r for r in b['catalogue_entries'] if r['model']==rec['source_model'])
        form=row['info'].get('form',0)
        if (n,form) not in bynational:
            skipped.append(dict(national=n,form=form,reason='No native personal row; engine/save extension required'));continue
        try:
            item=build_one(rec,b,bynational[(n,form)],donors,args.out)
            item['gender']=row['info'].get('gender',0)
            item['catalog']['species_info']={k:v for k,v in dict(species=item['internal'],form=form,gender=item['gender']).items() if v}
            result.append(item)
            if len(result)%10==0:print('BRIDGE',len(result),'errors',len(errors),flush=True)
        except Exception as ex:
            errors.append(dict(national=n,folder=rec['target_folder'],error=str(ex)))
            print('ERROR',n,rec['target_folder'],str(ex),flush=True)
        (args.out/'integration-progress.json').write_text(json.dumps(dict(models=result,errors=errors,skipped=skipped),indent=1),encoding='utf-8')
    summary=dict(models=len(result),species=len({r['national'] for r in result}),errors=len(errors),skipped=len(skipped),
                 runtime_tested=False,independent_tables_built=False)
    (args.out/'integration.json').write_text(json.dumps(dict(summary=summary,models=result,errors=errors,skipped=skipped),indent=1),encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()

"""Experimental minimal native render controls, preserving model/config/collision."""
from pathlib import Path
import copy,json,sys
from storage_paths import data_root
from integrate_model_assets import CONTROL,read_motion_list
from build_smoliv_model import schema,encode_checked,motion_match
from sword_assets import choose_motion
from retarget_layer_channels import retarget,target_names

ROOT=data_root();QA=ROOT/'qa/all-pokemon-20261030-r2'
def build(targets,destination):
    source_root=ROOT/'build/all-species-r1/all-models/romfs/ik_pokemon/data'
    donor=source_root/'pm2010/pm2010_00_00'
    sc=schema('tracr','ZA/Flatbuffers')
    legacy=None;report=[]
    assert destination.resolve().is_relative_to(QA.resolve()) and not destination.exists()
    for t in targets:
        folder=Path(t['model_path']).parent;stem=folder.name;pm=folder.parts[0]
        out=destination/'romfs/ik_pokemon/data'/folder;out.mkdir(parents=True)
        def rename(b):
            return b.replace(b'pm2010_00_00',stem.encode()).replace(b'pm2010',pm.encode()).replace(b'PLAY_PV_0010',('PLAY_PV_%04d'%t['internal']).encode())
        for path in donor.rglob('*'):
            rel=path.relative_to(donor)
            if path.is_file() and path.suffix not in ('.trpokecfg','.hkx') and (path.suffix in CONTROL or ('locators' in rel.parts and path.suffix=='.trskl')):
                dest=out/rename(rel.as_posix().encode()).decode();dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(rename(path.read_bytes()))
        if t['source']=='sword':
            if legacy is None:legacy=json.loads((ROOT/'build/legacy-model-candidates-r1/conversion.json').read_text(encoding='utf-8'))['models']
            rec=next(x for x in legacy if x.get('national_species')==t['national'] and x.get('target_folder')==folder.as_posix())
            available=copy.deepcopy(rec['source_motion_tracks'])
            import re
            oldpm=re.search(r'pm\d{4}',rec['source_model']).group()
            for resources in available.values():
                for item in resources.values():item['filename']=item['filename'].replace(oldpm,pm)
        elif t['source']=='violet':
            raw=(ROOT/'build/violet-model-candidates-r1/romfs/ik_pokemon/data'/folder/(stem+'_base.tracr')).read_bytes()
            tracks,_=read_motion_list(raw,sc);available={x['track_name']:x['track_resource'] for x in tracks}
        elif t['source']=='arceus':
            raw=(source_root/folder/(stem+'_base.tracr')).read_bytes()
            tracks,_=read_motion_list(raw,sc);available={x['track_name']:x['track_resource'] for x in tracks}
        else:raise ValueError('Only imported models may receive a render-control probe')
        value=sc.decode(rename((donor/'pm2010_00_00_base.tracr').read_bytes()));mapping=[]
        for track in value['track_list']['list']:
            if t['source']=='sword':choice=choose_motion(track['track_name'],available);method='Sword action mapping'
            else:choice,method=motion_match(track['track_name'],available)
            for kind in ('animation','material'):
                if kind in available[choice]:track['track_resource'][kind]=copy.deepcopy(available[choice][kind])
                else:track['track_resource'].pop(kind,None)
            mapping.append({'target':track['track_name'],'source':choice,'method':method})
        (out/(stem+'_base.tracr')).write_bytes(encode_checked(sc,value))
        layer=out/(stem+'_base.tracl')
        patched,channel_changes=retarget(layer.read_bytes(),target_names(t,ROOT))
        layer.write_bytes(patched)
        report.append({'key':t['key'],'native_graph_source':'Weedle','geometry_config_collision_preserved':True,
                       'target_bone_channels':channel_changes,'mapping':mapping,'experimental':True})
    (destination/'controls.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
    return report

if __name__=='__main__':
    targets=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))['targets']
    print('Control overlays:',len(build(targets,Path(sys.argv[2]))))

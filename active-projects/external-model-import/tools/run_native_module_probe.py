"""A/B probe: retain the original native graph, repair its mask and missing module."""
from pathlib import Path
import json,os,shutil,subprocess,sys
from run_pc_gallery import ROOT,QA,WORK,inspect_run
from retarget_layer_channels import retarget,target_names
from build_native_control_repairs import strip_missing_optional_modules,schema

def main():
    spec=json.loads((QA/'wide/layer-registry-probe-r39.json').read_text(encoding='utf-8'))
    source=WORK/'layer-registry-probe/mods/all-models'
    dest=WORK/'native-module-probe/mods'
    if not dest.exists():shutil.copytree(source,dest/'all-models',copy_function=os.link)
    sc=schema('tracn','SV/Flatbuffers/animation');report=[]
    for target in spec['targets']:
        folder=Path(target['model_path']).parent;stem=folder.name
        base=dest/'all-models/romfs/ik_pokemon/data'/folder
        layers,changes=retarget((base/(stem+'_base.tracl')).read_bytes(),target_names(target,ROOT))
        modules,removed=strip_missing_optional_modules((base/(stem+'_base.tracn')).read_bytes(),set(os.listdir(base)),sc)
        out=dest/'00-native-module-probe/romfs/ik_pokemon/data'/folder;out.mkdir(parents=True,exist_ok=True)
        (out/(stem+'_base.tracl')).write_bytes(layers);(out/(stem+'_base.tracn')).write_bytes(modules)
        report.append({'key':target['key'],'layer_changes':changes,'missing_modules_removed':removed})
    (QA/'wide/native-module-probe-r40-build.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
    print(json.dumps(report),flush=True)
    name='pc-native-module-probe-r40'
    cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),name,'--link-local-mods',str(dest),
         '--seconds','230','--stop-after-shots','--watch-models',str(QA/'wide/layer-registry-probe-r39.json'),
         '--save-src',str(QA/'wide/layer-registry-probe-r39'),
         '--cache-src',str(WORK/'runs/pc-native-baseline-r23/cache'),
         '--input',','.join(spec['inputs']),
         '--shot-at','900,1250,1650,2000,'+','.join(str(n) for pair in spec['body_frame_pairs'] for n in pair),
         '--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
    with (QA/'wide/native-module-probe-r40-driver.log').open('xb') as out:subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,check=True)
    result=inspect_run(name,spec['targets'],spec['body_frame_pairs'])
    print(json.dumps([{k:t.get(k) for k in ('key','render_status','animation_status','body_pixels_changed_gt10')} for t in result['targets']]),flush=True)

if __name__=='__main__':main()

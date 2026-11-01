from pathlib import Path
import json,os,shutil
from run_pc_gallery import ROOT,QA,WORK
from retarget_layer_channels import retarget,root_names
from run_pc_wide import plan

def main():
    targets=json.loads((QA/'wide/wide-import-002.json').read_text(encoding='utf-8'))['targets']
    targets=[t for t in targets if t['national'] in (125,140,141)]
    assert len(targets)==3
    inputs,shots=plan(len(targets))
    spec=QA/'wide/layer-registry-probe-r39.json'
    assert not spec.exists()
    spec.write_text(json.dumps({'mode':'box','targets':targets,'body_frame_pairs':shots,'inputs':inputs},indent=1),encoding='utf-8')
    source=WORK/'runs/pc-wide-import-002-r1/mods'
    dest=WORK/'layer-registry-probe/mods'
    assert source.is_dir() and not dest.exists()
    shutil.copytree(source,dest,copy_function=os.link)
    report=[]
    for target in targets:
        folder=Path(target['model_path']).parent;stem=folder.name
        raw=(source/'00-auto-render-fixes/romfs/ik_pokemon/data'/folder/(stem+'_base.tracl')).read_bytes()
        if target['source']=='violet':
            names=root_names((ROOT/'build/violet-model-candidates-r1/romfs/ik_pokemon/data'/folder/(stem+'_base.tracl')).read_bytes())
        else:
            from all_pc_inventory_v3 import SkeletonAuditSchema
            schema=SkeletonAuditSchema.from_bfbs((ROOT/'ref/SV/Flatbuffers/model/trskl.bfbs').read_bytes());schema.extensions=set()
            model_stem=Path(target['model_path']).stem
            skeleton=schema.decode((source/'all-models/romfs/ik_pokemon/data'/folder/(model_stem+'.trskl')).read_bytes())
            names=[node['name'] for node in skeleton['transform_nodes']]
        patched,details=retarget(raw,names)
        out=dest/'00-00-channel-probe/romfs/ik_pokemon/data'/folder/(stem+'_base.tracl')
        out.parent.mkdir(parents=True);out.write_bytes(patched)
        report.append({'key':target['key'],'source':target['source'],'details':details})
    (QA/'wide/layer-registry-probe-r39-build.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()

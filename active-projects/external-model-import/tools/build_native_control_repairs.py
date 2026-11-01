"""Stage native control repairs for PC QA; immutable source geometry is untouched."""
from pathlib import Path
import collections,json,os,sys
from build_simple_render_controls import ROOT,QA,schema,encode_checked
from retarget_layer_channels import retarget,target_names
from native_controller_modules import strip_missing_optional_modules

def build(destination):
    assert destination.resolve().is_relative_to(QA.resolve()) and not destination.exists()
    destination.mkdir(parents=True)
    targets=[t for t in json.loads((QA/'inventory-v3.json').read_text(encoding='utf-8'))['targets'] if t['imported']]
    sc=schema('tracn','SV/Flatbuffers/animation');report=[];failures=[]
    for t in targets:
        try:
            folder=Path(t['model_path']).parent;stem=folder.name
            base=ROOT/'build/all-species-r1/all-models/romfs/ik_pokemon/data'/folder
            controls=base
            if t['key']=='0031-00-0':controls=QA/'validated-render-fixes-r1/romfs/ik_pokemon/data'/folder
            names=target_names(t,ROOT)
            patched,details=retarget((controls/(stem+'_base.tracl')).read_bytes(),names)
            raw=(controls/(stem+'_base.tracn')).read_bytes()
            modules,removed=strip_missing_optional_modules(raw,set(os.listdir(base))|set(os.listdir(controls)),sc)
            output=destination/'romfs/ik_pokemon/data'/folder;output.mkdir(parents=True)
            if details.get('node_registry',{}).get('added') or details.get('base_bone_channels',{}).get('added'):
                (output/(stem+'_base.tracl')).write_bytes(patched)
            if removed:(output/(stem+'_base.tracn')).write_bytes(modules)
            report.append({'key':t['key'],'source':t['source'],'channel_changes':details,'missing_optional_modules_removed':removed,
                           'preserved_validated_minimal_graph':t['key']=='0031-00-0'})
        except Exception as exc:failures.append({'key':t['key'],'error':str(exc)})
    result={'targets':len(targets),'staged':len(report),'failures':failures,'source_build_unchanged':True,
            'geometry_and_materials_unchanged':True,'runtime_validation':'pending; isolated Electabuzz bone-channel probe only',
            'removed_module_types':dict(collections.Counter(e['animation_name'] for r in report for e in r['missing_optional_modules_removed'])),
            'models':report}
    (destination/'controls-report.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='models'}),flush=True)

if __name__=='__main__':build(Path(sys.argv[1]))

import json
from build_smoliv_model import ROOT

result=[];checked=0
for build in ('violet-model-candidates-r1','legacy-model-candidates-r1'):
    value=json.loads((ROOT/'build'/build/'conversion.json').read_text(encoding='utf-8'))
    for model in value['models']:
        if model.get('status')!='geometry_materials_converted':continue
        checked+=1
        for filename,rows in model.get('materials',{}).items():
            for material in rows:
                if any('transparent' in name.lower() for name in material['source_shaders']):
                    result.append({'build':build,'species':model['national_species'],'folder':model['target_folder'],
                                   'source_folder':model.get('source_folder'),'material_file':filename,**material})
path=ROOT/'qa/all-pokemon-20261030-r2/lost-transparency-audit.json'
path.write_text(json.dumps({'checked_models':checked,'materials':result},indent=1),encoding='utf-8')
print(json.dumps({'checked_models':checked,'materials':len(result),'species':sorted({x['species'] for x in result}),'legacy':sorted({x['species'] for x in result if x['build'].startswith('legacy')})}),flush=True)

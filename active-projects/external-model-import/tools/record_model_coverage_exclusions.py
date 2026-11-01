import json
from run_pc_gallery import ROOT,QA

inventory=json.loads((QA/'inventory-v4.json').read_text(encoding='utf-8'))
registered={t['national'] for t in inventory['targets']}
converted=set()
for build in ('violet-model-candidates-r1','legacy-model-candidates-r1'):
    value=json.loads((ROOT/'build'/build/'conversion.json').read_text(encoding='utf-8'))
    converted.update(t['national_species'] for t in value['models'] if t.get('status')=='geometry_materials_converted')
names=json.loads((QA/'species-names.json').read_text(encoding='utf-8'))
rows=[{'national':n,'name':names[n],
       'status':'converted_source_available_but_not_registered_in_current_build' if n in converted else 'no_converted_model_in_current_supplied_sources'} for n in sorted(set(range(1,1026))-registered)]
result={'registered_species_test_scope':len(registered),'excluded_species':rows,'scope':'Coverage of the current registered PC build; this is not all 1,025 national species.'}
(QA/'wide/coverage-exclusions-r1.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
print(json.dumps(result),flush=True)

"""Check converted mesh material names and stage only unambiguous namespace repairs."""
from pathlib import Path
import hashlib,json,re
from build_smoliv_model import ROOT,schema,encode_checked

qa=ROOT/'qa/all-pokemon-20261030-r2'
base=ROOT/'build/all-species-r1/all-models/romfs'
inventory=json.loads((qa/'inventory-v4.json').read_text(encoding='utf-8'))['targets']
dest=qa/'material-name-repairs-r1';dest.mkdir(exist_ok=True)
report=[];unresolved=[];seen=set();checked=0
for target in inventory:
    if not target['imported']:continue
    folder=Path('ik_pokemon/data')/Path(target['model_path']).parent
    if folder.as_posix() in seen:continue
    seen.add(folder.as_posix());directory=base/folder
    required=set()
    for path in directory.glob('*.trmsh'):
        mesh=schema('trmsh').decode(path.read_bytes())
        for shape in mesh['meshes']:
            required.update(m['material_name'] for m in shape.get('materials',[]))
    for path in directory.glob('*.trmtr'):
        checked+=1;value=schema('trmtr').decode(path.read_bytes())
        names={m['name'] for m in value['materials']};missing=required-names
        if not missing:continue
        mapping={}
        for name in sorted(missing):
            matches=[old for old in names if re.sub(r'pm\d{4}', 'PM',old)==re.sub(r'pm\d{4}','PM',name)]
            if len(matches)!=1:unresolved.append({'key':target['key'],'file':path.name,'missing':name,'matches':matches})
            else:mapping[matches[0]]=name
        if len(mapping)!=len(missing):continue
        for material in value['materials']:
            if material['name'] in mapping:material['name']=mapping[material['name']]
        assert required<={m['name'] for m in value['materials']}
        payload=encode_checked(schema('trmtr'),value)
        relative=folder/path.name;out=dest/'romfs'/relative;out.parent.mkdir(parents=True,exist_ok=True)
        if out.exists():assert out.read_bytes()==payload
        else:out.write_bytes(payload)
        report.append({'key':target['key'],'relative':relative.as_posix(),'renamed_materials':mapping,'sha256':hashlib.sha256(payload).hexdigest()})
result={'checked_model_folders':len(seen),'checked_material_files':checked,'repairs':report,'unresolved':unresolved,'original_build_unchanged':True,'runtime_validation':'pending'}
(dest/'material-bindings-audit.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
print(json.dumps(result),flush=True)

import json
from build_smoliv_model import ROOT,schema
from nas_game_cache import install
import za_folder

install();game=za_folder.game();qa=ROOT/'qa/all-pokemon-20261030-r2'
inventory=json.loads((qa/'inventory-v4.json').read_text(encoding='utf-8'))['targets']
report=[];seen=set();failures=[]
for t in inventory:
    if t['imported']:continue
    path='ik_pokemon/data/'+t['model_path'].replace('.trmdl','.trmtr')
    if path in seen:continue
    seen.add(path)
    try:
        raw=game.read(path)
        if b'Blend' not in raw and b'\x03\x00\x00\x00Add\x00' not in raw:continue
        value=schema('trmtr').decode(raw)
        materials=[m for m in value['materials'] if 'Blend' in m.get('alpha_type','') or m.get('alpha_type')=='Add']
        if materials:
            report.append({'key':t['key'],'path':path,'materials':materials})
            print(t['key'],json.dumps([{'name':m['name'],'alpha_type':m.get('alpha_type'),'shaders':[s['shader_name'] for s in m['shaders']]} for m in materials]),flush=True)
    except Exception as error:failures.append({'path':path,'error':str(error)[:120]})
(qa/'native-blend-materials.json').write_text(json.dumps({'checked':len(seen),'matches':report,'read_failures':failures},indent=1),encoding='utf-8')
print('Checked',len(seen),'native model material tables; transparent groups',len(report),'unreadable',len(failures),flush=True)

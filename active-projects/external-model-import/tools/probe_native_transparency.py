import json
from build_smoliv_model import ROOT,schema
from nas_game_cache import install
import za_folder

install();game=za_folder.game();report=[]
for species in (92,93,94,479,448,720):
    stem='pm%04d_00_00'%species;path='ik_pokemon/data/pm%04d/%s/%s.trmtr'%(species,stem,stem)
    try:materials=schema('trmtr').decode(game.read(path))['materials']
    except Exception as error:print(species,type(error).__name__,str(error)[:100]);continue
    report.append({'species':species,'path':path,'materials':materials})
    print(species,json.dumps([{'name':m['name'],'alpha_type':m.get('alpha_type'),'shaders':[s['shader_name'] for s in m['shaders']],'int_extra':m.get('int_extra')} for m in materials]))
(ROOT/'qa/all-pokemon-20261030-r2/native-transparency-diagnostic.json').write_text(json.dumps(report,indent=1),encoding='utf-8')

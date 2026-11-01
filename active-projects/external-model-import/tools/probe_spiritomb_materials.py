import json
from build_smoliv_model import ROOT,schema

result={}
for label,folder,stem in [('source',ROOT/'source-bank/violet/pokemon/data/pm0442/pm0442_00_00','pm0442_00_00'),('converted',ROOT/'build/violet-model-candidates-r1/romfs/ik_pokemon/data/pm2442/pm2442_00_00','pm2442_00_00')]:
    mats=schema('trmtr').decode((folder/(stem+'.trmtr')).read_bytes())['materials']
    result[label]=mats
    for m in mats:
        print(label,m['name'],json.dumps({'shaders':m['shaders'],'textures':m['textures'],'ints':m.get('int_parameter',[])}))
(ROOT/'qa/all-pokemon-20261030-r2/spiritomb-material-diagnostic.json').write_text(json.dumps(result,indent=1),encoding='utf-8')

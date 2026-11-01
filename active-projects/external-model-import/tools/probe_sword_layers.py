import json
from build_smoliv_model import ROOT,schema
from catalog_inventory import SWORD
from source_archives import Gfpak
bank=json.loads((ROOT/'source-bank/source-bank.json').read_text(encoding='utf-8'))['models']
records=json.loads((ROOT/'build/legacy-model-candidates-r1/conversion.json').read_text(encoding='utf-8'))['models']
result=[]
for species in (494,506):
    rec=next(r for r in records if r['national_species']==species)
    entry=next(e for e in bank if e['source']=='sword' and any(c['model']==rec['source_model'] for c in e['catalogue_entries']))
    value=schema('gfbmdl','SWSH/Flatbuffers/Model').decode(Gfpak(SWORD/entry['archive']).read_name(rec['source_model']))
    result.append({'species':species,'materials':value['materials'],'textureFiles':value['textureFiles']})
    for m in value['materials']:
        print(species,m['name'],json.dumps({'textures':[{**t,'resolved_file':value['textureFiles'][t.get('texture_index',0)]} for t in m.get('textures',[])]}))
(ROOT/'qa/all-pokemon-20261030-r2/sword-layer-diagnostic.json').write_text(json.dumps(result,indent=1),encoding='utf-8')

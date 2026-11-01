import collections,json
from build_smoliv_model import ROOT,schema
qa=ROOT/'qa/all-pokemon-20261030-r2'
native=json.loads((qa/'native-blend-materials.json').read_text(encoding='utf-8'))
print('Native blend types:',json.dumps({mode:[r['key'] for r in native['matches'] if any(m.get('alpha_type')==mode for m in r['materials'])] for mode in sorted({m['alpha_type'] for r in native['matches'] for m in r['materials']})}))
audit=json.loads((qa/'lost-transparency-audit.json').read_text(encoding='utf-8'))
groups=collections.defaultdict(list);cache={}
for row in audit['materials']:
    if not row['build'].startswith('violet'):continue
    path=ROOT/'source-bank/violet/pokemon/data'/row['source_folder']/row['material_file']
    if str(path) not in cache:cache[str(path)]=schema('trmtr').decode(path.read_bytes())['materials']
    source=next(m for m in cache[str(path)] if m['name']==row['material'])
    groups[source.get('alpha_type','<absent>')].append({'species':row['species'],'name':source['name'],'source_shaders':row['source_shaders']})
print('Source blend groups:',json.dumps({k:{'count':len(v),'examples':v[:4]} for k,v in groups.items()}))

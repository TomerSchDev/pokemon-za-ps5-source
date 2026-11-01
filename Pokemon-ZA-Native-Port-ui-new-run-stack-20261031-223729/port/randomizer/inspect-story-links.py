"""Read-only current-build boss/event/cinematic inventory. Does not patch ROMFS."""
from pathlib import Path
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[2]
PC=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
sys.path.insert(0,str(PC/'randomizer-lab'))
from inspect_game import Game,fnv
from reflection_reader import Buffer,Schema
from nso import Nso
out=ROOT/'evidence/randomizer-story-links';out.mkdir(exist_ok=True)
game=PC/'update-2.0.2-20261025/game'
g=Game(game/'romfs.bin',PC/'release-v0.1.4/ZA Recomp/zaprompts/_internal/ooz.dll')
n=Nso(game/'exefs/main');assert n.build_id=='b1f12fd919eae86ab8a978317677e64bce443d1f'
paths={'ik_event/bin/event_boss_battle_data/boss_btl_data_global.bin',
       'ik_event/bin/quest/main_quest.bin','ik_event/bin/phase/phase.bin',
       'ik_event/bin/event_control/event_control.bin'}
strings=[]
for match in re.finditer(rb'[ -~]{6,}',n.image):
    s=match.group().decode()
    if re.search(r'ik_event/.*(boss|demo|scene)|world/.*(demo|timeline)|BossBattle.*|Demo.*Pokemon',s,re.I):
        strings.append({'offset':match.start(),'text':s})
        if s.endswith(('.bin','.bfbs')) and re.fullmatch(r'[\w/.-]+',s):paths.add(s)
paths|={p.rsplit('.',1)[0]+ext for p in list(paths) for ext in ('.bin','.bfbs')}
inventory=[];tables={}
for p in sorted(paths):
    if p in g.entries:data=g.read(p)
    elif f'{fnv(p):016x}' in g.fileindex:data=g.file(p)
    else:continue
    assert len(data)<8<<20
    target=out/'extracted'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    inventory.append({'path':p,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()});tables[p]=data
boss_path='ik_event/bin/event_boss_battle_data/boss_btl_data_global.bin'
b=Buffer(tables[boss_path]);bosses=[]
for t in b.tables(b.scalar(0,'I'),0):
    fields={}
    for i,loc in enumerate(b.fields(t)):
        if loc is None:continue
        try:fields[str(i)]=b.text(loc)
        except (ValueError,UnicodeDecodeError):continue
    bosses.append({'offset':t,'string_fields':fields})
config=json.loads((ROOT/'evidence/randomizer-field-move-audit/decoded/pokemon_spawner_data_array.json').read_bytes())
enc=json.loads((ROOT/'evidence/randomizer-field-move-audit/decoded/encount_data_array.json').read_bytes())
spawners={r['id']:r for db in config['values'] for r in db['root']}
encounters={r['id']:r for db in enc['values'] for r in db['root']}
def clean(x):
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if not k.startswith('$')}
    if isinstance(x,list):return [clean(v) for v in x]
    return x
for boss in bosses:
    boss['links']=[]
    for field in ('0','1'):
        key=boss['string_fields'].get(field);sp=spawners.get(key)
        link={'field_inferred':field,'spawner_id':key,'resolved':bool(sp)}
        if sp:
            link['spawner']=clean(sp)
            link['encounters']=[clean(encounters.get(x['encountDataId'],{})) for x in sp['encountDataInfoList']]
        boss['links'].append(link)
absol=[r for r in bosses if any('0359' in s for s in r['string_fields'].values())]
pack_names=[x for x in g.names if re.search(r'0359|boss|demo|cinema|timeline',x,re.I)]
record={'build_id':n.build_id,'tables':inventory,'boss_event_records':len(bosses),
        'battle_spawners_resolved':sum(x['links'][1]['resolved'] for x in bosses),
        'absol_event_records':len(absol),'candidate_pack_count':len(pack_names),
        'limits':['Unknown boss fields retain numeric identifiers; their roles are inferred from string joins.',
                  'Pack names and references do not establish that actors can be substituted safely.',
                  'This read-only audit does not modify the console, game data or r14 binary.']}
for name,value in [('inventory',record),('boss-graph',bosses),('absol-case-study',absol),('candidate-packs',pack_names),('strings',strings)]:
    (out/(name+'.json')).write_text(json.dumps(value,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2));print('Example packs:',json.dumps(pack_names[:25]))

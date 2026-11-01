from pathlib import Path
import json,re,struct,collections,hashlib
from reflection_reader import Buffer
ROOT=Path(__file__).resolve().parent
def read(n):return json.loads((ROOT/'decoded'/n).read_text())
def flat(n):return [r for db in read(n)['values'] for r in db['root']]
def plain(x):
    if isinstance(x,dict):return {k:plain(v) for k,v in x.items() if not k.startswith('$')}
    if isinstance(x,list):return [plain(v) for v in x]
    return x
def local(path):return Buffer((ROOT/'private-tables'/path).read_bytes())
names=(ROOT.parents[1]/'pkhex/PKHeX.Core/Resources/text/other/en/text_Species_en.txt').read_text(encoding='utf-8-sig').splitlines()
b=local('avalon/data/personal_array.bin');personal=[]
for p in b.tables(b.scalar(0,'I'),0):
    q=b.field(p,0);internal,form,national=struct.unpack_from('<HHH',b.data,q)
    personal.append(dict(internal=internal,form=form,national=national,name=names[national] if national<len(names) else '?',
        present=bool(b.value(p,1,'?')),dex=b.value(p,2,'H'),types=[b.value(p,3,'B'),b.value(p,4,'B')],
        evolution_stage=b.value(p,17,'B'),offset=p))
personal_index={(x['internal'],x['form']):x for x in personal}
b=local('world/exl/pokemon/megaevo_data/megaevo_data.bin');mega=[]
for p in b.tables(b.scalar(0,'I'),0):
    internal=b.value(p,0,'H');form=b.value(p,3,'I');pi=personal_index.get((internal,form))
    mega.append(dict(internal=internal,item=b.value(p,1,'i'),from_form=b.value(p,2,'I'),to_form=form,
        animation=b.string(p,4),short_animation=b.string(p,5),present=bool(pi and pi['present']),name=pi['name'] if pi else '?',offset=p))
trainers=read('trdata_array.json')['values'];enc=flat('encount_data_array.json');pokemon=flat('pokemon_data_array.json');spawns=flat('pokemon_spawner_data_array.json')
ed={x['id']:x for x in enc};sd={x['id']:x for x in spawns};td={x['trid']:x for x in trainers}
references=collections.defaultdict(list);missing=[]
for s in spawns:
    for x in s['encountDataInfoList']:
        key=x['encountDataId'];references[key].append(s['id'])
        if key not in ed:missing.append([s['id'],key])
b=local('ik_event/bin/event_boss_battle_data/boss_btl_data_global.bin');boss=[]
for p in b.tables(b.scalar(0,'I'),0):
    fields={str(i):b.text(q) for i,q in enumerate(b.fields(p)) if q is not None}
    links=[]
    for key in ['0','1']:
        sp=sd.get(fields.get(key));links.append(dict(field=key,spawner=fields.get(key),resolved=sp is not None,
            encounters=[plain(ed.get(e['encountDataId'],{})) for e in sp['encountDataInfoList']] if sp else []))
    boss.append(dict(offset=p,fields=fields,links=links,ally_trainer_resolved=fields.get('2') in td))
b=local('ik_event/bin/event_trainer_battle_data/trainer_btl_data_global.bin');events=[]
for p in b.tables(b.scalar(0,'I'),0):
    fields={str(i):b.string(p,i) for i in range(13) if b.field(p,i) is not None}
    events.append(dict(offset=p,fields=fields))
def brief(pk):
    sp=pk.get('devId',pk.get('devNo'));form=pk.get('formId',pk.get('formNo',0));p=personal_index.get((sp,form),{})
    return dict(internal=sp,form=form,name=p.get('name','?'),level=pk.get('level',pk.get('minLevel')),offset=pk['$fields'].get('devId',pk['$fields'].get('devNo')))
trainer_summary=[dict(id=t['trid'],mega=bool(t['megEvolution']),last_hand=bool(t['lastHand']),party=[brief(t['poke'+str(i)]) for i in range(1,7) if t['poke'+str(i)]['devId']]) for t in trainers]
enc_summary=[dict(id=e['id'],**brief(e),spawners=references[e['id']],boss='boss' in e['id']) for e in enc]
base=[p for p in personal if p['present'] and p['form']==0 and p['internal']!=0]
mega_keys={(m['internal'],m['from_form'],m['item']) for m in mega if m['present']}
mega_resolved=[t['trid'] for t in trainers if t['megEvolution'] and any(
    (t[f'poke{i}']['devId'],t[f'poke{i}']['formId'],t[f'poke{i}']['item']) in mega_keys for i in range(1,7))]
mega_unresolved=[t['trid'] for t in trainers if t['megEvolution'] and t['trid'] not in mega_resolved]
summary=dict(trainer_rows=len(trainers),nonempty_trainer_slots=sum(len(t['party']) for t in trainer_summary),mega_enabled_trainer_rows=sum(t['mega'] for t in trainer_summary),
    mega_trainer_rows_with_recognized_stone_tuple=len(mega_resolved),mega_trainer_rows_needing_script_review=mega_unresolved,
    encounter_rows=len(enc),encounter_rows_referenced_by_spawners=sum(bool(references[e['id']]) for e in enc),pokemon_event_npc_rows=len(pokemon),
    spawner_rows=len(spawns),spawner_references=sum(map(len,references.values())),unresolved_spawner_references=len(missing),
    personal_rows=len(personal),present_base_species=len(base),mega_conversion_rows=len(mega),present_mega_conversion_rows=sum(x['present'] for x in mega),
    boss_event_rows=len(boss),boss_event_rows_with_resolved_ally=sum(x['ally_trainer_resolved'] for x in boss),trainer_event_rows=len(events),
    boss_field_0_resolved_as_spawner_id=sum(x['links'][0]['resolved'] for x in boss),
    boss_field_1_resolved_as_spawner_id=sum(x['links'][1]['resolved'] for x in boss),
    boss_families=sorted(set(re.findall(r'boss_(\d{4})',' '.join(x['id'] for x in enc)))),
    notes=['Counts include test/debug/unused rows; not a claim that every row occurs during normal play.','Personal base schema field 2 is ushort; current pkNX DLC struct is not applied.','Boss event field names remain inferred from reference joins; strings themselves are observed.'])
for name,data in [('personal-catalog',personal),('mega-catalog',mega),('trainers',trainer_summary),('encounters',enc_summary),('boss-reference-graph',boss),('trainer-event-links',events),('coverage',summary),('unresolved-spawner-references',missing)]:
    (ROOT/(name+'.json')).write_text(json.dumps(data,indent=2,ensure_ascii=True))
print(json.dumps(summary,indent=2))

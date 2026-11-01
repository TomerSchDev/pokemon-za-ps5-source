"""Audit all TMs; prepare targeted, seeded early-rock routes and authored moves.

The broad capability pools are audit evidence only. Ordinary wild encounters
retain the core randomizer output; optional side quests are not guaranteed.
"""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
PC=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
sys.path.insert(0,str(PC/'randomizer-lab'))
sys.path.insert(0,str(PC/'launcher-v0.2.0/source'))
from reflection_reader import Buffer
from fb_codec import Codec,plain
D=ROOT/'evidence/randomizer-field-move-audit/decoded'
def load(n):return json.loads((D/(n+'.json')).read_text())
def walk(v):
    if isinstance(v,dict):
        yield v
        for k,x in v.items():
            if not k.startswith('$'):yield from walk(x)
    elif isinstance(v,list):
        for x in v:yield from walk(x)
def clean(v):
    if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if not k.startswith('$')}
    if isinstance(v,list):return [clean(x) for x in v]
    return v
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def vector(b,p,i):
    f=b.field(p,i)
    return [b.scalar(x,'H') for x in b.vector(f,2)] if f else []
base=PC/'ingame-randomizer/prepared-streamed'
a=json.loads((base/'tables.json').read_text())
names=(PC.parent/'pkhex/PKHeX.Core/Resources/text/other/en/text_Moves_en.txt').read_text(encoding='utf-8-sig').splitlines()
pfile=ROOT/'evidence/randomizer-field-move-audit/extracted/avalon/data/personal_array.bin'
b=Buffer(pfile.read_bytes());personal={}
for p in b.tables(b.scalar(0,'I'),0):
    info=b.field(p,0);species=b.scalar(info,'H');form=b.scalar(info+2,'H')
    personal[species,form]={'tms':set(vector(b,p,22)), 'reminder':set(vector(b,p,24))}
for p in a['personal']:
    key=p['species'],p['form']
    personal[key].update(p)
attrs={x['wazaAttributeId']:set(x['wazaIdList']) for x in load('waza_attribute_data')['root']}
private=[x for x in walk(load('field_wazagimmick_private_array')) if 'gimmickId' in x]
used={x['gimmickId'] for x in private}
public=[x for x in load('field_wazagimmick_public')['root'] if x['gimmickId'] in used]
# Preserve each attribute separately (stricter than replacing the whole OR).
used_attrs={x['wazaAttribute'] for x in walk(public) if x.get('wazaAttribute')}
unknown_attrs=sorted(used_attrs-set(attrs))
roles={k:sorted(attrs[k]) for k in sorted(used_attrs) if k in attrs}
# Type-only field gates also exist. Move types come from the pinned move table.
wfile=ROOT/'evidence/randomizer-field-move-audit/extracted/avalon/data/waza_array.bin'
wb=Buffer(wfile.read_bytes())
move_info={wb.value(p,0,'H'):{'type':wb.value(p,2,'B'),'power':wb.value(p,5,'B'),'usable':wb.value(p,1,'?')} for p in wb.tables(wb.scalar(0,'I'),0)}
types={x['wazaType'] for x in walk(public) if 'wazaType' in x and x['wazaType']!=18 and x.get('wazaTypeCompare')}
for tp in sorted(types):roles[f'FieldType{tp}']=sorted(m for m,v in move_info.items() if v['type']==tp and v['usable'])
assert not any(c['requiredPower'] for x in public for c in x['conditionParam']), 'Power gates require a damage model'
itemfile=ROOT/'evidence/randomizer-rewards-research/extracted/world/exl/item_data/item_data/item_data.bin'
ib=Buffer(itemfile.read_bytes());tms=[]
for p in ib.tables(ib.scalar(0,'I'),0):
    if ib.value(p,5,'i')!=6:continue
    item=ib.value(p,0,'i');move=ib.value(p,11,'H');number=ib.value(p,12,'i')+1
    tms.append({'item':item,'number':number,'move':move,'name':f'TM{number:03d} {names[move]}',
                'roles':[k for k,v in roles.items() if move in v]})
assert len(tms)==160 and sorted(t['number'] for t in tms)==list(range(1,161))
field_moves=set().union(*(set(v) for v in roles.values()))
relevant_tm={t['move'] for t in tms}
def signature(p):
    levels={}
    for move in p.get('learnset',[]):
        if move['level']<0:continue
        for role,moves in roles.items():
            if move['move'] in moves:levels[role]=min(levels.get(role,101),max(1,move['level']))
    return set(p['tms'])&relevant_tm,levels
sigs={k:signature(p) for k,p in personal.items() if 'learnset' in p}
def dominates(candidate,original):
    ct,cn=sigs[candidate];ot,on=sigs[original]
    return ct>=ot and all(cn.get(r,101)<=lev for r,lev in on.items())
pools={}
for key in sigs:
    if not any(sigs[key]):continue
    choices=[s for s in a['pool'] if (s,0) in sigs and dominates((s,0),key)]
    pools[f'{key[0]}:{key[1]}']=choices
enc={x['id']:x for x in walk(load('encount_data_array')) if 'devNo' in x}
extracted=ROOT/'evidence/randomizer-field-move-audit/extracted/world/ik_data/field/pokemon/encount_data/encount_data/encount_data_array'
codec=Codec(extracted.with_suffix('.bfbs').read_bytes())
original_tree=codec.decode(extracted.with_suffix('.bin').read_bytes())
wild_template=codec.encode(original_tree,force_defaults=True)
decoded_template=codec.decode(wild_template)
assert plain(decoded_template)==plain(original_tree),'Progression template changed original semantics'
encoded_enc={x['id']:x for x in walk(decoded_template) if 'devNo' in x}
rows=[];guards=[]
for f in a['tables']['wild']['rows_files']:
    for r in json.loads((base/f['file']).read_text()):
        key=r['species'],r['form'];pool=pools.get(f'{key[0]}:{key[1]}',[])
        source=enc[r['identity']]
        assert source['devNo']==key[0] and source['formNo']==key[1]
        # Keep only the proven early-rock provider and authored move sets.
        # Do not constrain ordinary encounters for optional side-quest coverage.
        rock_provider=r['identity'] in ('ect_a0102_w01_v01_z659_tuto','ect_a0102_w01_v01_z659')
        fixed=rock_provider or bool(source.get('wazaList'))
        choices=[] if fixed else [s for s in pool if s!=key[0]]
        if key not in sigs or not any(sigs.get(key,(set(),{}))):
            if not fixed:continue
        fields={k:{'offset':encoded_enc[r['identity']]['$fields'][k],'bytes':4,'signed':True} for k in ('devNo','formNo','sex')}
        guards.append({'identity':r['identity'],'species':key[0],'form':key[1], 'fields':fields,
                       'generated_fields':r['fields'],
                       'pool':[] if fixed else pool,'fixed':fixed,'rock_provider':rock_provider,'min_level':source['minLevel'],
                       'original_sex':source['sex']})
        rows.append({'identity':r['identity'],'species':key[0],'form':key[1], 'choices':len(choices),'fixed':fixed})
learners={t['move']:{key for key,p in personal.items() if p.get('present') and t['move'] in p['tms']} for t in tms}
reward_choices={}
for t in tms:
    # The exact quest attributes are separate roles, so Water Gun, Hypnosis,
    # Sludge Bomb etc. cannot be replaced merely by another move of that type.
    # Until event scripts have been exhaustively solved, keep every later
    # research TM at its original level. A field-equivalent move alone is not
    # proof that an NPC does not explicitly ask for the original move.
    choices=[t['item']]
    assert t['item'] in choices
    reward_choices[str(t['item'])]=choices
# Main mission 03's actual rock accepts these move attributes. The tutorial
# Bunnelby and its unchanged spawn trigger are pinned above. Keep its usable
# alternative in the SAME research-level-2 slot, never later in the run.
rock=next(t for t in tms if t['item']==619)
early=[t['item'] for t in tms if set(t['roles'])>=set(rock['roles']) and t['move'] in personal[659,0]['tms']]
assert 619 in early and any(t['move']==280 and t['item'] in early for t in tms)
reward_choices['619']=early
assert any(x['identity']=='ect_a0102_w01_v01_z659_tuto' and x['fixed'] and x['species']==659 for x in guards)
rock_moves=set(attrs['WazaDestructionRock'])
natural=[];low_natural=set()
for sp in a['pool']:
    p=personal[sp,0]
    learned=[m for m in p['learnset'] if 0<=m['level']<=3 and m['move'] in rock_moves]
    if learned:natural.append({'species':sp,'name':p['name'],'moves':[{'move':m['move'],'name':names[m['move']],'level':m['level']} for m in learned]})
    if any(0<=m['level']<=4 and m['move'] in rock_moves for m in p['learnset']):low_natural.add(sp)
tm_routes=[]
for item in (619,358):
    tm=next(t for t in tms if t['item']==item)
    candidates=[{'species':sp,'name':personal[sp,0]['name']} for sp in a['pool'] if sp not in low_natural and tm['move'] in personal[sp,0]['tms']]
    assert len(candidates)>30
    tm_routes.append({'item':item,'name':tm['name'],'move':tm['move'],'candidates':candidates})
assert len(natural)>10
spec={'schema':4,'build_id':a['build_id'],'algorithm':'za202-story-guard-v2',
      'wild_template_file':'progression-wild.bin','wild_template_sha256':hashlib.sha256(wild_template).hexdigest(),'wild_bytes':len(wild_template),
      'source_bytes':(base/a['tables']['wild']['file']).stat().st_size,
      'guards':guards,'reward_choices':reward_choices,'tm_count':len(tms),'roles':list(roles),
      'rock':{'natural_candidates':natural,'tm_routes':tm_routes,'locations':['ect_a0102_w01_v01_z659_tuto','ect_a0102_w01_v01_z659'],
              'min_spawn_level':3,'max_spawn_level':4},
      'source_hashes':{'personal':sha(pfile),'moves':sha(wfile),'items':sha(itemfile)},
      'limitations':['Only the early rock barrier and authored move sets have targeted encounter protection.',
                     'Optional species/move side quests are not guaranteed; the broad capability constraints were removed at the user request.',
                     'Later research TMs retain their original sources; a full story-script dependency proof is not complete.']}
out=ROOT/'port/randomizer/reward-assets'
(out/'progression-wild.bin').write_bytes(wild_template)
(out/'progression.json').write_text(json.dumps(spec,separators=(',',':')),encoding='utf-8')
audit={'build_id':a['build_id'],'tm_count':len(tms),'tms':sorted(tms,key=lambda x:x['number']),
       'roles':roles,'unresolved_attributes':unknown_attrs,'public_gimmicks':clean(public),'private_gimmicks':clean(private),
       'candidate_pools':pools,'encounters':rows,'reward_choices':reward_choices,
       'personal_sha256':sha(pfile),'item_table_sha256':sha(itemfile),
       'limitations':['Field-table audit is not a complete story-script dependency graph.',
                      'Unknown quest species, item counts, evolution and scripted checks require separate analysis.']}
(ROOT/'evidence/randomizer-progression-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
print(json.dumps({'tms':len(tms),'roles':len(roles),'field_tms':len(relevant_tm),'wild_rows':len(rows),
                 'rows_with_alternatives':sum(r['choices']>0 for r in rows),'bunnelby_pool':pools.get('659:0'),
                 'rock_smash_alternatives':reward_choices.get('619')}))
print(json.dumps({'natural_rock_candidates':len(natural),'TM_routes':[(x['name'],len(x['candidates'])) for x in tm_routes]}))
if '--inspect-early' in sys.argv:
    rock=set(roles['WazaDestructionRock'])
    print(json.dumps([{'id':i,'species':x['devNo'],'min':x['minLevel'],'choices':[s for s in pools.get(f"{x['devNo']}:{x['formNo']}",[]) if any(0<=m['level']<=x['minLevel'] and m['move'] in rock for m in personal[(s,0)].get('learnset',[]))]} for i,x in enc.items() if 'a0102_w01' in i and x['minLevel']<=7]))

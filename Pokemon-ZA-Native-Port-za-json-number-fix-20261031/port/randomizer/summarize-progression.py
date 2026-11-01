"""Inspect exact ZA 2.0.2 moves and spawn data without changing the game."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
PC=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
sys.path.insert(0,str(PC/'randomizer-lab'))
from reflection_reader import Buffer
D=ROOT/'evidence/randomizer-field-move-audit/decoded'
def load(n):return json.loads((D/(n+'.json')).read_text())
def clean(v):
    if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if not k.startswith('$')}
    if isinstance(v,list):return [clean(x) for x in v]
    return v
def walk(v):
    if isinstance(v,dict):
        yield v
        for k,x in v.items():
            if not k.startswith('$'):yield from walk(x)
    elif isinstance(v,list):
        for x in v:yield from walk(x)
assets=json.loads((PC/'ingame-randomizer/prepared-streamed/tables.json').read_text())
enc={x['id']:x for x in walk(load('encount_data_array')) if 'devNo' in x}
public=clean(load('field_wazagimmick_public'))['root']
private=clean(load('field_wazagimmick_private_array'))
print('PRIVATE SAMPLE',json.dumps(private['values'][0]['root'][:2]))
print('GIMMICKS',json.dumps([x for x in public if x['gimmickId'].startswith(('QUEST_','HEDORO_WALL_QUEST','TSUTA_WALL_QUEST','FREEZED','ICE_BRIDGE'))]))
print('EARLY BUNNELBY',json.dumps([clean(x) for x in enc.values() if x['devNo']==659 and x['minLevel']<=10]))
print('ASSETS',list(assets), 'PERSONAL SAMPLE',assets['personal'][1])
pfile=ROOT/'evidence/randomizer-field-move-audit/extracted/avalon/data/personal_array.bin'
b=Buffer(pfile.read_bytes());ps=[]
for p in b.tables(b.scalar(0,'I'),0):
    info=b.field(p,0);species=b.scalar(info+4,'H');form=b.scalar(info+2,'H')
    if species in [659,158,498,152,66]:
        ptr=b.field(p,22);tm=[b.scalar(x,'H') for x in b.vector(ptr,2)] if ptr else []
        ps.append({'species':species,'form':form,'tms':tm,'present':b.value(p,1,'?')})
print('TM INFO',json.dumps(ps))

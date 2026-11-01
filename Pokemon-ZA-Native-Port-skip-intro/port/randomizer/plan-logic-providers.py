"""Read-only feasibility of small, seeded progression-provider teams."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
PC=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
sys.path.insert(0,str(PC/'randomizer-lab'))
from reflection_reader import Buffer
a=json.loads((PC/'ingame-randomizer/prepared-streamed/tables.json').read_text())
audit=json.loads((ROOT/'evidence/randomizer-progression-audit.json').read_text())
tm={t['move'] for t in audit['tms']};b=Buffer((ROOT/'evidence/randomizer-field-move-audit/extracted/avalon/data/personal_array.bin').read_bytes());moves={}
for p in b.tables(b.scalar(0,'I'),0):
    f=b.field(p,0);sp=b.scalar(f,'H');form=b.scalar(f+2,'H')
    if form or sp not in a['pool']:continue
    moves[sp]={b.scalar(v,'H') for v in b.vector(b.field(p,22),2)}&tm
names={p['species']:p['name'] for p in a['personal'] if p['form']==0}
left=tm.copy();team=[]
while left:
    sp=max(moves,key=lambda sp:len(moves[sp]&left));hit=moves[sp]&left
    if not hit:break
    team.append({'species':sp,'name':names[sp],'covers':len(hit)});left-=hit
print(json.dumps({'team':team,'uncovered':sorted(left)}))

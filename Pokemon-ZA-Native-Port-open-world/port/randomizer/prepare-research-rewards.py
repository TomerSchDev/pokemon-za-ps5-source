"""Prepare a pinned, bounded research-reward table; does not modify a console."""
from pathlib import Path
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[2]
PC=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
sys.path.insert(0,str(PC/'randomizer-lab'))
from reflection_reader import Buffer

source=ROOT/'evidence/randomizer-rewards-research/extracted/ik_event/bin/research_lv/research_lv.bin'
raw=source.read_bytes()
expected='442a5f71711b05aca2c368a59c115229ad1fa4bfddc613f997824d8865beefc7'
assert hashlib.sha256(raw).hexdigest()==expected
b=Buffer(raw);tables=b.tables(b.scalar(0,'I'),0);assert len(tables)==50
names=(PC.parent/'pkhex/PKHeX.Core/Resources/text/items/text_Items_en.txt').read_text(encoding='utf-8-sig').splitlines()
audit=json.loads((ROOT/'evidence/randomizer-progression-audit.json').read_text())
progression=json.loads((ROOT/'port/randomizer/reward-assets/progression.json').read_text())
tm_names={x['item']:x['name'] for x in audit['tms']}
def item_name(item):return tm_names.get(item,names[item])
storage=PC.parent/'pkhex/PKHeX.Core/Items/ItemStorage9ZA.cs'
storage_text=re.sub(r'//[^\n]*','',storage.read_text())
def category(name):
    match=re.search(r'\b'+name+r'\s*=>\s*\[([^]]+)\]',storage_text)
    assert match,name
    return {int(x) for x in re.findall(r'\b[0-9]+\b',match[1])}
categories={'Medicine':0,'Balls':1,'Other':2,'Treasure':3,'Berry':5,'TM':6,'MegaStones':7}
legal={item:(name,pocket) for name,pocket in categories.items() for item in category(name)}
excluded=category('Key')|category('Unreleased')
item_path=ROOT/'evidence/randomizer-rewards-research/extracted/world/exl/item_data/item_data/item_data.bin'
item_raw=item_path.read_bytes();items=Buffer(item_raw);pool=[]
for p in items.tables(items.scalar(0,'I'),0):
    item=items.value(p,0,'i');pocket=items.value(p,5,'i');limit=items.value(p,6,'i')
    if item not in legal or item in excluded or limit<=0: continue
    name,expected_pocket=legal[item]
    assert pocket==expected_pocket,(item,pocket,expected_pocket)
    assert items.string(p,2) and items.string(p,3) and 0<item<len(names)
    pool.append({'item':item,'name':item_name(item),'category':name,'pocket':pocket,'max_quantity':min(limit,1 if pocket in (6,7) or item in (534,535) else 999)})
pool.sort(key=lambda p:p['item']);assert len(pool)>300 and len({p['item'] for p in pool})==len(pool)
rows=[];previous_points=0
for i,p in enumerate(tables,1):
    fields=b.fields(p);assert b.scalar(fields[0],'I')==i
    if i==1:
        assert len(fields)==1
        continue
    assert len(fields)==4 and all(x is not None for x in fields)
    level,points,item,quantity=[b.scalar(x,'I') for x in fields]
    assert level==i and points>previous_points and 0<item<len(names) and 0<quantity<=999
    previous_points=points
    allowed=progression['reward_choices'].get(str(item))
    locked=item in category('Key') or (allowed is not None and len(allowed)==1)
    row={'level':level,'points':points,'item':item,'quantity':quantity,'name':item_name(item),
         'item_offset':fields[2],'quantity_offset':fields[3],'locked':locked}
    if allowed is not None:row['allowed_items']=allowed
    if item==619:
        row.pop('allowed_items',None);row['rock_route_reward']=True
        row['witness']='Seeded early natural rock-move Pokemon, or a compatible Pokemon paired with the level-2 TM.'
    rows.append(row)
out=ROOT/'port/randomizer/reward-assets';out.mkdir(exist_ok=True)
metadata={'schema':3,'algorithm':'za202-research-rewards-v3','build_id':'b1f12fd919eae86ab8a978317677e64bce443d1f',
          'path':'ik_event/bin/research_lv/research_lv.bin','file':'research-rewards.bin',
          'sha256':expected,'bytes':len(raw),'rows':rows,'pool':pool,'level_1_has_no_reward':True,
          'item_table_sha256':hashlib.sha256(item_raw).hexdigest(),'item_storage_sha256':hashlib.sha256(storage.read_bytes()).hexdigest(),
          'identification':'50 ordered levels. TM names from actual item MachineIndex + 1 and move ID; other names from PKHeX. All later research TMs retained until scripted requirements are solved.'}
(out/'research-rewards.bin').write_bytes(raw)
(out/'research-rewards.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
print(json.dumps({'levels':50,'rewards':len(rows),'randomized':sum(not x['locked'] for x in rows),'pool':len(pool),'bytes':len(raw),'sha256':expected}))

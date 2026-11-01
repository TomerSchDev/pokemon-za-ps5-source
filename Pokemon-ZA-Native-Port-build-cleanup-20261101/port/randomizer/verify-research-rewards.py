"""Independent Python oracle and binary-offset invariant checks for C++ outputs."""
from pathlib import Path
import collections,hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[2]
assets=ROOT/'port/randomizer/reward-assets'
spec=json.loads((assets/'research-rewards.json').read_text());original=(assets/'research-rewards.bin').read_bytes()
out=Path(sys.argv[1]);reports=json.loads((out/'reports.json').read_text())
allowed={p+i for row in spec['rows'] if not row['locked'] for p in [row['item_offset'],row['quantity_offset']] for i in range(4)}
digests=[]
for entry in reports:
    seed=entry['seed'];data=(out/(seed+'.bin')).read_bytes();assert len(data)==len(original)
    assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(original,data)))
    locked_items={r['item'] for r in spec['rows'] if r['locked']}
    pool=[x for x in spec['pool'] if x['item'] not in locked_items];selected=[];changed=0
    for row in spec['rows']:
        item=struct.unpack_from('<I',data,row['item_offset'])[0];qty=struct.unpack_from('<I',data,row['quantity_offset'])[0]
        if row['locked']:
            assert (item,qty)==(row['item'],row['quantity']);continue
        route=entry['report']['rock_route'];required=route['tm_item'] if row.get('rock_route_reward') and route['mode']=='tm' else 0
        eligible=[i for i,p in enumerate(pool) if (p['item']==required if required else p['item']!=row['item']) and ('allowed_items' not in row or p['item'] in row['allowed_items'])];bound=len(eligible)
        for attempt in range(1000):
            msg=json.dumps(['za202-research-rewards-v3',spec['build_id'],seed,row['level'],attempt],separators=(',',':')).encode()
            word=int.from_bytes(hashlib.sha256(msg).digest()[:8],'big')
            if word < (1<<64)-((1<<64)%bound):break
        else:raise AssertionError('Rejection limit')
        target=pool.pop(eligible[word%bound]);assert item==target['item'] and qty==min(row['quantity'],target['max_quantity'])
        assert target['pocket']!=4 and item!=16 and qty>0
        selected.append(item);changed+=1
    assert changed==8 and len(set(selected))==8
    if entry['report']['rock_route']['mode']=='tm':assert struct.unpack_from('<I',data,spec['rows'][0]['item_offset'])[0]==entry['report']['rock_route']['tm_item']
    h=hashlib.sha256(data).hexdigest();assert h==entry['report']['table_sha256']['research_rewards'];digests.append(h)
assert len(set(digests))==len(reports)
result={'seeds':len(reports),'pool':len(spec['pool']),'selected_rewards_per_seed':8,'unique_selected_rewards_per_seed':8,
        'level_2_TM_matches_seeded_rock_route':True,'later_research_tms_preserved':True,
        'fixed_level_50_shiny_charm':True,'xp_levels_and_other_bytes_unchanged':True,'independent_oracle_matches':True,
        'all_outputs_distinct':True,'quantity_caps_and_exclusions_verified':True}
(out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

"""Deterministic proposal generator. Does NOT patch, install or launch a mod.

Plans include unresolved gameplay requirements explicitly. A plan is not a
validated in-game randomizer. All seed inputs are versioned UTF-8 strings.
"""
from pathlib import Path
import argparse,hashlib,hmac,json,unicodedata
ROOT=Path(__file__).resolve().parent
ALGORITHM='za-seed-plan-v1'
BUILD='7222e13ecf6adb3249b5dd5c57fa40b102245fce'
def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')
def pick(seed,domain,identity,pool,exclude=None):
    candidates=sorted((p for p in pool if p!=exclude),key=canonical)
    if not candidates:raise ValueError('No replacement candidates')
    key=hashlib.sha256(canonical([ALGORITHM,BUILD,unicodedata.normalize('NFC',str(seed))])).digest()
    limit=(1<<64)-((1<<64)%len(candidates));counter=0
    while True:
        n=int.from_bytes(hmac.new(key,canonical([domain,identity,counter]),hashlib.sha256).digest()[:8],'big')
        if n<limit:return candidates[n%len(candidates)]
        counter+=1
def plan(seed,root=ROOT):
    inputs={}
    def load(name):
        raw=(root/name).read_bytes();inputs[name]=hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    catalog=load('personal-catalog.json');megas=load('mega-catalog.json')
    pool=[dict(species=p['internal'],form=0) for p in catalog if p['present'] and p['form']==0 and p['internal']]
    mega_pool=[dict(species=m['internal'],form=m['from_form'],mega_form=m['to_form'],item=m['item']) for m in megas if m['present']]
    mi={(m['species'],m['form'],m['item']):m for m in mega_pool}
    trainers=load('decoded/trdata_array.json')['values'];encounters=load('encounters.json')
    event_groups=load('decoded/pokemon_data_array.json')['values']
    source_inventory=load('table-inventory.json')
    items=[]
    for t in trainers:
        found_mega=False
        for slot in range(1,7):
            pk=t[f'poke{slot}'];sp=pk['devId']
            if not sp:continue
            key=(sp,pk['formId'],pk['item']);is_mega=bool(t['megEvolution'] and key in mi);found_mega|=is_mega
            src=mi[key] if is_mega else dict(species=sp,form=pk['formId'])
            domain='trainer-mega' if is_mega else 'trainer'
            dst=pick(seed,domain,[t['trid'],slot],mega_pool if is_mega else pool,src)
            items.append(dict(domain=domain,id=t['trid'],slot=slot,source=src,target=dst,level=pk['level'],
                status='proposal-only',requires=['compatible moves, form and held item','rival/ally progression consistency','in-game battle test']))
        if t['megEvolution'] and not found_mega:
            items.append(dict(domain='trainer-mega-unresolved',id=t['trid'],status='manual-review',reason='Mega flag without a recognized species/form/stone tuple; may be script-driven'))
    for e in encounters:
        src=dict(species=e['internal'],form=e['form']);id=e['id']
        mega=next((m for m in mega_pool if (m['species'],m['mega_form'])==(src['species'],src['form'])),None)
        if e['boss']:
            items.append(dict(domain='rogue-mega',id=id,source=src,status='manual-review',
                reason='Must map a complete linked encounter/boss/arena/AI profile, including followers and story triggers'))
            continue
        dst=pick(seed,'field-mega' if mega else 'field',id,mega_pool if mega else pool,mega if mega else src)
        items.append(dict(domain='field-mega' if mega else 'field',id=id,source=src,target=dst,status='proposal-only',
            referenced_by=len(e['spawners']),requires=['spawn locomotion and assets','scripted species checks and quest items','in-game capture/respawn test']))
    # These records also include decorative NPC Pokemon. No claim that every
    # record is a gift/ally, or that its owning scripts have been mapped.
    for group in event_groups:
        for e in group['root']:
            src=dict(species=e['devNo'],form=e['formNo'])
            items.append(dict(domain='event-npc-review',id=e['id'],source=src,status='manual-review',
                reason='Resolve owning event, gift, partner or decorative NPC before including in shuffle'))
    data=dict(schema=1,algorithm=ALGORITHM,build_id=BUILD,seed=unicodedata.normalize('NFC',str(seed)),applies_changes=False,
        validation='Static candidate plan only; no gameplay validity claim',base_species_pool=len(pool),mega_conversion_pool=len(mega_pool),
        excludes_alternate_non_mega_forms=True,source_input_sha256=inputs,
        source_game_files={r['path']:r['sha256'] for r in source_inventory},items=items)
    data['plan_sha256']=hashlib.sha256(canonical(data)).hexdigest();return data
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    with a.out.open('x',encoding='utf-8') as f:json.dump(plan(a.seed),f,indent=2)
    print(a.out)

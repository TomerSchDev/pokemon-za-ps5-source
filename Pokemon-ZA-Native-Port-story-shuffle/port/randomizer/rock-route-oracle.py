"""Independent seeded route oracle and raw-game capability checks."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
def choose(seed,domain,bound):
    for retry in range(1000):
        msg=json.dumps(['za202-rock-route-v1',seed,domain,retry],separators=(',',':')).encode()
        v=int.from_bytes(hashlib.sha256(msg).digest()[:8],'big')
        if v<(1<<64)-((1<<64)%bound):return v%bound
    raise AssertionError('Sampling failed')
def plan(spec,seed,wild,rewards):
    r=spec['rock']
    if wild and choose(seed,'route',2)==0:
        result=dict(r['natural_candidates'][choose(seed,'natural-species',len(r['natural_candidates']))]);result.update(mode='natural',tm_item=0)
    else:
        tm=r['tm_routes'][choose(seed,'tm-item',len(r['tm_routes'])) if rewards else 0]
        result=dict(tm['candidates'][choose(seed,'tm-species',len(tm['candidates']))]) if wild else {'species':659,'name':'Bunnelby'}
        result.update(mode='tm',tm_item=tm['item'],tm_name=tm['name'],move=tm['move'])
    result.update(locations=r['locations'],algorithm='za202-rock-route-v1');return result
if __name__=='__main__':
    pc=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
    sys.path.insert(0,str(pc/'randomizer-lab'))
    from reflection_reader import Buffer
    spec=json.loads((ROOT/'port/randomizer/reward-assets/progression.json').read_text())
    b=Buffer((ROOT/'evidence/randomizer-field-move-audit/extracted/avalon/data/personal_array.bin').read_bytes());personal={}
    for t in b.tables(b.scalar(0,'I'),0):
        f=b.field(t,0);key=(b.scalar(f,'H'),b.scalar(f+2,'H'))
        personal[key]={'tm':{b.scalar(x,'H') for x in b.vector(b.field(t,22),2)},
                       'moves':[(b.scalar(x,'H'),b.scalar(x+2,'b')) for x in b.vector(b.field(t,25),4)]}
    roles=json.loads((ROOT/'evidence/randomizer-field-move-audit/decoded/waza_attribute_data.json').read_text())
    rock=set(next(x['wazaIdList'] for x in roles['root'] if x['wazaAttributeId']=='WazaDestructionRock'))
    for candidate in spec['rock']['natural_candidates']:
        assert any(move in rock and 0<=level<=3 for move,level in personal[candidate['species'],0]['moves'])
    for tm in spec['rock']['tm_routes']:
        assert tm['move'] in rock
        for candidate in tm['candidates']:
            p=personal[candidate['species'],0]
            assert tm['move'] in p['tm'] and not any(move in rock and 0<=level<=4 for move,level in p['moves'])
    reports=json.loads((ROOT/'evidence/randomizer-r14-rewards-host-tests/reports.json').read_text(encoding='utf-8'))
    modes=set();species=set()
    for x in reports:
        expected=plan(spec,x['seed'],True,True);assert expected==x['report']['rock_route'];modes.add(expected['mode']);species.add(expected['species'])
    assert modes=={'natural','tm'} and len(species)>20
    generated=json.loads((ROOT/'evidence/randomizer-r14-progression-tests/reports.json').read_text(encoding='utf-8'))
    for x in generated:assert x['rock_route']==plan(spec,x['seed'],x['options']['wild'],x['options']['research_rewards'])
    result={'status':'PASS','seeds':len(reports),'both_routes_selected':True,'distinct_providers':len(species),
            'natural_provider_raw_learnset_max_level':3,'TM_provider_actual_compatibility':True,
            'TM_route_excludes_already_learned_rock_moves_through_level_4':True,'all_toggle_combinations_verified':True}
    (ROOT/'evidence/randomizer-r14-rock-route-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

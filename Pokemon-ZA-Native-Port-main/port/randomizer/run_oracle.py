"""Read-only replay of the targeted wild-table postprocessor."""
from pathlib import Path
import hashlib, importlib.util, struct

_spec=importlib.util.spec_from_file_location('rock_oracle',Path(__file__).with_name('rock-route-oracle.py'))
rock=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(rock)

def route_for_run(spec,report):
    opts=report['options']
    route=rock.plan(spec,report['seed'],opts['wild'],opts.get('research_rewards',False))
    migration=report.get('wild_repair',{})
    if route['mode']=='tm' and migration:
        item=migration['retained_first_reward_item'] if opts.get('research_rewards') else 619
        tm=next(t for t in spec['rock']['tm_routes'] if t['item']==item)
        provider=(dict(tm['candidates'][rock.choose(report['seed'],'tm-species',len(tm['candidates']))])
                  if opts['wild'] else {'species':659,'name':'Bunnelby'})
        provider.update(mode='tm',tm_item=tm['item'],tm_name=tm['name'],move=tm['move'],
                        locations=spec['rock']['locations'],algorithm='za202-rock-route-v1')
        route=provider
    return route

def replay_wild(spec,template,generated,report):
    if not report['options']['wild']:return generated
    assert spec['schema']==4 and len(generated)==spec['source_bytes']
    assert hashlib.sha256(template).hexdigest()==spec['wild_template_sha256']
    route=route_for_run(spec,report)
    assert route==report['rock_route'],'Rock route disagrees with independent sampler'
    data=bytearray(template)
    for row in spec['guards']:
        if row['rock_provider']:values=(route['species'],0,0)
        elif row['fixed']:values=(row['species'],row['form'],row['original_sex'])
        else:values=tuple(struct.unpack_from('<i',generated,row['generated_fields'][f]['offset'])[0] for f in ('devNo','formNo','sex'))
        for field,value in zip(('devNo','formNo','sex'),values):struct.pack_into('<i',data,row['fields'][field]['offset'],value)
    return bytes(data)

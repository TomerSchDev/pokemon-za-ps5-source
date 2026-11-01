"""Read-only evidence for this title's active run; compare PS5 tables with host core."""
from pathlib import Path
import argparse, hashlib, json, re, struct, subprocess, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import run_r3 as r
from run_oracle import replay_wild,route_for_run

ROOT=Path(__file__).resolve().parents[2]
REMOTE='/mnt/sandbox/PPSA91762_000/download0/zarecomp/rando'

def digest(data): return hashlib.sha256(data).hexdigest()
def wsl_path(path):
    value=path.resolve().as_posix()
    if not value.startswith('C:/'): raise ValueError('Expected project on C:')
    return '/mnt/c/'+value[3:]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--compare-host',action='store_true')
    p.add_argument('--revision',default='r8')
    a=p.parse_args()
    if not re.fullmatch(r'r[0-9]+',a.revision): raise ValueError('Invalid revision')
    c=r.Console()
    try:
        raw=c.read(REMOTE+'/active.json',4096)
        if raw is None: raise RuntimeError('No active run yet')
        run=json.loads(raw)['id']
        if not re.fullmatch(r'r[0-9a-f]{16}-[0-9a-f]{8}',run): raise ValueError('Unexpected run ID')
        report_raw=c.read(REMOTE+'/'+run+'/report.json',1<<20)
        report=json.loads(report_raw)
        assert report['native_run_id']==run and report['native_complete'] is True
        out=ROOT/'evidence'/('randomizer-run-'+r.stamp())
        out.mkdir()
        (out/'report.json').write_bytes(report_raw)
        receipt={'utc':r.utc_now(),'title':'PPSA91762','run':run,'seed':report['seed'],
                 'starter':report['starter_name'],'tables':[],'host_comparison':None}
        for item in report['native_tables']:
            path=item['path']
            if path.startswith('/') or '..' in path or '\\' in path: raise ValueError('Unsafe report path')
            data=c.read(REMOTE+'/'+run+'/romfs/'+path,32<<20)
            assert data is not None and digest(data)==item['sha256'],path
            if path=='ik_event/bin/research_lv/research_lv.bin':(out/'research-rewards.bin').write_bytes(data)
            receipt['tables'].append({'path':path,'bytes':len(data),'sha256':digest(data)})
        save=c.read(REMOTE+'/'+run+'/save/save_0/main',16<<20)
        assert save
        (out/'main').write_bytes(save)
        receipt['live_save']={'bytes':len(save),'sha256':digest(save),'matches_starting_save':digest(save)==report['save_sha256']}
    finally: c.close()
    if a.compare_host:
        assets=ROOT/'artifacts'/('randomizer-'+a.revision)/'PPSA91762/randomizer-assets'
        host_out=out/'host-core'
        keys=['wild','trainers','mega_trainers','dlc_rematches']
        mask=sum(1<<i for i,k in enumerate(keys) if report['options'][k])
        proc=subprocess.run(['wsl','-d','Ubuntu','--','/home/tomer/za-menu-toolchain/host/za-rando-core',
            wsl_path(assets),report['seed'],str(report['starter']),wsl_path(host_out),str(mask)],
            capture_output=True,text=True,encoding='utf-8',check=True)
        (out/'host-core-output.txt').write_text(proc.stdout+'\n'+proc.stderr,encoding='utf-8')
        host=json.loads((host_out/'report.json').read_text())
        fields=['seed','algorithm','build_id','starter','starter_name','starter_level','counts','save_sha256']
        for key in fields: assert host[key]==report[key],key
        assert all(host['options'][k]==report['options'][k] for k in keys)
        if report.get('progression') and report['options']['wild']:
            guard=json.loads((assets/'progression.json').read_text())
            assert guard['algorithm']==report['progression']['algorithm'],'Use assets from the run generation revision'
            if guard['schema']==4:
                data=replay_wild(guard,(assets/'progression-wild.bin').read_bytes(),(host_out/'wild.bin').read_bytes(),report)
            elif guard['schema']==2:data=bytearray((assets/'progression-wild.bin').read_bytes())
            else:data=bytearray((host_out/'wild.bin').read_bytes())
            for row in ([] if guard['schema']==4 else guard['guards']):
                candidates=[] if row['fixed'] else [x for x in row['pool'] if x!=row['species']]
                species=row['species'];form=row['form']
                if candidates:
                    bound=len(candidates)
                    for attempt in range(1000):
                        message=json.dumps(['za202-field-capabilities-v1',report['seed'],row['identity'],attempt],separators=(',',':')).encode()
                        word=int.from_bytes(hashlib.sha256(message).digest()[:8],'big')
                        if word<(1<<64)-((1<<64)%bound):break
                    else:raise AssertionError('Progression rejection limit')
                    species=candidates[word%bound];form=0
                for field,value in [('devNo',species),('formNo',form),('sex',row['original_sex'] if species==row['species'] else 0)]:
                    struct.pack_into('<i',data,row['fields'][field]['offset'],value)
            host['table_sha256']['wild']=digest(data)
        assert all(report['table_sha256'][k]==v for k,v in host['table_sha256'].items())
        receipt['host_comparison']={'matching_fields':fields,'all_three_tables_and_starting_save_match':True}
        if report.get('rock_route'):
            guard=json.loads((assets/'progression.json').read_text())
            assert report['rock_route']==route_for_run(guard,report)
            receipt['host_comparison']['rock_route_matches_independent_oracle']=True
        if report['options'].get('research_rewards'):
            rewards_assets=assets
            if report.get('wild_repair'):
                prior=report['wild_repair']['original_revision'];assert re.fullmatch(r'r[0-9]+',prior)
                rewards_assets=ROOT/'artifacts'/('randomizer-'+prior)/'PPSA91762/randomizer-assets'
            spec=json.loads((rewards_assets/'research-rewards.json').read_text());expected=bytearray((rewards_assets/'research-rewards.bin').read_bytes());pool=list(spec['pool'])
            algorithm=report['research_rewards']['algorithm']
            assert spec.get('algorithm','za202-research-rewards-v1')==algorithm,'Use assets from the run generation revision'
            if spec['schema']>=2:
                locked={x['item'] for x in spec['rows'] if x['locked']};pool=[x for x in pool if x['item'] not in locked]
            for row in spec['rows']:
                if row['locked']:continue
                forced=report.get('rock_route',{}).get('tm_item',0) if row.get('rock_route_reward') else 0
                eligible=[i for i,p in enumerate(pool) if (p['item']==forced if forced else p['item']!=row['item']) and ('allowed_items' not in row or p['item'] in row['allowed_items'])];bound=len(eligible)
                for attempt in range(1000):
                    message=json.dumps([algorithm,spec['build_id'],report['seed'],row['level'],attempt],separators=(',',':')).encode()
                    word=int.from_bytes(hashlib.sha256(message).digest()[:8],'big')
                    if word<(1<<64)-((1<<64)%bound):break
                else:raise AssertionError('Rejection limit')
                target=pool.pop(eligible[word%bound]);struct.pack_into('<I',expected,row['item_offset'],target['item']);struct.pack_into('<I',expected,row['quantity_offset'],min(row['quantity'],target['max_quantity']))
            assert bytes(expected)==(out/'research-rewards.bin').read_bytes()
            receipt['host_comparison']['research_rewards_match_independent_python_oracle']=True
    (out/'verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2));print('Evidence: '+str(out))

if __name__=='__main__': main()

"""Repair the r11 wild table by publishing a NEW run, retaining the entire old run.

Default is a read-only console snapshot plus a local preview. --stage publishes
an import package for r15 to apply on its next boot while the save mount exists.
Only the active run with the known over-restrictive guard is eligible.
"""
from pathlib import Path,PurePosixPath
import argparse,copy,hashlib,json,re,struct,subprocess,sys,time,secrets
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r
from run_oracle import replay_wild,route_for_run
ROOT=Path(__file__).resolve().parents[2]
REMOTE='/mnt/sandbox/PPSA91762_000/download0/zarecomp/rando'
WILD='world/ik_data/field/pokemon/encount_data/encount_data/encount_data_array.bin'
REWARDS='ik_event/bin/research_lv/research_lv.bin'
def sha(x):return hashlib.sha256(x).hexdigest()
def encode(x):return json.dumps(x,indent=2,ensure_ascii=True).encode()
def wsl(p):return '/mnt/c/'+p.resolve().as_posix()[3:]

def repair(files,guard,template,corewild,reward_spec,new_id):
    old=json.loads(files['report.json'])
    assert old['progression']['algorithm']=='za202-field-capabilities-v1'
    assert old['options']['wild'] and not old.get('wild_repair')
    for row in old['native_tables']:assert sha(files['romfs/'+row['path']])==row['sha256']
    report=copy.deepcopy(old);first=619
    if old['options'].get('research_rewards'):
        row=next(x for x in reward_spec['rows'] if x['level']==2)
        first=struct.unpack_from('<I',files['romfs/'+REWARDS],row['item_offset'])[0]
        assert first in (619,358),'Cannot assume an existing unrelated reward opens the rock gate'
    report['wild_repair']={'original_run':old['native_run_id'],'original_revision':'r11',
        'original_report_sha256':sha(files['report.json']),
        'save_at_repair_sha256':sha(files['save/save_0/main']),
        'retained_first_reward_item':first,'retained_other_tables':True,
        'policy':'Restore ordinary wild randomization; retain save, trainers, DLC and all earned/future rewards'}
    report['rock_route']=route_for_run(guard,report)
    wild=replay_wild(guard,template,corewild,report)
    report['progression']={'algorithm':guard['algorithm'],'tm_catalog_count':guard['tm_count'],
        'scope':'Seeded early rock provider plus authored move sets; other encounters use original randomizer output',
        'limitations':guard['limitations']}
    report['table_sha256']['wild']=sha(wild)
    report['native_run_id']=new_id
    for row in report['native_tables']:
        if row['path']==WILD:row['sha256']=sha(wild)
    fixed=dict(files);fixed['romfs/'+WILD]=wild;fixed['report.json']=encode(report)
    assert all(fixed[k]==v for k,v in files.items() if k not in ('report.json','romfs/'+WILD))
    assert fixed['save/save_0/main']==files['save/save_0/main']
    return fixed,report

def snapshot(c,base,rel='',depth=0):
    assert depth<20
    c.ftp.cwd(base+('/'+rel if rel else ''))
    try:entries=list(c.ftp.mlsd())
    finally:c.ftp.cwd('/')
    result={}
    for name,facts in entries:
        if name in ('.','..'):continue
        assert '/' not in name and '\\' not in name and name not in ('','..')
        p=(rel+'/' if rel else '')+name
        if facts.get('type')=='dir':result.update(snapshot(c,base,p,depth+1))
        else:
            data=c.read(base+'/'+p,32<<20);assert data is not None
            result[p]=data
    assert sum(map(len,result.values()))<128<<20
    return result

def mkdir_new_tree(c,base,files):
    c.ftp.mkd(base) # must be new; do not reuse or replace an existing run
    dirs=set()
    for p in files:
        q=PurePosixPath(p).parent
        while str(q)!='.':dirs.add(str(q));q=q.parent
    for p in sorted(dirs,key=lambda x:(x.count('/'),x)):c.ftp.mkd(base+'/'+p)
    for p,data in files.items():
        c.store(base+'/'+p,data);assert c.sha256(base+'/'+p)==sha(data),p

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');ap.add_argument('--stage',action='store_true');a=ap.parse_args()
    if a.apply:raise SystemExit('Direct FTP repair disabled: the save mount disappears on close. Use --stage with the r15 native importer.')
    c=r.Console()
    try:
        active=c.read(REMOTE+'/active.json',4096);run=json.loads(active)['id']
        assert re.fullmatch(r'r[0-9a-f]{16}-[0-9a-f]{8}',run)
        files=snapshot(c,REMOTE+'/'+run);old=json.loads(files['report.json'])
        assert old['native_run_id']==run
        assert c.read(REMOTE+'/'+run+'/save/save_0/main',32<<20)==files['save/save_0/main'],'Save changed during snapshot'
    finally:c.close()
    dest=ROOT/'evidence'/('randomizer-r14-repair-'+r.stamp());dest.mkdir()
    for p,data in files.items():
        q=dest/'original'/p;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
    (dest/'original-active.json').write_bytes(active)
    assets=ROOT/'artifacts/randomizer-r14/PPSA91762/randomizer-assets'
    guard=json.loads((assets/'progression.json').read_bytes())
    rewards=json.loads((ROOT/'artifacts/randomizer-r11/PPSA91762/randomizer-assets/research-rewards.json').read_bytes())
    keys=['wild','trainers','mega_trainers','dlc_rematches'];mask=sum(1<<i for i,k in enumerate(keys) if old['options'][k])
    core=dest/'host-core'
    p=subprocess.run(['wsl','-d','Ubuntu','--','/home/tomer/za-menu-toolchain/host/za-rando-core',
        wsl(assets),old['seed'],str(old['starter']),wsl(core),str(mask)],capture_output=True,check=True)
    (dest/'host-core-output.txt').write_bytes(p.stdout+p.stderr)
    expected=json.loads((core/'report.json').read_bytes())
    for key in ['seed','starter','starter_name','save_sha256','build_id']:assert expected[key]==old[key]
    for key,value in expected['table_sha256'].items():
        if key!='wild':assert old['table_sha256'][key]==value
    new_id=f'r{int(time.time()):016x}-{secrets.token_hex(4)}'
    fixed,report=repair(files,guard,(assets/'progression-wild.bin').read_bytes(),(core/'wild.bin').read_bytes(),rewards,new_id)
    expected_paths={'report.json','save/save_0/main'}|{'romfs/'+t['path'] for t in old['native_tables']}
    assert set(files)==expected_paths,'Extra run files need preservation support before importing'
    for p,data in fixed.items():
        q=dest/'repaired'/p;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
    receipt={'utc':r.utc_now(),'old_run':run,'new_run':new_id,'seed':old['seed'],
        'save_sha256':sha(files['save/save_0/main']),'save_preserved':True,
        'only_changed_files':['report.json','romfs/'+WILD],'rock_route':report['rock_route'],
        'backup':str(dest/'original'),'applied':False}
    if a.stage:
        c=r.Console()
        try:
            assert c.read(REMOTE+'/active.json',4096)==active,'Active run changed'
            for p,data in files.items():assert c.sha256(REMOTE+'/'+run+'/'+p)==sha(data),'Source changed: '+p
            manifest={'schema':1,'title':'PPSA91762','source_run':run,'target_run':new_id,
                'source_report_sha256':sha(files['report.json']),'source_save_sha256':receipt['save_sha256'],
                'target_report_sha256':sha(fixed['report.json']),'target_wild_sha256':sha(fixed['romfs/'+WILD])}
            payload={'report.json':fixed['report.json'],'wild.bin':fixed['romfs/'+WILD],'manifest.json':encode(manifest)}
            package='/data/homebrew/PPSA91762/run-repair';stage=package+'.new-'+new_id
            mkdir_new_tree(c,stage,payload)
            if 'run-repair' in c.listing('/data/homebrew/PPSA91762'):
                c.ftp.rename(package,package+'.before-'+new_id)
            c.ftp.rename(stage,package)
            for p,data in payload.items():assert c.sha256(package+'/'+p)==sha(data)
            for p,data in files.items():assert c.sha256(REMOTE+'/'+run+'/'+p)==sha(data),'Old run changed unexpectedly'
            receipt.update(staged=True,stage_path=package,native_manifest=manifest,original_run_retained_and_verified=True)
        finally:c.close()
    (dest/'verification.json').write_bytes(encode(receipt));print(json.dumps(receipt,indent=2));print(dest)
if __name__=='__main__':main()

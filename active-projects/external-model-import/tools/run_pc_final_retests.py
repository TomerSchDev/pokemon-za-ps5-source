"""Retest unresolved bodies and ambiguous motion with the complete QA repair set."""
from pathlib import Path
import argparse,collections,json,shutil,subprocess,sys,time
from run_pc_gallery import ROOT,QA,WORK,inspect_run
from run_pc_wide import plan
from collect_pc_model_results import collect

LINUX_QA='/volume1/Software/Pokemon-ZA-All-Models/Workstation-Data-20261030-v1/PS5-13.60/species-lab/import-all-20261030/qa/all-pokemon-20261030-r2'
PWSH=r'C:\Users\Tomer\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'

def queues_done():
    try:
        for revision,numbers in ((1,range(3,8)),(2,(1,2,8,9,10))):
            path=QA/'wide'/('progress-import-r%d.json'%revision)
            done={x['name'] for x in json.loads(path.read_text(encoding='utf-8'))['batches']}
            if not {'pc-wide-import-%03d-r%d'%(n,revision) for n in numbers}<=done:return False
        return True
    except (FileNotFoundError,json.JSONDecodeError):return False

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,default=1);args=parser.parse_args()
    while not queues_done():time.sleep(10)
    overview=collect()
    transparency=json.loads((QA/'transparency-repairs-r1/transparency-repairs.json').read_text(encoding='utf-8'))
    expected=collections.defaultdict(dict)
    for row in transparency['repairs']:
        for key in row['keys']:expected[key]['mods/00-auto-material-fixes/romfs/'+row['relative']]=row['sha256']
    old_materials=set();records={}
    for target in overview['targets']:
        if target['key'] not in expected:continue
        run=target.get('run')
        if not run:old_materials.add(target['key']);continue
        if run not in records:records[run]=json.loads((ROOT/'qa/runs'/run/'run.json').read_text(encoding='utf-8'))
        if any(records[run]['mods'].get(path)!=digest for path,digest in expected[target['key']].items()):old_materials.add(target['key'])
    todo=[t for t in overview['targets'] if not t['body_visible'] or t.get('animation_status')!='motion_detected' or t['key'] in old_materials]
    # Failed imported bodies first; native birds then get a non-aliasing sample.
    todo.sort(key=lambda t:(t['body_visible'],not t['imported'],t['key']))
    canonical={t['key']:t for t in json.loads((QA/'inventory-v4.json').read_text(encoding='utf-8'))['targets']}
    todo=[canonical[t['key']] for t in todo]
    retests=QA/'retests';retests.mkdir(exist_ok=True);resolved=[];sequence=0
    print('Final targeted PC retests: '+str(len(todo))+' identities; outdated transparency profiles: '+str(len(old_materials)),flush=True)
    for start in range(0,len(todo),90):
        remaining=todo[start:start+90];first_mods=None;attempts=set();boot_shift=0;segments=0
        while remaining:
            segments+=1;sequence+=1
            assert segments<=2*len(todo)+5,'No forward progress in targeted retests'
            name='pc-quality-retest-%03d-r%d'%(sequence,args.revision)
            inputs,pairs=plan(len(remaining))
            shots=[(a,a+19,b) for a,b in pairs]
            if boot_shift:
                inputs=[('%d:%s'%(int(x.split(':',1)[0])+boot_shift,x.split(':',1)[1])) if int(x.split(':',1)[0])>=1200 else x for x in inputs]
                shots=[tuple(n+boot_shift for n in triple) for triple in shots]
            spec=retests/(name+'.json');assert not spec.exists()
            spec.write_text(json.dumps({'mode':'box','targets':remaining,'body_frame_pairs':shots,
                                        'include_sibling_asset_folders':True,'motion_sample_offsets':[0,19,37]},indent=1),encoding='utf-8')
            save=retests/name
            fixture=[PWSH,'-NoProfile','-NonInteractive','-File',str(ROOT/'tools/bulkfixture/Run-MultiFixture.ps1'),
                     '-SourceSave',str(ROOT/'qa/saves/multi-six/save_0/main'),'-Manifest',str(spec),'-OutputSave',str(save/'save_0/main')]
            with (retests/(name+'-fixture.json')).open('xb') as out:subprocess.run(fixture,stdout=out,stderr=subprocess.STDOUT,check=True)
            cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),name,
                 '--seconds',str(int(shots[-1][-1]/18)+120),'--stop-after-shots','--watch-models',str(spec),
                 '--save-src',str(save),'--cache-src',str(WORK/'runs/pc-native-baseline-r23/cache'),
                 '--input',','.join(inputs),'--shot-at','900,1250,1650,2000,'+','.join(str(n) for triple in shots for n in triple),
                 '--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
            if first_mods is None:
                bundle='quality-retest-%03d-r%d'%(sequence,args.revision)
                ssh=['ssh','-i',r'C:\Users\Tomer\.ssh\theonepiece_codex_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes',
                     '-o','ConnectTimeout=5','-o','StrictHostKeyChecking=yes','TomerSch@192.168.1.234',
                     'python3',LINUX_QA+'/build_qa_bundle.py',LINUX_QA+'/retests/'+name+'.json',bundle]
                with (retests/(name+'-bundle.log')).open('xb') as out:subprocess.run(ssh,stdout=out,stderr=subprocess.STDOUT,check=True)
                cmd[3:3]=['--bundle',str(QA/'bundles'/bundle)]
            else:cmd[3:3]=['--link-local-mods',str(first_mods)]
            print('Starting '+name+' '+str(len(remaining))+' identities, samples 0/19/37',flush=True)
            with (retests/(name+'-driver.log')).open('xb') as out:subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,check=True)
            report=inspect_run(name,remaining,shots)
            record=json.loads((ROOT/'qa/runs'/name/'run.json').read_text(encoding='utf-8'))
            if first_mods is None:first_mods=WORK/'runs'/name/'mods'
            rows=report['targets'];fault=record.get('loader_stall_watch')
            if fault:
                index=fault['index'];target=remaining[index]
                resolved.extend(rows[:index]);rows[index]['render_status']='loader_stall_retry_pending'
                for row in rows[index+1:]:row['render_status']='deferred_after_loader_failure'
                if target['imported'] and target['key'] not in attempts:
                    from build_simple_render_controls import build
                    candidate=QA/'quality-control-candidates'/('%s-r%d'%(target['key'],args.revision))
                    if not candidate.exists():build([target],candidate)
                    shutil.copytree(candidate/'romfs',first_mods/'00-auto-render-fixes/romfs',dirs_exist_ok=True)
                    attempts.add(target['key']);remaining=remaining[index:]
                else:
                    rows[index]['render_status']='loader_stall_after_complete_asset_repairs'
                    resolved.append(rows[index]);remaining=remaining[index+1:]
            else:
                incomplete=next((i for i,t in enumerate(rows) if t['render_status'] in ('missing_capture','wrong_screen_requires_review')),None)
                if incomplete is None:resolved.extend(rows);remaining=[]
                else:
                    resolved.extend(rows[:incomplete]);remaining=remaining[incomplete:]
                    if incomplete==0:
                        assert boot_shift<2400,'Repeated QA boot/UI failure; models not marked as failures'
                        boot_shift+=1200
            (ROOT/'qa/runs'/name/'gallery-results.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
            state={'revision':args.revision,'requested_keys':[t['key'] for t in todo],'resolved':resolved,
                   'last_run':name,'remaining_current_group':[t['key'] for t in remaining]}
            (retests/('final-retests-r%d-checkpoint.json'%args.revision)).write_text(json.dumps(state,indent=1),encoding='utf-8')
    result={'revision':args.revision,'targets':resolved,'counts':dict(collections.Counter(t['render_status'] for t in resolved)),
            'motion_sample_offsets':[0,19,37],'source_game_unchanged':True,'PC_only':True}
    (retests/('final-retests-r%d-results.json'%args.revision)).write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({'retests_complete':True,'targets':len(resolved),'counts':result['counts']}),flush=True)

if __name__=='__main__':main()

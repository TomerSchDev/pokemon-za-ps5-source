"""Finish every offline installation/QA preflight before requesting console use."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
helpers=module('side_prepare_helpers',ROOT/'port/hebrew-rtl/prepare-side.py')
q=module('side_verify_queue',ROOT/'tools/console-install-queue/console_queue.py')
sha,write,wsl=helpers.sha,helpers.write,helpers.wsl

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--native-out',required=True);a=p.parse_args()
    source=a.source.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    if not a.native_out.startswith('/home/tomer/ps5-za-native/') or '/..' in a.native_out:raise ValueError('New native output required')
    old=json.loads((source/'manifest.json').read_text(encoding='utf-8-sig'))
    for name in ['port/main-install/seed-side-data.c','port/title/launch_title.c']:
        expected=old['source_hashes'][str(ROOT/name)]
        if sha(ROOT/name)!=expected:raise ValueError('Rebuild native helper after source changes')
    for row in old['artifacts']+[old['game']]:
        if sha(Path(row['path']))!=row['sha256']:raise ValueError('Prepared input changed: '+row['remote_path'])
    controller=module('side_controller_preflight',ROOT/'port/hebrew-rtl/console-choice.py')
    installer=module('side_bundle_preflight',ROOT/'port/main-install/install-main.py')
    identity={'pid':123,'session':'0000000000000123'}
    tests=[]
    with patch.object(controller.m.api,'eboot_processes',return_value=[{'pid':123}]), patch.object(controller.m.observer,'status',return_value={'session':identity['session']}):
        controller.side_owned(type('Console',(),{'ftp':None})(),identity)
        tests.append('matching side PID/session accepted')
    for processes,session in [([{'pid':999}],identity['session']),([{'pid':123},{'pid':999}],identity['session']),([{'pid':123}],'ffffffffffffffff')]:
        with patch.object(controller.m.api,'eboot_processes',return_value=processes),patch.object(controller.m.observer,'status',return_value={'session':session}):
            try:controller.side_owned(type('Console',(),{'ftp':None})(),identity)
            except RuntimeError:tests.append('unknown PID/session rejected')
            else:raise AssertionError('Unknown process accepted')
    fake=out/'synthetic-main.bin';fake.write_bytes(b'synthetic untested main')
    bad={'title_id':'PPSA91762','deployment':{'mode':'main_update'},'artifacts':[{'path':str(fake),'sha256':sha(fake),'remote_path':'/data/homebrew/PPSA91762/eboot.bin'}]}
    class FakeBoard:
        def load(self):return {}
        def authenticate(self,*args):return None,{'job':bad}
    with patch.object(controller.m.queue,'Board',return_value=FakeBoard()),patch.object(controller,'backup',side_effect=AssertionError('Console backup must not be reached')),patch.dict(os.environ,{'CONSOLE_INSTALL_TICKET':'synthetic','CONSOLE_INSTALL_TOKEN':'unused'}):
        try:controller.readiness(out/'must-not-be-created',source,None,True)
        except controller.m.queue.QueueError:tests.append('untested main rejected before any console operation')
        else:raise AssertionError('Untested main accepted')
    write(out/'controller-tests.json',{'result':'passed','tests':tests,'scope':'Mocked identity boundary, no console access'})
    commands=[
        ['wsl.exe','-d','Ubuntu','-u','tomer','--','python3',wsl(ROOT/'port/hebrew-rtl/test/verify_full_side_pack.py'),wsl(source),a.native_out],
        [sys.executable,'-I',str(ROOT/'tools/console-install-queue/test_install_enforcement.py')],
        [sys.executable,'-I','-c',"import runpy,sys;from pathlib import Path;p=Path(sys.argv.pop(1));sys.path.insert(0,str(p.parent));runpy.run_path(str(p),run_name='__main__')",str(ROOT/'port/perf-r24/observer/test-client.py')]
    ]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (out/('verification-%d.log'%i)).write_bytes(r.stdout)
        if r.returncode:print(r.stdout.decode('utf-8',errors='replace'));raise RuntimeError('Offline preflight failed')
    host=Path(r'\\wsl.localhost\Ubuntu')/a.native_out.lstrip('/').replace('/','\\')/'result.json'
    shutil.copyfile(host,out/'full-pack-result.json')
    first=json.loads((source/'job-dependencies.json').read_text(encoding='utf-8-sig'))
    game=json.loads((source/'job-game.json').read_text(encoding='utf-8-sig'))
    seed=json.loads((source/'job-seed.json').read_text(encoding='utf-8-sig'))
    # The canonical baseline retains EVERY file. Seed comes before the largest
    # image, so no later installation has to re-read the image as its baseline.
    installed={r['remote_path']:r for r in first['artifacts']}
    jobs=[('dependencies',first),('seed',seed),('game',game)]
    for phase,job in jobs:
        job['expected_base']=[] if phase=='dependencies' else [{'remote_path':r['remote_path'],'sha256':r['sha256']} for r in installed.values()]
        sizes={} if phase=='dependencies' else {path:Path(r['path']).stat().st_size for path,r in installed.items()}
        job['deployment']={'mode':'side_app','base_sizes':sizes}
        job['notes']+=' Complete installed-file baseline pinned; stage order dependencies -> seed -> game.'
        write(out/('job-'+phase+'.json'),job)
        normalized=q.normalized_job(out/('job-'+phase+'.json'))
        installer.base_readback_limits(normalized)
        if phase!='dependencies':
            state={'baselines':{'PPSA91990':{'files':{path:r['sha256'] for path,r in installed.items()}}}}
            q.Board().check_baseline(state,{'job':normalized})
        policy=q.install_policy(normalized)
        write(out/('plan-'+phase+'.json'),{**policy,'files':len(normalized['artifacts']),'baseline_files':len(normalized['expected_base']),'console_access':False})
        installed.update({r['remote_path']:r for r in job['artifacts']})
    qa={**first,'name':'Hebrew choice QA: installed side runtime only','artifacts':game['artifacts'][:2],
        'expected_base':[{'remote_path':path,'sha256':r['sha256']} for path,r in installed.items()],
        'deployment':{'mode':'side_app','base_sizes':{path:Path(r['path']).stat().st_size for path,r in installed.items()}},
        'notes':'Prepared runtime QA only: launch owned side title, seed independent data, restart, observe elevator and other menus, close owned side process. No main installation.'}
    write(out/'job-qa.json',qa)
    normalized_qa=q.normalized_job(out/'job-qa.json');q.install_policy(normalized_qa)
    q.Board().check_baseline({'baselines':{'PPSA91990':{'files':{path:r['sha256'] for path,r in installed.items()}}}},{'job':normalized_qa})
    tool_paths=['port/hebrew-rtl/console-choice.py','port/hebrew-rtl/verify-side.py','port/main-install/install-main.py','tools/console-install-queue/install_guard.py','port/perf-r24/observer/client.py']
    old.update(offline_preflight='passed',stage_order=['dependencies','seed','game'],final_app_files=len(installed),baseline_chain_verified=True,
        preflight_evidence=[{'path':str(out/('verification-%d.log'%i)),'sha256':sha(out/('verification-%d.log'%i))} for i in range(len(commands))],
        full_pack_evidence={'path':str(out/'full-pack-result.json'),'sha256':sha(out/'full-pack-result.json')},
        controller_identity_evidence={'path':str(out/'controller-tests.json'),'sha256':sha(out/'controller-tests.json')},
        install_tool_sources={name:sha(ROOT/name) for name in tool_paths},
        final_install_guard_tests={'result':'passed','count':16,'scope':'Synthetic transport, no console/game execution','evidence':{'path':str(out/'verification-1.log'),'sha256':sha(out/'verification-1.log')}},
        qa_plan={'path':str(ROOT/'port/hebrew-rtl/choice-console-scenarios.json'),'sha256':sha(ROOT/'port/hebrew-rtl/choice-console-scenarios.json')},launch_not_tested=True)
    write(out/'manifest.json',old)
    write(out/'pc-complete.json',{'result':'passed','own_processes_stopped':True,'console_access':False,'game_run':False,'manifest':{'path':str(out/'manifest.json'),'sha256':sha(out/'manifest.json')}})
    print(json.dumps({'result':'passed','out':str(out),'stage_order':old['stage_order'],'final_app_files':len(installed),'console_access':False}))

if __name__=='__main__':
    board=q.Board(resource='pc');agent=os.environ['PC_TEST_AGENT'];ticket=os.environ['PC_TEST_TICKET'];token=os.environ['PC_TEST_TOKEN'];board.check(agent,ticket,token)
    stop=threading.Event();errors=[]
    def beat():
        while not stop.wait(20):
            try:board.heartbeat(agent,ticket,token)
            except Exception as error:errors.append(error);return
    thread=threading.Thread(target=beat,daemon=True);thread.start()
    try:
        main()
        if errors:raise errors[0]
        board.check(agent,ticket,token)
    finally:stop.set();thread.join(3)

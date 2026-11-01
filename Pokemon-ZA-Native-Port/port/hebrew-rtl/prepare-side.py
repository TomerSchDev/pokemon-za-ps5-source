"""Prepare the guarded, isolated Hebrew QA title; no console connection."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
TITLE='PPSA91990'
NATIVE='/home/tomer/ps5-za-native/hebrew-choice-side-tools-20261101-r1'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def wsl(p):return '/mnt/'+str(p.resolve())[0].lower()+str(p.resolve())[2:].replace('\\','/')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--native-out',default=NATIVE);a=ap.parse_args()
    native=a.native_out
    if not native.startswith('/home/tomer/ps5-za-native/') or '/..' in native:
        raise ValueError('Use a new native project output directory')
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    subprocess.run(['wsl.exe','-d','Ubuntu','-u','tomer','--','mkdir',native],check=True)
    tests=[['wsl.exe','-d','Ubuntu','-u','tomer','--','python3',wsl(ROOT/'port/hebrew-rtl/test/test_side_seed.py'),native+'/host-tests'],
           [sys.executable,'-I','-m','unittest','discover','-s',str(ROOT/'tools/console-install-queue'),'-p','test_install_enforcement.py'],
           [sys.executable,'-I','-c',"import runpy,sys;from pathlib import Path;p=Path(sys.argv.pop(1));sys.path.insert(0,str(p.parent));runpy.run_path(str(p),run_name='__main__')",str(ROOT/'port/perf-r24/observer/test-client.py')]]
    for i,cmd in enumerate(tests):
        r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        (out/('tests-%d.log'%i)).write_bytes(r.stdout)
        if r.returncode:
            print(r.stdout.decode('utf-8',errors='replace'));raise RuntimeError('Offline regression failed; no bundle prepared')
    deps=ROOT/'evidence/hebrew-choice-console-20261101-dependencies-r1'
    saved=ROOT/'evidence/hebrew-choice-console-20261101-backup-r1'
    dep=json.loads((deps/'dependencies.json').read_text(encoding='utf-8'))
    for r in dep['files']:
        if sha(Path(r['path']))!=r['sha256']:raise ValueError('Dependency changed: '+r['relative'])
    backup=json.loads((saved/'save-backup-manifest.json').read_text(encoding='utf-8'))
    if not backup['all_runs'] or not backup['double_read_verified']:raise ValueError('Unverified save source')
    active=json.loads((saved/'save-backup/active.json').read_text(encoding='utf-8'))['id']
    seed={}
    for r in backup['files']:
        rel=r['relative']
        if rel=='active.json' or rel.startswith(active+'/'):
            p=Path(r['path'])
            if sha(p)!=r['sha256']:raise ValueError('Save source changed')
            seed['rando/'+rel]=p
    pkg=ROOT/'artifacts/randomizer-r29-hebrew-rtl-20261031-r4'
    meta=json.loads((pkg/'PACKAGE.json').read_text(encoding='utf-8'))
    for r in meta['mods']:
        p=pkg/'mods'/r['path']
        if sha(p)!=r['sha256']:raise ValueError('Hebrew source changed')
        seed['mods/0-hebrew/'+r['path'].split('/',1)[1]]=p
    with (out/'init-data.bin').open('xb') as f:
        f.write(b'ZASIDE01'+struct.pack('<I',len(seed)))
        for rel,p in sorted(seed.items()):
            name=rel.encode('ascii');f.write(struct.pack('<HQ',len(name),p.stat().st_size)+name)
            with p.open('rb') as src:shutil.copyfileobj(src,f,1<<20)
    param=json.loads((deps/'app/sce_sys/param.json').read_text(encoding='utf-8'))
    param.update(titleId=TITLE,conceptId='91990',contentId='UP9000-PPSA91990_00-ZAHEBREWCHOICE01')
    param['localizedParameters']['en-US']['titleName']='Z-A Hebrew Choice QA'
    write(out/'sce_sys/param.json',param)
    sdk='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk'
    commands=[]
    for name,source,defines in [
        ('seed-side-data.elf',ROOT/'port/main-install/seed-side-data.c',[]),
        ('launch-side.elf',ROOT/'port/title/launch_title.c',['-DZA_LAUNCH_ID="PPSA91990"','-DZA_LAUNCH_LOG="/data/za-hebrew-choice-91990-launch.log"','-lSceSystemService','-lSceUserService'])]:
        cmd=['wsl.exe','-d','Ubuntu','-u','tomer','--',sdk+'/bin/prospero-clang','-O2','-Wall',*defines,wsl(source),'-o',native+'/'+name]
        subprocess.run(cmd,check=True);commands.append(cmd)
        shutil.copyfile(Path(r'\\wsl.localhost\Ubuntu')/native.lstrip('/').replace('/','\\')/name,out/name)
    candidate=ROOT/'artifacts/hebrew-choice-overflow-20261031-r1/eboot-choice-fix-UNINSTALLED.bin'
    if sha(candidate)!='e08234a36bc0401fc17a5cac9b13267791ce0c8b615a52f98e6cf457b364401d':raise ValueError('Candidate changed')
    sources={'eboot.bin':candidate,'sce_sys/param.json':out/'sce_sys/param.json','init-data.bin':out/'init-data.bin','seed-side-data.elf':out/'seed-side-data.elf','launch-side.elf':out/'launch-side.elf'}
    sources.update({r['relative']:Path(r['path']) for r in dep['files'] if r['relative']!='sce_sys/param.json'})
    game=ROOT/'deliverables/ZA-Native-Title-r1-20261027/PPSA91761/game'
    sources.update({'game/'+p.relative_to(game).as_posix():p for p in game.rglob('*') if p.is_file() and p.name!='romfs.bin'})
    def row(rel,p):return {'path':str(p),'sha256':sha(p),'remote_path':'/data/homebrew/'+TITLE+'/'+rel}
    artifacts=[row(rel,p) for rel,p in sorted(sources.items())]
    job={'console':'192.168.1.135','title_id':TITLE,'name':'Hebrew choice QA isolated side title: dependencies (game image and seed pending)','deployment':{'mode':'side_app'},'artifacts':[r for r in artifacts if r['remote_path']!='/data/homebrew/'+TITLE+'/init-data.bin'],'expected_base':[],
         'notes':'Preparation stage only, not launchable until the separately verified game image is installed. Distinct title, no shared writable paths. Seed pack contains copied active run and Hebrew mods; initializer refuses different existing files and confines writes to this side sandbox. Main/vanilla untouched.'}
    write(out/'job-dependencies.json',job)
    phase2=[row('eboot.bin',candidate),row('sce_sys/param.json',out/'sce_sys/param.json'),row('game/romfs.bin',game/'romfs.bin')]
    write(out/'job-game.json',{**job,'name':'Hebrew choice QA isolated side title: complete game image','artifacts':phase2,'expected_base':[{'remote_path':r['remote_path'],'sha256':r['sha256']} for r in phase2[:2]],'notes':'Finish the existing isolated side installation; all dependency-stage files preserved. Exact main candidate binary; copied, independent mods/config/save. Never writes main or vanilla.'})
    phase3=phase2[:2]+[row('init-data.bin',out/'init-data.bin')]
    write(out/'job-seed.json',{**job,'name':'Hebrew choice QA isolated side title: copied independent mods and save','artifacts':phase3,'expected_base':[{'remote_path':r['remote_path'],'sha256':r['sha256']} for r in phase3[:2]],'notes':'Complete the independent seed pack after dependencies and game image. Initializer confines all writes to this side sandbox and refuses differing existing files. Main/vanilla saves never restored or modified.'})
    write(out/'manifest.json',{'title':TITLE,'candidate_eboot_sha256':sha(candidate),'entry_main_sha256':dep['main_eboot_sha256'],'side_title_observed_free_at':str(ROOT/'evidence/hebrew-choice-console-20261101-inspect-r1/inspection.json'),'recheck_collision_required':True,'active_run_copy':active,'seed_files':[{'relative':r,'sha256':sha(p)} for r,p in sorted(seed.items())],'artifacts':artifacts,'game':phase2[-1],'commands':commands,'source_hashes':{str(p):sha(p) for p in [Path(__file__),ROOT/'port/main-install/seed-side-data.c',ROOT/'port/title/launch_title.c']},'offline_tests':[{'command':cmd,'result':'passed','evidence':{'path':str(out/('tests-%d.log'%i)),'sha256':sha(out/('tests-%d.log'%i))}} for i,cmd in enumerate(tests)],'candidate_pc_regression_evidence':str(ROOT/'evidence/hebrew-choice-overflow-20261031-r1/pc-validation.json'),'launch_not_tested':True})
    print(json.dumps({'out':str(out),'files':len(artifacts),'seed_files':len(seed),'console_access':False}))

def native_update():
    ap=argparse.ArgumentParser();ap.add_argument('--native-only',action='store_true');ap.add_argument('--out',type=Path,required=True);ap.add_argument('--native-out',required=True);a=ap.parse_args()
    if not a.native_out.startswith('/home/tomer/ps5-za-native/') or '/..' in a.native_out:raise ValueError('New native output required')
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    subprocess.run(['wsl.exe','-d','Ubuntu','-u','tomer','--','mkdir',a.native_out],check=True)
    test=['wsl.exe','-d','Ubuntu','-u','tomer','--','python3',wsl(ROOT/'port/hebrew-rtl/test/test_side_seed.py'),a.native_out+'/host-tests']
    r=subprocess.run(test,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30);(out/'host-tests.log').write_bytes(r.stdout)
    if r.returncode:print(r.stdout.decode('utf-8',errors='replace'));raise RuntimeError('Native helper safety tests failed')
    sdk='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk'
    source=ROOT/'port/main-install/seed-side-data.c'
    command=['wsl.exe','-d','Ubuntu','-u','tomer','--',sdk+'/bin/prospero-clang','-O2','-Wall',wsl(source),'-o',a.native_out+'/seed-side-data.elf']
    r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30);(out/'build.log').write_bytes(r.stdout)
    if r.returncode:print(r.stdout.decode('utf-8',errors='replace'));raise RuntimeError('Native helper compilation failed')
    shutil.copyfile(Path(r'\\wsl.localhost\Ubuntu')/a.native_out.lstrip('/').replace('/','\\')/'seed-side-data.elf',out/'seed-side-data.elf')
    write(out/'native-manifest.json',{'source':{'path':str(source),'sha256':sha(source)},'payload':{'path':str(out/'seed-side-data.elf'),'sha256':sha(out/'seed-side-data.elf')},'test_log':{'path':str(out/'host-tests.log'),'sha256':sha(out/'host-tests.log')},'command':command,'scope':'Small pre-queue native helper preparation and synthetic host checks; no game/console access'})
    print(json.dumps({'out':str(out),'native_helper_sha256':sha(out/'seed-side-data.elf'),'console_access':False}))

def prepare_cleanup():
    ap=argparse.ArgumentParser();ap.add_argument('--cleanup-only',action='store_true');ap.add_argument('--out',type=Path,required=True);ap.add_argument('--native-out',required=True);ap.add_argument('--dynamic-identity',action='store_true');ap.add_argument('--app-id',type=lambda s:int(s,0));ap.add_argument('--pid',type=int);a=ap.parse_args()
    if not a.dynamic_identity and (a.app_id is None or not 0<a.app_id<0x80000000):raise ValueError('Explicit successful owned launch app ID required')
    if not a.dynamic_identity and (a.pid is None or a.pid<=1):raise ValueError('Explicit owned failed PID required')
    if not a.native_out.startswith('/home/tomer/ps5-za-native/') or '/..' in a.native_out:raise ValueError('New native output required')
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    subprocess.run(['wsl.exe','-d','Ubuntu','-u','tomer','--','mkdir',a.native_out],check=True)
    sdk='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk'
    source=ROOT/'port/title/close_failed_side.c'
    defines=[] if a.dynamic_identity else ['-DZA_EXPECTED_APP_ID='+str(a.app_id),'-DZA_EXPECTED_PID='+str(a.pid)]
    command=['wsl.exe','-d','Ubuntu','-u','tomer','--',sdk+'/bin/prospero-clang','-O2','-Wall','-Werror',*defines,wsl(source),'-lSceSystemService','-o',a.native_out+'/close-failed-side.elf']
    r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30);(out/'build.log').write_bytes(r.stdout)
    if r.returncode:raise RuntimeError('Cleanup compilation failed; inspect build.log')
    shutil.copyfile(Path(r'\\wsl.localhost\Ubuntu')/a.native_out.lstrip('/').replace('/','\\')/'close-failed-side.elf',out/'close-failed-side.elf')
    write(out/'cleanup-manifest.json',{'title':'PPSA91990','dynamic_identity':a.dynamic_identity,'app_id':a.app_id,'pid':a.pid,'source':{'path':str(source),'sha256':sha(source)},'payload':{'path':str(out/'close-failed-side.elf'),'sha256':sha(out/'close-failed-side.elf')},'command':command,'scope':'Only close the exact failed side app after PID, mount and crash-log validation; no installation/file writes'})
    print(json.dumps({'cleanup_prepared':str(out),'console_access':False}))

if __name__=='__main__' and '--cleanup-only' in sys.argv:
    prepare_cleanup()
elif __name__=='__main__' and '--native-only' in sys.argv:
    native_update()
elif __name__=='__main__':
    spec=importlib.util.spec_from_file_location('side_pc_queue',ROOT/'tools/console-install-queue/console_queue.py')
    q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
    board=q.Board(resource='pc');agent=os.environ['PC_TEST_AGENT'];ticket=os.environ['PC_TEST_TICKET'];token=os.environ['PC_TEST_TOKEN']
    board.check(agent,ticket,token)
    stop=threading.Event();errors=[]
    def beat():
        while not stop.wait(20):
            try:board.heartbeat(agent,ticket,token)
            except Exception as exc:errors.append(exc);return
    thread=threading.Thread(target=beat,daemon=True);thread.start()
    try:
        main()
        if errors:raise errors[0]
        board.check(agent,ticket,token)
    finally:
        stop.set();thread.join(3)

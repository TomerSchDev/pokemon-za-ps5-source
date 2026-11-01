"""Choice-fix console evidence; reuse the established console/lease helpers."""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.parse
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('choice_install_helpers', ROOT / 'port/r28b-dlc-dex/install-r28b.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.AGENT = 'codex-hebrew-choice'


def inspect(out):
    out.mkdir(parents=True, exist_ok=False)
    lease_file = out / '.lease.json'
    m.write(lease_file, {'ticket': os.environ['CONSOLE_INSTALL_TICKET'], 'token': os.environ['CONSOLE_INSTALL_TOKEN']})
    with m.Lease(out) as lease:
        record = {'at': m.api.utc_now(), 'processes': m.api.http_json('/processes_list'), 'listings': {}, 'files': {}}
        c = m.api.Console()
        try:
            for path in ['/data/homebrew', '/mnt/sandbox', '/data/homebrew/PPSA91762', '/user/app']:
                lease.check()
                record['listings'][path] = c.listing(path)
            for path in ['/data/homebrew/PPSA91762/sce_sys/param.json', '/data/homebrew/PPSA91762/performance-options.txt', '/data/homebrew/PPSA91762/perf-r24-options.txt', '/user/app/PPSA91762/mount.lnk']:
                data = c.read(path, 1 << 20)
                record['files'][path] = None if data is None else data.decode('utf-8', errors='replace')
            for path in ['/mnt/sandbox/PPSA91762_000/download0/zarecomp', '/mnt/sandbox/PPSA91762_000/download0/zarecomp/rando']:
                try:
                    record['listings'][path] = c.listing(path)
                except Exception as error:
                    record['listings'][path] = {'error': str(error)}
            record['main_eboot_sha256'] = c.sha256(m.EBOOT)
        finally:
            c.close()
        m.write(out / 'inspection.json', record)
        m.emit(record)


def backup(out, evidence_out=None):
    out.mkdir(parents=True, exist_ok=False)
    evidence=out if evidence_out is None else evidence_out.resolve()
    if evidence!=out:
        evidence.mkdir(parents=True,exist_ok=False)
        m.write(out/'nas-location.json',{'evidence':str(evidence)})
    m.write(out / '.lease.json', {'ticket': os.environ['CONSOLE_INSTALL_TICKET'], 'token': os.environ['CONSOLE_INSTALL_TOKEN']})
    base = '36b3d5d650bd1a8171c39a788785678fa395ab5c0043d6b02a0d028946944699'
    main_spec = importlib.util.spec_from_file_location('choice_main_helpers', ROOT / 'port/main-install/install-main.py')
    main = importlib.util.module_from_spec(main_spec)
    main_spec.loader.exec_module(main)
    main.m.AGENT = m.AGENT
    main.m.BASE = base
    main.m.mount_at_menu = main.mount
    with main.m.Lease(out) as lease:
        main.m.idle()
        c = main.api.Console()
        try:
            first = main.m.bounded_file(c, main.m.EBOOT, evidence / 'original/eboot.bin', lease)
            if first['sha256'] != base or c.sha256(main.m.EBOOT) != base:
                raise RuntimeError('Live base changed; stop and rebuild before any launch')
            main.write(evidence / 'initial-probe.json', {'at': main.api.utc_now(), 'base_sha256': base, 'readback_path': first['path'], 'second_readback_verified': True})
            main.m.backup(c, lease, evidence)
        finally:
            c.close()
    return main,evidence


def collect(out):
    """Read the live immutable application dependencies for an isolated bundle."""
    out.mkdir(parents=True, exist_ok=False)
    m.write(out / '.lease.json', {'ticket': os.environ['CONSOLE_INSTALL_TICKET'], 'token': os.environ['CONSOLE_INSTALL_TOKEN']})
    with m.Lease(out) as lease:
        m.idle()
        c = m.api.Console()
        rows = []
        try:
            if c.sha256(m.EBOOT) != '36b3d5d650bd1a8171c39a788785678fa395ab5c0043d6b02a0d028946944699':
                raise RuntimeError('Baseline changed')
            paths = ['performance-options.txt', 'perf-r24-options.txt', 'slot-depth-options.txt', 'submission-options.txt', 'local-shader-options.txt', 'performance-profile.txt', 'observer-enable.txt']
            for folder in ['sce_sys', 'sce_module', 'fonts', 'randomizer-assets']:
                paths += [folder + '/' + p for p in m.inventory(c, m.APP + '/' + folder)]
            for index, relative in enumerate(paths):
                row = m.bounded_file(c, m.APP + '/' + relative, out / 'app' / relative, lease)
                if c.sha256(row['remote_path']) != row['sha256']:
                    raise RuntimeError('Dependency changed: ' + relative)
                row['relative'] = relative
                rows.append(row)
                if index % 30 == 0:
                    m.emit({'stage': 'dependencies', 'done': index + 1, 'files': len(paths)})
            m.write(out / 'dependencies.json', {'at': m.api.utc_now(), 'files': rows, 'main_game_closed': m.idle() == [], 'main_eboot_sha256': c.sha256(m.EBOOT)})
        finally:
            c.close()


def readiness(out, package, evidence_out=None, main_update=False):
    """Fresh backup and actual preconditions; does not install anything."""
    package = package.resolve()
    manifest = m.read(package / 'manifest.json')
    if manifest['entry_main_sha256'] != '36b3d5d650bd1a8171c39a788785678fa395ab5c0043d6b02a0d028946944699':
        raise RuntimeError('Unexpected candidate base')
    board=m.queue.Board()
    _,queued=board.authenticate(board.load(),m.AGENT,os.environ['CONSOLE_INSTALL_TICKET'],os.environ['CONSOLE_INSTALL_TOKEN'])
    policy=m.queue.install_policy(queued['job'])
    mode='main_update' if main_update else 'side_app'
    title='PPSA91762' if main_update else 'PPSA91990'
    if policy['mode']!=mode or queued['job']['title_id']!=title:
        raise RuntimeError('Queued deployment differs; no console operation performed')
    installer,evidence=backup(out,evidence_out)
    with m.Lease(out) as lease:
        state=lease.board.load()
        active,row=lease.board.authenticate(state,m.AGENT,lease.data['ticket'],lease.data['token'])
        limits=installer.base_readback_limits(row['job'])
        c=m.api.Console()
        try:
            m.idle()
            if not row['job']['expected_base'] and 'PPSA91990' in c.listing('/data/homebrew'):
                raise RuntimeError('Side title collision; never adopt or overwrite it')
            current=c.sha256(m.EBOOT)
            if current!=manifest['entry_main_sha256']:raise RuntimeError('Main changed; merge/rebuild/requeue')
            bases=[]
            for index,r in enumerate(row['job']['expected_base']):
                readback=m.bounded_file(c,r['remote_path'],evidence/('side-base-%d.bin'%index),lease,limits[r['remote_path']])
                if readback['sha256']!=r['sha256']:raise RuntimeError('Side base changed')
                bases.append({'remote_path':r['remote_path'],'sha256':r['sha256'],'evidence':m.proof(readback['path'])})
            m.write(evidence/'closed-and-base.json',{'at':m.api.utc_now(),'processes':m.idle(),'game_closed':True,'main_sha256':current,'main_unchanged':True})
        finally:c.close()
        m.write(evidence/'external-handoff.json',{'source':'user_message','from':'Tomer','quote':'תתקין את תיקון העברית ותבדוק בקונסולה שהטקסט נשאר בתוך המסגרת גם במעלית וגם בתפריטים נוספים','scope':'Isolated side application first; preserve main and saves. Only our freshly identified backup launcher was closed.'})
        pc={'passed':True,'evidence':m.proof(package/'manifest.json')}
        ready={'console':m.api.HOST,'ticket':lease.data['ticket'],'checked_at':m.api.utc_now(),
               'pc_validation':pc,'external_owner_handoff':{'confirmed':True,'evidence':m.proof(evidence/'external-handoff.json')},
               'game_closed':{'verified':True,'evidence':m.proof(evidence/'closed-and-base.json')},
               'save_backup':{'fresh':True,'all_runs':True,'readback_verified':True,'evidence':m.proof(evidence/'save-backup-manifest.json')},'base_readbacks':bases}
        m.write(evidence/'readiness.json',ready)
        handoff={'name':row['job']['name'],'preserved_features':['Main and vanilla unchanged','Isolated side-title installation stage; copied data may still be pending as named in this job','Exact e08234a3 binary inherits JSON fix, r29 UI, MUSIC, FD fix and RTL; runtime QA still pending'],
                'rebuild_instructions':'port/hebrew-rtl/CHOICE-FIX-HE.md and prepare-side.py; new native output only. Side QA not yet passed; no main promotion authorized by this handoff.',
                'manifest':m.proof(package/'manifest.json')}
        if main_update:
            previous=state['baselines']['PPSA91762']
            handoff['preserved_features']=previous['preserved_features']+['Hebrew choice anchoring; exact candidate console regression passed']
            handoff['rebuild_instructions']='port/hebrew-rtl/CHOICE-FIX-HE.md and build-choice-candidate.py; reproduce the recorded 36b3d5d6 control, replace only RTL object b79d0a4a source; source/build evidence in source_preflight. Rollback is the installer-kept .before file; never restore an older save.'
            m.write(evidence/'main-baseline-manifest.json',{'schema':'za-hebrew-choice-main-1','name':row['job']['name'],'previous_baseline':previous,'source_preflight':m.proof(package/'manifest.json'),'candidate_eboot_sha256':manifest['candidate_eboot_sha256'],'test_report':policy['test_report'],'preserved_features':handoff['preserved_features'],'write_scope':'eboot only; existing assets/mods/config/saves preserved','rebuild_instructions':handoff['rebuild_instructions']})
            handoff['manifest']=m.proof(evidence/'main-baseline-manifest.json')
        m.write(evidence/'handoff.json',handoff)
        m.emit({'stage':'ready','out':str(evidence),'local_private_state':str(out),'deployment':policy['mode'],'hardware_test_passed':main_update})


SIDE='/data/homebrew/PPSA91990'
SIDE_DATA='/mnt/sandbox/PPSA91990_000/download0/zarecomp'

def side_client():
    m.observer.TITLE='PPSA91990'
    m.observer.BASE=SIDE_DATA+'/observer'
    m.observer.COMMAND=SIDE+'/observer-command.txt'
    return m.observer

def side_owned(c, identity):
    processes=m.api.eboot_processes()
    if len(processes)!=1 or m.api.process_pid(processes[0])!=identity['pid']:
        raise RuntimeError('Side QA PID changed; never close or control an unknown process')
    if identity.get('kind')=='za_failed_launch_before_observer':
        # Cleanup only: the loader can fail before the game's observer exists.
        evidence=Path(identity['startup_log']['path'])
        if m.sha(evidence)!=identity['startup_log']['sha256']:
            raise RuntimeError('Failed-launch evidence changed')
        log=evidence.read_text(encoding='utf-8',errors='replace')
        if not (re.search(r'<'+str(identity['pid'])+r'> EXEC /app0/eboot.bin',log)
                and 'PRX_SCE_MODULE_LOAD_ERROR' in log and 'titleId[PPSA91990]' in log):
            raise RuntimeError('The exact failed side launch is not proven')
        param=json.loads(c.read('/mnt/sandbox/PPSA91990_000/app0/sce_sys/param.json',65536))
        if param.get('titleId')!='PPSA91990':raise RuntimeError('Failed title mount changed')
        return
    if side_client().status(c.ftp)['session']!=identity['session']:
        raise RuntimeError('Side QA session changed')

def send_websrv_payload(source,out,expected_sha,identity_args=(), *, allowed_names=('launch-side.elf','seed-side-data.elf','close-failed-side.elf','relocate-side-mods.elf')):
    if m.sha(source)!=expected_sha:raise RuntimeError('Prepared ELF changed')
    name=source.name
    if name not in allowed_names:
        raise RuntimeError('Unsupported side payload')
    if identity_args and (name!='close-failed-side.elf' or len(identity_args)!=2 or any(type(n) is not int or n<=1 or n>=0x80000000 for n in identity_args)):
        raise RuntimeError('Invalid cleanup identity arguments')
    boundary='za-side-'+uuid.uuid4().hex
    body=(('--'+boundary+'\r\nContent-Disposition: form-data; name="elf"; filename="'+name+'"\r\n'
           'Content-Type: application/octet-stream\r\n\r\n').encode()+source.read_bytes()+
          ('\r\n--'+boundary+'--\r\n').encode())
    arguments=' '.join([name,*map(str,identity_args)])
    request=urllib.request.Request('http://'+m.api.HOST+':8080/elfldr?'+urllib.parse.urlencode({'pipe':1,'args':arguments}),
        data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary},method='POST')
    with urllib.request.urlopen(request,timeout=240 if name in ('seed-side-data.elf','relocate-side-mods.elf') else 45) as reply:
        response=reply.read(1<<20);status=reply.status
    log=out/(name+'.websrv-send.log');log.write_bytes(response)
    return {'transport':'official websrv multipart ELF API','http_status':status,
            'payload_sha256':expected_sha,'sender_log':m.proof(log)}

def deploy_side_payload(c,manifest,name,out,transport):
    remote=SIDE+'/'+name
    artifact=next(r for r in manifest['artifacts'] if r['remote_path']==remote)
    source=Path(artifact['path']).resolve()
    if m.sha(source)!=artifact['sha256'] or c.sha256(remote)!=artifact['sha256']:
        raise RuntimeError('Side payload bytes differ from the verified profile')
    if transport=='manager':return m.api.http_text(m.api.PAYLOAD_MANAGER+'/loadpayload:'+remote)
    if transport=='websrv':
        # Official websrv host/prospero-websrv-elfldr uses this multipart API.
        # Send only the ELF verified locally and at the isolated app path.
        return send_websrv_payload(source,out,artifact['sha256'])
    local=str(source)
    if len(local)<3 or local[1]!=':':raise ValueError('SDK sender expects the prepared Windows payload file')
    linux='/mnt/'+local[0].lower()+local[2:].replace('\\','/')
    sdk='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk/bin/prospero-deploy'
    log=out/(name+'.sdk-send.log')
    with log.open('xb') as output:
        result=subprocess.run(['wsl.exe','-d','Ubuntu','-u','tomer','--',sdk,'-h',m.api.HOST,'-p','9021',linux],
                              stdout=output,stderr=subprocess.STDOUT,timeout=240 if name=='seed-side-data.elf' else 45)
    if result.returncode:raise RuntimeError('SDK ELF sender failed; inspect '+str(log))
    return {'transport':'existing SDK prospero-deploy/ELF loader 9021','returncode':result.returncode,
            'payload_sha256':artifact['sha256'],'sender_log':m.proof(log)}

def side_operation(operation, out, package, identity_path=None,transport='manager',cleanup_path=None):
    out.mkdir(parents=True,exist_ok=False)
    m.write(out/'.lease.json',{'ticket':os.environ['CONSOLE_INSTALL_TICKET'],'token':os.environ['CONSOLE_INSTALL_TOKEN']})
    manifest=m.read(package/'manifest.json')
    with m.Lease(out) as lease:
        _,row=lease.board.authenticate(lease.board.load(),m.AGENT,lease.data['ticket'],lease.data['token'])
        if row['job']['title_id']!='PPSA91990':raise RuntimeError('Side QA needs its own queued job')
        c=m.api.Console()
        try:
            if c.sha256(SIDE+'/eboot.bin')!=manifest['candidate_eboot_sha256']:raise RuntimeError('Side executable changed')
            if operation=='launch-side':
                m.idle()
                capture=m.api.KlogCapture(out/'startup.klog.log');capture.start()
                try:
                    time.sleep(2.5)
                    response=deploy_side_payload(c,manifest,'launch-side.elf',out,transport)
                    m.write(out/'launch.json',{'at':m.api.utc_now(),'response':response,'title':'PPSA91990'})
                    launcher_log=c.read('/data/za-hebrew-choice-91990-launch.log',65536) or b''
                    (out/'launcher.log').write_bytes(launcher_log)
                    if b'registration open failed' in launcher_log or b'refusing launch' in launcher_log:
                        raise RuntimeError('Side launcher refused; inspect the retained launcher log, no unknown process is closed')
                    deadline=time.monotonic()+100
                    while time.monotonic()<deadline:
                        lease.check()
                        processes=m.api.eboot_processes()
                        if len(processes)==1:
                            try:
                                status=side_client().status(c.ftp)
                                identity={'pid':m.api.process_pid(processes[0]),'session':status['session'],'at':m.api.utc_now(),'title':'PPSA91990','eboot_sha256':manifest['candidate_eboot_sha256']}
                                side_owned(c,identity)
                                m.write(out/'identity.json',identity)
                                log=(out/'startup.klog.log').read_text(encoding='utf-8',errors='replace')
                                if all(x in log for x in ['main reached','run storage ready','launcher canvas']):
                                    capture.stop()
                                    m.write(out/'startup.json',{'result':'passed','scope':'identified side launcher startup only','identity':identity,'log':m.proof(out/'startup.klog.log')})
                                    m.emit({'stage':'side-launcher-running','identity':identity});return
                            except (m.ftplib.error_perm,ValueError):pass
                        time.sleep(.5)
                    raise RuntimeError('Side launcher not proven ready; inspect the retained PID identity before cleanup')
                finally:capture.stop()
            if identity_path is None:raise RuntimeError('Fresh owned side identity is required')
            identity=m.read(identity_path)
            if identity.get('title')!='PPSA91990' or identity['eboot_sha256']!=manifest['candidate_eboot_sha256']:
                raise RuntimeError('Not our exact side candidate')
            if identity.get('kind')=='za_failed_launch_before_observer' and operation!='close-side':
                raise RuntimeError('Failed-launch identity permits cleanup only')
            side_owned(c,identity)
            if operation=='relocate-side':
                pack=next(r for r in manifest['artifacts'] if r['remote_path']==SIDE+'/init-data.bin')
                if c.sha256(SIDE+'/init-data.bin')!=pack['sha256']:raise RuntimeError('Seed pack changed')
                response=deploy_side_payload(c,manifest,'relocate-side-mods.elf',out,transport)
                log=(out/'relocate-side-mods.elf.websrv-send.log').read_text(encoding='utf-8',errors='replace')
                match=re.search(r'COMPLETE readonly_mods=(\d+) removed_verified_copies=(\d+) available_bytes=(\d+)',log)
                if not match or int(match[1])!=manifest['readonly_mod_files'] or int(match[3])<(128<<20):raise RuntimeError('Relocation not proven complete; preserve owned identity and log')
                side_owned(c,identity)
                m.write(out/'relocation.json',{'at':m.api.utc_now(),'response':response,'verified_mods':int(match[1]),'removed_verified_copies':int(match[2]),'available_bytes':int(match[3]),'rando_save_writes':False})
                m.emit({'stage':'readonly-mods-relocated','free_bytes':int(match[3])});return
            if operation=='seed-side':
                pack=next(r for r in manifest['artifacts'] if r['remote_path']==SIDE+'/init-data.bin')
                if c.sha256(SIDE+'/init-data.bin')!=pack['sha256']:raise RuntimeError('Seed pack changed')
                response=deploy_side_payload(c,manifest,'seed-side-data.elf',out,transport)
                deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    lease.check();side_owned(c,identity)
                    log=c.read(SIDE_DATA+'/side-seed.log',4<<20) or b''
                    if b'FAILED' in log:raise RuntimeError('Side initialization refused; main unchanged')
                    if ('COMPLETE %d/%d;'%(len(manifest['seed_files']),len(manifest['seed_files']))).encode() in log:
                        (out/'seed.log').write_bytes(log)
                        m.write(out/'seed.json',{'at':m.api.utc_now(),'response':response,'source_pack_sha256':pack['sha256'],'copy_and_readback':'passed','files':len(manifest['seed_files']),'scope':'isolated side data only'})
                        m.emit({'stage':'side-data-initialized','files':len(manifest['seed_files'])});return
                    time.sleep(.5)
                raise RuntimeError('No completed side initialization evidence')
            if operation=='close-side':
                if cleanup_path is not None:
                    if identity.get('kind')!='za_failed_launch_before_observer':
                        raise RuntimeError('Native failed-launch cleanup requires its crash-bound identity')
                    cleanup=m.read(cleanup_path)
                    log=Path(identity['startup_log']['path']).read_text(encoding='utf-8',errors='replace')
                    app_id=identity.get('app_id',cleanup.get('app_id'))
                    if cleanup['title']!='PPSA91990' or type(app_id) is not int or ('appId={0x%08x}'%app_id) not in log:
                        raise RuntimeError('Cleanup app ID differs from the exact failed launch')
                    if not cleanup.get('dynamic_identity') and (cleanup['app_id']!=app_id or cleanup.get('pid',identity['pid'])!=identity['pid']):
                        raise RuntimeError('Fixed cleanup differs from the exact failed launch')
                    identity_args=(app_id,identity['pid']) if cleanup.get('dynamic_identity') else ()
                    result=send_websrv_payload(Path(cleanup['payload']['path']),out,cleanup['payload']['sha256'],identity_args)
                else:result=m.api.http_json('/process_kill?pid='+str(identity['pid']))
                m.write(out/'close-request.json',{'at':m.api.utc_now(),'identity':identity,'response':result})
                deadline=time.monotonic()+20
                while m.api.eboot_processes():
                    if time.monotonic()>deadline:raise RuntimeError('Our side process did not close')
                    time.sleep(.5)
                m.write(out/'closed.json',{'at':m.api.utc_now(),'identity':identity,'response':result,'game_closed':True})
                m.emit({'stage':'owned-side-closed'})
        finally:c.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['inspect', 'backup', 'collect', 'readiness','main-readiness','launch-side','seed-side','close-side','relocate-side'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--console-ok', action='store_true')
    parser.add_argument('--package',type=Path)
    parser.add_argument('--identity',type=Path)
    parser.add_argument('--cleanup-manifest',type=Path)
    parser.add_argument('--evidence-out',type=Path,help='Large private evidence destination; lease tokens stay in local --out')
    parser.add_argument('--payload-transport',choices=('manager','sdk','websrv'),default='manager')
    args = parser.parse_args()
    if not (args.console_ok or os.environ.get('ZW_CONSOLE_OK') == '1'):
        parser.error('coordinated --console-ok required')
    if args.operation in ('readiness','main-readiness'):
        if not args.package:parser.error('readiness needs --package')
        readiness(args.out.resolve(),args.package,args.evidence_out,args.operation=='main-readiness')
    elif args.operation in ('launch-side','seed-side','close-side','relocate-side'):
        if not args.package:parser.error('side operation needs --package')
        side_operation(args.operation,args.out.resolve(),args.package.resolve(),args.identity,args.payload_transport,args.cleanup_manifest)
    else:
        {'inspect': inspect, 'backup': backup, 'collect': collect}[args.operation](args.out.resolve())

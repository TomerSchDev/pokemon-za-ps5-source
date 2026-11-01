"""Lease-guarded commands and verified screenshots for the owned console QA session."""
from pathlib import Path
from datetime import datetime,timezone
import ftplib,hashlib,json,re,sys,time
from storage_paths import data_root
ROOT=data_root();QA=ROOT/'qa/all-pokemon-20261030-r2';OUT=QA/'console-fifty-20261031-r1'
BASE=Path(__file__).resolve().parents[3];LOCAL=BASE/'console-qa-fifty-20261031-r1'
sys.path.insert(0,str(BASE/'Pokemon-ZA-Native-Port'));import run_r3 as api
sys.path.insert(0,str(BASE/'Pokemon-ZA-Native-Port/port/perf-r24/observer'));import client as observer
sys.path.insert(0,str(QA/'python-lib'))
STATE=OUT/'console-session.json';APP='/data/homebrew/PPSA91762'
def lease_guard():
 assert not (LOCAL/'.lease-lost.json').exists(),'Lease was lost; no console commands permitted.'
 heartbeat=json.loads((LOCAL/'.lease-heartbeat.json').read_text())
 assert time.time()-heartbeat['utc']<90,'Console reservation heartbeat is not fresh.'
def discover(c):
 matches=[]
 for name in c.listing('/mnt/sandbox'):
  if not re.fullmatch('PPSA91762_[0-9]{3}',name):continue
  base='/mnt/sandbox/'+name
  param=c.read(base+'/app0/sce_sys/param.json',16384)
  if not param or json.loads(param).get('titleId')!='PPSA91762':continue
  data=base+'/download0/zarecomp';raw=c.read(data+'/observer/session.json',4096)
  if raw:matches.append((data,json.loads(raw)))
 assert len(matches)==1,('Expected exactly one owned observer',matches)
 data,info=matches[0];ps=api.eboot_processes();assert len(ps)==1
 assert info['protocol']==17 and info['title']=='PPSA91762'
 return {'session':info['session'],'data':data,'pid':api.process_pid(ps[0]),'discovered_utc':datetime.now(timezone.utc).isoformat()}
def guard(c,state):
 lease_guard();observer.BASE=state['data']+'/observer'
 assert observer.status(c.ftp)['session']==state['session'],'Observer session changed; do not reuse commands.'
 assert [api.process_pid(x) for x in api.eboot_processes()]==[state['pid']],'Console process changed.'
def command(c,state,op,arg=None,frames=None,label=None):
 guard(c,state);seq=time.time_ns()//1000
 observer.issue(c.ftp,state['session'],seq,op,arg,frames)
 ack_path=observer.BASE+'/session_'+state['session']+'/ack_%d.json'%seq
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  raw=c.read(ack_path,4096)
  if raw:
   ack=json.loads(raw)
   if ack.get('result')!='settling':break
  time.sleep(.15)
 else:raise TimeoutError('No observer acknowledgement for '+op)
 dest=OUT/'captures'/(label or ('command-%d'%seq))
 record=observer.collect(c.ftp,state['session'],seq,dest,expected_retire_capture=arg if op=='retire_capture' else None)
 print(json.dumps(record,ensure_ascii=True),flush=True)
 if op=='snapshot' and record.get('files'):
  assert all(f.get('readback_verified') for f in record['files'])
  retired=command(c,state,'retire_capture',state['session']+':'+str(seq),label=(label or str(seq))+'-retired')
  assert retired['ack']['result']=='retired','Verified capture could not be retired after archiving.'
 return record
def backup(c,state):
 guard(c,state);root=state['data']+'/rando';destination=OUT/'before-console/all-runs';manifest=[]
 active=c.read(root+'/active.json',16384);assert active
 def save(remote,rel,raw=None):
  if raw is None:raw=c.read(remote,128<<20)
  assert raw is not None
  assert c.read(remote,128<<20)==raw,'Source changed during backup: '+remote
  path=destination/rel;path.parent.mkdir(parents=True,exist_ok=True)
  if path.exists():assert path.read_bytes()==raw
  else:path.write_bytes(raw)
  manifest.append({'remote':remote,'relative':str(rel),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 def walk(remote,rel,depth=0):
  assert depth<5
  c.ftp.cwd(remote);items=list(c.ftp.mlsd());c.ftp.cwd('/')
  for name,facts in items:
   if name in ('.','..'):continue
   assert '/' not in name and '\\' not in name
   if facts.get('type')=='dir':walk(remote+'/'+name,Path(rel)/name,depth+1)
   elif facts.get('type') not in ('cdir','pdir'):save(remote+'/'+name,Path(rel)/name)
 runs=[]
 for name in c.listing(root):
  if not re.fullmatch('r[0-9a-f]+-[0-9a-f]+',name):continue
  main=c.read(root+'/'+name+'/save/save_0/main',128<<20)
  if main is None:continue
  runs.append(name);walk(root+'/'+name+'/save',Path(name)/'save')
  report=c.read(root+'/'+name+'/report.json',16<<20)
  if report:save(root+'/'+name+'/report.json',Path(name)/'report.json',report)
 save(root+'/active.json',Path('active.json'),active)
 assert runs and json.loads(active)['id'] in runs
 result={'utc':datetime.now(timezone.utc).isoformat(),'all_runs':True,'fresh':True,'readback_verified':True,'run_ids':runs,'files':manifest,'source_saves_unchanged':True,'active':json.loads(active)}
 (OUT/'before-console/save-backup-manifest.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
 print(json.dumps({'backed_up_runs':len(runs),'files':len(manifest),'active':result['active']},ensure_ascii=True),flush=True)
def main():
 action=sys.argv[1];lease_guard()
 if action=='klog':
  path=OUT/'all-console.klog.log';assert not path.exists()
  capture=api.KlogCapture(path);capture.start()
  try:
   while not (LOCAL/'.stop-klog').exists():
    lease_guard()
    if capture.error:raise RuntimeError(capture.error)
    time.sleep(5)
  finally:capture.stop()
  return
 c=api.Console()
 try:
  if action=='launch':
   assert not api.eboot_processes(),'Another title is running.'
   previous=json.loads(STATE.read_text()) if STATE.exists() else None
   helper='/data/pldmgr/payloads/za_rowlet_r2_launch/rowlet_launch.elf'
   assert c.read(helper,4<<20),'The reviewed scoped launcher is missing.'
   print(api.http_text(api.PAYLOAD_MANAGER+'/loadpayload:'+helper),flush=True)
   started=time.monotonic();deadline=started+90;candidate=None;stable_since=started
   launch_attempts=1;last_launch=started
   while True:
    try:
     state=discover(c)
     if previous and state['session']==previous['session']:raise AssertionError('Waiting for new process observer')
     if candidate!=state['session']:candidate=state['session'];stable_since=time.monotonic()
     if time.monotonic()-stable_since>=3 and time.monotonic()-started>=5:break
    except (AssertionError,ftplib.error_perm):
     if time.monotonic()>deadline:raise
     # A killed title may leave its application mount in teardown after the
     # process is gone. Retry only this title's known launch failure, bounded,
     # while no other title process exists; never delete a sandbox scaffold.
     if launch_attempts<3 and time.monotonic()-last_launch>=15 and not api.eboot_processes():
      launch_log=c.read('/data/rowlet-r2-launch.log',16384) or b''
      if b'SystemLaunch rc=0x80020002' in launch_log:
       lease_guard();assert not api.eboot_processes()
       print('Retrying owned title after completed process teardown (attempt %d)'%(launch_attempts+1),flush=True)
       print(api.http_text(api.PAYLOAD_MANAGER+'/loadpayload:'+helper),flush=True)
       last_launch=time.monotonic();launch_attempts+=1
    assert time.monotonic()<deadline,'New stable observer did not initialize'
    time.sleep(1)
   if previous:
    history=OUT/'session-history';history.mkdir(exist_ok=True)
    saved=history/(previous['session']+'.json')
    if not saved.exists():saved.write_text(json.dumps(previous,indent=1),encoding='utf-8')
   STATE.write_text(json.dumps(state,indent=1),encoding='utf-8');print(json.dumps(state),flush=True)
  elif action=='refresh':
   previous=json.loads(STATE.read_text());state=discover(c)
   assert state['pid']==previous['pid'],'The process changed; establish ownership separately.'
   history=OUT/'session-history';history.mkdir(exist_ok=True)
   saved=history/(previous['session']+'.json')
   if not saved.exists():saved.write_text(json.dumps(previous,indent=1),encoding='utf-8')
   STATE.write_text(json.dumps(state,indent=1),encoding='utf-8');print(json.dumps(state),flush=True)
  else:
   state=json.loads(STATE.read_text());guard(c,state)
   if action=='shot':command(c,state,'snapshot',label=sys.argv[2])
   elif action=='input':command(c,state,'input',sys.argv[2],int(sys.argv[3]))
   elif action=='continue':command(c,state,'continue',sys.argv[2])
   elif action=='backup':backup(c,state)
   elif action=='clone-source':
    active=json.loads(c.read(state['data']+'/rando/active.json',16384));run=active['id']
    assert re.fullmatch('r[0-9a-f]+-[0-9a-f]+',run)
    report=json.loads(c.read(state['data']+'/rando/'+run+'/report.json',16<<20));assert report['native_complete']
    dest=OUT/'before-console/active-run-root'
    for row in report['native_tables']:
     relative=Path('romfs')/row['path'];assert '..' not in relative.parts and not relative.is_absolute()
     raw=c.read(state['data']+'/rando/'+run+'/'+relative.as_posix(),32<<20)
     assert raw and hashlib.sha256(raw).hexdigest()==row['sha256']
     assert raw==c.read(state['data']+'/rando/'+run+'/'+relative.as_posix(),32<<20)
     target=dest/relative;target.parent.mkdir(parents=True,exist_ok=True)
     if target.exists():assert target.read_bytes()==raw
     else:target.write_bytes(raw)
    (dest/'report.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
    try:mods=c.listing(state['data']+'/mods')
    except ftplib.error_perm:mods=['FTP enumeration denied; native activation payload must inventory and preserve existing links.']
    (OUT/'before-console/active-mods.json').write_text(json.dumps({'mods':mods,'active':active,'session':state},indent=1),encoding='utf-8')
    print(json.dumps({'copied_active_run_tables':len(report['native_tables']),'mods':mods,'run':run}),flush=True)
   elif action=='status':print(json.dumps({'state':state,'observer':observer.status(c.ftp),'active':json.loads(c.read(state['data']+'/rando/active.json',16384))}),flush=True)
   elif action=='close':
    print(json.dumps(api.http_json('/process_kill?pid=%d'%state['pid'])),flush=True)
    deadline=time.monotonic()+20
    while api.eboot_processes():
     assert time.monotonic()<deadline;time.sleep(.25)
   else:raise ValueError(action)
 finally:c.close()
if __name__=='__main__':main()

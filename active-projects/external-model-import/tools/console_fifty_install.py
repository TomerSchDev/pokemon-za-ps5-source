"""Upload a manifest-pinned inactive model tree; no executable or save replacement."""
from pathlib import Path
from datetime import datetime,timezone
import ftplib,hashlib,json,subprocess,sys,time
from console_fifty_live import ROOT,OUT,BASE,LOCAL,APP,api,lease_guard
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def evidence(p):return {'path':str(p),'sha256':digest(p)}
def begin():
 source=OUT/'before-console/preflight-before-install.json';pre=json.loads(source.read_text())
 assert not pre['processes'] and not pre['processes_after'] and not api.eboot_processes()
 backup=OUT/'before-console/save-backup-manifest.json';saved=json.loads(backup.read_text())
 assert saved['all_runs'] and saved['readback_verified']
 assert time.time()-datetime.fromisoformat(saved['utc']).timestamp()<300
 assert time.time()-datetime.fromisoformat(pre['utc']).timestamp()<300
 old=ROOT/'console-install-20261030/rowlet-fix-r2/console-released.json'
 assert old.exists() and json.loads(old.read_text()).get('console_released')
 handoff=OUT/'before-console/current-window-handoff.json'
 handoff.write_text(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'current_user_explicitly_requested_console_tests':True,'previous_model_owner_is_this_same_chat':True,'previous_release_evidence':evidence(old),'no_running_title':True,'reserved_ticket':json.loads((LOCAL/'.console-lease.json').read_text())['ticket'],'no_other_queue_owner_when_claimed':True},indent=1))
 lease=json.loads((LOCAL/'.console-lease.json').read_text())
 readiness={'console':'192.168.1.135','ticket':lease['ticket'],'checked_at':datetime.now(timezone.utc).isoformat(),
   'external_owner_handoff':{'confirmed':True,'evidence':evidence(handoff)},
   'game_closed':{'verified':True,'evidence':evidence(source)},
   'save_backup':{'fresh':True,'all_runs':True,'readback_verified':True,'evidence':evidence(backup)},
   'base_readbacks':[{'remote_path':APP+'/eboot.bin','sha256':pre['eboot_sha256'],'evidence':evidence(Path(pre['eboot_readback']))}]}
 path=LOCAL/'readiness.json';path.write_text(json.dumps(readiness,indent=1))
 subprocess.run([sys.executable,str(Path(__file__).with_name('console_fifty_lease.py')),'begin',str(path)],check=True)
 (LOCAL/'.installing.json').write_text(json.dumps({'ticket':lease['ticket'],'utc':time.time()}))
def install():
 lease_guard();assert (LOCAL/'.installing.json').exists();assert not api.eboot_processes()
 package=json.loads((OUT/'model-package.json').read_text());c=api.Console();readbacks=[]
 try:
  def readback(remote,dest,expected):
   h=hashlib.sha256();dest.parent.mkdir(parents=True,exist_ok=True)
   assert not dest.exists()
   with dest.open('xb') as out:
    def block(b):h.update(b);out.write(b)
    c.ftp.retrbinary('RETR '+remote,block,1<<20)
   assert h.hexdigest()==expected,'Console readback differs: '+remote
   return evidence(dest)
  for name,expected in (('console-fifty-models-20261031-r1.zip',package['zip_sha256']),('console-fifty-models-20261031-r1.manifest.bin',package['manifest_sha256'])):
   lease_guard();assert not api.eboot_processes()
   local=OUT/name;remote=APP+'/'+name
   try:prior=c.ftp.size(remote)
   except ftplib.error_perm:prior=None
   assert prior is None,'Versioned destination already exists; inspect before retry.'
   done=0;last=0;start=time.monotonic()
   def progress(b):
    nonlocal done,last
    done+=len(b)
    if done-last>=64<<20:
     print('Uploading cohort assets: %d / %d MiB'%(done//2**20,local.stat().st_size//2**20),flush=True);last=done;lease_guard()
   with local.open('rb') as f:c.ftp.storbinary('STOR '+remote+'.part',f,1<<20,callback=progress)
   staged=readback(remote+'.part',OUT/'readbacks/staged'/name,expected)
   lease_guard();assert not api.eboot_processes();c.ftp.rename(remote+'.part',remote)
   installed=readback(remote,OUT/'readbacks/installed'/name,expected)
   readbacks.append({'remote_path':remote,'staged':staged,'installed':installed})
   print('Verified upload publication: '+name,flush=True)
  folder='/data/pldmgr/payloads/za_console_fifty_20261031'
  try:c.ftp.mkd(folder)
  except ftplib.error_perm:c.ftp.cwd(folder)
  helper=folder+'/install-fifty.elf';raw=(OUT/'install-fifty.elf').read_bytes();c.store(helper,raw);c.chmod(helper,'755');assert c.read(helper,4<<20)==raw
  lease_guard();assert not api.eboot_processes()
  print('Starting manifest-pinned extraction: '+api.http_text(api.PAYLOAD_MANAGER+'/loadpayload:'+helper),flush=True)
  deadline=time.monotonic()+1200;last=b''
  while True:
   lease_guard()
   raw=c.read('/data/console-fifty-20261031-r1-extract.log',2<<20)
   if raw and raw!=last:
    last=raw;print(raw.decode('utf-8','replace').splitlines()[-1],flush=True)
    (OUT/'asset-extraction.log').write_bytes(raw)
   if raw and any(word in raw for word in (b'COMPLETE',b'FAILED',b'REFUSED')):break
   assert time.monotonic()<deadline,'Asset extraction deadline'
   time.sleep(3)
  assert raw and b'COMPLETE' in raw,raw
  result=json.loads(c.read('/data/console-fifty-20261031-r1-extract.json',16384))
  assert result['complete'] and result['files']==package['files'] and result['archive_sha256']==package['zip_sha256']
  result.update(utc=datetime.now(timezone.utc).isoformat(),readbacks=readbacks,executable_replaced=False,user_save_modified=False)
  (OUT/'assets-installed.json').write_text(json.dumps(result,indent=1));print(json.dumps(result),flush=True)
 finally:c.close()
if __name__=='__main__':
 if sys.argv[1]=='begin':begin()
 elif sys.argv[1]=='install':install()
 else:raise ValueError(sys.argv[1])

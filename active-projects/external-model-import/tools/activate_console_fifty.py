"""Stage and activate a distinct QA run in the owned launcher session."""
from pathlib import Path
import hashlib,json,subprocess,time
from console_fifty_live import ROOT,OUT,BASE,LOCAL,APP,api,lease_guard,guard
def linux(p):
 s=str(p.resolve());return '/mnt/'+s[0].lower()+s[2:].replace('\\','/')
def main():
 lease_guard();state=json.loads((OUT/'console-session.json').read_text());identity=json.loads((OUT/'trial-identity.json').read_text())
 package=json.loads((OUT/'model-package.json').read_text());assert json.loads((OUT/'assets-installed.json').read_text())['complete']
 source=OUT/'trial-setup';remote=APP+'/console-fifty-20261031-r1-trial-setup';c=api.Console()
 try:
  guard(c,state)
  def mkdir(path):
   try:c.ftp.mkd(path)
   except Exception:c.ftp.cwd(path)
  mkdir(remote)
  files=sorted(p for p in source.rglob('*') if p.is_file() and p.name!='setup-ready.json')+[source/'setup-ready.json']
  for p in files:
   rel=p.relative_to(source);parent=remote
   for component in rel.parts[:-1]:parent+='/'+component;mkdir(parent)
   target=remote+'/'+rel.as_posix();raw=p.read_bytes()
   existing=c.read(target,64<<20)
   if existing is None:
    c.store(target+'.part',raw);assert c.read(target+'.part',64<<20)==raw;c.ftp.rename(target+'.part',target)
   else:assert existing==raw,'Different existing staging data: '+target
   assert c.read(target,64<<20)==raw
  compiler=LOCAL/'compiler';compiler.mkdir(exist_ok=True)
  names=[p.relative_to(source/'run').as_posix() for p in sorted((source/'run').rglob('*')) if p.is_file()]
  constants={'DATA':state['data'],'SESSION_ID':state['session'],'PREVIOUS_RUN':identity['source_run'],'RUN_ID':identity['run'],'MODEL_ARCHIVE_SHA':package['zip_sha256']}
  header=''.join('#define %s %s\n'%(k,json.dumps(v)) for k,v in constants.items())
  header+='#define RUN_FILES %du\nstatic const char*run_files[]={%s};\n'%(len(names),','.join(json.dumps(n) for n in names))
  (compiler/'console_fifty_activation.h').write_text(header,encoding='utf-8')
  raw=Path(__file__).with_name('activate_console_fifty.c').read_bytes();(compiler/'activate_fifty.c').write_bytes(raw)
  sdk='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk'
  elf=compiler/'activate-fifty.elf'
  subprocess.run(['wsl.exe','-e',sdk+'/bin/prospero-clang','-O2','-Wall','-Wno-misleading-indentation','-I'+linux(compiler),linux(compiler/'activate_fifty.c'),'-o',linux(elf)],check=True)
  remote_elf='/data/pldmgr/payloads/za_console_fifty_20261031/activate-fifty.elf'
  c.store(remote_elf,elf.read_bytes());c.chmod(remote_elf,'755');assert c.read(remote_elf,4<<20)==elf.read_bytes()
  guard(c,state);print('Scoped activation: '+api.http_text(api.PAYLOAD_MANAGER+'/loadpayload:'+remote_elf),flush=True)
  deadline=time.monotonic()+40
  while True:
   raw=c.read('/data/console-fifty-20261031-r1-activate.log',1<<20)
   if raw and any(x in raw for x in (b'COMPLETE',b'FAILED',b'REFUSED')):break
   assert time.monotonic()<deadline;time.sleep(.3)
  (OUT/'activation.log').write_bytes(raw);print(raw.decode('utf-8','replace'),flush=True);assert b'COMPLETE' in raw
  guard(c,state);assert json.loads(c.read(state['data']+'/rando/active.json',16384))['id']==identity['run']
  new_save=c.read(state['data']+'/rando/'+identity['run']+'/save/save_0/main',16<<20)
  assert new_save==(source/'run/save/save_0/main').read_bytes()
  result={'utc':time.time(),'run':identity['run'],'previous_run':identity['source_run'],'new_save_readback_verified':True,'all_previous_runs_retained':True,'executable_unchanged':True,'restart_required':True,'session':state}
  (OUT/'trial-activated.json').write_text(json.dumps(result,indent=1));print(json.dumps(result),flush=True)
 finally:c.close()
if __name__=='__main__':main()

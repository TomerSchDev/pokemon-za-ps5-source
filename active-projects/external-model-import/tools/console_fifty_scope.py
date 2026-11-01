"""Expose only the current five families from the already verified console assets."""
from pathlib import Path
import ftplib,hashlib,json,posixpath,subprocess,sys,time,zipfile
from console_fifty_live import OUT,LOCAL,APP,STATE,api,lease_guard,guard

def linux(p):
 s=str(p.resolve());return '/mnt/'+s[0].lower()+s[2:].replace('\\','/')

def main():
 batch=int(sys.argv[1]);assert 1<=batch<=10;lease_guard()
 selection=json.loads((OUT/'selection.json').read_text())['targets']
 assets=json.loads((OUT/'assets.json').read_text())['targets']
 wanted={x['key'] for r in selection[(batch-1)*5:batch*5] for x in (r['model'],r['evolution']['model'])}
 wanted|={x['key'] for x in assets if x['national'] in (10,44,46,201,722,928)}
 models=[x for x in assets if x['key'] in wanted];assert len(models)>=10
 package=json.loads((OUT/'model-package.json').read_text())
 state=json.loads(STATE.read_text())
 full=posixpath.dirname(posixpath.dirname(state['data']))+'/app0/console-fifty-20261031-r1-models'
 name='console-fifty-scope-b%02d'%batch;scope=state['data']+'/'+name
 with zipfile.ZipFile(OUT/'console-fifty-models-20261031-r1.zip') as z:
  prefix='mods/all-models/'
  files=[p[len(prefix):] for p in z.namelist() if p.startswith(prefix+'romfs/') and not p.endswith('/')]
 assert files,'Empty package index'
 top={p.split('/')[1] for p in files}-{'ik_pokemon'}
 ik={p.split('/')[2] for p in files if p.startswith('romfs/ik_pokemon/')}-{'data'}
 links=['romfs/'+p for p in sorted(top)]+['romfs/ik_pokemon/'+p for p in sorted(ik)]
 links+=sorted({'romfs/ik_pokemon/data/'+str(Path(m['model_path']).parent).replace('\\','/') for m in models})
 count=sum(any(p==n or p.startswith(n+'/') for n in links) for p in files)
 assert count<12000,('Scoped file count still too large',count)
 compiler=LOCAL/'compiler';compiler.mkdir(exist_ok=True)
 registration=OUT/('registration-b%02d'%batch);assert (registration/'registration-ready.json').is_file()
 remote_registration=APP+'/console-fifty-registration-b%02d'%batch
 constants={'DATA':state['data'],'SID':state['session'],'SCOPE':scope,'LINK_TARGET':'../'+name,'ARCHIVE_SHA':package['zip_sha256'],'REG_TARGET':'../../../app0/console-fifty-registration-b%02d'%batch}
 header=''.join('#define %s %s\n'%(k,json.dumps(v)) for k,v in constants.items())
 pairs=[(scope+'/'+p,posixpath.relpath(full+'/'+p,posixpath.dirname(scope+'/'+p))) for p in links]
 header+='#define N_LINKS %d\nstatic const char*links[][2]={%s};\n'%(len(pairs),','.join('{%s,%s}'%(json.dumps(a),json.dumps(b)) for a,b in pairs))
 (compiler/'scope_fifty.h').write_text(header)
 (compiler/'scope_fifty.c').write_bytes(Path(__file__).with_suffix('.c').read_bytes())
 elf=compiler/('scope-b%02d.elf'%batch);sdk='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk'
 subprocess.run(['wsl.exe','-e',sdk+'/bin/prospero-clang','-O2','-Wall','-Wno-misleading-indentation','-I'+linux(compiler),linux(compiler/'scope_fifty.c'),'-o',linux(elf)],check=True)
 c=api.Console()
 try:
  guard(c,state)
  for p in sorted(registration.rglob('*')):
   if not p.is_file():continue
   rel=p.relative_to(registration);parent=remote_registration
   for component in ((),):pass
   for component in [None]+list(rel.parts[:-1]):
    if component is not None:parent+='/'+component
    try:c.ftp.mkd(parent)
    except ftplib.all_errors:c.ftp.cwd(parent)
   target=remote_registration+'/'+rel.as_posix();raw=p.read_bytes();existing=c.read(target,16<<20)
   if existing is None:
    c.store(target+'.part',raw);assert c.read(target+'.part',16<<20)==raw;c.ftp.rename(target+'.part',target)
   else:assert existing==raw,'Different existing registration '+target
  remote='/data/pldmgr/payloads/za_console_fifty_20261031/scope-b%02d.elf'%batch
  c.store(remote,elf.read_bytes());c.chmod(remote,'755');assert c.read(remote,4<<20)==elf.read_bytes()
  guard(c,state)
  if c.read('/data/console-fifty-scope.log',1<<20) is not None:
   try:c.ftp.delete('/data/console-fifty-scope.log')
   except ftplib.error_reply as e:assert str(e).startswith('226 ')
  print(api.http_text(api.PAYLOAD_MANAGER+'/loadpayload:'+remote),flush=True)
  deadline=time.monotonic()+30
  while True:
   raw=c.read('/data/console-fifty-scope.log',1<<20)
   if raw and any(x in raw for x in (b'COMPLETE',b'FAILED',b'REFUSED')):break
   assert time.monotonic()<deadline;time.sleep(.2)
  assert b'COMPLETE' in raw,raw.decode(errors='replace')
  (OUT/('scope-b%02d.log'%batch)).write_bytes(raw)
  receipt={'batch':batch,'model_keys':sorted(wanted),'visible_files':count,'scope':scope,'links':links,'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'log':raw.decode()}
  (OUT/('scope-b%02d.json'%batch)).write_text(json.dumps(receipt,indent=1))
  print(json.dumps(receipt),flush=True)
 finally:c.close()
if __name__=='__main__':main()

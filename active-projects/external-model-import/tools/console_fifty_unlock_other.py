"""Fix the trial's locked Other pocket while its game has not started."""
import hashlib,json,subprocess,time
from pathlib import Path
from console_fifty_live import OUT,STATE,api,guard

def main():
 state=json.loads(STATE.read_text());identity=json.loads((OUT/'trial-identity.json').read_text());c=api.Console()
 try:
  guard(c,state);folder=state['data']+'/observer/session_'+state['session']
  for n in c.listing(folder):
   if n.startswith('ack_'):
    a=json.loads(c.read(folder+'/'+n,4096));assert a.get('op')!='continue','Only a fresh launcher session is allowed'
  active=json.loads(c.read(state['data']+'/rando/active.json',4096));assert active['id']==identity['run']
  remote=state['data']+'/rando/'+identity['run']+'/save/save_0/main'
  raw=c.read(remote,16<<20);assert raw and raw==c.read(remote,16<<20)
  revision=OUT/'save-revisions'/('other-unlock-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));revision.mkdir(parents=True)
  source=revision/'source-main';target=revision/'other-unlocked-main';source.write_bytes(raw)
  ps=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe'
  script=Path(__file__).with_name('Unlock-ConsoleFiftyOther.ps1')
  result=subprocess.run([str(ps),'-NoProfile','-File',str(script),'-SourceSave',str(source),'-OutputSave',str(target)],capture_output=True,text=True,check=True)
  (revision/'check.json').write_text(result.stdout);print(result.stdout,flush=True)
  fixed=target.read_bytes();guard(c,state);assert c.read(remote,16<<20)==raw
  c.store(remote+'.other-unlock.part',fixed);assert c.read(remote+'.other-unlock.part',16<<20)==fixed
  c.ftp.rename(remote+'.other-unlock.part',remote);assert c.read(remote,16<<20)==fixed
  receipt={'source_sha256':hashlib.sha256(raw).hexdigest(),'result_sha256':hashlib.sha256(fixed).hexdigest(),'run':identity['run'],'only_trial_run_modified':True,'readback_verified':True,'session':state['session']}
  (revision/'installed.json').write_text(json.dumps(receipt,indent=1));print(json.dumps(receipt),flush=True)
 finally:c.close()
if __name__=='__main__':main()

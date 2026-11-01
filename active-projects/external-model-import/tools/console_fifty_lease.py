"""Cooperative exclusive console window. Keeps the token out of logs and deliveries."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
from storage_paths import data_root
ROOT=data_root();OUT=ROOT/'qa/all-pokemon-20261030-r2/console-fifty-20261031-r1'
BASE=Path(__file__).resolve().parents[3];LOCAL=BASE/'console-qa-fifty-20261031-r1'
QUEUE=BASE/'Pokemon-ZA-Native-Port/tools/console-install-queue/console_queue.py'
AGENT='codex-console-fifty-20261031';LEASE=LOCAL/'.console-lease.json'
def call(args,token=None):
 env=dict(os.environ)
 if token:env['CONSOLE_INSTALL_TOKEN']=token
 r=subprocess.run([sys.executable,'-I',str(QUEUE)]+args,env=env,capture_output=True,text=True,encoding='utf-8')
 if r.returncode:raise RuntimeError('Queue error %d: %s'%(r.returncode,r.stdout+r.stderr))
 return json.loads(r.stdout)
def main():
 action=sys.argv[1]
 if action=='claim':
  assert not LEASE.exists()
  package=json.loads((OUT/'model-package.json').read_text());before=json.loads((OUT/'before-console/preflight.json').read_text())
  job={'console':'192.168.1.135','title_id':'PPSA91762','name':'Random cohort of 50 imported species: real console animations, attacks and level evolutions',
       'artifacts':[{'path':str(OUT/'console-fifty-models-20261031-r1.zip'),'sha256':package['zip_sha256'],'remote_path':'/data/homebrew/PPSA91762/console-fifty-models-20261031-r1.zip'},
                    {'path':str(OUT/'console-fifty-models-20261031-r1.manifest.bin'),'sha256':package['manifest_sha256'],'remote_path':'/data/homebrew/PPSA91762/console-fifty-models-20261031-r1.manifest.bin'}],
       'expected_base':[{'remote_path':'/data/homebrew/PPSA91762/eboot.bin','sha256':before['eboot_sha256']}],
       'external_dependencies':[],
       'notes':'Current user explicitly authorizes console testing. Previous model-testing window was released by this same chat. Live read-only checks found no running title and no active queue lease. Create a distinct test run and preserve all user saves, current executable, music and other agents mods. No executable replacement is planned.'}
  p=LOCAL/'queue-job.json';p.write_text(json.dumps(job,indent=1),encoding='utf-8')
  queued=call(['enqueue','--agent',AGENT,'--request-id','models-fifty-real-console-20261031-r1','--job',str(p)])
  ticket=queued.get('ticket') or queued.get('job',{}).get('ticket');assert ticket,queued
  lease=call(['claim','--agent',AGENT,'--ticket',ticket]);LEASE.write_text(json.dumps(lease),encoding='utf-8')
  print(json.dumps({'ticket':ticket,'phase':lease.get('phase'),'lease_stored_locally':True}),flush=True)
 elif action=='heartbeat':
  lease=json.loads(LEASE.read_text());ticket=lease['ticket'];token=lease['token']
  while not (LOCAL/'.stop-heartbeat').exists():
   try:
    result=call(['heartbeat','--agent',AGENT,'--ticket',ticket],token)
    (LOCAL/'.lease-heartbeat.json').write_text(json.dumps({'utc':time.time(),'status':'valid','ticket':ticket}),encoding='utf-8')
   except Exception as ex:
    (LOCAL/'.lease-lost.json').write_text(json.dumps({'utc':time.time(),'error':str(ex)}));raise
   time.sleep(30)
 elif action=='begin':
  lease=json.loads(LEASE.read_text())
  result=call(['heartbeat','--agent',AGENT,'--ticket',lease['ticket'],'--begin-install',sys.argv[2]],lease['token'])
  print(json.dumps({'ticket':lease['ticket'],'installing':True}),flush=True)
 else:raise ValueError(action)
if __name__=='__main__':main()

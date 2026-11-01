"""Read-only live console inventory and an exact executable backup on NAS."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys,time
from storage_paths import data_root
ROOT=data_root();OUT=ROOT/'qa/all-pokemon-20261030-r2/console-fifty-20261031-r1'
BASE=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(BASE/'Pokemon-ZA-Native-Port'));import run_r3 as api
APP='/data/homebrew/PPSA91762'

def main():
 processes=api.eboot_processes();assert not processes,'Console title started during preparation; inspect ownership before launch.'
 c=api.Console()
 try:
  files=c.listing(APP)
  backup=OUT/'before-console';backup.mkdir(exist_ok=True)
  suffix='-before-install' if '--before-install' in sys.argv else ''
  target=backup/('eboot'+suffix+'.bin');assert not target.exists()
  digest=hashlib.sha256();done=0;last=0;start=time.monotonic()
  with target.open('xb') as out:
   def block(b):
    nonlocal done,last
    out.write(b);digest.update(b);done+=len(b)
    if done-last>=128<<20:
     print('Existing console executable backup: %d MiB'%(done//2**20),flush=True);last=done
   c.ftp.retrbinary('RETR '+APP+'/eboot.bin',block,1<<20)
  assert done==c.ftp.size(APP+'/eboot.bin')
  result={'utc':datetime.now(timezone.utc).isoformat(),'processes':processes,'processes_after':api.eboot_processes(),'eboot_readback':str(target),'eboot_sha256':digest.hexdigest(),'eboot_bytes':done,'seconds':time.monotonic()-start,'app_files':files,'console_mutated':False}
  assert not result['processes_after']
  (backup/('preflight'+suffix+'.json')).write_text(json.dumps(result,indent=1),encoding='utf-8')
  print(json.dumps({k:v for k,v in result.items() if k!='app_files'},ensure_ascii=True),flush=True)
  print('APP_FILES',json.dumps(files),flush=True)
 finally:c.close()

if __name__=='__main__':main()

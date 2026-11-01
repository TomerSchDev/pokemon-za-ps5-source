"""Install only the bounded-input extension, preserving the FD-fixed build and saves."""
import json, shutil, time
from pathlib import Path
import resume_console_fifty as deploy
from console_fifty_live import OUT, STATE, APP, api, guard

def main():
    build=Path(r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\r28b-fd-qa-input-20261031-r2')
    info=json.loads((build/'BUILD-INFO.json').read_text())
    folder=OUT/'resume-20261031-r2/qa-input-build-r2';folder.mkdir(parents=True,exist_ok=True)
    for relative in ['BUILD-INFO.json','host-tests.log','link.log','conversion.log','candidate/eboot.bin']:
        p=build/relative;target=folder/p.name
        if target.exists():assert deploy.sha(target)==deploy.sha(p)
        else:shutil.copyfile(p,target);assert deploy.sha(target)==deploy.sha(p)
    deploy.DEST=OUT/'resume-20261031-r2/combo-deployment-r2'
    assert not (deploy.DEST/'deployment.json').exists()
    source=folder/'eboot.bin';assert deploy.sha(source)==info['eboot_sha256']
    state=json.loads(STATE.read_text());identity=json.loads((OUT/'trial-identity.json').read_text())
    c=api.Console()
    try:
        guard(c,state);assert json.loads(c.read(state['data']+'/rando/active.json',4096))['id']==identity['run']
        backup=deploy.backup(c,state['data']);guard(c,state)
        print(json.dumps(api.http_json('/process_kill?pid=%d'%state['pid'])),flush=True)
        end=time.monotonic()+20
        while api.eboot_processes():assert time.monotonic()<end;time.sleep(.3)
        deploy.require_closed()
        before=deploy.readback(c,APP+'/eboot.bin','eboot-before.bin')
        assert before['sha256']==info['base_eboot_sha256'],'Current executable changed; merge required'
        staged_remote=APP+'/eboot.qa-input-r2.part';previous=APP+'/eboot.before-qa-input-r2.bin'
        assert c.read(staged_remote,1) is None and c.read(previous,1) is None
        with source.open('rb') as f:c.ftp.storbinary('STOR '+staged_remote,f,1<<20)
        staged=deploy.readback(c,staged_remote,'eboot-staged.bin');assert staged['sha256']==info['eboot_sha256']
        deploy.record('staged.json',staged);deploy.require_closed()
        c.ftp.rename(APP+'/eboot.bin',previous)
        try:c.ftp.rename(staged_remote,APP+'/eboot.bin')
        except Exception:c.ftp.rename(previous,APP+'/eboot.bin');raise
        installed=deploy.readback(c,APP+'/eboot.bin','eboot-installed.bin');assert installed['sha256']==info['eboot_sha256']
        assert c.sha256(previous)==info['base_eboot_sha256']
        deploy.record('deployment.json',{'utc':deploy.now(),'base':before,'staged':staged,'installed':installed,'save_backup':str(backup),'previous_executable_preserved_remote':previous,'console_installed':True,'gameplay_verified':False})
    finally:c.close()
if __name__=='__main__':main()

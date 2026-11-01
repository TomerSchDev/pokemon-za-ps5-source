"""Explicit, idle-only r19 install/launch. No implicit game close or save edits."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import run_r3 as r

APP='/data/homebrew/PPSA91762'
NEW='1f8d448a9d6a89f3abc2d94e36db23bef008d3dc8e1d30e9f3ea7c5fea557918'
KNOWN={
    '5e02bcf386b07cd1c96e0ee2f2bd3f32bd900849aeacdc4668023a71372150c0':'r15',
    '498aec45e8ae1c698aa505c41548207b2276a80918758727242f36e9ae8bee4c':'r16',
    '27c3b2e662a7181abb751e29d846746ec86a49d3bacca9f3bc58c1359ec249fb':'r17',
    '67284db32a427459a88f8ca0bb8f09d5e12992e8e48ae1e2ac33f29356a04139':'r17a',
    'f66383cc523d538fc87dc9717ffb13aff149199cf11ace0baffe62a20dc686a7':'r19',
    NEW:'r19a',
}
EVIDENCE=ROOT/'evidence/local-shader-r19'

def sha(data):return hashlib.sha256(data).hexdigest()
def idle():
    active=r.eboot_processes()
    if active:raise RuntimeError('Console occupied; no game will be closed: '+json.dumps(active))

def deploy(c):
    idle()
    assert json.loads(c.read(APP+'/sce_sys/param.json'))['titleId']=='PPSA91762'
    assert c.read('/user/app/PPSA91762/mount.lnk')==APP.encode()
    source=ROOT/'artifacts/randomizer-r19a-local-compiler/PPSA91762'
    data=(source/'eboot.bin').read_bytes();assert sha(data)==NEW
    installed=c.sha256(APP+'/eboot.bin')
    if installed not in KNOWN:raise RuntimeError('Unknown installed build: '+str(installed))
    run=r.stamp();out=EVIDENCE/('deployment-'+run);out.mkdir(parents=True,exist_ok=False)
    journal=dict(at=r.utc_now(),previous_sha256=installed,new_sha256=NEW,previous_build=KNOWN[installed],
                 backup=str(out),files=[],installed=False)
    def save():(out/'receipt.json').write_text(json.dumps(journal,indent=2)+'\n')
    save()
    if installed!=NEW:
        backup=c.read(APP+'/eboot.bin',512<<20);assert sha(backup)==installed
        (out/'previous-eboot.bin').write_bytes(backup)
        # Preserve the original remotely too. Swap only after both readbacks.
        remote_backup=APP+'/eboot.bin.before-r19-'+run
        stage=APP+'/eboot.bin.r19-staged-'+run
        c.store(stage,data);c.chmod(stage,'755');assert c.sha256(stage)==NEW
        idle();assert c.sha256(APP+'/eboot.bin')==installed
        c.ftp.rename(APP+'/eboot.bin',remote_backup)
        journal['remote_backup']=remote_backup;save()
        try:c.ftp.rename(stage,APP+'/eboot.bin')
        except Exception:
            c.ftp.rename(remote_backup,APP+'/eboot.bin');raise
        assert c.sha256(APP+'/eboot.bin')==NEW
    for name,value in [('local-shader-options.txt',b'local\n'),('observer-enable.txt',b'observe-r17\n')]:
        old=c.read(APP+'/'+name,4096)
        if old is not None:(out/name).write_bytes(old)
        journal['files'].append(dict(name=name,old_sha256=sha(old) if old is not None else None))
        save()
        if old!=value:
            stage=APP+'/'+name+'.r19-staged-'+run;c.store(stage,value);assert c.read(stage)==value
            idle();c.ftp.rename(stage,APP+'/'+name)
        assert c.read(APP+'/'+name)==value
    journal['installed']=True;save()
    return journal

def main():
    p=argparse.ArgumentParser();p.add_argument('op',choices=['inspect','deploy','launch','log']);p.add_argument('--seconds',type=int,default=900)
    a=p.parse_args();EVIDENCE.mkdir(parents=True,exist_ok=True)
    if a.op=='log':
        path=EVIDENCE/('r19-'+r.stamp()+'.klog.log');capture=r.KlogCapture(path);capture.start();print(str(path),flush=True)
        deadline=time.monotonic()+a.seconds
        try:
            while time.monotonic()<deadline and capture.is_alive():time.sleep(.25)
        finally:capture.stop()
        print(json.dumps(dict(path=str(path),lines=capture.lines,error=capture.error)));return
    c=r.Console()
    try:
        if a.op=='inspect':
            result=dict(processes=r.eboot_processes(),installed_sha256=c.sha256(APP+'/eboot.bin'),
                        local_options=c.read(APP+'/local-shader-options.txt',128).decode() if c.read(APP+'/local-shader-options.txt',128) else None)
        elif a.op=='deploy':result=deploy(c)
        else:
            idle();assert c.sha256(APP+'/eboot.bin')==NEW
            result=dict(at=r.utc_now(),response=r.http_text(r.PAYLOAD_MANAGER+'/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf'))
        path=EVIDENCE/(a.op+'-'+r.stamp()+'.json');path.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2));print(path)
    finally:c.close()

if __name__=='__main__':main()

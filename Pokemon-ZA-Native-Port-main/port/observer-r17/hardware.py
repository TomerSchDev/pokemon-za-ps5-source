"""Scoped r17 hardware validation. Explicit commands; never closes another title."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r
from client import status,issue,collect,BASE

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'evidence/observer-r17-hardware'
APP='/data/homebrew/PPSA91762'
SANDBOX='/mnt/sandbox/PPSA91762_000'
SOURCE=ROOT/'artifacts/randomizer-r17a-observer-validated/PPSA91762'
EXPECTED='67284db32a427459a88f8ca0bb8f09d5e12992e8e48ae1e2ac33f29356a04139'
PREVIOUS='27c3b2e662a7181abb751e29d846746ec86a49d3bacca9f3bc58c1359ec249fb'
OLD='5e02bcf386b07cd1c96e0ee2f2bd3f32bd900849aeacdc4668023a71372150c0'
def sha(data):return hashlib.sha256(data).hexdigest()
def evidence(name,data):
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    p=EVIDENCE/(name+'-'+r.stamp()+'.json');p.write_text(json.dumps(data,indent=2)+'\n');return str(p)
def idle():
    active=r.eboot_processes()
    if active:raise RuntimeError('Console occupied: '+json.dumps(active))
def backup(c):
    base=SANDBOX+'/download0/zarecomp/rando'
    active=c.read(base+'/active.json',4096)
    if not active:raise RuntimeError('Save sandbox unavailable; remain in launcher until backup succeeds')
    run=json.loads(active)['id'];assert re.fullmatch(r'r[0-9a-f]{16}-[0-9a-f]{8}',run)
    out=EVIDENCE/('save-backup-'+r.stamp());out.mkdir(parents=True)
    (out/'active.json').write_bytes(active)
    files=[]
    for rel in ('report.json','save/save_0/main','cheats.txt'):
        remote=base+'/'+run+'/'+rel;data=c.read(remote,16<<20)
        if data is None:
            if rel!='cheats.txt':raise RuntimeError('Required save/report missing: '+rel)
            continue
        assert sha(data)==c.sha256(remote),'Changed during backup: '+rel
        target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        files.append(dict(path=rel,bytes=len(data),sha256=sha(data)))
    assert c.read(base+'/active.json',4096)==active
    result=dict(at=r.utc_now(),run=run,path=str(out),files=files,double_read_verified=True)
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
def deploy(c):
    idle();assert json.loads(c.read(APP+'/sce_sys/param.json'))['titleId']=='PPSA91762'
    assert sha((SOURCE/'eboot.bin').read_bytes())==EXPECTED
    installed=c.sha256(APP+'/eboot.bin')
    if installed not in (OLD,PREVIOUS,EXPECTED):raise RuntimeError('Unexpected installed build: '+str(installed))
    original=ROOT/'artifacts/randomizer-r15/PPSA91762/eboot.bin'
    assert sha(original.read_bytes())==OLD
    rec=dict(at=r.utc_now(),old_sha256=installed,new_sha256=EXPECTED,rollback_eboot=str(original),files=[])
    folder=EVIDENCE/('deployment-backup-'+r.stamp());folder.mkdir(parents=True)
    for name in ('performance-options.txt','observer-enable.txt'):
        data=c.read(APP+'/'+name,4096)
        if data is not None:(folder/name).write_bytes(data)
        rec['files'].append(dict(name=name,previous_sha256=sha(data) if data is not None else None))
    rec['config_backup']=str(folder)
    journal=EVIDENCE/('deployment-'+r.stamp()+'.json')
    journal.write_text(json.dumps(rec,indent=2)+'\n')
    for name in ('eboot.bin','performance-options.txt','observer-enable.txt'):
        data=(SOURCE/name).read_bytes();digest=sha(data);remote=APP+'/'+name
        if c.sha256(remote)!=digest:
            stage=remote+'.r17-staged';c.store(stage,data);c.chmod(stage,'755' if name=='eboot.bin' else '644')
            assert c.sha256(stage)==digest
            idle();c.ftp.rename(stage,remote)
        assert c.sha256(remote)==digest
        rec[name]={'sha256':digest,'bytes':len(data),'readback_verified':True}
        journal.write_text(json.dumps(rec,indent=2)+'\n')
        print('Verified '+name,flush=True)
    return rec
def main():
    p=argparse.ArgumentParser();p.add_argument('op',choices=('inspect','deploy','launch','backup','log'));p.add_argument('--seconds',type=int,default=900)
    a=p.parse_args();EVIDENCE.mkdir(parents=True,exist_ok=True)
    if a.op=='log':
        path=EVIDENCE/('r17-'+r.stamp()+'.klog.log');cap=r.KlogCapture(path);cap.start();print(str(path),flush=True)
        deadline=time.monotonic()+a.seconds
        try:
            while time.monotonic()<deadline and cap.is_alive():time.sleep(.25)
        finally:cap.stop()
        print(json.dumps(dict(path=str(path),lines=cap.lines,error=cap.error)));return
    c=r.Console()
    try:
        if a.op=='inspect':
            result=dict(processes=r.eboot_processes(),metadata=json.loads(c.read(APP+'/sce_sys/param.json')),launcher=bool(c.read('/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf')),
                        active=c.read(SANDBOX+'/download0/zarecomp/rando/active.json',4096).decode() if c.read(SANDBOX+'/download0/zarecomp/rando/active.json',4096) else None)
        elif a.op=='deploy':result=deploy(c)
        elif a.op=='backup':result=backup(c)
        else:
            idle();assert c.sha256(APP+'/eboot.bin')==EXPECTED
            assert c.read('/user/app/PPSA91762/mount.lnk')
            result=dict(at=r.utc_now(),response=r.http_text(r.PAYLOAD_MANAGER+'/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf'))
        path=evidence(a.op,result);print(json.dumps(result,indent=2));print(path)
    finally:c.close()
if __name__=='__main__':main()

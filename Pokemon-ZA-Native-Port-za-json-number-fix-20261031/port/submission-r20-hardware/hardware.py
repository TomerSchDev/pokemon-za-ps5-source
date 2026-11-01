"""Parent-owned r20 deployment. Explicit idle-only changes; never kills a title."""
import argparse, hashlib, json, re, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import run_r3 as r
APP='/data/homebrew/PPSA91762'
SOURCE=ROOT/'artifacts/randomizer-r20-batch/PPSA91762/eboot.bin'
BASE=ROOT/'artifacts/randomizer-r19a-local-compiler/PPSA91762/eboot.bin'
BASE_SHA='1f8d448a9d6a89f3abc2d94e36db23bef008d3dc8e1d30e9f3ea7c5fea557918'
E=ROOT/'evidence/submission-r20-hardware'

def sha(data):return hashlib.sha256(data).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def idle():
    procs=r.eboot_processes()
    if procs:raise RuntimeError('Console occupied; no process will be closed: '+json.dumps(procs))
def identity(c):
    assert json.loads(c.read(APP+'/sce_sys/param.json'))['titleId']=='PPSA91762'
    assert c.read('/user/app/PPSA91762/mount.lnk')==APP.encode()
def options(c,profile,out):
    identity(c);idle()
    name='submission-options.txt';previous=c.read(APP+'/'+name,1024)
    if previous is not None:(out/'previous-submission-options.txt').write_bytes(previous)
    data=(profile+'\n').encode()
    stage=APP+'/'+name+'.staged-'+r.stamp()
    c.store(stage,data);assert c.read(stage)==data
    idle();c.ftp.rename(stage,APP+'/'+name)
    assert c.read(APP+'/'+name)==data
    return dict(profile=profile,previous=previous.decode(errors='replace') if previous else None,readback=True)
def deploy(c,expected,out,rollback=False):
    idle();identity(c)
    source=BASE if rollback else SOURCE
    new=BASE_SHA if rollback else expected
    data=source.read_bytes();assert sha(data)==new
    installed=c.sha256(APP+'/eboot.bin')
    if installed not in (BASE_SHA,expected):raise RuntimeError('Unknown installed binary: '+str(installed))
    assert sha(BASE.read_bytes())==BASE_SHA
    record=dict(at=r.utc_now(),previous_sha256=installed,new_sha256=new,installed=False,rollback_source=str(BASE))
    for name in ('performance-options.txt','performance-profile.txt','observer-enable.txt','local-shader-options.txt'):
        old=c.read(APP+'/'+name,1024)
        if old is not None:(out/name).write_bytes(old)
        record[name]=old.decode(errors='replace') if old else None
    if c.read(APP+'/local-shader-test.txt',1024) is not None:raise RuntimeError('Diagnostic shader config still exists')
    receipt=out/'receipt.json';write(receipt,record)
    if installed!=new:
        stage=APP+'/eboot.bin.r20-stage-'+r.stamp()
        backup=APP+'/eboot.bin.before-r20-'+r.stamp()
        c.store(stage,data);c.chmod(stage,'755')
        assert c.sha256(stage)==new
        idle();assert c.sha256(APP+'/eboot.bin')==installed
        c.ftp.rename(APP+'/eboot.bin',backup)
        record['remote_backup']=backup;write(receipt,record)
        try:c.ftp.rename(stage,APP+'/eboot.bin')
        except Exception:
            c.ftp.rename(backup,APP+'/eboot.bin');raise
        assert c.sha256(APP+'/eboot.bin')==new
    record['options']=options(c,'each',out)
    record['installed']=True;write(receipt,record)
    return record
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('op',choices=['inspect','deploy','profile','launch','rollback','log'])
    p.add_argument('--sha256')
    p.add_argument('--profile',choices=['each','batch'],default='each')
    p.add_argument('--seconds',type=int,default=900)
    a=p.parse_args();E.mkdir(parents=True,exist_ok=True)
    if a.op=='log':
        path=E/('r20-'+r.stamp()+'.klog.log');cap=r.KlogCapture(path);cap.start()
        print(str(path),flush=True)
        try:
            deadline=time.monotonic()+a.seconds
            while time.monotonic()<deadline and cap.is_alive():time.sleep(.25)
        finally:cap.stop()
        print(json.dumps(dict(path=str(path),lines=cap.lines,error=cap.error)));return
    if a.op!='inspect':
        assert a.sha256 and re.fullmatch('[0-9a-f]{64}',a.sha256)
        assert sha(SOURCE.read_bytes())==a.sha256
    c=r.Console()
    try:
        out=E/(a.op+'-'+r.stamp());out.mkdir(exist_ok=False)
        if a.op=='inspect':
            result=dict(processes=r.eboot_processes(),metadata=json.loads(c.read(APP+'/sce_sys/param.json')),
                        profile=c.read(APP+'/submission-options.txt',1024))
            if result['profile'] is not None:result['profile']=result['profile'].decode(errors='replace')
        elif a.op in ('deploy','rollback'):result=deploy(c,a.sha256,out,a.op=='rollback')
        elif a.op=='profile':
            idle();assert c.sha256(APP+'/eboot.bin')==a.sha256
            result=options(c,a.profile,out)
        else:
            idle();identity(c);assert c.sha256(APP+'/eboot.bin')==a.sha256
            result=dict(at=r.utc_now(),response=r.http_text(r.PAYLOAD_MANAGER+'/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf'))
        write(out/'result.json',result);print(json.dumps(result,ensure_ascii=True,indent=2));print(out)
    finally:c.close()
if __name__=='__main__':main()


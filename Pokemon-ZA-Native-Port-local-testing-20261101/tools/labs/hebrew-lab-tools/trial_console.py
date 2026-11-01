"""Scoped, recorded Hebrew preview operations on PPSA91762 only."""
import argparse
import ftplib
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

LAB=Path(__file__).resolve().parents[1]
PROJECT=LAB.parent/'Pokemon-ZA-Native-Port'
sys.path[:0]=[str(PROJECT),str(PROJECT/'port/perf-r24/observer')]
import run_r3 as r
import client

OUT=LAB/'trial/console-r1'
APP='/data/homebrew/PPSA91762'
ROOT='/mnt/sandbox/PPSA91762_000/download0/zarecomp'
OLD='c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153'
CONFIGS=('performance-options.txt','performance-profile.txt','submission-options.txt','slot-depth-options.txt','perf-r24-options.txt','observer-enable.txt')

def write(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(data):return hashlib.sha256(data).hexdigest()
def save(s):write(OUT/'state.json',s)
def load():return json.loads((OUT/'state.json').read_text(encoding='utf-8'))
def emit(obj):print(json.dumps(obj,ensure_ascii=False),flush=True)
def title(c):
    assert json.loads(c.read(APP+'/sce_sys/param.json',16384))['titleId']=='PPSA91762'
    assert c.read('/user/app/PPSA91762/mount.lnk',4096)==APP.encode()
def owned(c,s):
    title(c);ps=r.eboot_processes();assert len(ps)==1 and r.process_pid(ps[0])==s['current']['pid'],ps
    assert client.status(c.ftp)['session']==s['current']['session']
    return s['current']
def mkdir(c,path):
    assert path.startswith(ROOT+'/mods/') or path==ROOT+'/mods'
    parts=path.split('/');cur=''
    for part in parts:
        if not part:continue
        cur+='/'+part
        try:c.ftp.mkd(cur)
        except ftplib.error_perm as ex:
            if not str(ex).startswith('550'):raise
def verify_save(c,s):
    checks=[]
    for f in s['save_files']:
        actual=c.sha256(f['remote']);assert actual==f['sha256'],f['remote']
        checks.append(dict(file=f['remote'],sha256=actual))
    return checks

def launch(c,s,label):
    title(c);assert not r.eboot_processes(),'Console occupied'
    assert c.sha256(APP+'/eboot.bin')==s.get('installed_sha256',OLD)
    try:previous=client.status(c.ftp)['session']
    except ftplib.error_perm:previous=s.get('last_closed',{}).get('session')
    response=r.http_text(r.PAYLOAD_MANAGER+'/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf')
    emit(dict(stage='launch requested',label=label,response=response))
    until=time.monotonic()+85
    while time.monotonic()<until:
        try:
            st=client.status(c.ftp);ps=r.eboot_processes()
            if st['session']!=previous and len(ps)==1:
                cur=dict(pid=r.process_pid(ps[0]),session=st['session'],seq=0,label=label,at=r.utc_now())
                s['current']=cur;s.setdefault('boots',[]).append(cur.copy());save(s)
                emit(dict(stage='fresh observer session',**cur));return
        except (ftplib.error_perm,OSError):pass
        time.sleep(.5)
    raise TimeoutError('Fresh title observer not reached')

def backup(c,s):
    # download0 exposes persisted files as soon as it mounts. The first launch
    # probe can precede observer initialization; bind its eventual live token
    # only while still on our own, first maintenance PID, before any commands.
    ps=r.eboot_processes()
    if not s.get('save_files') and s['current']['label']=='maintenance-r27b':
        assert len(ps)==1 and r.process_pid(ps[0])==s['current']['pid']
        live=client.status(c.ftp)['session']
        if live!=s['current']['session']:
            s['ignored_persisted_startup_session']=s['current']['session']
            s['current']['session']=live;save(s)
    owned(c,s);active=c.read(ROOT+'/rando/active.json',4096);assert active
    run=json.loads(active)['id'];assert __import__('re').fullmatch('[A-Za-z0-9_-]{1,79}',run)
    s['run']=run;s['save_files']=[]
    for name,remote in [('active.json',ROOT+'/rando/active.json'),('report.json',ROOT+'/rando/'+run+'/report.json'),
        ('save/save_0/main',ROOT+'/rando/'+run+'/save/save_0/main'),('cheats.txt',ROOT+'/rando/'+run+'/cheats.txt'),
        ('larecomp.ini',ROOT+'/larecomp.ini')]:
        data=c.read(remote,32<<20)
        if data is None:
            assert name in ('cheats.txt','larecomp.ini');continue
        assert c.read(remote,32<<20)==data
        p=OUT/'save-backup'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        s['save_files'].append(dict(remote=remote,file=str(p.relative_to(OUT)),bytes=len(data),sha256=digest(data)))
    s['configs']={name:c.read(APP+'/'+name,65536).decode() for name in CONFIGS}
    save(s);write(OUT/'save-backup/verification.json',dict(at=r.utc_now(),run=run,files=s['save_files'],double_read=True))
    emit(dict(stage='fresh current save/config backup complete',run=run,files=len(s['save_files'])))

def stage(c,s):
    owned(c,s);verify_save(c,s)
    local=LAB/'trial/assets/mods/000-hebrew-trial'
    manifest=json.loads((local/'trial-manifest.json').read_text(encoding='utf-8'))
    try:names=c.listing(ROOT+'/mods')
    except ftplib.error_perm:names=[]
    assert not any('000-hebrew-trial' in x for x in names),names
    enabled=[n for n in names if not n.startswith(('_','.'))]
    assert len(enabled)<15,'Mod layer capacity reached'
    collisions=[]
    for item in manifest['files']:
        rel=item['path']
        for prefix in [ROOT+'/rando/'+s['run']]+[ROOT+'/mods/'+n for n in enabled]:
            if c.sha256(prefix+'/'+rel) is not None:collisions.append(prefix+'/'+rel)
    assert not collisions,collisions
    remote=ROOT+'/mods/_000-hebrew-trial-stage-r1';mkdir(c,remote)
    files=[]
    for p in sorted(local.rglob('*')):
        if not p.is_file():continue
        path=remote+'/'+p.relative_to(local).as_posix();mkdir(c,path.rsplit('/',1)[0]);data=p.read_bytes()
        c.store(path,data);assert c.sha256(path)==digest(data)
        files.append(dict(path=p.relative_to(local).as_posix(),bytes=len(data),sha256=digest(data)))
    owned(c,s);verify_save(c,s)
    final=ROOT+'/mods/000-hebrew-trial';c.ftp.rename(remote,final)
    for f in files:assert c.sha256(final+'/'+f['path'])==f['sha256']
    s['mod_files']=files;s['mod_enabled']=True;save(s)
    write(OUT/'mod-installation.json',dict(at=r.utc_now(),files=files,seed_mod_conflicts=collisions,enabled=True,readback=True))
    emit(dict(stage='trial mod published and final readbacks verified',files=len(files)))

def close(c,s):
    cur=owned(c,s);checks=verify_save(c,s)
    reply=r.http_json('/process_kill?pid='+str(cur['pid']))
    until=time.monotonic()+15
    while r.eboot_processes():
        assert time.monotonic()<until;time.sleep(.3)
    s['last_closed']=dict(**cur,response=reply,save_check=checks);del s['current'];save(s)
    emit(dict(stage='owned title closed; save unchanged',pid=cur['pid']))

def stage_app(c,s):
    title(c);assert not r.eboot_processes()
    local=LAB/'trial/assets/mods/000-hebrew-trial'
    stage=APP+'/.hebrew-trial-assets-r1-stage';final=APP+'/hebrew-trial-assets-r1'
    assert 'hebrew-trial-assets-r1' not in c.listing(APP)
    def folder(path):
        assert path==stage or path.startswith(stage+'/')
        tail=path[len(APP)+1:];cur=APP
        for part in tail.split('/'):
            cur+='/'+part
            try:c.ftp.mkd(cur)
            except ftplib.error_perm as error:
                if not str(error).startswith('550'):raise
            # Verify the directory exists; never suppress a genuine permission error.
            c.ftp.cwd(cur);c.ftp.cwd('/');c.chmod(cur,'755')
    files=[]
    for p in sorted(local.rglob('*')):
        if not p.is_file():continue
        remote=stage+'/'+p.relative_to(local).as_posix();folder(remote.rsplit('/',1)[0]);data=p.read_bytes()
        old=c.sha256(remote)
        if old is not None:assert old==digest(data),'Different staged file; preserve and inspect'
        else:c.store(remote,data)
        c.chmod(remote,'644');assert c.sha256(remote)==digest(data)
        files.append(dict(path=p.relative_to(local).as_posix(),bytes=len(data),sha256=digest(data)))
    assert not r.eboot_processes();c.ftp.rename(stage,final)
    for f in files:assert c.sha256(final+'/'+f['path'])==f['sha256']
    s['staged_app_assets']=dict(root=final,files=files);save(s)
    write(OUT/'app-assets-staged.json',dict(at=r.utc_now(),root=final,files=files,readback=True))
    emit(dict(stage='app-side assets staged and readback verified; native install pending',files=len(files)))

def install(c,s):
    assert not r.eboot_processes();title(c)
    binary=LAB/'trial/build-r5/eboot.bin';data=binary.read_bytes();wanted=digest(data)
    for name in ('hebrew_trial.cpp','hebrew_install.cpp','hebrew_io.h'):
        assert digest((binary.parent/'src'/name).read_bytes())==digest((LAB/'trial/src'/name).read_bytes()),'Source changed after build snapshot'
    previous=s.get('installed_sha256',OLD)
    assert c.sha256(APP+'/eboot.bin')==previous
    old=PROJECT/'artifacts/randomizer-r27b-play/PPSA91762/eboot.bin'
    assert digest(old.read_bytes())==OLD
    original=OUT/'original/eboot.bin';original.parent.mkdir(exist_ok=True)
    if original.exists():assert digest(original.read_bytes())==OLD
    else:shutil.copyfile(old,original)
    # Back up the exact console-matched original before replacing anything.
    nas=Path(r'\\TheOnePiece\Software\PS5-13.60\Hebrew-Trial-20261029-r1')
    for p in [original]+list((OUT/'save-backup').rglob('*')):
        if not p.is_file():continue
        target=nas/'console-backup'/p.relative_to(OUT);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert digest(target.read_bytes())==digest(p.read_bytes())
        else:shutil.copyfile(p,target)
        assert digest(target.read_bytes())==digest(p.read_bytes())
    stage=APP+'/eboot.bin.hebrew-trial-r1.new'
    staged=c.sha256(stage)
    if staged is not None and staged!=wanted:c.ftp.rename(stage,stage+'.retained-'+staged[:12])
    if staged!=wanted:c.store(stage,data)
    c.chmod(stage,'755');assert c.sha256(stage)==wanted
    assert not r.eboot_processes();title(c);assert c.sha256(APP+'/eboot.bin')==previous
    prior=APP+('/eboot.bin.before-hebrew-trial-r1' if previous==OLD else '/eboot.bin.before-hebrew-trial-'+binary.parent.name)
    assert c.sha256(prior) is None
    c.ftp.rename(APP+'/eboot.bin',prior)
    try:c.ftp.rename(stage,APP+'/eboot.bin')
    except Exception:c.ftp.rename(prior,APP+'/eboot.bin');raise
    assert c.sha256(APP+'/eboot.bin')==wanted
    for name,text in s['configs'].items():assert c.read(APP+'/'+name,65536)==text.encode()
    s['installed_sha256']=wanted;s.setdefault('original_eboot_remote',prior)
    transaction=dict(at=r.utc_now(),previous_sha256=previous,original_sha256=OLD,new_sha256=wanted,backup=prior,configs_unchanged=True,readback=True)
    s.setdefault('binary_transactions',[]).append(transaction);save(s)
    write(OUT/('binary-installation-'+binary.parent.name+'.json'),transaction)
    emit(dict(stage='r27b Hebrew menu installed',sha256=wanted))

def command(c,s,op,arg=None,frames=None):
    cur=owned(c,s);cur['seq']+=1;save(s)
    out=OUT/cur['label']/('command-'+str(cur['seq']));out.mkdir(parents=True)
    client.issue(c.ftp,cur['session'],cur['seq'],op,arg,frames)
    until=time.monotonic()+25
    while time.monotonic()<until:
        try:
            rec=client.collect(c.ftp,cur['session'],cur['seq'],out)
            write(out/'receipt.json',rec);emit(rec);return
        except ftplib.error_perm:time.sleep(.3)
    raise TimeoutError('Observer command receipt missing')

def restarted(c,s):
    previous=s['current'];until=time.monotonic()+85
    while time.monotonic()<until:
        try:
            st=client.status(c.ftp);ps=r.eboot_processes()
            if st['session']!=previous['session'] and len(ps)==1 and r.process_pid(ps[0])!=previous['pid']:
                cur=dict(pid=r.process_pid(ps[0]),session=st['session'],seq=0,label='relaunch-'+str(len(s['boots'])),at=r.utc_now())
                s['current']=cur;s['boots'].append(cur.copy());save(s);verify_save(c,s)
                emit(dict(stage='cold relaunch confirmed',previous=previous,current=cur));return
        except (OSError,ftplib.error_perm):pass
        time.sleep(.5)
    raise TimeoutError('Expected cold relaunch was not observed')

def verify_mod(c,s):
    owned(c,s);raw=c.read(ROOT+'/hebrew-trial-install-r1.json',32768);assert raw
    receipt=json.loads(raw);write(OUT/'native-install-receipt.json',receipt)
    assert receipt['result']==1,receipt
    folder=ROOT+'/mods/'+('_000-hebrew-trial' if receipt['existing_disabled'] else '000-hebrew-trial')
    checks=[]
    for item in s['staged_app_assets']['files']:
        actual=c.sha256(folder+'/'+item['path']);assert actual==item['sha256'],item['path']
        checks.append(dict(file=item['path'],sha256=actual))
    verify_save(c,s);s['native_mod_verified']=True;s['mod_enabled']=not receipt['existing_disabled'];save(s)
    write(OUT/'native-mod-readback.json',dict(at=r.utc_now(),root=folder,files=checks,save_unchanged=True))
    emit(dict(stage='native install and all remote mod hashes verified',enabled=s['mod_enabled'],files=len(checks)))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('op',choices=('launch','backup','stage','stage-app','close','install','continue','snapshot','input','restarted','verify','verify-mod','inspect'))
    parser.add_argument('--label',default='maintenance');parser.add_argument('--button');parser.add_argument('--frames',type=int,default=1)
    a=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    s=load() if (OUT/'state.json').exists() else dict(created_utc=r.utc_now(),boots=[])
    c=r.Console()
    try:
        if a.op=='launch':launch(c,s,a.label)
        elif a.op=='backup':backup(c,s)
        elif a.op=='stage':stage(c,s)
        elif a.op=='stage-app':stage_app(c,s)
        elif a.op=='close':close(c,s)
        elif a.op=='install':install(c,s)
        elif a.op=='continue':command(c,s,'continue',s['run'])
        elif a.op=='snapshot':command(c,s,'snapshot')
        elif a.op=='input':command(c,s,'input',a.button,a.frames)
        elif a.op=='restarted':restarted(c,s)
        elif a.op=='verify':emit(dict(save_check=verify_save(c,s),current=owned(c,s)))
        elif a.op=='verify-mod':verify_mod(c,s)
        elif a.op=='inspect':
            for p in [ROOT,ROOT+'/mods',ROOT+'/mods/_000-hebrew-trial-stage-r1',ROOT+'/mods/_000-hebrew-trial-stage-r1/licenses']:
                try:emit(dict(path=p,names=c.listing(p)))
                except ftplib.error_perm as error:emit(dict(path=p,error=str(error)))
    finally:c.close()

if __name__=='__main__':main()

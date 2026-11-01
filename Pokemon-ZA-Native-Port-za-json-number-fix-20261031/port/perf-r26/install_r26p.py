"""Transactional PPSA91762 r26p install. Never writes game saves or PPSA91761."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'port/perf-r25'))
import hardware_r25 as hw
h=hw.h
OLD='35ee54dacd03b217a30f9e18b7e57f8117a880b859013dee7b005da44b6d573e'
NEW='1e1a58ac19d7ba80f654877562d78586f81c3f7750502db5f5df9f36c7dd493b'
SOURCE=ROOT/'artifacts/randomizer-r26p-play/PPSA91762'
CHANGED=('eboot.bin','perf-r24-options.txt','slot-depth-options.txt')

def emit(x):print(json.dumps(x,ensure_ascii=False),flush=True)
def readstate():return json.loads((h.OUT/'state.json').read_text(encoding='utf-8'))
def save(s):h.write(h.OUT/'state.json',s)
def nas_copy(path):
    def digest_file(p):
        with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
    expected=digest_file(path);dest=hw.NAS/path.relative_to(h.OUT)
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and digest_file(dest)!=expected:
        dest=dest.with_name(dest.stem+'-'+expected[:12]+dest.suffix)
    if not dest.exists():shutil.copyfile(path,dest)
    assert digest_file(dest)==expected,str(dest)
    return dest
def rawlog(s):return hw.rawbootlog(s)

def init(c):
    h.idle();h.title(c);assert not (h.OUT/'state.json').exists()
    assert hw.digest((SOURCE/'eboot.bin').read_bytes())==NEW
    cfg={n:c.read(h.APP+'/'+n,4096) for n in (*h.CONFIGS,'perf-r24-options.txt')}
    assert cfg['performance-options.txt']==b'optimized\n'
    assert cfg['slot-depth-options.txt']==b'16\n'
    assert cfg['perf-r24-options.txt']==b'vkprof=0\nticks=tsc\nscale=1\n'
    original=c.read(h.APP+'/eboot.bin',512<<20);assert hw.digest(original)==OLD
    assert c.sha256(h.APP+'/eboot.bin')==OLD
    dest=h.OUT/'original';dest.mkdir()
    (dest/'eboot.bin').write_bytes(original)
    for n,b in cfg.items():
        if b is not None:(dest/n).write_bytes(b)
    s=dict(at=h.r.utc_now(),initial_eboot_sha256=OLD,initial_configs={n:None if b is None else b.decode() for n,b in cfg.items()},
           original_files={n:None if b is None else dict(bytes=len(b),sha256=hw.digest(b)) for n,b in cfg.items()},
           requested_sha256=NEW,boots=[],phases=[],nas=str(hw.NAS))
    save(s)
    for f in dest.iterdir():nas_copy(f)
    emit(dict(stage='original executable/configs backed up and NAS SHA256 verified',out=str(h.OUT)))
    hw.launch(c,s,'original-save-backup')
    cur=h.owned(c,s);extras={}
    for name,remote in [('active.json',h.DATA+'/active.json'),('cheats.txt',h.DATA+'/'+cur['run']+'/cheats.txt')]:
        b=c.read(remote,65536);extras[name]=None if b is None else dict(bytes=len(b),sha256=hw.digest(b))
        if b is not None:
            f=h.OUT/'save-backup'/name;f.write_bytes(b);assert c.read(remote,65536)==b;nas_copy(f)
    s['save_extras']=extras;save(s);h.write(h.OUT/'save-backup/extras.json',extras);nas_copy(h.OUT/'save-backup/extras.json')
    hw.close(c,s)
    emit(dict(stage='latest active save backed up; original closed',run=cur['run']))

def replace(c,name,data,expected_old,tag):
    h.idle();h.title(c)
    target=h.APP+'/'+name;wanted=hw.digest(data);actual=c.sha256(target)
    assert actual==expected_old,dict(name=name,actual=actual,expected=expected_old)
    stage=target+'.new';staged=c.sha256(stage)
    if staged is not None and staged!=wanted:
        c.ftp.rename(stage,stage+'.retained-'+tag)
        staged=None
    if staged!=wanted:c.store(stage,data)
    if name=='eboot.bin':c.chmod(stage,'755')
    assert c.sha256(stage)==wanted
    h.idle();h.title(c);assert c.sha256(target)==expected_old
    previous=target+'.before-r26p-'+tag
    c.ftp.rename(target,previous)
    try:c.ftp.rename(stage,target)
    except Exception:c.ftp.rename(previous,target);raise
    assert c.sha256(target)==wanted
    return dict(file=name,old_sha256=expected_old,new_sha256=wanted,remote_backup=previous,stage_readback_verified=True,final_readback_verified=True)

def launch_new(c,s):
    h.idle();h.title(c);assert c.sha256(h.APP+'/eboot.bin')==NEW
    out=h.OUT/'r26p-first-boot';out.mkdir(exist_ok=False)
    try:prior=h.client.status(c.ftp)['session']
    except h.ftplib.error_perm:prior=None
    offset=(h.OUT/'all.klog.log').stat().st_size
    h.idle()
    response=h.r.http_text(h.r.PAYLOAD_MANAGER+'/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf')
    emit(dict(stage='r26p launched',response=response))
    deadline=time.monotonic()+85;last=None;stable=0
    while time.monotonic()<deadline:
        try:
            st=h.client.status(c.ftp);ps=h.r.eboot_processes();active=c.read(h.DATA+'/active.json',4096)
            log=(h.OUT/'all.klog.log').read_bytes()[offset:]
            if len(ps)==1 and active and st['session']!=prior and b'main reached' in log:
                sid=st['session'];stable=stable+1 if sid==last else 0;last=sid
                if stable>=2:break
        except h.ftplib.error_perm:pass
        time.sleep(.5)
    else:raise RuntimeError('New title did not reach stable observer')
    cur=dict(label='r26p-first-boot',pid=h.r.process_pid(ps[0]),session=sid,run=json.loads(active)['id'],sha256=NEW,
             seq=0,klog_offset=offset,at=h.r.utc_now(),options=(SOURCE/'perf-r24-options.txt').read_text(),backup_verified=True)
    s['current']=cur;s['boots'].append(cur.copy());save(s);h.write(out/'identity.json',cur);h.verify_save(c,s);hw.guard(s)

def install(c,s):
    h.idle();h.title(c);assert 'current' not in s
    assert (h.OUT/'save-backup/verification.json').exists()
    assert hw.digest((SOURCE/'eboot.bin').read_bytes())==NEW
    for n in h.CONFIGS:
        assert c.read(h.APP+'/'+n,4096)==s['initial_configs'][n].encode(),n
    assert c.read(h.APP+'/perf-r24-options.txt',4096)==s['initial_configs']['perf-r24-options.txt'].encode()
    s['transaction_started_at']=h.r.utc_now();save(s);receipts=[];tag=h.r.stamp()
    for n in CHANGED:
        data=(SOURCE/n).read_bytes()
        old=OLD if n=='eboot.bin' else hw.digest((h.OUT/'original'/n).read_bytes())
        receipts.append(replace(c,n,data,old,tag));s['replacements']=receipts;save(s)
        emit(dict(stage='installed and readback verified',file=n,sha256=hw.digest(data)))
    h.write(h.OUT/'transaction.json',dict(at=h.r.utc_now(),files=receipts,only_files=list(CHANGED)))
    for n in h.CONFIGS:
        expected=(SOURCE/n).read_bytes() if n=='slot-depth-options.txt' else s['initial_configs'][n].encode()
        assert c.read(h.APP+'/'+n,4096)==expected,n
    launch_new(c,s)

def startup(s):
    hw.save_bootlogs(s);log=hw.bootlog(s)
    assert '[za-r26p] fps=1' in log
    assert '[za-r25] submit=thread requested' in log and '[za-r25] submission: thread' in log
    assert 'renderer CPU profile (LARECOMP_VK_PROF): off' in log
    assert '[post] 1920x1080 fsr1 -> 3840x2160' in log
    assert not re.search(r'\[za-r24-options\] force60=1',log)
    slots=re.findall(r'\[za-r23-slots\] active=(\d+)',log);assert slots and int(slots[-1]) in (8,64)
    assert re.search(r'\[za-cheats\].*fps_counter=1',log)
    notes=[l for l in log.splitlines() if re.search(r'\[za-r26p\]|\[za-r25\]|\[za-r25-clock\]|\[za-r26\]|\[za-r24-options\]|\[za-cheats\]',l)]
    rec=dict(at=h.r.utc_now(),effective_slots=int(slots[-1]),fps_counter_setting_on=True,force60_off=True,notes=notes)
    h.write(h.OUT/'startup-verification.json',rec);emit(dict(stage='startup settings verified',effective_slots=int(slots[-1]),fps_counter_on=True))

def ready(c,s):
    cur=h.owned(c,s);out=h.OUT/cur['label'];h.verify_save(c,s)
    h.command(c,s,out,'continue',cur['run'],expected={'continue_requested'});emit(dict(stage='waiting for title screen'));hw.pause(s,12)
    h.command(c,s,out,'input','A',1,expected={'input_armed'});emit(dict(stage='loading current save and warming shaders'));hw.pause(s,35)
    cur['loaded']=True;save(s);hw.snapshot(c,s,'ready');startup(s)

def measure(c,s):
    cur=h.owned(c,s);assert cur['loaded'];out=h.OUT/'r26p-first-boot/30fps-check';out.mkdir(exist_ok=False)
    hw.pause(s,10,True);before=hw.snapshot(c,s,'before-30fps-check')
    seq=cur['seq']+1;cur['seq']=seq;save(s);h.client.issue(c.ftp,cur['session'],seq,'measure',20)
    emit(dict(stage='checking 30 FPS for 20 seconds',seq=seq));hw.pause(s,23,True)
    rec=h.collect(c,cur['session'],seq,out,{'complete'});h.owned(c,s);hw.pause(s,2.5,True)
    timing=json.loads((out/(Path(rec['files'][0]['name']).stem+'-analysis.json')).read_text())
    assert timing['fps_modes']==[0] and not timing['capture_inside_window']
    fps=timing['all_intervals']['interval_rate_fps'];assert round(fps,2)==30.00,dict(reason='30-FPS acceptance failed',fps=fps)
    after=hw.snapshot(c,s,'after-30fps-check');hw.save_bootlogs(s)
    result=dict(at=h.r.utc_now(),fps=fps,timing=timing,receipt=rec,before=before,after=after,save_check=h.verify_save(c,s),passed=True)
    h.write(h.OUT/'30fps-verification.json',result);s['smoke_test_passed']=True;save(s);emit(dict(stage='30-FPS check passed',fps=fps,save_unchanged=True))

def rollback(c,s,reason):
    ps=h.r.eboot_processes()
    if ps:
        cur=h.owned(c,s);h.verify_save(c,s)
        h.r.http_json('/process_kill?pid='+str(cur['pid']))
        until=time.monotonic()+15
        while h.r.eboot_processes():assert time.monotonic()<until;time.sleep(.5)
        hw.save_bootlogs(s)
    s.pop('current',None);save(s);h.idle();h.title(c);receipts=[]
    for n in CHANGED:
        target=h.APP+'/'+n;want=(h.OUT/'original'/n).read_bytes();actual=c.sha256(target)
        if actual!=hw.digest(want):receipts.append(replace(c,n,want,actual,'rollback-'+h.r.stamp()))
        assert c.sha256(target)==hw.digest(want)
    s['rolled_back']=True;save(s);h.write(h.OUT/'rollback.json',dict(at=h.r.utc_now(),reason=reason,files=receipts,verified=True,save_never_restored=True))
    emit(dict(stage='rolled back and verified',reason=reason))

def complete(c,s):
    assert s['smoke_test_passed'] and not s.get('rolled_back');h.owned(c,s)
    review=json.loads((h.OUT/'visual-review.json').read_text(encoding='utf-8'))
    assert review['fps_counter_visible'] and review['no_obvious_corruption']
    assert c.sha256(h.APP+'/eboot.bin')==NEW
    actual={n:c.read(h.APP+'/'+n,4096) for n in (*h.CONFIGS,'perf-r24-options.txt')}
    for n,b in actual.items():assert b==((SOURCE/n).read_bytes() if n in CHANGED else s['initial_configs'][n].encode()),n
    assert c.read(hw.INI,65536)==(None if s['initial_ini'] is None else s['initial_ini'].encode())
    checks=h.verify_save(c,s);startup(s)
    final=dict(at=h.r.utc_now(),installed_sha256=NEW,installed=True,only_replaced=list(CHANGED),
               save_unchanged=True,save_check=checks,ini_unchanged=True,other_options_unchanged=True,
               fps_counter_visible=True,visual_review=review,application_running=True,
               smoke_test=json.loads((h.OUT/'30fps-verification.json').read_text()),nas=str(hw.NAS))
    h.write(h.OUT/'installation.json',final)
    for n in CHANGED:
        path=h.OUT/'installed/PPSA91762'/n;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/n,path);nas_copy(path)
    (h.OUT/'INSTALLATION-HE.txt').write_text('r26p-play הותקנה בהצלחה ב-PPSA91762.\nמונה FPS אומת חזותית בפינה. מצב 30 אומת במדידה של 20 שניות: '+f"{final['smoke_test']['fps']:.5f} FPS.\n"+
        'הוחלפו רק eboot.bin, perf-r24-options.txt ו-slot-depth-options.txt. השמירה ו-larecomp.ini לא השתנו.\nהמשחק נשאר פתוח ומוכן לשימוש.\n'+
        'SHA-256: '+NEW+'\nNAS: '+str(hw.NAS)+'\n',encoding='utf-8')
    for name in ('installation.json','INSTALLATION-HE.txt','transaction.json','startup-verification.json','30fps-verification.json','visual-review.json'):
        nas_copy(h.OUT/name)
    for f in (h.OUT/'r26p-first-boot').rglob('*'):
        if f.is_file() and f.suffix in ('.png','.csv','.json','.log'):nas_copy(f)
    s['installation_complete']=True;save(s);nas_copy(h.OUT/'state.json')
    emit(dict(stage='installation complete; NAS SHA256 verified',sha256=NEW,nas=str(hw.NAS),application_running=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('op',choices=('log','init','install','ready','measure','complete','rollback'));p.add_argument('--reason',default='Requested rollback')
    a=p.parse_args();h.OUT=a.out.resolve();h.OUT.mkdir(parents=True,exist_ok=True);hw.NAS=Path(r'\\TheOnePiece\Software\PS5-13.60')/h.OUT.name
    if a.op=='log':hw.logger(h.OUT);raise SystemExit
    c=h.r.Console()
    try:
        if a.op=='init':init(c)
        else:
            s=readstate()
            if a.op=='install':install(c,s)
            elif a.op=='ready':ready(c,s)
            elif a.op=='measure':measure(c,s)
            elif a.op=='complete':complete(c,s)
            elif a.op=='rollback':rollback(c,s,a.reason)
    except Exception as e:
        h.write(h.OUT/('error-'+h.r.stamp()+'.json'),dict(at=h.r.utc_now(),op=a.op,type=type(e).__name__,error=str(e)))
        if (h.OUT/'state.json').exists():
            s=readstate()
            if s.get('transaction_started_at') and not s.get('installation_complete') and a.op not in ('complete','rollback'):
                rollback(c,s,str(e))
        raise
    finally:c.close()

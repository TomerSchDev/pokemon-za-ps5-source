"""Restore the missing FPS TRIAL control, updating only PPSA91762/eboot.bin while idle."""
import argparse
import json
from pathlib import Path
import shutil
import install_r26p as i
h=i.h
i.OLD='1e1a58ac19d7ba80f654877562d78586f81c3f7750502db5f5df9f36c7dd493b'
i.NEW='c382275b90704d50e50e57875116bd69341e6c6b9c9c4e4d43223b367e19f7fa'
i.SOURCE=i.ROOT/'artifacts/randomizer-r26p1-play/PPSA91762'
i.CHANGED=('eboot.bin',)
base_startup=i.startup

def startup(s):
    base_startup(s)
    assert 'FPS TRIAL restored (r26p1)' in i.hw.bootlog(s)
i.startup=startup

def init(c):
    h.idle();h.title(c);assert not (h.OUT/'state.json').exists()
    assert i.hw.digest((i.SOURCE/'eboot.bin').read_bytes())==i.NEW
    configs={n:c.read(h.APP+'/'+n,4096) for n in (*h.CONFIGS,'perf-r24-options.txt')}
    assert configs['performance-options.txt']==b'optimized\n'
    assert all(b is not None for b in configs.values())
    original=c.read(h.APP+'/eboot.bin',512<<20)
    assert i.hw.digest(original)==i.OLD and c.sha256(h.APP+'/eboot.bin')==i.OLD
    dest=h.OUT/'original';dest.mkdir()
    (dest/'eboot.bin').write_bytes(original)
    for name,data in configs.items():(dest/name).write_bytes(data)
    s=dict(at=h.r.utc_now(),initial_eboot_sha256=i.OLD,requested_sha256=i.NEW,
           initial_configs={n:b.decode() for n,b in configs.items()},boots=[],phases=[],nas=str(i.hw.NAS))
    i.save(s)
    for f in dest.iterdir():i.nas_copy(f)
    i.emit(dict(stage='r26p executable and current options backed up and NAS hashes verified'))
    i.hw.launch(c,s,'latest-save-backup')
    cur=h.owned(c,s);extras={}
    for name,remote in [('active.json',h.DATA+'/active.json'),('cheats.txt',h.DATA+'/'+cur['run']+'/cheats.txt')]:
        data=c.read(remote,65536)
        extras[name]=None if data is None else dict(bytes=len(data),sha256=i.hw.digest(data))
        if data is not None:
            assert c.read(remote,65536)==data
            f=h.OUT/'save-backup'/name;f.write_bytes(data);i.nas_copy(f)
    s['save_extras']=extras;i.save(s);h.write(h.OUT/'save-backup/extras.json',extras);i.nas_copy(h.OUT/'save-backup/extras.json')
    i.hw.close(c,s)
    i.emit(dict(stage='latest save backed up; original closed; ready for binary-only update',run=cur['run']))

def trial(c,s):
    h.verify_save(c,s);out=h.OUT/'r26p-first-boot/60-trial-check';out.mkdir(exist_ok=False)
    try:
        request=h.command(c,s,out,'fps',1,expected={'requested'})
        i.hw.pause(s,1,True)
        rec=h.command(c,s,out,'measure',4,expected={'complete'})
        timing=json.loads((out/(Path(rec['files'][0]['name']).stem+'-analysis.json')).read_text())
        assert 1 in timing['fps_modes'] and not timing['capture_inside_window'],timing
        assert 'user armed static 60 trial' in i.hw.bootlog(s)
    finally:
        restore=h.command(c,s,out,'fps',0,expected={'requested'});i.hw.pause(s,2,True)
    assert 'user restored original frame mode' in i.hw.bootlog(s)
    s['trial_api_verified']=True;i.save(s)
    h.write(h.OUT/'60-trial-verification.json',dict(at=h.r.utc_now(),request=request,receipt=rec,timing=timing,restore=restore,
        passed=True,restored_to_30=True,scope='Hardware observer exercised the existing trial API. The menu call into that API was verified by host tests and linked-image disassembly.'))
    i.emit(dict(stage='60 trial API verified on console; restored 30',fps=timing['all_intervals']['interval_rate_fps']))

def complete(c,s):
    h.owned(c,s);assert s['smoke_test_passed'] and s['trial_api_verified'] and not s.get('rolled_back')
    assert c.sha256(h.APP+'/eboot.bin')==i.NEW
    for name,text in s['initial_configs'].items():assert c.read(h.APP+'/'+name,4096)==text.encode(),name
    assert c.read(i.hw.INI,65536)==(None if s['initial_ini'] is None else s['initial_ini'].encode())
    for name,remote in [('active.json',h.DATA+'/active.json'),('cheats.txt',h.DATA+'/'+s['current']['run']+'/cheats.txt')]:
        data=c.read(remote,65536);expected=s['save_extras'][name]
        assert (None if data is None else i.hw.digest(data))==(None if expected is None else expected['sha256']),name
    checks=h.verify_save(c,s);startup(s)
    smoke=json.loads((h.OUT/'30fps-verification.json').read_text())
    result=dict(at=h.r.utc_now(),installed=True,version='r26p1-play',installed_sha256=i.NEW,only_replaced=['eboot.bin'],
        save_unchanged=True,save_check=checks,configs_unchanged=True,ini_unchanged=True,active_run_and_cheats_unchanged=True,
        fps_trial_menu_link_verified=True,menu_controller_tests_passed=True,hardware_trial_api_verified=True,
        final_display_menu_visual_confirmation='pending_user',smoke_test=smoke,application_running=True,startup_mode=30,nas=str(i.hw.NAS))
    h.write(h.OUT/'installation.json',result)
    (h.OUT/'INSTALLATION-HE.txt').write_text('r26p1-play הותקנה: תיקון שורת FPS TRIAL החסרה.\nהוחלף רק eboot.bin, עם SHA-256 לפני ואחרי ההחלפה.\nהשמירה העדכנית, הריצה, הצ׳יטים, קובצי האפשרויות ו-larecomp.ini נשארו ללא שינוי.\nבדיקת 20 שניות במצב 30: '+f"{smoke['fps']:.5f} FPS.\n"+
        'ניסיון 60 וחזרה ל-30 אומתו בממשק האבחון של הקונסולה. חיבור התפריט אומת בבדיקות ובדיסאסמבלי.\nהמשחק פתוח במצב 30. L3+R3 > FPS TRIAL > X מפעיל ניסיון 60, ו-X נוסף מחזיר ל-30.\nאם אין 60 יציב, מנגנון r16 הקיים חוזר ל-30; אפשר לנסות שוב באותה שורה.\nמיקום השורה בתצוגת הטלוויזיה ממתין לאישור המשתמש.\nNAS: '+str(i.hw.NAS)+'\n',encoding='utf-8')
    dst=h.OUT/'installed/PPSA91762/eboot.bin';dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(i.SOURCE/'eboot.bin',dst);i.nas_copy(dst)
    for name in ('installation.json','INSTALLATION-HE.txt','transaction.json','startup-verification.json','30fps-verification.json','60-trial-verification.json'):
        i.nas_copy(h.OUT/name)
    for f in (h.OUT/'r26p-first-boot').rglob('*'):
        if f.is_file() and f.suffix in ('.json','.log','.csv','.png'):i.nas_copy(f)
    s['installation_complete']=True;i.save(s);i.nas_copy(h.OUT/'state.json')
    i.emit(dict(stage='r26p1 installed and NAS copies SHA256 verified',game_running=True,startup_mode=30))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('op',choices=('log','init','install','ready','measure','trial','complete','rollback'))
    p.add_argument('--reason',default='Requested rollback');a=p.parse_args()
    h.OUT=a.out.resolve();h.OUT.mkdir(parents=True,exist_ok=True);i.hw.NAS=Path(r'\\TheOnePiece\Software\PS5-13.60')/h.OUT.name
    if a.op=='log':i.hw.logger(h.OUT);raise SystemExit
    c=h.r.Console()
    try:
        if a.op=='init':init(c)
        else:
            s=i.readstate()
            if a.op=='install':i.install(c,s)
            elif a.op=='ready':i.ready(c,s)
            elif a.op=='measure':i.measure(c,s)
            elif a.op=='trial':trial(c,s)
            elif a.op=='complete':complete(c,s)
            elif a.op=='rollback':i.rollback(c,s,a.reason)
    except Exception as e:
        h.write(h.OUT/('error-'+h.r.stamp()+'.json'),dict(at=h.r.utc_now(),op=a.op,type=type(e).__name__,error=str(e)))
        if (h.OUT/'state.json').exists():
            s=i.readstate()
            if s.get('transaction_started_at') and not s.get('installation_complete') and a.op not in ('complete','rollback'):
                i.rollback(c,s,str(e))
        raise
    finally:c.close()

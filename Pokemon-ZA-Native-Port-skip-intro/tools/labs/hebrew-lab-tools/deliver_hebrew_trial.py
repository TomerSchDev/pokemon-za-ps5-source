"""Final scoped trial package: installed binary, pinned assets, sources and evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

LAB=Path(__file__).resolve().parents[1]
TRIAL=LAB/'trial';BUILD=TRIAL/'build-r5';CONSOLE=TRIAL/'console-r1'
NAME='Hebrew-Trial-20261029-r1'
DEST=LAB/'deliverables'/NAME
NAS=Path(r'\\TheOnePiece\Software\PS5-13.60')/NAME

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def copy(p,target):target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)

def main():
    if DEST.exists():raise FileExistsError('Keep existing final revision')
    state=json.loads((CONSOLE/'state.json').read_text(encoding='utf-8'))
    assert state['installed_sha256']==sha(BUILD/'eboot.bin')=='cd1eb5f6044ab99d56161c6009d6d0972df475d269c0522dee650fab31d4f618'
    log=(CONSOLE/'hardware.klog.log').read_text(encoding='utf-8',errors='replace')
    assert '[za-hebrew-install] installed_verified result=1 reason=none files=20' in log
    assert '[za-hebrew-trial] installer ready; mode=1' in log
    assert '[fs] mod: 000-hebrew-trial' in log
    # Never infer physical controller acceptance from a simulated menu test.
    manual=state.get('manual_button_verification',dict(status='pending_user',cold_relaunch_exercised=False))
    report=dict(created_utc=datetime.now(timezone.utc).isoformat(),title='PPSA91762',
        installed=True,eboot_sha256=state['installed_sha256'],base='r27b-play',
        base_sha256='c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153',
        source_assets_ftp_readback_verified=True,native_destination_sha256_readback_files=20,
        destination_ftp_readback=False,destination_ftp_limitation='Private native files deny external FTP reads; native installer verifies every source/destination SHA-256 and receipt readback.',
        ps5_visual_review=dict(passed=True,screens=['world','Hebrew main menu'],
            visible=['תפריט','קופסאות','תיק','פוקידקס','שמירת התקדמות','עזרה והגדרות']),
        manual_button_verification=manual,host_tests=dict(controller=28,metadata_helper=23,installer=25,menu_assertions=623),
        save_main_sha256='80dac662c5d9f7f9983bee85f0d1a73f7a246c79bfa6067ddc6c5e093b09417c',
        same_current_run=state['run'],no_save_restore=True,protected_title_untouched='PPSA91761',
        translation_scope='60 exact existing PoC strings plus headings-r5; full glossary review remains pending')
    payload=DEST/'package';payload.mkdir(parents=True)
    copy(BUILD/'eboot.bin',payload/'PPSA91762/eboot.bin')
    shutil.copytree(TRIAL/'assets/mods/000-hebrew-trial',payload/'PPSA91762/hebrew-trial-assets-r1')
    shutil.copytree(BUILD/'src',payload/'source/trial/src')
    copy(TRIAL/'build-r1.sh',payload/'source/trial/build-r1.sh')
    copy(TRIAL/'runtime-inputs.mk',payload/'source/trial/runtime-inputs.mk')
    copy(LAB/'tools/trial_console.py',payload/'source/tools/trial_console.py')
    evidence=payload/'evidence';evidence.mkdir()
    latest=('menu-host-verification.json','menu-host-tests-final.log','controller-host-tests-r5.log',
            'io-host-tests-r5.log','installer-r5-verification.json','installer-r5-host-results.log')
    for name in latest:copy(TRIAL/'tests'/name,evidence/'host-tests'/name)
    for p in (TRIAL/'tests').glob('*'):
        if p.is_file() and p.suffix in ('.cpp','.sh'):copy(p,payload/'source/trial/tests'/p.name)
    for name in ('registration.json','image-preservation.json','imports-added.txt','imports-removed.txt','source-SHA256SUMS.txt','SHA256SUMS.txt'):
        copy(BUILD/'evidence'/name,evidence/'build'/name)
    copy(CONSOLE/'app-assets-staged.json',evidence/'app-assets-staged.json')
    copy(CONSOLE/'binary-installation-build-r5.json',evidence/'binary-installation.json')
    for command,name in [('command-3','PS5-world.png'),('command-5','PS5-Hebrew-menu.png')]:
        paths=list((CONSOLE/'hebrew-trial-r5-ready'/command).glob('*.png'));assert len(paths)==1
        copy(paths[0],evidence/name)
    filtered='\n'.join(line for line in log.splitlines() if re.search(r'\[za-hebrew|\[reboot\]|\[fs\].*(000-hebrew-trial|mods have taken)',line))+'\n'
    (evidence/'hardware-filtered.log').write_text(filtered,encoding='utf-8')
    write(evidence/'installation.json',report)
    text=(TRIAL/'README-HE.md').read_text(encoding='utf-8')
    status='ההתקנה ב־PS5 הושלמה. העברית אומתה חזותית בתפריט המשחק ובכותרת, והריצה הקיימת נטענה בהצלחה. המתקין אימת 20 קבצים וקריאה חוזרת בתוך תהליך המשחק. קובצי המוד הפרטיים אינם ניתנים לקריאה חוזרת דרך שירות ה־FTP החיצוני.\n\n'
    status+='כפתור המעבר עבר בדיקות מחשב ובדיקת חיבור בבינארי. הפעלת המעבר בשלט וה־cold restart ב־PS5 ממתינים לאישור המשתמש.' if manual['status']=='pending_user' else 'כפתור המעבר נבדק עם המשתמש; ראו installation.json לפרטי האימות.'
    text=text.replace('{{HARDWARE_RESULT}}',status)
    (payload/'README-HE.md').write_text(text,encoding='utf-8')
    write(payload/'manifest.json',report)
    sums=''.join(f'{sha(p)}  {p.relative_to(payload).as_posix()}\n' for p in sorted(payload.rglob('*')) if p.is_file())
    (payload/'SHA256SUMS.txt').write_text(sums,encoding='utf-8')
    archive=DEST/(NAME+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in sorted(payload.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(payload).as_posix())
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    copy(payload/'README-HE.md',DEST/'README-HE.md')
    (DEST/'SHA256SUMS-DELIVERY.txt').write_text(f'{sha(archive)}  {archive.name}\n{sha(DEST/"README-HE.md")}  README-HE.md\n',encoding='utf-8')
    copied=[]
    for p in sorted(DEST.rglob('*')):
        if not p.is_file():continue
        target=NAS/p.relative_to(DEST);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p),'Different NAS version already exists'
        else:shutil.copyfile(p,target)
        assert sha(target)==sha(p)
        copied.append(dict(file=p.relative_to(DEST).as_posix(),sha256=sha(p)))
    receipt=dict(local=str(DEST),nas=str(NAS),nas_verified=True,zip_sha256=sha(archive),zip_bytes=archive.stat().st_size,files=copied)
    write(CONSOLE/'delivery-r1.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='files'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()

"""Versioned r20 candidate delivery and SHA-256-verified NAS copy."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, zipfile
ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'artifacts/randomizer-r20-batch'
PORT=ROOT/'port/submission-r20'
EXTRA=ROOT/'port/submission-r20-hardware'
E=ROOT/'evidence/submission-r20'
EXPECTED='33e435707b787fe23391996a5063b724d1c74627f4fea6e52d7b6d637b2f3819'

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def main():
    assert digest(ART/'PPSA91762/eboot.bin')==EXPECTED
    audit=json.loads((E/'preservation-audit.json').read_text())
    assert audit['same_dynamic_imports'] and audit['dynamic_import_count']==325
    image=json.loads((ART/'evidence/image-preservation.json').read_text())
    assert all(s['preserved'] for s in image['preserved_sections'])
    assert all(s['preserved'] for s in image['game_tables'])
    now=datetime.now(timezone.utc)
    out=ROOT/'deliverables'/('ZA-Randomizer-r20-Batching-Candidate-'+now.strftime('%Y%m%d-%H%M%SZ'))
    out.mkdir(parents=True,exist_ok=False)
    for name in ('README.txt',):shutil.copy2(PORT/name,out/name)
    shutil.copy2(ROOT/'reports/מודי 60FPS והתאמה לפורט.txt',out/'60FPS-Research-HE.txt')
    status={
      'at':now.isoformat(),'build':'r20-batch','title':'PPSA91762','eboot_sha256':EXPECTED,
      'host_trace_tests_passed':True,'full_ps5_link_passed':True,'image_and_import_audits_passed':True,
      'hardware_tested':False,'installed':False,'fps_gain_proven':False,
      'packaged_profile':'each','candidate_profile':'batch',
      'note':'CPU scheduling tests use the actual batching code with a mock GPU. PS5 performance and rendering are pending; no 60FPS claim.',
      'scope':'Only batching and title revision; fixed generated game archive and r19a local compiler included. Save/ROMFS/DLC data are not part of this update.'}
    hardware=ROOT/'evidence/submission-r20-hardware/final-result.json'
    if hardware.exists():status['hardware_result']=json.loads(hardware.read_text())
    write(out/'Verification.json',status)
    text='''Pokémon Legends: Z-A Randomizer — r20, גרסת ניסוי לאיחוד הגשות
הקוד נבנה ונבדק במחשב. חבילת הבסיס מוגדרת each, כלומר האיחוד כבוי עד לניסוי מכוון.
ההגדרה batch מפעילה איחוד של מקטעי עבודה ל־GPU, עד גבולות הסנכרון והקיבולת.
שינוי ההגדרה דורש סגירה ופתיחה של האפליקציה.
בדיקות סדר פקודות, המתנות ושימוש חוזר במשאבים עברו עם ASan/UBSan;
גם הקישור ל־PS5, רשימת הייבוא ושימור טבלאות המשחק עברו.
בדיקות המחשב אינן מוכיחות תקינות תמונה או שיפור FPS בקונסולה.
זו אינה הבטחה ל־60 FPS, ומוד תזמון דינמי חדש אינו כלול.
Update.zip מכיל רק eboot.bin והגדרת איחוד לאפליקציה PPSA91762 שכבר מותקנת.
Source.zip מכיל את שינויי הקוד והבדיקות, עם מקורות העדכון הקודם.
נדרשים קוד הבסיס וסביבת הבנייה המקומיים; אין בו ROMFS, שמירות, מפתחות או נתוני DLC.
Verification.json מכיל סטטוס מדויק. אם יש בו hardware_result, קראו את תוצאות הקונסולה.
'''
    (out/'STATUS-HE.txt').write_text(text,encoding='utf-8-sig')
    evidence=out/'evidence';evidence.mkdir()
    for name in ('preservation-audit.json','preparation.json','registration.json','runtime-r20.patch','tests.log','eboot.sha256.txt'):
        shutil.copy2(E/name,evidence/name)
    shutil.copy2(ART/'evidence/image-preservation.json',evidence/'image-preservation.json')
    previous=ROOT/'deliverables/ZA-Randomizer-r19a-Local-Compiler-20261028-163222Z/Source.zip'
    with zipfile.ZipFile(previous) as old,zipfile.ZipFile(out/'Source.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in old.namelist():
            z.writestr(name,old.read(name))
        for folder in (PORT,EXTRA):
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix in ('.h','.inc','.c','.py','.sh','.txt'):
                    z.write(f,f.relative_to(ROOT).as_posix())
        z.write(E/'runtime-r20.patch','evidence/submission-r20/runtime-r20.patch')
        if 'run_r3.py' not in old.namelist():z.write(ROOT/'run_r3.py','run_r3.py')
    with zipfile.ZipFile(out/'Update.zip','w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        z.write(ART/'PPSA91762/eboot.bin','PPSA91762/eboot.bin')
        z.writestr('PPSA91762/submission-options.txt','each\n')
        z.write(out/'STATUS-HE.txt','STATUS-HE.txt')
        z.write(out/'Verification.json','Verification.json')
        with zipfile.ZipFile(out/'Source.zip') as s:
            for name in s.namelist():
                if name.startswith('LICENSES/'):z.writestr(name,s.read(name))
    for name in ('Source.zip','Update.zip'):
        with zipfile.ZipFile(out/name) as z:assert z.testzip() is None
    files={f.relative_to(out).as_posix():{'bytes':f.stat().st_size,'sha256':digest(f)} for f in out.rglob('*') if f.is_file()}
    write(out/'SHA256.json',files)
    target=Path('//TheOnePiece/Software/PS5-13.60/Pokemon-ZA-Native-Port')/out.name
    result=dict(local=str(out),nas=str(target),nas_verified=False)
    try:
        target.mkdir(parents=True,exist_ok=False)
        for f in out.rglob('*'):
            if not f.is_file():continue
            dest=target/f.relative_to(out);dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(f,dest);assert digest(f)==digest(dest)
        result['nas_verified']=True
    except Exception as e:result['nas_error']=str(e)
    write(EXTRA/'delivery.json',result);print(json.dumps(result,ensure_ascii=True))
if __name__=='__main__':main()


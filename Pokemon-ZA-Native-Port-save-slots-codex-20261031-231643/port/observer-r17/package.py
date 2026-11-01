"""Package reviewed outputs only and verify versioned NAS copies."""
from pathlib import Path
from datetime import datetime,timezone
import difflib
import hashlib
import json
import shutil
import subprocess
import zipfile

root=Path(__file__).resolve().parents[2]
source=root/'port/observer-r17'
art=root/'artifacts/randomizer-r17a-observer-validated'
evidence=root/'evidence/observer-r17'
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
expected='67284db32a427459a88f8ca0bb8f09d5e12992e8e48ae1e2ac33f29356a04139'
binary=art/'PPSA91762/eboot.bin'
assert digest(binary)==expected
assert (art/'evidence/imports.txt').read_bytes()==(root/'artifacts/randomizer-r16-validated/evidence/imports.txt').read_bytes()
assert 'integrity: valid' in (art/'evidence/self-inspection.txt').read_text()
assert digest(root/'artifacts/randomizer-r16-validated/PPSA91762/eboot.bin')=='498aec45e8ae1c698aa505c41548207b2276a80918758727242f36e9ae8bee4c'
assert digest(root/'artifacts/randomizer-r15/PPSA91762/eboot.bin')=='5e02bcf386b07cd1c96e0ee2f2bd3f32bd900849aeacdc4668023a71372150c0'
base=Path(r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\perf-r16-20261028')
work=base.parent/'capture-r17-20261028'
for name in ('device','exec'):
    if name=='exec':
        assert digest(base/f'source/runtime/nvn/vulkan/{name}.c')==digest(work/f'source/runtime/nvn/vulkan/{name}.c')
        continue
    old=base/f'source/runtime/nvn/vulkan/{name}.c';new=work/f'source/runtime/nvn/vulkan/{name}.c'
    (evidence/f'{name}.patch').write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='r16/'+name+'.c',tofile='r17/'+name+'.c')))
old=base/'source/runtime/hle/input.c';new=work/'source/runtime/hle/input.c'
(evidence/'input.patch').write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='r16/input.c',tofile='r17/input.c')))
client_test=subprocess.run(['C:/Users/Tomer/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',str(source/'test-client.py')],check=True,capture_output=True,text=True)
(evidence/'client-tests.txt').write_text(client_test.stdout)
stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
out=root/'deliverables'/('ZA-Randomizer-r17a-Observer-'+stamp);out.mkdir()
hebrew='''כלי צילום ומדידת ביצועים לפוקימון — r17a

נבדק הקוד שבנה סוכן מריו, ושולב בגרסת בדיקה נפרדת על בסיס r16.
אפשר לבקש צילום מתוך המשחק, לשלוח לחיצה מוגבלת, להמשיך לריצה הקיימת
ולמדוד FPS וזמני פריימים בחלון של עד שתי דקות. הצילום נעשה מחוץ לחלון
המדידה, וזמן הצילום נרשם בנפרד. הנתונים כוללים סימון עבודת שיידרים.

הקומפילציה ל־PS5 ובדיקות המחשב עברו. הגרסה הותקנה בקונסולה עם אימות
SHA256 לאחר שהמשתמש פינה אותה מבדיקת מריו. הגרסה הראשונית עלתה לתפריט
והשמירה הנוכחית גובתה בשתי קריאות תואמות. תוקן נתיב הפקודות למחשב:
ה־PS5 אינו מאפשר יצירת קבצים ב־sandbox דרך FTP, ולכן קובץ השליטה מועבר
דרך תיקיית האפליקציה ונקרא ב־app0. התוצאות נשמרות בתיקיית הנתונים.
לפני בדיקת המשחק התקבלה בקשת מנוחה דרך HDMI-CEC, והקונסולה נותקה.
עדיין אין בחבילה תוצאות ביצועים חדשות או צילום מפוקימון.
מדידת הפריימים מבוססת על שליחה לתצוגה, ואינה מדידת סריקה של הטלוויזיה
או הוכחה שמהירות המשחק/האנימציות נכונה. צילום אינו מתאפשר כשהרנדרר תקוע.

קובץ העדכון מיועד לאפליקציית הרנדומייזר PPSA91762 הקיימת בלבד.
לפני התקנה יש לפנות את הקונסולה מבדיקות אחרות ולגבות את התוכנית והשמירה.
להחליף רק את שלושת הקבצים שבחבילה: eboot.bin, performance-options.txt,
observer-enable.txt. אין להחליף מטמוני שיידרים, משחק, שמירות או נתוני ריצה.
הנחיות מלאות, בדיקות, מגבלות וכלי המחשב נמצאים בחבילת הקוד וב־README.txt.
אפשר להשבית את כלי הצילום בהסרת observer-enable.txt לפני פתיחה מחדש.
'''
(out/'README-HE.txt').write_text(hebrew,encoding='utf-8')
shutil.copy2(source/'README.txt',out/'README.txt')
with zipfile.ZipFile(out/'ZA-Randomizer-r17a-Observer-Update.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name in ('eboot.bin','performance-options.txt','observer-enable.txt'):z.write(art/'PPSA91762'/name,'PPSA91762/'+name)
    z.write(out/'README-HE.txt','README-HE.txt');z.write(out/'README.txt','README.txt')
with zipfile.ZipFile(out/'ZA-r17a-Observer-Source-and-Audit.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for folder in (source,root/'port/performance-r16'):
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix in ('.c','.h','.py','.sh','.txt'):z.write(p,p.relative_to(root).as_posix())
    for p in sorted(evidence.iterdir()):
        if p.is_file() and p.suffix in ('.json','.txt','.patch','.log'):z.write(p,p.relative_to(root).as_posix())
    for name in ('imports.txt','image-preservation.json','self-inspection.txt','elf-inspection.txt'):
        z.write(art/'evidence'/name,'evidence/native-build/'+name)
for name in ('ZA-Randomizer-r17a-Observer-Update.zip','ZA-r17a-Observer-Source-and-Audit.zip'):
    with zipfile.ZipFile(out/name) as z:assert z.testzip() is None
verification={'at':datetime.now(timezone.utc).isoformat(),'title':'PPSA91762','eboot_bytes':binary.stat().st_size,
              'eboot_sha256':expected,'host_tests':json.loads((evidence/'host-tests.json').read_text()),
              'client_tests':'passed','native_self_integrity':'valid','r16_imports_unchanged':True,
              'r15_r16_binaries_retained_and_hash_verified':True,'installed_on_ps5':True,'measured_on_ps5':False,
              'console_contacted':True,'next_step':'Wake PS5 and open payload services; HDMI CEC suspend interrupted launch'}
(out/'VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
files=[p for p in sorted(out.iterdir()) if p.is_file()]
(out/'SHA256SUMS.txt').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in files))
files.append(out/'SHA256SUMS.txt')
nas=Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port')/out.name
copy={'destination':str(nas),'verified':False,'files':[]}
try:
    nas.mkdir(parents=True,exist_ok=True)
    for p in files:
        target=nas/p.name;sha=digest(p)
        if target.exists() and digest(target)!=sha:raise RuntimeError('Different existing NAS file: '+str(target))
        if not target.exists():shutil.copy2(p,target)
        assert digest(target)==sha
        copy['files'].append({'name':p.name,'bytes':p.stat().st_size,'sha256':sha})
    copy['verified']=True
except (OSError,RuntimeError) as e:copy['error']=str(e)
(out/'NAS-COPY-VERIFIED.json').write_text(json.dumps(copy,indent=2)+'\n')
if copy['verified']:
    shutil.copy2(out/'NAS-COPY-VERIFIED.json',nas/'NAS-COPY-VERIFIED.json')
    assert digest(out/'NAS-COPY-VERIFIED.json')==digest(nas/'NAS-COPY-VERIFIED.json')
print(json.dumps({'local':str(out),'nas':str(nas),'nas_verified':copy['verified'],'files':copy['files']},indent=2))

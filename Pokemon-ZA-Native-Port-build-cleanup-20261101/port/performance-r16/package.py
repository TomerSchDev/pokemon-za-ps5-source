"""Package the verified local candidate and copy final deliverables to the NAS."""
from pathlib import Path
import datetime, hashlib, json, shutil, zipfile

root=Path(__file__).resolve().parents[2]
work=Path(r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\perf-r16-20261028')
base=Path(r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\title-r1-20261027')
app=root/'artifacts/randomizer-r16-validated/PPSA91762'
ev=root/'evidence/performance-r16'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()
expected='498aec45e8ae1c698aa505c41548207b2276a80918758727242f36e9ae8bee4c'
assert sha(app/'eboot.bin')==expected
assert sha(base/'source/runtime/nvn/vulkan/exec.c')=='1cfd51bcca8d2a2fd8419eb2e2752c19d4fb75eaeab3a1b1fc381a5fa7d6e72d'
assert sha(root/'artifacts/randomizer-r15/PPSA91762/eboot.bin')=='5e02bcf386b07cd1c96e0ee2f2bd3f32bd900849aeacdc4668023a71372150c0'
assert (ev/'host-tests.txt').read_text().count('PASS ')==7
ae=root/'artifacts/randomizer-r16-validated/evidence'
assert (ae/'imports.txt').read_bytes()==(root/'artifacts/randomizer-r15/evidence/imports.txt').read_bytes()
assert 'integrity: valid' in (ae/'self-inspection.txt').read_text()
preserve=json.loads((ae/'image-preservation.json').read_text())
assert all(x['preserved'] for x in preserve['preserved_sections']+preserve['game_tables'])
assert 'FPS TRIAL' in (work/'cheats-r16.cpp').read_text()

stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
dest=root/'deliverables'/('ZA-Randomizer-r16-Performance-'+stamp)
dest.mkdir(exist_ok=False)
readme='''Pokémon Legends: Z-A Randomizer — גרסת ניסוי r16

נבנתה במחשב עבור האפליקציה הקיימת PPSA91762. הקובץ עבר קישור, המרה,
חתימה ובדיקת שלמות. הגרסה טרם הועברה ל־PS5 ולא נבדקה במשחק.

מה השתנה
• תיקון טבלאות שיידרים ו־pipelines שעלולות להיתקע כשהן מתמלאות.
• תיקוני אתחול מקבילי ומעקב אחר עבודות קימפול ממתינות ורצות.
• פחות חישובים חוזרים של מפתחות רינדור ופחות עבודה בבניית נתוני השיידרים.
• ביטול בקר התזמון הכללי הנוסף לפני תחילת המשחק.
• שורה חדשה בתפריט הקיים: FPS TRIAL, להפעלת ניסיון 60 אחרי הטעינה.

אחרי התקנת העדכון ובזמן שאפשר לבדוק
המשחק יתחיל ב־30. היכנס לשמירה והמתן עד שאפשר לשלוט בדמות.
פתח את התפריט עם L3+R3, בחר FPS TRIAL ולחץ X. סגור את התפריט בעיגול.
אם הקצב נמוך לאורך כמה חלונות מדידה נקיים, המשחק יחזור למצב המקורי.
אפשר לפתוח שוב את התפריט ולנסות מחדש, או לחזור ידנית ל־30.
הבחירה נשמרת רק להפעלה הנוכחית. שאר הצ׳יטים נשמרים כפי שנשמרו ב־r15.

בדיקות שעברו במחשב
24,000 רשומות מטמון מתנגשות; 40,000 השוואות מפתחות רינדור;
80,000 השוואות hash של תוכניות; 4,096 השוואות מדויקות של נתוני שיידרים;
640,000 פעולות מקביליות; בדיקות התזמון וממשק ההפעלה בפועל.
בדיקות C הורצו עם AddressSanitizer ו־UndefinedBehaviorSanitizer.
נשמרו כל טבלאות הפונקציות בהמרת הקובץ, ולא נוספו ייבואים לעומת r15.

מגבלות וסדר ההמשך
זו גרסת הניסוי הראשונה בתוכנית. מצב ה־60 הוא עדיין ניסיון סטטי עם חזרה
אוטומטית ל־30; התזמון הדינמי המלא של RC3.0 אינו משולב עדיין.
אין עדיין מדידה שמוכיחה שיפור בקונסולה או 60 יציבים. נדרשת בדיקה מאותה
שמירה ובאותו אזור עם מטמון מוכן, כולל מהירות הליכה, קרב, תפיסה ותמונה.
הקובץ performance-options.txt מאפשר השוואת האופטימיזציות באותה בנייה;
פרופילי ההשוואה וההסבר הטכני נמצאים בארכיונים.

תוכן החבילה
Update: eboot.bin ושני קובצי אפשרויות בלבד. אינו מתקין מחדש את המשחק,
ה־DLC, הרנדומיזציה, השמירות או מטמוני השיידרים. אלה נשארים מההתקנה הקיימת.
יש לסגור את האפליקציה ולגבות את eboot.bin הקיים לפני החלפתו. לא להעתיק
תיקיית cache ישנה מתיקיות בנייה; החבילה הזאת אינה מכילה אחת.
Source-and-Audit: הקוד ששונה, בדיקות, patch ותוצאות. אין בו ROM, מפתחות
או קוד המשחק שנוצר מהקבצים שלך. הוא דורש את סביבת הפיתוח הקיימת לבנייה.

SHA-256 של eboot.bin החדש:
'''+expected+'\n'
(dest/'README-HE.txt').write_text(readme,encoding='utf-8-sig')
receipt={'revision':'r16','title_id':'PPSA91762','created_local':stamp,'binary_sha256':expected,
         'binary_bytes':(app/'eboot.bin').stat().st_size,'host_tests_passed':7,'console_installed':False,'gameplay_tested':False,
         'dynamic_rc3_integrated':False,'original_r15_source_and_binary_unchanged':True,'imports_equal_r15':True,
         'conversion':preserve,'patch':json.loads((ev/'patch-manifest.json').read_text()),
         'performance_object_sha256':sha(work/'randomizer-r16/objects/title_performance.o'),
         'renderer_object_sha256':sha(work/'source/build/ps5/rt/nvn/vulkan/exec.o')}
(dest/'VERIFICATION.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding='utf-8')

update=dest/'ZA-Randomizer-r16-Update.zip'
with zipfile.ZipFile(update,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name in ('eboot.bin','performance-profile.txt','performance-options.txt'):
        z.write(app/name,'PPSA91762/'+name)
    for profile in ('optimized','shadow','renderer-baseline','pacing-baseline'):
        z.writestr('comparison-profiles/'+profile+'.txt',profile+'\n')
    for name in ('README-HE.txt','VERIFICATION.json'):z.write(dest/name,name)
print('Update archive written',flush=True)
audit=dest/'ZA-R16-Source-and-Audit.zip'
with zipfile.ZipFile(audit,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in (root/'port/performance-r16').iterdir():
        if p.is_file() and p.suffix in ('.c','.h','.py','.sh','.txt'):z.write(p,'port/performance-r16/'+p.name)
    for name in ('exec.c','za_r16_cache_table.h'):z.write(work/'source/runtime/nvn/vulkan'/name,'patched-runtime/'+name)
    for name in ('title_entry-r16.c','cheats-r16.cpp','build-r16.sh'):z.write(work/name,'generated/'+name)
    for p in (work/'host-tests').glob('*.c'):z.write(p,'generated-tests/'+p.name)
    for p in ev.iterdir():
        if p.is_file():z.write(p,'evidence/'+p.name)
    for name in ('image-preservation.json','imports.txt','self-inspection.txt','elf-inspection.txt'):z.write(ae/name,'image-evidence/'+name)
    z.write(work/'source/LICENSE','LICENSE-upstream.txt')
    z.write(dest/'VERIFICATION.json','VERIFICATION.json')
for archive in (update,audit):
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
manifest={p.name:sha(p) for p in dest.iterdir() if p.is_file()}
(dest/'SHA256SUMS.txt').write_text(''.join(h+'  '+name+'\n' for name,h in manifest.items()),encoding='utf-8')
print('Archives CRC-checked; copying to NAS',flush=True)
nas=Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port')/dest.name
try:
    nas.mkdir(exist_ok=False)
    verified=[]
    for p in dest.iterdir():
        if not p.is_file():continue
        target=nas/p.name;shutil.copy2(p,target)
        h=sha(p);assert sha(target)==h,p.name
        verified.append({'name':p.name,'sha256':h,'bytes':p.stat().st_size})
    copy_receipt=dest/'NAS-COPY-VERIFIED.json'
    copy_receipt.write_text(json.dumps({'destination':str(nas),'verified':verified},indent=2),encoding='utf-8')
    shutil.copy2(copy_receipt,nas/copy_receipt.name)
    assert sha(copy_receipt)==sha(nas/copy_receipt.name)
    print(json.dumps({'local':str(dest),'nas':str(nas),'nas_verified':True,'files':verified},indent=2),flush=True)
except Exception as e:
    print(json.dumps({'local':str(dest),'nas_verified':False,'error':str(e)},indent=2),flush=True)
    raise

"""Package this validated local update and copy final files to the user's NAS."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, zipfile

ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'evidence/local-shader-r19'
PORT=ROOT/'port/local-shader-r19'
ART=ROOT/'artifacts/randomizer-r19a-local-compiler'
NEW='1f8d448a9d6a89f3abc2d94e36db23bef008d3dc8e1d30e9f3ea7c5fea557918'
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()
def read(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def main():
    now=datetime.now(timezone.utc)
    out=ROOT/'deliverables'/('ZA-Randomizer-r19a-Local-Compiler-'+now.strftime('%Y%m%d-%H%M%SZ'))
    out.mkdir(parents=True,exist_ok=False)
    dst=out/'evidence';dst.mkdir()
    assert digest(ART/'PPSA91762/eboot.bin')==NEW
    warm=read(E/'r19a-warm-restart.json')
    assert warm['test_config_absent'] and warm['local_compiles_after_restart']==0
    measurements=[]
    for session,seq in [('00000628dc75800f',5),('0000065d86099824',4)]:
        src=E/('session-'+session)
        ack=read(src/f'command_{seq}.json')['ack'];assert ack['result']=='complete'
        analysis=read(src/f'measure_{seq}-analysis.json')
        measurements.append({'session':session,'phase':'before restart' if seq==5 else 'after restart',**analysis})
        for name in (f'command_{seq}.json',f'measure_{seq}.csv',f'measure_{seq}-analysis.json'):
            shutil.copy2(src/name,dst/(session+'-'+name))
    verification={
        'at':now.isoformat(),'build':'r19a','title':'PPSA91762','eboot_sha256':NEW,
        'installed_and_readback_verified':True,
        'controlled_local_compile':{'shader':'3ca51913eaabc794','stage':'fragment','role':'built-in presentation shader',
            'compile_ms':1.438,'queue_ms':0.008,'bytes':696,'host_sha256_equal':True,'spirv_val':'Vulkan 1.3 passed',
            'sha256':'d419cc24c8b2a2d64a9a29ad8604ad5df972b45e25520256d8823be44cee1661'},
        'requested_but_not_exercised_shader':'f120ba848ee181dc',
        'warm_restart':warm,'measurements':measurements,
        'scene':'Stationary in the existing saved interior, in front of the office desk; not an outdoor route or combat benchmark.',
        'save_report_and_cheats_preserved':read(E/'r19a-save-preserved.json'),
        'input_fix':'Future scheduled input no longer disarmed by same-frame polling; A entered the existing save in two launches.',
        'limits':[
            'The integrated forced test exercised one simple presentation shader, not all game shaders or stress under simultaneous combat compilation.',
            '36 captured host outputs and the earlier r18b PS5 standalone compiler test provide separate broader compiler evidence.',
            'FPS is CPU presentation submission interval rate; no display-scanout or simulation-speed measurement.',
            'No old-build A/B FPS measurement was taken. This does not demonstrate a performance improvement or 60 FPS.',
            'New shaders, driver pipeline creation, asset loading and other game work may still stall. This is not full shader precompilation.',
            'Startup transitions still had hitches. Screenshot encoding also stalls for about 0.29 seconds and was excluded from measurement windows.',
            'A single bounded worker handles misses; first-use built-ins/compute and draws waiting for pipelines may still block.',
            'Long-session stability, memory pressure during heavy combat, and every shader variant remain untested.']}
    write(out/'hardware-verification.json',verification)
    for name in ['r19a-import-delta.json','r19a-test-cleanup.json','r19a-forced-hashes.json','r19a-save-preserved.json',
                 'r19a-warm-restart.json','registration.json']:
        shutil.copy2(E/name,dst/name)
    shutil.copytree(E/'r19a-host',dst/'host')
    shutil.copy2(ART/'evidence/image-preservation.json',dst/'image-preservation.json')
    shutil.copy2(E/'deployment-20261028-162206Z/receipt.json',dst/'deployment.json')
    shutil.copy2(E/'session-0000065d86099824/frame_1553_3.png',out/'Verified-in-game.png')
    # Only game diagnostics; exclude unrelated system/account/network logs.
    log=(E/'r19-20261028-160506Z.klog.log').read_text(errors='replace')
    log=log[log.index('[za-title-randomizer-r19a-local-compiler] main reached;'):]
    selected=[line for line in log.splitlines() if any(s in line for s in
        ('[shaderc-cache]','[shader-local]','[hitch]','[vk] t=','[za-title-randomizer-r19a-local-compiler]','[za-randomizer] boot selected'))]
    (dst/'game-diagnostics.log').write_text('\n'.join(selected)+'\n')
    shutil.copytree(E/'r19a-forced-output',dst/'controlled-shader')
    shutil.copy2(PORT/'README.txt',out/'README.txt')
    status='''Pokémon Legends: Z-A Randomizer — עדכון r19a
28.10.2026

הותקן ונבדק ב־PS5. אפשר להמשיך לשחק באותה אפליקציה ובאותה שמירה.

מה השתנה
הוספנו קומפיילר GLSL מקומי: כאשר שיידר אינו נמצא במטמון, המשחק יכול לקמפל
אותו על ה־PS5 במקום להמתין לקומפילציה במחשב. העבודה עוברת דרך תהליך־משנה
אחד עם תור מוגבל; התוצאה עוברת את העיבוד הרגיל של המשחק ונשמרת אטומית.
הכנת הקומפיילר מתחילה כבר בתפריט הרנדומייזר.
תוקנה גם לחיצה אוטומטית שנמחקה לפני שהגיע הפריים המיועד לה.

מה נבדק בפועל
שיידר תצוגה אחד נבנה במכוון מחדש בקונסולה: 1.438 מילישניות לקומפילציה,
0.008 מילישניות בתור. התוצאה זהה ב־SHA-256 לתוצאה מהמחשב ועברה spirv-val.
אחרי סגירה ופתיחה מחדש השיידר נשאר במטמון, ולא הייתה קומפילציה חוזרת.
השמירה נטענה פעמיים ותמונות המשחק נבדקו מהמחשב.
בשתי מדידות של 20 שניות בעמידה מול השולחן בחדר הנוכחי התקבלו 30.000 FPS,
ללא פריים מעל 50 מילישניות; הפריים הארוך ביותר היה כ־33.41 מילישניות.
זו מדידת מרווחי שליחת פריימים, לא מדידה ישירה של המסך או של מהירות הסימולציה.
השמירה, דוח הרנדומייזר והצ׳יטים נמצאו זהים לגיבוי שנלקח לפני הבדיקה.
הגדרת הבדיקה הוסרה. הגרסה הנוכחית פתוחה בשמירה שלך במצב רגיל.

מה עדיין לא הוכח
זו אינה הבטחה שכל הגמגומים נפתרו, ואינה גרסת 60 FPS חדשה.
הבדיקה המשולבת כללה שיידר תצוגה פשוט; שיידר הקודקודים הנוסף שבחרנו לבדיקה
לא הופעל בסצנה הזאת ולכן אינו נספר כהצלחה. בדיקות קומפיילר רחבות יותר בוצעו
בנפרד במחשב וב־PS5 במסגרת r18b.
עדיין ייתכנו עצירות בעת טעינת תוכן חדש, בניית pipelines בדרייבר או המתנה
לשיידר ראשון. בטעינה הראשונית נצפו עצירות. מדידות ה־FPS התייחסו למשחק אחרי סיום הטעינה.
לא בוצעה השוואת FPS מול הגרסה הקודמת, בדיקת קרבות עמוסים או בדיקת יציבות ארוכה.
אין כאן מאגר מקומפל מראש של כל וריאציות השיידרים במשחק.

קבצים וגיבוי
Update.zip הוא עדכון לקובץ התוכנית ולהגדרת הקומפיילר של PPSA91762 הקיים בלבד.
אין בו נתוני RomFS, DLC, שמירות, מפתחות או מטמונים. הוא אינו מתקין משחק מלא.
Source.zip מכיל את השינויים והבדיקות; לבנייה צריך את סביבת הפיתוח והקוד המקומיים.
hardware-verification.json ותיקיית evidence מכילים את תוצאות הבדיקות ומגבלותיהן.
הגרסאות הקודמות נשמרו מקומית ובקונסולה. גיבוי השמירה נמצא גם ב־NAS תחת
PS5-13.60/Pokemon-ZA-Native-Port/Save-Backups/save-backup-20261028-160533Z.
'''
    (out/'STATUS-HE.txt').write_text(status,encoding='utf-8-sig')
    source_manifest={p.name:digest(p) for p in PORT.iterdir() if p.is_file()}
    write(dst/'source-sha256.json',source_manifest)
    previous=ROOT/'deliverables/ZA-Randomizer-r19-Local-Compiler-Pending-20261028-175016/Source-v2.zip'
    with zipfile.ZipFile(previous) as old,zipfile.ZipFile(out/'Source.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in old.namelist():
            if not name.startswith('port/local-shader-r19/'):
                z.writestr(name,old.read(name))
        for p in sorted(PORT.iterdir()):
            if p.is_file():z.write(p,'port/local-shader-r19/'+p.name)
        for name in ['observer.h','client.py','analyze.py']:
            z.write(ROOT/'port/observer-r17'/name,'port/observer-r17/'+name)
        glsl_license=Path('//wsl.localhost/Ubuntu/home/tomer/ps5-za-native/shader-prewarm-research/glslang/LICENSE.txt')
        z.write(glsl_license,'LICENSES/glslang-LICENSE.txt')
    with zipfile.ZipFile(out/'Update.zip','w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        z.write(ART/'PPSA91762/eboot.bin','PPSA91762/eboot.bin')
        z.write(ART/'PPSA91762/local-shader-options.txt','PPSA91762/local-shader-options.txt')
        z.write(out/'STATUS-HE.txt','STATUS-HE.txt')
        z.write(out/'hardware-verification.json','hardware-verification.json')
        with zipfile.ZipFile(out/'Source.zip') as source:
            for name in source.namelist():
                if name.startswith('LICENSES/'):z.writestr(name,source.read(name))
    for name in ['Source.zip','Update.zip']:
        with zipfile.ZipFile(out/name) as z:assert z.testzip() is None
    files={str(p.relative_to(out)).replace('\\','/'):{'bytes':p.stat().st_size,'sha256':digest(p)} for p in out.rglob('*') if p.is_file()}
    write(out/'SHA256.json',files)
    target=Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port')/out.name
    copied=[]
    try:
        target.mkdir(parents=True,exist_ok=False)
        for p in out.rglob('*'):
            if not p.is_file():continue
            remote=target/p.relative_to(out);remote.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,remote);assert digest(remote)==digest(p),str(remote)
            copied.append(str(p.relative_to(out)))
        nas={'verified':True,'path':str(target),'files':len(copied)}
    except Exception as exc:nas={'verified':False,'path':str(target),'error':str(exc),'files_copied':len(copied)}
    receipt={'local':str(out),'nas':nas}
    write(E/'final-delivery.json',receipt)
    print(json.dumps(receipt,indent=2,ensure_ascii=False))

if __name__=='__main__':main()

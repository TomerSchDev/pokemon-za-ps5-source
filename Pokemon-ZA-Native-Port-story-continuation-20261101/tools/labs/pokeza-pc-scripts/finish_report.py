"""Package measured evidence and user instructions. No credentials or caches."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import zipfile

root=Path(__file__).resolve().parent
package=root.parents[1]/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024'
proof=package/'evidence'; proof.mkdir(exist_ok=True)
bench={n:json.loads((root/'runs'/n/'benchmark.json').read_text()) for n in ['08-bench30','09-bench60']}
profile=json.loads((root/'runs/10-profile/profile-summary.json').read_text())
experiment_path=root/'runs/11-hot-o1/benchmark.json'
experiment=json.loads(experiment_path.read_text()) if experiment_path.exists() else None
build=json.loads((root/'aot-v1.0.0/build-result.json').read_text())
for name in ['08-bench30','09-bench60','11-hot-o1']:
    p=root/'runs'/name/'probe-play.json'
    if p.exists():
        record=json.loads(p.read_text())
        record.update(game_execution_verified=True,
                      visual_evidence='build/frames/frame_00900.png, manually reviewed',
                      verification_scope='Saved scene reload; does not certify whole game')
        p.write_text(json.dumps(record,indent=2))
snapshot=json.loads((root/'saves/post-battle-20261024/snapshot.json').read_text())
snapshot['reloaded']=True
snapshot['reload_evidence']='08-bench30/build/frames/frame_00900.png, visually reviewed'
(root/'saves/post-battle-20261024/snapshot.json').write_text(json.dumps(snapshot,indent=2))

images={
 '01-city.png':root/'runs/06-live/build/frame_32100.png',
 '02-battle-damage.png':root/'runs/07-battle/build/frame_12300.png',
 '03-battle-victory.png':root/'runs/07-battle/build/frame_21300.png',
 '04-save-reloaded.png':root/'runs/08-bench30/build/frames/frame_00900.png',
 '05-60fps-scene.png':root/'runs/09-bench60/build/frames/frame_00900.png',
}
for name,src in images.items(): shutil.copy2(src,proof/name)
for name,data in [('benchmark-30.json',bench['08-bench30']),('benchmark-60.json',bench['09-bench60']),
                  ('profile.json',profile),('build.json',build),('save.json',snapshot)]:
    (proof/name).write_text(json.dumps(data,indent=2))
for run in ['08-bench30','09-bench60','10-profile']:
    for name in ['stderr.log','probe-play.json','method.json','telemetry.jsonl']:
        src=root/'runs'/run/name
        if src.exists(): shutil.copy2(src,proof/(run+'-'+name))
if experiment:
    (proof/'benchmark-hot-o1.json').write_text(json.dumps(experiment,indent=2))
    shutil.copy2(root/'hot-o1-library/manifest.json',proof/'hot-o1-build.json')
    shutil.copy2(root/'runs/11-hot-o1/stderr.log',proof/'11-hot-o1-stderr.log')
    shutil.copy2(root/'runs/11-hot-o1/build/frames/frame_00900.png',proof/'06-hot-o1-scene.png')

facts=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),project='Pokemon Legends Z-A PC',
 game_version='1.0.0',title_id='0100F43008C44000',runtime='ZA Recomp v0.1.4',
 runtime_commit='4d82d8998adb75036c27f476e8d8f7e737bed36a',
 generation_commit=build['revision'],generation_headers_unchanged_in_v014=True,
 runtime_source_rebuilt=False,game_library_built_locally=True,
 hardware=dict(cpu='Intel Core i7-12700F',gpu='NVIDIA RTX 3050 8GB',ram_gb=32,driver='610.88'),
 verified=['boot','new save','save reload','station and city movement','camera',
           'starter selection','target lock','enemy attack','player Tackle and HP damage',
           'first battle victory','post-battle progression','post-battle save reload'],
 not_verified=['complete game','DLC and updates','mods','physical gamepad','audio quality',
               'console-matched shadow correctness','sustained 60 FPS throughout game'],
 game_library_sha256=build['library_sha256'],benchmarks=bench,
 isolated_hot_o1_experiment=experiment,
 profile_scope=profile['scope'],nas_copy_completed=False,
 nas_status='UNC Software path unavailable; direct LAN SSH timed out. Local files retained.')
(package/'verification.json').write_text(json.dumps(facts,indent=2))

def row(n):
    b=bench[n]
    return (f"ממוצע {b['fps_interval_mean']} FPS; טווח {b['fps_interval_min']}–{b['fps_interval_max']}; "
            f"פער הצגה מרבי שדווח {b['largest_reported_gap_ms']} ms; {b['intervals']} חלונות מדידה.")
commit=facts['runtime_commit']
source='https://github.com/Hexveil404/PokeZ-ARecomp/blob/'+commit+'/'
report=f'''בדיקת Pokémon Legends: Z-A במחשב של Tomer — 24.10.2026

המשחק הגיע בפועל לתנועה בעיר ולקרב הראשון: Totodile נגד Pancham של Andi.
נבדקו נעילה, מתקפת Tackle משני הצדדים, ירידת חיים, ניצחון, המשך העלילה ושמירה.
השמירה נטענה שוב באמצעות ספריית המשחק הרגילה, ללא תוסף הקלט האוטומטי.
זהו אימות של פתיחת המשחק והקרב הראשון; לא בדיקה של כל המשחק.

המחשב והבנייה
Intel i7-12700F, NVIDIA RTX 3050 עם 8GB לפי nvidia-smi, זיכרון 32GB,
Windows 11 ודרייבר NVIDIA 610.88. נתון ה-4GB ב-WMI אינו נתון ה-VRAM ששימש לדוח.
משחק 1.0.0, מזהה 0100F43008C44000; ללא עדכונים או DLC.
סביבת הריצה היא ההפצה הרשמית v0.1.4. הגיבוב שלה הושווה לגיבוב GitHub.
קוד המשחק נבנה מקומית: 224,367 פונקציות main ועוד 40,069 פונקציות SDK,
1,364 יחידות C; 1,209 ב-O1 ו-155 ב-O0 לפי מדיניות הפונקציות הגדולות של הריפו.
ספריית המשחק: 370,315,776 בתים. SHA-256: {build['library_sha256']}.
לא נבנתה כאן מחדש כל סביבת הריצה. ראו evidence/build.json ו-verification.json.

ביצועים שנמדדו, ולא תחזית
אותה שמירה, דמות עומדת בסמטה בתחילת הדרכת הלילה, חלון מדידה של 60–120 שניות,
1x, רזולוציה דינמית כבויה, SMAA/FSR1. מטמון התחלה זהה הועתק מהרצת הבדיקה.
ללא צילום תקופתי, ללא sampler וללא תוסף הקלט; צילום זיהוי אחד נעשה לפני חלון המדידה.
30 FPS: {row('08-bench30')}
60 FPS בכפייה לצורך מדידה: {row('09-bench60')}
אלה ערכי FPS בחלונות לוג של כשתי שניות, לא 1% low או אחוזוני זמני פריימים.
זו סצנה מוגבלת וסטטית; אינה מייצגת קרב מאוחר, אזור צפוף או את כל העיר.
בתנועה בעיר בהרצה האינטראקטיבית נראו גם ירידות לכ-26–29 FPS. היו בה צילומים תקופתיים,
ולכן לא משתמשים בממוצע הכולל שלה כמדד ביצועים. צילום כזה עצר את התצוגה לעיתים לכשנייה.
טעינת shaders חדשים יכולה להוסיף גמגום ראשוני; הבדיקה החוזרת אינה מבחן מטמון ריק.
ברירת המחדל בחבילה היא 30 FPS. אין בסיס להבטיח 60 קבועים בכל המשחק במחשב הזה.
בקוד הנוכחי, מצב 60 שאינו משיג את היעד עלול להאט את זמן העולם; קיימת חזרה אוטומטית
ל-30 במצב הרגיל. בדיקת 60 ביטלה במפורש את החזרה הזאת לצורכי מדידה בלבד.
מקור: {source}runtime/hle/framepace.c#L45

מה המשמעות של קוד C כאן
זהו תרגום מקדים של הוראות ARM64 לקוד C נמוך-רמה, ואז קומפילציה ל-x86-64.
ה-C מחזיק מצב אוגרים, טעינות ושמירות זיכרון וקפיצות; הוא אינו קוד המקור המקורי של המשחק.
אין צורך לפרש הוראות ARM בכל פריים, אבל עדיין יש שכבת שירותים של Horizon,
מימוש NVN ותרגום shaders ופקודות גרפיות ל-Vulkan. הקוד אפשרי מעשית: הבנייה הזאת רצה.
השימוש במילה native אינו מבטל את העלות של שירותי התאימות והתרגום הגרפי.
מקור: {source}README.md#L5
דוגמה מקומית: research/pokeza-pc/aot-v1.0.0/main/main_001.c, שורות 5–25.

אופטימיזציה למחשב הזה
הבנייה כבר משתמשת ב-x86-64-v3, כולל AVX2/FMA/BMI2 המתאימים למעבד הזה.
במדידה שבה נכפה יעד 60 התקבלו כ-43 FPS בסצנה הזאת. במימוש זמן העולם הנוכחי זה
אינו תחליף תקין למצב 30 בזמן משחק רגיל, ולכן לא נשמר כמצב ברירת מחדל.
רשימת HOT_GIANTS בריפו מתועדת כמותאמת לגרסת משחק 2.0.0; אין להניח שהכתובות
מזהות את אותן פונקציות ב-1.0.0. זה כיוון מעשי לבדיקת פונקציות חמות שנבנו ב-O0.
מקור: {source}runtime/gamebuild.c#L237
בוצע גם דיגום כתובות נפרד, עם מפת קישור של ספרייה שנקשרה מחדש מאותם אובייקטים.
evidence/profile.json מציג את הכתובות והפונקציות שנצפו. הדוגם כולל threads ממתינים
ומשהה אותם לצורך דגימה: מספר הדגימות אינו אחוז זמן CPU ואינו מדד FPS נקי.
הדגימה הייתה דלילה: שתי פונקציות המשחק המובילות נצפו רק 9 פעמים כל אחת.
אין בכך די לקבוע שהן צוואר הבקבוק או להצדיק הבטחת האצה; דרוש פרופיל CPU עשיר יותר.
הצעדים האפשריים הם מיפוי פונקציות חמות ל-1.0.0, קומפילציה סלקטיבית ב-O1/O2,
ואז השוואת ביצועים ותקינות מאותה שמירה. PGO או שינוי ניהול הזיכרון דורשים עבודה נוספת.
החבילה הרגילה משמרת את הבנייה שנבדקה בקרב. תוצאת ניסוי ממוקד מופיעה בהמשך, אם הושלם.
אין אומדן לאחוז האצה לכל המשחק. ריבוי ליבות כשלעצמו
אינו מבטיח שיפור אם המסלול המגביל הוא שרשור עיקרי או סנכרון.

הצללים המשוננים שדווחו
הדיווח הוא על שינון/רזולוציה נמוכה, לא על הבהוב. הסיבה המדויקת עדיין לא הוכחה.
העלאת רזולוציית התמונה בריפו מוגבלת למטרות ציור ביחס קרוב ל-16:9; מפות צל מרובעות
לא מוגדלות אוטומטית. גם כפיית aniso16 פוסחת על samplers של השוואת עומק.
לכן אי אפשר להבטיח ש-2x או סינון אניזוטרופי יתקנו את הצללים.
מקורות: {source}runtime/nvn/vulkan/textures.c#L178
{source}runtime/nvn/vulkan/textures.c#L1143
נדרשת השוואת אותה סצנה, זמן ומצלמה למקור, ובדיקת מפות עומק, סינון ו-depth bias.
לא בוצעה השוואה כזאת, ולא הוחל תיקון צללים או כיבוי צללים כדי להסתיר את הבעיה.

תקלות ומגבלות שנתגלו
ה-generator הארוז נכשל בקידוד cp1255 בעת כתיבת Pokémon ללוג ב-Windows בעברית.
הבנייה הושלמה בעזרת אותו קוד generator עם Python -X utf8; זו התאמת תהליך הבנייה.
בכלי הקלט המקומי תוקן סדר נעילה-לפני-תקיפה. בניסיונות עם הפסקות קלט הפסדנו בקרב;
לאחר רצף תקין, ללא שינוי חיים או לוגיקת המשחק, ניצחנו. אין להציג הפסדים כאלה כבאג משחק.
אין במסלול שנבדק שחזור של דיווח המסך השחור בקרב הראשון שפורסם ב-issue #4:
https://github.com/Hexveil404/PokeZ-ARecomp/issues/4
היעדר שחזור אינו מבטל את הדיווח במחשבים אחרים.
נמצאה גם הוראת MTE שממופה לנתיב לא ממומש ב-SDK; לא נצפתה הגעה אליה בסבב זה.
לא נבדקו אודיו בהאזנה, בקר פיזי, mods, גרסאות אחרות, DLC או השלמת המשחק.
הרצות הבדיקה הופסקו במכוון לאחר תקציב זמן או שמירה; קוד יציאה של terminate בלוג
אינו כשלעצמו הוכחה לקריסה.

מסירה
Play.cmd: משחק חדש. Continue-Test.cmd: השמירה שאחרי הקרב הראשון.
ראו README-he.txt למיפוי הכפתורים ולמיקום הלוגים.
העותק המקומי נשמר. ההעתקה ל-NAS לא הושלמה: נתיב Software לא היה זמין,
וגם ניסיון החיבור הישיר ל-LAN לא השיב. לא נקבע ניסיון חוזר אוטומטי.
'''
(package/'Test-Report-he.txt').write_text(report,encoding='utf-8-sig')
if experiment:
    change=100*(experiment['fps_interval_mean']/bench['09-bench60']['fps_interval_mean']-1)
    with (package/'Test-Report-he.txt').open('a',encoding='utf-8') as f:
        f.write(f'''\nניסוי אופטימיזציה ממוקד, בנפרד מהחבילה הרגילה
הפונקציות f_7000056b10 ו-f_70000f42e0 הועברו מ-O0 ל-O1 בלבד, ללא עריכת מקור המשחק.
אותה שמירה ואותו מטמון התחלתי, יעד 60 בכפייה, חלון 60–120 שניות:
ממוצע {experiment['fps_interval_mean']} FPS, טווח {experiment['fps_interval_min']}–{experiment['fps_interval_max']},
לעומת 42.96 בבסיס: הבדל של {change:+.1f}% במדד הזה בסבב היחיד הזה.
הניסוי אינו כולל בדיקה חוזרת של הקרב או מבחן לכל המשחק. לא הוחלף בו קובץ המשחק
בחבילת ההפעלה הרגילה. הספרייה הניסיונית נשמרה בנפרד ב-research/pokeza-pc/hot-o1-library.
אין להסיק מההבדל בסצנה זו אחוז האצה לכל המשחק. נדרשות חזרות ובדיקות תקינות לפני אימוץ.
''')
progress=json.loads((root/'progress.json').read_text(encoding='utf-8-sig'))
progress.update(updated_utc=facts['recorded_utc'],stage='Opening gameplay and first battle verified; local playable package ready',
                probe_session=None,probe_pid=None,final_deliverable=str(package),battle_victory_verified=True,
                save_reload_verified=True,nas_copy_completed=False)
(root/'progress.json').write_text(json.dumps(progress,indent=2))

tools_zip=package/'Lab-Tools-20261024.zip'
with zipfile.ZipFile(tools_zip,'w',zipfile.ZIP_DEFLATED) as z:
    for name in ['build_game.py','run_probe.py','lab_control.c','lab_send.py','build_lab.py',
                 'telemetry.ps1','prepare_profile.py','profile_summary.py','summarize_benchmark.py',
                 'bench_suite.py','snapshot_post_battle.py','package_pc.py','finish_report.py','try_hot_o1.py']:
        z.write(root/name, name)
    z.writestr('README.txt','Local lab scripts. Depend on the pinned upstream repository and existing research layout.\nNo game source, keys, signing material, dependencies, or caches are included.\n')
manifest=[]
for f in sorted(package.rglob('*')):
    if not f.is_file() or f.name=='SHA256.json': continue
    with f.open('rb') as h: sha=hashlib.file_digest(h,'sha256').hexdigest()
    manifest.append(dict(path=f.relative_to(package).as_posix(),bytes=f.stat().st_size,sha256=sha))
(package/'SHA256.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(dict(package=str(package),files=len(manifest),bytes=sum(f['bytes'] for f in manifest))))

"""Deliver a versioned architectural review and bounded diagnostic evidence."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import shutil
import statistics
import subprocess

ROOT=Path(__file__).resolve().parent
DEST=ROOT.parents[1]/'deliverables/Pokemon-ZA-Architecture-Review-20261025'
NAMES=['24-state-on-a-retry1','25-state-off-a','26-state-off-b','27-state-on-b']
NAS=Path(r'\\TheOnePiece\Software\Pokemon-ZA-PC')/DEST.name

def digest(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():
        if digest(src)!=digest(dst): raise RuntimeError('Different file exists: '+str(dst))
    else: shutil.copy2(src,dst)
    assert digest(src)==digest(dst)

def main():
    values={n:json.loads((ROOT/'runs'/n/'benchmark.json').read_text()) for n in NAMES}
    for n in NAMES:
        assert json.loads((ROOT/'runs'/n/'probe-play.json').read_text())['game_execution_verified']
    on=statistics.mean(values[n]['fps_interval_mean'] for n in (NAMES[0],NAMES[3]))
    off=statistics.mean(values[n]['fps_interval_mean'] for n in NAMES[1:3])
    review=json.loads((ROOT/'architecture_review.json').read_text(encoding='utf-8'))
    review['state_filter_test']=dict(runs={n:{k:v for k,v in d.items() if k!='samples'} for n,d in values.items()},
        on_mean_fps=on,off_mean_fps=off,on_vs_off_percent=(on/off-1)*100,
        already_enabled_in_delivered_build=True,new_runtime_optimization_applied=False,
        method='A-B-B-A, identical r2 DLL/save/cache/1x/SMAA/FSR1, forced60, seconds50..80, frame900 capture before timing',
        limits='Single stationary scene, two runs per condition, interval FPS rather than individual frame-time percentiles',
        excluded_startup_run='24-state-on-a: parent re-executed into child; excluded and owned child stopped; revised harness fails closed on startup address collision')
    DEST.mkdir(exist_ok=False)
    (DEST/'Architecture-review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
    text=f'''בדיקת ארכיטקטורה ואופטימיזציה — Pokémon Legends Z-A במחשב
25.10.2026 | Core i7-12700F, RTX 3050 8GB, RAM 32GB
קוד runtime שנבדק: 4d82d8998adb75036c27f476e8d8f7e737bed36a

המסקנה
יש מקום סביר לשפר את המימוש שאנחנו מריצים, ויש לכך בסיס בקוד
ובמדידות. חלק מהסרבול נובע מהמרת בינארי ARM ל-C ומשכבות התאימות.
אי אפשר להסיק מכך שהקוד המקורי של מפתחי המשחק נכתב בצורה גרועה.
הצעד הקרוב המועדף הוא צמצום חישובים חוזרים בהכנת ציור, תוך
השוואה מול המסלול הקיים. מעבר למנוע משחק אחר אינו נדרש לכך.

מה נבדק מול דפוסים ידועים

1. חישוב רק כאשר מצב השתנה — Dirty flags / incremental state
עובדה: draw_ בונה PipeKey ומחשב hash בכל קריאת ציור, גם כשהוא
מוצא אחר כך pipeline שכבר קיים. get_program מחשב בנפרד מפתח שיידר.
סינון bind כפול מתבצע רק לאחר העבודה הזאת.
ראיה: runtime/nvn/vulkan/exec.c שורות 1417, 3202, 3286, 3336, 3350.
מדידה: האזור הכולל של מפתח ה-pipeline כ-1.415 מילישניות לפריים.
זה אינו זמן hash לבדו ואינו כולו חיסכון שאפשר להשיג.
הצעה: לסמן שינוי של קבוצות המצב ולעשות שימוש חוזר במפתח תקף.
צריך לשמור תלות בתוכנית, פורמטים של מטרות ציור, מבנה קודקודים,
טופולוגיה, blending, depth, rasterization ומסלולי mirror/feedback.
זו ההצעה הממוקדת הראשונה; שיעור החזרות והרווח טרם נמדדו.

2. סינון פקודות גרפיקה כפולות — כבר ממומש ונבדק אצלך
ss_need נמנע משליחת מצב זהה שוב; ss_forget מאפס את הידע בגבולות
הדרושים. ראיה: exec.c שורות 893–930.
ביצעתי בדיקת on/off בסדר A-B-B-A, עם אותה ספריית r2:
פעיל: {values[NAMES[0]]['fps_interval_mean']:.2f}, {values[NAMES[3]]['fps_interval_mean']:.2f} FPS; ממוצע {on:.2f}.
כבוי: {values[NAMES[1]]['fps_interval_mean']:.2f}, {values[NAMES[2]]['fps_interval_mean']:.2f} FPS; ממוצע {off:.2f}.
פעיל לעומת כבוי: {(on/off-1)*100:+.2f}% במדידה הזאת.
זהו רווח של מנגנון שכבר היה פעיל בחבילה, ולא האצה חדשה שהוספתי.
נבדקה סצנה אחת ובדיקת on/off אינה הבטחה לביצועים בכל המשחק.

3. מטמון descriptors ונתונים דינמיים
Khronos מתארים שימוש חוזר ב-descriptor sets וב-buffer גדול עם
offsets דינמיים כשיטות לצמצום עלות במעבד. כאן stage_set מקצה
ומעדכן sets, אבל כבר קיימים מאגרי זיכרון ומניעת העתקות כפולות.
ראיה: exec.c שורות 480, 507, 590, 605, 2089, 2780.
הערת המפתח בשורות 897–899 אומרת שמטמון כללי נוסף כבר נוסה:
כשליש מהרשומות התאימו, אבל מחיר ההשוואה היה גבוה מהחיסכון
ב-NVIDIA. זו טענת המפתח; לא שחזרתי כאן את הניסוי ההוא.
לכן המלצה מספר לימוד אינה מספיקה. צריך למדוד חזרות ועלות lookup,
ואולי להפריד משאבים יציבים מנתונים דינמיים או להשתמש בדורות שינוי.
מדד sets של 2.381 מילישניות כולל גם הכנת buffers והעתקות.
מקור: https://docs.vulkan.org/samples/latest/samples/performance/descriptor_management/README.html

4. איגוד פקודות וסנכרון לפי תלות במשאבים
בקוד יש barriers מסוג ALL_COMMANDS לכל כיוון, ושליחה בסוף כל רשימת
פקודות. בסצנה שלנו נמדדו 78 flushes לפריים וכ-3.704 מילישניות
המתנה לשימוש חוזר בחריצי תור השליחה.
ראיה: exec.c שורות 230, 303, 4756; objects.c שורה 131.
תיעוד Khronos מסביר שסנכרון רחב מדי עלול להגביל חפיפה בעבודת GPU.
יש אפשרות לחקור איגוד רשימות וצמצום barriers, אבל רק לאחר מיפוי
תלויות, aliasing וכתיבות GPU שהמעבד קורא. לא הוסר שום fence.
מקור: https://docs.vulkan.org/samples/latest/samples/performance/pipeline_barriers/README.html

5. חלוקת עבודת ציור למשימות מקביליות
הקוד משתמש במצב משותף st ונועל את ביצוע רשימות הפקודות. תהליכי
עבודה לתרגום וקומפילציית שיידרים כבר קיימים; בפרופיל היציב לא
הייתה קומפילציה, ולכן הוספת עובדים לקומפילציה לא תפתור את המדד הזה.
ראיה: objects.c שורות 118–137; exec.c שורות 653, 744, 4456.
הארכיטקטורה האפשרית היא חבילות ציור עם מצב בלתי משתנה, מאגרי
פקודות נפרדים לעובדים וסדר שליחה ששומר על תלויות. הכנסת draw_
הנוכחי לכמה threads תיצור תחרות על מצב משותף; זו אינה הסבה קטנה.
גם מספר גדול של משימות זעירות עלול להוסיף עלות.
מקור: https://docs.vulkan.org/samples/latest/samples/performance/command_buffer_usage/README.html

6. סידור נתונים ווקטוריזציה במעבד
Intel מדגישים גישה רציפה לזיכרון וסידור SoA למקטעים שמתאימים ל-SIMD.
הסריקה ב-r1 כבר מחזיקה ארבעה ערכי x/y/z בווקטורים מקומיים, ו-r2
מוסיף בחירה קריאה של המנצח. הקומפילציה כבר מכוונת ל-x86-64-v3.
אין צורך להוסיף AVX2 כאילו הוא חסר. שינוי מבנה הנקודות הגלובלי
יפגע בקוד שנותר ותלוי ברשומות של 12 בתים; אפשר להתחיל בגבולות
מקומיים ולשמור על סדר הפעולות והגישה לזיכרון.
מקור: https://www.intel.com/content/www/us/en/developer/articles/training/explicit-vector-programming-best-known-methods.html

7. אופטימיזציה מונחית פרופיל — PGO
LLVM יכול להשתמש בפרופיל מתאים לסידור קוד ולהחלטות inlining.
ספירת פונקציות ולוג FPS אינם פרופיל PGO של המהדר. יש לבנות גרסת
מדידה תואמת, לדגום תנועה, קרבות ומעברי סצנה, ולבדוק את הבנייה
המשופרת גם במסלולים שלא שימשו לאימון. לא נבנתה כאן גרסת PGO.
לא אשתמש ב-fast-math באופן גורף: כבר תועדה רגישות מספרית ל-FZ.
מקור: https://clang.llvm.org/docs/UsersManual.html#profile-guided-optimization

ניסוי הפיתוח המומלץ הבא
להוסיף תחילה מטמון צל למפתחות ציור: לחשב את המפתח בדרך הקיימת,
להשוות אותו למפתח שהיה אפשר למחזר ולספור התאמות, בלי לשנות ציור.
רק אחרי אפס הבדלים, להפעיל דילוג על חישוב כאשר כל התלויות תקפות.
הצלחה תדרוש גם ירידה בזמן הכנת המפתח וגם תועלת חוזרת בפריימים,
עם בדיקת תנועה וקרב וללא פגמים בציור. לא מובטח מראש אחוז שיפור.
ECS או מעבר למנוע אחר אינם תנאי לניסוי הזה.

כלי מדידה ותוצרים
החבילה כוללת את הנתונים המלאים, צילום מכל ריצה וכלי שחזור.
ניסיון ההפעלה הראשון 24-state-on-a נפסל: תהליך ההפעלה הסתיים
והמשחק המשיך בתהליך חלופי. הילד זוהה לפי PID/הורה/נתיב ונעצר.
כלי המדידה המעודכן מכבה re-exec פנימי במקרה של התנגשות כתובות
באתחול ונכשל במפורש במקום לאבד את הגבלת הזמן. אין שינוי לאתחול
תקין או לקוד המשחק. tools/run_probe.py כאן מחליף את עותק כלי
המדידה שב-source/tools של חבילת r2; ספריית המשחק r2 לא השתנתה.

המדדים מתייחסים למחשב ולסצנה שנבדקו. מדדי CPU הם זמני קיר
מקוננים ואסור לחבר אותם. טווחי GPU כוללים לפעמים המתנה למעבד.
לא נבדק כאן כל המשחק ולא יושמה ארכיטקטורת רינדור חדשה.
'''
    (DEST/'Architecture-Review-he.txt').write_text(text,encoding='utf-8-sig')
    for name in ['run_probe.py','compare_state_filter.py','summarize_benchmark.py','profile_render.py','summarize_render.py']:
        copy(ROOT/name,DEST/'tools'/name)
    for n in NAMES:
        run=ROOT/'runs'/n
        for f in ['method.json','probe-play.json','benchmark.json','stderr.log']:
            copy(run/f,DEST/'evidence'/n/f)
        copy(run/'build/frames/frame_00900.png',DEST/'evidence'/n/'frame_00900.png')
    for f in ['method.json','probe-play.json']:
        copy(ROOT/'runs/24-state-on-a'/f,DEST/'evidence/excluded-startup'/f)
    hashes={p.relative_to(DEST).as_posix():digest(p) for p in sorted(DEST.rglob('*')) if p.is_file()}
    (DEST/'SHA256.json').write_text(json.dumps(hashes,indent=2))
    status=dict(destination=str(NAS),attempted_utc=datetime.now(timezone.utc).isoformat(),completed=False)
    try:
        probe=subprocess.run(['powershell.exe','-NoProfile','-Command',
            "if (Test-Path -LiteralPath '\\\\TheOnePiece\\Software') {exit 0} else {exit 2}"],timeout=12,capture_output=True)
        if probe.returncode: raise OSError('NAS unavailable')
        for p in sorted(DEST.rglob('*')):
            if p.is_file(): copy(p,NAS/p.relative_to(DEST))
        status.update(completed=True,verification='All copied file SHA256 hashes match')
    except (OSError,subprocess.TimeoutExpired):
        status['reason']='NAS unavailable or timed out'
    (ROOT/'reports/architecture-review-nas-copy.json').write_text(json.dumps(status,indent=2))
    print(json.dumps(dict(deliverable=str(DEST),on_fps=on,off_fps=off,nas=status),indent=2))

if __name__=='__main__': main()

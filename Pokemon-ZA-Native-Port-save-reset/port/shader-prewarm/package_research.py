"""Package only final research source/metadata; no SDK, game content or build cache."""
from pathlib import Path
from datetime import datetime
import hashlib, json, shutil, subprocess, sys, zipfile

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent
E = ROOT/'evidence/shader-prewarm-research-20261028'
W = Path(r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\shader-prewarm-research')


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


forecast = json.loads((E/'forecast-summary.json').read_bytes())
validation = json.loads((E/'compiler/compiler-validation.json').read_bytes())
assert validation['captured_passed'] == validation['identical_to_previous_cli'] == 12
assert len(validation['negative_cases']) == len(validation['smoke_stages_passed']) == 3
assert 'PIE:' in (W/'ps5-link-final.log').read_text()
assert 'DYN' in (W/'compiler-elf-header.txt').read_text()
imports = (W/'compiler-imports.txt').read_text()
blocked = {'fork','execvp','waitpid','link','__cpu_model','__cpu_indicator_init','telldir','seekdir'}
assert not blocked.intersection(line.split()[-1] for line in imports.splitlines() if line.split())
tests = subprocess.run([sys.executable, str(SRC/'test_forecast.py')], capture_output=True, text=True)
assert tests.returncode == 0, tests.stdout + tests.stderr
(E/'forecast-tests.txt').write_text(tests.stdout+tests.stderr, encoding='utf-8')

binary_paths = ['ps5-build/libza_glsl_compiler.a', 'ps5-build/glslang/glslang/libglslang.a',
    'ps5-build/glslang/glslang/libglslang-default-resource-limits.a', 'compiler-link-check.elf']
receipt = dict(glslang_commit='f0bd0257c308b9a26562c1a30c4748a0219cc951',
    compiler_target='x86_64-sie-ps5', compiler='clang 21', linked=True,
    executed_on_ps5=False, installed=False, imported_blocklist_audit_passed=True,
    linker_note='Uses existing title platform/RADV recipe and --gc-sections; not a measured incremental title size.',
    binaries=[dict(path=x, bytes=(W/x).stat().st_size, sha256=digest(W/x)) for x in binary_paths],
    forecast_tests_passed=7, captured_shader_tests_passed=12,
    source_sha256={p.name:digest(p) for p in SRC.iterdir() if p.is_file()})
(E/'build-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
for name in ('ps5-configure.log','ps5-build-final.log','ps5-link-final.log','compiler-elf-header.txt'):
    shutil.copy2(W/name, E/name)

stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
out = ROOT/'deliverables'/('ZA-Shader-Prewarm-Research-'+stamp)
out.mkdir(parents=True, exist_ok=False)
report = '''מחקר הכנת שיידרים לפי אזור וסיד — Pokémon Legends: Z-A על PS5
תאריך: 28.10.2026

המסקנה: הרעיון מעשי כבסיס להכנה מראש לפי אזור. בניתי תחזית תוכן
וקומפיילר ליעד PS5. המערכת עדיין אינה משולבת במשחק ואינה מכינה
אוטומטית את כל השיידרים של אזורים שלא ביקרנו בהם.

מה אומת
• שחזור הטבלה הסופית של הסיד 6177047620 זהה ב-SHA-256 לעותק שנבדק
  בקונסולה. זהו הסיד האחרון המתועד, ולא קריאה חיה של השמירה הנבחרת.
• מיפוי 20 אזורי בר: 348 רשומות הופעה, 258 רשומות מפגש ייחודיות
  ו-175 צירופי פוקימון/צורה. באזור הראשון נמצאו 11 צירופים ב-18 רשומות הופעה.
• נבדקו בסך הכול 1,966 רשומות מפגש ו-2,211 רשומות הופעה. כל הפניות
  ההופעה למפגשים נפתרו. 1,049 רשומות הופעה חסרות הקשר אזור מפורש;
  581 רשומות מפגש לא מקושרות מטבלת ההופעות שנבדקה. אלו אינן שגיאות
  קומפילציה: הן פערים במיפוי שדורשים טבלאות אירועים/סצנות נוספות.
• זמן ביום, מזג אוויר ודגלי סיפור נשמרו בתוצאה. התחזית היא כל האפשרויות
  הרלוונטיות, לא הבטחה שכל הפוקימונים זמינים עכשיו.
• glslang 16.2.0 נבנה עם clang 21 ליעד PS5 וקושר לקובץ בדיקה עם
  ספריות המערכת. ספריית glslang הסטטית היא כ-6.7 MB; זו אינה צריכת הזיכרון.
• אותו ממשק קומפיילר הורץ במחשב על 12 שיידרים שנלכדו מהמשחק.
  כולם עברו spirv-val והתוצרים של כולם זהים לחלוטין לתוצרים הקודמים.
  גם בדיקות vertex/fragment/compute ושלוש בדיקות קלט שגוי עברו.
• שבע בדיקות תחזית עברו, לרבות שמירת תנאים, הפרדת מזהה פנימי ממספר
  Pokédex, הופעה במספר אזורים והגנת שבירת הסלעים בסיד שנבדק.

מה עדיין צריך לפתח
1. לבדוק את הקומפיילר על ה-PS5: זמן, שיא צריכת זיכרון, יציבות ועבודה
   ברקע. הבנייה והבדיקות במחשב אינן מדידה של ביצועי הקונסולה.
2. לחבר אותו למטמון הקיים כך שהחמצה תוכל להיקמפל מקומית, בלי מחשב.
3. למפות מודלים, חומרים ואפקטים לשיידרים ולהגדרות הציור המלאות.
   רשימת פוקימונים לבדה אינה מספיקה: יש גם סביבה, תאורה, מתקפות,
   מאמנים, חברי הצוות, צורות, תפיסה, שייני, Mega וממשק משתמש.
4. לשמור מתכוני יצירת pipeline לפי תוכן ואזור ולבנות תור הכנה מתועדף
   לפני תחילת המשחק/במעבר אזור. קובץ SPIR-V לבדו לא משלים את הכנת הדרייבר.
5. לפענח וריאציות שטרם הופיעו, באמצעות נתוני החומרים/ארכיוני BNSH
   או טעינת תוכן מבוקרת. נמצאו ארכיוני BNSH בנתונים, אך השיוך טרם הושלם.

המלצה
להתחיל בהכנה בזמן תפריט/טעינה של תוכן משותף, הצוות והאזור הראשון,
ואז להרחיב לאזור הבא. במהלך משחק יש להגביל את תור העבודה והזיכרון
לפי מדידות אמיתיות. להכין את כל הצירופים האפשריים בבת אחת עלול
להיות יקר מאוד ואינו נדרש כדי לשפר את תחילת הריצה.

ההתקנה והמטמון בקונסולה לא שונו במסגרת המחקר. אין עדיין הוכחה שכל
תקיעה עתידית תיעלם, או שכל התקיעות הקיימות נגרמות משיידרים.

פרטים טכניים, קוד ותוצאות אימות נמצאים בחבילת המחקר המצורפת.
מקורות ראשוניים:
https://github.com/KhronosGroup/glslang/tree/f0bd0257c308b9a26562c1a30c4748a0219cc951
https://docs.vulkan.org/guide/latest/pipeline_cache.html
'''
(out/'Shader-Prewarm-Research-HE.txt').write_text(report, encoding='utf-8-sig')
metadata = ['area-forecast.json','forecast-summary.json','asset-audit.json','build-receipt.json',
    'forecast-tests.txt','ps5-configure.log','ps5-build-final.log','ps5-link-final.log',
    'compiler-elf-header.txt','compiler/compiler-validation.json']
with zipfile.ZipFile(out/'Shader-Prewarm-Prototype-and-Evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for path in sorted(SRC.iterdir()):
        if path.is_file() and (path.suffix in {'.py','.c','.h','.sh','.cmake','.txt'} or path.name=='CMakeLists.txt'):
            z.write(path, 'source/'+path.name)
    for name in metadata:
        z.write(E/name, 'evidence/'+name)
manifest = dict(files=[dict(name=p.name,bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(out.iterdir())])
(out/'DELIVERABLES-VERIFIED.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(str(out))
print(json.dumps(manifest,indent=2))

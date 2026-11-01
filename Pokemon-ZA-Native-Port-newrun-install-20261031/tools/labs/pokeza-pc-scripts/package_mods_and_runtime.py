"""Package explicit deliverable allowlists. Never include game data, keys or caches."""
from pathlib import Path
from datetime import datetime, timezone
import difflib, hashlib, json, re, shutil, subprocess, zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'deliverables'
MOD=HERE/'mod-studio'
OPT=HERE/'runtime-opt-r1'
UP=HERE.parent/'pokeza-recomp'
MOUT=OUT/'Pokemon-ZA-Mod-Studio-0.1.0-20261025'
ROUT=OUT/'Pokemon-ZA-Runtime-Optimization-r1-20261025'

def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,text):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
def js(p,obj): write(p,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def cp(a,b):
    b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)
def zipdir(folder,dest):
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(folder).as_posix())
def inventory(folder):
    return {p.relative_to(folder).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(folder.rglob('*')) if p.is_file() and p.name!='SHA256.json'}

LAUNCH=r'''param([string]$GamePackage='', [string]$GameLibrary='', [string]$Dependencies='C:\msys64\ucrt64\bin')
$ErrorActionPreference='Stop'
# Start-Process from PowerShell 7 may inherit a module path unsuitable for 5.1.
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
if (!$GamePackage) { $GamePackage=Join-Path (Split-Path $PSScriptRoot -Parent) 'Pokemon-ZA-PC-v0.1.4-20261024' }
if (!$GameLibrary) { $GameLibrary=Join-Path (Split-Path $PSScriptRoot -Parent) 'Pokemon-ZA-Readable-C-r2-20261025\lasgame-readable-r2.dll' }
$GamePackage=(Resolve-Path -LiteralPath $GamePackage).Path
$GameLibrary=(Resolve-Path -LiteralPath $GameLibrary).Path
$exe=Join-Path $PSScriptRoot 'runtime\lasrecomp.exe'
foreach ($required in @($exe,$GameLibrary,(Join-Path $GamePackage 'game\romfs.bin'),(Join-Path $Dependencies 'avcodec-62.dll'),(Join-Path $Dependencies 'libshaderc_shared.dll'))) {
    if (!(Test-Path -LiteralPath $required)) { throw ('Required local dependency is missing: '+$required) }
}
if ((Get-FileHash -LiteralPath $GameLibrary -Algorithm SHA256).Hash.ToLowerInvariant() -ne '7bbbb82e063f379e9e37560386c36e620885317ab55dfce06cbb3c34d75dc788') { throw 'This experimental launcher requires the tested Readable C r2 library.' }
$main=Join-Path $GamePackage 'game\exefs\main'
$stream=[System.IO.File]::OpenRead($main)
try { $header=New-Object byte[] 96; if ($stream.Read($header,0,96) -ne 96) { throw 'Truncated NSO header' } } finally { $stream.Dispose() }
$build=([BitConverter]::ToString($header[64..95])).Replace('-','').ToLowerInvariant()
if ($build -ne '7222e13ecf6adb3249b5dd5c57fa40b102245fce000000000000000000000000') { throw 'Only Z-A base 1.0.0 was tested.' }
Get-ChildItem Env: | Where-Object { $_.Name.StartsWith('LARECOMP_') -or $_.Name.StartsWith('POKELAB_') } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+$_.Name) }
$work=Join-Path $PSScriptRoot 'user-data'
foreach ($dir in @($work,(Join-Path $work 'save'),(Join-Path $work 'logs'),(Join-Path $work 'build'))) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$guard=[System.IO.File]::Open((Join-Path $work 'running.lock'),[System.IO.FileMode]::OpenOrCreate,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None)
try {
    $env:PATH=$Dependencies+';'+$env:PATH
    $env:LARECOMP_DATA_ROOT=$work
    $env:LARECOMP_GAME_LIB=$GameLibrary
    $env:LARECOMP_SAVE_DIR=Join-Path $work 'save'
    $env:LARECOMP_SETTINGS=Join-Path $work 'settings.ini'
    $env:LARECOMP_NO_UPDATE_CHECK='1'
    $env:LARECOMP_REEXEC='20'
    $env:LARECOMP_KEY_REUSE='1'
    $env:LARECOMP_EMPTY_SUBMIT='1'
    $env:LARECOMP_SUBMISSION_SLOTS='16'
    if (!(Test-Path -LiteralPath $env:LARECOMP_SETTINGS)) {
        @('aspect = original','fullscreen = 0','volume = 0.3','show_fps = 1','fps60 = 0','resolution = 1x','dynamic_res = off','tex_hd = 0','antialias = smaa','upscaler = fsr1','language = en-US','mouse_camera = off') | Set-Content -LiteralPath $env:LARECOMP_SETTINGS -Encoding UTF8
    }
    for ($attempt=1; $attempt -le 5; $attempt++) {
        $stamp=Get-Date -Format 'yyyyMMdd-HHmmss-fff'
        $err=Join-Path $work ('logs\'+$stamp+'-stderr.log')
        $out=Join-Path $work ('logs\'+$stamp+'-stdout.log')
        $p=Start-Process -FilePath $exe -ArgumentList ('"{0}" --play' -f (Join-Path $GamePackage 'game')) -WorkingDirectory $work -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        Write-Host ('Game PID: '+$p.Id+'; isolated save: '+$env:LARECOMP_SAVE_DIR)
        $p.WaitForExit();$p.Refresh()
        if (!(Select-String -LiteralPath $err -Pattern 'FATAL: guest address range 7000000000-7800000000 is not free' -Quiet)) { exit $p.ExitCode }
        Write-Host 'Address reservation collision before game startup; retrying after the previous process exited.'
    }
    throw 'Five startup address collisions. Logs are in user-data/logs. The original installation was not changed.'
} finally { $guard.Dispose() }
'''

def main():
    for folder in (MOUT,ROUT):
        if folder.exists(): raise RuntimeError('Versioned deliverable already exists: '+str(folder))
        folder.mkdir(parents=True)
    assert not subprocess.check_output(['git','-C',str(UP),'status','--porcelain'],text=True).strip()
    integration=json.loads((MOD/'integration-audio-read-result.json').read_text())
    assert integration['registered'] and integration['replaced'] and integration['read'] and integration['captured']

    cp(MOD/'dist/ZA-Mod-Studio.exe',MOUT/'ZA-Mod-Studio.exe')
    cp(MOD/'Developer-Guide.txt',MOUT/'Developer-Guide.txt')
    cp(MOD/'samples/rules-demo.zip',MOUT/'examples/rules-demo.zip')
    for name in ['modcore.py','studio.py','test_modcore.py','integration_probe.py','make_sample.py','Developer-Guide.txt']:
        cp(MOD/name,MOUT/'source'/name)
    cp(MOD/'test-results.txt',MOUT/'evidence/test-results.txt')
    js(MOUT/'evidence/integration.json',integration)
    session=Path(integration['session'])
    for name in ['stderr.log','stdout.log','launch.json','mod-plan.json','romfs-reads.txt']:
        cp(session/name,MOUT/'evidence'/name)
    cp(Path(integration['captured'][0]),MOUT/'evidence/overlay-game-frame.png')
    # Preserve the rejected named-file assertion: it was a telemetry limitation,
    # not silently converted into a successful test.
    for name in ['integration-result.json','integration-audio-result.json']:
        cp(MOD/name,MOUT/'evidence'/name)
    js(MOUT/'evidence/ui-qa.json',dict(date='2026-10-25',zip_import=True,enable_toggle=True,
        review_one_mod_one_file=True,game_version_shown='1.0.0',sample='authored SDK fixture',
        launch_test='Studio.launch backend integration; GUI Launch button not exercised',
        final_small_changes='Added process-exit status and build directory after UI QA; no layout change'))
    write(MOUT/'README-he.txt','''ZA Mod Studio 0.1.0 — מנהל מודים ל־Pokémon Legends Z-A במחשב
25.10.2026

פתיחה: ZA-Mod-Studio.exe. אין צורך להתקין Python.
בחר את תיקיית חבילת המשחק שכבר נבנתה, ובה runtime ו־game.
המנהל מיועד כרגע לבסיס 1.0.0 בלבד; הוא בודק את מזהה הבנייה של main.

אפשר לייבא ZIP עם mod.json, תיקיית חבילה, או תיקיית RomFS של מוד קיים.
סמן מוד באמצעות לחיצה כפולה. בחר שם פרופיל ו־Seed, בדוק חבילות והפעל.
לכל פרופיל שמירה חדשה ונפרדת. שינוי המודים או ה־seed מחייב פרופיל אחר.
החבילה המקורית אינה נכתבת מחדש. המנהל משתמש בסביבת ההרצה הרגילה,
ואינו מפעיל אוטומטית את ניסוי הביצועים שנמסר בחבילה נפרדת.

מה כבר קיים: בדיקת גרסאות וגיבובים, איתור התנגשויות ותלויות, ייצור קבצים
חלופיים באמצעות מתכוני נתונים, ערבוב דטרמיניסטי לפי seed, והפעלה עם לוגים.
מה עדיין חסר: מיפוי טבלאות פוקימונים/מאמנים והכללים המיוחדים למשחק.
זה אינו רנדומייזר מוכן של Pokémon. קובץ הדוגמה הוא נתונים מומצאים ל־SDK
בנתיב שהמשחק אינו קורא; הוא לא משנה פוקימונים או דרגת קושי.

מודים שמחליפים קוד ARM/ExeFS דורשים התאמה לקוד המחשב המקופמל.
בדיקת hash אינה מוכיחה שמוד נתונים תואם לפורמט שהמשחק מצפה לו.
לא נבדקו DLC או בסיס 2.0.0. מעבר גרסה יצריך מתאם ובדיקות נפרדים.

18 בדיקות יחידה עברו. בדיקת המשחק אימתה רישום וקריאת קובץ חלופי זהה
למקור בתחום ה־RomFS שהורחב בזיכרון; נשמר גם צילום מהמשחק. זו אינה בדיקת
שינוי משחקיות. הממשק נבדק בייבוא, סימון ובדיקת חבילת דוגמה.

דוחות: workspace/profiles/<profile>/sessions/<time>/stderr.log
שמירות: workspace/profiles/<profile>/save
אם התהליך נסגר מיד, הממשק מציין זאת. שגיאת guest address range היא כשל
הקצאת כתובות בתחילת הריצה; אפשר לנסות הפעלה נוספת אחרי סגירת התהליך.
מטמוני הגרפיקה נפרדים בכל הפעלה בשלב זה, ולכן ייתכן חימום shaders חוזר.

Developer-Guide.txt וקוד המקור מצורפים. החבילה אינה כוללת משחק, מפתחות או DLC.
''')
    zipdir(MOUT/'source',MOUT/'Mod-Studio-source-0.1.0.zip')

    cp(OPT/'source/build/lasrecomp.exe',ROUT/'runtime/lasrecomp.exe')
    cp(OPT/'SDL3-3.4.18/x86_64-w64-mingw32/bin/SDL3.dll',ROUT/'runtime/SDL3.dll')
    cp(OPT/'SDL3-3.4.18/LICENSE.txt',ROUT/'licenses/SDL3.txt')
    cp(UP/'LICENSE',ROUT/'licenses/Runtime-MIT.txt')
    write(ROUT/'Launch-Optimized.ps1',LAUNCH)
    write(ROUT/'Play-Optimized.cmd','@echo off\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Optimized.ps1"\nif errorlevel 1 pause\n')
    for name in ['prepare.py','program_cache.inc','pipeline_cache.inc','run.py','suite_v3.py','Design-and-limits.txt','provenance.json']:
        cp(OPT/name,ROUT/'source/research/pokeza-pc/runtime-opt-r1'/name)
    for name in ['run_probe.py','summarize_benchmark.py']:
        cp(HERE/name,ROUT/'source/research/pokeza-pc'/name)
    for name in ['runtime/nvn/vulkan/exec.c','Makefile']:
        cp(OPT/'source'/name,ROUT/'source/modified-runtime'/name)
    cp(UP/'LICENSE',ROUT/'source/LICENSE-runtime.txt')
    diff=[]
    for name in ['runtime/nvn/vulkan/exec.c','Makefile']:
        diff.extend(difflib.unified_diff((UP/name).read_text().splitlines(True),(OPT/'source'/name).read_text().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
    write(ROUT/'source/runtime-opt-r1.patch',''.join(diff))
    write(ROUT/'source/BUILD.txt','''The archive contains modifications and the exact modified exec.c/Makefile, not game source.
Obtain https://github.com/Hexveil404/PokeZ-ARecomp at
4d82d8998adb75036c27f476e8d8f7e737bed36a into research/pokeza-recomp.
The checkout must be clean. Run research/pokeza-pc/runtime-opt-r1/prepare.py.
It creates a separate source copy and preserves the original checkout.
See Design-and-limits.txt for toolchain, SDL package hash and make command.
The tested game library ABI is 7b03da558e0b6144. Game assets/library are not
included. run.py/suite_v3.py use existing private test saves and r2 library.
They cannot reproduce gameplay from this source archive alone.
''')
    cp(OPT/'Design-and-limits.txt',ROUT/'Design-and-limits.txt')
    measurements=[]
    for name in ['35-revision-control-a','36-revision-key-a','37-revision-ring-a','38-revision-ring-b','39-revision-key-b','40-revision-control-b']:
        run=HERE/'runs'/name
        b=json.loads((run/'benchmark.json').read_text())
        measurements.append(dict(run=name,fps=b['fps_interval_mean'],gap_ms=b['largest_reported_gap_ms']))
        for file in ['benchmark.json','method.json','probe-play.json','larecomp.ini']:
            cp(run/file,ROUT/'evidence'/name/file)
    for name in ['34-revision-shadow','41-final-shadow-ring16','42-baseline-validation']:
        run=HERE/'runs'/name
        for file in ['stderr.log','method.json','probe-play.json']:
            cp(run/file,ROUT/'evidence'/name/file)
    final=HERE/'runs/41-final-shadow-ring16'
    counts=re.findall(r'checks=(\d+) mismatches=0',(final/'stderr.log').read_text(errors='replace'))
    assert int(counts[-1])>1000000
    for num in ['00900','02100']:
        cp(final/f'build/frames/frame_{num}.png',ROUT/f'evidence/final-frame-{num}.png')
    control=(measurements[0]['fps']+measurements[5]['fps'])/2
    keys=(measurements[1]['fps']+measurements[4]['fps'])/2
    ring=(measurements[2]['fps']+measurements[3]['fps'])/2
    report=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),measurements=measurements,
        control_fps=control,key_empty_fps=keys,key_empty_16slots_fps=ring,percent_change=(ring/control-1)*100,
        final_runtime_sha256=sha(ROUT/'runtime/lasrecomp.exe'),benchmark_runtime_sha256=json.loads((HERE/'runs/37-revision-ring-a/method.json').read_text())['runtime_sha256'],
        post_benchmark_change='Constrain target dereference loop to active pass_ncolor, matching original constructor',
        final_shadow_comparisons=int(counts[-1]),shadow_mismatches=0,
        validation='PointSize/topology VUIDs also reproduced with every new optimization disabled; not a clean Vulkan validation pass.',
        scope='Repeated one-scene startup/save reload/movement tests, not whole-game or DLC validation',
        promoted_to_stable=False)
    js(ROUT/'verification.json',report)
    write(ROUT/'Report-he.txt',f'''Pokémon Z-A — ניסוי שיפור סביבת הריצה r1 — 25.10.2026

מחשב: Core i7-12700F, RTX 3050 8GB, זיכרון 32GB, Windows 11.
בסיס המשחק: 1.0.0. ספריית המשחק: Readable C r2 שנמסרה קודם.
סביבת הריצה נבנתה ממקור פתוח ב־commit 4d82d8998adb75036c27f476e8d8f7e737bed36a.
זהו קוד סביבת הריצה ושכבת התרגום; לא קוד המקור המקורי של Pokémon.

מה שונה
נשמרת תוצאה אחרונה של חישוב מפתח shader/pipeline כאשר כל התלויות זהות.
שינוי בפריסת קודקודים מסומן בגרסה במקום העתקת המבנה כולו בכל ציור.
הגשת עבודה ריקה ללא semaphores אינה ממתינה לאיפוס של תא שכבר סיים.
אפשר לבחור 8 או 16 תאים למחזור הגשות העבודה ל־GPU; ההמתנות לשימוש חוזר,
המחסומים וסדר פקודות ההעלאה והציור נשמרים. מצב הבסיס נשאר ברירת המחדל
בקוד. קובץ ההפעלה הניסיוני בוחר באפשרויות החדשות וב־16 תאים.

תוצאות מאותה סצנת סמטה, שש ריצות בסדר A-B-C-C-B-A
בסיס: {measurements[0]['fps']:.2f}, {measurements[5]['fps']:.2f}; ממוצע {control:.2f} FPS.
מטמון ודילוג על עבודה ריקה, 8 תאים: {measurements[1]['fps']:.2f}, {measurements[4]['fps']:.2f}; ממוצע {keys:.2f}.
אותו שילוב עם 16 תאים: {measurements[2]['fps']:.2f}, {measurements[3]['fps']:.2f}; ממוצע {ring:.2f}.
הפרש השילוב לעומת הבסיס: {(ring/control-1)*100:.2f}%. שיפור המטמון לבדו לא משמעותי כאן.
הרזולוציה והגדרות הציור זהות. החלון הנמדד הוא שניות 50–80 מתוך 90,
אחרי טעינה, עם תקרת 60 FPS. אלה ממוצעי דיווחים בני כשתי שניות, לא 1% lows.
לא הוכחה השגת 60 FPS יציבים. ריצות שונות בעבר אינן בסיס תקף להשוואה הזאת.

בדיקת תקינות
בגרסה הסופית נערכו {int(counts[-1]):,} השוואות מול חישוב המפתחות המקורי ללא אי־התאמה,
בריצה בת 110 שניות עם טעינת שמירה, תנועה וסיבוב מצלמה. נשמרו צילומים.
לאחר סדרת המדידה הוגבל טווח קריאת render targets כך שיתאים לקוד המקורי;
הגרסה הסופית עברה בדיקת shadow נוספת, אך סדרת ששת מדדי הביצועים לא חזרה
במלואה אחרי התיקון הקטן. שני גיבובי הקוד נרשמו ב־verification.json.
אזהרות Vulkan לגבי PointSize/topology הופיעו גם כאשר כל האפשרויות החדשות
כבויות. אין כאן אישור תקינות מלא של Vulkan או הוכחה שכל בעיות הציור נפתרו.
קרבות, DLC, קלט־לתמונה, צריכת זיכרון נוספת וסשן משחק ארוך לא נבדקו מחדש
עם השילוב הזה. יותר תאים עשויים לשנות צריכת זיכרון או השהיה; אלה לא נמדדו.

כיצד לפתוח
Play-Optimized.cmd משתמש בחבילת המשחק ובספריית Readable C r2 בתיקיות
האחיות שכבר קיימות במחשב זה. נדרשות גם התלויות המקומיות ב־C:/msys64/ucrt64/bin.
זו חבילת ניסוי למחשב הזה, לא חבילה ניידת עצמאית. אין צורך להחליף קבצים
בהתקנה הרגילה. היא מתחילה שמירה נפרדת ב־user-data/save ובברירת מחדל 30 FPS.
אפשר לבחור 60 בתפריט המשחק לצורך בדיקה, אבל אין הבטחה לביצועים האלה.

מה לא מומש
לא בוצע איחוד שרירותי של command lists, הסרת barriers, ציור מקבילי מלא,
PGO או fast-math גורף. הקוד משתמש במצב גלובלי ובהנחות סדר שצריך לפרק לפני
שינויים כאלה. Design-and-limits.txt מפרט את התלויות וההחלטות.
הניסוי לא קודם לגרסה היציבה, ולא נטען שהוא משפר את רזולוציית הצללים.

DLC ורנדומייזר
ב־tools/zaimport/Program.cs יש ייבוא בסיס/עדכון/DLC ושילוב RomFS עם עדכון.
tools/patches.py מכיר מזהי בנייה של 1.0.0 ו־2.0.0. זו תמיכה בקוד, לא בדיקה
של DLC שסופק בשיחה הזאת. עדיין לא התקבל DLC. נדרשים התאמת החבילות,
קימפול מתאים, שמירה נפרדת ובדיקת כניסה לתוכן. מנהל המודים כרגע מוגבל ל־1.0.0.
רנדומייזר חדש ייבנה על התשתית אחרי מיפוי הנתונים וכללי התקדמות תקפים.
''')
    zipdir(ROUT/'source',ROUT/'Runtime-optimization-source-r1.zip')
    for folder in [MOUT,ROUT]:
        js(folder/'SHA256.json',inventory(folder))
        zipdir(folder,OUT/(folder.name+'.zip'))
    js(HERE/'mod-runtime-delivery.json',dict(mod_studio=str(MOUT),runtime=str(ROUT),nas_copy_completed=False))
    print(json.dumps(dict(mod_studio=str(MOUT),runtime=str(ROUT),performance=report),indent=2))

if __name__=='__main__':main()

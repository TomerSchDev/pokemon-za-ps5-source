"""Versioned r27 update/source/evidence delivery; excludes game assets and saves."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args(); out = a.out.resolve()
    assert out.parent == ROOT / 'deliverables' and not out.exists()
    package = ROOT / 'artifacts/randomizer-r27-play'
    record = json.loads((package / 'r27-package-verification.json').read_text(encoding='utf-8'))
    assert record['pc_money_proof_accepted'] and record['only_package_changes'] == ['eboot.bin']
    assert digest(package / 'PPSA91762/eboot.bin') == record['eboot_sha256']
    proof = json.loads((ROOT / 'port/cheats-r27/evidence/pc-proof.json').read_text())
    assert all(proof[key] for key in ('pc_verified', 'ui_verified', 'save_verified', 'off_verified', 'cap_verified', 'reload_verified'))
    out.mkdir(parents=True)
    nas = Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port') / out.name
    status = dict(version='r27-play', at=datetime.now(timezone.utc).isoformat(),
                  base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  eboot_sha256=record['eboot_sha256'], pie_sha256=record['candidate_pie_sha256'],
                  built_and_packaged=True, installed=False, hardware_tested=False,
                  pending='Close the currently running console game, then verified current-save backup and installation.',
                  features=['trainer name for new runs', 'one-shot MONEY additions'],
                  preserved=['r26p1 runtime', 'FPS TRIAL', 'FPS counter', 'threaded submission', 'slot depth 64',
                             'shader compilation/cache', 'all packaged options and assets'],
                  money_pc_results={k: proof[k] for k in ('normal', 'cap', 'off')},
                  tests=dict(name='ASan/UBSan lifecycle tests, PKHeX refreshed 3/3, PS5 -Werror',
                             money='ASan/UBSan concurrency/cancellation/cap, exact source patcher, actual PC UI/save/reload',
                             overlay='real overlay plus MONEY runtime, rendered-label regression, FPS and existing cheats',
                             installer='7 offline rollback/transaction guard tests',
                             image='5 changed game members only; runtime/imports/registrations/FPS/timing retained'),
                  limitations=['MONEY menu header may need one more close/open to refresh',
                               'Name and MONEY interactions not yet verified on PS5 hardware',
                               'ITEMS and ALPHA not implemented in this milestone',
                               'Legacy r11 repair remains restricted; named r27 runs are not eligible'],
                  hebrew_translation_modified=False, nas=str(nas))
    (out / 'Results.json').write_text(json.dumps(status, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    report = '''r27-play — תוצאות המשך מסמך ההעברה, 29.10.2026

נבנתה ונארזה גרסת r27-play על בסיס r26p1. היא מוכנה להתקנה; עדיין לא הותקנה ולא נבדקה על PS5. בעת הבדיקה האחרונה זוהה משחק פעיל בקונסולה ונשלחה בקשה לסגור אותו לפני גיבוי והחלפה.

מה נוסף:
• בחירת שם מאמן במקלדת לריצות חדשות. Continue, הריצות הקודמות ושמירות ההתקדמות נשמרים ללא שינוי.
• MONEY בתפריט L3+R3: תוספת חד־פעמית של 10,000 / 100,000 / 1,000,000, עם תקרה 9,999,999, ביטול בקשה ממתינה וכיבוי בטעינה מחדש.
• FPS TRIAL, מונה FPS וכל רכיבי הביצועים של r26p1 נשמרו. רק eboot.bin שונה בחבילת האפליקציה.

בדיקות משחק ממשיות במחשב:
• 10,384 + 10,000 = 20,384; הסכום הופיע במשחק ונשמר. PKHeX אימת את השמירה ואת הקבוצה.
• 9,999,990 + 1,000,000 = 9,999,999; התקרה הופיעה בתפריט עוד לפני השמירה, ואומתה גם לאחריה.
• טעינה חוזרת עם הצ׳יט כבוי: 9,999,999, ללא תוספת חוזרת וללא שינוי בעותק השמירה.
• כל הבדיקות נעשו על עותקים; שמירות המקור נשארו ללא שינוי.

בדיקות קוד ובנייה:
בדיקות sanitizers לשם, מחזור חיי ריצות, כסף ותפריט עברו. בדיקות התפריט אימתו גם את ההתנהגות הקיימת של FPS TRIAL, SHINY ו־CAPTURE. שבע בדיקות הגנה של המתקין עברו. קומפילציה ל־PS5 עם Werror עברה. חמש יחידות הכסף הן היחידות שהוחלפו בארכיון המשחק; יתר רכיבי המשחק וה־runtime נשארו זהים. נבדקו חיבורי הפונקציות, imports ורישומי runtime. בודק הבנייה תוקן כדי לזהות wrapper מקומי שכבר היה מקומי גם בגרסה הקודמת; קוד המשחק והבינארי לא השתנו בתיקון הבודק, והתיעוד המקורי נשמר.

הפעלת MONEY:
בחר סכום עם ימין/שמאל ולחץ X. סגור את תפריט הצ׳יטים ופתח את תפריט המשחק, או שמור מתוך המשחק. QUEUED הוא בקשה ממתינה; ADDED הוא שינוי שהוחל בפועל. כותרת הכסף במשחק עשויה להתעדכן רק בסגירה ופתיחה נוספת של התפריט. שמור כדי לשמור את הכסף להפעלה הבאה. NORMAL מבטל רק בקשה שטרם הוחלה.

המשך:
גיבוי מאומת ועדכני, התקנת eboot בלבד כשהמשחק סגור, ובדיקת התפריט, שם חדש, Continue וכסף ב־PS5. לא בוצעו שינויי עברית, ITEMS, ALPHA, סצנות או תזמון דינמי חדש.
'''
    report += '\nSHA-256 eboot: ' + record['eboot_sha256'] + '\nNAS: ' + str(nas) + '\n'
    (out / 'Results-HE.txt').write_text(report, encoding='utf-8')
    shutil.copyfile(ROOT / 'port/perf-r27/README-HE.txt', out / 'README-HE.txt')
    shutil.copyfile(ROOT / 'STATUS-HANDOFF-20261029-HE.md', out / 'STATUS-HANDOFF-r27-20261029-HE.md')
    # Binary update deliberately contains no unchanged data files or settings.
    with zipfile.ZipFile(out / 'ZA-r27-Update.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.write(package / 'PPSA91762/eboot.bin', 'PPSA91762/eboot.bin')
        for n in ('README-HE.txt', 'Results-HE.txt'): z.write(out / n, n)
        z.write(package / 'r27-package-verification.json', 'r27-package-verification.json')
        for f in sorted((package / 'evidence/r27').rglob('*')):
            if f.is_file(): z.write(f, f.relative_to(package).as_posix())
    allow = {'.c', '.cpp', '.h', '.hpp', '.py', '.sh', '.cs', '.csproj', '.md', '.txt', '.json', '.log', '.s', '.png'}
    selected = {}
    for rel in ('port/perf-r27', 'port/cheats-r27', 'port/rando-v2', 'evidence/r27-build-audit',
                'evidence/r27-money-static', 'evidence/perf-r27'):
        for f in (ROOT / rel).rglob('*'):
            if not f.is_file() or f.suffix not in allow: continue
            if any(part in {'__pycache__', 'obj', 'bin', 'research'} for part in f.relative_to(ROOT / rel).parts): continue
            assert f.stat().st_size < 8 << 20, f
            selected[f.relative_to(ROOT).as_posix()] = f
    diff = subprocess.check_output(['git', 'diff', '--', 'port/rando-v2'], cwd=ROOT)
    with zipfile.ZipFile(out / 'ZA-r27-Source-Evidence.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, f in sorted(selected.items()): z.write(f, name)
        z.writestr('tracked-name-changes.patch', diff)
        z.writestr('SOURCE-NOTE.txt', 'Targeted r27 sources/tests/evidence over repository commit ' + status['base_commit'] +
                   '. Existing PS5 SDK/runtime and r26p1 baseline are prerequisites. No game ROMs, saves, keys, dependencies or generated game C are included.\n')
    hashes = {f.name: digest(f) for f in sorted(out.iterdir()) if f.is_file()}
    (out / 'SHA256.json').write_text(json.dumps(hashes, indent=2) + '\n')
    # Versioned destination must be new or already contain exactly these bytes.
    try:
        nas.mkdir(parents=True, exist_ok=True)
        copied = []
        for f in sorted(out.iterdir()):
            target = nas / f.name
            if target.exists(): assert digest(target) == digest(f), 'Existing different NAS version: ' + str(target)
            else: shutil.copyfile(f, target)
            assert digest(target) == digest(f)
            copied.append(f.name)
        print(json.dumps(dict(out=str(out), nas=str(nas), nas_sha256_verified=True, files=copied), ensure_ascii=False))
    except (OSError, AssertionError) as error:
        print(json.dumps(dict(out=str(out), nas=str(nas), nas_sha256_verified=False, error=str(error)), ensure_ascii=False))
        raise


if __name__ == '__main__': main()

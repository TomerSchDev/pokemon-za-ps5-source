"""Package a completed r27b installation; never contacts the console or reads saves.

Run only after updating the handoff with the successful installation and hash.
Both --hardware (installation.json) and a fresh versioned --out are mandatory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'r27b-play'
BASE_SHA = 'c382275b90704d50e50e57875116bd69341e6c6b9c9c4e4d43223b367e19f7fa'
EBOOT_SHA = 'c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153'
REJECTED_HARDWARE = ROOT / 'evidence/r27-hardware-20261029-1653Z'
SOURCE_DIRS = (
    'port/perf-r27', 'port/cheats-r27', 'port/rando-v2',
    'evidence/r27-build-audit', 'evidence/r27-money-static',
    'evidence/perf-r27', 'evidence/perf-r27b',
)
SOURCE_SUFFIXES = {'.c', '.cpp', '.h', '.hpp', '.py', '.sh', '.cs', '.csproj',
                   '.md', '.txt', '.json', '.log', '.s', '.png'}
SKIP_PARTS = {'__pycache__', 'obj', 'bin', 'research', 'save', 'saves',
              'save-backup', 'original', 'installed', 'node_modules'}
PACKAGE_EVIDENCE = {
    'build-verification.json', 'sources.json', 'money-hook-manifest.json',
    'archive.json', 'registration.json', 'pc-proof-accepted.json',
    'package-verification.json', 'flags-control.txt',
    'incremental-verification.json', 'copy-verification.json',
}
HARDWARE_JSON = ('installation.json', 'transaction.json',
                 'startup-verification.json', '30fps-verification.json')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def checked_file(path, root, limit=8 << 20):
    require(path.is_file() and not path.is_symlink(), 'Missing or linked file: ' + str(path))
    require(path.resolve().is_relative_to(root.resolve()), 'Path outside allowed root: ' + str(path))
    require(path.stat().st_size < limit, 'Unexpectedly large evidence file: ' + str(path))
    return path


def validate_saves(checks):
    require(isinstance(checks, list) and len(checks) >= 2, 'Missing save checks')
    require({'report.json', 'save/save_0/main'} <= {c.get('path') for c in checks},
            'Missing current report/main hash checks')
    require(all(c.get('unchanged') is True and re.fullmatch(r'[0-9a-f]{64}', c.get('sha256', ''))
                for c in checks), 'A save check did not pass')


def validate_transaction(transaction, old_sha, new_sha):
    require(transaction.get('only_files') == ['eboot.bin'], 'Unexpected transaction files')
    files = transaction.get('files', [])
    require(len(files) == 1, 'Expected exactly one transaction file')
    entry = files[0]
    require(entry.get('file') == 'eboot.bin' and entry.get('old_sha256') == old_sha
            and entry.get('new_sha256') == new_sha, 'Transaction hashes do not match')
    require(entry.get('stage_readback_verified') is True and entry.get('final_readback_verified') is True,
            'Transaction readback verification missing')


def select_hardware(hardware_path, record):
    hardware = hardware_path.resolve()
    require(hardware.name == 'installation.json' and hardware.parent.parent == ROOT / 'evidence'
            and hardware.parent.name.startswith('r27b-hardware-'), 'Expected r27b hardware installation.json')
    folder = hardware.parent
    require(not (folder / 'rollback.json').exists(), 'This r27b installation was rolled back')
    selected = {}
    for name in HARDWARE_JSON:
        selected['hardware/r27b/' + name] = checked_file(folder / name, folder)
    installed = read_json(hardware)
    require(installed.get('installed') is True and installed.get('version') == VERSION,
            'Successful r27b installation is required')
    require(installed.get('installed_sha256') == EBOOT_SHA and installed.get('only_replaced') == ['eboot.bin'],
            'Installed image differs from the accepted package')
    for flag in ('configs_unchanged', 'ini_unchanged', 'active_run_and_preferences_unchanged'):
        require(installed.get(flag) is True, 'Missing preservation check: ' + flag)
    validate_saves(installed.get('save_check'))
    package_at_install = installed.get('pc_money_proof', {})
    for key in ('version', 'eboot_sha256', 'candidate_pie_sha256', 'base_eboot_sha256',
                'launcher_observer_call_verified'):
        require(package_at_install.get(key) == record[key], 'Installation package mismatch: ' + key)
    validate_transaction(read_json(folder / 'transaction.json'), BASE_SHA, EBOOT_SHA)
    startup = read_json(folder / 'startup-verification.json')
    require(startup.get('version') == VERSION and startup.get('force60_off') is True,
            'Missing r27b startup verification')
    require(startup.get('effective_slots') in (8, 64) and startup.get('fps_counter_setting') in (0, 1),
            'Unexpected startup settings')
    fps = read_json(folder / '30fps-verification.json')
    require(fps.get('passed') is True and installed.get('smoke_test') == fps,
            'Installation and measured FPS receipts differ')
    validate_saves(fps.get('save_check'))
    require(fps['save_check'] == installed['save_check'], 'Save hashes changed between checks')
    timing = fps['timing']
    rate = fps['fps']
    require(isinstance(rate, (int, float)) and math.isfinite(rate) and round(rate, 2) == 30.00,
            '30 FPS acceptance has not passed')
    require(timing['all_intervals']['interval_rate_fps'] == rate
            and timing.get('fps_modes') == [0] and timing.get('capture_inside_window') is False,
            'Unexpected measurement mode or interval rate')
    ack = fps['receipt']['ack']
    require(ack.get('op') == 'measure' and ack.get('result') == 'complete', 'Incomplete FPS measurement')
    for label, embedded in (('ready', None), ('before-30fps-check', fps['before']),
                            ('after-30fps-check', fps['after'])):
        snapshot_dir = folder / 'r26p-first-boot' / label
        snapshot_file = checked_file(snapshot_dir / 'snapshot.json', folder)
        snapshot_record = read_json(snapshot_file)
        validate_saves(snapshot_record.get('save_check'))
        require(snapshot_record['save_check'] == installed['save_check'],
                'Snapshot save hashes differ: ' + label)
        snapshot = snapshot_record['receipt']
        if embedded is not None:
            require(snapshot == embedded, 'Snapshot differs from FPS receipt: ' + label)
        require(snapshot['ack']['op'] == 'snapshot' and snapshot['ack']['result'] == 'saved',
                'Incomplete snapshot: ' + label)
        selected['hardware/r27b/' + snapshot_file.relative_to(folder).as_posix()] = snapshot_file
        pngs = snapshot.get('files', [])
        require(len(pngs) == 1, 'Expected a single selected snapshot PNG')
        entry = pngs[0]
        require(re.fullmatch(r'frame_[0-9]+_[0-9]+\.png', entry['name'])
                and entry.get('readback_verified') is True, 'Invalid snapshot filename or receipt')
        png = checked_file(snapshot_dir / entry['name'], folder, limit=12 << 20)
        require(png.stat().st_size == entry['bytes'] and digest(png) == entry['sha256'],
                'Snapshot hash mismatch: ' + label)
        selected['hardware/r27b/' + png.relative_to(folder).as_posix()] = png
    rollback_file = checked_file(REJECTED_HARDWARE / 'rollback.json', REJECTED_HARDWARE)
    rollback = read_json(rollback_file)
    require(rollback.get('verified') is True and rollback.get('save_never_restored') is True,
            'First r27 rollback has not been verified')
    require(len(rollback['files']) == 1 and rollback['files'][0]['file'] == 'eboot.bin'
            and rollback['files'][0]['new_sha256'] == BASE_SHA
            and rollback['files'][0]['stage_readback_verified'] is True
            and rollback['files'][0]['final_readback_verified'] is True,
            'First r27 rollback did not restore the pinned baseline')
    selected['hardware/rejected-r27/rollback.json'] = rollback_file
    return installed, startup, fps, rollback, selected


def select_sources():
    selected = {}
    for rel in SOURCE_DIRS:
        folder = ROOT / rel
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            parts = path.relative_to(folder).parts
            if any(part.lower() in SKIP_PARTS for part in parts):
                continue
            # Exclude raw runtime logs; keep test/build logs and curated JSON proof.
            if any(word in path.name.lower() for word in ('klog', 'stderr', 'stdout', '-control.log')):
                continue
            selected[path.relative_to(ROOT).as_posix()] = checked_file(path, folder)
    # The restored r17 observer declaration is an explicit r27b build input.
    header = ROOT / 'port/observer-r17/observer.h'
    selected['port/observer-r17/observer.h'] = checked_file(header, ROOT / 'port/observer-r17')
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware', required=True, type=Path, help='Successful r27b installation.json')
    parser.add_argument('--out', required=True, type=Path, help='Fresh versioned folder under deliverables/')
    args = parser.parse_args()
    out = args.out.resolve()
    require(out.parent == ROOT / 'deliverables' and not out.exists()
            and re.fullmatch(r'r27b-play-[0-9]{8}-[0-9]{4,6}Z(?:-[A-Za-z0-9]+)?', out.name),
            'Use a fresh deliverables/r27b-play-YYYYMMDD-HHMMSSZ folder')
    package = ROOT / 'artifacts/randomizer-r27b-play'
    receipt_file = package / 'r27-package-verification.json'
    record = read_json(checked_file(receipt_file, package))
    require(record.get('version') == VERSION and record.get('base_eboot_sha256') == BASE_SHA
            and record.get('eboot_sha256') == EBOOT_SHA, 'Wrong package or baseline')
    require(record.get('pc_money_proof_accepted') is True
            and record.get('only_package_changes') == ['eboot.bin']
            and record.get('launcher_observer_call_verified') is True, 'Package acceptance missing')
    require(record['incremental']['verified'] is True
            and record['incremental']['changed_objects'] == ['native_menu.o', 'title_entry.o']
            and all(record['incremental'][key] is True for key in
                    ('runtime_byte_identical', 'money_tree_byte_identical', 'timing_tree_byte_identical')),
            'r27b incremental verification missing')
    eboot = checked_file(package / 'PPSA91762/eboot.bin', package, limit=512 << 20)
    require(digest(eboot) == EBOOT_SHA, 'Package eboot SHA-256 mismatch')
    for name, expected in record['source_sha256'].items():
        source = checked_file(ROOT / name, ROOT)
        require(digest(source) == expected, 'Built source changed: ' + name)
    package_evidence = {}
    require(set(record['evidence']) == {'evidence/r27/' + n for n in PACKAGE_EVIDENCE},
            'Unexpected package evidence manifest')
    for name, expected in record['evidence'].items():
        source = checked_file(package / name, package)
        require(digest(source) == expected, 'Package evidence hash mismatch: ' + name)
        package_evidence[name] = source
    proof_file = ROOT / 'port/cheats-r27/evidence/pc-proof.json'
    proof = read_json(proof_file)
    require(digest(proof_file) == record['pc_money_proof']['proof_sha256'], 'PC proof changed')
    require(all(proof.get(key) is True for key in
                ('pc_verified', 'ui_verified', 'save_verified', 'off_verified', 'cap_verified', 'reload_verified')),
            'PC proof is incomplete')
    negative = read_json(ROOT / 'evidence/perf-r27b/negative-r27-control/result.json')
    require(negative.get('passed') is True and negative.get('old_r27_correctly_rejected') is True
            and 'za_observer_menu' in negative.get('reason', ''), 'Missing observer negative control')
    installed, startup, fps, rollback, hardware_files = select_hardware(args.hardware, record)
    handoff = ROOT / 'STATUS-HANDOFF-20261029-HE.md'
    handoff_text = handoff.read_text(encoding='utf-8')
    require(VERSION in handoff_text and EBOOT_SHA in handoff_text,
            'Update the handoff with successful r27b installation and full SHA-256 first')
    sources = select_sources()
    diff = subprocess.check_output(['git', 'diff', '--', 'port/rando-v2'], cwd=ROOT)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    nas = Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port') / out.name
    timing = fps['timing']['all_intervals']
    status = dict(
        version=VERSION, at=datetime.now(timezone.utc).isoformat(), base_commit=commit,
        installed=True, installed_at=installed['at'], eboot_sha256=EBOOT_SHA,
        baseline_version='r26p1-play', baseline_eboot_sha256=BASE_SHA,
        pie_sha256=record['candidate_pie_sha256'], only_replaced=['eboot.bin'],
        hardware_boot_and_30fps_verified=True, ps5_name_interaction_verified=False,
        ps5_money_interaction_verified=False, new_60fps_claim=False,
        fps_observed=fps['fps'], fps_measurement=fps['timing']['measurement'],
        fps_all_intervals=timing, fps_receipt_at=fps['at'], startup=startup,
        save_check=installed['save_check'], configs_unchanged=True, ini_unchanged=True,
        active_run_and_preferences_unchanged=True,
        first_r27=dict(failure='Missing za_observer_menu call; automated Continue timed out',
                       rollback_verified=True, save_never_restored=True, rollback_at=rollback['at']),
        r27b_observer_hook_restored=True, old_r27_negative_control=negative,
        money_pc_verified=True, money_pc_results={k: proof[k] for k in ('normal', 'cap', 'off')},
        preserved=['FPS TRIAL', 'FPS counter preference', 'r26p1 runtime', 'existing options and saves'],
        limitations=['PS5 NAME and MONEY interactions remain unverified',
                     'CPU present-submission intervals do not measure scanout or simulation speed',
                     'MONEY header may require a second close/open to refresh',
                     'ITEMS and ALPHA are not implemented in this milestone'],
        hebrew_translation_modified=False,
        hardware_evidence_sha256={n: digest(p) for n, p in hardware_files.items()},
        nas_destination=str(nas), nas_copy_status='See packaging command result; success requires SHA-256 verification')
    report = f'''r27b-play — תוצאות ההתקנה והבדיקות

r27b-play הותקנה ב־PS5 בהצלחה לפי אישור ההתקנה מ־{installed['at']}.
הוחלף eboot.bin בלבד, על בסיס r26p1. קובצי ההגדרות, קובץ INI, הריצה הפעילה, העדפות המשתמש והשמירה הקיימת נבדקו ונשארו ללא שינוי. אין בחבילה שמירות משחק או גיבוי בינארי של הגרסה הקודמת.

מדידת הביצועים בפועל: {fps['fps']:.6f} FPS במשך {timing['duration_s']:.3f} שניות, על פני {timing['intervals']} מרווחים. זהו קצב מרווחי הגשת התמונה ב־CPU ל־vkQueuePresentKHR; המדידה אינה מודדת סריקת מסך או מהירות סימולציה. צילום המסך נעשה מחוץ לחלון המדידה. המצב שנבדק הוא 30 FPS ו־force60 כבוי. אין כאן טענה חדשה ל־60 FPS. FPS TRIAL ומונה FPS הקיימים נשמרו; ערך העדפת המונה בזמן האתחול: {startup['fps_counter_setting']}.

בניסיון הראשון, r27 לא השלימה Continue אוטומטי משום שחיבור za_observer_menu מתפריט r17 הושמט. המתקין החזיר בבטחה את eboot של r26p1 ואימת אותו; לא שוחזרה שמירה ישנה על ההתקדמות. ב־r27b הוחזר החיבור, והבודק מאמת את הקריאה בבינארי. בדיקת ביקורת שלילית דחתה את תמונת r27 הישנה בשל הקריאה החסרה. בהשוואה ל־r27 השתנו native_menu.o ו־title_entry.o בלבד; קוד הכסף, ה־runtime והתזמון נותרו זהים.

מה נוסף: בחירת NAME לריצות חדשות בלבד, ותוספות MONEY חד־פעמיות של 10,000 / 100,000 / 1,000,000, עד תקרה של 9,999,999. Continue ו־Saved Runs שומרים על שמות ושמירות הריצות הקיימות.

בדיקות NAME ו־MONEY האינטראקטיביות ב־PS5 עדיין לא אומתו. בדיקות המחשב עברו: NAME עבר בדיקות מחזור חיים, שחזור דטרמיניסטי ו־PKHeX; MONEY עבר משחק ממשי עם תצוגה, שמירה וטעינה מחדש. במחשב נמדדו {proof['normal']['before']:,} + {proof['normal']['request']:,} = {proof['normal']['after']:,}; בדיקת התקרה הגיעה ל־{proof['cap']['after']:,}; טעינה עם MONEY כבוי שמרה על {proof['off']['reloaded_value']:,} ללא תוספת חוזרת. אלו בדיקות מחשב, ולא אישור להפעלת NAME או MONEY ב־PS5.

בדיקות sanitizers לשם, לכסף ולתפריט, קומפילציה ל־PS5, בדיקות FPS TRIAL בתפריט ובדיקות ההגנה של המתקין עברו. ראיות הבנייה והבדיקות כלולות בארכיון המקור. לא נעשו שינויים בתרגום לעברית, ITEMS או ALPHA במסגרת זו.

SHA-256 eboot מותקן: {EBOOT_SHA}
SHA-256 בסיס r26p1: {BASE_SHA}
יעד העתקת NAS: {nas}
העתקת NAS נחשבת מאומתת רק לאחר הודעת nas_sha256_verified=true מתהליך האריזה.
'''
    save_hash_lines = '\n'.join(f"{c['path']}: {c['sha256']} (ללא שינוי)" for c in installed['save_check'])
    report += '\nSHA-256 של השמירה והדוח שנבדקו:\n' + save_hash_lines + '\n'
    readme = f'''r27b-play — שם מאמן וצ׳יט כסף לרנדומייזר Z-A

מצב: הותקנה בהצלחה ונבדקה עלייה למשחק ומדידת 30 FPS. הנתונים המדויקים וההסתייגויות מופיעים ב־Results-HE.txt וב־Results.json. NAME ו־MONEY האינטראקטיביים עדיין לא אומתו ב־PS5; בדיקות המחשב שלהם עברו. FPS TRIAL ומונה FPS נשמרו, ללא טענה חדשה לביצועי 60 FPS.

שם מאמן: בתפריט הרנדומייזר בחר NAME, הזן עד 12 תווים ואשר DONE. השם חל על ריצה חדשה בלבד ועל המאמן המקורי של הפוקימונים השייכים לה. Continue ו־Saved Runs משאירים ריצות קיימות כפי שהן. Triangle מחליף אותיות גדולות/קטנות.

MONEY: בתוך המשחק לחץ L3+R3, בחר MONEY וסכום בעזרת ימין/שמאל, ולחץ X פעם אחת. QUEUED הוא בקשה ממתינה; ADDED הוא שינוי שהוחל. סגור את תפריט הצ׳יטים ופתח את תפריט המשחק או שמור מתוך המשחק. התקרה היא 9,999,999. שינוי הסכום או NORMAL מבטלים בקשה ממתינה בלבד. טעינה מחדש מאפסת את הצ׳יט; סכום שכבר הוחל נשאר ויש לשמור כדי לשמרו להפעלה הבאה. בבדיקת המחשב נדרשה לעיתים סגירה ופתיחה נוספת של תפריט המשחק לרענון כותרת הכסף.

חבילת ZA-r27b-Update.zip כוללת eboot.bin בלבד תחת PPSA91762, עם דוחות ואישורי בנייה. היא אינה כוללת ROM, שמירות, הגדרות משחק חלופיות, בינארי גיבוי או קובץ PIE לצורכי ניפוי. אין להחליף תיקיית משחק שלמה באמצעותה.
התקנה מנוהלת: port/perf-r27/install_r27.py, רק כאשר המשחק סגור ובהתאם לתהליך הגיבוי והאימות. אין להעתיק שמירה ישנה על התקדמות קיימת.

בנייה:
bash port/perf-r27/build-r27b-play.sh build
bash port/perf-r27/build-r27b-play.sh package /absolute/path/to/pc-proof.json
המקור המצורף הוא שכבת השינויים והראיות על בסיס Git המתועד ב־Results.json; סביבת SDK/runtime ובסיס r26p1 קיימים נדרשים בנפרד.

השינוי מ־r27 ל־r27b מחזיר את קריאת za_observer_menu; ניסיון r27 הראשון בוטל והבינארי הקודם הוחזר בבטחה. הראיות כוללות גם את אישור החזרה ואת בדיקת הביקורת השלילית.
SHA-256 eboot: {EBOOT_SHA}
'''
    # All validation above is read-only. Never overwrite an earlier delivery.
    out.mkdir(parents=True, exist_ok=False)
    (out / 'Results.json').write_text(json.dumps(status, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (out / 'Results-HE.txt').write_text(report, encoding='utf-8')
    (out / 'README-HE.txt').write_text(readme, encoding='utf-8')
    handoff_name = 'STATUS-HANDOFF-r27b-20261029-HE.md'
    (out / handoff_name).write_text(handoff_text, encoding='utf-8')
    with zipfile.ZipFile(out / 'ZA-r27b-Update.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        archive.write(eboot, 'PPSA91762/eboot.bin')
        for name in ('README-HE.txt', 'Results-HE.txt', 'Results.json', handoff_name):
            archive.write(out / name, name)
        archive.write(receipt_file, 'r27-package-verification.json')
        for name, path in sorted(package_evidence.items()):
            archive.write(path, name)
        for name, path in sorted(hardware_files.items()):
            archive.write(path, name)
    with zipfile.ZipFile(out / 'ZA-r27b-Source-Evidence.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted({**sources, **hardware_files}.items()):
            archive.write(path, name)
        archive.write(receipt_file, 'artifacts/randomizer-r27b-play/r27-package-verification.json')
        for name in ('README-HE.txt', 'Results-HE.txt', 'Results.json', handoff_name):
            archive.write(out / name, name)
        archive.writestr('tracked-name-changes.patch', diff)
        archive.writestr('SOURCE-NOTE.txt', 'Targeted r27b sources/tests/evidence over repository commit ' + commit +
                         '. Existing PS5 SDK/runtime and r26p1 baseline are prerequisites. No game ROMs, saves, keys, dependencies, raw klog, backup binaries or generated game C are included. Source-tree historical README files describe their original revision; use the top-level r27b README and Results for current status.\n')
    hashes = {path.name: digest(path) for path in sorted(out.iterdir()) if path.is_file()}
    (out / 'SHA256.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
    try:
        nas.mkdir(parents=True, exist_ok=True)
        # Preflight the entire destination before copying any final file.
        files = sorted(out.iterdir())
        for path in files:
            target = nas / path.name
            require(not target.exists() or digest(target) == digest(path), 'Existing different NAS version: ' + str(target))
        for path in files:
            target = nas / path.name
            if not target.exists():
                with path.open('rb') as source, target.open('xb') as destination:
                    shutil.copyfileobj(source, destination)
            require(digest(target) == digest(path), 'NAS SHA-256 mismatch: ' + str(target))
        print(json.dumps(dict(out=str(out), nas=str(nas), nas_sha256_verified=True,
                              files=[path.name for path in files]), ensure_ascii=False))
    except (OSError, ValueError) as error:
        print(json.dumps(dict(out=str(out), nas=str(nas), nas_sha256_verified=False,
                              local_deliverables_preserved=True, error=str(error)), ensure_ascii=False))
        raise


if __name__ == '__main__':
    main()

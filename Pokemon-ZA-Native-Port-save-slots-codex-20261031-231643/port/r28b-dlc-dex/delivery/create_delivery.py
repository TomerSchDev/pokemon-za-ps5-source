"""Package the two pinned, offline-tested PS5 candidates. Never contacts hardware.

prepare copies binaries/proofs and writes instructions. finalize incorporates the
real local queue receipt and creates verified release ZIPs. Source exports use an
explicit tools-only allowlist; game source/data/saves and state are never exported.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

PROJECT = Path(__file__).resolve().parents[3]
BUILD = Path(r"\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\r28b-dlc-dex-20261030-c01")
SHARED_STATE = PROJECT.parent / "console-install-state"
REMOTE = "/data/homebrew/PPSA91762/eboot.bin"
BASE_SHA = "5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea"
MUSIC_BASE_SHA = "43fc453648bc9c499cc154979b56cf693c2db5a05b81e12e8b751b669406d99e"
VARIANTS = {
    "r28b": ("randomizer-r28b-dlc-dex", "cd249e36d5c4bf98a9732c1f71923122b0b52fcd3ed48f1976232678297942f7", BASE_SHA),
    "r28b-music": ("randomizer-r28b-dlc-dex-music", "8e4280f0da65ec3d00cb77b559833f1e9c6e427009e79ec15b0fab45fbf5dc7e", MUSIC_BASE_SHA),
}
SOURCE_ROOTS = ("port/dlc-dex-unlock", "port/r28b-dlc-dex", "tools/console-install-queue")
EVIDENCE = ("feature-image-checks.json", "final-image.json", "image-checks.json",
            "image-preservation.json", "registration.json", "imports.json",
            "self-inspection.txt", "archive-vs-base.json", "archive-vs-r28.json",
            "control-rebuild.json", "copied-inputs.json", "link-inputs.txt",
            "runtime-inputs.txt", "feature-source-SHA256SUMS.txt",
            "linked-calls.json", "music-override-inputs.json")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def save_json(path, data):
    write(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def instructions(package, variant, expected, base):
    music = variant == "r28b-music"
    label = "r28b + MUSIC" if music else "r28b"
    write(package / "README-HE.md", f"""# {label} — פתיחת DLC Pokédex מוקדמת

חבילת eboot ל־PPSA91762, משחק 2.0.2 + Mega Dimension. כוללת את r28a עם texfix, ספירת Lumiose + Hyperspace במשימות, ופתיחה של הדגל האמיתי `FLAG_DLC_DEX_ENABLE`. {'כוללת גם את חמשת אובייקטי MUSIC המאומתים של r29.' if music else 'זו הגרסה הבסיסית; למוזיקה השתמשו בגרסת MUSIC המשולבת.'}

כשהמשחק קורא לבדיקת הדגל ומנהל הדגלים כבר מוכן, העזר משתמש ב־setter המקורי ומוודא readback=1. אין צורך לערוך שמירה מראש. דגלי Another Dimension, Donuts ושלב עלילת ה־DLC אינם משתנים. המנגנון אינו מעניק פוקימון.

במסלול המקורי של פתיחת ה־Pokédex, Mankey עשוי להתווסף כ־Seen אם עוד לא נראה. הוא אינו מסומן Caught ולא מתווסף לצוות. שמירה רגילה עשויה לשמר את הדגל ואת Seen; חזרה ל־eboot ישן אינה מבטלת שינוי שכבר נשמר.

הבנייה ובדיקות host/קישור עברו. **טרם בוצעה בדיקת משחק או שמירה/טעינה בקונסולה לחבילה הזו.** קראו INSTALL-HE.md, TEST-HE.md ו־MERGE-HE.md. מזהי הבנייה והראיות ב־BUILD-INFO.json וב־evidence/.

SHA-256 של PPSA91762/eboot.bin:
`{expected}`

ההתקנה מתואמת דרך תור מקומי משותף, המתואר ב־QUEUE-HE.md. התור ממתין ל־handoff מהסוכן האחר; הוא אינו מתקין אוטומטית ואינו מוכיח שהקונסולה פנויה. גרסאות הבסיס והמוזיקה הן חלופות: לא מתקינים אותן אחת אחרי השנייה.
""")
    write(package / "INSTALL-HE.md", f"""# התקנת {label} — PPSA91762 בלבד

משנים רק `{REMOTE}`. את השמירות, active.json, קובצי האפשרויות, נכסי העברית, המודלים וקובצי הריצות משאירים במקומם. פתיחת הדגל תתרחש בתוך המשחק לאחר הפעלה; אין כאן כלי עריכת שמירה.

## לפני ההתקנה

1. בדקו את התור המשותף וקבלו handoff ממשי מבעל הקונסולה הקודם. claim היא reservation מקומית בלבד. שמרו token אצל המתקין ועדכנו heartbeat כל דקה. אין להפסיק ניסוי פעיל או תהליך לא מזוהה.
2. לאחר שמירה וסגירה מסודרת של המשחק, ודאו שאין תהליך PPSA91762 פעיל.
3. צרו גיבוי טרי של **כל** תיקיות הריצות r… ושל active.json. חשבו SHA-256 לכל קובץ וקראו שוב את הקבצים מהקונסולה להשוואה. שמרו manifest וראיות. לא ממשיכים בלי גיבוי מאומת.
4. קראו בחזרה את eboot הנוכחי ושמרו עותק מקומי ונקודת חזרה בעלת שם ייחודי. הבסיס המותר לעבודה המוכנה הזו: `{base}`. זהו תנאי התאמה, לא טענה שזו הגרסה המותקנת כרגע.
5. אם ה־SHA שונה, זהו את השינויים ובצעו מיזוג לפי MERGE-HE.md. אין לשנות את hash הבסיס ב־job רק כדי לעקוף חסימה. חבילה עם שינויי קוד חדשים במודלים דורשת eboot משולב חדש.
6. תעדו את התנאים שנבדקו בפועל ב־readiness JSON עם ticket, זמן עדכני וקובצי ראיות. הפעילו heartbeat --begin-install לפי QUEUE-HE.md. בדקו שוב שאין lease אבודה לפני כל כתיבה לקונסולה.

## החלפה וקריאות אימות

7. העלו את PPSA91762/eboot.bin בשם זמני ייחודי, למשל eboot.bin.r28b-new-<ticket>.
8. קראו את הקובץ הזמני בחזרה. הגודל וה־SHA חייבים להתאים לחבילה. ה־SHA הצפוי: `{expected}`.
9. שנו את שם ה־eboot הנוכחי לשם גיבוי ייחודי, בלי לדרוס גיבוי קודם; לאחר מכן שנו את שם הקובץ הזמני ל־eboot.bin.
10. קראו שוב את eboot.bin והשוו לאותו SHA. אם הקריאה אינה תואמת, אל תפעילו את המשחק. שמרו את שני קובצי ה־readback והשלימו/סגרו את חלון ההתקנה באמצעות receipt או resolution אמיתי, לפי מצב ההחלפה.
11. ודאו שגיבוי כל השמירות ו־active.json עדיין תואם ל־manifest. בצעו את TEST-HE.md, ושחררו את הקונסולה בתום החלון. אין לסמן הצלחת חומרה על סמך בדיקות סטטיות בלבד.

## חזרה לאחור

כשהמשחק סגור, החזירו את **ה־eboot המדויק שנקרא לפני ההתקנה** באותו תהליך זמני → readback → rename → readback. כך נשמרים שינויי הקוד שהיו מותקנים. אין לשחזר שמירה ישנה מעל התקדמות חדשה. החזרת executable אינה מכבה דגל או מבטלת Seen שנשמרו כבר; לחבילה אין פעולת ביטול דגל.
""")
    write(package / "TEST-HE.md", f"""# בדיקת {label} בקונסולה

בדיקות אלו עדיין לביצוע. לאחר התקנה מאומתת, הפעילו קליטת klog לפני המשחק ושמרו תוצאות תחת evidence/r28b-hardware-<timestamp> מחוץ לחבילת ההפצה. השתמשו ב־Continue לריצה שנבחרה עם Tomer; אין לפתוח או להחליף ריצה לצורך הבדיקה בלי תיאום.

## 1. פתיחת הדגל והמסך

1. תעדו את מצב FLAG_DLC_DEX_ENABLE ואת שלב העלילה בעותק הגיבוי שלפני הבדיקה באמצעות קורא בלבד. אין להשתמש ב־set-system-flag של PKHeX לצורך הבדיקה.
2. פתחו את ה־Pokédex ואת בחירת ה־Hyperspace/DLC Dex. אם הדגל היה כבוי וה־getter המתוקן הגיע לביצוע, צפויה שורת `[dlc-dex-unlock-r1] state=4 flag=FLAG_DLC_DEX_ENABLE before=0 set_ok=1 after=1`. דגל שכבר פעיל עשוי לא להפיק שורה. היעדר שורה לבדו אינו מוכיח כישלון; ייתכן שהמסלול לא בוצע.
3. בדקו את שני מסכי ה־Pokédex, רשימות ריקות, מינים שנתפסו קודם, וחזרה לתפריט. תעדו צילום של המסך ותוצאת המעבר. הפתיחה אינה אמורה לקדם עלילת DLC, להפעיל Another Dimension או לפתוח Donuts.
4. Mankey עשוי להפוך ל־Seen דרך קוד המסך המקורי; אין לצפות ל־Caught או לפוקימון חדש בצוות. בתיעוד השוו שדות ממוקדים ולא hash של שמירה שלמה שממילא משתנה במשחק.
5. שמרו כרגיל, סגרו והפעילו Continue. בדקו שוב מסך ודגל מתוך עותק חדש של השמירה. זו בדיקת persistence שטרם בוצעה. הפעלת הבנייה שוב עלולה להדליק מחדש דגל כבוי, ולכן מסך פתוח לאחר Continue לבדו אינו מוכיח שהדגל נשמר בדיסק.
6. ודאו שדגלי Another Dimension, Donuts ו־SYS_WORK_DLC_PHASE לא השתנו בגלל הפתיחה. בצעו את ההשוואה בחלון ללא התקדמות עלילתית רגילה, ותעדו כל שינוי נוסף.

## 2. שימור texfix וספירת ה־Pokédex

חפשו בעלייה `[za-texguard] r28a texfix active`. בצעו לפחות 10 כניסות/יציאות מבניינים, 5 מעברי Wild Zone, 5 קרבות טבע וקרב מאמן אם זמין, 20 פתיחות תפריטים, 5 Flying Taxi, 3 שמירות והפעלה מחדש. צלמו שמיים באזורים שבהם הופיעו צורות כהות. רשמו `[za-native-fault]`, signal 11 וכל הודעת texguard; הודעת דילוג על טקסטורה משוחררת כשלעצמה אינה קריסה.

בדקו Number Registered במשימה ובקשות Mable: Lumiose=L ועוד Hyperspace=H, combined=L+H. חפשו `[dexcount]` בעת הערכת התנאי או פתיחת המסך. אם Main Mission 2 עדיין בשלב Register at least five species וב־combined לפחות 5, בדקו את trigger המעבדה. מתחת ל־5 הוא אינו אמור להתקדם. מיני DLC שנתפסו כבר אמורים להיספר ללא תפיסה מחדש. בקשות Hyperspace ייעודיות נשארות לפי Hyperspace בלבד. תיקון הספירה עצמו אינו כותב לשמירה; תוספת פתיחת הדגל כן משנה מצב חי.

## 3. רגרסיות ומסירה

בדקו ITEMS, MONEY, NAME, עברית, FPS TRIAL וטעינת המודלים שהיו מותקנים. {'בדקו גם MUSIC בתפריט, את המצב השמור ואת החלפת המוזיקה בהתאם לריצה; תוכנית MUSIC SHA fcef0023680e21a305b962d9962bcdafe518d0c9c899d50f841692f9d6471c70.' if music else 'אם בריצה נדרשת MUSIC, יש להשתמש בחבילה המשולבת ולא להתקין גרסה זו במקומה.'} שמרו klog מלא, צילומי המסכים, שני ה־readbacks ותוצאת שמירה/טעינה. פענוח כתובות texguard נעשה מול llvm-pie.elf של **הגרסה הזו**, לפי הנתיב ב־BUILD-INFO.json, עם הפחתת בסיס 0x400000 כפי שנדרש בכלי הקיים.

אין לטעון ש־rollback של executable מבטל שינויי שמירה. בדיקת חזרה לקובץ הקודם מתבצעת רק כשהמשחק סגור ובלי שחזור שמירה ישנה.
""")
    write(package / "MERGE-HE.md", f"""# שילוב פתיחת DLC Dex עם מודלים ומוזיקה

בסיס r28a המאומת נשמר. הבנייה הזו מוסיפה main_287.o אחד לארכיון dexcount ואת za_dlc_dex_unlock.o לשורת הקישור. texfix, main_261.o/main_310.o ו־za_dexcount.o נשמרו. {'גרסה זו כוללת גם את שינויי MUSIC ב־native_menu.o, run_store.o, title_entry.o ואת za_music.o ו־za_music_plan.o.' if music else 'לשילוב MUSIC קיימת חבילה נפרדת מוכנה, עם אותם texfix/dexcount/פתיחת דגל.'}

## מודלים שמשנים נתונים בלבד

אם ה־eboot המותקן זהה לבסיס המותר ב־INSTALL-HE.md, והמודלים משנים רק RomFS/mods, התקנת ה־eboot אינה מחליפה את קובצי המודלים. אין לדרוס wild tables, נכסים, קובצי ריצות, אפשרויות או active.json. אימות SHA של הבסיס עדיין חובה.

## מודלים שמשנים קוד

אם הסוכן האחר מוסיף שינויי eboot, יש ליצור **בנייה משולבת חדשה** מעל העץ המדויק שלו. שינוי שם גרסה אינו מספיק. אין להחליף אותו בחבילה הזו לפני מיזוג והוכחת שימור שינוייו.

כלי המיזוג ב־port/r28b-dlc-dex שבחבילת המקורות: prepare-merge-tree.py/prepare-merge.sh דורשים runtime-tree, base-out עם רשימות כל קלטי הקישור, archive, work חדש, ושלושה hashes מפורשים של eboot/PIE/archive. מתחילים ב־--audit-only של prepare-merge-tree.py; לאחר מכן prepare-merge.sh מעתיק קלטים לעץ חדש ומקשר ביקורת **זהה בית־לבית** ל־PIE הבסיס, ואז build-feature.sh מוסיף את התוספת.

אם main_287.o כבר השתנה, בקרת הקומפילציה תעצור. יש למזג את שני השינויים ברמת המקור ולקמפל פעם אחת; אין להחליף אובייקט ולהעלים שינוי קודם. כך גם ב־main_261/main_310 של dexcount או בקובצי runtime של texfix. אין לערוך את עצי הבסיס או את התיקיות המוגנות בזמן בנייה.

העץ המקומי של שתי הבניות המוכנות: /home/tomer/ps5-za-native/r28b-dlc-dex-20261030-c01; פלט הגרסה הזו: {variant}. זהו reference לקריאה בלבד. metadata, hashes וקלטי הקישור מתועדים ב־BUILD-INFO.json וב־evidence/. המקורות המוצעים הם toolkit משלים לריפו המקומי, ואינם כוללים קוד משחק מתורגם, נתוני משחק או SDK.

לפני התקנה חדשה: השוו imports ורישומים, עברו verify-r28a image/final-image, verify-feature-image, בדיקת ארכיון והמרת ELF→SELF; ב־MUSIC גם 33 קריאות מוזיקה. עדכנו manifest, חבילה ו־job עם hashes אמיתיים. העבודה הישנה בתור מתבטלת/מוחלפת במפורש כדי שלא יותקן בסיס ישן לאחר החדש.
""")
    queue_root = SHARED_STATE.as_posix()
    queue_tool = (PROJECT / "tools/console-install-queue/console_queue.py").as_posix()
    write(package / "QUEUE-HE.md", f"""# תור ההתקנות — הכנה ומסירה

התור המשותף היחיד לכל הקונסולה 192.168.1.135 נמצא ב־`{queue_root}`. גם סוכן Windows וגם סוכן WSL חייבים להשתמש באותה תיקיית NTFS. אין ליצור תור חדש ב־NAS או בתוך חבילה שחולצה.

```powershell
py -3 -I "{queue_tool}" --root "{queue_root}" status
```

הכלי המלא, דוגמאות readiness/receipt והוראות claim/heartbeat/complete מצורפים בתיקייה console-install-queue/. בזמן הרצה מהעותק המצורף תמיד העבירו --root עם הנתיב המשותף שלמעלה, כדי שלא ייווצר תור נפרד.

QUEUE-JOB.json הוא job קונקרטי עם hash ארטיפקט ובסיס צפוי. רק גרסת MUSIC מוגשת לתור כחבילת ההתקנה המועדפת; הגרסה הבסיסית היא חלופה ואינה עבודה נוספת אוטומטית. QUEUE-RECEIPT.json, אם צורף, הוא קבלה על הגשה מקומית בלבד. אין autorunner, אין התקנה שבוצעה ואין זמינות חומרה שהוכחה.

קיימת תלות בניסוי המודלים/Rowlet של הסוכן האחר. נדרש handoff לפני התקנה. התור אוכף בלעדיות בין משתתפים שאימצו אותו; הוא אינו חוסם פיזית כלי אחר שלא משתמש בו. lease stale אינה נלקחת אוטומטית. בסיס שאינו תואם מחייב זיהוי ומיזוג, גם אם הגיע תור העבודה.
""")


def make_job(package, variant, expected, base):
    return {
        "console": "192.168.1.135", "title_id": "PPSA91762",
        "name": f"{VARIANTS[variant][0]} awaiting console handoff",
        "artifacts": [{"path": "PPSA91762/eboot.bin", "sha256": expected, "remote_path": REMOTE}],
        "expected_base": [{"remote_path": REMOTE, "sha256": base}],
        "external_dependencies": [{
            "kind": "agent_thread", "thread_id": "01a18be6-5f7e-7903-9aa5-59ed51a8be62",
            "title": "חיבור כל הפוקימונים למשחק אחד", "state": "active-or-unknown",
            "scope": "console-wide", "state_path": "PS5-13.60/species-lab/import-all-20261030/console-install-20261030",
            "required_merge": "Obtain explicit console handoff. If current eboot differs, identify and preserve all model/music code in a new merged candidate before installing."}],
        "notes": "Preparation only, no autorunner. Replace only eboot after fresh verified all-runs saves+active.json backup, game closed, exact base readback, staged/readback/rename/readback. Preserve models, MUSIC, texfix, dexcount, Hebrew, ITEMS, MONEY, NAME and FPS. Do not change expected_base to bypass a mismatch.",
    }


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    for variant, (name, expected, base) in VARIANTS.items():
        source = BUILD / variant
        info = read_json(source / "build-summary.json")
        assert info["eboot_sha256"] == expected and info["title_id"] == "PPSA91762"
        checks = info["checks"]
        assert checks["dynamic_imports_preserved"] and checks["dynamic_import_count"] == 336
        assert checks["legacy_linked_calls"] == 36 and checks["dexcount_linked_calls"] == 4
        assert checks["new_feature_linked_calls_present"] and len(checks["new_feature_linked_calls"]) == 3
        assert info["base"]["base_control_relinked_byte_identical"]
        assert info["base"]["all_original_base_inputs_unchanged_after_build"]
        assert info["console_tested"] is False
        if variant == "r28b-music":
            assert checks["music_linked_calls"] == 33
            assert all(r["identical_to_published_music"] for r in info["music"]["overrides"])
        package = root / name
        (package / "PPSA91762").mkdir(parents=True)
        shutil.copy2(source / "eboot.bin", package / "PPSA91762/eboot.bin")
        assert sha(package / "PPSA91762/eboot.bin") == expected
        assert (package / "PPSA91762/eboot.bin").stat().st_size == info["eboot_bytes"]
        info["installation_expected_base_sha256"] = base
        info["delivery_status"] = "prepared-offline-awaiting-console-handoff"
        info["save_persistence_tested"] = False
        save_json(package / "BUILD-INFO.json", info)
        (package / "evidence").mkdir()
        for filename in EVIDENCE:
            candidate = source / "evidence" / filename
            if not candidate.exists():
                candidate = BUILD / "r28b/evidence" / filename
            if candidate.is_file():
                shutil.copy2(candidate, package / "evidence" / filename)
        shutil.copytree(PROJECT / "tools/console-install-queue", package / "console-install-queue",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".gitignore"))
        shutil.copy2(PROJECT / "port/dlc-dex-unlock/README-HE.md", package / "FEATURE-DETAILS-HE.md")
        instructions(package, variant, expected, base)
        save_json(package / "QUEUE-JOB.json", make_job(package, variant, expected, base))
    save_json(root / "DELIVERY-PLAN.json", {
        "created_utc": datetime.now(timezone.utc).isoformat(), "project": str(PROJECT),
        "packages": [r[0] for r in VARIANTS.values()], "preferred": VARIANTS["r28b-music"][0],
        "shared_queue_root": str(SHARED_STATE), "hardware_access_performed": False})
    print(json.dumps({"prepared": str(root), "preferred_job": str(root / VARIANTS["r28b-music"][0] / "QUEUE-JOB.json")}, ensure_ascii=False))


def sums(folder):
    records = [(sha(path), path.relative_to(folder).as_posix()) for path in sorted(folder.rglob("*"))
               if path.is_file() and path.name != "SHA256SUMS.txt"]
    write(folder / "SHA256SUMS.txt", "\n".join(f"{digest}  {name}" for digest, name in records))
    return records


def release_zip(folder, archive):
    if archive.exists():
        raise FileExistsError(archive)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as target:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                target.write(file, file.relative_to(folder).as_posix())
    # Streaming hashes prove compressed contents equal every packaged input.
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            with source.open(member) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            assert actual == sha(folder / member.filename), member.filename


def finalize(root):
    receipt = read_json(root / "QUEUE-RECEIPT.json")
    assert receipt["state"] == "queued" and receipt["ticket"]
    preferred = VARIANTS["r28b-music"][0]
    write(root / "NEXT-INSTALL-HE.md", f"""# מוכן להתקנה — r28b DLC Dex

מספר בתור: **{receipt['ticket']}**, מצב: queued / waiting-console-handoff. החבילה המועדפת: `{preferred}`. הפתיחה שולבה גם בגרסה בסיסית חלופית. לא בוצעה התקנה או בדיקת משחק.

העבודה ממתינה למסירת הקונסולה מסוכן המודלים/Rowlet. בדקו תחילה את התור המשותף ב־`{SHARED_STATE}`. אין להסתמך על היעדר lease כהוכחה שהקונסולה פנויה.

ה־SHA המותר כבסיס לעבודת MUSIC הוא `{MUSIC_BASE_SHA}`; הוא אינו הצהרה על המצב הנוכחי בקונסולה. אם הסוכן האחר התקין קוד שונה, חובה לזהות ולמזג אותו לפני התקנה. נתוני מודלים נשארים במקומם. קראו INSTALL-HE.md, TEST-HE.md ו־MERGE-HE.md בחבילה.

אחרי התקנה מאומתת נדרשת בדיקת מסך DLC Dex, שמירה/טעינה ושימור texfix/dexcount/MUSIC. החזרת eboot קודם אינה מבטלת דגל שנשמר. התור הוא כלי תיאום משותף ללא מתקין אוטומטי.
""")
    shutil.copy2(root / "NEXT-INSTALL-HE.md", SHARED_STATE / "NEXT-INSTALL-r28b-HE.md")
    releases = []
    for variant, (name, expected, _) in VARIANTS.items():
        package = root / name
        assert sha(package / "PPSA91762/eboot.bin") == expected
        if variant == "r28b-music":
            shutil.copy2(root / "QUEUE-RECEIPT.json", package / "QUEUE-RECEIPT.json")
        shutil.copy2(root / "NEXT-INSTALL-HE.md", package / "NEXT-INSTALL-HE.md")
        sums(package)
        archive = root / (name + ".zip")
        release_zip(package, archive)
        releases.append({"file": archive.name, "sha256": sha(archive), "bytes": archive.stat().st_size})
    source_zip = root / "r28b-dlc-dex-tools.zip"
    source_records = []
    with zipfile.ZipFile(source_zip, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for relative in SOURCE_ROOTS:
            for file in sorted((PROJECT / relative).rglob("*")):
                if not file.is_file() or "__pycache__" in file.parts:
                    continue
                if file.suffix not in (".py", ".c", ".h", ".md", ".sh", ".json") and file.name != ".gitignore":
                    raise ValueError("unexpected tools export: " + str(file))
                name = file.relative_to(PROJECT).as_posix()
                target.write(file, name)
                source_records.append({"path": name, "sha256": sha(file)})
        target.writestr("SOURCE-MANIFEST.json", json.dumps(source_records, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(source_zip) as target:
        assert target.testzip() is None
        for record in source_records:
            assert hashlib.sha256(target.read(record["path"])).hexdigest() == record["sha256"]
    releases.append({"file": source_zip.name, "sha256": sha(source_zip), "bytes": source_zip.stat().st_size})
    for name in ("NEXT-INSTALL-HE.md", "QUEUE-RECEIPT.json", "DELIVERY-PLAN.json"):
        file = root / name
        releases.append({"file": name, "sha256": sha(file), "bytes": file.stat().st_size})
    save_json(root / "RELEASE-MANIFEST.json", {"queue_ticket": receipt["ticket"], "releases": releases,
              "zip_contents_sha256_verified": True, "console_installed": False, "console_tested": False})
    print(json.dumps({"finalized": str(root), "queue_ticket": receipt["ticket"], "releases": releases}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "finalize"))
    parser.add_argument("--root", type=Path, required=True)
    options = parser.parse_args()
    (prepare if options.action == "prepare" else finalize)(options.root.resolve())

# תור התקנות משותף לקונסולה

התור שומר סדר FIFO ו־reservation בלעדית לכל הקונסולה `192.168.1.135`, לכל ה־titles יחד. הוא אינו מתחבר לקונסולה ואינו מפעיל מתקין. `enqueue` ו־`claim` הן פעולות תיאום מקומיות; הן אינן הוכחה שהקונסולה פנויה.

דוגמאות JSON מלאות נמצאות ב־`examples/`: ‏`job.example.json`, ‏`readiness.example.json`, ‏`receipt.example.json`, ‏`resolution.example.json`. אלו templates עם placeholders, שאינם job אמיתי ואינם אישור לעובדות חומרה. קובצי ראיות ו־readbacks נוצרים בידי המתקין לאחר בדיקה בפועל.

ה־state המשותף: `PS5-13.60/console-install-state`, מחוץ לריפו. ב־Windows וב־WSL משתמשים **באותה תיקיית NTFS**: ב־Windows דרך `C:/...`, וב־WSL דרך `/mnt/c/...`. אין ליצור תור נפרד בעץ WSL או ב־NAS. אפשר להעביר `--root` לפני הפקודה, או להגדיר `CONSOLE_INSTALL_STATE`, בתנאי שכל המשתתפים משתמשים באותו מקום.

זהו פרוטוקול **cooperative/advisory**: סוכן שאינו מאמץ אותו יכול להמשיך לגשת לקונסולה. עבודה חיצונית קיימת דורשת handoff ממשי לפני התקנה; תצוגת שיחה פעילה באפליקציה אינה בדיקת בעלות או זמינות של הקונסולה.

## שימוש

משורש `Pokemon-ZA-Native-Port`:

```powershell
py -3 -I tools/console-install-queue/console_queue.py status
py -3 -I tools/console-install-queue/console_queue.py enqueue --agent codex-main --request-id unique-stable-request --job C:/path/job.json
$lease = py -3 -I tools/console-install-queue/console_queue.py claim --agent console-worker | ConvertFrom-Json
$env:CONSOLE_INSTALL_TOKEN = $lease.token
py -3 -I tools/console-install-queue/console_queue.py heartbeat --agent console-worker --ticket $lease.ticket
```

כל פקודה מדפיסה JSON אחד. שמרו את ה־token אצל בעל ה־reservation; `status` אינו מציג אותו. ב־WSL מריצים `python3 -I ...` דרך קובץ bash, כנהוג בפרויקט. בפקודות המועברות דרך `wsl.exe`, השתמשו בנתיבי `/mnt/c/...` או `C:/...`, כדי ש־backslashes לא ייבלעו ב־shell.

`claim` לוקחת רק את ראש התור. `--ticket 00000001` מאפשר לדרוש ticket מסוים, אך אינו מאפשר לדלג. ה־ticket נשמר גם אחרי `release` וחזרה לתור. `request-id` מונעת הגשה כפולה: אותו מזהה, סוכן ותוכן יחזירו את אותו ticket. זהות ארטיפקט מבוססת על SHA־256, גודל ויעד; איות או capitalization של הנתיב המקומי אינם יוצרים עבודה אחרת.

## Job: ארטיפקטים ובסיס צפוי

דוגמת מבנה בלבד; מחליפים את ה־placeholders בנתיבים וב־hashes אמיתיים לפני הגשה:

```json
{
  "console": "192.168.1.135",
  "title_id": "PPSA91762",
  "name": "merged candidate awaiting console handoff",
  "artifacts": [
    {"path": "C:/path/candidate/eboot.bin", "sha256": "<64 hex digits>", "remote_path": "/data/homebrew/PPSA91762/eboot.bin"}
  ],
  "expected_base": [
    {"remote_path": "/data/homebrew/PPSA91762/eboot.bin", "sha256": "<64 hex digits>"}
  ],
  "external_dependencies": [
    {"kind": "agent_thread", "thread_id": "01a18be6-5f7e-7903-9aa5-59ed51a8be62", "state": "active-or-unknown", "title": "חיבור כל הפוקימונים למשחק אחד", "scope": "console-wide", "state_path": "PS5-13.60/species-lab/import-all-20261030/console-install-20261030"}
  ],
  "notes": "Preserve models/music plus texfix/dexcount; merge if current eboot differs."
}
```

ההגשה מאמתת מקומית כל ארטיפקט וה־SHA שלו. `expected_base` הוא תנאי התאמה, ולא הצהרה שהגרסה הזאת נמצאת כרגע בקונסולה. אם הקריאה החוזרת בעת ההתקנה שונה, עוצרים לצורך זיהוי ושילוב; אין לדרוס שינויי מודלים או מוזיקה. ה־job נשמר כ־`preparation_only` וישירות כ־`queued`; אין autorunner.

## תחילת חלון התקנה: תנאים ממשיים

ה־reservation מתחילה ב־`reserved` עם `waiting-console-handoff`. המתאם מבצע בדיקות חומרה רק במסגרת המשימה המורשית שלו, ושומר readiness JSON המתייחס ל־ticket. לאחר מכן:

```powershell
py -3 -I tools/console-install-queue/console_queue.py heartbeat --agent console-worker --ticket $lease.ticket --begin-install C:/path/readiness.json
```

מבנה readiness:

```json
{
  "console": "192.168.1.135",
  "ticket": "00000001",
  "checked_at": "2026-10-30T12:00:00Z",
  "external_owner_handoff": {"confirmed": true, "evidence": {"path": "C:/evidence/handoff.txt", "sha256": "<64 hex digits>"}},
  "game_closed": {"verified": true, "evidence": {"path": "C:/evidence/processes.json", "sha256": "<64 hex digits>"}},
  "save_backup": {"fresh": true, "all_runs": true, "readback_verified": true, "evidence": {"path": "C:/evidence/backup-manifest.json", "sha256": "<64 hex digits>"}},
  "base_readbacks": [
    {"remote_path": "/data/homebrew/PPSA91762/eboot.bin", "sha256": "<expected base SHA>", "evidence": {"path": "C:/evidence/current-eboot-readback.bin", "sha256": "<same expected base SHA>"}}
  ]
}
```

התנאים חייבים להיבדק בחמש הדקות האחרונות. נדרשים: handoff מהסוכן החיצוני, משחק סגור, גיבוי טרי של כל הריצות ו־readback שלו, ו־readback של ה־base שה־SHA שלו תואם ל־job. הכלי מאמת את קובצי הראיות וה־hashes המקומיים; את העובדות החיות מאמת סוכן ההתקנה. JSON שנכתב ידנית בלי בדיקה אינו הוכחת חומרה.

מכאן פועלים לפי `INSTALL-HE.md`: קובץ זמני, readback והשוואה, rename, ואז readback נוסף. אין שחזור שמירה ישנה מעל התקדמות חדשה. הקריאות והבדיקות של `TEST-HE.md` נשארות חלק ממשימת המתקין; התור אינו מריץ אותן.

## Heartbeat, סיום ושחרור

ברירת המחדל ל־lease היא 600 שניות; שלחו heartbeat לפחות פעם בדקה לאורך חלון העבודה. הטווח המותר ל־`--lease-seconds` הוא 30–3600. exit code ‏3 הוא `lost`: מפסיקים מיד פעולות קונסולה. lease שפג אינו מתחדש בדיעבד, גם אם פג באמצע אימות ארטיפקט גדול.

```powershell
py -3 -I tools/console-install-queue/console_queue.py complete --agent console-worker --ticket $lease.ticket --receipt C:/evidence/receipt.json
py -3 -I tools/console-install-queue/console_queue.py release --agent console-worker --ticket $lease.ticket --reason waiting-for-merge
```

`complete` דורשת `phase=installing` ו־receipt עם `console`, ‏`ticket`, ‏`save_backup_still_verified=true`, ‏`console_handoff_complete=true`, ורשימת `readbacks`. לכל יעד יש `remote_path`, ‏`staged:{path,sha256}` ו־`installed:{path,sha256}`: שני קובצי הקריאה החוזרת חייבים להתאים ל־SHA של הארטיפקט המוגש. אותה קריאת complete עם אותו token ו־receipt היא אידמפוטנטית ואינה משלימה פעמיים.

שחרור reservation במצב `reserved` מחזיר את אותו ticket לתור עם סיבה. אחרי `installing` נדרש גם `--resolution C:/evidence/resolution.json`, עם `console`, ‏`ticket`, ‏`lease_id`, ‏`no_active_installation=true`, ‏`console_handoff_confirmed=true` וקובץ `evidence:{path,sha256}`. זו הצהרת סיום חלון מבוססת ראיות, ולא סגירה אוטומטית של תהליך.

בעל ההגשה יכול לבטל job שעדיין queued באמצעות `release --agent <submitter> --ticket <ticket> --reason <reason> --cancel-queued`. ה־ticket נשמר בהיסטוריה ומסומן cancelled.

## תקיעה ו־reconciliation

אין takeover אוטומטי, גם אחרי timeout. lease stale ממשיכה לחסום את כל ה־titles. אחרי בירור ממשי וסיום חלון קודם, מתאם יכול לשחררה באמצעות `release --agent <coordinator> --ticket <ticket> --reason <reason> --expected-lease-id <exact expired lease id> --resolution <resolution.json>`. דרושים זיהוי מדויק של ה־lease וראיות ל־handoff ולהיעדר התקנה פעילה. לאחר מכן נדרש claim חדש ו־readiness חדש; token ישן אינו תקף.

מנעול המטא־דאטה היחיד הוא `.queue-mutex`, שנוצר ב־mkdir אטומי. אם תהליך מת באמצע עדכון, הספרייה נשארת והכתיבות נעצרות. `status` מציג את `owner.json` שלה ואת ה־lease מתוך snapshot תקין. **לא מסירים mutex לפי גיל בלבד.** מתאם בודק את ה־PID, ה־host וה־platform בשתי הסביבות, מוודא שהכותב הסתיים ומתעד את הבירור. רק לאחר מכן מעביר את ספריית ה־mutex לשם ארכיון ייחודי באותה תיקייה, בלי למחוק state. אין ליצור root חלופי כדי לעקוף תקיעה.

`state.json` כולל SHA־256 של payload קנוני, ו־`state.prev.json` שומר את הגרסה הקודמת. העדכון הוא temp+fsync+atomic replace. קריסה לפני נקודת ההחלפה משאירה את הישן; אחריה נשאר החדש. שגיאת hash או state חסר לצד prev מחייבות בירור; אין rollback אוטומטי שעלול להחזיר lease שכבר הסתיימה.

קודי יציאה: `0` הצלחה; `2` קלט/תנאי/ראיות אינם תקינים; `3` lease אבודה; `4` תור/lease/mutex תפוסים; `5` נדרש תיקון state מבוקר.

## בדיקות וחיפוש מנעולים קיימים

```powershell
py -3 -I tools/console-install-queue/test_console_queue.py
py -3 -I tools/console-install-queue/test_cross_platform.py
```

כל הבדיקות רצות בתיקיות temp עם קבצים סינתטיים, ללא גישה לחומרה. נבדקו 18 מקרי host, כולל enqueue/claim/complete מקבילים, שני titles, stale/lost, hash corruption, קריסה אמיתית של כותב, וכשלים לפני ואחרי commit. בדיקת Windows+WSL משותפת הוכיחה 8 הגשות FIFO, שישה מתחרים על claim עם זוכה יחיד, retry אידמפוטנטי ו־heartbeat/release מהמערכת השנייה.

בחיפוש הקיים בריפו, בתיקיות runtime/species-lab ובקובצי התיאום הרלוונטיים, `native-probe/docs/TESTING.md:64` מזכיר shared console lock ללא מימוש מקומי. `pokeza-recomp-ps5/tools/shot.sh` משתמש ב־`.shot.lock` להרצות צילומי PC בלבד; הוא אינו מנעול קונסולה ואינו תור חלופי.

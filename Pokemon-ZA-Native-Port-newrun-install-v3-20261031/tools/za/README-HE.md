# za — כניסה אחת לאימות ולשחזור ארבע גרסאות Z-A

`za` מרכז את הפינים, בדיקת התנאים, הקישור והמרת ה־SELF לפקודה אחת. הוא מקומי, ללא חיבור לקונסולה וללא גישה לשמירות.

## מה השחזור מוכיח

`reproduce` מקשר **PIE חדש** מהאובייקטים ומארכיוני המשחק המוקפאים של הגרסה, מסיר debug, ממיר ל־ELF של PS5 וחותם `eboot.bin` חדש. אחר כך הוא משווה SHA-256 וגם קורא ומשווה את כל הבתים מול קובצי הייחוס. קובצי הפלט אינם העתק של ה־PIE או ה־eboot המקוריים.

זו הוכחת **קישור מחדש מאובייקטים מוקפאים**, ולא בנייה מלאה מקוד המקור של המשחק. ה־AOT לא נבנה מחדש. הוכחה של ארבעת הבינארים אינה הוכחה של שמירות, טבלאות רנדומיזציה, נכסי app0 או בדיקת חומרה.

| פרופיל | גרסה מדויקת | תחילת SHA-256 של eboot |
|---|---|---|
| `r27b` | r27b-play המקורית, NAME ו־MONEY | `c5b32192` |
| `r28` | r28-play עם ITEMS והעברית שנשמרה מהבסיס | `65f6745f` |
| `r28a` | r28a-play הסופית: texfix וספירת DLC | `5c6777ec` |
| `r28b` | r28b-play ההיסטורית: dexopen בשני הקוראים | `ffd2cf18` |

`r28b` כאן **אינה** `r28b-dlc-dex-music` שהותקנה מאוחר יותר (`8e4280f0…`). לכל פרופיל יש שני שורשי ייחוס: עץ הבנייה המקורי וה־eboot שנמסר בנפרד ב־`artifacts/`.

## הפעלה ב־Windows

מהריפו:

```powershell
tools\za\za.cmd profiles
tools\za\za.cmd doctor all
tools\za\za.cmd verify all
tools\za\za.cmd reproduce all --out /home/tomer/ps5-za-native/za-reproduce-NEW
tools\za\za.cmd check-proof /home/tomer/ps5-za-native/za-reproduce-NEW/r28b/proof.json
tools\za\za.cmd build r29-ui --out /home/tomer/ps5-za-native/r29ui-NEW --package /abs/new-package-dir
```

`za.cmd` משתמש ב־Python 3 של WSL Ubuntu, ואינו דורש Python ב־PATH של Windows. אם Python מותקן ב־Windows אפשר גם `python tools/za/za.py ...`; נתיבי Windows מוחלטים בארגומנטים מתורגמים ל־`/mnt/…`. ב־WSL מפעילים `python3 /mnt/c/.../tools/za/za.py ...`.

- `profiles`: הגדרה מדויקת של הגרסאות ושיטת השחזור.
- `doctor [all|r27b|r28|r28a|r28b]`: בודק את כל קלטי הפרופיל, הספריות, כלי הקישור, קובצי הייחוס והפינים.
- `verify [profile]`: מאמת רק את הבינארים המקוריים שנשמרו; **אין זו הוכחת שחזור**.
- `reproduce [profile] --out NEW`: יוצר תיקייה חדשה, מפיק בינארים ומשווה אותם. מחזיר exit code ‏0 רק אם כל הפרופילים שנבחרו עברו.
- `check-proof PROOF`: בודק מחדש את קובצי הפלט בפועל מול הפינים והייחוס; אינו מסתפק ב־`status` שבדוח.
- `doctor` ו־`verify` מקבלים `--report NEW.json` לשמירת תוצאה חדשה.
- `build r29-ui --out NEW [--package NEW] [--assets DIR] [--tree DIR]`: מפעיל את `port/ui-v2/tools/build-r29-ui.py`. סקריפט ה־UI אחראי לחוזה הגנרטור, לבדיקות host/PS5, לבקרות המקור ולחבילה; קוד היציאה וההודעות שלו מועברים כמו שהם. זו בניית הגרסה החדשה, בנפרד משחזור ארבע הגרסאות ההיסטוריות.

## גרסאות main (נוסף 31.10.2026)

- כל גרסת main היא lock נפרד ב־`releases/<name>.lock.json`. הוא נכתב פעם אחת ב־`freeze_release.py` ולא נערך אחר כך. הקלטים שלו מועתקים לתיקייה קפואה חדשה ב־`/home/tomer/ps5-za-native/za-<name>-frozen-*`.
- `releases/MAIN` מכיל את שם הגרסה הנוכחית. כרגע: `main-1.0.0`, שהיא r29-ui עם eboot `51b7e65b…`. **היא עוד לא נבדקה בקונסולה.**
- `build main --out NEW [--package NEW]`:
  - מקשר את הגרסה מחדש ומשווה אותה בית־בבית לגרסה המקורית.
  - בודק כל קובץ בחבילה מול ה־`SHA256SUMS.json` המוצמד.
  - עם `--package`, מרכיב חבילה חדשה: ה־eboot מהקישור החדש, ושאר הקבצים מהחבילה המוצמדת.
- `profiles.lock.json` לא השתנה (‎192ce23c…), ולכן ההוכחות של ארבע הגרסאות ההיסטוריות עדיין תקפות. לכל הוכחה של גרסת release נרשם ה־SHA של ה־lock שלה (`profile_lock`, `profile_lock_sha256`).
- `all` כולל עכשיו גם את גרסאות ה־release.
- הוכחת השחזור של 1.0.0 נמצאת ב־`evidence/main-1.0.0-reproduce-20261031-01/`.
- המודל המלא: `workbench/MAIN-BRANCH-HE.md`. כרטיס לסוכנים: `workbench/cards/main.md`.

## קלטים, אמון ופלט

`profiles.lock.json` כולל רשימות קלט מסודרות, מספרי בתים ו־SHA-256. נתיב `{repo}` יחסי למיקום הכלי; `{native}` הוא `/home/tomer/ps5-za-native`. סדר האובייקטים, הארכיונים ודגלי הקישור נשמר מהבניות המקוריות. סטיות בפין או קובץ חסר עוצרות לפני הקישור. הכלי בודק שוב את הקלטים אחרי ההפקה.

עצי המקור נשארים לקריאה. המתכון ההיסטורי של RADV כותב symbol map: הכלי מפעיל אותו עם facade פרטי בתיקיית הפלט, כך שלא יכתוב ל־`PS5_Vulkan/build` המשותף. אובייקטי ה־CRT וה־stubs מועתקים מקלטים מוקפאים; שאר הקלטים נקראים ישירות מהעצים המקוריים.

כל פרופיל מייצר `llvm-pie.elf`, `title-stripped.elf`, `eboot.elf`, `eboot.bin`, ‏`build.log`, ‏`recipe.json` ו־`proof.json`. השורש מייצר `summary.json`. ה־ELF, האובייקטים והארכיונים הם קלטי build מקומיים ואינם נכללים בחבילת קוד המקור של הכלי.

הקוד וה־helper נלכדים בתחילת התהליך ונשמרים כ־`executed-za.py` ו־`executed-recipe.sh` בפלטים עתידיים; חותמות הדוח מתייחסות ל־snapshots האלה. בהרצת ההוכחה הראשונה נוספה כניסת ה־UI בזמן שהתהליך כבר רץ, ולגרסה ההיא עוד לא הייתה לכידה חד־פעמית. ראו את `evidence/za-reproduction-codex-20261031-01/PROVENANCE-HE.md` לפרטי ההסתייגות; השוואות הבינארים עצמן תקפות.

אין דריסת פלט קיים, ניקוי אוטומטי, עדכון פינים אוטומטי או התקנה בקונסולה. `freeze.py` הוא כלי תחזוקה נפרד ליצירת הפינים הראשוניים; הוא מסרב לדרוס lock קיים, ואינו מופעל על ידי `za`.

## בדיקות

```powershell
wsl -d Ubuntu -- python3 -m unittest discover -s /mnt/c/.../tools/za -p test_za.py -v
```

בדיקות הדחייה משנות תוכן באותו אורך, מזייפות קבלת הצלחה, משנות ייחוס ומנסות לכתוב לתוך עץ מקור. לאחר שחזור יש להפעיל גם `check-proof` על כל אחד מארבעת דוחות ההוכחה.

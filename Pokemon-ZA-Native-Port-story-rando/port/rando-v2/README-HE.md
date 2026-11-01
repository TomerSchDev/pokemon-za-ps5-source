# rando-v2 — שם המאמן בריצה חדשה (PPSA91762)

29.10.2026. קבצים חדשים בלבד. `port/randomizer`, ‏`port/perf-r26` והכותר PPSA91761 לא שונו. לא נבנה eboot ולא הותקן
דבר בקונסולה. המחקר על צ'יטים בזמן משחק ועל קטעי מעבר נמצא ב-`analysis/rando-v2-name-cheats-cutscenes-HE.md`.

## מה זה עושה
- בתפריט ה-randomizer נוספה שורה **NAME** (שורה 4; הטוגלים עברו לשורות 5–8, ‏RESEARCH REWARDS ל-9, ‏SAVED RUNS ל-10).
  ‏X פותח מקלדת על המסך: ‏A–Z, ‏a–z, ‏0–9, רווח, ‏`- . ! ? ' &`. ‏D-pad זז (עם גלישה), ‏X מקליד, ‏□ מוחק, ‏△ מחליף
  אותיות גדולות/קטנות, ‏○ מבטל, ‏DONE שומר. 1–12 תווים, בלי רווח בהתחלה; רווח בסוף נחתך.
- השם נכתב **רק לשמירה של ריצה חדשה**, אחרי ה-patch של הסטרטר ולפני `publishRun`. התבנית `city-save.bin` לא משתנה,
  וריצות קיימות לא נגעות.
- מה משתנה בשמירה: ‏`MyStatus` (‏`0xE3E89BD1`, ‏OT ב-`0x10`), וה-OT של הפוקימונים של השחקן בקבוצה (`0x3AA1A9AD`) ובקופסאות
  (`0x0D66012C`) — רק כשה-checksum תקין, ה-ID32 שווה ל-ID32 של `MyStatus` וה-OT הוא השם הישן. אחריהם: checksum חדש,
  הצפנה מחדש, ‏xorpad ו-SHA-256 של SwishCrypto. פוקימון של מאמן אחר נשאר בית-בית זהה.
- `report.json` מקבל `player_name`, ‏`player_name_template`, ‏`player_name_pokemon {renamed, kept, unreadable}` ו-`save_sha256`
  מעודכן. הלוג: `[za-randomizer] trainer name set (N chars), R Pokemon renamed, K kept`.
- ברירת המחדל בשדה: השם האחרון שנבחר (`/download0/zarecomp/rando/player-name.txt`, נכתב אטומית אחרי ריצה שהצליחה), אחרת
  השם של התבנית, אחרת `Trainer`. רשימת SAVED RUNS מציגה את השם של כל ריצה מ-report.json.
- לא משתנים: כינויי פוקימונים, שם ה-HT של פוקימונים שנסחרו (בתבנית יש רק את הסטרטר, כך שזה לא רלוונטי לריצה חדשה).

## קבצים
| קובץ | מה |
|---|---|
| `za_player_name.hpp/.cpp` | `validPlayerName`, ‏`readPlayerName`, ‏`applyPlayerName` (פורמט לפי PKHeX: SwishCrypto, ‏SCXorShift32, ‏PA9 Decrypt8/Encrypt8) |
| `name_keyboard.hpp/.cpp` | מצב המקלדת (ללא ציור) |
| `name_glyphs.hpp` | גליפים 5×7 לאותיות קטנות ול-`! ? ' &` (הפונט של התפריט מכיל רק אותיות גדולות) |
| `native_menu.cpp` | עותק של `port/randomizer/native_menu.cpp` עם NAME, מקלדת, ‏`nameRun` ו-SAVED RUNS עם שם |
| `build-check-ps5.sh` | קומפילציית PS5 של שלושת הקבצים עם `-Werror` + בדיקת קישור ברמת סמלים מול אובייקטי r15 |
| `test/` | בדיקות host (ASan/UBSan), כלי `rename_tool`, ולוג הראיות `evidence-20261029.log` |
| `verify/` | כלי .NET מעל PKHeX.Core: ‏`inspect`, ‏`fixtures`, ‏`verify BEFORE AFTER NAME` |
| `research/` | סקריפטים קריאה-בלבד וה-JSON שלהם (מפתחות בלוקים בקוד המתורגם, סריקת קטעי המעבר) |

## בדיקות (כולן על עותקים; אף פעם לא על שמירה חיה)
```
# fixtures מ-PKHeX (template + פוקימון זר + קופסאות), לתיקייה זמנית
dotnet verify/bin/.../ZaNameVerify.dll fixtures TEMPLATE OUT_DIR
bash test/run-host-tests.sh FIXTURES_DIR OUT_DIR      # WSL, clang-21, ASan+UBSan
dotnet ZaNameVerify.dll verify BEFORE AFTER "NAME"    # PASS/FAIL + rc
bash build-check-ps5.sh OUT_DIR                        # WSL, prospero-clang18
```
התוצאות ב-`test/evidence-20261029.log`:
- PKHeX: ‏9/9 PASS — ‏plain → `Ash Ketchum`; תבנית מעורבת (פוקימון זר בקבוצה, בקופסה: שלנו, שלנו עם שם אחר, זר) →
  `Aa1 -.!?'&Zz` ו-`Q`; ו-6 שמירות סטרטר אמיתיות (מינים 1, 25, 133, 152, 158, 498, ה-deltas של הקונסולה עם בדיקת
  `output_sha256`) → `Serena`. בכל אחת השתנו רק הבלוקים הצפויים. ביקורת שלילית (שם צפוי שגוי) → ‏FAIL, ‏rc=1.
- host: ‏`test_player_name` ו-`test_keyboard` — ‏PASS, ‏0 כשלים, כולל: שינוי שם וחזרה ל-`Test` נותן את הקובץ המקורי
  בית-בית; שם פסול/שמירה פגומה/קטועה נדחים בלי לשנות את הקלט.
- PS5: שלושת הקבצים מתקמפלים עם `-Wall -Wextra -Werror`; אין הגדרות כפולות; אין import שהקישור של הכותר לא פותר כבר
  (ה-imports החדשים — `std::to_string`, ‏`string::insert`, ‏`arc4random`, ‏`time`, ‏`unsetenv` — מיובאים כבר ע"י
  `native_menu.o` הנוכחי); ‏`mbedtls_sha256_{init,starts,update,finish,free}` מוגדרים ב-`mbedtls_sha256.o` של הכותר.
  ביקורת שלילית לבדיקת הקישור (סמל שלא קיים) מזוהה.

## שילוב בבנייה (לא בוצע — `port/randomizer` מחוץ לתחום)
1. ב-`build-randomizer.sh`: לקמפל את `port/rando-v2/native_menu.cpp` במקום `randomizer/native_menu.cpp`, ולהוסיף
   `rando-v2/za_player_name.cpp` ו-`rando-v2/name_keyboard.cpp`; ‏`-I$root/port/rando-v2`.
2. `za_player_name.cpp` חייב `-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"` (כמו אובייקטי Mbed TLS): הוא משתמש ב-
   `mbedtls_sha256_context`, שהמבנה שלו תלוי בקונפיגורציה.
3. `assets_hashes.h` וקבצי ה-assets לא משתנים.
4. **repair**: `repair-existing-run.py` מייצר מחדש את הריצה עם `za-rando-core` ומשווה `save_sha256` לדוח הישן. בריצה
   עם שם ההשוואה תיכשל, עד ש-`za-rando-core` (או הסקריפט) יפעיל את אותו `applyPlayerName` עם `player_name` מהדוח.
   הפונקציה דטרמיניסטית (אותו קלט + אותו שם = אותם בתים), כך שזה מספיק.
5. בדיקה בקונסולה לפני הפצה: ריצה חדשה עם שם → "Continue" → שם המאמן בתפריט/כרטיס המאמן ו-OT בסיכום הסטרטר.

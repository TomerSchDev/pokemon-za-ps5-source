# rando-music — ערבוב מוזיקה לרנדומייזר של Z-A (r29-music)

רכיב מבודד. הוא לא נוגע ב־`port/randomizer` ולא ב־`port/rando-v2`. הוא נבנה מעל בסיס קיים: r28-play כברירת מחדל, או r27b.

## איך Z-A בוחר מוזיקה
- **‏`BGM.bnk`** הוא בנק Wwise בגרסה v145 (‏2022.1). הוא מכיל 65 ‏music switch containers.
- **‏`world/exl/audio/bgm_command/bgm_command.bin`** הוא טבלה של המשחק. היא ממפה פקודות של קוד המשחק לאירועי Wwise לפי שם, למשל `PLAY_BGM_PLACEMENT`, ‏`PLAY_BGM_VS_TRAINER` ו־`SET_STATE_T1_A02_IN`.
- אירועי `SET_STATE_*` מציבים states. עץ ההחלטה של כל switch בוחר לפי צירוף ה־states שיר אחד: playlist בלולאה.
- **עיר ואזורים:** ‏`PLAY_BGM_PLACEMENT` מנגן 16 switches בשכבות. המצבים קובעים איזה מהם נשמע.
- **קרבות:** ‏`PLAY_BGM_VS_TRAINER` בוחר את השיר לפי `VS_TRAINER_TYPE_xx` ולפי שלב: ‏READY,‏ BATTLE או WIN.
- **לכן ערבוב ברמת הנתונים פירושו לשנות את עלי עצי ההחלטה ב־`BGM.bnk`.** כל עלה הוא מזהה u32 בהיסט קבוע. השינוי מחליף ערכי u32 בלבד, וגודל הקובץ לא משתנה.

## מה משתנה
- **קבצים:** רק עותק של `BGM.bnk` בתיקיית הריצה: `romfs/audio/wwise/bin/Switch/BGM.bnk`. ה־LayeredFS של ה־runtime מגיש אותו כמו את שאר הטבלאות.
- **תוכנית:** ‏`tools/make_music_plan.py` גוזר את התוכנית ממשחק המקור. היא כוללת 174 עלים ב־64 יחידות ובארבע קטגוריות:
  - `town`: ‏22 יחידות.
  - `zone`: ‏7 יחידות, אזורי פרא וקרב.
  - `battle`: ‏19 יחידות.
  - `boss`: ‏16 יחידות.
- **יחידה:** וריאציות של אותו שיר באותו switch, באותו מבנה ובאותו אורך, למשל שש העיבודים של נושא העיר. יחידה זזה בשלמותה.
- **מה לא זז:**
  - תיקיות האירועים והסיפור ‏(PS, ‏EV_CMN, ‏EV_EXC).
  - סצנות (DEMO / ‏Dxxx).
  - ‏ST/NET.
  - ‏`VS_BOSS_03` האדפטיבי.
  - עלי ניצחון (WIN).
  - שקט.
  - לולאות של פחות מ־30 שניות.
  - שירים עם user cue. הפתיח של העיר מקדם את ה־state ‏T1 לפי ה־cue שלו.
  - כל יעד Play ישיר של אירוע, ובכלל זה בחירת מוזיקת הקרב של המשחק.
  - ‏`ME.bnk`, כלומר ג'ינגלים ופנפרות.
- **מצבים:**
  - `category`: ‏derangement בתוך כל קטגוריה.
  - `chaos`: ‏derangement על כל 64 היחידות.
  - הבחירה דטרמיניסטית לפי ה־seed: ‏SHA-256 עם הפרדת תחום, כמו בפרסי המחקר.

## קבצים
| קובץ | תפקיד |
|---|---|
| `za_music.cpp/.hpp` | הליבה הניידת: אימות התוכנית מול הבנק, ערבוב, דוח |
| `run_store_music.cpp` | עותק של `run_store.cpp` עם `native_music` (לא ב־`native_tables`, לכן r27b/r28 עדיין מכירות ריצות כאלה) |
| `native_menu_music.cpp` | עותק של `rando-v2/native_menu.cpp` עם שורת MUSIC (שורה 10 מתוך 12) |
| `za_music_plan.hpp` | ממשק לתוכנית המוטמעת; ה־`.cpp` נוצר בזמן בנייה (`tools/embed_plan.py`) ואינו ב־git |
| `tools/za_bgm.py`, `tools/make_music_plan.py` | קורא Wwise v145 (צריכה מדויקת של כל 2,026 אובייקטי המוזיקה) ובונה התוכנית |
| `test/` | בדיקות host (ASan/UBSan), אורקל Python עצמאי, בדיקת התפריט האמיתי על host |
| `pc/run_music_pc.py`, `pc/audio_level.py` | הרצות PC עם data root ושמירה נפרדים, לוג קריאות RomFS ולכידת audout |
| `host/` | CLI שיוצר תיקיית ריצה מלאה כמו New Run של הכותר |
| `build-r29-music.sh`, `verify-r29.py` | בניית PS5 מעל r28 (או `r27b`) ובדיקת התמונה |

## בנייה על בסיס אחר (r28a, r27b)
- **הפקודה:** ‏`build-r29-music.sh PLAN.json PLAN_SHA256 BASE`. ערכי `BASE` האפשריים:
  - `r28`, ברירת המחדל.
  - `r27b`.
  - `tree=<עץ עבודה>`, לכל בסיס בסגנון r28, כמו r28a-play. בבסיס כזה מגדירים גם:
    - `R29_BASE_OUT`: תיקיית הפלט, עם `objects/`, ‏`llvm-pie.elf`, ‏`eboot.bin` ו־`evidence/`.
    - `R29_BASE_ARCHIVE`.
    - `R29_BASE_REV`.
    - `R29_BASE_EBOOT_SHA256`.
    - `R29_BASE_ARCHIVE_SHA256`.
  - דוגמה מלאה נמצאת ב־`BUILD-INFO.json` של החבילה.
- **מה מוחלף:** רק חמישה אובייקטים: `native_menu.o`, ‏`run_store.o`, ‏`title_entry.o`, ‏`za_music.o` ו־`za_music_plan.o`.
- **מה לא נוגעים בו:** הארכיון, ה־runtime, אובייקטי הצ'יטים והעברית ורשומת הקישור של הבסיס.
- **עץ הבסיס נקרא בלבד.** ‏SHA-256 של קובצי הבסיס נבדק לפני הבנייה ואחריה.
- **בקרה לפני החלפה:** המקור הלא־משונה צריך לבנות מחדש את `native_menu.o` ואת `title_entry.o` של הבסיס בייט־בבייט. אם תיקון אחר שינה אותם, הבנייה נעצרת ולא מוחקת את השינוי. במקרה כזה צריך למזג את שורת MUSIC אל המקור החדש.
- **ב־r27b:** אין `--wrap=za_observer_menu`, והמאמת בודק את הקריאה הישירה. בבסיס הזה מגדירים `R29_BASE_CALLS=r27b`.

## נתוני משחק
- התוכנית, הבנקים שנוצרים, קובצי ה־WAV ולוגי הקריאות נשמרים רק ב־`PS5-13.60\music-lab` וב־WSL, מחוץ ל־git.
- בתיקייה הזאת יש קוד בלבד.

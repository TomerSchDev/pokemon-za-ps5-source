# rando-dexopen — רשימת ה־Pokédex של Mega Dimension (Hyperspace) פתוחה מההתחלה (r28b)

30.10.2026 · Z-A 2.0.2 + Mega Dimension · רנדומייזר PPSA91762. בלי קונסולה, בלי commits, בלי כתיבה לשמירות.
**מצב: נבדק ב־host בלבד (ASan+UBSan על הפונקציות המתורגמות האמיתיות + 38 בדיקות הגנה של ה־patcher). אין הוכחה בתוך המשחק — לפי החלטת Tomer לקו התיקונים הזה, הקונסולה היא הבדיקה.**

## הבעיה
- רשימת ה־Hyperspace Pokédex (מיני ה־DLC, 132 מינים) מוסתרת עד שסיפור ה־DLC מדליק את דגל השמירה `FLAG_DLC_DEX_ENABLE`.
- עם הרנדומייזר מיני DLC נתפסים כבר באזורים הראשונים ונרשמים ב־Pokédex (הוכח ב־PKHeX, ‏r28a), אבל אי אפשר לראות את הרשימה ואת ההתקדמות בה.
- r28a (‏dexcount) כבר סופר אותם במשימות; r28b פותח גם את הרשימה עצמה.

## מה המשחק עושה (לפי za-atlas, 30.10.2026)
- הדגל: אובייקט descriptor ב־`0x7003e26880` = {hash (‏FNV-1a 64 של השם: ‏`58e63b00d271631f`), מצביע לשם, אורך 0x13}. **נקרא בדיוק בשתי פונקציות מתורגמות ולא נכתב באף אחת** (הכתיבה מגיעה מנתוני אירועי ה־DLC):
  1. `f_70008d4178` ‏(`main_287.c:633–689`), ‏DLC::IsHyperspaceDexEnabled: ‏`w20 = *(0x700610df00+0x200)` (מילת המוכנות של מנהל הדגלים); אם 0 → מחזירה 0. אחרת בונה מפתח מה־descriptor (‏`f_700000421c`), קוראת את הדגל (`f_70000393b8(flagmgr=*(0x7003ec3328), &key)`) → ‏w19, משחררת holder (לא קורה ל־descriptor סטטי), ומחזירה `w8 & w19` (‏w8 = מוכנות ≠ 0). **14 קוראים, כולם UI של ה־Pokédex**: ‏BuildVisibleEntries, ‏CanSwitchDexList, ‏ToggleLumioseHyperspaceList, ‏EnsureMankeySeenForDLC (‏main_1080), איטרציה על רשומות (‏main_211 ‏`f_7000663300`), חלונית המידע (‏main_309 ‏`f_7000a01744`), יחידת ה־dex בפאנל המשימות (‏main_261 ‏`f_7000825960`), ‏main_1093 ‏(`f_7002d58394`, ‏`f_7002d594c0`, ‏`f_7002d59678`), ‏main_140 ‏`f_700040496c`, ‏main_286 ‏`f_70008d0610`, ‏main_1080 ‏`f_7002c8ecd8`, ‏`f_7002c8f0d0`.
  2. `f_700033f8d8` ‏(`main_115.c:7562–7955`), ‏Pokedex::GetMegaDexCount: אותו דגם; תוצאת ה־getter ב־w22, ואז `w8 = (w19≠0) & w22` נשמר ב־`sp+0x1c` כמסנן "כולל רשומות Hyperspace" (כשהוא 0, רשומות שה־bool בשדה 4 שלהן דלוק מדולגות). קוראים: ‏Pokedex::PublishDexCounters (טלמטריה, ‏`f_700033d0a0`), ‏main_1080 ‏`f_7002c8d5b8`, ‏main_1093 ‏`f_7002d58b00`.
- דגלי הסיפור של ה־DLC (`FLAG_DLC_ANOTHER_DIMENSION_ENABLE`, ‏`FLAG_DLC_QUEST_ENABLE`, ‏`SYS_WORK_DLC_PHASE`) — לא נוגעים בהם.

## התיקון (החלטת Tomer: לפתוח, כל עוד רק ה־Pokédex מושפע)
**לא כותבים את דגל השמירה.** שני הקוראים מתייחסים אליו כדלוק בכל פעם שבדיקת המוכנות עוברת, דרך עזר C קטן עם מתג אחד:

| יחידה | פונקציה | שינוי |
|---|---|---|
| `main_287.c` | `f_70008d4178` | השורה האחרונה `w0 = w8 & w19` → `w0 = za_dexopen_hyperspace_dex_enabled(w8, w19)` (= ‏w8 כשהמתג דלוק; ‏`w8 & w19` כשכבוי). קריאת ה־getter ושחרור ה־holder לא משתנים |
| `main_115.c` | `f_700033f8d8` | מיד אחרי `w22 = w0` של ה־getter: ‏`w22 = za_dexopen_mega_dex_flag(w22)` (= 1 כשהמתג דלוק; ללא שינוי כשכבוי) |
| חדש | `za_dexopen.c/.h` | המתג (`za_dexopen_set_enabled`, ברירת מחדל דלוק — אותו מנגנון כמו `za_dexcount_extra_enabled`), מונים, ושורת klog אחת לכל אתר בשימוש הראשון (ושוב רק אם ערך הדגל האמיתי משתנה) |

- ה־patcher ‏`prepare-dexopen-hooks.py` עובד בעוגנים מדויקים: ‏build ID של ה־NSO, ‏SHA-256 של כל יחידה, עוגן יחיד בתוך הפונקציה, 22 שורות מבוקרות, מסרב ליחידה עם `L_dispatch` או עם hook קודם, הכל־או־כלום, לא דורס פלט שונה.
- **תופעות לוואי צפויות (קוד משחק קיים שנפתח):**
  - בפתיחת ה־Pokédex, כשמנהל ה־Pokédex מוכן ו־Mankey ‏(species 56) עדיין לא "נראה", ‏`PokedexUI::EnsureMankeySeenForDLC` ‏(`f_7002c8b53c`) מסמן את Mankey כ־Seen (form 0) דרך `Pokedex::ApplySeenRegistration` — כך המשחק עצמו נוהג כש־DLC מדליק את הרשימה. זה שינוי ב־Pokédex שבשמירה (SeenMask), לא CaughtMask, ולא פוקימון חדש.
  - מונה ה־Mega Dex שמתפרסם לטלמטריה (`megadex_cnt`) כולל גם רשומות Hyperspace.
- **מה לא משתנה:** השמירה והדגלים (לא נכתב דבר), סיפור ה־DLC וגישה ל־Hyperspace, דונאטס, משימות, ‏dexcount ו־texfix של r28a, ה־runtime, ה־title והתפריט.

## שינויים מדויקים (SHA-256)
| פריט | לפני | אחרי |
|---|---|---|
| `main_287.c` | `1c8e0186dd2b993060f63d1e381f9765fed756d0e0f71031007c6a2f91e7f442` | `0c66bc089fa8d4dba346c093605159c7532e01eb602b0a0fdf6fdc94d70a3c48` |
| `main_287.o` (PS5) | `f8398bf6569a3de60a8ed60fb7a111b5102604f5b2c89975377bf204f2f65d38` | `ae020153406b53df733916d2406e5cf33c2bcff98637121721f9dcb4c7ca5f29` |
| `main_115.c` | `598e9785c9ff3f64a426049eecef964083f0bf989f51361d1deaf63e82adaba6` | `91d4b32454ebbaae3ac2e2b7af22d966476e64a4bcdbd02c06f78e95b94465ed` |
| `main_115.o` (PS5) | `ca1c1ca07c3fd1e73632eea3b79ebf732ae253414c9a0535f5804690db2f5b5d` | `630b180af6977b4fb25d820702fff878aeeea8d486f7ac1175e377acb660912c` |
| ארכיון המשחק | `liblasgame-r28-dexcount.a` ‏(r28a) ‏`1f0c586e721f93b80cd86b9b3675a18d95bca338952b5b3d01e7518bcc9a41cc` | `liblasgame-r28-dexopen.a` ‏`7a2e71bc89c0d0af9b2c3aab53a4f4f26258fba049cdb2fcfa03beed6f14d90b` |
| `za_dexopen.o` (חדש) | — | `467e7e5dc8894acd5bcdc3868aecb3d68cf005c0ebb04273924469513a3f14bb` |
| `eboot.bin` (r28b-play) | r28a ‏`5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea` | `ffd2cf18fc513ec4400d949325a5db2771336adb479b71026c7063280dd6aa26` |

- **בקרה:** שתי היחידות המקוריות עברו קומפילציה מחדש במתכון של r28 ויצאו זהות בית־בבית לחברי הארכיון של r28a.
- **סמלים:** הסמלים המוגדרים לא השתנו; imports חדשים ביחידות: רק `za_dexopen_hyperspace_dex_enabled` ‏(main_287) ו־`za_dexopen_mega_dex_flag` ‏(main_115).
- **`za_dexopen.o` מייבא:** `__stderrp`, ‏`fflush`, ‏`fputs`, ‏`sceKernelDebugOutText`, ‏`snprintf` — כולם כבר imports של r28/r28a, ולכן רשימת ה־imports של ה־PIE לא משתנה.
- **שחזור:** נבנה פעמיים לשני עצים חדשים (18:01 ו־18:13 UTC); כל חמשת הפלטים (eboot, ‏PIE, ‏stripped, ארכיון, אובייקט) יצאו זהים; ‏eboot של הבנייה השנייה לפי היומן שלה: `ffd2cf18fc513ec4400d949325a5db2771336adb479b71026c7063280dd6aa26` (`evidence/reproducibility.json`).

## שילוב ובנייה
```
# אובייקטים בלבד (על עץ r28a הסופי, קריאה בלבד):
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/c/.../port/rando-dexopen/ps5/apply-r28b.sh \
  /home/tomer/ps5-za-native/r28a-play-final-20261030 /home/tomer/ps5-za-native/<תיקייה-חדשה>
# בנייה מלאה (עץ חדש = עותק של r28a הסופי + apply + link + אימותים + חתימה):
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/c/.../port/rando-dexopen/build-r28b.sh \
  /home/tomer/ps5-za-native/r28a-play-final-20261030 /home/tomer/ps5-za-native/<עץ-חדש>
```
- `apply-r28b.sh`: קורא בלבד את עץ r28a, הארכיון (נעול ב־SHA-256) והיחידות המתורגמות; בודק build ID; מפיק `liblasgame-r28-dexopen.a` ו־`za_dexopen.o` עם manifest וראיות.
- `build-r28b.sh`: מעתיק את עץ r28a הסופי, מצלם את התיקייה הזו, מריץ את apply מהצילום, מקשר במתכון של r28a (+‏`za_dexopen.o`), ומאמת: `verify-r28b.py base/dexopen/inputs/image` ו־`port/runtime-texfix/verify-r28a.py image` (הבדיקות של r28a מול r28-play, כמו שהן).
- **עץ הבנייה הסופי:** `/home/tomer/ps5-za-native/r28b-play-20261030` (קריאה בלבד אחרי המסירה; שלמותו אומתה ב־`sha256sum -c` אחרי האירוע שלמטה). עץ השחזור `…-repro` נבנה, הפיק את אותם SHA-256 (היומן שלו שמור ב־`evidence/repro-build-2.log` של החבילה), ואז **נמחק**: בזמן הכתיבות האחרונות שלו התמלא דיסק C: של המחשב (0 MB פנויים) וה־ext4 של WSL איבד את הבלוקים של `eboot.bin`/`eboot.elf`/`SHA256SUMS.txt` באותו עץ. ‏**C: נשאר מלא (כ־0.9 GB פנויים אחרי ניקוי הזמניים שלי) — Tomer צריך לשחרר מקום לפני בניות נוספות.**
- **חזרה:** הארכיון של r28a (`liblasgame-r28-dexcount.a`) בלי `za_dexopen.o` = r28a. אין שינוי בשמירות.

## בדיקות
- `test/run-host-tests.sh` (WSL, ‏clang-21), תוצאה: **PASS** (`evidence/host-tests.log`):
  - **רתמת ASan+UBSan** על הטקסט המתורגם האמיתי של שתי הפונקציות, מקור מול patched (`test/test_dexopen.c`): מוכנות 0/1 × דגל 0/1 (וערכים לא־בוליאניים), המתג כבוי = מקור, שחרור ה־holder (אחרון / לא אחרון / לא refcounted) זהה בשניהם, ‏Mega Dex עם רשומות Lumiose/Hyperspace/"always" — המקור סופר 1 והמתוקן 3 (עם הדגל האמיתי דלוק שניהם 3), מנהל דגלים לא מוכן, singleton לא מוכן, רשימה ריקה, רשומות ה־Pokédex נקראות ולא נכתבות, שמירת x19–x30 ו־sp, שורת trace פעם אחת לאתר, 8 threads.
  - **38 בדיקות patcher:** build ID, ‏hash של כל יחידה, עוגן יחיד בתוך הפונקציה, כל שורה מבוקרת, ‏L_dispatch, ‏hook קודם, הכל־או־כלום, אי־דריסה, הקלטים לא משתנים.
  - `za_dexopen.c` לבד: ‏`-std=c11 -pedantic -Wall -Wextra -Werror` עם trace כבוי/דלוק/דלוק+klog.
- **לא נבדק:** פתיחת הרשימה במשחק (PC או קונסולה). אין הוכחת PC — לפי החלטת Tomer.

## בדיקת צד־הנתונים (אינפורמטיבי)
חיפוש השם `FLAG_DLC_DEX_ENABLE` וה־hash שלו (`58e63b00d271631f`, ‏FNV-1a 64 — אומת) בכל 13,181 החבילות של ה־RomFS (238,566 קבצים, 20.2 GB אחרי פריסה; ‏`research/scan_flag_refs.py`, קריאה בלבד): **שני קבצים בלבד, לפי שם, אפס לפי hash:**
1. `ik_event/bin/flag/system_flag.bin` — מרשם דגלי המערכת (49 שמות `FLAG_*`, בלי תנאים).
2. `ik_event/bin/phase/dlc_phase.bin` — טבלת השלבים של ה־DLC: 79 ‏`flag_condition` שכולם בודקים דגלי אירוע `flag_Ev_d01_*`, ואף אחד לא את `FLAG_DLC_DEX_ENABLE`; השם מופיע פעם אחת ליד שאר דגלי ה־enable של ה־DLC ו־`TRUE`, מחוץ לכל רשומת תנאי — ככל הנראה פעולת ההדלקה של השלב (לא אומת מבנית).
**מסקנה:** אין קורא נתונים (תנאי משימה/טריגר) של הדגל; הקוראים הם רק שתי הפונקציות המתוקנות. התיקון לא משנה את הדגל, ולכן גם טבלת השלבים של ה־DLC רואה אותו כרגיל.

## בדיקה בקונסולה
ראו `docs/TEST-HE.md` (סעיף 4): פתיחת ה־Pokédex עם מעבר לרשימת Hyperspace מההתחלה, המספר בפאנל המשימות, שורות `[dexopen]` ב־klog, ‏Mankey כ־Seen.

## קבצים
- `prepare-dexopen-hooks.py`, ‏`za_dexopen.c/.h`, ‏`ps5/apply-r28b.sh`, ‏`ps5/compare_ar.py`, ‏`build-r28b.sh`, ‏`verify-r28b.py`, ‏`make-build-info.py`, ‏`deliver-r28b.py`.
- `test/` — ‏`run-host-tests.sh`, ‏`test_dexopen.c`, ‏`test_patcher.py`, ‏`extract-functions.py`.
- `research/` — סקריפטי צד־הנתונים (קריאה בלבד). `evidence/` — יומן הבדיקות ותוצאות הסריקה (עובדות נגזרות בלבד).
- `docs/` — המסמכים של החבילה (`artifacts/randomizer-r28b-play`).

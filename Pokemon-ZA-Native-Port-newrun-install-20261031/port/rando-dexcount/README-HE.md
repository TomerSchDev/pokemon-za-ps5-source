# rando-dexcount — מיני ה-DLC נספרים במשימות "רשום N מינים" (r28a)

30.10.2026 · Z-A 2.0.2 + Mega Dimension · רנדומייזר PPSA91762. בלי קונסולה, בלי commits, בלי בניית חבילה.
**מצב: נבדק ב-host בלבד, לא הוכח בתוך המשחק.** הוכחת ה-PC בוטלה לפני שלב התקדמות המשימה; הבדיקה תיעשה בקונסולה.

## הבעיה
- **משימה ראשית 2** ("A New Life in Lumiose City"), שלב 2_1_50: "Register at least five species" — ‏≥5.
- **שני טריגרים במעבדה** (`trigger_main_02`, ‏`pos_t1_main_021160_000`): ‏phase ‏21160 ו-≥5 → התקדמות ל-21200; ‏<5 → דיאלוג "עוד לא".
- **46 בקשות של מייבל** "Filling Your Pokédex (01–46)": ספים 5, 10 … 230.
- כולן משתמשות ב-`have_pokemon_encyclopedia_total_condition`, והוא סופר רק את רשימת **Lumiose** (232 מינים). מיני ה-DLC (רשימת Hyperspace, ‏132) לא נספרים אף פעם.
- המלאי המלא: `research/dex-missions-2.0.2.json`, מ-`research/find-dex-missions.py` (קריאה בלבד, עובדות נגזרות בלבד).

## מה המשחק סופר
- **המעריך:** ‏`f_7000a1158c` ‏(`main_310.c`, ‏slot ‏+0x78 ב-vtable של התנאי).
  - קורא ל-`f_700033e770(manager, 0, 0)`: מספר המינים ברשימת Lumiose שיש להם צורה "נתפסה" בבלוק ה-Pokédex.
  - משווה עם הסף.
- **הרשימות:** `pokedex_contents_data.bin` — ‏kind 0 = ‏232, ‏kind 1 = ‏132. **ללא חפיפה.**
- **מספר בפאנל:** "Number Registered N/5" מחושב בנפרד, ב-`f_700082b5c4` ‏(`main_261.c`). פריט מסוג 2 → אותה ספירת Lumiose.
  - הוכח ב-fnprof על ה-PC: `f_7000414e44` → `f_700082b5c4` → `f_700033e770`.

## השערת "Pokédex נעול" — נבדקה ונפסלה
- ב-PC, ממשחק ששמירתו היא עותק של שמירת בדיקה (phase ‏21150–21160), נתפסו בטבע: Meowth, ‏Zubat ו-Spoink. שלושתם מיני Hyperspace בלבד.
- הדגלים באותו רגע: `FLAG_DLC_DEX_ENABLE=false`, ‏`SYS_WORK_DLC_PHASE=0`.
- **PKHeX:** דגלי "נתפס" שלהם **כתובים** בבלוק ה-Pokédex. ‏Lumiose ‏1, ‏Hyperspace ‏3.
  - ראיות: `evidence/pkhex-ckpt1-to-ckpt3.json`, ‏`evidence/pkhex-ckpt2.json`.
- **מסקנה:** אין צורך לפתוח בכוח את ה-Pokédex של ה-DLC. הלכידות נרשמות; רק המונה של המשימה מתעלם מהן.
- **הפאנל בתפריט הראה "1/5"** כשהיו רשומים 4 מינים (`evidence/screens/`, לא ב-git).

## התיקון (אפשרות ב׳: hook צר)
| יחידה | פונקציה | שינוי |
|---|---|---|
| `main_310.c` | `f_7000a1158c` | אחרי ספירת Lumiose נקראת גם `f_700033e770(manager,1,0)`; ההשוואה על `za_dexcount_combine(L,H)` |
| `main_261.c` | `f_700082b5c4` | רק פריט מסוג 2 מחזיר `za_dexcount_display(L,H)`. סוג 18 (פריט ה-Hyperspace) וכל השאר — ללא שינוי |
| חדש | `za_dexcount.c/.h` | סכום רווי, מתג פנימי (ברירת מחדל פעיל), שורת klog רק כשהערך משתנה |

- כל מין נספר פעם אחת: הרשימות זרות.
- **מה לא משתנה:**
  - מסכי ה-Pokédex.
  - התקדמות ה-DLC עצמו: `have_dimension_encyclopedia_total_condition` ופריט 18.
  - תנאי השלמה ותארים: `complete_*_encyclopedia`.
  - בקשות Mega dex.
  - השמירה ודגלים: לא נכתב דבר.
- **תוצאה רצויה (החלטת Tomer):** בקשות "Filling Your Pokédex" של מייבל סופרות גם מיני DLC.
- **ריצות קיימות:** הספירה מחושבת חי מה-Pokédex שבשמירה, ומיני DLC שכבר נתפסו כבר רשומים בו. לכן **לכידות קודמות נספרות מיד**, בלי לתפוס מחדש ובלי לשנות שמירה.

## שינויים מדויקים (SHA-256)
| פריט | לפני | אחרי |
|---|---|---|
| `main_310.c` | `bac882ee…c44214` | `cdd94cad…eb2aea` |
| `main_310.o` (PS5) | `a0abfe00…5dc08` | `9fe2a40b…33779` |
| `main_261.c` | `87a899bb…84b91d` | `87e144d7…5f821` |
| `main_261.o` (PS5) | `862beb9d…281fd` | `39c40977…ba467` |
| `liblasgame-r28.a` | `a86c3134…4bb30` | `liblasgame-r28-dexcount.a` `1f0c586e…a41cc` |
| `za_dexcount.o` (חדש) | — | `207e7a1a…ce06f` |

- הערכים המלאים: `ps5/HANDOFF.json`.
- **בקרה:** כל יחידה מקורית עברה קומפילציה מחדש במתכון של r28, ויצאה זהה בית-בית לחבר בארכיון.
- **סמלים:** הסמלים המוגדרים לא השתנו.
- **imports חדשים:** רק `za_dexcount_*`.
- **`za_dexcount.o` מייבא:** `__stderrp`, ‏`fflush`, ‏`fputs`, ‏`sceKernelDebugOutText`, ‏`snprintf`. כולם כבר מיובאים בכותר r28.

## שילוב ב-r28a (בלי לבנות חבילה)
```
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/c/.../port/rando-dexcount/ps5/apply-r28a.sh \
  /home/tomer/ps5-za-native/r28a-play-20261030 /home/tomer/ps5-za-native/<תיקייה-חדשה>
```
- **קריאה בלבד:** עץ העבודה, הארכיון (נעול ב-SHA-256) והיחידות המתורגמות. ה-build ID נבדק.
- **הפלט:** `liblasgame-r28-dexcount.a` ו-`za_dexcount.o`, יחד עם manifest וראיות.
- **פלט מוכן:** `/home/tomer/ps5-za-native/rando-dexcount-r28a-20261030`.
- **בקישור:**
  1. להשתמש בארכיון החדש במקום `liblasgame-r28.a`.
  2. להוסיף את `za_dexcount.o` ל-`ZA_PS5_EXTRA_INPUTS`.
- `DEXCOUNT_PANEL=0` = המעריך בלבד, בלי תיקון המספר בפאנל.
- **חזרה:** הארכיון המקורי, בלי `za_dexcount.o`. אין שינוי בשמירות.

## בדיקות
- `test/run-host-tests.sh` (WSL), תוצאה: **PASS** (`evidence/host-tests.log`). מה נבדק:
  - **רתמת ASan+UBSan** על הטקסט המתורגם האמיתי של שתי הפונקציות, מקור מול patched:
    - 5..230 × טווחי 232/132.
    - op ‏`<`/`>=`.
    - מתג כבוי.
    - manager לא מוכן.
    - כל סוגי הפריטים 0–20.
    - שמירת x19–x30 ו-sp.
    - 8 threads.
  - **24 בדיקות patcher:** build ID, ‏hash של כל יחידה, ‏anchor יחיד בתוך הפונקציה, כל שורה מבוקרת, הכל-או-כלום, אי-דריסה, הקלטים לא משתנים.
- **ב-PC (`evidence/pc-proof.json`, חלקי):**
  - הוכח: הלכידות המוקדמות נרשמות.
  - הוכח: הבאג בפאנל.
  - הוכח: נתיב הפאנל.
  - **לא נבדק:** התקדמות המשימה עם התיקון.
- **כלי ה-PC:** ב-`test/`.
  - `build-pc.py`, ‏`run-pc.py`: נתיב data ותיקיית שמירה נפרדים, עותקים בלבד.
  - `pc_control.c`: בקר בדיקה.
  - `pc_capture.c`: מאיץ לכידה לבדיקה בלבד.
  - `make-proof-mod*.py`: מוד חריצי DLC.
  - `verify/`: ‏PKHeX.

## בדיקה בקונסולה
1. **התקנה רגילה:** גיבוי שמירה מאומת לפני כל פעולה. מאזינים ל-klog (3232).
2. **ריצה:** הריצה הקיימת או ריצה חדשה. אין צורך בטבלאות מיוחדות — תופסים מיני DLC ליד ההתחלה.
3. **במשימה 2:** פותחים את התפריט (X).
   - "Number Registered" צריך להיות Lumiose + DLC.
   - klog: `[dexcount] mission panel Number Registered: lumiose=.. hyperspace=.. combined=..`
4. **במעבדה, כשהסכום ≥5:** המשימה מתקדמת.
   - klog: `[dexcount] have_pokemon_encyclopedia_total condition: ... combined=..`
   - כשהסכום <5: עדיין "עוד לא".
5. **בקשות של מייבל:**
   - "Filling Your Pokédex": סופרות Lumiose+DLC.
   - "Filling Your Hyperspace Pokédex": רק DLC.
6. **שמירה וטעינה:** שומרים, סוגרים, Continue — אותם מספרים.

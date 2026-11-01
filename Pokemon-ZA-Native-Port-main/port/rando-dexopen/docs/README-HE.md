# r28b-play — רשימת ה־Hyperspace Pokédex פתוחה מההתחלה (על r28a)

ל־PPSA91762 בלבד, גרסת משחק 2.0.2 עם Mega Dimension. ‏**r28b = r28a-play + תיקון אחד נוסף, ב־eboot.bin בלבד.** כל מה שהיה ב־r28a (texfix, ‏dexcount) וב־r28 (ITEMS, ‏MONEY, ‏NAME, ‏FPS TRIAL, מונה FPS, כפתור HEBREW TRIAL, ‏`submit=thread` ועומק 64, ‏4K עם רינדור 1080p) נשאר כמו שהוא: אותם 64 אובייקטי runtime, אותם 35 אובייקטי title ואותו `za_dexcount.o` בית־בבית; בארכיון המשחק הוחלפו שני חברים בלבד. הבנייה מוכנה לבדיקה ידנית ב־PS5; **לא ניגשנו לקונסולה ולא התקנו אותה.**

## 1. מה ירשנו מ־r28a (ללא שינוי)
- **texfix** — תיקון קריסת הטקסטורות (`[za-texguard] r28a texfix active` בעלייה). פרטים ב־`artifacts/randomizer-r28a-play/README-HE.md` ו־`port/runtime-texfix/`.
- **dexcount** — "Register at least five species", ‏triggers המעבדה ו־46 בקשות Mable סופרים Lumiose + Hyperspace; המספר בפאנל תואם (`[dexcount] …`). פרטים ב־`port/rando-dexcount/`.

## 2. התיקון החדש: dexopen
**הבעיה.** רשימת ה־Mega Dimension (Hyperspace) ב־Pokédex (132 מינים) מוסתרת עד שסיפור ה־DLC מדליק את דגל השמירה `FLAG_DLC_DEX_ENABLE`. עם הרנדומייזר מיני DLC נתפסים מההתחלה ונרשמים בשמירה (אומת ב־PKHeX ב־r28a), אבל הרשימה וההתקדמות בה אינן נראות.

**מה המשחק עושה** (za-atlas, 30.10.2026): הדגל (descriptor ‏`0x7003e26880`, ‏hash ‏`58e63b00d271631f`) **נקרא בדיוק בשתי פונקציות מתורגמות ולא נכתב באף אחת** — ‏`DLC::IsHyperspaceDexEnabled` ‏(`f_70008d4178`, ‏main_287; 14 קוראים, כולם UI של ה־Pokédex: בניית הרשימה, מעבר בין הרשימות, איטרציה על רשומות, חלונית המידע, יחידת ה־dex בפאנל המשימות) ו־`Pokedex::GetMegaDexCount` ‏(`f_700033f8d8`, ‏main_115; המסנן "כולל רשומות Hyperspace"; קוראים: טלמטריית המונים ושני מסכי Pokédex). שתיהן בודקות קודם את מילת המוכנות של מנהל הדגלים (`*(0x700610df00+0x200)`) ואז קוראות את הדגל. בנתוני המשחק אין אף תנאי משימה/טריגר שקורא את הדגל (סריקה של כל 13,181 החבילות: רק מרשם הדגלים `flag/system_flag.bin` וטבלת השלבים `phase/dlc_phase.bin`, שם הוא מופיע מחוץ לכל רשומת תנאי, ככל הנראה כפעולת ההדלקה).

**ההחלטה (Tomer): לפתוח, כל עוד רק ה־Pokédex מושפע. הדגל והשמירה לא נכתבים.** שני הקוראים מתייחסים לדגל כדלוק בכל פעם שבדיקת המוכנות עוברת:
- `f_70008d4178`: השורה האחרונה `w0 = w8 & w19` (מוכנות & דגל) → `w0 = za_dexopen_hyperspace_dex_enabled(w8, w19)` = ‏w8. קריאת ה־getter ושחרור ה־holder לא משתנים.
- `f_700033f8d8`: מיד אחרי שתוצאת ה־getter נקלטת ב־w22: ‏`w22 = za_dexopen_mega_dex_flag(w22)` = 1. המשחק ממשיך כרגיל (`w8 = (w19≠0) & w22` → המסנן).
- `za_dexopen.c` (אובייקט חדש): מתג אחד (`za_dexopen_set_enabled`, ברירת מחדל דלוק; אותו מנגנון כמו ב־dexcount) שמכבה את שני האתרים ומחזיר בדיוק את הביטוי המקורי; מונים; שורת klog אחת לכל אתר בשימוש הראשון, ושוב רק אם ערך הדגל האמיתי משתנה.
- דגלי הסיפור של ה־DLC (`FLAG_DLC_ANOTHER_DIMENSION_ENABLE`, ‏`FLAG_DLC_QUEST_ENABLE`, ‏`SYS_WORK_DLC_PHASE`) לא נוגעים בהם.

**מה השתנה בבינארי:** שני חברים בארכיון המשחק — `main_287.o` ו־`main_115.o` (היחידות המקוריות משוחזרות מהארכיון של r28a בית־בבית; הסמלים המוגדרים לא השתנו; import חדש אחד לכל יחידה) — ואובייקט חדש `za_dexopen.o` (מייבא רק `__stderrp fflush fputs sceKernelDebugOutText snprintf`, כולם כבר imports של r28). רשימת ה־imports של ה־PIE זהה ל־r28a ול־r28 (336); ה־globals שנוספו מול r28a: `za_dexopen_hyperspace_dex_enabled`, ‏`za_dexopen_mega_dex_flag` בלבד; 36 הקריאות המקושרות של r28a + 4 של dexcount + 2 של dexopen — כולן קיימות. נבנה פעמיים לשני עצים חדשים ויצא זהה. ה־SHA-256 ב־`BUILD-INFO.json` (סעיף `dexopen`) וב־`evidence/`.

**תופעות לוואי צפויות (קוד משחק קיים שנפתח):** (א) בפתיחה הראשונה של ה־Pokédex, אם Mankey ‏(#56) עוד לא "נראה", ‏`PokedexUI::EnsureMankeySeenForDLC` מסמן אותו כ־Seen ‏(form 0) — כך המשחק נוהג כש־DLC מדליק את הרשימה; זה SeenMask בשמירה, לא Caught ולא פוקימון חדש. (ב) מונה ה־Mega Dex שמתפרסם לטלמטריה כולל רשומות Hyperspace.

**מה הוכח ומה לא:** בדיקות host: ‏ASan+UBSan על הפונקציות המתורגמות האמיתיות (מקור מול מתוקן: המקור מסתיר רשומות Hyperspace כשהדגל 0, המתוקן מונה אותן; עם המתג כבוי זהה למקור; מוכנות, שחרור holder, רשומות נקראות ולא נכתבות, ABI) ו־38 בדיקות הגנה של ה־patcher עברו; הבנייה אומתה offline (קלטים זהים ל־r28a, ‏imports, קריאות מקושרות, רישום ה־runtime, ‏self inspection). **אין הוכחה במשחק (לא במחשב ולא בקונסולה) שהרשימה נפתחת — לפי החלטת Tomer לקו התיקונים הזה, הקונסולה היא הבדיקה.** ב־klog: ‏`[dexopen] DLC::IsHyperspaceDexEnabled (f_70008d4178): FLAG_DLC_DEX_ENABLE=0 -> 1 (forced: Hyperspace Pokedex list open) (call N)` ו־`[dexopen] Pokedex::GetMegaDexCount (f_700033f8d8): …`, פעם אחת לכל אתר.

## 3. שימוש
- אין פעולה נדרשת. שלושת התיקונים פעילים תמיד.
- צפי בקונסולה: ה־Pokédex נפתח עם מעבר לרשימת Hyperspace מההתחלה, המינים שנתפסו מה־DLC מופיעים בה, המספר בפאנל המשימות נשאר Lumiose + Hyperspace; ראו `TEST-HE.md` סעיף 4.

## 4. התקנה וחזרה לאחור
לפי `INSTALL-HE.md`: רק כשהמשחק סגור, גיבוי טרי ומאומת של השמירה של כל ריצה, ‏eboot בלבד, ‏`.new` → readback → rename → readback.

**SHA-256 של r28b-play ‏`PPSA91762/eboot.bin`:** `ffd2cf18fc513ec4400d949325a5db2771336adb479b71026c7063280dd6aa26` (גם ב־`SHA256SUMS.txt` וב־`BUILD-INFO.json`).

חזרה: ‏r28a-play ‏`5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea` ‏(`rollback/r28a-play/eboot.bin` בחבילה); ‏r28-play ‏`65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568` ‏(`rollback/r28-play/eboot.bin`); ‏r27b ‏`c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153` ‏(`artifacts/randomizer-r27b-play`). החזרת eboot אינה נוגעת בשמירות; **לעולם לא משחזרים שמירה ישנה מעל התקדמות חדשה.**

## 5. שילוב עם חבילת המודלים
ראו `MERGE-HE.md`: אם החבילה משנה רק נתונים, לוקחים את ה־eboot הזה כמו שהוא; אם היא נושאת eboot משלה, בונים מחדש על העץ של r28b עם שלושת סקריפטי ההחלה (הפקודות המדויקות שם).

## 6. מקורות ובנייה
- `port/rando-dexopen/` — התיקון, הבדיקות, `ps5/apply-r28b.sh` (אובייקטים), ‏`build-r28b.sh` (העץ המלא), ‏`verify-r28b.py`, ‏`make-build-info.py`, ‏`deliver-r28b.py`, ‏`research/` (סריקת צד־הנתונים).
- `port/runtime-texfix/`, ‏`port/rando-dexcount/` — התיקונים של r28a (לא שונו).
- עץ הבנייה הסופי ב־WSL: `/home/tomer/ps5-za-native/r28b-play-20261030` (קריאה בלבד; שלמותו אומתה ב־`sha256sum -c`). ה־PIE שם משמש לפענוח כתובות `caller` ולפענוח קריסות עם `za_atlas.py crash`. הבנייה השנייה (`…-repro`) הפיקה את אותם חמישה SHA-256 (eboot ‏`ffd2cf18fc513ec4400d949325a5db2771336adb479b71026c7063280dd6aa26`; היומן ב־`evidence/repro-build-2.log`, ההשוואה ב־`evidence/reproducibility.json`) ונמחקה אחר כך, כי דיסק C: של המחשב התמלא במהלך כתיבותיה האחרונות ופלטיה המאוחרים אבדו. **דיסק C: נשאר כמעט מלא** — לשחרר מקום לפני בניות נוספות.
- `evidence/` בחבילה: הבקרה (שתי היחידות משוחזרות בית־בבית, `dexopen/apply.log`), התשומות (`base-copy.json`, ‏`inputs.json`: הכול זהה ל־r28a חוץ מהמפורט), בדיקות התמונה (`image-checks.json` מול r28, ‏`image-r28b.json` מול r28a), הרישום, ה־self inspection, בדיקות ה־host (`host-tests.log`) וסריקת צד־הנתונים (`data-side/`).

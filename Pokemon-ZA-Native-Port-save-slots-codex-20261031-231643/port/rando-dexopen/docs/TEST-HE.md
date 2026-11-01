# בדיקת r28b-play ב־PS5 — שלושת התיקונים

**לסוכן הקונסולה, בתיאום עם Tomer. משך: 35–50 דקות. ‏Continue לריצה הפעילה; לא פותחים ריצה חדשה בלי Tomer.**
r28b = r28a (texfix + dexcount) + **dexopen** (רשימת ה־Hyperspace Pokédex פתוחה מההתחלה). סעיפים 1–3 הם בדיקות r28a כמו שהן; סעיף 4 חדש. **ל־dexopen אין הוכחה במשחק (לא במחשב ולא בקונסולה) — לפי החלטת Tomer, הבדיקה הזו היא ההוכחה.**

## 0. לפני ההתחלה
- ההתקנה לפי `INSTALL-HE.md` הסתיימה, כולל שני ה־readback.
- **מפעילים את קליטת ה־klog לפני הפעלת המשחק**, ומשאירים אותה עד שהמשחק נסגר. שומרים הכול ב־`evidence/r28b-hardware-<תאריך>/all.klog.log`.

## 1. שהבנייה הנכונה רצה
- בעלייה: `[za-texguard] r28a texfix active: live list locked, finalized textures guarded and quarantined (4096), present under exec_lock` (ה־texfix של r28a נשאר כמו שהוא).
- בפתיחה הראשונה של ה־Pokédex (או של מסך שסופר את ה־Mega Dex): שורת `[dexopen] …` (סעיף 4). אם אין אף שורת `[dexopen]` אחרי פתיחת ה־Pokédex: זה לא r28b. עוצרים ומחזירים גרסה לפי INSTALL-HE.md.

## 2. תיקון הטקסטורות (texfix) — כמו ב־r28a
מבצעים מעברי סצנה רבים, ורושמים שעה בקירוב לכל מקבץ:
- כניסה ויציאה מבניינים: לפחות 10 (Pokémon Center, חנויות, הקפה).
- Wild Zones: כניסה ויציאה לפחות 5 פעמים.
- קרבות: לפחות 5 עם פוקימונים בטבע, ועוד קרב מאמן אחד אם יש.
- תפריטים: לפחות 20 פתיחות וסגירות. תפריט X ודפיו, המפה, ה־Pokédex (**כולל מעבר לרשימת Hyperspace**), התיק, ותפריט L3+R3 (FPS TRIAL, ‏ITEMS בעמוד 2).
- Flying Taxi: לפחות 5 נסיעות.
- שמירה במשחק: לפחות 3.
- פעם אחת לפחות: יציאה מסודרת, הפעלה מחדש ו־Continue.
- הליכה ברחובות עם שמיים פתוחים, במקומות שבהם הופיעו הצורות הכהות (תמונת הייחוס: `evidence/sky-artifact-20261030/tv-photo-tomer.jpg` בחבילת r28a), בשעות יום שונות במשחק.

**מה מחפשים:** `[za-native-fault]` או `signal 11` (קריסה — לשמור את 40 השורות שאחריהן); שורות `[za-texguard] … is not live …` ו־`counts at frame` (לא תקלה — לרשום את כולן); צורות כהות בשמיים (תמונה, שעה, מקום; לציין גם אם **לא** הופיעו).

## 3. ספירת ה־Pokédex במשימות (dexcount) — כמו ב־r28a
**מה תוקן:** "Register at least five species" של Main Mission 2, שני ה־triggers במעבדה ו־46 בקשות "Filling Your Pokédex" של Mable סופרים Lumiose + Hyperspace, והמספר "Number Registered N/M" מראה אותו מספר. מיני DLC שנתפסו קודם כבר רשומים ונספרים מיד. לא נכתב דבר לשמירה.
1. Continue לריצה הקיימת. עם הרנדומייזר מיני DLC מופיעים כבר באזורים הראשונים.
2. אם Main Mission 2 נמצאת ב־"Register at least five species": תפריט ראשי (X) → "Number Registered" = Lumiose + DLC שנתפסו. ‏klog: ‏`[dexcount] mission panel Number Registered: lumiose=L hyperspace=H combined=L+H (call N)`.
3. כשה־combined ≥ 5: במעבדה המשימה מתקדמת. ‏klog: ‏`[dexcount] have_pokemon_encyclopedia_total condition: … combined=…`. עם combined < 5 עדיין דיאלוג "not yet".
4. בקשות Mable: "Filling Your Pokédex (NN)" לפי Lumiose + Hyperspace; "Filling Your Hyperspace Pokédex" — רק Hyperspace.
5. שמירה, סגירה, Continue — אותם מספרים.

## 4. רשימת ה־Hyperspace Pokédex פתוחה מההתחלה (dexopen) — חדש
**מה תוקן:** רשימת ה־Mega Dimension (Hyperspace) ב־Pokédex הייתה מוסתרת עד שסיפור ה־DLC מדליק את `FLAG_DLC_DEX_ENABLE`. ב־r28b שני הקוראים של הדגל (‏`DLC::IsHyperspaceDexEnabled` ו־`Pokedex::GetMegaDexCount`) מתייחסים אליו כדלוק בכל פעם שמנהל הדגלים מוכן. **הדגל עצמו והשמירה לא נכתבים**; סיפור ה־DLC, הגישה ל־Hyperspace והדונאטס לא משתנים.

**בדיקה:**
1. Continue לריצה הקיימת (ריצה שבה סיפור ה־DLC **לא** הדליק את הדגל — זה המצב של כל ריצה שלא הגיעה לשלב הזה ב־DLC). אפשר גם ריצה חדשה, בתיאום עם Tomer.
2. פתח את ה־Pokédex מהתפריט הראשי. **צפוי:** אפשר לעבור בין רשימת Lumiose לרשימת Hyperspace (כפתור המעבר/הכרטיסייה של Hyperspace זמינים) **מההתחלה**; ברשימת Hyperspace מופיעים המינים שנתפסו מה־DLC כ"נתפסו" (הם נרשמו בשמירה גם לפני התיקון). ‏klog: ‏`[dexopen] DLC::IsHyperspaceDexEnabled (f_70008d4178): FLAG_DLC_DEX_ENABLE=0 -> 1 (forced: Hyperspace Pokedex list open) (call N)` — פעם אחת, בשימוש הראשון.
3. במסך שמראה את ספירת ה־Mega Dex (מסכי ה־Pokédex של main_1080/main_1093): ‏klog: ‏`[dexopen] Pokedex::GetMegaDexCount (f_700033f8d8): FLAG_DLC_DEX_ENABLE=0 -> 1 (forced: Hyperspace Pokedex list open) (call N)` — פעם אחת. אם במקום זה מופיע `… flag manager not ready …` זה רק אומר שהקריאה קדמה למוכנות המנהל (לא תקלה).
4. **פאנל המשימות:** "Number Registered N/M" (dexcount, סעיף 3) חייב להישאר Lumiose + Hyperspace; יחידת ה־dex בפאנל (`f_7000825960`) היא אחד מ־14 הקוראים של ה־getter — אם משהו בפאנל נראה שונה מ־r28a, לרשום בדיוק מה.
5. **תופעת לוואי צפויה:** בפתיחה הראשונה של ה־Pokédex, ‏Mankey ‏(#56) עשוי להופיע כ־"נראה" (Seen) גם אם לא נפגש — זה `PokedexUI::EnsureMankeySeenForDLC`, קוד משחק קיים שרץ כשהרשימה פתוחה. לרשום אם זה קרה. זה **לא** אמור לסמן אותו כנתפס ולא להוסיף פוקימון.
6. **מה לא אמור להשתנות:** משימות ה־DLC/‏Hyperspace עצמן (לא נפתחות מוקדם), דונאטס, סיפור ה־DLC, רשימת Lumiose, ספירות ה־dexcount. אם משהו מאלה נראה שונה, זה ממצא.
7. שמור במשחק, סגור, Continue: הרשימה עדיין פתוחה (התיקון חי בכל הפעלה, לא בשמירה). אופציונלי: PKHeX על עותק השמירה — צפויים רק שינויי משחק רגילים (ואולי Seen של Mankey).
8. **ביקורת הפוכה (אופציונלי, אם יש ריצה שבה סיפור ה־DLC כבר הדליק את הדגל):** שורות ה־`[dexopen]` צריכות להראות `FLAG_DLC_DEX_ENABLE=1 -> 1` בלי "forced" — ההתנהגות זהה למשחק המקורי.

**שורות ה־klog** מופיעות פעם אחת לכל אתר בשימוש הראשון, ושוב רק אם ערך הדגל האמיתי משתנה (למשל כשסיפור ה־DLC מדליק אותו). אין שורה = הפונקציה עדיין לא רצה (למשל לפני פתיחת ה־Pokédex).

## 5. איסוף ודיווח (בעברית)
- klog מלא.
- קריסה: כן/לא, ואם כן המיקום והשורות שאחריה.
- שורות `[za-texguard]`: כולן (אתר, caller, frame, ספירות).
- שמיים: כן/לא + תמונה.
- dexcount: המספרים לפני ואחרי כל תפיסה, ושורות `[dexcount]`.
- **dexopen:** צילום של ה־Pokédex עם רשימת Hyperspace פתוחה, שורות `[dexopen]`, האם Mankey סומן Seen, האם משהו מחוץ ל־Pokédex השתנה.
- הקצב (`[vk] t=… fps`) בהשוואה ל־r28a.

## 6. פענוח caller של texguard
מחסירים 0x400000 מהכתובת ומפענחים מול ה־PIE של r28b (`llvm-pie.elf` בעץ הבנייה `/home/tomer/ps5-za-native/r28b-play-20261030/r28b/`): `llvm-symbolizer --obj=<r28b>/llvm-pie.elf 0x<caller-0x400000>`. ‏caller `(nil)` פירושו שהאתר עצמו מזהה את המקום. לקריסה: `py -3 -I tools\za-atlas\P6\za_atlas.py crash <klog> --elf /home/tomer/ps5-za-native/r28b-play-20261030/r28b/llvm-pie.elf`.

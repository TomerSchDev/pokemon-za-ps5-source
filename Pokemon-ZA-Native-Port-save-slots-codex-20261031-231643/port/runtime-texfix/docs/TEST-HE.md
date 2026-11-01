# בדיקת r28a-play ב־PS5 — שני התיקונים

**לסוכן הקונסולה, בתיאום עם Tomer. משך: 30–45 דקות. ‏Continue לריצה הפעילה; לא פותחים ריצה חדשה בלי Tomer.**

## 0. לפני ההתחלה
- ההתקנה לפי `INSTALL-HE.md` הסתיימה, כולל שני ה־readback.
- **מפעילים את קליטת ה־klog לפני הפעלת המשחק**, ומשאירים אותה עד שהמשחק נסגר. שומרים הכול ב־`evidence/r28a-hardware-<תאריך>/all.klog.log`.

## 1. שהבנייה הנכונה רצה (שתי שורות ב־klog בעלייה)
- `[za-texguard] r28a texfix active: live list locked, finalized textures guarded and quarantined (4096), present under exec_lock`
- שורת dexcount (ראו §3; מופיעה בפעם הראשונה שמשימת dex נבדקת, לא בהכרח בעלייה).
- אם שורת ה־texguard חסרה: זה לא r28a. עוצרים ומחזירים גרסה לפי INSTALL-HE.md.

## 2. תיקון הטקסטורות (texfix): קריסות ושמיים
מבצעים מעברי סצנה רבים, ורושמים שעה בקירוב לכל מקבץ:
- כניסה ויציאה מבניינים: לפחות 10 (Pokémon Center, חנויות, הקפה).
- Wild Zones: כניסה ויציאה לפחות 5 פעמים.
- קרבות: לפחות 5 עם פוקימונים בטבע, ועוד קרב מאמן אחד אם יש.
- תפריטים: לפחות 20 פתיחות וסגירות. תפריט X ודפיו, המפה, ה־Pokédex (**כולל Hyperspace Pokédex**), התיק, ותפריט L3+R3 (FPS TRIAL, ‏ITEMS בעמוד 2).
- Flying Taxi: לפחות 5 נסיעות.
- שמירה במשחק: לפחות 3.
- פעם אחת לפחות: יציאה מסודרת, הפעלה מחדש ו־Continue.
- הליכה ברחובות עם שמיים פתוחים, במקומות שבהם הופיעו הצורות הכהות (תמונת הייחוס: `evidence/sky-artifact-20261030/tv-photo-tomer.jpg`), בשעות יום שונות במשחק.

**מה מחפשים:**
- `[za-native-fault]` או `signal 11`: קריסה. לשמור את 40 השורות שאחריהן.
- כל שורה שמתחילה ב־`[za-texguard]` חוץ משורת ה־active: `… is not live … (caller 0x…, frame N)` ושורות `counts at frame N: …`. אלה **לא תקלה** — הן המקומות שבהם המשחק השתמש בטקסטורה משוחררת והתיקון דילג. רושמים את כולן.
- צורות כהות או זבל בשמיים: תמונה, שעה, מקום. לציין במפורש גם אם **לא** הופיעו.

## 3. תיקון ספירת ה־Pokédex (dexcount)
**מה תוקן:** השלב "Register at least five species" של Main Mission 2 (‏`2_1_50`), שני ה־triggers שלו במעבדה (`trigger_main_02`) ו־46 בקשות "Filling Your Pokédex" של Mable (5 עד 230) ספרו רק את ה־Lumiose Pokédex. עכשיו התנאי `have_pokemon_encyclopedia_total_condition` סופר Lumiose + Hyperspace (Mega Dimension), כל מין פעם אחת, והמספר "Number Registered N/M" במסך המשימות מראה אותו מספר. **מינים מ־DLC שנתפסו לפני התיקון כבר רשומים** (אומת ב־PKHeX במחשב), ולכן הם נספרים מיד, בלי לתפוס מחדש. התיקון לא כותב כלום לשמירה.

**בדיקה (לפי צעדי הסוכן של dexcount):**
1. Continue לריצה הקיימת. לא צריך טבלאות או slots מיוחדים: עם הרנדומייזר מיני DLC (Mega Dimension / Hyperspace) מופיעים כבר באזורים הראשונים.
2. אם Main Mission 2 נמצאת ב־"Register at least five species": פתח את התפריט הראשי (X). במסך המשימות, "Number Registered" חייב להיות **Lumiose + DLC שנתפסו** (לפני התיקון: רק Lumiose). ‏klog: ‏`[dexcount] mission panel Number Registered: lumiose=L hyperspace=H combined=L+H (call N)`.
3. כשה־combined ≥ 5: לך לסמן המעבדה (Pokémon Research Lab). המשימה חייבת להתקדם (סצנת המעבדה, השלב "Go report your Pokédex-filling success"). ‏klog: ‏`[dexcount] have_pokemon_encyclopedia_total condition: … combined=≥5`. עם combined < 5 חייב להופיע עדיין דיאלוג ה־"not yet".
4. בקשות Mable (תפריט ראשי → research requests, אחרי משימה 2): בקשת "Filling Your Pokédex (NN)" צריכה להציג/להשלים לפי Lumiose + Hyperspace. בקשות "Filling Your Hyperspace Pokédex" (אם נראות) חייבות להמשיך לספור **רק** Hyperspace.
5. ביקורת: תפיסה של מין מ־Lumiose שלא רשום מתקדמת כרגיל.
6. שמור במשחק, סגור, Continue: המספרים חייבים להישאר זהים (התיקון לא שומר כלום). אופציונלי: בדיקת PKHeX של עותק השמירה — רק שינויי משחק רגילים.
7. דיווח: צילומים של מסך המשימות לפני ואחרי, שורות ה־`[dexcount]`, והמשימה שמתקדמת.

**שורות ה־klog מופיעות רק כש־(L,H) משתנים**, פעם אחת לכל נקודת כניסה. אין שורה = הפונקציה המתוקנת עדיין לא רצה (למשל לפני פתיחת מסך המשימות).

**לא משתנה:** מסכי ה־Pokédex, התקדמות ה־Hyperspace dex של ה־DLC (`have_dimension_encyclopedia_total_condition`, פריט type 18), תנאי השלמה/תארים, בקשות Mega dex, שמירה, דגלים ופתיחת DLC. אם משהו מאלה נראה שונה, זה ממצא.

## 4. איסוף ודיווח (בעברית)
- klog מלא.
- קריסה: כן/לא, ואם כן המיקום והשורות שאחריה.
- שורות `[za-texguard]`: כולן (אתר, caller, frame, ספירות).
- שמיים: כן/לא + תמונה.
- dexcount: המספרים לפני ואחרי כל תפיסה, ושורות `[dexcount]`.
- הקצב (`[vk] t=… fps`) בהשוואה ל־r28.

## 5. פענוח caller של texguard
מחסירים 0x400000 מהכתובת ומפענחים מול ה־PIE של r28a (`llvm-pie.elf` בעץ הבנייה): `llvm-symbolizer --obj=<r28a>/llvm-pie.elf 0x<caller-0x400000>`. ‏caller `(nil)` פירושו שהאתר עצמו מזהה את המקום.

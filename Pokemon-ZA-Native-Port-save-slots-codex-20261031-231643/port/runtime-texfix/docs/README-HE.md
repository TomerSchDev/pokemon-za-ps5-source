# r28a-play — תיקון קריסת הטקסטורות + ספירת ה־Pokédex במשימות

ל־PPSA91762 בלבד, גרסת משחק 2.0.2 עם Mega Dimension. ‏**r28a = r28-play + שני תיקונים, ב־eboot.bin בלבד.** כל מה שהיה ב־r28 (ITEMS, ‏MONEY, ‏NAME, ‏FPS TRIAL, מונה FPS, כפתור HEBREW TRIAL, ‏`submit=thread` ועומק 64, ‏4K עם רינדור 1080p) נשאר כמו שהוא: אותם אובייקטים בית־בבית, חוץ ממה שמפורט כאן. הבנייה מוכנה לבדיקה ידנית ב־PS5; **לא ניגשנו לקונסולה ולא התקנו אותה.**

## 1. תיקון קריסת הטקסטורות (texfix)

**הקריסה של r28-play** (klog ‏`[za-native-fault] sig=11 fa=a2 pc=489215`): ‏`backend_texture_destroyed` ← ‏`nvnTextureFinalize`. רשימת הטקסטורות החיות של ה־runtime (`g_live`) החזיקה NvnTexture שכבר עבר finalize ושוחרר; הזיכרון שלו נוצל מחדש, ובמקום מצביע ה־backend היה `0x2`. ‏`0x2 + 0xa0` (השדה `reg`) = כתובת התקלה `0xa2`. אומת בפירוק ה־PIE של r28 ושוחזר בבדיקת host (אותו 0xa2).

**שתי דרכים בקוד מכניסות טקסטורה משוחררת לרשימה**, ושתיהן נסגרו:
- **רישום מחדש דרך מצביע ישן:** ה־render targets הקשורים ב־executor, רשימות פקודות מוקלטות (שומרות מצביעי host; ב־NVN מותר finalize אחרי הקלטה) ו־`g_last_presented`. אחרי finalize, `tex_backend` רואה `backend == NULL` בזיכרון המשוחרר, יוצר backend חדש ומוסיף לרשימה. **המנגנון הזה נצפה בפועל במחשב** (`set-render-targets … is not live … skipped`, 4 פעמים בסשן של 12 דקות).
- **נתיב ה־present רץ בלי `exec_lock`** מול finalize על thread עבודה: `live_add`, רשימת ההשמדה הנדחית, טבלת ה־views והעתקות ה־alias נגעו בנתונים משותפים במקביל.

**התיקון** (ארבעה אובייקטים של ה־runtime: `nvn/objects.o`, ‏`nvn/vulkan/textures.o`, ‏`exec.o`, ‏`device.o`; אין עלות לכל draw):
- הרשימה היא זוגות (טקסטורה, backend) תחת נעילה משלה; התחזוקה ניגשת רק ל־backends ולעולם לא לרשומת טקסטורה; `remove` מוודא את ה־slot ומתקן בסריקה.
- finalize מנקה את כל ההפניות של ה־runtime (targets וחיתוכים ב־exec, ‏`g_last_presented`), ה־upload של הווידאו מוגן באותה נעילה, וה־present רץ תחת `exec_lock`.
- שדה שמירה `za_guard` ב־NvnTexture (ב־padding; ה־layout וגודל 200 לא משתנים). טקסטורה שעברה finalize מסומנת DEAD ונכנסת להסגר של 4096 לפני free. בנקודות הרישום ובקלט מרשימות מוקלטות (SetRenderTargets, ‏ClearTexture, ‏Copy*, ‏present, ‏pool register, ‏finalize כפול) טקסטורה מתה מדולגת ומדווחת פעם אחת לכל אתר ו־caller: ‏`[za-texguard] <אתר>: texture … is not live (guard …) - skipped, never registered (caller 0x…, frame N)`, וסיכום `counts at frame N` כל 1800 פריימים כשיש שינוי. בעלייה: `[za-texguard] r28a texfix active …`.

**הקשר לצורות הכהות בשמיים:** השערה בלבד. טקסטורה שנרשמת מחדש מקבלת image שתוכנו לא מוגדר. בדיקת הקונסולה צריכה לומר אם הן נעלמו.

**מה הוכח:** בדיקות host תחת ASan+UBSan ו־TSan (clang 21 ו־gcc 15) כולל ביקורת שלילית שמשחזרת 0xa2; במחשב (runtime ‏v0.1.4 עם התיקון) סשן מתוסרט של 19,347 פריימים עם רחובות, בניינים, תפריטים, מפה, ניסיונות קרב ושלוש שמירות, וסשן טעינה של השמירה הזו — בלי קריסה, ו־4 דילוגים מתועדים. הפרטים ב־`port/runtime-texfix/README-HE.md` וב־`evidence/r28a-texfix/`.

## 2. ספירת ה־Pokédex במשימות (dexcount)

השלב "Register at least five species" של Main Mission 2 (‏`2_1_50`), שני ה־triggers שלו במעבדה ו־46 בקשות "Filling Your Pokédex" של Mable (5–230) ספרו רק את ה־Lumiose Pokédex; מינים שנתפסו מ־Mega Dimension (ה־Hyperspace Pokédex) לא קידמו אותם. עכשיו התנאי `have_pokemon_encyclopedia_total_condition` והמספר "Number Registered N/M" במסך המשימות סוכמים את שתי הרשימות (זרות: 232 + 132 מינים; כל מין פעם אחת). מיני DLC שנתפסו בעבר כבר רשומים בשמירה (אומת ב־PKHeX), ולכן נספרים מיד. התיקון לא כותב כלום לשמירה; ה־Pokédex, התקדמות ה־Hyperspace dex (type 18), תנאי השלמה ובקשות Mega dex לא משתנים.

**מה השתנה:** שתי יחידות משחק בארכיון — `main_310.o` (‏`f_7000a1158c`, מעריך התנאי: אחרי ספירת Lumiose ‏`f_700033e770(manager,0,0)` שואל גם את Hyperspace ‏`(manager,1,0)` ומשווה את הסכום) ו־`main_261.o` (‏`f_700082b5c4`, ערך פריט המשימה, נתיב type 2 בלבד) — ואובייקט חדש `za_dexcount.o` (סכימה רוויה, ללא נעילות, ללא גישה לזיכרון המשחק; trace ל־klog). היחידות המקוריות משוחזרות מהארכיון בית־בבית (בקרה), וכל 1410 החברים האחרים זהים. ה־SHA-256 ב־`BUILD-INFO.json` (סעיף `dexcount`) וב־`evidence/dexcount/`.

**מה הוכח ומה לא:** בדיקות host: ASan+UBSan על הפונקציות המתורגמות האמיתיות (מקור מול מתוקן) ו־24 בדיקות הגנה של ה־patcher עברו; ‏PKHeX במחשב הוכיח שמיני DLC שנתפסו מוקדם רשומים. **אין הוכחה במשחק (לא במחשב ולא בקונסולה) שהמשימה מתקדמת — לבקשת Tomer, הקונסולה היא הבדיקה.** ב־klog: ‏`[dexcount] have_pokemon_encyclopedia_total condition: lumiose=L hyperspace=H combined=L+H (call N)` ו־`[dexcount] mission panel Number Registered: …`, פעם אחת כשהערכים משתנים.

## 3. שימוש
- אין פעולה נדרשת. שני התיקונים פעילים תמיד.
- צפי בקונסולה: אין `[za-native-fault]`; תפיסה מ־Mega Dimension מקדמת את Main Mission 2 ובקשת Mable; ראו `TEST-HE.md`.

## 4. התקנה וחזרה לאחור
לפי `INSTALL-HE.md`: רק כשהמשחק סגור, גיבוי טרי ומאומת של השמירה של כל ריצה, ‏eboot בלבד, ‏`.new` → readback → rename → readback.

**SHA-256 של r28a-play ‏`PPSA91762/eboot.bin`:** `5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea` (גם ב־`SHA256SUMS.txt` וב־`BUILD-INFO.json`).

חזרה: ‏r28-play ‏`65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568` ‏(`rollback/r28-play/eboot.bin` בחבילה); ‏r27b ‏`c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153` ‏(`artifacts/randomizer-r27b-play`). החזרת eboot אינה נוגעת בשמירות; **לעולם לא משחזרים שמירה ישנה מעל התקדמות חדשה.**

## 5. שילוב עם חבילת המודלים
ראו `MERGE-HE.md`: אם החבילה משנה רק נתונים, לוקחים את ה־eboot הזה כמו שהוא; אם היא נושאת eboot משלה, בונים מחדש על העץ של r28a עם שני סקריפטי ההחלה (הפקודות המדויקות שם).

## 6. מקורות ובנייה
- `port/runtime-texfix/` — התיקון, הבדיקות, `build-r28a-candidate.sh` (r28 + texfix), ‏`build-r28a-final.sh` (+ dexcount), ‏`verify-r28a.py`.
- `port/rando-dexcount/` — התיקון השני ו־`ps5/apply-r28a.sh`.
- עץ הבנייה הסופי ב־WSL: `/home/tomer/ps5-za-native/r28a-play-final-20261030` (קריאה בלבד). ה־PIE שם משמש לפענוח כתובות `caller`.
- `evidence/` בחבילה: הבקרה (ארבעת האובייקטים משוחזרים בית־בבית), התשומות (הכול זהה ל־r28 חוץ מהמפורט), בדיקות התמונה, הרישום, ה־self inspection וה־patch המלא.

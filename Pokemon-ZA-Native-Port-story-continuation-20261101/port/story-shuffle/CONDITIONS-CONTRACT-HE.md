# חוזה תנאי הסיפור — מחקר r2

ל־`phase_condition` ול־`work_condition` יש רישומי factory נפרדים בקוד המשחק.
מספר אופרטור זהה אינו מוכיח משמעות זהה בשניהם. ה־oracle אינו רשאי לשטח אותם
ל־`(operator,args)` או להסיר ארגומנטים שלא פוענחו.

כל רשומת ראיה שומרת:

- `kind` ו־`factory_key`: שם ה־discriminator המקורי בנתונים.
- `serialized_operator`: המספר מהטבלה. `operator` נשאר alias לצורך קריאת ראיות ישנות.
- `arguments`: כל הארגומנטים, בסדר המקורי; בתנאי work גם `SYS_WORK_PHASE` והערך הנוסף.
- `table_offset`: מיקום הטבלה בקובץ שנקרא. רשומה שנבנתה מחדש יכולה לקבל offset אחר.
- `source` ו־`condition_input_sha256[source]`: זיהוי הקובץ ו־hash הקלט שלו.
- זוג `vanilla`/`changed`: לפני ואחרי; החלפת factory היא שגיאה בפני עצמה.
- `runtime_operator` שומר את המספר לאחר normalization, ו־`normalization_proven=true`
  מפנה לפרופיל `za202-condition-numeric-1`. `serialized_operator` הוא u32 גם כאשר
  קורא הטבלאות הפנימי משתמש ב־i32. אין לפרש את מספר ה־wire כאילו היה opcode של runtime.

`condition_pairs` מחזיק בזיכרון את הרשומות המלאות. בדוחות המסירה של `audit.py` נשמרים
רק מספר הרשומות ו־SHA-256 של ההיטל המלא, כדי לא להעלות את כל נתוני תנאי המשחק.
`unmodeled_conditions` מרכז מקרים שאין
להם מודל מותר, עם סוג התנאי, כל הארגומנטים, hash המקור והסיבה לחסימה.
`invariant_failures` מפריד שגיאות לפי המודל המוכח מחסמי הסכמה;
`ok` נשאר false אם יש אפילו תנאי לא מפוענח.

זהות מבנית אינה פענוח סמנטי. `structurally_unchanged=true` מתעד שה־kind/מספר/ארגומנטים
לא השתנו; `semantic_pass` נשאר false לתנאי לא מפוענח, גם בסדר הפרקים המקורי.
בפרט, תנאי סף שלא נערך עדיין יכול להתנהג אחרת כשסדר ה־phase משתנה.
אין פטור כללי ל"שורות שלא נגעו בהן".

מחקר הקוד הוכיח את המסלול מה־FlatBuffer, דרך normalizer, עד descriptor וקריאת factory.
טבלת wire1..8 היא `[2,3,6,4,7,5,8,9]`; מספרים אחרים נשמרים. לכן wire7 הוא טווח פתוח,
wire8 טווח סגור, wire100 הוא `[a,b)` ו־wire101 הוא `(a,b]`. ההנחה הישנה שכולם טווח
כולל הייתה שגויה. מקור ה־NSO הוא SHA-256
`2308530d73b7fea60bb845ad57d9b1f10d3ff213f89c01f73627dc8224f43ef9`.
ה־source callchain וה־GOT/descriptor bindings נמצאים ב־`STATIC-PROVENANCE.json` במסירה.

שני ה־callbacks קוראים a,b. באופרטור scalar כגון equality רק a משפיע; b עשוי להיות
נוכח אך אינו בשימוש. שמונת מקרי `[phase,0]` שנחסמו ב־r1 הם **PhaseCondition**,
ולא WorkCondition כפי שתואר בטעות במסירת r1 לפני שימור ה־kind. ה־kind המקורי לא
נשמר ב־tuple של הבודק הישן. תיקון זה מתועד ב־r2, והארכיון ההיסטורי r1 נשאר ללא שינוי.

בנפרד הוכח שגם WorkCondition על `SYS_WORK_PHASE` קורא מאותו manager ומאותו work.
היישום מגביל את התמיכה בו לצורת equality המוכחת עם שלושה ארגומנטים ו־b=0; אינו
מסיק תמיכה במשתני work אחרים. בקורפוס שנבדק אין שורות alias כאלה. מחרוזות שאינן
מספרי u32 עשרוניים, מבנים לא נתמכים ואופרטורים לא מוכרים נשארים חסומים.

תוצאות הבדיקות המחייבות רשומות ב־HANDOFF ובדוחות המתוארכים. מעבר של בדיקות נתונים
אינו אישור להשלמת פרק או לשילוב ב־UI/PS5; כל שערי השילוב נשארים false.

## Lua namespace — המשך r3

החלפה לפי מספר phase או substring PHASE הופרכה: היא שכתבה גם DLC, וה־oracle הישן
חלק את אותה טעות. מקור r2 והמטריצה הישנה נשמרים כ־negative control.
`lua-context-manifest.json` הוא רשימת הקשרים למקור Lua מלא חתום, עם prototype/K-index,
code SHA, מרחב, רשימת references ו־use closure מוגבל. אין להסיק מרחב משם prototype
או מערך המספר. כתיבה של K פוגעת בכל שימושיו, ולכן mixed/unknown/incomplete חסומים.

הקבוע הראשי היחיד באיחוד המועמדים הוא r/5990 K7=51200, עם EQK ישיר יחיד.
ה־writer רשאי לערוך רק אותו. הבודק מחשב independently את טבלת הקבועים הצפויה
ומוודא byte preservation מחוץ ל־payload שלו. הוא אינו קורא לפונקציית ה־writer.
חסר Lua או mismatch במקור/manifest עוצרים generation לפני פלט; `--no-lua` אינו
פטור מהאימות ואינו יכול לעבור אם הסדר מחייב תרגום MAIN.

ה־namespace מוכח לפי exact key ב־call arguments. המימוש native של שם פונקציית Lua
המגובב אינו מוכח; אין להציג זאת כהוכחת interpreter או runtime מלאים.
שינוי נתוני המשחק/ה־Lua דורש review ו־manifest חדש, לא repin checksum אוטומטי.

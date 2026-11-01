# ערבוב הסיפור — המשך מחקר r3

מקור המחקר הוא `story-rando` ב־`64973b2`, ואחריו חמשת כלי `story-shuffle` של Claude.
המקור המקורי נשמר ב־snapshot; העבודה כאן מבודדת בענף `codex/story-shuffle-continuation-20261101`.
אין התקנה, שינוי שמירה, חיבור ל־UI או קידום למשחק הראשי.

## תיקון שנדרש בעקבות הביקורת

כלל ה־Lua הישן זיהה phase לפי המספר או המחרוזת PHASE. הוא ערבב גם
`SYS_WORK_DLC_PHASE`: בסדר4→6→5→7→8 שלושה מתוך ארבעת הקבועים ששינה היו של DLC.
ה־oracle השתמש באותו כלל ולכן אישר את ההשחתה. מטריצת r2 שעברה24/24 היא
**negative control פסול**, ולא הוכחת נכונות. המקור והתוצאות שלה נשמרים ללא שינוי.

r3 משתמש ב־manifest חתום למקור Lua מסוים. האיחוד לכל24הסדרים כולל18קבועים:
17במרחב DLC נשארים ללא שינוי, ורק `r/5990 K7=51200` שייך לסיפור הראשי ומותר לתרגום.
הכותב עורך רק את payload הקבוע הראשי. הבודק משווה בנפרד את עץ ה־Lua המלא ואת כל
הבייטים שמחוץ ל־payload המותר. מקור לא מוכר, manifest לא תואם, מרחב מעורב/לא מפוענח,
כיסוי שימושים חסר או Lua חסר נחסמים לפני ייצוא עץ mod.
ההוכחה היא לזרימת מחרוזת המפתח המדויקת אל פונקציית Lua; binding ה־API המגובב
למימוש native עדיין אינו מוכח. אין להרחיב את הרשימה אוטומטית לקלטים חדשים.

## תנאים ומסירה

ה־oracle משמר factory וכל הארגומנטים. מיפוי wire1..8 הוא `[2,3,6,4,7,5,8,9]`;
wire7 פתוח,8 סגור,100 `[a,b)`,101 `(a,b]`. פרטים ב־`CONDITIONS-CONTRACT-HE.md`.
שמונת מקרי `[phase,0]` הם PhaseCondition ולא WorkCondition כפי שסווגו בטעות ב־r1.
היסטוריית r1 נשמרת; הסיווג תוקן במסירה החדשה.

הפעלה רק דרך `zw` הקנוני, ולאחר קבלת תור `pc-queue`:

```powershell
zw story-shuffle-test Synthetic Integration.test_identity_is_semantically_vanilla OracleMutations -v
zw story-shuffle-tool audit C:\outside-git\NEW-story-audit
zw story-shuffle-tool story_shuffle C:\outside-git\NEW-story-mod --order 4,6,5,7,8
```

ה־CLI דורש תיקייה חדשה מחוץ לכל checkout. כישלון oracle מייצר דוחות בלבד;
כישלון source/context מוקדם אינו יוצר תיקייה. נתוני משחק נשארים מחוץ ל־git ולארכיון.
תוצאות מדויקות, hashes ומגבלות מתועדים ב־HANDOFF ובמסירת r3.

## המשך נדרש

כל שערי `ready_for_ui`, `ready_for_ps5`, hardware ו־full-chapter נשארים false.
ה־oracle בודק תנאים על רשומות phase שנכתבו בנתונים, לא על כל ערך u32 זמני.
soft/clamped thresholds דורשים ביקורת לפי המשימות/מפות שהם מפעילים.

ריצת b1 ההיסטורית הציגה ניצחון והמשך שיחה, עם party/trainer fixtures מקלים.
היא תואמת למקור הישן עם באג ה־DLC; היא אינה הוכחת gameplay של r3.
נדרשת השלמת פרק מוחלף, קרב/דרגת Royale ומעבר לגבול שני עם exact candidate.
קריסות PC קודמות כללו OOM/commit1455, ואינן כשלעצמן כשל של אלגוריתם הסיפור.

תוכנית הסיפור של ריצה חייבת להיות immutable וקשורה ל־hashes של כל הקבצים.
ה־run store הנוכחי אינו תומך אוטומטית ב־16טבלאות נוספות; נדרש contract של manifest,
יכולת/גרסה ו־import/export fail-closed. לא משנים סדר של שמירה קיימת ולא מוחקים
metadata לא מוכר. `catchup_shuffled.py` הוא כלי fixture על עותק שמירה בלבד.
לא הותקן שינוי סיפור, ולכן אין rollback נדרש למשחק הראשי.

## אימות r3 — תור PC22

25/25בדיקות ממוקדות עברו, כולל הפעלת oracle r2 המקורי שקיבל פלט DLC מושחת,
בעוד r3 דחה אותו. כל24הסדרים עברו עם2217תנאים לכל סדר,0כשלים ו־0סכמות לא מפוענחות.
בכל סדר נבדקו כל הבייטים מחוץ ל־payload המותר;17קבועי DLC נשארו זהים.
החלפת Lua הראשית היא0או1לפי הסדר. הקוד, ה־reader וה־manifest נותרו זהים להקפאה.
נשארו0–150softnotes ו־0–16clampedranges לסדר; אלה אינם אישור gameplay.
התוצאות וה־SHA המדויקים ב־HANDOFF ובמסירת `story-continuation-20261101-r3`.

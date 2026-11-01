# לסוכן הקונסולה/המודלים — תור התקנות משותף

התור חל על כל `192.168.1.135`, גם כשעובדים ב־titles שונים. כרגע זו תשתית הכנה ותור בלבד; היא אינה מתקינה דבר ואינה משנה בעלות על עבודה שכבר מתבצעת מחוץ לתור.

1. קראו `README-HE.md` ובדקו `py -3 -I tools/console-install-queue/console_queue.py status` מתוך `Pokemon-ZA-Native-Port`. ה־state היחיד הוא `PS5-13.60/console-install-state`; ב־WSL משתמשים באותה תיקיית `/mnt/c/...`.
2. הגישו job עם ארטיפקטים ו־SHA־256, בסיס צפוי ותלויות חיצוניות. קחו reservation רק דרך `claim`, לפי FIFO. שמרו את ה־token ושלחו heartbeat כל דקה. `lost` מחייב לעצור פעולות קונסולה מיד.
3. לפני חלון התקנה תעדו handoff של הבעלות הקודמת, משחק סגור, גיבוי טרי מאומת לכל הריצות ו־readback של ה־eboot הנוכחי. הפעילו `heartbeat --begin-install <readiness.json>` רק עם עובדות וראיות ממשיות. reservation אינה הוכחה שהקונסולה פנויה.
4. תלויות ידועות לבירור: שיחת המודלים/Rowlet `01a18be6-5f7e-7903-9aa5-59ed51a8be62`; כלי העבודה `species-lab/import-all-20261030/console-install-20261030/console_ops.py` ו־`rowlet-fix-r2`. מצב השיחה הוא אינדיקציה לתיאום בלבד, ולא בדיקת מצב הקונסולה.
5. אם ה־eboot הנוכחי כולל כבר שינויי מודלים/מוזיקה (למשל r29 music), אין להחליפו בבסיס r28a/r28b שמשמיט אותם. משווים SHA, מזהים את הבסיס ומשלבים לפי `MERGE-HE.md`. ההתקנה נשארת זמני → readback → rename → readback, לפי `INSTALL-HE.md`; הבדיקות לפי `TEST-HE.md`.
6. בסיום רשמו receipt עם קובצי שני ה־readbacks והשתמשו ב־`complete`; `release` מחזירה את אותו ticket לתור. reservation stale נשארת חוסמת עד reconciliation מפורש ומבוסס ראיות. אין לאפס state, ליצור תור נוסף או לקחת בעלות לפי timeout בלבד.

הקובץ הזה הוא מסירת הוראות מקומית. לא נשלחה הודעה לסוכן החיצוני ולא בוצעה גישה לקונסולה במסגרת הכנת התור.

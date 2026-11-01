# דרייבר ניסוי FS91780 — הכנה בלבד

עדכון אימות בפועל: PC88 הושלם ושוחרר. מקור הדרייבר49f לא השתנה. שמונה מקרי זיהוי עברו; שלוש בדיקות defer/ארבעה תרחישים עברו מול72f25; שתי בדיקות stream comparison ובדיקת HTTP application error עברו. ארבעת עצי התהליכים נסגרו עם active_processes0. משך המעטפת7.008 שניות. ראיית guard: `evidence/save-fs-console-20261101-r2/executed/guard-verification.json`, ‏SHA256 `c91266f358b88a2d2bc4f50f01a3bf1b57abc465fad8fe8573a5f105d791d4f9`. אין בדיקת חומרה או הכנה חיה כתוצאה מהבדיקות האלה.

אין הרשמה או תפיסת תור בקוד. אין חיבור לקונסולה ב־`plan` או `selftest`. חיבור חי מותר רק לאחר סקירה, כל הראיות והקבצים מוכנים, ו־GO מתואם של הסוכן הראשי. אין כאן הרשאה עצמאית להתקנה.

הדרייבר קבוע ל־PPSA91780. הוא קורא להתקנה הקנונית `install-main.bundle_main` עם `--defer-complete`, ומשתמש ב־`run_r3.Console`, ‏`KlogCapture`, ‏`bounded_file`, ‏`Lease` וב־`close_owned` הקיימים. רק callback זיהוי הבעלות מותאם זמנית ל־FS, בתוך עותק מודול מיובא פרטי. אין מתקין, parser, payload או פרוטוקול FTP מקביל.

## קבצים מוכנים ו־pins

- `driver.py`: ‏`49f7112a620d62c4482df584777d44456522608f1b520483eaabe1c3358e1851`.
- `CONFIG.json`: ‏`8628589e6ba31f8ed25d60c410c5126d5fa16a331d8705d83e439667ad74b886`.
- שמונה קובצי `fs91780-job.json` קיימים ומוגדרים מראש, fingerprint ‏`2f5160e4ba13751c0628d8f19c7cd79cdc26b5906957f37e25b686b69566a645`.
- eboot ‏`d5cf6177…`, launcher ‏`01e2b20d…`. נתיב launcher בודד: `/data/homebrew/PPSA91780/launch.elf`; הלוג שלו נכתב בידי ה־launcher עצמו תחת אותו app.
- המתקין הקנוני ‏`72f25da1…`: הסוכן הראשי סקר את השינוי מ־696473, שמוסיף מצב compare אופציונלי. הדרייבר אינו מספק `--compare-readbacks` ומשתמש במסלול bounded הרגיל. בדיקות defer חייבות לרוץ שוב מול ה־SHA הנוכחי לפני גישה חיה.
- גיבוי18 ריצות/122 קבצים הקודם משמש מקור השוואה בלבד. אין טענת fresh ללא אימות חי חדש של כל הרשימה ושני hashes לכל קובץ.

שינוי קוד/תלות/pin מחייב סקירה מחוץ לתור. אין repin אוטומטי.

## פקודות מוכנות

להריץ מה־checkout הקנוני. הפקודות אינן בונות או מורידות תלות.

```powershell
$fsConfig = 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port-story-condition-research-20261101\port\save-fs-probe-console\CONFIG.json'
$fsConfigSha = '8628589e6ba31f8ed25d60c410c5126d5fa16a331d8705d83e439667ad74b886'
.\zw save-fs-console plan --config $fsConfig --config-sha256 $fsConfigSha --out evidence/save-fs-console-20261101-r1/offline-plan.json
```

תוצאת plan צפויה: שמונה קבצים מאומתים, side_app91780, ‏`console_access:false`, ‏`OFFLINE_ARTIFACTS_READY_ONLY`. זו אינה מוכנות חיה ואינה בדיקת חומרה.

אחרי שכל מקורות הבדיקות וה־pins מוכנים, בתור PC קנוני קטן נפרד:

```powershell
.\zw save-fs-console selftest --config $fsConfig --config-sha256 $fsConfigSha --out evidence/save-fs-console-20261101-r1/identity-tests.json
.\zw save-install-defer-test --repo 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port' --candidate 'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port\port\main-install\install-main.py'
.\zw install-guard-test -k stream_comparison
.\zw install-guard-test -k http_application_error
```

הראשונה בודקת שמונה מקרי זיהוי/סירוב סינתטיים. השנייה היא שלוש בדיקות defer קיימות, ארבעה תרחישים. שתי הפקודות האחרונות מריצות רק את שתי בדיקות ההשוואה ואת בדיקת שגיאת HTTP. פלט אמיתי נשמר עבור כולן בתור88. קובץ `guard-verification.json` בסכמה `fs-driver-verification-1` מפנה ב־`identity_tests` וב־`defer_tests` לראיות בפועל עם path/SHA256, ובנוסף לשתי בדיקות התלות. ה־driver והמתקין חייבים להתאים ל־hash שבפלט הבדיקות. ללא הוכחות אלה גם `prepare-live` מסרב להתחבר.

אחרי סקירה ו־GO, **לפני הרשמה לתור ההתקנה**, ורק כשאין owner או מדידת FPS:

```powershell
.\zw save-fs-console prepare-live --config $fsConfig --config-sha256 $fsConfigSha --verification GUARD-VERIFICATION.json --verification-sha256 GUARD-VERIFICATION-SHA --coordination ACTUAL-HUMAN-HANDOFF.json --out 'C:\Users\Tomer\AppData\Local\Temp\za-fs91780-live-prep-NEW' --console-ok
```

ה־handoff הוא הודעת משתמש אמיתית, לא דוגמת אישור: `approved_by:Tomer`, ‏`scope:read_only_console_preparation`, ‏`game_closed:true` וציטוט המקור. הדרייבר אינו כותב אותו בעצמו. המחשב לא מחזיק תור קונסולה במהלך ההכנה; לפני קריאה ובכל chunk/MLSD נבדק `Board().load().active is None`. הופעת owner עוצרת וסוגרת את חיבור ההכנה.

ההכנה בודקת שאין תהליך משחק, שאין התנגשות title/data/registration, שאין sandbox שמונע את ה־launcher, ושאין mount.lnk של91780. היא משווה רשימת ריצות וקבצים מלאה לגיבוי הקודם, מאמתת את עותקיו המקומיים ואת כל הקבצים החיים פעמיים, וקוראת את תשעת נתיבי MAIN המוגדרים, כולל eboot. `prepared.json` נוצר רק בסוף אימות תקין. אם השמירה אינה נגישה כשהמשחק סגור, או שנוסף/השתנה קובץ: `NOT-READY`, בלי mount/launch/restore. יש לתאם בנפרד את כלי הגיבוי/התפריט הקיים; אין פעולה סמויה.

לפני ההרשמה כל המקורות, תוצרי בדיקות, גיבוי, readbacks, תוכנית זו ותבניות readiness/handoff צריכים להיות מוכנים. לאחר הקצאת מספר תור יש לקשור רק את מספר הכרטיס לנתוני ההכנה שכבר נמדדו, בלי לרענן `checked_at` ובלי לשנות את המועמד. ראיה שעברה חמש דקות/מצב שהשתנה מחייבים withdrawal ורענון מחוץ לתור.

```powershell
.\zw save-fs-console run --config $fsConfig --config-sha256 $fsConfigSha --verification GUARD-VERIFICATION.json --verification-sha256 GUARD-VERIFICATION-SHA --prepared PREPARED.json --readiness READINESS.json --handoff HANDOFF.json --out 'C:\Users\Tomer\AppData\Local\Temp\za-fs91780-install-test-NEW' --console-ok
```

פקודת run דורשת lease קונסולה קנוני פעיל ומועמד תואם. נתיבי ראיות חיים חייבים להיות מקומיים בכונן C:; אין העתקת main readbacks או שמירות ל־NAS מחבילה זו.

## סדר, תקציב ותוצאות

1. אימות מקומי של כל הקבצים וההכנה התקפה; סירוב קצר בעת שימוש אם הופיע תהליך או title מתנגש.
2. התקנת שמונה קבצים במסלול הקנוני: new → readback → rename → readback; שמירת ה־lease עם defer.
3. המתנה לרישום ShadowMount אוטומטי עד55 שניות; תוכן mount.lnk חייב להיות בדיוק `/data/homebrew/PPSA91780` (מותר סוף שורה בלבד). אין payload לרישום ואין שינוי ב־mount.
4. התחלת klog פסיבי, אימות חיבורו, הפעלת launcher מוצהר אחד, ואיסוף דוח חדש עד60 שניות. שם תיקיית הדוח כולל PID והוא חייב להתאים לתהליך החדש; param.json המותקן/מותקן־ב־sandbox ו־eboot חייבים להתאים ל־pins, ואסור שיהיה title נוסף.
5. סגירה רק דרך `close_owned` הקיים לאחר בדיקת השרשרת הזאת. תקציב הסגירה הקיים20 שניות.
6. readback חדש של כל שמונת הקבצים ושל נתיבי MAIN שהוכנו, אימות שעותק הגיבוי עדיין תקין, manifest מסירה חדש, ורק אז `Board.complete` מפורש. אין שינוי MAIN/vanilla/שמירה, ואין הפעלת91781.

תקציב כולל מתוכנן240 שניות, עם מרווח עד מגבלת600 שניות כאשר יש ממתין. זהו תקציב הכנה, לא מדידה שבוצעה. אין התחלת שלב שלא נכנס בחלון שנותר; אם השלבים לא נכנסים יש למסור בבטחה בהתאם לבעלות/כללי ניתוק.

`UNSUPPORTED_IMPORT`, ‏`UNSUPPORTED_OR_DENIED` ושאר מגבלות נרשמים ככאלה. דוח עם sentinels שלא נשמרו או result מסוג UNSAFE מסומן UNSAFE. אפילו הצלחה ללא unsupported אינה קביעה כללית של FS_SAFE. קוד יציאה של כלי ההתקנה אינו תוצאת הבדיקה.

## תקלה, עצירה ו־rollback

- שינוי PID/title/eboot/report-chain, report חסר או mount אחר: אין סגירת תהליך לא מזוהה. אם אין שרשרת בעלות מלאה והמשחק נשאר פתוח, יש לעצור ולדווח לסוכן הראשי לצורך סגירה ידנית מתואמת. אין completion מזויף.
- דוח פגום/לא שלם: להמתין רק בתוך התקציב; לסגור רק אם זיהוי הבעלות הושלם. הדוח אינו PASS.
- כשל התקנה: לשמור את transaction/error הקנוניים ואת ה־lease. אין מחיקת תיקיות או הורדה של eboot ישן. מסלול rollback של המתקין הקיים שומר עותק קודם רק כשיש baseline; כאן יעד חדש, ולכן לא מאמצים או מחליפים title קיים.
- שינוי MAIN/readback: אין restore אוטומטי ואין טענת handoff תקין. MAIN המקורי אינו יעד כתיבה של הדרייבר מלכתחילה.
- ניתוק: אותו כרטיס ובעלים נשמרים לפי התור הקנוני; לא משחררים בגלל timeout רשת.
- אין מחיקה של scratch, שמירות או תיקיות sandbox. ה־probe עצמו מטפל רק באובייקטים הפרטיים שהוא יצר; הדרייבר קורא דוח בלבד.

למסירת source ייכללו הקוד, config/job/תוכנית, hashes ותוצאות מסוכמות בלבד. אין להעתיק lease/token, שמירות, main readbacks, SDK, game assets, raw state או דוחות פרטיים גולמיים ללא סקירה.

# מנתקים תלויות ישנות ומקבעים בסיס בנייה

תאריך: 1 בנובמבר 2026. זהו מיפוי לקריאה בלבד ותוכנית הגירה; לא בוצעו בנייה, שינוי קלטים, העברה, מחיקה, עצירת תהליכים או פעולה בקונסולה.

**נמצאו תלויות ממשיות בתיקיות ישנות, ויש להסדיר אותן לפני התקדמות נוספת של המסלולים הרלוונטיים.** ההבחנה של תומר נשמרת: יבוא מודלים חיצוניים וערבוב הסיפור הם שני הפרויקטים הפעילים; היתר צפויים להיות מוכנים לקונסולה. בדיקת המקור מראה ששני המסלולים הפעילים עוסקים בעיקר ביצירת נתונים, mods ו־QA, ולא בהכרח בקומפילציית משחק C/C++ חדשה. main-1.1.0 כבר מבודד ב־frozen root עצמאי, אך שחזור תיקון ה־JSON הרשום כמותקן עדיין מפנה לקובץ מקור ב־worktree ישן. המפה המאוחדת כוללת **1,133 צמתים ו־1,429 קשרים**, ומרכזת שבע פעולות הגירה מחייבות לבדיקה. החסמים נרשמו במסמך וב־JSON; **לא הוטמעה אכיפה ולא נעצרו סוכנים אחרים בפועל**. ([המפה המובנית](BUILD_DEPENDENCY_MAP.json), [מקורות שני הפרויקטים](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/active_projects.md), [מיפוי חבילות](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/ready_artifacts.md).)

## חומר עדכני פירושו בסיס מאושר ושלם

הנחיית תומר האחרונה קובעת את סדר העבודה:

> אוקי מה שאתה מתאר רק מראה למה סדר מאוד חשוב... 
> אם פרויקט שעובד משתמש בחומר ישן זה לא טוב, אני מעדיף לגרום לו לעצור ולהשתמש בחומר החדש מאשר שמשאיר בלאגן

בהתאם לכך, הפניה חיה אל evidence אד־הוק, bytecode מגרסאות שונות או מקור לא־מנוהל ב־worktree אחר מסומנת **חסם הגירה**. נדרש בסיס נוכחי מאושר, עם מקור, גרסה, קלטים וראיות התנהגות. העתקת קובץ ישן לתיקייה ששמה חדש אינה מספיקה; גם בחירת הקובץ בעל התאריך החדש ביותר אינה אימות תאימות. עד שהחלופה מאומתת, שומרים את הקלט המדויק הקודם ואת מסלול החזרה כהגנה זמנית. אין בכך הצדקה לשימור אינסופי של כל העץ שסביבו. זו הנחיית העבודה של המיפוי הנוכחי, לא הרשאה להרוג תהליך לא מוכר או לשנות תור של סוכן אחר. ([כללי המשאבים](../../workbench/cards/resource-queues.md), [כללי main](../../workbench/cards/main.md).)

גרסאות compiler/SDK ו־frozen inputs של release מאושר הן מקרה אחר: גיל הקובץ לבדו אינו הופך אותן למיושנות. release lock קיים נשאר בלתי משתנה. אם מחליפים גרסת SDK, compiler או קלט שמשנה משמעות, נדרשים descriptor או release חדשים ואימות מתאים. כך נוכל לנתק תלות בתיקיית ניסוי ישנה בלי לאבד תיקון פעיל או לשנות את המשחק כדי להתאים לסידור הדיסק. ([כרטיס main](../../workbench/cards/main.md), סעיפי Freeze ו־Rules; [כללי בנייה](../../workbench/cards/build.md).)

סימון הראיות בדוח הוא **מקור** לקשר שנמצא בקוד או manifest, **מטא־נתונים** לקיום/גודל/זמן שנקראו כעת, **חתימה חדשה** כאשר חושב SHA לקובץ קטן במחקר, **מתועד קודם** לחתימת בינארי או תוצאת בדיקה מרשומה קיימת, ו־**הצעה** לפעולה שטרם בוצעה. קובץ שקיים אינו בהכרח תואם; hash שנרשם בעבר אינו בדיקת תוכן חדשה; רישום baseline מקומי אינו אימות חי של הקונסולה.

## שני הפרויקטים הפעילים דורשים חבילות קלט נוכחיות

| פרויקט | השורש שנמצא במקור | המסלול הנוכחי וראיית מצב | חסם שצריך לסגור |
|---|---|---|---|
| יבוא מודלים חיצוניים | `PS5-13.60/species-lab/import-all-20261030/tools` | QA תחת `pc-fifty-20261031-r1/prepared-suite-20261101-r1`; manifest r4 מצהיר על 6,878 קלטים | כלים וקלטי הכנה מפוזרים בין r1/r2/r4 ו־pilot קודם |
| ערבוב הסיפור | `Pokemon-ZA-Native-Port-story-continuation-20261101/port/story-shuffle` | generator data-only; handoff מתעד `ready_for_ps5=false` ו־`ready_for_ui=false` | summary r3 מתיקיית evidence קנונית, parser מ־story-rando וקלט `--base-mods` דינמי |

אלה **סיווגי משתמש וקשרים מוצהרים שנבדקו במקור**, לא ניטור של קבצים שנפתחו בפועל בריצה חדשה. לסיפור יש קוד modified/untracked; HEAD לבדו אינו snapshot מלא. לא נמצא consumer נוכחי מאומת של שני הפרויקטים אל build root של WSL בתחום הסריקה, אך אין בכך הוכחת global no-use. ([הערות הפרויקטים](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/active_projects.md), [מיפוי WSL](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/wsl_inventory.md).)

### המודלים כבר משתמשים ב־NAS, אך חבילת הכלים טרם אוחדה

**מקור:** `storage_paths.py` מגדיר NAS root דרך `POKEMON_NAS_WORK_ROOT`, וממנו data/game/extracted roots. המתכונים צורכים schemas, donors, תוצרים מועמדים וקטלוג dumps שנמצאים בגבול הנתונים הקיים. חלק מהכלים גוזרים ROOT לפי מיקום הסקריפט ואחרים משתמשים ב־NAS; אין resolver אחיד לכל המתכונים. קיימת גם קומפילציית helper ב־C# מול PKHeX, בנפרד מבניית המשחק. ([storage_paths.py:4](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/import-all-20261030/tools/storage_paths.py:4>), [integrate_model_assets.py:64](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/import-all-20261030/tools/integrate_model_assets.py:64>), [Compile-PreparedSpeciesTools.ps1:9](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/import-all-20261030/tools/Compile-PreparedSpeciesTools.ps1:9>).)

**חתימת manifest חדשה, לא אימות נכסים:** `common/artifact-manifest-r4.json` בגודל 2,620,447 בתים נמדד כ־`d057b8c5343d0c6ee48d05786c846d0f53df0760c9146bd0285b6e0aa25f2512`. נספרו בו **6,850 נתיבי romfs ו־28 קלטים אחרים**. הוא עדיין מצהיר על `common/python-compiled-r1`, `python-compiled-r2`, `python-compiled-r4` ו־`compiled-r1`, כולל inspector ו־PKHeX. הקלטים האלה קיימים לפי התצפית, אך לא הוכחה נחיצות runtime של כל אחד ולא חושבו מחדש hashes לכל 6,878 הקבצים. יש לברר כל תפקיד ולהחליפו בכלי הנוכחי המאושר, ואז להפיק suite חדש ושלם. אין לשנות את המניפסט של job שכבר נרשם. ([manifest r4](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/pc-fifty-20261031-r1/prepared-suite-20261101-r1/common/artifact-manifest-r4.json>), [refresh_prepared_species_r4.py:17](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/import-all-20261030/tools/refresh_prepared_species_r4.py:17>).)

`run_pc_nas.py` הוא **מתכון חלופי/ותיק** שמכיל fetch של `payload.tar.zst` ואימות hashes. המטמון שאליו הוא מפנה, `pc-model-tests`, אינו קיים בתצפית; אין להציגו כ־runner הפעיל כיום או כתשתית אחסון כללית מוכנה. מסלול ההכנה הנוכחי משתמש ב־hebrew-lab וב־staged runs. אפשר ללמוד מה־fetch/verify הקיים בהמשך, לאחר איחוד הסמנטיקה והנתיבים. ([run_pc_nas.py:79](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/import-all-20261030/tools/run_pc_nas.py:79>), [prepare_species_suite.py:105](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/import-all-20261030/tools/prepare_species_suite.py:105>).)

### הסיפור צורך תוצאות ישנות כקלט לפעולות נוכחיות

**מקור ישיר:** `dependency_review.py:55` ו־`prepare_end6_probe.py:36–37` קוראים את `Pokemon-ZA-Native-Port/evidence/story-continuation-20261101-r3/all24-model/summary.json`. הקובץ קיים. `lua_context.py:15–16` ו־`oracle.py:126` משתמשים ב־`port/story-rando/tools/luadump`; ה־Lua manifest המקומי מקובע בחתימה. `story_shuffle.py` משתמש גם ב־`hebrew-lab/tools/fbedit` וב־RomFS, ו־probe מקבל `--base-mods` שאינו נפתר לנתיב יחיד מתוך המקור בלבד. ([dependency_review.py:55](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port-story-continuation-20261101/port/story-shuffle/tools/dependency_review.py:55>), [prepare_end6_probe.py:36](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port-story-continuation-20261101/port/story-shuffle/tools/prepare_end6_probe.py:36>), [lua_context.py:13](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port-story-continuation-20261101/port/story-shuffle/tools/lua_context.py:13>), [oracle.py:126](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port-story-continuation-20261101/port/story-shuffle/tools/oracle.py:126>).)

לכן חבילת הסיפור הנוכחית צריכה לקבל summary שנוצר מהמודל ומה־schema העדכניים המאושרים, או ראיה מפורשת שאותו תוכן עדיין תקף. יש לאחד את תלות parser ה־Lua עם גרסת מקור ותוצאות regression מתאימות, ולפתור את base-mods לכל invocation. העברת r3 summary כמות שהוא לתיקייה חדשה אינה סוגרת את החסם. אלה **דרישות קבלה מוצעות שטרם בוצעו**, ולא טענה שהסיכום הנוכחי שגוי או שה־parser הישן אינו תקין.

## תוצר מוכן לקונסולה אינו בהכרח חבילת שחזור עצמאית

**מקור ומטא־נתונים:** `MAIN` מצביע על `main-1.1.0`. ב־lock יש 126 רשומות inputs: **125 נתיבי WSL בתוך `za-main-1.1.0-frozen-20261031`**, ו־Windows eboot המשמש reference/output. הבנייה משתמשת גם ב־SDK ובכלים משותפים. שדה `frozen_from` מצביע ל־Hebrew candidate היסטורי, אך `za.py` אינו משתמש בו כקלט link. לכן r26/r27/r28 אינם קלטים ישירים ל־relink הנוכחי של main. זהו בסיס ממשי לסדר חדש, ולא סיבה לשמר את כל שרשרת הפרויקטים ההיסטורית לידו. ([main lock](../../tools/za/releases/main-1.1.0.lock.json), שורות 12,161–290; [za.py](../../tools/za/za.py), שורות 172–227; [מיפוי WSL](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/wsl_inventory.md).)

| קבוצת תוצרים שנמצאה | מצב שניתן לקבוע כעת | מה עדיין צריך להיות עצמאי |
|---|---|---|
| `artifacts/main-1.1.0-20261031-01` | eboot קיים, 402,798,978 בתים; manifest קודם בן 780 קבצים מצהיר על `7d837a58…` | frozen root, package, SDK וראיות rebuild/gate |
| `artifacts/new-run-json-fix-install-20261031-r2` | eboot קיים, 402,799,298 בתים; baseline מקומי מצהיר על `36b3d5d…` | תיקון JSON, recipe, wrap flags, control וחבילת rollback |
| main-1.0.0/1.0.1 ו־r29 UI | חבילות/locks היסטוריים קיימים; לא baseline חדש | reconstruction לפי הגרסה והראיות שלה |
| r27b/r28/r28a/r28b | פרופילים וחבילות היסטוריים, לעתים כמה eboot occurrences באותה קבוצה | ספריות משותפות ומתכון שחזור של אותו profile |
| Hebrew RTL candidates ו־DLC Dex/Music | תוצרים/ראיות נמצאו, בלי promotion חדש במחקר | מקור, recipe, mods/config ו־rollback הרלוונטיים |
| Hebrew-choice side application | journal מקומי רושם PPSA91990 ו־199 קבצים; אינו המשחק הראשי | מקור helper/installer וראיות נפרדות; אין בדיקה חיה חדשה |
| 24 תיקיות artifacts נוספות | לא סווגו בסריקה התחומה | בירור תפקיד ו־consumers, בלי להסיק שאין בהן שימוש |

הטבלה נשענת על **21 קבוצות חבילה/ראיות, מהן 15 עם 20 מופעי eboot**, ולא על אימות תוכן חדש של כל החבילות. במחקר לא חושבו hashes חדשים לבינאריים הגדולים ולא אומתו installation או rollback בקונסולה. תיקייה בעלת eboot אינה מוכיחה שכל קלטי השחזור זמינים; גודל זהה אינו הוכחת hash זהה. רשימת הנתיבים המלאה, source snapshots וה־baseline fields המסוננים נמצאים במפה. ([מלאי החבילות](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/ready_artifacts.md), [המפה](BUILD_DEPENDENCY_MAP.json).)

**החסם הקטן והחשוב ביותר הוא תיקון ה־JSON.** היומן המקומי רושם שהגרסה המותקנת מוסיפה ל־main-1.1.0 wrapper ו־`--wrap=localeconv`/`--wrap=strtod`. הוא מפנה ל־`Pokemon-ZA-Native-Port-ui-new-run-stack-20261031-223729/port/ui-v2/src/json_number_ps5.c`, קובץ **בן 1,487 בתים** שלא נוהל ב־commit לפי ההוראה הקודמת. SHA חדש לקובץ הקטן תואם ל־pin: `c380a65fcf0dc271ba5f1d09d9fab4ac3045c5a18daa09bb2ae98e9324f32a96`. נדרשים גם מתכוני candidate/install ב־worktrees אחרים. צריך לשלב את התיקון במקור ובמתכון הנוכחיים ולייצר descriptor עצמאי; אין צורך להפוך את כל ה־worktree הישן לתלות קבועה. עם זאת, **לא הוכח שזהו הקובץ היחיד שכל צרכני אותו עץ דורשים**. ([המקור](<C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port-ui-new-run-stack-20261031-223729/port/ui-v2/src/json_number_ps5.c>), [baseline/חתימה שנמדדה](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/ready_artifacts.json), [ניתוב המתכונים](../../workbench/zw.py), שורות 61–64.)

## שבע הגירות סוגרות את התלויות לפני פינוי

הטבלה היא **תוכנית קבלה ותיעדוף**, ולא תסריט שבוצע או מנגנון שחוסם כיום את הכלים. כל מפתח M תואם ל־`critical_migration_items` במפת JSON. המצב `BLOCKED` עוצר התקדמות במסלול הרלוונטי עד לפתרון מאומת; הוא אינו הוראה לשנות רשומה שכבר נרשמה בתור או לסיים תהליך של סוכן אחר.

| מזהה וצרכן | תלות שנמצאה | יעד נוכחי מסודר ותנאי קבלה |
|---|---|---|
| M01 — story review/probe | `evidence/story-continuation-20261101-r3/all24-model/summary.json` | summary תואם למודל/schema הנוכחיים; שינוי callers מבודד והשוואת review/oracle/probe; אין החלשת assertions |
| M02 — Lua/story preparation | `story-rando/tools/luadump`, Lua manifest ו־`--base-mods` | parser מאושר עם מקור וגרסה, regression על התרחישים הנוכחיים ו־base-mod manifest מפורש לכל invocation |
| M03 — prepared models suite | `common/python-compiled-r1/r2/r4`, `compiled-r1`, grouped inputs | מקור הכלים הנוכחי, Python/.NET/PKHeX מקובעים ו־regression equivalence; stage ומניפסט חדשים ושלמים לפני הרשמה חדשה |
| M04 — model conversion recipes | NAS pilot donor/PKHeX, schemas ו־candidate directories | קטלוג קלטים נוכחי מאושר עם גרסאות/חתימות ו־resolver מפורש; נבדקת התאמה סמנטית ולא רק קיום path |
| M05 — registered main JSON fix | wrapper לא־מנוהל + candidate/install recipes חוצי־worktrees | תיקון משולב במקור הנוכחי, descriptor חדש, שחזור main control ושימור fix/flags; ה־baseline המדויק נשמר כ־rollback עד אימות החלופה |
| M06 — historical reproduction | שלוש glslang/SPIRV libraries ב־`shader-prewarm-research` לכל אחד מפרופילי r27b/r28/r28a/r28b | historical bundle סגור או ספריות חלופיות מאושרות; אימות זהות/התנהגות לפי מטרת השחזור ו־restore עצמאי |
| M07 — PC relink ותיק | `ui-v2-work/pc/aot-obj`, `dll/objects.rsp`, `pc-build-05/obj`, import library | חבילת EXE/import-library/DLL objects תואמת עם build ID/ABI/שם EXE/flags/pins; אינה מניחה שזהו המסלול הפעיל של המודלים/הסיפור |

M01–M05 הם העדיפות להסדרת הבסיס הנוכחי. M06 מותנה בהחלטה לשמר יכולת reproduction היסטורית, ו־M07 הוא שער לפני שימוש מחדש במתכון הוותיק. אין צורך להעביר את כל הפרויקטים הישנים לבסיס הבנייה החדש. צריך לנתק את החלקים החיים מהם, ולארוז את ההיסטוריה עם הסגירה שלה. ([קשרי הסיפור והמודלים](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/active_projects.json), [קשרי WSL](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/wsl_inventory.json), [קשרי חבילות ושחזור](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/ready_artifacts.json).)

הפיילוט הראשון המוצע הוא **סגירת חבילת השחזור של תיקון ה־JSON**, משום שהקלט הקטן מזוהה בחתימה והבסיס כבר frozen. אחריו יש להסדיר את summary/parser של הסיפור ואת חבילת כלי המודלים. לכל מסלול מכינים מקור וקלטים נוכחיים, מפיקים descriptor חדש, מאמתים control והתנהגות בתהליך מבודד, ורק אז מכינים בדיקה חדשה. אין לקמפל או להוריד חסרים תוך החזקת תור PC/console; בדיקות רלוונטיות יגיעו לתור רק מוכנות. לא משנים locks, לא repin של job קיים ולא promotion של main ללא התהליך המאושר. ([כללי main](../../workbench/cards/main.md), [מוכנות ותורים](../../workbench/cards/resource-queues.md).)

## מאגר הרשת יוכל להחליף עצים ישנים אחרי אימות סגירה

**הצעה:** לאחר סגירת ההגירות, catalog ברשת ישמור חבילות immutable של קלטים נוכחיים, תוצרי קונסולה, recipes וראיות, עם מפרט compiler/SDK/target ו־SHA מלא. materialization מקומי יביא רק את הקלטים החסרים למטמון, וייצר תיקיית job נפרדת. הגדרת הגרסה תהיה לוגית ולא נתיב ל־worktree ניסיוני. SDK ו־frozen release תקינים יישמרו כקלטים משותפים מקובעים; תיקיות candidate ו־evidence ישנות לא יהיו ברירת מחדל לפיתוח פעיל. כיום זהו תכנון בלבד — לא הוטמע store, resolver, eviction או TTL.

קיום של שלוש תיקיות NAS מדויקות אומת במטא־נתונים: מקור AOT PC, ראיות main-1.1.0 וראיות JSON fix. **תוכנן לא אומת, ולא הועבר תוכן משחק במחקר.** README PC מתעד העתקה היסטורית של 1,412 objects למטמון מקומי; ה־relink עדיין דורש קבצים מקומיים ורשימת response מלאה. מנגנון pull חלקי אינו הוכחה שחבילת שחזור עצמאית כבר קיימת. אין להעלות game-derived content לשירות חיצוני, ו־LAN אינו פטור אוטומטי ממגבלות ההעברה. ([relink-game-dll.sh](../../port/ui-v2/pc/relink-game-dll.sh), שורות 27–29,42–60,79–95; [README PC](../../port/ui-v2/pc/README-pc-build.md), שורות 132–146; [כללי הפרויקט](../../AGENTS.md).)

לפני הגדרת local eviction נדרשים סגירת כל הקלטים של החבילה, אימות תוכן מלא ולא מדגם בלבד, בדיקת restore במסלול שאינו קורא את העצים הישנים, ושימור baseline ו־rollback. עצי r27/r28 ו־Hebrew/UI/save candidates היסטוריים הם **מועמדים לבחינת ארכוב קר**, לאחר בירור consumers דינמיים ו־untracked inputs; אינם רשימת העברה או מחיקה מאושרת. המקור הקודם נשמר זמנית כדי לאפשר חזרה בטוחה, ומעמדו נבחן שוב עם סיום ההגירה. אין צורך לשמרו לנצח רק כי מתכון עדיין מפנה אליו.

## המפה תחומה ומאומתת כמסמך, לא כהוכחת פינוי

מיפוי WSL מונה **128 תיקיות ו־13 קבצים עליונים**, 47 מסמכי build קטנים, 162 רשומות artifact ו־312 יעדי symlink ללא traversal. נבדקה קיימות של **824 נתיבי profile ייחודיים ללא חסרים**, אך לא תוכנם או כל ה־SDK. סריקת החבילות הוגבלה לעומק 3 והחריגה descent לתוכן game/mods/saves/assets. מספר התיקיות הלא־מסווגות השתנה במהלך העבודה, ולכן זהו אוסף תצפיות עם זמן וחתימת מקור, לא snapshot אטומי של סביבה קפואה. ([פרטי WSL](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/wsl_inventory.md), [פרטי חבילות](../../../../research_notes/מיפוי%20תלויות%20ותוצרי%20בנייה/ready_artifacts.md).)

ב־`BUILD_DEPENDENCY_MAP.json` ה־IDs מבודדים לפי מקור (`active::`, `wsl::`, `ready::`), כדי ששני profiles או nodes בעלי שם דומה לא יתאחדו בטעות. נשמרים ID מקורי, סוג קשר וראיות. `consumes_for_link` ו־shared dependencies שונים מ־`historical_provenance`, reference לאימות או `produces_recorded_output`. המפה אינה מאחדת אוטומטית את כל הקשרים ל־retention closure; כינוי path אינו הוכחת זהות תוכן. נבדקו פענוח JSON, IDs ייחודיים, endpoints קיימים והימצאות שבע פעולות ההגירה. **1133 nodes אינם 1133 קבצים פיזיים ייחודיים.** ([המפה](BUILD_DEPENDENCY_MAP.json).)

לא נאספו allocated/reclaimable bytes, extents, file handles פתוחים או bandwidth. שיתוף reflink/hardlink, symlinks ותמונת WSL VHDX מונעים תרגום אוטומטי של סכום גדלי קבצים לכמות מקום שתתפנה ב־Windows. לא בוצע ניסוי restore, build חדש, בדיקת משחק או אימות קונסולה. אין פה מספר GB מובטח, רשימת מחיקה או כלי אכיפה פעיל. החתימות החדשות במפה של קובצי המחקר הקטנים מזהות את התצפיות; החתימות ההיסטוריות של binaries נשארות מסומנות ככאלה. ([מגבלות וסוגי ראיות](BUILD_DEPENDENCY_MAP.json), [שימוש reflink ב־freeze_release.py](../../tools/za/freeze_release.py), שורה 75.)

תוצרי המחקר הם הדוח הזה, מפת JSON ועותק דוח זהה בתיקיית reports, לצד כרטיס `build-storage` קצר. helpers חד־פעמיים ונתוני המקור נשארים ב־research_notes מחוץ לקוד הייצור. לא שונו `AGENTS.md`, סקריפטי build, locks, תורים או תוצרי משחק, ולא בוצע commit. ההמשך המסודר הוא לסגור את חסמי ההגירה עם קלטים נוכחיים מאושרים, להוכיח שהמסלול החדש עצמאי, ורק אז להחליט על אחסון קר ופינוי מקומי.


## עדכון תחזוקה — 2026-11-01T06:43:51.858825+00:00

המספרים והמסקנות בגוף הדוח לעיל מתארים את תמונת המחקר המקורית מ־1 בנובמבר 2026; הם לא שוכתבו בדיעבד. למפת JSON נוספו כעת שלושה רכיבי תחזוקה משולבים: `tools/za/za.py`, העזר `tools/za/build_cleanup.py` ובדיקות `tools/za/test_build_cleanup.py`. נמדדו SHA-256 של הקבצים בפועל במקור הקנוני, והם תואמים לגרסאות שנבדקו בשילוב. המפה מונה כעת **1136 nodes ו־1432 edges**: שלושה nodes ושלושה קשרים חדשים — import של העזר, בדיקת בטיחות filesystem ובדיקת שערי cleanup בבקר. כל ה־nodes והקשרים ההיסטוריים נשמרו ללא שינוי. ([המפה](BUILD_DEPENDENCY_MAP.json), [delta מתועד](../../../../research_notes/מועמדי%20ניקוי%20וגודל%20אחסון/cleanup_mapping_delta.json).)

**אימות שבוצע ותועד בשלב השילוב:** ב־Windows הורצו 36 בדיקות סינתטיות — 34 עברו ושתיים דולגו בגלל הרשאת symlink חסרה; ב־WSL עברו כל 36 הבדיקות. החתימות ותוצאות הריצה נבדקו מתוך הלוגים הקנוניים הקיימים. עדכון המיפוי עצמו לא הריץ בדיקות נוספות. לא בוצעו build אמיתי של המשחק, בדיקת משחק או בדיקת קונסולה לצורך אימות רכיב זה. ([תיעוד השילוב](../../../../research_notes/מועמדי%20ניקוי%20וגודל%20אחסון/cleanup_implementation.json), [Windows](../../../../research_notes/מועמדי%20ניקוי%20וגודל%20אחסון/cleanup-tests-canonical-windows.log), [WSL](../../../../research_notes/מועמדי%20ניקוי%20וגודל%20אחסון/cleanup-tests-canonical-wsl.log).)

הרכיב החדש הוא קלט תחזוקה עדכני שיש לכלול בסקירת inputs לפני בנייה עתידית. מיפויו ואימות הבדיקות הסינתטיות **אינם אישור להתחיל build**, אינם סוגרים את חסמי ההגירה הקודמים ואינם משנים locks, baseline או תורי הבדיקה. הניקוי המשולב מוגבל למסלולים שתועדו בתיעוד השילוב; אין כאן טענת כיסוי לכל builders ההיסטוריים. ([תיעוד השילוב](../../../../research_notes/מועמדי%20ניקוי%20וגודל%20אחסון/cleanup_implementation.json), [חוזה inputs הנוכחי](../../workbench/cards/build-inputs.md).)

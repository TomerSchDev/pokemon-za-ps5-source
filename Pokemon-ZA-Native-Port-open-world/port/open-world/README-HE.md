# open-world — "עולם: פתוח מההתחלה" (31.10.2026)

ענף `open-world` (מבוסס על `story-rando`). אין כאן נתוני משחק, טקסט משחק או שמירות. הדוח: `workbench/reports/open-world/index.html`.

## מה זה עושה
מוריד ספי התקדמות (`phase_condition` עם האופרטור `>=`) של תוכן העולם לשלב מוקדם. כל כתיבה היא החלפה במקום של מספר בן 5 ספרות
(אותו אורך), בלי קידוד מחדש ובלי שינוי גודל. 4 קבצים בלבד נכתבים:

| קטגוריה | קובץ | כמה | ספ חדש |
|---|---|---|---|
| חנויות (חנות רגילה, אבנים, חנות מגה) | `world/exl/shop/shop_item_lineup` | 38 שורות | 10000 (מיד אחרי הפתיחה) |
| מוניות (22 נהגים, 29 תנאים) | `trigger/map/trigger_map_t2` | 29 | 21110 (סוף הדרכת המפה/נסיעה מהירה, פרק 2) |
| אירועי מרכז פוקימון, אימון, חנות Mega Shards, נקודות בסיס, מתנות NPC | `trigger_map_t2` | 18 | 21110 |
| משימות צד עד פרק 8 | `quest/sub_quest` | 102 | 21110 |
| משימות המחקר של Mable | `quest/momiji_quest` | 4 | 21600 (כש-Mable נפתחת) |

הספים נגזרים מ-`phase.bin` (השלב שאחרי הפעולה שמדליקה `flag_FastTravel_Enable` / `FLAG_MOMIJI_ENABLE`), לא מקודדים.

## מה לא נוגעים (מוגן, והאורקל בודק)
`phase.bin`, ‏`main_quest`, ‏`trigger_main_00…10` (כולל stoppers), טריגרי קרבות (בוס/מאמן/פרא), נקודות חזרה, שיחות NPC,
תפריטים, `trigger_global`, ‏`door_jump`, ‏`destination_data`. משימות צד שהסיפור קורא או כותב (`sub_001`–`003`, ‏`sub_118`, ‏`sub_140`)
נשארות סגורות. תוכן פרק 9 ואחרי הסיום (סף ≥ 90000) נשאר סגור.

## כלים
```
py -3 -X utf8 port/open-world/open_world.py inventory [--json F]      # כל 2,220 התנאים ב-26 טבלאות, מסווגים
py -3 -X utf8 port/open-world/open_world.py build OUTMOD [--tier open|open-postgame] [--glide-early] [--base-mod DIR ...]
py -3 -X utf8 port/open-world/open_world.py verify OUTMOD                # אורקל עצמאי, exit 1 על כל ממצא
py -3 -X utf8 port/open-world/test_open_world.py                         # 10 בדיקות (צריך את עותק המשחק המקומי)
```
`OUTMOD` חייב להיות מחוץ ל-git. הפלט: `OUTMOD/romfs/<path>`, ‏`open-world-log.json` (כל תנאי ששונה: קובץ, קטגוריה, מפתח, ישן→חדש, offset),
`save-ops.json` (דגלי שמירה אופציונליים).

## סדר מול אפשרויות סיפור אחרות
open-world רץ **אחרון** (`--base-mod` של ה-shuffle / skip-intro). הוא מסווג שערים לפי מה שהם (נהג מונית, שורת חנות, מזהה משימה), לא לפי
המספר, והספים שלו בפרקים 1–2 שאף shuffle לא מזיז. בדיקה: open-world ו-`chapter_swap` מתחלפים בית-בבית, ו-build על גבי mod החלפה אמיתי עובר את האורקל.

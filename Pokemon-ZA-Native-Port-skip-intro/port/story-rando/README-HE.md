# story-rando — מחקר: ערבוב סדר הסיפור (31.10.2026)

ענף `story-rando`. מחקר בלבד: אין כאן נתוני משחק, טקסט משחק או שמירות. הדוח המלא: `workbench/reports/story-rando/index.html`.

## כלים (`tools/`)
| קובץ | מה עושה |
|---|---|
| `story_extract.py OUT` | מחלץ (קריאה בלבד) את טבלאות `ik_event` ואת סקריפטי ה-Lua לתיקייה **מחוץ ל-git**, ומפענח אותן ל-JSON בלי סכמה |
| `fbdump.py` | מפענח FlatBuffers היוריסטי (אין `.bfbs` לטבלאות `ik_event`) |
| `luadump.py` | קורא bytecode של Lua 5.4 (סקריפטי האירועים, קומפילציית Haxe; שמות ה-API מגובבים `S<16 hex>`) |
| `phase_summary.py`, `quest_summary.py`, `chapter_graph.py` | טבלת ה-phase, משימות הסיפור, גרף פרקים |
| `trig_stats.py`, `cond_inventory.py`, `maptr.py` | טריגרים לפי פרק, מלאי כל ה-`*_condition` |
| `lua_ph.py`, `lua_deps.py` | קבועי phase ודגלים חוצי-פרקים בסקריפטי ה-Lua |
| `phase_consts.py` | סורק את `.text` של `main` (MOVZ/MOVK) לקבועי phase |
| `za-story-save/` | C# + PKHeX.Core: `dump` / `set` של דגלים, system work, quest work — רק על **עותק** של שמירה, פלט לתיקייה חדשה |

## ממצאים בשורה אחת
- ה-phase (`SYS_WORK_PHASE`) הוא מכונת מצבים ליניארית בנתונים (`ik_event/bin/phase/phase.bin`, 191 רשומות): כל רשומה = מזהה + תנאי יציאה (דגל `flag_Ev_mXX_YYYY`) + פעולות מעבר (דגלים/work/דרגת Royale/שעון/מזג אוויר).
- טריגרי הסיפור (`trigger_main_NN.bin`) תלויים כמעט רק ב-phase של הפרק שלהם (`phase == X`), והקוד המקורי לא מקודד קבועי phase של הסיפור הראשי (רק "רעש"). 22 פונקציות Lua בודקות phase.
- ניסויי PC (‏`hebrew-lab/runs/story-rando-*`): המשחק סומך על `SYS_WORK_PHASE` שבשמירה, ולא מחשב אותו מחדש מדגלים בטעינה. ה-phase מתקדם רק כשאירוע מדליק דגל. "השלמה" שחושבה מ-`phase.bin` (`catchup.py 40100`) מכניסה את המשחק נקי לתחילת פרק 4; רק דרגת ה-Royale לא מכוסה.
- PKHeX 9ZA: `SetValue(key, value)` לא כותב את הערך, ולכן `za-story-save` כותב לפי אינדקס.
- **החלפת פרקים הוכחה על PC**: `chapter_swap.py` (פרק 6 לפני פרק 5) + `boundary_helpers.py` + `catchup.py 42030`. אחרי האירוע האחרון של פרק 4, ה-phase עבר 42030→51000 (פרק 6), ‏`main_06_01` נפתחה ופרק 5 נשאר סגור (ריצות `story-rando-swap56-*`).
- פרקים 4–8 כבר מכילים "מרכזים" של 3–4 משימות בכל סדר (40800, 50200, 62000, 74000, 83200).

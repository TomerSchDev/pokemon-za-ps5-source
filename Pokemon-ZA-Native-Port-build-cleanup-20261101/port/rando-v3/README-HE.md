# rando-v3 — הגנרטור של הרנדומייזר עם רמות הרנדומיזציה של UI v2 (31.10.2026)

תיקייה חדשה. `port/randomizer` ו-`port/rando-v2` **לא נערכו**; `core/` כאן הוא עותק בייט-בבייט של `port/randomizer/core`
(‏SHA-256 ב-`provenance.json`), והקוד החדש יושב ב-`src/`. אין בתיקייה הזאת נתוני משחק: כל הנכסים נבנים מחוץ ל-git
(ראו "נכסים" למטה).

## 1. `capabilities.json` — החוזה עם סוכן ה-UI

הקובץ שסוכן ה-UI קורא **בזמן הבנייה**. לכל `id` של שורה ב-`port/ui-v2/src/ui_model.cpp` יש רשומה:

| שדה | משמעות |
|---|---|
| `kind` | `level` / `toggle` / `number` / `pick` / `text` — כמו `Kind` ב-`ui_model.h` |
| `default` | מזהה האפשרות (או המספר) שהגנרטור מניח כשהערך חסר ב-`ui_options` |
| `supported` | מזהי האפשרויות שהגנרטור **כותב היום**. כל מזהה אחר של אותה שורה → `NOT IN THIS BUILD` ב-UI, והגנרטור **מסרב** לריצה שמבקשת אותו (שגיאה ברורה, לא התעלמות) |
| `unsupported` | המזהים שעדיין לא נתמכים (מידע; המשלים של `supported`) |
| `supported_range` | ל-`number`: הטווח שהגנרטור מקבל |
| `supported_species` | ל-`starter_pick`: רשימות המינים לפי `starter_mode` |
| `owner` | כשהאפשרות מבוצעת על ידי מודול אחר שרץ אחרי הגנרטור (שם המאמן — rando-v2; מוזיקה — r29-music) |
| `notes` | מה האפשרות עושה בפועל, ומגבלות |

`proposed_options` — אפשרויות שהגנרטור יודע לממש אבל **אין להן עדיין שורה** ב-`ui_model.cpp` (למשל `base_stats`,
`catch_rate`). סוכן ה-UI מוזמן להוסיף להן שורה עם המזהים המוצעים; עד אז הגנרטור מתייחס אליהן כ-`vanilla`.

`run_tables` — אילו קבצים ריצה מייצרת (`native_tables` ב-`report.json`) ואילו קבצים נוספים מתוכננים
(`native_extra_tables`, באותו מנגנון כמו `native_music` של r29 כדי שבינארים ישנים ימשיכו להציג את הריצה).

הקובץ מתעדכן בכל פעם שרמה חדשה נתמכת; השדה `updated` הוא חותמת הזמן של העדכון האחרון.

## 2. `ui_options` ב-`report.json`

הסכמה (מ-`ui_model.cpp`, `toJson`):

```json
"ui_options": {"schema": 2, "values": {"wild_mode": "random", "trainer_levels": "plus20", "starter_mode": "any", "starter_pick": 650, "player_name": "Tomer"}}
```

- רמות/מתגים לפי **id יציב** של האפשרות (לא אינדקס); מספרים כמספרים; `starter_pick` = מספר מין (או `null` כש-`starter_mode = random`).
- מפתח שחסר → ברירת המחדל מ-`capabilities.json`. מפתח לא מוכר → נשמר בדוח ומוותר (לא שגיאה).
- `options` הישן (`wild`/`trainers`/`mega_trainers`/`dlc_rematches`/`research_rewards` בוליאניים) **נשאר** בדוח לתאימות:
  `wild = (wild_mode != off)`, `trainers = (trainers_mode != off)`.
- דוח ללא `ui_options` (ריצות r6–r29) נקרא כמו היום; הגנרטור מקבל גם `Options` ישן וממפה אותו ל-`ui_options`.

## 3. מצב (31.10, בוקר)

נתמך היום (= הגנרטור של r15 + rando-v2 + r29): `wild_mode` off/random, `trainers_mode` off/random, `mega_trainers`,
`dlc_rematches`, `starter_mode` vanilla/any/random (+`starter_pick`), `research_rewards`, `music` (r29), `player_name` (rando-v2).
כל שאר הרמות — בעבודה, לפי הסדר שבמשימה: רמות בר (zones / in_zone / chaos) → מאמנים (swap / strength) → התחלתי →
Alpha → רמות בר → רמות מאמנים → צורות → חפצי/מהלכי מאמנים → סטטים/לכידה → דרישות מחקר.

## 4. נכסים (מחוץ ל-git)

- קלט: `\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\Research\pokeza-pc\ingame-randomizer\prepared-streamed`
  (‏88 קבצים, אותו סט שנארז ב-`/app0/randomizer-assets` — `tables.json` ‏SHA-256 `a8491458…9b1e`), `port/randomizer/reward-assets`,
  סכמות ה-`.bfbs` וטבלאות הגלם ב-`evidence/randomizer-field-move-audit/extracted` וב-`.claude/tmp/rando-options-research/romfs2`.
- עותק עבודה: `PS5-13.60\rando-v3-lab\inputs\prepared-streamed` (מחוץ לריפו). הפלט של `tools/prepare-v3-assets.py` →
  `PS5-13.60\rando-v3-lab\assets` (ראו `HANDOFF.json` כשיהיה).

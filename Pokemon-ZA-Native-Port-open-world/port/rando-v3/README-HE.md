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

## 3. אבן דרך 1 — רמות בר ו-Alpha (31.10.2026)

`HANDOFF.json` הוא שער המסירה ל-UI: יש לצרוך אותו רק כאשר `ready_for_ui` הוא `true`, ולאמת את
`capabilities_sha256`, מניפסט הנכסים ואת `v3_sha256`. מצב הבדיקות וההגבלות מפורטים שם.

נוסף לבסיס r15 + rando-v2 + r29, אבן הדרך משחררת:

- `wild_levels`: ‏`vanilla`, ‏`plus10`, ‏`plus25`, ‏`range`, ‏`mixed`.
  האחוזים חלים על מינימום ומקסימום, בעיגול חצי כלפי מעלה ותקרה 100; `range` מגריל כל קצה בטווח ±5,
  מסדר את הקצוות ומגביל ל-1–100; `mixed` מעביר טווחים בין אזורים מאותה מחלקה, לפי סדר הרמות במשבצות.
- `alpha_rate`: ‏`vanilla`, ‏`x2`, ‏`x5`, ‏`always`. המכפילים מוגבלים ל-100; ‏`always` קובע 100 רק
  לשורות שבהן הסיכוי המקורי גדול מ-0. שורות 0 נשארות 0, ו-140 שורות Alpha קבועות נשארות 100.
  זו המשמעות המאושרת ב-UI, "Every slot that can be an Alpha"; היא מצמצמת את הצעת המחקר להפעיל Alpha בכל שורה.
- שני ספקי ה-Rock המוקדמים (`ect_a0102_w01_v01_z659_tuto`, ‏`ect_a0102_w01_v01_z659`) שומרים את
  רמותיהם ואת סיכויי ה-Alpha המקוריים. זה כולל את שורת ה-tutorial שצוינה במחקר. שורות boss אינן משתנות.
  תוספות הרמה של ה-spawner ושל Alpha נשארות מקוריות, ולכן 1–100 הוא הטווח בטבלת המפגש, לא הבטחה לרמה הסופית במשחק.

רמות ו-Alpha פועלים גם כשהחלפת המינים היא `wild_mode=off`. ברירות המחדל נשארות בייט-בבייט כצינור הישן.
שאר הרמות ב-`unsupported` חסומות ב-`settingsFromUi`, כולל רמות מאמנים, צורות וסטטים. למטרות מחקר בלבד,
`generateRun` עם `Settings` ישיר עדיין מאפשר את האלגוריתמים הניסיוניים; ה-UI חייב לקרוא קודם ל-`settingsFromUi`.
מצב Chaos הניסיוני משחרר את הגנות ה-Rock ואינו נגיש ב-UI של אבן הדרך.

API: ‏`za::v3::Assets{tables, starters, progression, rewards, v3}` → ‏`settingsFromUi(ui_options, settings, error)`
→ ‏`generateRun(assets, reader, seed, settings, ui_options, result, progress)`. יש לקשר את קובצי `core/`,
שלושת קובצי הגנרטור ב-`src/`, ובצד האחסון את `src/run_store_v3.cpp` במקום ה-run-store הישן.
יש להטמיע את ה-pins מ-`assets_hashes_v3.h`, ובמיוחד את `ZA_V3_SHA256`, ולשלוח את כל קובצי מניפסט הנכסים.

`tools/fb_codec.py` משחזר **פענוח ומיפוי offsets של שדות scalar בלבד**. ה-encoder שמוסיף sub-tables,
וקטורים או מחרוזות לא שוחזר. זה מספיק כאן מפני שכל השדות כבר קיימים ב-template המאומת.

בדיקות: `tools/build-host.sh ASSETS OUT SEEDS` בונה ורץ עם ASan/UBSan כברירת מחדל;
`RANDO_V3_SAN=0` מפעיל בנייה רגילה בתיקיית אובייקטים נפרדת. הוא מעביר לבדיקות גם את `capabilities.json`;
הבדיקות משוות את ה-release gate לחוזה, בודקות את כל צירופי רמות הבר/Alpha עם החלפת מינים כבויה ופעילה,
ומשוות את הבייטים שמחוץ לשדות המותרים. ‏`tools/oracle_v3.py --assets ASSETS --reports OUT/reports.json`
משחזר את הטבלאות עצמאית ב-Python. ‏`tools/build-ps5-check.sh` הוא compile-check בלבד; הוא אינו הוכחת חומרה.

מצבי בדיקה ממוקדים: `RANDO_V3_CONTRACT_ONLY=1` בונה ובודק רק את חוזה ה-JSON, לרבות כל 25 צירופי
ברירות המחדל של Shiny/Capture שבבעלות הלאנצ'ר; `RANDO_V3_MILESTONE_ONLY=1` מדלג על סריקת הרמות
הניסיוניות ומשאיר את מטריצת 40 צירופי המיילסטון ואת בדיקות השלילה. `RANDO_V3_SKIP_EQUIVALENCE=1`
מיועד לחזרה על המקטעים האחרים כאשר רגרסיית הבסיס כבר תועדה בנפרד; הפלט מציין במפורש שהיא דולגה.
ברירות המחדל של Shiny/Capture עוברות דרך parser הגנרטור ללא שינוי Settings; הלאנצ'ר כותב אותן ל-`cheats.txt`.

## 4. נכסים (מחוץ ל-git)

- קלט: `\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\Research\pokeza-pc\ingame-randomizer\prepared-streamed`
  (‏88 קבצים, אותו סט שנארז ב-`/app0/randomizer-assets` — `tables.json` ‏SHA-256 `a8491458…9b1e`), `port/randomizer/reward-assets`,
  סכמות ה-`.bfbs` וטבלאות הגלם ב-`evidence/randomizer-field-move-audit/extracted` וב-`.claude/tmp/rando-options-research/romfs2`.
- עותק עבודה: `PS5-13.60\rando-v3-lab\inputs\prepared-streamed` (מחוץ לריפו). הפלט של `tools/prepare-v3-assets.py` →
  `PS5-13.60\rando-v3-lab\assets` (ראו `HANDOFF.json` כשיהיה).

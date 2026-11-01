# main וענפי פרויקט: הצעה לגרסה 1.0.0 (31.10.2026)

**מצב: הצעה, ממתינה לאישור של Tomer.** שום דבר לא הותקן ושום דבר לא נכתב ל־git.
כרטיס קצר לסוכנים: `workbench/cards/main.md`.

## בקצרה
- **1.0.0 = r29-ui**: ממשק 9 המסכים החדש וגנרטור rando-v3 (שלב 1), על בסיס r28b DLC Dex + MUSIC.
  - eboot `51b7e65b…`, PIE `bf206bf4…`. החבילה: `artifacts/randomizer-r29-ui-codex-20261031-01`.
- **אזהרה: r29-ui לא נבדקה בקונסולה אף פעם.** בדיקה לקריאה בלבד (31.10) לא מצאה eboot בגודל 402,693,938 בתים באף כותר.
  - שרשרת ההתקנות של היום בקונסולה: 8e4280f0 → 4b4d1b50 → 41e7d81e → 2883b727 → 2726483b (עברית, מותקנת כעת).
- **השחזור עבר.** `za build main` מקשר את 1.0.0 מחדש מקלטים קפואים, והתוצאה זהה בית־בבית ל־PIE ול־eboot שנמסרו. גם 200 קובצי החבילה עברו בדיקה.

## 1. מלאי פיצ'רים

עמודות "נמצא ב־": ‏M = r28b+MUSIC ‏(8e4280f0, נבדקה בקונסולה) · I = העברית המותקנת (2726483b) · U = r29-ui = 1.0.0.

| פיצ'ר | מקור | M | I | U | בקונסולה | סוג |
|---|---|---|---|---|---|---|
| ליבת runtime (NVN→Vulkan, framepace, LayeredFS) | עץ WSL `…/source/runtime`. ענף `ps5` ב־git **מפגר אחריו** | ✓ | ✓ | ✓ | כן | eboot |
| texfix (קריסת טקסטורות) | `port/runtime-texfix` | ✓ | ✓ | ✓ | כן, דרך M ו־I | eboot |
| **תיקון overlay-fd** (קריסה בסביבת 1024 קובצי mod) | patch ב־`r28b-dlc-dex-fd-20261031-r1`. נכנס עכשיו ל־runtime בענף `fix/overlay-fd-limit` | ✗ | ✓ | ✗ | עקיף: I עולה עם 564 קבצים | eboot |
| רנדומייזר ליבה (בר, מאמנים, מגה, DLC) ו־progression | `port/randomizer` | ✓ | ✓ | v3 | כן (M) | eboot + randomizer-assets |
| rando-v3: רמות בר, Alpha, מילות הגדרה | `port/rando-v3` | ✗ | ✗ | ✓ | **לא** | eboot + randomizer-assets (174 קבצים) |
| ממשק UI v2 (9 עמודים, launcher, overlay חדש) | `port/ui-v2` | ✗ | ✗ | ✓ | **לא** | eboot |
| launcher/תפריט ישן | `port/randomizer`, `port/rando-music` | ✓ | ✓ | מוחלף | כן | eboot |
| ספירת Pokédex כולל DLC | `port/rando-dexcount` (+ hooks בארכיון) | ✓ | ✓ | ✓ | לא אומת במשחק | eboot |
| פתיחת DLC Dex מוקדמת | `port/dlc-dex-unlock` | ✓ | ✓ | ✓ | לא אומת | eboot |
| ערבוב מוזיקה (OFF כברירת מחדל) | `port/rando-music` (התוכנית מוטמעת ב־eboot) | ✓ | ✓ | ✓ | חלקית | eboot |
| צ'יטים L3+R3: SHINY/CAPTURE/MONEY/ITEMS/FPS | `port/perf-r28` (`cheats-r28`). ב־U: `port/ui-v2/src/overlay_ps5.cpp` | ✓ | ✓ | ✓ | התפריט כן. ההשפעה בפועל (MONEY/ITEMS/SHINY) לא אומתה | eboot |
| NAME (שם מאמן) | `port/rando-v2` | ✓ | ✓ | ✓ | לא | eboot |
| ביצועים r16/r24 (`optimized`, ‏`perf-r24-options.txt`) | `port/performance-r16`, `port/perf-r24*` | ✓ | ✓ | ✓ | כן | eboot + config ב־app0 |
| r25 clock, ‏r26 dyn timing, ‏za_prof | `port/perf-r25/26`, `perf-r24prof` | ✓ | ✓ | ✓ | כבויים בקונפיג | eboot |
| observer (פרוטוקול 17) | `port/observer-r17` | ✓ | ✓ | ✓ | כן | eboot |
| shader cache ו־glslang | `port/shaderc-cache` | ✓ | ✓ | ✓ | כן | eboot + cache |
| Hebrew Trial (טקסט בסדר ויזואלי, שורה ב־L3+R3) | `hebrew-lab/trial`, `port/perf-r28/src/hebrew_*` | ✓ | ✓ | אובייקט קיים, השורה הוסרה | כן | eboot + app0 |
| **עברית RTL** (FriBidi) | `port/hebrew-rtl` | ✗ | ✓ | ✗ | כן | eboot |
| **mods/hebrew** (564 קבצים, גופן Assistant) | `artifacts/randomizer-r29-hebrew-rtl-20261031-r4` | ✗ | ✓ | ✗ | כן | mods + payload |
| שמות עבריים למינים חדשים | `/home/tomer/ps5-za-native/hebrew-species-pretranslation-20261031-r1/delivery` | ✗ | ✗ | ✗ | לא | mods |
| מודלים ומינים חדשים (QA) | eboot ‏41e7d81e ומודים `00-*console-fifty*` | ✗ | ✗ | ✗ | בבדיקה | eboot + mods (~24,500) |

**Config של main:**
- `/app0/performance-options.txt` = `optimized`.
- `/app0/perf-r24-options.txt` = `scale=1 ticks=tsc vkprof=0 submit=thread fps=1`.
- `/app0/randomizer-assets/`: גרסת v3 מלאה. נכסים ישנים נדחים.

## 2. מה זה main בפועל
main איננו commit אחד. זו **גרסת release** אחת, שמורכבת מארבעה חלקים שננעלים יחד:

1. **eboot**: פרופיל `tools/za/releases/<name>.lock.json`.
   - בפנים: SHA-256 של כל קלט קישור, סדר הקישור, הפניות ל־PIE ול־eboot, וה־eboot שנמסר.
   - הקלטים עצמם מועתקים לתיקייה קפואה חדשה, `/home/tomer/ps5-za-native/za-<name>-frozen-*`, שאף סוכן לא נוגע בה.
2. **נתונים**: חבילה עם `SHA256SUMS.json` מוצמד. ב־1.0.0 אלה ה־eboot ו־randomizer-assets. בהמשך יתווספו `mods/<ענף>/`.
3. **Config**: קובצי app0 שתוכנם קבוע (ראו למעלה).
4. **מקור**: ה־commit-ים של git שמהם נבנו הקלטים (הריפו הזה ו־runtime). **ל־1.0.0 זה עוד חסר** (סעיף 5).

`tools/za/releases/MAIN` מצביע על הגרסה הנוכחית. הכניסה האחת:

```
zw za build main --out /home/tomer/ps5-za-native/main-NEW [--package NEW]
```

הפקודה:
- מקשרת מחדש ומשווה בית־בבית ל־eboot המקורי.
- בודקת כל קובץ בחבילה.
- עם `--package`, מרכיבה חבילה חדשה להתקנה.

## 3. ענפי פרויקט ומיזוג
- **ענף** = נושא אחד. דוגמאות: `heb-trans`, `species-names`, `models`, `fd-fix`.
  - לכל ענף: תיקייה `port/<x>/` (מתכון, פינים, בדיקות), ענף git באותו שם (ב־worktree נפרד), ותיקיות פלט חדשות בלבד.
- **בסיס** = תמיד main. המתכון של הענף מתחיל מהתיקייה הקפואה של main ומשחזר אותה כבקרה, לפני כל שינוי.
  - לעולם לא מתחילים מ"מה שמותקן עכשיו בקונסולה". זה המקור של הרגרסיות עד היום.
- **מיזוג**: רק Tomer מאשר, וסוכן אחד ממזג בכל פעם. שלב אחרי שלב:
  1. Rebase על main הנוכחי.
  2. בקרות:
     - הבסיס משוחזר בית־בבית.
     - אובייקטים שלא השתנו נבנים מחדש זהים.
     - רשימת אובייקטים שהשתנו, עם diff של סמלים ובלי אובדן סמלים מהבסיס.
  3. בדיקות host ואז PC proof (סצנה מוגבלת על שמירה מועתקת). במודים: ספירת קבצים והתנגשויות של סדר מיון.
  4. **שער קונסולה** בתיאום עם Tomer: `zw queue`, גיבוי שמירה, `.new` ← readback ← rename. עובר אם המשחק עולה, השמירה נקראת והפיצ'ר עובד.
  5. `freeze_release.py` כותב lock חדש. אחר כך `MAIN` עובר לגרסה החדשה, `za build main` עובר, ונכתבת תיקיית evidence.
  6. מיזוג ענפי git. ה־hash-ים נרשמים בבלוק `release` של ה־lock.
- **גרסאות**:
  - PATCH (1.0.1): תיקון בלי אופציה חדשה, למשל תיקון ה־fd.
  - MINOR (1.1.0): פיצ'ר או אופציה חדשים, למשל עברית.
  - MAJOR (2.0.0): שבירה של שמירות או של מילות ההגדרות.
  - חזרה אחורה = להחזיר את `MAIN` לגרסה הקודמת. lock-ים קיימים לא נערכים לעולם.

### דוגמה ראשונה: הענף `heb-trans`
המצב היום: eboot ‏2726483b = r28b+MUSIC + תיקון fd + RTL, מתכון `port/hebrew-rtl/build-r29-hebrew.sh`, חבילת mods r4.
הוא **לא** בנוי על 1.0.0. המיזוג דורש:

1. בסיס חדש:
   - `BASE_SPEC` שמצביע על התיקייה הקפואה של main-1.0.0 (ה־PIE, 64 אובייקטי runtime ו־`extra-inputs.txt`).
   - הארכיון זהה (`18dbbadc`), ולכן הבקרה של main_992 נשארת כמו שהיא.
   - צריך לוודא שה־overlay החדש של UI v2 לא דורס את `f_700264efe4`.
2. החלטה על תיקון ה־fd (סעיף 4). עם 564 קבצים בלבד ייתכן שזה יעבוד גם בלעדיו, אבל המרווח מ־1024 קטן.
3. חבילת `mods/hebrew` נכנסת לחבילה של main כחלק נתונים מוצמד. בנוסף:
   - שער התנגשות: מודים `00-*` של ענף המודלים ממוינים לפני `hebrew` וגוברים עליו. זה מה שגרם ל־"Mudbray" ב־HUD.
   - צריך להחליט על שם או סדר קבוע, למשל `zz-hebrew`, או לאחד את קובצי הטקסט.
4. טקסטים שה־UI v2 מצייר בעצמו (באנגלית) לא עוברים דרך GFMSG, ולכן הם לא יתורגמו. זה פריט פתוח.
5. שער קונסולה, ואז גרסה **1.1.0**.

גם `species-names` (נתונים בלבד) ו־`models` (eboot + כ־24,500 קבצים, **מחייב** את תיקון ה־fd) הם ענפים נפרדים. אותו מסלול חל עליהם.

## 4. תיקון overlay-fd
- **1.0.0 לבד לא צריכה אותו.** היא לא טוענת מודים.
- **כל ענף עם מודים צריך אותו לפני שהוא נכנס:** עברית (564 קבצים), מודלים (כ־24,500), שמות מינים.
  - ההוכחה: 2883b727, שאין בה את התיקון, קרסה עם מודי המודלים.
- **ההמלצה**: להכניס אותו ל־main כגרסה **1.0.1** לפני שממזגים את `heb-trans`.
- **הדרך**:
  1. ענף ה־runtime `fix/overlay-fd-limit`. ‏commit ‏57e3b9d כולל את התיקון, ו־ae5e0bd מוסיף בדיקת host.
  2. בונים מחדש את fs.o, ‏ipc.o ו־kernel.o בתוך העץ של main.
  3. בקרה: שאר 61 האובייקטים זהים.
- **הסתייגות**: fs.o ו־ipc.o משתחזרים בית־בבית מול האובייקטים שרצו בקונסולה. kernel.c תואם רק בשורות שהשתנו, כי ענף `ps5` מפגר (סעיף 5).

## 5. מה חסר כדי לבנות 1.0.0 מקוד מקור ולא מאובייקטים קפואים
1. **runtime**:
   - ענף `ps5` ב־git (d06e23f) מפגר אחרי העצים שנבנו בפועל ב־WSL. חסרים בו שינויי Vulkan r20–r28a, ‏klock_take של r24, ‏`ps5_compat.h`, ‏texfix ו־`apply-runtime-launcher`.
   - **צעד נדרש**: ענף `main` בריפו ה־runtime, ששווה בדיוק ל־`tree/source/runtime` של r29-ui.
   - ההוכחה: בניית כל 64 האובייקטים מחדש, בית־בבית.
2. **ארכיון המשחק** (`liblasgame-base.a`, ‏18dbbadc): יחידות AOT עם תיקוני dexcount ו־DLC.
   - זה קוד שנגזר מהמשחק, ולכן **לא נכנס ל־git**. הוא נשאר קפוא ומוצמד ב־hash (ב־NAS ובתיקייה הקפואה).
3. **אובייקטים 000–041** (צ'יטים, מוזיקה, ביצועים, observer ועוד): המקורות נמצאים ב־`port/*`, אבל לא לכולם נרשם hash של מקור. צריך בקרת בנייה מחדש לכל אחד.
4. **הריפו הזה**: עשרות שינויים ב־`port/` שלא נכנסו ל־commit (‏`git status`), ואין ענף `main` (יש רק `master`).
   - **צעד נדרש**: commit של מצב המקורות שממנו נבנתה r29-ui (‏`evidence/source-hashes.json` שלה), ענף `main` ממנו, ורישום ה־hash ב־lock.
5. **toolchain**: ‏PS5_Vulkan, ה־SDK ו־clang-21 מוצמדים ב־hash ולא מנוהלים בגרסאות. זה מספיק לשחזור.

## 6. החלטות ל־Tomer (ההמלצה שלי מודגשת)
1. **1.0.0 לא נבדקה בקונסולה.** האפשרויות:
   - (א) **לבדוק את r29-ui בקונסולה ואז לתייג אותה 1.0.0.**
   - (ב) לתייג את r28b+MUSIC ‏(8e4280f0, האחרונה שנבדקה בקונסולה) כ־1.0.0, ואת r29-ui כ־1.1.0.
   - המלצה: **(א)**. הפרופיל כבר מוכן, ובמקרה כישלון חוזרים ל־(ב).
2. תיקון ה־fd: **1.0.1, לפני כל ענף עם מודים**. החלופה היא להכניס אותו כבר לבדיקת הקונסולה של 1.0.0.
3. "הרנדומיזציה שאנחנו רוצים" ב־1.0.0: ברירות המחדל של v3 (wild off/random, ‏levels vanilla…mixed, ‏alpha vanilla…always), מוזיקה OFF, צ'יטים זמינים. **להשאיר את מה שב־r29-ui ולשנות ברירות מחדל רק בגרסה הבאה.**
4. עברית כברירת מחדל: **כן, אחרי שענף `heb-trans` ימוזג (1.1.0)**, עם אפשרות לכבות אותה (שינוי שם התיקייה).
5. מי ממזג ל־main: **רק סוכן אחד, אחרי אישור שלך בכל מיזוג**. lock-ים לא נערכים לעולם.
6. git: **לאשר commit של מקורות r29-ui, יצירת `main` מ־`master`, וענף `main` בריפו ה־runtime ששווה לעץ WSL** (סעיף 5). עד שזה נעשה, main מבוסס על אובייקטים קפואים בלבד.
7. סדר מודים: **שם קבוע לעברית (`zz-hebrew`) או איחוד טקסטים** לפני שהמודלים נכנסים.

## קבצים
- `tools/za/releases/main-1.0.0.lock.json` (sha `030b5020…`)
- `tools/za/releases/MAIN`
- `tools/za/releases/main-1.0.0.release.json`
- `tools/za/freeze_release.py`
- `tools/za/za.py`: טעינת releases ו־`build main`.
- `tools/za/test_za.py`: 15 בדיקות עוברות.
- `evidence/main-1.0.0-reproduce-20261031-01/`
- תיקייה קפואה: `/home/tomer/ps5-za-native/za-main-1.0.0-frozen-20261031` (‏1.4G).
- שחזור: `/home/tomer/ps5-za-native/za-main-1.0.0-reproduce-20261031-01`.
- חבילה: `/home/tomer/ps5-za-native/za-main-1.0.0-package-20261031-01`.


## Active installation-tool branch (31.10.2026)

| Branch | Base | Scope | Status |
|---|---|---|---|
| codex/tools-newrun-install | main-1.1.0 / a69658a | Dedicated eboot-only JSON-number fix adapter; reuses existing queue, backup, swap and rollback mechanism | Local preparation only; no console access or installation authorization |

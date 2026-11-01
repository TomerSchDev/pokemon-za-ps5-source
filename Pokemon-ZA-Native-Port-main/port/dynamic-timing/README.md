# dynamic-timing — תזמון דינמי ל-Z-A 2.0.2 (מודל, glue ובדיקות)

29.10.2026. **מחקר ותכנון, לא בנייה.** שום דבר כאן לא מקושר ל-eboot, לא הותקן ולא הורץ בקונסולה.
הניתוח המלא, כולל הראיות וסימוני "מוכח / הנחה": `analysis/dynamic-timing-design-HE.md`.

## הרעיון בשורה אחת
במקום לשכתב את טבלת משכי הפריים של המשחק (`main+0x3393e20`) כמו Dynamic 60 RC3.0, מחזירים את משך הצעד
**לצרכן שקובע את צעד הסימולציה בלבד** (שלוש פונקציות `SetFrameMode`). הטבלה המקורית נשארת לצרכנים שמחלקים בה:
קצב האנימציות (`f_7001015260`, `f_70010273f0`) וה-DRS. כך תיקון הזמן לא מבוטל באנימציות, וזו כנראה הסיבה
לסטיות האנימציה שהמחבר תיעד ב-RC1.1.

## הקבצים
| קובץ | מה |
|---|---|
| `za_dyn_timing.h/.c` | המודל: C11 טהור, בלי פלטפורמה ובלי globals. `za_dt_frame()` פעם בפריים, `za_dt_step_for()` לכל SetFrameMode. מדיניות `safe` (מומלצת) ו-`rc3` (ההחלטות של RC3 על ה-hooks הנכונים). |
| `za_rc3_reference.h/.c` | מודל נאמן-להוראות של ה-helper של RC3.0 (double/float, `fcvtzs` רווי, התחלה מ-tick 0, השהיה של קריאה אחת). משמש רק להשוואה בבדיקות. |
| `za_dyn_glue.h/.c` | ה-glue המוצע לפורט: `za_dt_frame_cfg` (H1), `za_dt_present_mode` (H2), `za_dt_step_ns` (H3–H5), ו-`za_dt_anim_table_ns` (‏H6/H7 אופציונליים: אבחון, וניסוי A/B של מכנה האנימציה). כולל אפשרויות `ZA_DT_*`, לוג `[za-dyn]`, ומגביל FPS ו-hitches לבדיקות קונסולה. |
| `prepare-dynamic-hooks.py` | מאמת את אתרי ה-hook (build ID, מילות ההוראה, הטבלה, SHA-256 של היחידות, מופע יחיד של כל משפט). עם `--out` כותב **עותקים** מתוקנים של `main_660.c`, `main_665.c`, `main_1049.c` ו-manifest; עם `--anim` גם של `main_467.c` ו-`main_468.c` (‏H6/H7); עם `--syntax` מריץ עליהם `clang -fsyntax-only`. |
| `audit_nso.py` | ביקורת קריאה-בלבד של ה-NSO, שמשחזרת את הממצאים הסטטיים: הטבלה, כל ההפניות לעמוד הטבלה, ה-relocation שמצביע אליה, שלושת ה-vtables של ה-holders, ה-GOT של ה-singleton ב-`0x610b900`, והמחרוזות. |
| `test/test_dyn_timing.c` | 60,144 בדיקות של המודל מול שעון וירטואלי וה-present pacing של הפורט, ובהשוואה ל-RC3. |
| `test/test_glue.c` | ה-glue מול stubs של ה-runtime, כולל 4 threads קוראים במקביל. |
| `test/run-tests.sh` | בונה ומריץ הכול (clang, `-Wall -Wextra -Werror`, ASan+UBSan), שוב ב-`-O2 -march=x86-64-v3`, ובדיקת קומפילציה ליעד PS5. |
| `test/results.txt` | הפלט של ההרצה האחרונה. |

## הרצה
```
# מ-Windows (Git Bash / PowerShell):
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash "/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port/port/dynamic-timing/test/run-tests.sh"
```
הבינאריים נבנים ב-`/tmp` ונמחקים. בדיקת היעד PS5 משתמשת ב-SDK שב-`/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk` אם הוא קיים.

אימות אתרי ה-hook וביקורת ה-NSO (קריאה בלבד; ב-WSL, צריך `liblz4.so.1` או את המודול `lz4`):
```
python3 -I port/dynamic-timing/prepare-dynamic-hooks.py <aot/main> <exefs/main>
python3 -I port/dynamic-timing/prepare-dynamic-hooks.py <aot/main> <exefs/main> --anim --out /tmp/x --syntax <source>/runtime
python3 -I port/dynamic-timing/audit_nso.py <exefs/main>
```

## מה נבדק ועבר (29.10.2026, clang 21.1.8)
- **קצב קבוע 25–60 FPS:** ב-`safe` הסימולציה עוקבת אחרי שעון הקיר בטווח 1% מ-31 עד 60 FPS, וקצב האנימציה נשאר 1.000.
  ב-30 ומטה הצעד הוא 33.33ms המקורי (25 FPS → 83%, כמו המשחק המקורי במצב 30).
- **RC3 על אותם תרחישים:** 58–59 FPS ב-0.98 (הצמדה ל-16.67), אנימציות ב-0.83 ב-50 FPS, ב-1.10 ב-33 FPS
  (המספרים ש-RC1.1 פרסם), וב-1.5 ב-45 FPS (מצב 1).
- **מעברים 60→45→60:** מעבר אחד לכל כיוון, צעד רציף (קפיצה מרבית 3ms), בלי פריימים מהירים.
- **תנודה סביב 46 FPS:** `safe` מחליף מצב פעם אחת (hysteresis 46/48 + 30 פריימים); ספי RC3 מתהפכים 79 פעמים.
- **עצירות:** stall של 2s ו-pause של 30s מדולגים. **ב-RC3 אחריהם 63/116 פריימים במהירות עד פי 2**. hitch של 120ms נחתך ל-50ms.
- **שעון:** חזרה אחורה (5ms, 10s) וקפיצה קדימה (10s) לא משבשות. RC3 מגיב בצעדים שגויים.
- **הפעלה:** בלי פרץ בהתחלה. ב-RC3 (prev tick = 0) כ-139 פריימים במהירות עד פי 2 אחרי uptime של 100s.
- **present interval:** אם הוא עוקב אחרי המצב (בלי המקבילה לפאצ'-ה-SDK), מצב 1 ננעל על 30 ולא חוזר. עם interval 1 הוא חוזר.
- **>60 FPS בלי pacing:** רצפת 16.67ms נותנת פי 2. ניסוי `sub60` עוקב אחרי 120 FPS.
- **שני frame clocks, אימוץ, דגל ה-registry, stand-down (מצב 2, דגל ה-variable step), jitter, סשן מעורב של 20 דקות** (0.09% סטייה).
- **glue (26 בדיקות):**
  - `off` לא משנה את r16/force60. מגביל ה-FPS עובד גם בו, כדי להשוות ל-static 60 תחת ירידה מאולצת.
  - `safe` מחזיק את המצב, נותן present interval 1, רושם לוגים עם מוני קריאות ה-step וה-anim, ומפעיל מגביל FPS ו-hitches.
  - ‏H6/H7: כברירת מחדל ערך הטבלה (קצב 1.2 ב-50 FPS, כלומר צעד/נומינלי); בניסוי הצעד (קצב 1.0, כמו RC3).
  - 4 threads ביצעו מאות אלפי קריאות בזמן 200,000 פריימים, בלי ערך לא עקבי.
- **יעד PS5:** `za_dyn_timing.c` ו-`za_dyn_glue.c` מתקמפלים ב-`-target x86_64-sie-ps5 -Werror`.
- **אתרי ה-hook:** 15 מילות הוראה (21 עם `--anim`), הטבלה ו-SHA-256 של היחידות תואמים. כל משפט מופיע פעם אחת. העותקים המתוקנים, 3 שורות ב-`main_660.c` ושורה אחת בכל יחידה אחרת, עוברים `-fsyntax-only` מול `runtime/cpu.h` של עץ הבנייה.

## מה לא הוכח
- התנהגות המשחק בקונסולה: מהירות הליכה, מתקפות, תפיסה, סנכרון קול. תוכנית הבדיקה נמצאת בפרק 5 של המסמך.
- משמעות ה-registry ב-`main+0x610b980` (הוכח רק שזה הבייט הנמוך של מונה איברים ב-hash map) ומשמעות המצב הגלובלי
  ש-`f_7001015260` מחלק בו. ההסבר לסטיות של RC1.1 הוא הסקה, לא מדידה.
- שאין frame clock נוסף ושדגל ה-variable step (`cfg+0x21`) תמיד 0. ה-glue רושם את שניהם בלוג.

## שילוב בבנייה (לסוכן הבא)
1. `prepare-dynamic-hooks.py <aot/main> <exefs/main> --anim --out $work/dyn-r25 --syntax $work/source/runtime`.
2. לקמפל את העותקים עם הדגלים של `build-hardware-r13.sh` (‏`-O1 -DGUEST_VOLATILE ...`; אף אחת מהיחידות לא ב-`giants.mk`),
   ולהחליף אותם בעותק של ארכיון המשחק.
3. להוסיף ל-title את `za_dyn_timing.o` ו-`za_dyn_glue.o`. `za_title_frame_cfg` של r16 נשאר, ונקרא מ-H1 כשהמדיניות `off`.
4. ב-title entry, מפתחות ב-`perf-r24-options.txt`:
   - `timing=off|safe|rc3` → `ZA_DT_POLICY`.
   - `timing_log` → `ZA_DT_LOG`.
   - `timing_anim=table|step` → `ZA_DT_ANIM`.
   - `timing_stress_fps` → `ZA_DT_STRESS_FPS`.
   - `timing_spike_ms` / `timing_spike_every` → `ZA_DT_STRESS_SPIKE_MS` / `ZA_DT_STRESS_SPIKE_EVERY`.
5. אופציונלי: `--wrap=za_performance_status` שיחזיר `za_dt_status()` כשהוא לא -1, כדי שעמודת ה-mode של ה-observer תראה את המצב הדינמי.

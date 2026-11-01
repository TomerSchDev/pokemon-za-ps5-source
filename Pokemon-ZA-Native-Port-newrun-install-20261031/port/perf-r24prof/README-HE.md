# r24-prof — מדידה: scale, force60 ופרופיילר דגימה

בסיס: r24-perf (`a7890eca…6a5610`), וממנו r23c. כל קובצי האפשרויות של r23c זהים בבייטים, ו-`performance-options.txt` נשאר `optimized`.
**כל תכונה חדשה כבויה כשהמפתח שלה חסר.** בלי מפתחות חדשים ההתנהגות היא של r24-perf.

תוצר: `artifacts/randomizer-r24-prof/PPSA91762` (החבילה), ולידה, **מחוץ** לחבילה, `llvm-pie-r24prof.elf` — ה-PIE המדויק שממנו הומר ה-eboot (לפענוח הדגימות). ה-SHA-256 של שניהם ב-`artifacts/randomizer-r24-prof/BUILD-INFO.txt`.
חזרה: להתקין מחדש את r24-perf (`a7890eca…`) או את r23c (`dd1df486…`); שניהם מתעלמים מהמפתחות החדשים.

## מפתחות חדשים ב-`/app0/perf-r24-options.txt`
שורה `key=value`, בלי רווחים סביב `=`; `#` מתחיל הערה. נקרא פעם אחת בעליית האפליקציה.

| מפתח | ברירת מחדל | מה עושה |
|---|---|---|
| `scale=<f>` | כבוי (Match display) | `LARECOMP_SCALE=f`: גובה הרינדור = 1080×f ללא קשר למצב התצוגה. `scale=1` עם פלט 4K = רינדור 1080p והגדלה ב-present; `1.5` = ‏1620p. טווח 0.25–4. |
| `force60=1` | כבוי | כל קריאה של מצב הפריימים של המשחק מחזירה 0 (60 FPS): בלי ניסיון ובלי חזרה ל-30. **למדידה בלבד** — מתחת ל-60 המשחק מתקדם בהילוך איטי. ה-observer מדווח mode 1 מרגע שזה בתוקף. |
| `sample=1` | כבוי | פרופיילר דגימה (להלן). |
| `sample_us=<n>` | 1000 | המרווח בין דגימות של ה-render thread (200–100000 µs). |
| `sample_threads=render\|all` | all | רק ה-render thread, או גם כל thread אורח לסירוגין. |
| `sample_seconds=<n>` | 20 | חלון: קובץ אחד ושורת klog אחת לכל חלון (5–120). |
| `sample_keep=<n>` | 30 | קבצים לכל boot; הישן ביותר נדרס (1–200). |

ערך לא חוקי נרשם בלוג (`bad value`) ולא משנה כלום. המפתחות של r24 (`gaps`, `dcache`, `prof`, `prof_every`, `mode`) לא השתנו.

### מה ה-present עושה עם scale
בבנייה הזו (PS5, Vulkan) `UPSCALE_SHARP` = **FSR1** (EASU+RCAS), והוא פועל רק כשהפלט גדול מהתמונה; `antialias` כבוי כברירת מחדל (אין `larecomp.ini` בקונסולה). לכן `scale=1` בפלט 4K = רינדור 1920×1080 ו-FSR1 ל-3840×2160. השורות בלוג:
- `[za-r24prof] render scale 1.000 x 1.000 (...) for output 3840x2160; LARECOMP_SCALE=1 res_mode=0; present: antialias=off upscaler=fsr1 (...)` — בכל שינוי של קנה המידה.
- `[post] 1920x1080 fsr1 -> 3840x2160` — השורה הקיימת של ה-runtime, כשהמסלול משתנה.

## הפרופיילר
thread דוגם שולח `SIGPROF` (`pthread_kill`) ל-render thread בכל `sample_us`, ובמקביל ל-thread אורח אחד בתורו (`all`) — כ-2,000 דגימות בשנייה בברירת המחדל. ה-handler (בלי נעילות, בלי הקצאות, בלי stdio, בלי TLS) רושם RIP וקורא אחד (`[RBP+8]` רק כש-RBP בתוך המחסנית של ה-thread ומעל RSP) לטבעת מוקצית מראש. בסוף כל חלון ה-thread הדוגם כותב קובץ ושורת klog.

- **threads:** אורחים נרשמים ב-`thread_main` (kernel.c), ה-render thread מסומן בהגשה הראשונה שלו (`nvnQueueSubmitCommands`), ו-thread ה-kick של RADV בקריאה הראשונה שלו ל-`sceAgcSuspendPoint` (link `--wrap`).
- **קבצים:** `/download0/zarecomp/r24prof/samples-b<boot>-s<slot>.bin` (בזמן ריצה: `/mnt/sandbox/PPSA91762_000/download0/zarecomp/r24prof/`). `slot = window % keep`. בעלייה נמחקים קבצי ה-boot שלפני הקודם. החסם על הדיסק מודפס בשורת ההפעלה (`disk_bound_mib`, כ-89 MiB בברירות המחדל). חלון בלי דגימות לא נכתב. כתיבה לקובץ `.part` ואז rename.
- **שורות klog:**
  - הפעלה: `[za-r24prof] sampling on: period_us=1000 threads=all window_s=20 keep=30 boot=N dir=… signal=SIGPROF anchor=… text=…-… (vq rc=0) disk_bound_mib=…`
  - `[za-r24prof] render thread: slot 3 (g58, guest entry 7100…)`, `[za-r24prof] RADV kick thread: slot 7`
  - לכל חלון: `[za-r24prof] win=4 span_ms=20012 sent=39980 kill_err=0 recs=39950 drop=0 skip=0 unk=0 text=1 file=samples-b2-s004.bin th: R:g58=19990/12%/61% g5a=1210/88%/90% …` — לכל thread (שישה העסוקים): דגימות / **ext%** (RIP מחוץ לטקסט של ה-eboot: מודולי מערכת, בעיקר המתנות ו-syscalls ב-libkernel) / **nofp%** (בלי קורא). ext% מחליף את שעוני ה-thread השבורים כהערכת עבודה מול המתנה; `?` כשטווח הטקסט לא ידוע.
- **פענוח במחשב:** `python3 port/perf-r24prof/symbolize_samples.py --pie artifacts/randomizer-r24-prof/llvm-pie-r24prof.elf samples-b*.bin [--from-ns … --to-ns …] [--json out.json]`: לכל thread ולכולם — קבוצות (game = קוד מתורגם `f_<addr>`, ‏runtime/<קובץ>, ‏radv, ‏port, ‏ext), פונקציות מובילות, וזוגות קורא→פונקציה. `--from-ns/--to-ns` (CLOCK_MONOTONIC, כמו ה-CSV של ה-observer) בוחרים קבצים שחופפים למדידה.

### עלות משוערת (לא נמדדה בקונסולה)
כ-2,000 אותות בשנייה; מסירת אות ו-handler של כמה מיקרו-שניות כל אחד — סדר גודל של אחוז-שניים מליבה אחת, מפוזר. ה-thread הדוגם עצמו: syscall‏ nanosleep לכל period, ו-TSC (לא clock_gettime) לתזמון. כתיבת חלון (כ-1 MiB) עוצרת את הדגימה לכמה מילישניות. זיכרון: טבעת 1.5 MiB + מאגר קובץ ≈ ‏2.8 MiB, ‏malloc פעם אחת.

## סיכונים ידועים
- **EINTR:** ‏`SA_RESTART` מחדש את רוב ה-syscalls, אבל `nanosleep` ו-`poll`/המתנות עם timeout עשויים לחזור מוקדם; ‏`pthread_cond_wait` עשוי להתעורר — הקוד אמור לטפל ב-wakeups מדומים, אבל זו התנהגות שלא נבדקה בתדר הזה על ה-runtime.
- **אות בתוך קוד אורח:** ה-handler רץ על ה-alt stack של ה-thread (`SA_ONSTACK`; ‏1 MiB לכל thread אורח מ-`crash_handler_install`). thread בלי alt stack (ה-kick) מריץ אותו על המחסנית שלו — מסגרת קטנה.
- **קורא:** הקוד מקומפל בלי frame pointers, ולכן RBP הוא לרוב אוגר רגיל: הרבה דגימות בלי קורא (`nofp`), ובמחסניות fiber תמיד בלי. קורא שנרשם הוא "סביר", לא מוכח.
- **לא אומת בחומרה:** מסירת `pthread_kill`/`SIGPROF` ב-libkernel של 13.60, ה-layout של `sceKernelVirtualQuery` (נבדק ונפסל אם לא סביר → `text=0`, ‏ext%=`?`), ‏`pthread_attr_get_np` לטווח המחסנית, ה-wrap של `sceAgcSuspendPoint`.
- **force60** הוא מצב 60 הסטטי: מתחת ל-60 FPS המשחק כולו איטי. לא לשחק בו.

## כיבוי
להסיר את השורה (או `sample=0`, `force60=0`, להסיר `scale=`) ולהפעיל מחדש את האפליקציה. בלי `sample=1` אין signal handler, אין thread דוגם ואין קבצים; כל hook הוא טעינה אטומית אחת.

## בדיקות host (`port/perf-r24prof/test/test.sh`, ‏ASan/UBSan)
- `test_options.c`: ברירת המחדל של החבילה, מפתחות r24, טווחים וערכים לא חוקיים.
- `test_core.c`: registry, טבעת (כולל drop ואינדקסים שלא הושלמו), כלל הקורא, גוף ה-handler, פורמט הקובץ, רוטציה, שורת הסיכום, ו-4,000 אותות `SIGPROF` אמיתיים ל-6 threads עם `pthread_kill`.
- `test_symbolize.py`: PIE סינתטי (game / runtime / radv / ext), קוראים, פילטר זמן, וקריאת הקובץ שכתב ה-C.

# r24-clock — בדיקת עלות השעון ב-render thread

r24-prof, ועוד שלוש אפשרויות ומונה. כל השינויים מבחינים בין התנהגות קיימת להתנהגות החדשה לפי מפתח ב-`/app0/perf-r24-options.txt`; בלי המפתח, ההתנהגות כמו r24-prof.

## למה
בפרופיל של r24-prof (`r24prof-profile-hardware-20261029-080200Z`):
- ‏67% מהדגימות של ה-render thread היו בכתובת אחת ב-libkernel ‏(`0x800000fec`).
- הקוראים: `draw_` ‏(43%), ‏`draw` ‏(9.6%), ‏`vk_tex` ‏(6.3%), ‏`os_time_get_nano`, ‏`os_time_get_absolute_timeout`, ‏`cbuf_info`.
- `draw_` ב-exec.c קורא לשעון כ-12 פעמים לכל draw (`PROF_T0` / `PROF_ADD` ו-`prof ? SDL_GetTicksNS()`), כש-`prof` = ‏`LARECOMP_VK_PROF`. r16 ‏(`za_performance_init`) מפעיל אותו תמיד.
- `SDL_GetTicksNS` של ה-shim קורא ל-`clock_gettime(CLOCK_MONOTONIC)`, ‏syscall שנמדד בכ-20 µs ב-13.60.

הבנייה הזו מאפשרת לכבות את המדידה, להחליף את השעון ל-TSC, ולספור בדיוק כמה `clock_gettime` נקראים ולמדוד כמה כל אחד עולה.

## בנייה
| | |
|---|---|
| eboot | `artifacts/randomizer-r24-clock/PPSA91762/eboot.bin`, 402,048,514 בתים, SHA-256 `35ee54dacd03b217a30f9e18b7e57f8117a880b859013dee7b005da44b6d573e` |
| PIE | `artifacts/randomizer-r24-clock/llvm-pie-r24clock.elf`, 490,971,264 בתים, SHA-256 `8feaf3fd3e2b3c2be21e5639e6032b54ca8b4ce4eb879599dae4c4aff06a62e4`. ליד החבילה, לא בתוכה; לפענוח דגימות עם `port/perf-r24prof/symbolize_samples.py --pie`. |
| בסיס | r24-prof ‏(`64acf8fa…4fb3`) |
| עבודה | `/home/tomer/ps5-za-native/perf-r24clock-20261029` (rsync -a של perf-r24prof-20261029) |
| מתכון | `build-perf-r24clock.sh` |
| ראיות | `evidence/perf-r24clock/` |

## המפתחות החדשים
| מפתח | משתנה | מה עושה |
|---|---|---|
| `vkprof=0` | `ZA_PERF_VKPROF_OFF` | ה-title entry מסיר את `LARECOMP_VK_PROF` מיד אחרי ש-r16 מציב אותו, ו-exec.c קורא אותו פעם אחת באתחול ה-renderer. מדידת ה-CPU של ה-renderer כבויה: אין קריאות שעון לכל draw, ושורת `[vk]` מאבדת את `\| gpu … cpu exec … draw … submit` ואת שדות ה-tex/pass/views/pace שאחריהם. `vkprof=1` או בלי המפתח: כמו היום. |
| `ticks=tsc` | `SDL3_PS5_TICKS=tsc` | `SDL_GetTicksNS`, ‏`SDL_GetTicks` ו-`SDL_GetPerformanceCounter` של ה-shim נקראים מה-TSC ‏(`sceKernelReadTsc` / `sceKernelGetTscFrequency`, חלוקה ב-128 ביט) במקום `clock_gettime`. הבחירה בזמן ריצה, בקריאה הראשונה. כשנבחר TSC רצה בדיקה חד-פעמית: 1,000 קריאות TSC מול `clock_gettime` באותו thread, ונרשמים הסטייה הגדולה, קריאות שחזרו אחורה, ו-µs לקריאת `clock_gettime`. `ticks=clock` או בלי המפתח: `clock_gettime` כמו היום. |
| `tsc=1` | `LARECOMP_PS5_TSC=1` | `plat_now_ns` של ה-runtime ‏(ps5.c) מה-TSC: ה-vsync המדומה, התזמון וזמני ה-kernel. נפרד מ-`ticks` כי הוא נוגע בקצב המשחק. ps5.c רושם בלוג את השעון שבשימוש. |

**המונה (תמיד פעיל):** כל `clock_gettime` שהקוד של ה-title או ארכיון RADV קוראים לו עובר דרך `--wrap=clock_gettime` אל `za_clock.c`. שם הוא נספר ונמדד ב-TSC, לפי סוג ה-thread:
- `render`: ה-thread שקרא אחרון ל-`nvnQueueSubmitCommands`.
- `guest`: שאר ה-threads של המשחק.
- `other`: השאר, כמו ה-kick של RADV, ה-vsync והאודיו.

על שורת `[za-r24-perf]` נוסף:
`cg_render=<קריאות> cg_render_ns=<זמן בתוך הקריאות> cg_render_max_ns=<הקריאה הארוכה>`, וכך גם ל-`guest` ול-`other`.
העלות: שתי קריאות TSC ‏(~24 ns) וכמה פעולות atomic לכל `clock_gettime`. קריאות שמתבצעות בתוך מודולי המערכת לא נספרות.

## החבילה
`perf-r24-options.txt` נשלח **בתצורת הבדיקה המהירה**:
- פעילים רק `scale=1` (פלט 4K, רינדור 1080p) ו-`force60=1` (מצב 60 קבוע, מאט מתחת ל-60). **זו חבילת בדיקה, לא לשחק בה.**
- כל השאר כהערות: `vkprof`, ‏`ticks`, ‏`tsc`, ‏`gaps`, ‏`dcache`, ‏`prof`, ‏`mode`, ‏`sample*`.

ששת קובצי האפשרויות של r23c זהים בבייטים, נשלפים מ-`Update.zip` של r23c ומאומתים מול `Packaging.json`. `performance-options.txt` = ‏`optimized`.

## השינויים
- `apply-runtime-r24clock.py`, עריכות טקסט מדויקות על עותק העבודה:
  - `exec.c`: שורת לוג של מצב `prof` באתחול ה-renderer, ו-`za_clock_report` בסוף שורת `[za-r24-perf]`.
  - `platform/ps5.c`: לוג של השעון של `plat_now_ns`.
  - `port/sdl3-shim/src/sdl3_ps5_core.c`: בלוק הטיימרים, עם בחירת TSC בזמן ריצה ובדיקה חד-פעמית.
  - ה-diffs המלאים ב-`evidence/perf-r24clock/*.diff`.
- `title_entry-r24clock.c`: ה-title entry של r24-prof, עם `za_r24clock_options.h` ועם `vkprof=0` אחרי `za_performance_init`.
- `za_r24clock_options.h`: המפענח של r24-prof עם שלושת המפתחות החדשים.
- `za_clock.c`: ה-wraps (`clock_gettime`, ‏`za_prof_note_render`, ‏`za_prof_thread_begin` / `za_prof_thread_end`) ו-`za_clock_report`.
- `analyze_r24clock.py`: הסיכום של `analyze_r24.py`, ועוד `clock_gettime` לפריים ולקריאה, ושדות `[vk]` לכל חלון.

## אימות (ראו BUILD-INFO.txt)
- הרישומים (hle_impls 9,360 / services 320 / resets 296 בתים) נשמרו.
- אין ייבואים דינמיים חדשים מול r24-prof.
- אין global שמוגדר פעמיים.
- `self --inspect`: ‏12 segments, ‏integrity valid.
- אובייקטים: שונו רק `title_entry.o`, ‏`sdl3_ps5_core.o`, ‏`exec.o`, ‏`ps5.o`, ונוסף `za_clock.o`. ‏`vma.o` זהה בקוד ושונה רק בנתיב של מחרוזת assert. כל השאר זהים בבייטים ל-r24-prof.
- רק `__wrap_clock_gettime` קורא ל-`clock_gettime` המיובא. בין הקוראים ל-wrap: ‏`SDL_GetTicksNS`, ‏`plat_now_ns`, ‏`block_current`, ‏`svc_impl`, ו-`c23_timespec_get`, שדרכו עוברים `os_time_get_nano` ו-`os_time_get_absolute_timeout` של Mesa.
- החבילה זהה ל-r24-prof בכל קובץ חוץ מ-eboot.bin ו-perf-r24-options.txt.

## בדיקות host
`test/test.sh`, כולן עוברות:
- המפענח (ASan/UBSan).
- המונה, עם TSC מזויף ו-threads אמיתיים: ספירה לפי סוג thread, זמן בתוך הקריאה, מקסימום, איפוס, חיתוך.
- `analyze_r24clock.py` מול klog סינתטי.
- קומפילציה ליעד PS5 של `za_clock.c`, ה-title entry וה-shim (`-Werror`).
- המקור של ה-shim בלי השינוי נבנה מחדש זהה בבייטים לאובייקט של r24-prof (strip-debug), כלומר המתכון של אובייקט ה-shim מוכח.

## לא אומת בחומרה
- כמה `clock_gettime` באמת נקראים ומה עולה כל אחד. זה בדיוק מה שהבדיקה מודדת.
- שה-TSC מונוטוני וסינכרוני בין ליבות ב-13.60. הבדיקה החד-פעמית רצה ב-thread אחד בלבד.
- שאין קוד במסלול המשחק שתלוי בהבדל בין `clock_gettime` ל-TSC: `tsc=1` נוגע ב-vsync המדומה ובתזמון.
- `vkprof=0` משנה רק את מדידת ה-CPU של ה-renderer. ה-observer, מוני r24 ו-gaps לא תלויים בה (נבדק בקוד, לא בחומרה).

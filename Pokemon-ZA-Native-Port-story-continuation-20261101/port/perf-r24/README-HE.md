# r24-perf — r23c המותקן + מכשור ביצועים ואפשרויות A/B

כותרת: `randomizer-r24-perf`, אפליקציה `PPSA91762`. בסיס: r23c המותקן (eboot `dd1df486…8677`), במתכון שלו בדיוק — `repro-r23c.sh` בנה מחדש את העותק הלא-משונה וקיבל eboot זהה בבייטים. לא הותקן ולא הורץ בקונסולה.

## אפשרויות — `/app0/perf-r24-options.txt`
קובץ נפרד, כי `/app0/performance-options.txt` שייך ל-r16: הוא מפעיל את ה-key memo וה-cbuf lean רק כשהתוכן הוא בדיוק `optimized\n` (או `shadow\n` או ריק), וכל תוכן אחר מכבה אותם. החבילה שולחת אותו `optimized\n`, זהה בבייטים ל-r23c.

שורה `key=value` לכל אפשרות, `#` מתחיל הערה. נקרא פעם אחת בתחילת `main` עם open/read/close (כמו התיקון של r23c). קובץ חסר או מפתח חסר = התנהגות r23c. כל מפתח נרשם בלוג `[za-r24-options]`.

| מפתח | משתנה סביבה | משמעות |
|---|---|---|
| `gaps=1` | `ZA_PERF_GAPS` | ציר זמן GPU: חותמות זמן GPU בתחילת/סוף כל הגשה לוגית → busy / idle / היסטוגרמת פערים |
| `dcache=cpu` | `ZA_PERF_DCACHE` | מטמון ה-dispatch לכל `Cpu` במקום `__thread` (emulated TLS). `tls` = r23c |
| `prof=1` | — | פרופיל GPU לכל pass (`[gpuprof] frame N: …`) כל `prof_every` פריימים (ברירת מחדל 120; כל פריים כזה ממתין ל-GPU פעם אחת). הפרופיילר של שורת `[vk]` דולק תמיד, כי r16 מגדיר `LARECOMP_VK_PROF=1` — גם ב-r23c |
| `prof_every=<n>` | `ZA_PERF_GPUPROF_EVERY` | תדירות הפרופיל לכל pass |
| `mode=<W>x<H>` | `SDL3_PS5_MODE` | מצב VK_KHR_display שה-visible region שלו בגודל הזה (למשל `1920x1080`); אם אין כזה — המצב הראשון כמו קודם. רשימת המצבים נרשמת תמיד |

עומק slots: `/app0/slot-depth-options.txt` של r23c מקבל עכשיו `8`, `16`, `32`, `64` (עם LF אופציונלי). אותו מנגנון: מעבר חד-פעמי אחרי פריים תקין, אותה בדיקת אחידות ו-headroom של 1GiB במקטע הפנוי הרציף הגדול ביותר — לפני ואחרי הקצאת המשאבים של ה-slots הנוספים — ואותה חזרה ל-8 בסירוב. גם הפקודה החיה `slot_depth` של ה-observer מקבלת 32/64.

החבילה כוללת את ששת קובצי האפשרויות של r23c, זהים בבייטים לחבילה המותקנת שלו (`performance-options.txt`=`optimized`, `performance-profile.txt`=`30`, `observer-enable.txt`=`observe-r17`, `local-shader-options.txt`=`local`, `submission-options.txt`=`batch4`, `slot-depth-options.txt`=`16`), ובנוסף `perf-r24-options.txt` עם `gaps=1`, `dcache=tls`, `prof=0`.

## השורה `[za-r24-perf]`
שורה אחת לכל חלון סטטיסטיקה (~2 שניות), מיד לפני שורת `[vk]` של אותו חלון. שורת `[vk]` עצמה זהה ל-r23c. כל הערכים הם סכומי החלון ביחידות שלמות (ns, ספירות):
`frame frames logic_ns logic_n present_ns present_n klock_takes klock_blocked klock_wait_ns dcache_tables dcb kwords flush_ns dcb_submit_ns kick_ns gaps spans gpu_span_ns gpu_busy_ns idle_ns idle_between_ns idle_within_ns idle_unknown_ns ngaps gap_lt100us gap_lt500us gap_lt2ms gap_lt8ms gap_ge8ms spans_dropped threads thread_cpu_ns top=id:ns:prio:core:entry,…`

- `logic` — מהחזרה מה-present עד ה-`nvnQueueSubmitCommands` הראשון אחריו; `present` — הזמן בתוך `backend_present`.
- `klock_*` — רכישות `g_klock`, אלו שמצאו אותו תפוס וזמן ההמתנה שלהן (כל 23 אתרי הנעילה).
- `dcb` — קריאות `radv_ps5_submit` (הגשות AGC כולל פיצולים); `kwords` — מילות הפקודה; `flush_ns` / `dcb_submit_ns` / `kick_ns` — הטיימרים של ה-winsys (`radv_ps5_cpu_flush`, `sceAgcDriverSubmitDcb`, `sceAgcSuspendPoint` בחוט ה-kick). נקראים דרך `--wrap` בקישור, בלי לבנות את RADV מחדש; שורת ה-winsys של 10 שניות (`radv/ps5 submissions:`) ממשיכה לקבל את הסכומים המלאים שלה.
- `gaps=1`: `gpu_busy_ns` — איחוד קטעי ה-GPU של ההגשות; `idle_between_ns` — פער בין שתי הגשות `vkQueueSubmit2` שונות; `idle_within_ns` — פער בין הגשות לוגיות בתוך אותה הגשה; ההיסטוגרמה לפי גודל פער.
- `threads` / `top` — זמן CPU של חוטי האורח (`pthread_getcpuclockid`), שישה העסוקים ביותר. `threads=-1` אם הקונסולה מסרבת לשעון הזה.

## הרצה בלי השגחה (אותו פרוטוקול observer)
- `python port/perf-r24/console.py --client r24 …` — `console.py` המקורי ללא שינוי, עם הלקוח של r24 (`record`, `measure`, `fps`, `snapshot`, `close` וכו' כמו קודם).
- `python port/perf-r24/sample_slots_r24.py … 32` — עותק של `sample_slots.py` עם הלקוח של r24, עומקים 8/16/32/64 ו-identity `client=r24`.
- `python port/perf-r24/analyze_r24.py --klog <klog> --csv <measure_N.csv>` — סוכם את חלונות `[za-r24-perf]` שנמצאים כולם בטווח הפריימים של המדידה ומחלק בפריימים.

## מגבלות
- שום דבר כאן לא נבדק בחומרה. `pthread_getcpuclockid`, מצב תצוגה שאינו הראשון ו-32/64 slots על 13.60 — לא מאומתים.
- חותמות ה-GPU הן התחלה/סוף של buffers, לא של כל draw; פער "within" כולל barriers ו-cache flushes. אין לחבר זמני CPU ו-GPU.
- `dcache=cpu` מניח ש-`Cpu` רץ על חוט אחד בכל רגע (כך ב-fiber.c, דרך דגל ה-busy). מצביע הטבלה יושב בריפוד של `Cpu`, כי שינוי `cpu.h` היה משנה את `GAMELIB_ID` ופוסל את ארכיון המשחק.

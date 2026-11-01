# r25-perf — thread הגשה, שעון TSC והקלטה משורשרת של RADV מעל r24-clock

29.10.2026. בנייה ראשונה מתוך הביקורת `analysis/fps-headroom-audit-HE.md` (טבלה מדורגת, שורות 1 ו-2). `radv_threaded` ותוכנית batch4/batch8 נוספו בעקבות `analysis/high-fps-research-HE.md` (סעיפים 1.4 ו-6). נבנתה ונבדקה במחשב בלבד; **לא הותקנה ולא רצה על הקונסולה**.

## למה
בבדיקת העומס (r24-clock, ‏force60, פלט 4K עם 1080p פנימי) נקודת בית הקפה נתנה כ-46.97 FPS (כ-21.3 ms לפריים). ה-render thread של המשחק (זה שקורא ל-`nvnQueueSubmitCommands`) מתרגם, מגיש ל-GPU (`vkQueueSubmit2`) ומציג (`vkQueuePresentKHR`) בטור, על עצמו. בנקודת הבדיקה הוא היה עסוק כ-15 ms מתוך 16.67, מתוכם כ-4.3 ms הגשה (`sceAgcDriverSubmitDcb` ‏3.9 ms) [נמדד, עלייה C של r24-clock].

## מה חדש — שלושה מפתחות ב-`/app0/perf-r24-options.txt`, כבויים אם אינם מופיעים

| מפתח | משתנה | מה עושה |
|---|---|---|
| `submit=thread` (או `inline`) | `ZA_PERF_SUBMIT` | thread הגשה נפרד: ה-render thread ממשיך להקליט, לסגור ולאגד את ה-command buffers בדיוק כמו קודם, אבל כל `vkQueueSubmit2` וכל `vkQueuePresentKHR` עוברים לפי הסדר ל-thread אחד (worker) וה-render thread חוזר מיד |
| `clock=tsc` (או `real`) | `ZA_PERF_CLOCK` | אחרי בדיקת סנכרון TSC בין ליבות: `CLOCK_MONOTONIC` מה-TSC לכל מי שקורא דרך ה-wrap, **חוץ מתזמון המשחק** (`plat_now_ns` והאודיו נשארים על השעון האמיתי; `tsc=1` נשאר המתג הנפרד שלהם) |
| `radv_threaded=1` (או `0`) | `RADV_THREADED_RECORDING` | ההקלטה המשורשרת של RADV עצמו: קריאות `vkCmd*` נכנסות לתור (עם העתקת הארגומנטים), ו-worker של ה-device מקליט אותן. `vkEndCommandBuffer` ממתין שה-worker יסיים. אנחנו רק מגדירים את המשתנה לפני `vkCreateInstance`; הקוד כבר נמצא בארכיון RADV המקושר |

כל המפתחות של r24 / r24-prof / r24-clock נשארו ללא שינוי. `performance-options.txt` נשאר `optimized`, וכל קובצי האפשרויות של r23c זהים בבייטים.

**למה לא ה-thread של Mesa:** ל-sync של ה-PS5 אין `VK_SYNC_FEATURE_TIMELINE` (`radv_ps5_sync.c`), ולכן Mesa מריץ timeline מדומה (submit מסוג DEFERRED), ו-`MESA_VK_ENABLE_SUBMIT_THREAD` חל רק במצב ASSISTED (`vk_device.c`). צריך thread משלנו.

## submit=thread — מה נשמר בדיוק, ואיך
- **סדר:** worker אחד, FIFO. כל פריט נכנס לתור תחת `za_sq_lock` בסדר שבו הקוד הקודם היה מגיש.
- **ערכי timeline:** ללא שינוי (מוגש עותק של ה-`VkSubmitInfo2`). `submit_seq` עדיין סופר הגשות לוגיות.
- **המתנות:** `vk_wait_seq` קודם דוחף את ה-batch שמוחזק ב-CPU (r20b), אחר כך ממתין שה-worker הגיש את הערך הזה לדרייבר (`za_r25_wait_submitted`), ורק אז ממתין ל-timeline כמו קודם. כך `QueueFinish`, fences, שימוש חוזר ב-slot, קריאת counters וקריאת XFB ממתינים גם לעבודה שבידי ה-worker.
- **slots:** slot מתאפס רק אחרי שההגשה שלו הסתיימה (`sub()` ← `vk_wait_seq`), כלומר גם הוגשה.
- **רישום:** ה-ledger של r23, טבעת ההגשות של r24 והמונים של r20 מתעדכנים בעת ההכנסה לתור (באותו סדר), על ה-render thread ותחת `za_sq_lock`. ה-worker לעולם לא לוקח `za_sq_lock`, `seq_lock` או `cq_lock`, ולכן הכנסה לתור מלא (back-pressure, 64 פריטים) בזמן ש-`za_sq_lock` מוחזק לא נתקעת.
- **present:** ההגשה של ה-present (המתנה ל-acquire, signal ל-done) נכנסת לתור לפני ה-present עצמו. `vkQueuePresentKHR` ו-`vkAcquireNextImageKHR` דורשים סנכרון חיצוני של ה-swapchain, ולכן שניהם לוקחים `za_r25_sc_lock`. ה-acquire ממתין תחתיו 2 ms לכל היותר ומנסה שוב, כך שה-present של ה-worker אף פעם לא מעוכב לאורך זמן (ה-acquire של VideoOut ממתין ל-flip, לא ל-present שלנו).
- **תוצאת ה-present** מגיעה למשחק באיחור של פריים (ה-present האחרון שהסתיים). OUT_OF_DATE / SUBOPTIMAL שה-worker ראה גורמים ל-present הבא לדווח OUT_OF_DATE פעם אחת, ו-`device.c` בונה את ה-swapchain מחדש. גם ה-observer מקבל את התוצאה הזו (פריים אחד מאוחר).
- **`vkDeviceWaitIdle`** (בניית swapchain מחדש, יציאה, אתחול מחדש בתוך התהליך) דורש סנכרון של כל ה-queues: הוא רץ בתוך quiesce (ריקון התור והשבתת ה-worker עד הסוף).
- **אובדן device:** ה-worker הוא שמבצע את הקריאה שנכשלת, מדפיס (`LARECOMP_VK_DEVLOST_TRACE`) ו-FATAL, כמו ב-inline.
- **inline (ברירת המחדל):** אותן קריאות על ה-render thread כמו ב-r24-clock. נוספו רק מדידות TSC סביבן.

## clock=tsc
- **בדיקה בעלייה** (`za_clock_r25_enable`, לפני שה-threads של המשחק קיימים): לכל זוג CPUs (הראשון במסכת ה-affinity מול כל אחד מהאחרים, עד 16 זוגות) — שני threads נעוצים (`pthread_setaffinity_np`) מבצעים 1000 סבבי ping-pong של קריאות TSC מגודרות ב-`lfence`.
- **דחייה** (השעון נשאר אמיתי, ונרשם בלוג) אם: thread לא ננעץ; סבב חרג מ-50 ms; קריאה כלשהי חזרה אחורה בין ליבות ביותר מ-1 µs; גבולות ה-offset לא עקביים; או גבול ה-skew מעל 2 µs.
- **השעון:** עוגן אחד מהשעון האמיתי, ומשם `base + (tsc - base_tsc)`, עם clamp גלובלי כך שקריאה מאוחרת לעולם לא תהיה קטנה מקודמת (מגן מפני skew שיורי מתחת למיקרו-שנייה).
- **מה מומר:** רק `CLOCK_MONOTONIC` דרך ה-wrap. בפועל: Mesa/RADV (`os_time_*` דרך `c23_timespec_get`, `vk_device_get_timestamp`), טיקים של SDL כשאין `ticks=tsc`, ה-sampler, ה-compiler worker ו-`ps5_clock_nanosleep`. ‏`CLOCK_REALTIME` (מועדי ההמתנה של `kernel.c`) ושעוני CPU של threads לא מומרים.
- **בדוח:** `ck_drift_ns` — השעון הנגזר מ-TSC מינוס השעון האמיתי, נדגם פעם בחלון.

## radv_threaded=1 — מה נבדק לפני שנוסף
- **האפשרות קיימת ב-Mesa שלנו:** ‏PS5_Mesa ב-`1ba9874f`, ו-`d0d7325e` ("radv: threaded recording (RADV_THREADED_RECORDING=1)") הוא אב שלו.
  - בקוד: `src/amd/vulkan/layers/radv_threaded_layer.c:66-70` — ‏`os_get_option("RADV_THREADED_RECORDING")` ואחריו `atoi != 0`. ‏`os_get_option` הוא `getenv`.
  - בתמונה המקושרת (`libvulkan_radeon.ps5.a` של PS5_Vulkan) נמצאים המחרוזת, `radv_threaded_worker` ו-`radv_threaded_recording_enabled`.
- **מתי RADV קורא אותו:** ב-`vkCreateDevice` (`radv_device.c:1499`). שם הוא מפעיל את ה-worker ומכניס את ה-layer לטבלת ה-dispatch של ה-device (`radv_device.c:820`).
- **שזה עובד ב-title סטטי:**
  - `getenv`, ‏`setenv` ו-`unsetenv` מיובאים מה-libc של המערכת.
  - יש תקדים: `setenv("MESA_SHADER_CACHE_DIR", ...)` ב-`platform/ps5.c:409` הוכח בחומרה (r4), ו-RADV כותב את המטמון לפיו.
  - ה-title entry קורא את קובץ האפשרויות בתחילת `main`, לפני `za_game_main`, כלומר לפני `vkCreateInstance`.
- **שכל `vkCmd*` של ה-runtime עובר דרך ה-layer:** ה-loader הסטטי (`port/vk-loader/vk_loader.c:686-718`) ממלא את `vkl_fn` מ-`vkGetDeviceProcAddr` אחרי יצירת ה-device, ולפני כן מה-trampolines של ה-instance. שני המקורות עוברים דרך טבלת ה-dispatch של ה-device.
- **שהסדר נשמר** (`radv_threaded_layer_gen.py:32-48, 145-149`):
  - כל `vkCmd*` נכנס לתור עם עותק עמוק של הארגומנטים.
  - פקודות שהתור לא יודע לשמור (למשל push descriptors) קודם מרוקנות את התור ורק אז מוקלטות.
  - destroy, ‏free ו-`vkResetDescriptorPool` ממתינים ל-worker.
  - `vkEndCommandBuffer` מרוקן וממתין (`radv_threaded_layer.c:388-396`).
- **שזה מתחבר ל-`submit=thread`:**
  - ה-layer לא עוטף את `vkQueueSubmit2`, ‏`vkQueuePresentKHR` או `vkAcquireNextImageKHR`.
  - command buffer מגיע ל-submitter שלנו רק אחרי `vkEndCommandBuffer`, כלומר כשהוא כבר מוקלט במלואו. סדר הזיכרון עובר דרך ה-mutex של ה-layer ואז דרך התור שלנו.
  - ה-worker של RADV לא נוגע ב-queue ולא באף מנעול שלנו.
  - המקביליות שנוספת (worker אחד מקליט בזמן ש-thread אחר מגיש) קיימת גם עם `submit=inline`, וזה שימוש תקין ב-Vulkan.
  - המצב שלנו מוגבל ל-16 command buffers להגשה (`ZA_BATCH_CBS`, כולל batch8), והוא לא משתנה.
- **מיקום ה-threads:** ה-runtime לא נועץ threads, כי `SetThreadCoreMask` הוא no-op (`kernel.c:831`). לכן ה-worker של RADV וה-submitter שלנו לא יורשים את הליבה של ה-render thread.
- **מה היה צריך להוסיף אצלנו — השעון:** כשנגמרת ל-worker של RADV העבודה, הוא מסתובב עד 50 µs על `clock_gettime(CLOCK_MONOTONIC)` (`radv_threaded_layer.c:99-104`). הקריאות האלה עוברות דרך ה-`--wrap` שלנו, כלומר עשרות קריאות לכל batch, ואלפים תחת `clock=tsc`.
  - בלי טיפול הן היו מנפחות את `cg_other`.
  - הן גם היו כותבות כל הזמן למונים המשותפים ול-clamp הגלובלי של `clock=tsc`, וה-render thread היה מתחרה איתן על אותן שורות cache.
  - לכן `za_clock_r25.c` מזהה את ה-worker (`radv_threaded_replaying()`, הפונקציה של RADV עצמו) רק כש-`radv_threaded=1`, ורק ב-thread שאינו ה-render thread.
  - הקריאות שלו נספרות רק ב-`cg_radv`, במונה בשורת cache נפרדת, ומקבלות את השעון האמיתי או TSC בלי clamp. הן משמשות רק את ה-spin של ה-worker עצמו.
  - כש-`radv_threaded=0`, ה-wrap עושה טעינה אחת ו-branch.
  - `cg_radv` > 0 מוכיח שה-worker של RADV רץ, כלומר ש-RADV קרא את המשתנה.
- **מחיר צפוי ב-render thread:** העתקת ארגומנטים במקום הקלטה, והמתנה ל-worker ב-`vkEndCommandBuffer` ובכל destroy/free/reset של descriptor pool. ה-worker גם שורף ליבה עד 50 µs אחרי כל batch.

## מדידות חדשות בשורת `[za-r24-perf]`
- **render thread** (TSC, עם או בלי profile): `exec_ns`, `rsub_ns` (‏`vk_submit_extra` ו-flush של r20b; ב-inline כולל `vkQueueSubmit2`, ב-thread רק הכנסה לתור והמתנת back-pressure), `acquire_ns` / `acquires`, ו-`render_busy_ns` = exec + rsub + logic + present (המדד של הביקורת).
- **submitter:** `sub_items`, `sub_presents`, `sub_busy_ns`, `sub_pushes`, `sub_push_waits`, `sub_push_wait_ns`, `sub_depth_sum` / `sub_depth_max` ו-`sub_lag` (הגשות לוגיות שעוד לא הגיעו לדרייבר, נדגם פעם בחלון).
- **שעון:** `cg_tsc` (קריאות שנענו מה-TSC), `cg_game` (קריאות של תזמון המשחק), `ck=tsc|real`, `ck_drift_ns`, ‏`cg_radv` (הקריאות של ה-worker של RADV; ב-`radv_threaded=1` בלבד).
- **שורות עלייה:** `[za-r25]` (כולל `radv_threaded=0|1`) ו-`[za-r25-clock]` (כולל שורה לכל זוג CPUs).
- **ניתוח:** `python port/perf-r25/analyze_r25.py --klog <klog> --csv <measure_<seq>.csv> --out <...>.json`.
  - ב-`r25` מופיעים גם `radv_threaded` ו-`submission_profile` (מתוך `[za-r20b-submit] startup profile=`).
  - `driver` מכיל DCB-ים לפריים, ‏`dcb_submit` ms לפריים ולכל DCB, ‏kick ms לכל DCB ו-kwords לפריים, להשוואה בין batch4 ל-batch8.

## קבצים (`port/perf-r25/`)
- `za_submitter.h` — ליבת התור וה-worker, בלי Vulkan (נבדקת ב-host).
- `za_submitter_vk.inc` — חיבור ל-Vulkan; נכנס ל-`exec.c` לפני `za_submission_queue_r20.inc`.
- `za_tsc_check.h` — בדיקת הליבות, ההחלטה, השעון וה-clamp (נבדקים ב-host).
- `za_clock_r25.c` — ה-wrap של r24-clock, ועוד `clock=tsc`, ‏`za_clock_game_gettime` והמסלול של ה-worker של RADV (`cg_radv`). מחליף את `za_clock.o`.
- `za_r25_options.h`, `title_entry-r25.c` — המפתחות החדשים (`radv_threaded` מגדיר את `RADV_THREADED_RECORDING` ומודיע ל-wrap).
- `apply-runtime-r25.py` — עריכות טקסט מדויקות בעותק: `exec.c`, ה-`.inc` של ההגשה וה-executor, `device.c`, `platform/ps5.c`, `services/audio.c`.
- `build-perf-r25.sh` — הבנייה.
- `analyze_r25.py` — הניתוח.
- `test/` — בדיקות ה-host.
- `TEST-r25-HE.md` — תוכנית הבדיקה בקונסולה.

## בנייה ובדיקות
- `bash port/perf-r25/build-perf-r25.sh` ב-WSL. הפלט: `artifacts/randomizer-r25-perf/PPSA91762`, ה-PIE המדויק `artifacts/randomizer-r25-perf/llvm-pie-r25.elf`, והראיות ב-`evidence/perf-r25/`.
- `bash port/perf-r25/test/test.sh` ב-WSL. הוא מריץ את ליבת התור תחת ASan/UBSan ו-TSan: סדר, back-pressure, המתנה להגשה, ריקון, quiesce, עצירה, ושני producers שמחזיקים מנעול משלהם.
- הוא גם בודק את בדיקת ה-TSC על ה-TSC האמיתי של המחשב ועם שעונים מזויפים שמקדימים או מאחרים, את השעון ואת ה-clamp בין threads, את המפתחות ואת ה-analyzer, וקומפילציה ליעד PS5.
- `test_clock_radv.c` מכליל את `za_clock_r25.c` עצמו, עם stubs לייבואים של ה-PS5 ול-`radv_threaded_replaying`. הוא רץ תחת ASan/UBSan ו-TSan, ובודק:
  - ה-worker של RADV נספר רק ב-`cg_radv`.
  - ב-`clock=tsc` ה-worker מקבל TSC בלי clamp (ה-clamp לא זז); ב-`clock=real` הוא מקבל את הקריאה האמיתית.
  - כולם מלבדו, כולל ה-render thread גם כשהוא "replaying", נספרים כמו קודם.
  - כש-`radv_threaded` כבוי אין שינוי.
  - הדוח מאופס.
  - worker מסתובב במקביל ל-render thread.
  - ‏`host-include/` מחליף את כותרות ה-affinity של FreeBSD.

## לא אומת בחומרה
- ה-worker על הקונסולה: סדר ההגשה מול ה-present, ה-acquire עם המתנה של 2 ms, quiesce סביב `vkDeviceWaitIdle`, ומה קורה כשאובדן device קורה על ה-worker.
- שה-acquire של VideoOut מכבד timeout שאינו 0 ו-UINT64_MAX (בקוד הוא כן: `os_time_get_absolute_timeout`).
- הרווח בפועל: ה-render thread אמור להתקצר בכ-4 ms, אבל ייתכן שהוא יחכה יותר ל-ring slot (16 slots ≈ 4 הגשות פיזיות). אם כן, כדאי לנסות את עומק 32/64 שקיים ב-r24.
- בדיקת ה-TSC רצה רק בעלייה; ה-drift נמדד לאורך הריצה, אבל לא נוצר עליו תיקון.
- הקריאות ל-`pthread_getaffinity_np` ו-`pthread_setaffinity_np` הן ייבוא חדש מ-libkernel (קיימות ב-stubs).
- `radv_threaded=1` לא רץ אף פעם עם המשחק הזה.
  - ה-layer עבר CTS (474,440 מקרים), אבל לא נבדק על סצנה של Z-A: transform feedback, ‏descriptor sets לכל draw, ‏`vkResetDescriptorPool` ב-hot path.
  - לא נבדק גם שילוב של שלושה threads בתוך RADV בבת אחת (render, ה-worker של RADV וה-submitter).
  - הרווח לא ידוע. ההערכה במחקר היא עד ≈1.2 ms (חלק ה-RADV של ה-render thread) פחות עלות ההעתקה, ואולי פחות, כי `vkEndCommandBuffer` נקרא לפני כל הגשה.
- `submit=thread` עם batch8: נבדק בקוד (16 command buffers להגשה = `ZA_BATCH_CBS`), לא בחומרה.

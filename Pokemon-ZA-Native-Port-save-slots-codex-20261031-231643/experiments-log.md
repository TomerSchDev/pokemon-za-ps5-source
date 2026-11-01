# יומן ניסויים — Pokémon Legends Z-A Native PS5

כל רשומה: השערה, שינוי, build/run ID, תוצאה, הצעד הבא. תאריכים לפי UTC אלא אם צוין אחרת.

## החלטות
- **27.10.2026 ~06:30Z — גרסת המשחק לפורט: 2.0.2 + DLC "Mega Dimension"** (החלטת Tomer; הסקר ב-analysis/game-version-inventory.md המליץ 1.0.0 בגלל ראיות PC רחבות יותר). הסט: research/pokeza-pc/update-2.0.2-20261025 (exefs/main build b1f12fd9…, romfs.bin ממוזג 5,989,104,840 B שכולל את תוכן ה-DLC, aoc/0100f43008c45002.bin stub של 604 B, aot/ = הקוד המתורגם ל-2.0.2, runtime-source = pokeza-recomp 4d82d89 + patch זיהוי של 5 שורות "v0.1.4-local202"). השלכות ידועות: אין hook לקצב פריימים ל-build הזה (30 FPS), ראיות PC דלות (4 ריצות קצרות, DLC לא נבדק במחשב), שמירות בפורמט 2.0.x. אין לערבב עם 1.0.0.
- **27.10.2026 — r5 אושר** (probe לחסמים: ELF סטטי שמן, external_memory_host, מיפוי 3.2 GB, 48 תהליכונים).

## r1 — 26.10.2026 20:13Z — ZA Native Probe A0 (CPU VideoOut)
- **השערה:** אפליקציה מקומית שנבנתה עם ps5-payload-dev/sdk v0.42 נטענת על 13.60, מציגה מסך, קוראת וכותבת קבצים.
- **שינוי:** בסיס ps5-native-app-boilerplate 38c9175 + probe.cpp; זהות PPSA91760.
- **build:** za-native-probe-a0-20261026-r1, PID 96.
- **תוצאה:** מסך אושר חזותית על ידי Tomer; קריאת /app0 וכתיבת /download0 הצליחו; mmap של 32GiB נכשל ENOMEM; דפים בודדים ב-MAIN_BASE/HEAP_BASE הצליחו; TCP listener נכשל EACCES.
- **הבא:** שמירת הטווח דרך API מקומי (r2).

## r2 — 26.10.2026 20:20Z — שמירת טווח האורח ומיפוי direct memory
- **השערה:** sceKernelReserveVirtualRange על 0x7000000000..0x7800000000 מצליח, ומיפוי direct memory לתוכו עובד.
- **שינוי:** מסלול native reserve/alloc/map/mprotect/munmap/release ב-probe.cpp; eboot.bin הוחלף (SHA-256 7ca20759…318f).
- **build:** za-native-probe-a0-20261026-r2, PID 99 (ובהמשך PID 108 לאחר הפעלה מחדש).
- **תוצאה:** כל ה-rc היו 0; native_rw_ok=true; heartbeat חי לאורך דגימות; VideoOut הגיע ל-flip_submitted. אין אישור חזותי נפרד ל-r2.
- **הבא:** Vulkan דרך RADV (r3).

## r3 — 26.10.2026 — Vulkan דרך RADV (PS5 winsys) על 13.60
- **השערה:** ארכיון RADV של PS5_Mesa 1ba9874 (pin של PS5_Vulkan f410e67) מקושר סטטית ל-title מאתחל instance/device, יוצר swapchain דרך VK_KHR_display על VideoOut, ומציג פריימים מצוירים ב-GPU על קושחה 13.60.
- **pins:** PS5_Vulkan f410e67a0241b3e8edcdbcd2a9b285dfc4a412ed; PS5_Mesa 1ba9874f478657ccf6da72ce55f0260164cc0bd0; PS5_PayloadSDK b83202be73e930050e00de0f1b4d9ec46c0391bf (מעל upstream v0.42); zlib 1.3.2; toolchain: SDK wrapper בוחר clang 21.1.8 (Ubuntu), host mesa_clc מול LLVM 21.
- **שינוי:** title חדש באותה זהות PPSA91760: vk-probe/src/za_vk_probe.c + build-vk-probe.sh; רק eboot.bin מוחלף (libc.prx זהה: e6ff45d1…0036).
- **build:** za-vk-probe-a0-20261026-r3, eboot.bin SHA-256 4962b5e512bf2fb8f6b3f6f982c1195239744802d51965efb31d310a35b788f6 (24,487,519 בתים); RADV archive SHA-256 0124a064…08aed; clang 21.1.8. PID 112, הופעל 21:19:47Z.
- **תוצאה (21:19Z–21:23Z):** **Vulkan עובד על 13.60.** 30 עברו, 1 נכשל, exit_reason=completed אחרי 183 שניות, יציאה נקייה (אין תהליך eboot.bin אחרי, אין fatal signal/GPU fault ב-klog).
  - device: "PlayStation 5 GPU (RADV NAVI21)", Vulkan 1.4.354, radv Mesa 26.2.0; 8 GiB device-local, 4 GiB host-visible; 16 הרחבות instance, 221 הרחבות device.
  - דרישות המשחק: כל 9 ההרחבות וכל 33 התכונות מדווחות.
  - VK_KHR_display: "PS5 VideoOut" 3840×2160 @ 59.940 Hz, 3 modes; surface נתמך, B8G8R8A8_UNORM מוצע; swapchain 3 תמונות (rc=0).
  - pipeline עם dynamic rendering קומפל על הקונסולה ב-10.5 ms; זמני שלבים: instance 13.0 / device 51.3 / surface 48.8 / swapchain 19.5 ms; פריים ראשון 243.8 ms מההתחלה.
  - 10,792 פריימים ב-180 שניות; זמן פריים min/avg/max 16.653/16.683/16.711 ms (נעול ל-60 Hz, FIFO); last_present_rc=0.
  - readback (פריים 90): מרכז 0xff555555, פינה 0xff0f0f40 — כצפוי.
  - הכשל היחיד: "files: the persistent log in /app0 opened" — /app0 הוא read-only מתוך האפליקציה (גם RADV: "Failed to create /app0/radv-shader-cache ... Permission denied"). לכן אין עותק קבוע ב-/data/homebrew/PPSA91760; ה-JSON הסופי נלקח מ-/download0 על ידי watch_r3.py.
  - באג ב-run_r3.py (תוקן): exit_reason "running" נחשב ליציאה, ולכן ה-run יצא אחרי דגימה אחת.
  - ראיות: evidence/vk-r3-update-20261026-211944Z.json, vk-r3-20261026-211944Z.json/-klog.log/-probe.log, vk-r3-watch-20261026-212251Z.json (19 דגימות). הועתקו ל-NAS: \\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port\r3-results-20261026-2323 (SHA-256 אומת לכל קובץ).
  - אישור חזותי מ-Tomer: טרם התקבל.
- **הבא:** r4 — שלט (pad) וקול באותו title; shader cache ל-/download0 במקום /app0. אחר כך סעיפים ג–ד (נעילת גרסת משחק, platform/ps5).

## r4 — 27.10.2026 06:03Z — שלט, קול ו-shader cache באותו title
- **השערה:** scePad ו-sceAudioOut עובדים מתוך title שהופעל דרך ה-launcher payload על 13.60 (ABI כמו ProsperoEden); ה-shader cache של RADV ניתן להפניה ל-/download0 דרך MESA_SHADER_CACHE_DIR.
- **שינוי:** שלבים pad ו-audio ב-vk-probe/src/za_vk_probe.c (+472/-31), push constant "white" ב-tri.vert (המשולש מלבין כשכפתור לחוץ), run_r3.py ל-r4 (PERSISTENT_* ב-/download0, DEFAULT_BUILD, KNOWN_EBOOTS). ה-SDK מספק stubs ל-libScePad/libSceAudioOut/libSceUserService בלי headers; הפרוטוטיפים ומבנה ה-pad נלקחו מ-ProsperoEden. אודיו ב-thread ייעודי (pthread).
- **build:** za-vk-probe-a0-20261027-r4, eboot.bin SHA-256 135151946d6e81483f5934c52b3dc778df23f5443b97a143245c9d5770be6573 (24,497,189 בתים); אותם pins כמו r3 (SDK b83202be, Mesa 1ba9874, clang 21.1.8); libc.prx ללא שינוי. r3 (PID 118, הופעל מחדש על ידי מישהו) נסגר לפני ההתקנה; גיבוי ב-evidence/backup-eboot-4962b5e512bf2fb8.bin.
- **תוצאה (06:03Z):** **40 עברו, 0 נכשלו, exit_reason=completed** — עצירה ב-OPTIONS אחרי 32.5 שניות, 1,924 פריימים, 16.683 ms ממוצע, readback תקין (0xff555555 / 0xff0f0f40), אין crash/GPU fault ב-klog.
  - pad: sceUserServiceInitialize rc 0, foreground user 375927969; scePadInit rc 0; scePadOpen rc 0x030f0700 (=handle); 1,925 קריאות scePadReadState ללא כשל, connected=1; **27 לחיצות**, כפתורים שנראו 0x0000fffe, לחיצה ראשונה בפריים 708 (12.1 ש׳, מסכה 0x4000); light bar rc 0; OPTIONS עצר את הלולאה.
  - audio: sceAudioOutInit rc 0; sceAudioOutOpen(user 0xff, main, 256, 48000, S16 stereo) rc 0x20000000 (=handle); SetVolume rc 0; pthread_create rc 0; **טון 1 ש׳ הושלם** (188 grains, 0 כשלים); 27 ביפים (500 grains); 6,022 grains סה"כ, 0 כשלי output; close rc 0.
  - shader cache: /download0/radv-shader-cache נוצר (mkdir rc 0), MESA_SHADER_CACHE_DIR הוגדר (rc 0); 2 entries אחרי enumeration ובסוף (mesa_shader_cache_db, radv_builtin_shaders). שורת "Failed to create /app0/radv-shader-cache ... Permission denied" מ-r3 **נעלמה** מה-klog.
  - **אישור מ-Tomer (08:04 שעון ישראל): "יש צלילים כשאני לוחץ על כפתורים"** — ביפ לכל לחיצה אושר. משולש לבן בלחיצה, light bar ירוק וטון הפתיחה — טרם אושרו במפורש.
  - ליקוי רישום קטן: pad.handle ו-audio.handle נרשמו -1 ב-JSON בעוד ה-handle נמצא ב-open_rc (הלוג מציג handle 51316480). לא משפיע על התוצאה.
  - ראיות: evidence/vk-r4-update-20261027-060307Z.json, vk-r4-20261027-060307Z.json (+ -klog.log, -probe.log).
- **משמעות:** **אבן דרך A הושלמה** — טעינה על 13.60, לוג מזוהה, Vulkan instance/device/swapchain, פריים GPU עם readback, קריאת /app0, כתיבת /download0, אירוע משלט, קול, יציאה נקייה והפעלה מחדש.
- **הבא:** אבן דרך B. (1) לנעול גרסה 1.0.0 (המלצת analysis/game-version-inventory.md). (2) r5 — probe לחסמים שזוהו ב-analysis/pokeza-runtime-platform.md: ייבוא host pointer של direct memory דרך VK_EXT_external_memory_host, מיפוי ~3.2 GB בכתובת קבועה בחלון האורח, 48 תהליכונים עם stack 256 MB, וטעינת ELF של מאות MB (או sprx) ב-title.

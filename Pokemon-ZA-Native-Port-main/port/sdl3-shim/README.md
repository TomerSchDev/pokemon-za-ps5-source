# SDL3 shim ל-PS5 — תחליף מינימלי ל-SDL3 עבור ה-runtime של Pokémon Legends Z-A Recomp

תאריך: 27.10.2026. מצב: **קומפילציה בלבד** (compile-only) עם ה-toolchain של `vk-probe` עברה (`build-check.sh`, חמישה שלבים, `-Wall -Wextra -Werror`); כל 56 הסמלים שה-shim מייבא נמצאו ב-stubs של ה-SDK / בארכיון RADV / ב-builtins ש-recipe הקישור של r4 כבר מספק (`llvm-nm`, בדיקה ידנית). **לא הורץ על הקונסולה** ולא נבדק בקישור מלא של title.

ה-runtime של הרקומפ (C) משתמש ב-SDL3 לחלון/משטח Vulkan, אירועים, שלט, אודיו, טיימרים וכמה כלי עזר. אין SDL3 ל-PS5 (רק SDL2 ציבורי, ו-SDL3 רשמי תחת NDA), ולכן ה-shim הזה מממש **בדיוק** את תת-הקבוצה שה-runtime קורא — באותם שמות, חתימות, enum-ים ומבני נתונים כמו SDL3 — מעל ה-API-ים של PS5 שה-probe (`vk-probe/src/za_vk_probe.c`, ריצות r3/r4 על 13.60) כבר הוכיח.

## מבנה

```
port/sdl3-shim/
├── include/SDL3/        24 headers: SDL.h (מטרייה) + תת-headers באותם שמות כמו SDL3
├── src/
│   ├── sdl3_ps5_internal.h   פרוטוטיפים של Sony (אין headers ב-SDK), מבנה ה-pad, קבועים, עזרים משותפים
│   ├── sdl3_ps5_core.c       Init/Quit, שגיאות, לוג, hints, messagebox, טיימרים, cpuinfo, filesystem, threads, surfaces
│   ├── sdl3_ps5_video.c      החלון היחיד + SDL_Vulkan_* (VK_KHR_display דרך vk_icdGetInstanceProcAddr של RADV)
│   ├── sdl3_ps5_input.c      תור אירועים, scePad → אירועי gamepad + snapshot, API של gamepad, מקלדת/עכבר "לא לחוץ"
│   └── sdl3_ps5_audio.c      sceAudioOut על thread (כמו r4) + מיקסר של כל ה-streams הפתוחים
├── test/consumer.c      צרכן שמכיל את ה-headers כמו ה-runtime ומשתמש בכל קריאה/שדה כמוהו (compile-only, C ו-C++)
├── build-check.sh       בדיקת קומפילציה ב-WSL עם אותו wrapper/דגלים כמו build-vk-probe.sh
└── README.md            המסמך הזה
```

## מקור ה-ABI

- **SDL 3.4.18** — ה-headers שה-build של ה-PC קומפל מולם (ולא 3.2.28 של msys2):
  `research/pokeza-pc/runtime-opt-r1/SDL3-3.4.18/x86_64-w64-mingw32/include/SDL3/`.
  ההוכחה: `runtime-opt-r1/build-final.log` ו-`update-2.0.2-20261025/runtime-build.log` מכילים `-I../SDL3-3.4.18/x86_64-w64-mingw32/include`, ו-`SDL_LoadPNG`/`SDL_SavePNG` שה-runtime קורא קיימים רק מ-3.4 (לא ב-3.2.28). כל ערך enum, דגל ומבנה ב-headers כאן הועתק משם (בדקתי גם שאין הבדל בתת-הקבוצה הזו מול 3.2.28 מלבד `SDL_GAMEPAD_TYPE_GAMECUBE/STEAM` שנוספו לפני `COUNT`).
- **פרוטוטיפים של Sony** (ה-SDK מספק stubs בלי headers — מוצהרים ב-`src/sdl3_ps5_internal.h`):
  - `[probe]` מהקובץ `vk-probe/src/za_vk_probe.c` (r4, רץ על 13.60): `sceUserService*`, `scePad*`, `sceAudioOut*`, `sceKernelDebugOutText`, ומבנה ה-pad של 120 בתים (כפתורים ב-0, `connected` ב-0x4c, `timestamp` ב-0x50) — מועתקים מילה במילה, כולל ה-`_Static_assert`-ים.
  - `[sdk]` מ-`ps5platform/kernel.h` של ה-payload SDK (pin `b83202be`): `sceKernelGetDirectMemorySize`, `sceKernelReadTsc`, `sceKernelGetTscFrequency`, `scePthreadGetaffinity(pthread_t, uint64_t*)`. מתועדים שם ובפרוב של הפלטפורמה (PROBE.md), **לא הורצו ב-probe שלנו**.
  - `[eden]` ביטי הכפתורים של ה-pad מ-`research/prosperoeden/third_party/ps5_pad.hpp` (ProsperoEden רץ על הקונסולה הזאת). r4 ראה בפועל את המסכה `0x0000fffe` (כל הכפתורים חוץ מ-Create 0x1 ו-touchpad 0x100000, שאולי פשוט לא נלחצו).
- **מיפוי DualSense → SDL** לפי המיפוי המובנה של SDL ל-PS5 (HIDAPI): Cross→SOUTH, Circle→EAST, Square→WEST, Triangle→NORTH, Options→START, Create→BACK, L1/R1→SHOULDER, L3/R3→STICK, D-pad, touchpad click→TOUCHPAD; מקלות `v*257-32768` (למעלה/שמאלה = שלילי כמו SDL), triggers `0..32767`. ה-runtime (`input.c`) קורא `-LEFTY` ו-`> 16000` על ה-triggers — תואם.

## איך בודקים (WSL)

```
wsl -d Ubuntu -- bash "/mnt/c/.../Pokemon-ZA-Native-Port/port/sdl3-shim/build-check.sh"
```

הסקריפט משתמש ב-`sh $PS5_VULKAN/tooling/prospero-clang18` עם `PS5_CLANG=/usr/bin/clang-21` ו-`PS5_PAYLOAD_SDK` (כמו `build-vk-probe.sh`), ומריץ חמישה שלבים: (1) כל header ציבורי לבדו, כ-C11 וכ-C++20, וגם שני סדרי include מול `vulkan.h`; (2) כל קובץ `src/*.c` עם `-std=c11 -O2 -Wall -Wextra -Werror`; (3) `test/consumer.c` עם דגלי ה-RTFLAGS של ה-runtime, כ-C וכ-C++; (4) כל סמל `SDL_*` שה-consumer מייבא מוגדר באובייקטים של ה-shim (`llvm-nm`); (5) קובצי ה-C של ה-runtime שמכילים SDL (`hle/input.c`, `hle/bindings.c`, `hle/pl.c`, `services/audio.c`, `paths.c`, `main.c`, וה-headers `nvn/renderer.h`, `ui/menu.h`, `input_bind.h`) עוברים `-fsyntax-only` מול ה-headers של ה-shim (קריאה בלבד מעץ המקור; `RUNTIME_CHECK=skip` מדלג). תיקיית העבודה: `/tmp/sdl3-shim-build` (או `SDL3_SHIM_WORK`). `device.c`/`exec.c`/`textures.c` לא נבדקים בשלב 5 כי הם צריכים את VMA (`vk.h`); ה-headers שהם מכילים מכוסים בשלב 1.

## שילוב ב-title (מה הפורט צריך לעשות)

1. לקמפל את `src/*.c` עם `-I port/sdl3-shim/include -I $PS5_MESA/include` ולקשר יחד עם ה-runtime; ה-runtime עצמו מקומפל עם `-I port/sdl3-shim/include` במקום SDL3 אמיתי.
2. **קישור**: ה-shim מייבא `scePad*`, `sceAudioOut*`, `sceUserService*`, `sceKernelGetDirectMemorySize`, `scePthreadGetaffinity` (stubs: `libScePad.so`, `libSceAudioOut.so`, `libSceUserService.so`, `libkernel.so` — `--as-needed target/lib/*.so` כמו ב-`build-vk-probe.sh`), `vk_icdGetInstanceProcAddr` (ארכיון RADV), ו-libc/pthread רגילים.
3. **Vulkan**: ה-runtime קורא ל-`vkCreateInstance`, `vkGetInstanceProcAddr` וכו' כסמלים ישירים (`-lvulkan` ב-PC). ארכיון RADV מייצא **רק** `vk_icdGetInstanceProcAddr`/`vk_icdGetPhysicalDeviceProcAddr`/`vk_icdNegotiateLoaderICDInterfaceVersion` (נבדק ב-`llvm-nm`), ולכן הפורט צריך "loader" סטטי קטן שמפנה את ה-`vk*` של ה-runtime ל-ICD — **מחוץ ל-shim**. `SDL_Vulkan_GetVkGetInstanceProcAddr()` מחזיר את `vk_icdGetInstanceProcAddr` ואפשר לבנות עליו.
4. **לוג**: ה-shim כותב ל-`stderr` (`[sdl3-ps5] ...`, ו-`SDL_Log*` כ-`[sdl3] LEVEL: ...`). ה-title חייב לקרוא `ps5_klog_capture_stderr(...)` בתחילת `main` (כמו ה-probe) כדי שזה יגיע ל-klog.
5. **לכבות ב-runtime**: PNG (`SDL_LoadPNG`/`SDL_SavePNG` כאן הם stubs שנכשלים עם שגיאה — `paths.c` יוותר על האייקון, `textures.c` על HD packs, `device.c` על צילומי מסך; עדיף לקמפל החוצה), ImGui backend (`imgui_impl_sdl3` — לא קיים כאן; `menu.mm`/`launcher.mm` משתמשים גם ב-SDL שלא מסופק, ראו "לא מסופק"), ו-`SDL_main.h` (ה-runtime לא משתמש).
6. `SDL_Init(VIDEO|GAMEPAD)` ב-`device.c` ואחר כך `SDL_InitSubSystem(AUDIO)` ב-`audio.c` (מכמה threads) — תקין: האתחול idempotent ומוגן במנעול; `SDL_Quit` סוגר הכול.

## טבלת הפונקציות (החוזה: כל מה שקובצי ה-C של ה-runtime קוראים)

סימון: **מומש** = עובד מעל API של PS5 / לוגיקה מלאה; **stub** = מתקמפל ומחזיר תשובה קבועה/כישלון מסודר; **חלקי** = מומש עם מגבלה.

### אתחול, שגיאות, לוג, hints — `sdl3_ps5_core.c`
| פונקציה | מצב | הערות |
|---|---|---|
| `SDL_Init`, `SDL_InitSubSystem`, `SDL_QuitSubSystem`, `SDL_WasInit`, `SDL_Quit` | מומש | VIDEO = כלום (RADV מנהל את VideoOut), GAMEPAD = UserService+scePad (בלי שלט אינו כישלון), AUDIO = sceAudioOut + thread (כישלון → `false`, ה-runtime ממשיך בלי קול). אין ref-count (SDL סופר; כאן idempotent). |
| `SDL_GetError`, `SDL_SetError`, `SDL_ClearError` | מומש | מחרוזת שגיאה per-thread (`_Thread_local`, emulated TLS). 50 השגיאות הראשונות גם ל-stderr. |
| `SDL_SetHint`, `SDL_GetHint` | stub | נשמרים ב-16 תאים, לא משפיעים על כלום. |
| `SDL_Log`, `SDL_LogTrace..Critical`, `SDL_LogMessage(V)`, `SDL_SetLogPriority(ies)`, `SDL_GetLogPriority`, `SDL_ResetLogPriorities` | מומש | ל-stderr; עדיפויות ברירת מחדל כמו SDL (APPLICATION=INFO, ASSERT=WARN, TEST=VERBOSE, אחרת ERROR). |
| `SDL_ShowSimpleMessageBox` | stub | שורת לוג, מחזיר true. |
| `SDL_GetVersion`, `SDL_GetRevision` | מומש | 3.4.18. |
| `SDL_malloc`, `SDL_calloc`, `SDL_realloc`, `SDL_free`, `SDL_strdup` | מומש | malloc/free של libc (ה-title heap דרך `--wrap` של recipe הקישור). |

### חלון ו-Vulkan — `sdl3_ps5_video.c`
| פונקציה | מצב | הערות |
|---|---|---|
| `SDL_CreateWindow` | מומש | חלון לוגי **אחד**; הגודל המבוקש (1280×720) מתועד ומוחלף: עד שיש surface מדווח 3840×2160 (ברירת מחדל, `SDL3_PS5_WINDOW=WxH`), ואחרי `SDL_Vulkan_CreateSurface` — הרזולוציה הפיזית של התצוגה. `SDL_WINDOW_HIDDEN` מוסר; מתווספים `FULLSCREEN|INPUT_FOCUS|MOUSE_FOCUS`. |
| `SDL_DestroyWindow`, `SDL_ShowWindow` | מומש | |
| `SDL_GetWindowFlags` | מומש | `input.c` בודק `INPUT_FOCUS` — תמיד דולק. |
| `SDL_GetWindowSize`, `SDL_GetWindowSizeInPixels` | מומש | אחרי ה-surface שווים ל-`currentExtent` של ה-swapchain (r3/r4: 3840×2160) — חשוב כי `vk_frame_begin` משווה אותם ל-`sc_extent` כל פריים. |
| `SDL_SetWindowFullscreen`, `SDL_SetWindowIcon` | stub | מחזירים true. |
| `SDL_Vulkan_GetInstanceExtensions` | מומש | `{VK_KHR_surface, VK_KHR_display}`, count=2. |
| `SDL_Vulkan_CreateSurface` | מומש | רצף ה-probe: `vkEnumeratePhysicalDevices` (אחד) → `vkGetPhysicalDeviceDisplayPropertiesKHR` (תצוגה אחת) → `vkGetDisplayModePropertiesKHR` (המצב הראשון) → `vkCreateDisplayPlaneSurfaceKHR` ב-`physicalResolution`, transform IDENTITY, alpha OPAQUE, plane 0. הכול דרך `vk_icdGetInstanceProcAddr(instance, ...)`. |
| `SDL_Vulkan_DestroySurface`, `SDL_Vulkan_GetPresentationSupport` | מומש / stub | `vkDestroySurfaceKHR` דרך ה-ICD; presentation support תמיד true (r3/r4: `supported 1`). |
| `SDL_Vulkan_LoadLibrary`, `SDL_Vulkan_GetVkGetInstanceProcAddr`, `SDL_Vulkan_UnloadLibrary` | מומש | אין loader: ה-`path` מתועלם, המצביע הוא `vk_icdGetInstanceProcAddr` של RADV. |

### אירועים ושלט — `sdl3_ps5_input.c`
| פונקציה | מצב | הערות |
|---|---|---|
| `SDL_PumpEvents` | מומש | `scePadReadState` אחת (ה-state השמור, כמו `poll_pad` ב-r4) → `GAMEPAD_ADDED/REMOVED` על שינוי `connected`, `GAMEPAD_BUTTON_DOWN/UP` לכל ביט שהשתנה, `GAMEPAD_AXIS_MOTION` לכל ציר שהשתנה; `INTERCEPTED` (תפריט PS) = הכול משוחרר. פעם בשנייה בודק את קובץ העצירה (ראו QUIT). |
| `SDL_PollEvent` | מומש | מוציא מהתור; כשהתור ריק — pump אחד ועוד ניסיון. לולאת `while (SDL_PollEvent)` קוראת את השלט פעם-פעמיים. `SDL_PollEvent(NULL)` = יש אירוע? |
| `SDL_WaitEventTimeout`, `SDL_WaitEvent` | מומש | poll + שינה של 1 ms עד ה-timeout (ל-`ui_run` עם 16 ms: עד 16 קריאות pad). |
| `SDL_PushEvent` | מומש | thread-safe (mutex); timestamp מתמלא אם 0; תור של 1024. |
| `SDL_EVENT_QUIT` | מומש (טריגר מוגדר) | לעולם לא נוצר מעצמו. הטריגרים: קובץ `SDL3_PS5_QUIT_FILE` (ברירת מחדל `/download0/za-sdl3.quit`, נבדק ב-`stat` פעם בשנייה; `""` מבטל) או `SDL_PushEvent` מה-title. |
| `SDL_HasGamepad`, `SDL_GetGamepads`, `SDL_GetGamepadNameForID`, `SDL_GetGamepadTypeForID` | מומש | instance id 1 כשמחובר; `SDL_GetGamepads` מחזיר מערך `{1,0}` (SDL_malloc, לשחרר עם `SDL_free`). |
| `SDL_OpenGamepad`, `SDL_CloseGamepad`, `SDL_GetGamepadID`, `SDL_GetGamepadName`, `SDL_GetGamepadType` | מומש | אובייקט gamepad יחיד; שם "DualSense Wireless Controller"; סוג `SDL_GAMEPAD_TYPE_PS5` (→ `input.c` בוחר prompts של PlayStation). |
| `SDL_GetGamepadButton`, `SDL_GetGamepadAxis` | מומש | מה-snapshot האחרון (מנעול), ניתן לקריאה מכל thread (ה-HLE של `GetNpadState` רץ על threads של האורח). |
| `SDL_GetScancodeName`, `SDL_GetScancodeFromName` | מומש | טבלת שמות SDL לתת-הקבוצה (אותיות, ספרות, פיסוק, F1–F12, חיצים, keypad, modifiers); השוואה case-insensitive כמו SDL. |
| `SDL_GetKeyFromScancode`, `SDL_GetScancodeFromKey` | מומש | פריסת US; shift → אותיות גדולות/סימנים; מקשים בלי תו → `SDL_SCANCODE_TO_KEYCODE`. |
| `SDL_SetWindowRelativeMouseMode` | stub | true. אין מקלדת/עכבר: אף `KEY_*`/`TEXT_*`/`MOUSE_*`/`JOYSTICK_*` לא נוצר (רק מה שה-title דוחף). |

### אודיו — `sdl3_ps5_audio.c`
| פונקציה | מצב | הערות |
|---|---|---|
| `SDL_GetAudioDeviceFormat` | מומש | מדווח S16 stereo 48000 Hz, `sample_frames` = 1024 (`SDL3_PS5_AUDIO_DEVICE_FRAMES`). ה-runtime גוזר מזה את יעד התור (2 periods): audout ≈ 43 ms, audren ≈ 48 ms. |
| `SDL_OpenAudioDeviceStream` | חלקי | S16/F32, 1/2/6 ערוצים, כל קצב (resampling ליניארי ל-48 kHz; 5.1 מקופל לסטריאו עם המקדמים של `audio.c`). **ללא callbacks** (ה-runtime מעביר NULL). מתחיל paused כמו SDL. עד 16 streams. |
| `SDL_PutAudioStreamData`, `SDL_GetAudioStreamQueued`, `SDL_ClearAudioStream` | מומש | ring buffer בפורמט הקלט (שנייה, גדל עד 32 MB); `Queued` = בתים שהוכנסו וטרם נצרכו, בדיוק כסמנטיקה של SDL. |
| `SDL_ResumeAudioStreamDevice`, `SDL_PauseAudioStreamDevice` | מומש | |
| `SDL_SetAudioStreamGain`, `SDL_GetAudioStreamGain`, `SDL_GetAudioStreamDevice`, `SDL_DestroyAudioStream` | מומש | gain מוחל במיקסר; id לוגי `0x100+slot`. |
| (פנימי) thread המיקסר | מומש | כמו r4: `sceAudioOutOpen(0xff, main, 256, 48000, S16 stereo)` (fallback למשתמש של ה-pad), `SetVolume` 0 dB, `sceAudioOutOutput` חוסם = קצב; שקט כשאין נתונים. stack של 1 MiB מפורש. |

### טיימרים, מערכת, threads, surfaces — `sdl3_ps5_core.c`
| פונקציה | מצב | הערות |
|---|---|---|
| `SDL_GetTicksNS`, `SDL_GetTicks`, `SDL_GetPerformanceCounter/Frequency` | מומש | `clock_gettime(CLOCK_MONOTONIC)` (כמו ה-probe) יחסית לקריאה הראשונה. אופציה: `-DSDL3_PS5_TSC_TICKS=1` → `sceKernelReadTsc`/`sceKernelGetTscFrequency` (12 ns במקום ~20 µs לקריאה לפי מסמכי PS5_Vulkan; **לא אומת כאן**). |
| `SDL_Delay`, `SDL_DelayNS` | מומש | `nanosleep` בלולאת EINTR (`clock_nanosleep` לא מיוצא מ-libkernel). |
| `SDL_DelayPrecise` | מומש | שינה עד ~1 ms לפני היעד, אחר כך spin על השעון. |
| `SDL_GetNumLogicalCPUCores` | מומש | popcount של `scePthreadGetaffinity(pthread_self())` (PROBE.md: `0x1fff` = 13), fallback `sysconf` (16) ואז 13. |
| `SDL_GetSystemRAM` | חלקי | `sceKernelGetDirectMemorySize()/MiB` (≈12288) — הזיכרון שה-title יכול להשתמש בו, לא ה-RAM הכולל. ל-לוג בלבד ב-`main.c`. |
| `SDL_GetBasePath` | מומש | `"/app0/"`. |
| `SDL_GetPrefPath` | מומש | `/download0/<org>/<app>/` (או `SDL3_PS5_PREF_ROOT`), נוצר עם mkdir -p. |
| `SDL_CreateDirectory` | מומש | mkdir -p עם `stat` (לא `access`, שנכשל EPERM על הקונסולה). |
| `SDL_CreateThread` (מאקרו) → `SDL_CreateThreadRuntime`, `SDL_WaitThread`, `SDL_DetachThread` | מומש | pthread עם stack מפורש של 2 MiB (`SDL3_PS5_THREAD_STACK_KB`), כי thread בלי בקשה מקבל 64 KiB בלבד. |
| `SDL_CreateSurface`, `SDL_CreateSurfaceFrom`, `SDL_DestroySurface` | מומש | ABGR8888/RGBA8888 בלבד; מבנה `SDL_Surface` זהה ל-3.4.18. |
| `SDL_ConvertSurface` | חלקי | העתקה רק כשהפורמט זהה (זה מה ש-`textures.c` מבקש אחרי PNG); אחרת NULL + שגיאה. |
| `SDL_LoadPNG`, `SDL_SavePNG` | **stub (נכשל)** | אין מפענח PNG ב-shim. מחזירים NULL/false עם `SDL_GetError` מוסבר. |

### לא מסופק (לא בקובצי ה-C של ה-runtime; רק ב-`.mm`/ImGui)
`SDL_GetCurrentDisplayMode`, `SDL_GetDisplayForWindow`, `SDL_GetWindowPixelDensity`, `SDL_DisplayMode`, `SDL_OpenURL`, `SDL_ShowOpenFileDialog`, `SDL_ShowOpenFolderDialog`, `SDL_DialogFileFilter`, `SDL_StartTextInput`, `SDL_StopTextInput` (ב-`menu.mm`, `launcher.mm`, `controls_ui.mm`), ו-`ImGui_ImplSDL3_*` (`imgui_impl_sdl3.cpp`). ה-UI של ImGui (`launcher.mm`, `menu.mm`) צריך להיות מחוץ ל-build של ה-PS5 או עטוף ב-`#ifdef`; `menu_render`/`menu_handle_event`/`menu_apply_window_requests` יצטרכו stubs מצד הפורט.

## משתני סביבה (הפורט יכול לקבוע ב-`setenv` לפני `SDL_Init`)
| משתנה | ברירת מחדל | משמעות |
|---|---|---|
| `SDL3_PS5_WINDOW` | `3840x2160` | גודל החלון המדווח לפני שיש surface. |
| `SDL3_PS5_QUIT_FILE` | `/download0/za-sdl3.quit` | קובץ שמייצר `SDL_EVENT_QUIT`; ריק = מבוטל. |
| `SDL3_PS5_TOUCHPAD_BUTTON` | `touchpad` | `back` → לחיצת touchpad הופכת ל-`SDL_GAMEPAD_BUTTON_BACK` (כפתור "−" של Switch בבינדינג ברירת המחדל) אם Create לא מדווח. |
| `SDL3_PS5_AUDIO_DEVICE_FRAMES` | `1024` | ה-period שמדווח ל-`SDL_GetAudioDeviceFormat` (256–8192). |
| `SDL3_PS5_THREAD_STACK_KB` | `2048` | stack ל-`SDL_CreateThread`. |
| `SDL3_PS5_PREF_ROOT` | `/download0` | בסיס ל-`SDL_GetPrefPath`. |

## פערים ידועים ומה לא אומת

1. **לא רץ על הקונסולה.** רק קומפילציה (וסמלים) נבדקו. הרצפים עצמם (scePad, sceAudioOut, VK_KHR_display) הם אלה של r3/r4, אבל השילוב — מיקסר עם כמה streams, resampling, אירועים מה-pad ב-`ui_run` — טרם הורץ.
2. **`vkCreateInstance` ושות' של ה-runtime** — RADV מייצא רק `vk_icd*`; הפורט צריך loader סטטי (מחוץ ל-shim). ה-shim עצמו לא תלוי בכך.
3. **Create / PS / Mute** — `scePad` לא מדווח PS (INTERCEPTED) ו-Mute; Create (0x1) מוצהר ב-ProsperoEden אבל לא נצפה ב-r4. לכן `BACK` (Switch "−") ו-`GUIDE` עלולים לא להגיע; `SDL3_PS5_TOUCHPAD_BUTTON=back` כפתרון.
4. **`sceKernelGetDirectMemorySize`, `scePthreadGetaffinity`** — מוצהרים לפי `ps5platform/kernel.h` ומתועדים ב-PROBE.md של הפלטפורמה; לא הורצו ב-probe שלנו. שניהם עם fallback (12288 MiB; sysconf/13).
5. **עלות השעון** — `clock_gettime` ≈ 20 µs (syscall) לפי מסמכי PS5_Vulkan; `SDL_GetTicksNS` נקרא ב-37 מקומות ב-runtime (כולל פרופיילינג per-draw). אם זה יורגש — `-DSDL3_PS5_TSC_TICKS=1` (לא אומת).
6. **אירועי joystick** (`SDL_EVENT_JOYSTICK_*`) לא נוצרים (SDL מייצר אותם לצד אירועי gamepad); `input.c` משתמש רק בהם לסינון `input_user_blocked`.
7. **`SDL_PollEvent` עושה pump רק כשהתור ריק** (SDL עושה pump בכל קריאה) — חוסך קריאות `scePadReadState`; ההבדל לא נראה ל-runtime.
8. **אודיו**: latency ≈ 2 grains (10.7 ms) + התור של ה-runtime; `SDL_GetAudioStreamQueued` לא כולל את ה-grain שבדרך לפורט (כמו SDL). ערוץ 6 מקופל בלי LFE lowpass. callbacks לא נתמכים (ה-runtime לא משתמש).
9. **PNG** — stubs שנכשלים; HD packs, אייקון וצילומי מסך לא יעבדו עד שיהיה libpng/stb בפורט.
10. **מבני `SDL_Event` שהושמטו** (display, kdevice, mdevice, jball, jhat, jbattery, gtouchpad, gsensor, adevice, cdevice, sensor, tfinger, pen*, render, drop, clipboard) — ה-runtime לא נוגע בהם; הגודל 128 בתים ו-offset 0 של כל חבר נשמרים (`SDL_COMPILE_TIME_ASSERT`).
11. **headers חסרים ב-SDK**: כל הפרוטוטיפים של Sony מוצהרים ידנית; שינוי pin של ה-SDK לא משפיע עליהם, אבל שינוי ב-ABI של `scePadReadState` (120 בתים) ישבור את ה-`_Static_assert`.

# vk-loader — "loader" סטטי של Vulkan ל-PS5 עבור ה-runtime של Pokémon Legends Z-A Recomp

תאריך: 27.10.2026. מצב: **קומפילציה בלבד** (compile-only) עם ה-toolchain של `vk-probe` עברה (`build-check.sh`, ארבעה שלבים, `-std=c11 -O2 -Wall -Wextra -Werror`): כל 108 הסמלים `vk*` שה-runtime מייבא (מתוך `undefined.tsv` של ביקורת הקומפילציה) מוגדרים ב-`vk_loader.o` (`llvm-nm`), הארכיון של RADV מספק את שתי נקודות הכניסה של ה-ICD שה-loader מייבא ואינו מגדיר אף סמל שה-loader מגדיר (אין כפילות בקישור). **לא הורץ על הקונסולה** ולא נבדק בקישור מלא של title.

## הבעיה

ה-runtime (`runtime/nvn/vulkan/*.c`, `imgui_glue.cpp`), ה-backend של ImGui (`imgui_impl_vulkan.cpp`) ו-`device.c` קוראים לפקודות Vulkan כסמלים ישירים — `vkCreateInstance`, `vkCmdDraw`, `vkQueuePresentKHR` … — כמו שעושים במחשב מול `vulkan-1.dll`/`libvulkan.so`. בקונסולה אין loader של Khronos: ארכיון RADV (`libvulkan_radeon.ps5.a`, 9,169 סמלים) מייצא **רק** `vk_icdGetInstanceProcAddr`, `vk_icdGetPhysicalDeviceProcAddr` ו-`vk_icdNegotiateLoaderICDInterfaceVersion` (נבדק ב-`llvm-nm`; `build-check.sh` שלב 4), וכל השאר `radv_*`/`vk_*` פנימיים. ה-probe של r3/r4 עבד דרך `vk_icdGetInstanceProcAddr`/`vkGetDeviceProcAddr` בלבד. ה-loader הזה נותן ל-runtime את הסמלים שהוא מצפה להם, בלי לגעת בקוד שלו.

## מבנה

```
port/vk-loader/
├── gen_vk_loader.py        המחולל: מנתח את vulkan_core.h של PS5_Mesa ואת required-symbols.txt ומוציא vk_loader.c (דטרמיניסטי)
├── required-symbols.txt    108 השמות vk* שה-runtime מייבא (השורות MISSING של undefined.tsv), עם מקור
├── vk_loader.c             הקובץ המחולל: 290 trampolines + טבלת מצביעים + הלוגיקה של הטעינה (אין לערוך ידנית)
├── build-check.sh          בדיקה ב-WSL: חילול-מחדש והשוואה, קומפילציה, nm מול הרשימות, בדיקת הארכיון
└── README.md               המסמך הזה
```

## איך זה עובד

`vk_loader.c` מגדיר לכל פקודה פונקציה בעלת **בדיוק** החתימה של ה-header (הוא נכלל עם הפרוטוטיפים דולקים, ולכן כל סטייה בחתימה היא שגיאת קומפילציה), שקופצת דרך `vkl_fn[VKL_vkXxx]`:

| רמה | פקודות | מאיפה המצביע | מתי |
|---|---|---|---|
| global | `vkCreateInstance`, `vkEnumerateInstanceVersion`, `vkEnumerateInstanceExtensionProperties`, `vkEnumerateInstanceLayerProperties` | `vk_icdGetInstanceProcAddr(NULL, name)` | בקריאה הגלובלית הראשונה (עצל) — **עובדות לפני שיש instance**; קודם `vk_icdNegotiateLoaderICDInterfaceVersion(5)` כפי ש-ICD בגרסה 2+ מצפה |
| `vkGetInstanceProcAddr` | — | מועבר ישירות ל-`vk_icdGetInstanceProcAddr` (כמו ב-probe וב-SDL3 shim); לשמות של ה-wrappers של ה-loader עצמו (`vkCreateInstance`, `vkCreateDevice`, `vkDestroy*`, `vkGetDeviceProcAddr`, `vkEnumerateInstance*`) מחזיר אותם, כדי שגם מי שמשיג אותם במצביע יעבור דרך הטבלה | תמיד |
| instance (`VkInstance`/`VkPhysicalDevice` ראשון; גם `vkGetDeviceProcAddr`) | 50 | `vk_icdGetInstanceProcAddr(instance, name)` | אחרי הצלחת `vkCreateInstance` |
| device (`VkDevice`/`VkQueue`/`VkCommandBuffer` ראשון) | 235 | `vkGetDeviceProcAddr(device, name)` (המסלול המהיר, ישירות לפונקציה של RADV) | אחרי הצלחת `vkCreateDevice`; ב-`vkCreateInstance` הן כבר קיבלו את ה-trampolines של Mesa (`vk_icdGetInstanceProcAddr(instance, …)` מחזיר לפקודות device את `vk_tramp_*` שמנתב דרך טבלת ה-dispatch של ה-device) — וזה ה-**fallback** כש-`vkGetDeviceProcAddr` מחזיר NULL |

התנהגויות שהועתקו מה-loader של Khronos: `vkCreateInstance` עם `enabledLayerCount > 0` מחזיר `VK_ERROR_LAYER_NOT_PRESENT` בלי לפנות ל-ICD (אין שכבות בקונסולה; `device.c` מנסה שוב בלי ולידציה — זה בדיוק המסלול שלו), `vkEnumerateInstanceVersion` בלי פקודה ב-ICD = 1.0, `vkDestroyInstance`/`vkDestroyDevice` עם NULL = no-op ומאפסים את הטבלה (device → חזרה ל-trampolines של ה-instance; instance → הכול NULL). מצביע NULL בזמן קריאה: `vkl_missing` כותב ל-stderr איזו פקודה, באיזו רמה ומה מצב ה-instance/device — ו-`abort()` (במקום קפיצה ל-NULL בלי הסבר).

לוג: `[vk-loader] instance %p: N of M … resolved`, `device %p: N direct, N through instance-level trampolines, N not provided`; שמות שה-runtime קורא (`required`) שלא נפתרו נרשמים תמיד; `ZA_VK_LOADER_TRACE=1` מדפיס את כל השמות. `za_vk_loader_report()` (לא שם של Vulkan) מדפיס את מצב כל הטבלה. ה-title חייב לקרוא `ps5_klog_capture_stderr(...)` כדי שזה יגיע ל-klog (כמו ה-shim).

**הנחות**: instance אחד ו-device אחד (ה-runtime יוצר בדיוק אחד מכל סוג; השני היה דורס את הטבלה), ו-`vkCreateInstance` נקרא דרך הסמל הזה (לא דרך מצביע מ-`SDL_Vulkan_GetVkGetInstanceProcAddr` — אבל גם מצביע ששואלים מ-`vkGetInstanceProcAddr` של ה-loader מחזיר את ה-wrapper שלו).

## מקור ה-ABI והסמלים

- **headers**: `/home/tomer/ps5-za-native/PS5_Mesa/include/vulkan/{vulkan.h,vulkan_core.h,vk_icd.h}` — `VK_HEADER_VERSION 354` (Vulkan 1.4.354), אותם headers שמהם נבנה ארכיון RADV. ה-sha256 של `vulkan_core.h` רשום בראש `vk_loader.c`; `build-check.sh` מחולל מחדש ומשווה, כך ששינוי header = כישלון קולני + חילול מחדש. `vk_icd.h` מצהיר את `vk_icdGetInstanceProcAddr`/`vk_icdNegotiateLoaderICDInterfaceVersion` (הפרוטוטיפ המדויק של ה-ICD).
- **הפקודות**: מה-sections של ה-header (`#define VK_VERSION_1_x 1`, `#define VK_KHR_xxx 1`): כל הליבה 1.0–1.3 (215; ה-runtime יוצר instance עם `apiVersion = VK_API_VERSION_1_3`, ו-Mesa פותר פקודות ליבה רק עד גרסת האפליקציה — 1.4 לא נכלל כי לא ייפתר), ו-ההרחבות `VK_KHR_surface`, `VK_KHR_swapchain`, `VK_KHR_display`, `VK_KHR_display_swapchain` (ה-surface של ה-shim), `VK_KHR_get_physical_device_properties2`, `VK_KHR_get_surface_capabilities2`, `VK_KHR_dynamic_rendering`, `VK_KHR_synchronization2` (ה-aliases KHR של `vkCmdPipelineBarrier2`/`vkQueueSubmit2`/`vkCmdWriteTimestamp2` לצד שמות הליבה 1.3 — `device.c` טוען אותם ב-`vkGetDeviceProcAddr` לפי `g_vkc.api`), `VK_KHR_timeline_semaphore`, `VK_EXT_debug_utils` (רק עם `LARECOMP_VK_VALIDATION`), `VK_EXT_external_memory_host` (`exec.c`: ייבוא חלון הזיכרון של האורח), `VK_EXT_extended_dynamic_state`/`2`, `VK_EXT_device_fault`, `VK_NV_device_diagnostic_checkpoints` — סה"כ 290. הרשימה ב-`DEFAULT_SECTIONS` של המחולל (`--sections` מחליף).
- **הנדרש**: `required-symbols.txt` = 108 השורות `vk* MISSING` של `pokeza-recomp-ps5/build/ps5-audit/undefined.tsv` (ענף `ps5`, commit `4cefcdf`): 2 global (`vkCreateInstance`, `vkGetInstanceProcAddr`), 15 instance, 91 device — כולן ליבה 1.0/1.1 + `KHR_surface`/`KHR_swapchain`. המחולל נכשל אם שם נדרש חסר ב-header או מחוץ ל-sections; `build-check.sh` משווה גם ל-`undefined.tsv` עצמו כשהוא נגיש (`POKEZA_RECOMP`).
- **מה ה-runtime משיג במצביע ולא כסמל** (ולכן לא חייב להיות כאן, אבל נמצא): `VK_DEVICE_COMMANDS_12/13` של `vk.h` (`vkGetSemaphoreCounterValue`, `vkWaitSemaphores`, `vkCmdBeginRendering`…, עם הסיומות KHR/EXT ב-1.2), `vkGetMemoryHostPointerPropertiesEXT`, `vkGetDeviceFaultInfoEXT`, `vkCmdSetCheckpointNV`/`vkGetQueueCheckpointDataNV`, `vkCreateDebugUtilsMessengerEXT`; VMA (`vma.cpp`: `VMA_STATIC_VULKAN_FUNCTIONS 0`, `VMA_DYNAMIC_VULKAN_FUNCTIONS 1`) מקבל את `vkGetInstanceProcAddr`/`vkGetDeviceProcAddr` **של ה-loader** (`device.c:326`) ושואל דרכם — שניהם מעבירים ל-ICD.

## איך בודקים (WSL)

```
wsl -d Ubuntu -- bash "/mnt/c/.../Pokemon-ZA-Native-Port/port/vk-loader/build-check.sh"
```

השלבים: (1) `gen_vk_loader.py` מחולל ל-`/tmp/vk-loader-build/` ומשווה בייט-בבייט ל-`vk_loader.c` (python3 של WSL, `-I`); (2) קומפילציה עם `sh $PS5_VULKAN/tooling/prospero-clang18` (`PS5_CLANG=/usr/bin/clang-21`, ה-sysroot של ה-payload SDK) `-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -I $PS5_MESA/include`; (3) `llvm-nm`: כל שם ב-`required-symbols.txt` וב-`undefined.tsv` מוגדר (`T`), ו-`vk_loader.o` לא מייבא אף `vk[A-Z]*` (הייבוא שלו: `vk_icdGetInstanceProcAddr`, `vk_icdNegotiateLoaderICDInterfaceVersion`, ו-libc: `abort fflush fprintf fwrite getenv strcmp __stderrp`); (4) הארכיון מגדיר את שתי נקודות ה-ICD ואין חיתוך בין הסמלים שהוא מגדיר לאלה של ה-loader. תוצאה אחרונה: 290 פקודות, 108/108 נדרשות, אובייקט 132 KB.

חילול מחדש (אחרי שינוי header/רשימה/sections):
```
python3 -I gen_vk_loader.py --vulkan-include /home/tomer/ps5-za-native/PS5_Mesa/include --required required-symbols.txt --out vk_loader.c [--list]
```

## שילוב ב-title

1. לקמפל את `vk_loader.c` עם `-I $PS5_MESA/include` (אותו header כמו ה-runtime) ולקשר יחד עם האובייקטים של ה-runtime, **לפני** ארכיון RADV בשורת הקישור (`tools/ps5/link-title.sh`: `ZA_PS5_EXTRA_INPUTS`); ה-recipe `radv-link.sh` כבר מכניס את הארכיון כולו ואת builtins של clang.
2. ה-SDL3 shim (`port/sdl3-shim`) לא תלוי ב-loader (פונה ל-`vk_icdGetInstanceProcAddr` לבד) — אבל ה-surface שהוא יוצר, ה-instance שה-runtime יוצר כאן וה-device — כולם אותו ICD, אז המצביעים תואמים.
3. סדר הפעולות שה-runtime כבר מקיים: `vkCreateInstance` (device.c) → `vkEnumeratePhysicalDevices`… → `vkCreateDevice` → `vkGetDeviceProcAddr` ל-`VK_DEVICE_COMMANDS` ול-VMA. אם מישהו יקרא לפקודת device לפני `vkCreateDevice` — ה-trampoline של Mesa (רמת instance) יעבוד; לפני `vkCreateInstance` — `vkl_missing` + abort עם הודעה.
4. **אין** `vkEnumerateInstanceExtensionProperties` ב-undefined.tsv — ה-shim קורא לזה דרך ה-ICD; הסמל בכל זאת מוגדר (כמו שאר הגלובליות).

## פערים ומה לא אומת

1. **לא רץ על הקונסולה.** הרצפים (`vk_icdGetInstanceProcAddr(NULL/instance, …)`, `vkGetDeviceProcAddr`) הם של ה-probe r3/r4 שרץ על 13.60, אבל הקובץ הזה עצמו לא נקשר ולא הורץ.
2. **פקודה של הרחבת device שלא נתמכת**: `vk_icdGetInstanceProcAddr(instance, "vkCmdSetCheckpointNV")` ב-Mesa מחזיר trampoline גם כש-RADV לא מממש את ההרחבה (הבדיקה `!device || …` בטבלת ה-dispatch), ואז קריאה דרכו קופצת ל-NULL **בתוך Mesa**. ה-loader שומר את ה-trampoline הזה כ-fallback (לפי ההגדרה) ומדווח ב-`vkCreateDevice` על כל שם נדרש שנפל ל-fallback; ה-runtime עצמו קורא כסמל רק לליבה ול-`KHR_surface`/`KHR_swapchain` שתמיד מופעלות, ואת ההרחבות הוא שואל במצביע ובודק NULL.
3. **גרסת הליבה**: Mesa פותר פקודות ליבה לפי `apiVersion` של `VkApplicationInfo` (1.3 ב-`device.c`), לא לפי גרסת ה-driver (1.4.354). פקודות 1.4 לא נכללו; אם ה-runtime יעבור ל-1.4 — להוסיף `VK_VERSION_1_4` ל-sections.
4. **instance/device יחידים** ולא thread-safe במילוי הטבלה (ה-runtime ממלא מה-render thread לפני שאר ה-threads רצים; כתיבות מצביע רגילות).
5. **`-Wcast-function-type`**: ההמרות מ-`PFN_vkVoidFunction` הן אותן המרות שה-probe עושה עם אותם דגלים (`-Wall -Wextra -Werror`) — עברו גם כאן.
6. `vk_icdGetPhysicalDeviceProcAddr` (גרסת interface 4) לא בשימוש — אין הרחבות physical-device לא מוכרות ל-loader הזה.

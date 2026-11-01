# shaderc-cache — תחליף "מטמון בלבד" ל-shaderc עבור ה-runtime של Pokémon Legends Z-A Recomp ב-PS5

תאריך: 27.10.2026. מצב: **קומפילציה בלבד** (compile-only) עם ה-toolchain של `vk-probe` עברה (`build-check.sh`, שישה שלבים, `-std=c11 -O2 -Wall -Wextra -Werror`): כל 12 הסמלים `shaderc_*` שה-runtime מייבא (`undefined.tsv`) מוגדרים ב-`shaderc_cache.o`; `shaderc_cache.c` מתקמפל גם מול ה-header **האמיתי** של shaderc 2025.4 (חתימות זהות); `runtime/nvn/vulkan/shaders.c` עובר `-fsyntax-only` מול ה-header שכאן; ובדיקת **זהות ה-hash** מול `src_hash` של ה-runtime (הטקסט נגזר מ-`shaders.c` בזמן הבדיקה ומקומפל במחשב) — 72 השוואות, 0 הבדלים. **לא הורץ על הקונסולה.**

## מה זה

ל-PS5 אין glslang/shaderc (פורט מלא: `analysis/ps5-runtime-compile-gaps.md` §3.5ב, 2–3 ימים). `shaders.c` של ה-runtime כבר עובד עם מטמון דיסק: `vk_glsl_to_spirv` מחשב `src_hash(src, stage)`, מחפש `cache/spirv/<hash>.spv` (יחסית ל-cwd = שורש הנתונים), ורק בהחמצה קורא ל-`shaderc_compile_into_spv`. המימוש כאן מממש את ה-API של shaderc **בלי קומפיילר**: `shaderc_compile_into_spv` מחשב את **אותו hash** ומחפש את `<hash>.spv` ברשימת תיקיות (ברירת מחדל `cache/spirv` — המטמון של ה-runtime עצמו — ואז `/app0/cache/spirv`, מטמון שנשלח עם ה-title); נמצא → תוצאה מוצלחת עם ה-SPIR-V; לא נמצא → תוצאת **שגיאת קומפילציה** עם הודעה שמציינת את שם השיידר, ה-stage, ה-hash וגרסת Vulkan, וה-GLSL נכתב לתיקיית "החסרים" כדי שאפשר יהיה לקמפל אותו במחשב. ה-runtime מטפל בשני המקרים כרגיל: הצלחה → `no_contraction` (ל-vertex; אידמפוטנטי על קובץ שכבר עבר אותו) → `cache_store` לתוך `cache/spirv` שלו; כישלון → `LOG("[shader] <name>: GLSL compile failed:\n<message>\n<source>")` ו-NULL (pipeline בלי השיידר; `vk_builtin_shader` → FATAL).

```
port/shaderc-cache/
├── include/shaderc/        shaderc.h, env.h, status.h, visibility.h — תת-קבוצה של shaderc 2025.4 באותם ערכים וחתימות
├── shaderc_cache.c         המימוש: 12 פונקציות ה-API + za_shaderc_cache_hash + za_shaderc_cache_report
├── symbols.txt             12 השמות, מתוך undefined.tsv
├── test/consumer.c         שימוש כמו shaders.c (C11 וגם C++20), compile-only
├── test/hash-parity.c      בדיקה במחשב: src_hash של ה-runtime (נגזר מ-shaders.c) == za_shaderc_cache_hash
├── tools/compile-missing.sh  במחשב: מקמפל את החסרים (glslc / glslangValidator, -O0, vulkan1.3) ל-<hash>.spv
├── build-check.sh          בדיקה ב-WSL
└── README.md
```

## ה-hash (חייב להיות זהה ל-`shaders.c`)

```
h = (0xcbf29ce484222325 ^ stage) + 3        // + 3 = גרסת העיבוד-לאחר (no_contraction) של shaders.c
if (api < VK_API_VERSION_1_3) h ^= api << 32 // SPIR-V 1.5 ל-Vulkan 1.2: קבצים אחרים
FNV-1a על בתי ה-GLSL (כ-uint8_t)             // שם הקובץ: cache/spirv/%016llx.spv
```

- `stage` = מספר ה-STAGE של ה-runtime (`runtime/nvn/maxwell/shader.h`): vertex 0, fragment 1, geometry 2, tess-ctrl 3, tess-eval 4, compute 5; `shaders.c` ממפה `shaderc_vertex_shader`→0, `shaderc_fragment_shader`→1, אחרת compute (5) — וכאן ההפך, לכל ששת הסוגים.
- `api` = `g_vkc.api` של ה-runtime (1.3; 1.2 תחת `LARECOMP_VK_COMPAT`). ה-runtime מעביר אותו דרך `shaderc_compile_options_set_target_env(o, shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_3 | _1_2)` — הערכים של `shaderc_env_version_vulkan_*` **שווים** ל-`VK_API_VERSION_*` (`(1<<22)|(x<<12)`), לכן אותו XOR.
- רמת האופטימיזציה (`shaderc_optimization_level_zero`, או `performance` עם `LARECOMP_VK_OPT`) **אינה** חלק מה-hash — גם לא ב-`shaders.c`. מטמון שנוצר במחשב עם `LARECOMP_VK_OPT=1` ייראה תקף וייתן SPIR-V אחר; ליצור את המטמון **בלי** `LARECOMP_VK_OPT`.
- אם `shaders.c` ישנה את הקבוע `+ 3` או את התבנית — לעדכן `ZSC_HASH_VERSION` כאן; `test/hash-parity.c` נכשל אם הם מתפצלים (הוא מקמפל את `src_hash` **מתוך `shaders.c` של ה-clone**).

## **חשוב: ה-GLSL מכיל את בסיס/גודל חלון הזיכרון של האורח**

`maxwell/translate.c` (שורות 784, 1701) כותב לתוך ה-GLSL של כל טעינה/אחסון גלובלי את המספרים `maxwell_gmem_base` ו-`maxwell_gmem_size`:
`{ ulong ga = <addr> - 0x<gmem_base>ul; bool ok = ga < 0x<gmem_size>ul; … }`. ב-`exec.c` (`translate_program`, `build_compute`): `maxwell_gmem_base = gwin_base + lo`, `maxwell_gmem_size = len`, כאשר `gwin_base` = בסיס חלון האורח (`GUEST_LO = 0x7000000000`, `runtime/rt.h`; ב-PS5 שמור בדיוק שם — `platform/ps5.c`, הוכח ב-r2) ו-`gmem_window_get` נותן `lo = 0, len = gwin_max` (כל החלון) **או**, כשיש חלון מוגבל, `lo = (gwin_max − window) & ~0xFFFFF`, `len = gwin_max − lo`. ה-`window` = `LARECOMP_VK_GMEM_WINDOW` (MB) אם הוגדר, אחרת **256 MB ב-GPU שמדווח `INTEGRATED` ו-0 (הכול) ב-DISCRETE**; `gwin_max` = גודל ה-heap שהמשחק קבע / האזור הפיזי.

לכן ה-hash של כל שיידר מתורגם תלוי ב-**(א)** כתובת הבסיס של החלון, **(ב)** `LARECOMP_VK_GMEM_WINDOW` / סוג ה-GPU, **(ג)** `gwin_max`. מטמון שנוצר במחשב תקף לקונסולה **רק** אם שלושתם שווים: אותו `GUEST_LO` (קבוע משותף, כל עוד ה-PC לא נבנה עם בסיס אחר), אותו `LARECOMP_VK_GMEM_WINDOW` מפורש (**לקבוע אותו במפורש בשני הצדדים** — למשל `0`, כי לא אומת האם RADV ב-PS5 מדווח `INTEGRATED` או `DISCRETE`; השורה `[vk] using … (dedicated|integrated …)` בלוג אומרת), ואותו גודל heap/אזור. אחרת כל שיידר מתורגם יחמיץ (השיידרים המובנים — present/clear/SMAA/FSR — לא מכילים את זה וייפגעו רק משינוי `api`). אותה גרסת runtime בשני הצדדים (`+ 3`, תבנית ה-GLSL של `translate.c`).

## ה-API (החוזה: מה ש-`shaders.c` קורא)

| פונקציה | התנהגות |
|---|---|
| `shaderc_compiler_initialize` | אובייקט סטטי יחיד, לעולם לא NULL (`vk_shaders_init` → FATAL אחרת); בפעם הראשונה (`pthread_once`) קורא את משתני הסביבה ורושם ללוג את התיקיות |
| `shaderc_compiler_release` | no-op |
| `shaderc_compile_options_initialize` / `_release` | מבנה קטן (`target`, `version`, `level`); ברירת מחדל Vulkan 1.3 (ה-runtime תמיד קובע) |
| `shaderc_compile_options_set_target_env` | שומר `target` + `version` (= ה-`api` של ה-hash); target שאינו Vulkan → `configuration_error` בקומפילציה |
| `shaderc_compile_options_set_optimization_level` | נשמר בלבד (ראו למעלה) |
| `shaderc_compile_into_spv` | hash → חיפוש `<dir>/<hash>.spv` בכל תיקייה (אימות כמו `cache_load`: > 20 בתים, כפולה של 4, magic `0x07230203`) → `success` + בתים; אחרת `compilation_error` + הודעה + כתיבת ה-GLSL ל-`<missing>/<hash>.<vert|frag|comp|geom|tesc|tese>` ושורה ב-`<missing>/index.txt` (`hash stage vulkanX.Y name`); סוג שיידר לא מוכר → `invalid_stage`; `compiler`/`entry_point_name` לא בשימוש |
| `shaderc_result_get_compilation_status` / `_get_length` (בתים) / `_get_bytes` / `_get_error_message` / `_release` | כמו shaderc; NULL result → `null_result_object` / 0 / NULL / "null result object" |
| `za_shaderc_cache_hash(src, len, stage, api)`, `za_shaderc_cache_report()` | לא שמות של shaderc: ה-hash לבדיקות, ודו"ח hits/misses/dumped ללוג |

ההודעה בהחמצה (מגיעה ללוג דרך `shaders.c`, לפני ה-GLSL המלא): `no precompiled SPIR-V for <name> (stage frag, hash 0123…, Vulkan 1.3, miss N): looked for <hash>.spv in 2 cache dir(s): cache/spirv; the GLSL was written to cache/spirv-missing/<hash>.frag - compile it on the PC into cache/spirv/<hash>.spv (…)`.

Thread-safety: ה-runtime מקמפל מכמה threads (קומפיילר per-thread, options ו-result per-call) — כאן אין מצב משותף מלבד האתחול (`pthread_once`) ומונים אטומיים.

## משתני סביבה

| משתנה | ברירת מחדל | משמעות |
|---|---|---|
| `ZA_SHADERC_CACHE_DIRS` | `cache/spirv:/app0/cache/spirv` | תיקיות לחיפוש, מופרדות ב-`:` (עד 8), לפי הסדר; יחסיות ל-cwd (שורש הנתונים של ה-runtime) |
| `ZA_SHADERC_MISSING_DIR` | `cache/spirv-missing` (fallback `/download0/za-spirv-missing` כשאי אפשר ליצור/לכתוב) | לאן נכתב ה-GLSL של החמצות |
| `ZA_SHADERC_TRACE` | כבוי | `1` = שורת לוג לכל hit |

## תהליך העבודה: יצירת המטמון במחשב והשלמת החסרים

1. להריץ את **אותה גרסת runtime** במחשב (Windows/Linux build של ה-clone), עם `LARECOMP_VK_GMEM_WINDOW` זהה לזה שייקבע בקונסולה ובלי `LARECOMP_VK_OPT`, ולשחק את המסלולים הרלוונטיים; `cache/spirv/` של אותה ריצה (528–599 שיידרים לסשן לפי §3.5א) הוא המטמון. להעתיק אותו ל-`/app0/cache/spirv` (בחבילה) או ל-`cache/spirv` בשורש הנתונים בקונסולה.
2. בקונסולה: החמצות נרשמות ל-`cache/spirv-missing/` (ולקלוג). להעתיק את התיקייה למחשב ולהריץ `bash tools/compile-missing.sh <missing> <cache/spirv> [--target-env vulkan1.3]` (glslc או glslangValidator, `-O0`; `index.txt` אומר לאיזו גרסת Vulkan כל קובץ נדרש), או פשוט להריץ שוב במחשב מסלול שמייצר אותם. ה-SPIR-V של glslc/glslang שקול למה ש-shaderc (שעוטף את אותו glslang) היה נותן ב-`optimization_level_zero`; את `no_contraction` ה-runtime מחיל בעצמו בטעינה.

## איך בודקים (WSL)

```
wsl -d Ubuntu -- bash "/mnt/c/.../Pokemon-ZA-Native-Port/port/shaderc-cache/build-check.sh"
```

(1) כל header ב-`include/shaderc` לבדו, C11 ו-C++20; (2) `shaderc_cache.c` עם `sh $PS5_VULKAN/tooling/prospero-clang18` (`PS5_CLANG=/usr/bin/clang-21`, sysroot של ה-payload SDK) `-std=c11 -O2 -Wall -Wextra -Werror` מול `include/shaderc`, ושוב מול `C:/msys64/ucrt64/include/shaderc` האמיתי (`ZA_MSYS2_INC`); (3) `test/consumer.c` C11/C++20; (4) `llvm-nm`: הייבוא של ה-consumer, `symbols.txt` ו-`undefined.tsv` ⊆ המוגדר; הייבוא של האובייקט: libc + `pthread_once` + `mkdir`/`stat` בלבד; (5) `runtime/nvn/vulkan/shaders.c` `-fsyntax-only` מול `include/shaderc` (עם headers של Vulkan מ-PS5_Mesa ו-VMA מ-MSYS2); (6) `hash-parity`: `src_hash` נגזר מ-`shaders.c` ב-awk, מקומפל **במחשב** (`HOST_CC`, ברירת מחדל `/usr/bin/clang-21` ל-Linux) עם `shaderc_cache.c` ו-`test/hash-parity.c` ורץ — 6 מקורות × 6 stages × 2 גרסאות API. תיקיית עבודה `/tmp/shaderc-cache-build` (`SHADERC_CACHE_WORK`); `RUNTIME_CHECK=skip` מדלג על 5–6.

## שילוב ב-title

לקמפל את ה-runtime (לפחות `shaders.c`) עם `-I port/shaderc-cache/include` **לפני** ה-include של MSYS2 (או בלעדיו — ה-header כאן מספיק ל-`shaders.c`), לקמפל `shaderc_cache.c` באותו אופן ולהוסיף לקישור (`ZA_PS5_EXTRA_INPUTS` של `tools/ps5/link-title.sh`). `vk_shaders_init` של ה-runtime נשאר כמו שהוא (מצליח). כשיהיה shaderc אמיתי ל-PS5 — להחליף את האובייקט; ה-header כאן תואם לאמיתי בתת-הקבוצה הזאת.

## פערים ומה לא אומת

1. **לא רץ על הקונסולה**; תקינות המטמון מהמחשב מול הקונסולה (בסיס/גודל חלון, `gwin_max`, סוג ה-GPU של RADV ב-PS5) לא אומתה — ראו הסעיף המודגש.
2. **אין קומפילציה בכלל**: כל שיידר חדש (ציוד/אזור/אפקט שלא נראה במחשב) מחמיץ עד שיקומפל במחשב; השיידרים המובנים (present/clear/texcopy/depthcopy/post/SMAA/EASU/RCAS) **חייבים** להיות במטמון — `vk_builtin_shader` הוא FATAL בלעדיהם.
3. ה-runtime קורא ל-shaderc רק אחרי שהוא עצמו לא מצא את הקובץ ב-`cache/spirv`; התיקייה הראשונה בברירת המחדל זהה — החיפוש הכפול שם מיותר אבל זול (fopen שנכשל).
4. ההודעה והלוג כותבים ל-stderr (`[shaderc-cache] …`); ה-title חייב `ps5_klog_capture_stderr(...)` כדי שיגיעו ל-klog.
5. שינוי `src_hash` ב-`shaders.c` (הקבוע `+ 3`, ה-XOR של ה-API) חייב להשתקף כאן; `build-check.sh` תופס זאת רק כשה-clone נגיש (`POKEZA_RECOMP`).

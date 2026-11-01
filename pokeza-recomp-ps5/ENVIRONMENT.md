# סביבת הניסוי לפורט ה-PS5 — Pokémon Legends Z-A Recomp, גרסה 2.0.2 + DLC "Mega Dimension"

תאריך: 27.10.2026. זהו ענף `ps5` של clone נפרד (`pokeza-recomp-ps5`) של
`https://github.com/Hexveil404/PokeZ-ARecomp.git` ב-commit `4d82d8998adb75036c27f476e8d8f7e737bed36a`
(tag `v0.1.4`), כפי שהוא ב-`research/pokeza-recomp` — שלא שונה ולא ישונה. כל שינוי לפורט נעשה **כאן בלבד**.

סימון: **[מוכח]** = אומת בקובץ/בלוג/בגיבוב; **[הנחה]** = מסקנה שטרם אומתה.

## 0. מה הסביבה הזו, ומה היא לא

- clone עם `core.autocrlf=false` ו-`core.eol=lf`: קובצי המקור, ה-Makefile וסקריפטי ה-bash הם LF **[מוכח]** (ה-checkout
  של `research/pokeza-recomp` הוא CRLF ולכן לא התאים ל-`make`/bash). חריגים שנשארו בכוונה: 42 קובצי פרויקט של
  Visual Studio תחת `third_party/imgui/` (CRLF לפי ה-`.gitattributes` של imgui עצמו) ו-15 קבצים שמאוחסנים ב-git
  כ-CRLF במקור (`third_party/ooz/*`, `third_party/smaa/*`, `tools/za/{auto-win.sh,bisect_o1.py,keyboard_font.py}`,
  `tools/zaimport/zaimport.csproj`) — אינם קלט לבנייה.
- ה-commit הראשון בענף מחיל את patch הזיהוי של 2.0.2 (5 שורות: `runtime/main.c`, `runtime/ui/launcher.mm`, תווית
  `v0.1.4-local202`) — זהה בית-בבית (מודולו CR) ל-`update-2.0.2-20261025/runtime-source` ול-
  `deliverables/Pokemon-ZA-PC-2.0.2-MegaDimension-r1-20261025/source-changes/local-2.0.2-recognition.patch` **[מוכח: diff ריק]**.
- **אין כאן נתוני משחק, קוד מחולל, שמירות או מפתחות** — רק הפניות (סעיפים 1–3). `.gitignore` של הפרויקט מונע הכנסה
  של `input/`, `extracted/`, `generated*/`, `save/`, `build/`.
- שורשי ההפניה: `research/` = `C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/`,
  `deliverables/` = `.../ns2jb-nintendo-switch-2-switch-1/deliverables/`. מסמכי הניתוח: `Pokemon-ZA-Native-Port/analysis/`.

## 1. הסט הנעול: 2.0.2 + DLC (קריאה בלבד; לא מועתק לכאן)

מקור: `research/pokeza-pc/update-2.0.2-20261025/game/` (25.10.2026). עותק זהה בחבילה
`deliverables/Pokemon-ZA-PC-2.0.2-MegaDimension-r1-20261025/game/`. ה-SHA-256 להלן הם אלה שרשומים ב-`SHA256.json`
של החבילה וב-`Launch.ps1` שלה (שנועל 4 מהם); **ב-27.10.2026 חושבו מחדש על העותק ב-`research/` והתאימו כולם** **[מוכח]**.

| קובץ (יחסית ל-`game/`) | גודל (B) | SHA-256 | הערה |
|---|---:|---|---|
| `exefs/main` | 33,970,422 | `2308530d73b7fea60bb845ad57d9b1f10d3ff213f89c01f73627dc8224f43ef9` | build ID `b1f12fd919eae86ab8a978317677e64bce443d1f` (8 בתים ב-offset 0x40); נעול ב-Launch.ps1 |
| `exefs/sdk` | 6,247,676 | `0449487b457490afae879c08d6a90dd28295eaaa5c55677089a46b13991afbab` | זהה ל-sdk של 1.0.0 |
| `exefs/rtld` | 8,550 | `714ead44bbd81ccba54509399a5dca59c1a24e068b384292f6755829f1e9d523` | לא נטען על ידי ה-runtime |
| `exefs/main.npdm` | 1,700 | `9960d4579cb8f8aedfac6e51d8452e31c5acdd0e39308cfc0d4a42955d956058` | עדיפות/מחסנית/system resource |
| `romfs.bin` | 5,989,104,840 | `0ad824b860ebbd8dc512000a5789917241ef047f1ecea223344c3022a2377e90` | בסיס + עדכון ממוזגים (zaimport: "update applied, 1 DLC") |
| `aoc/0100f43008c45002.bin` | 604 | `f3810c027bef4e7e8709ca1f1b5c7e7713ff499900269cd12df8a88064db0d1a` | RomFS של ה-DLC (stub: `keyfile.dat` ריק; תוכן ה-DLC ב-romfs.bin); נעול ב-Launch.ps1 |
| `lasgame.dll` | 372,428,288 | `a3e0da9a4f07e82c5db23f7eec90982b25edc0e7f240e73503a65e5f510b78fe` | **ייחוס בלבד** — DLL של Windows; ל-PS5 נבנית ספרייה משלו מהקוד המחולל (סעיף 2); נעול ב-Launch.ps1 |
| `lasgame.dll.id` | 18 | `7c4ce73cce6d6e27487e7b50cd43a8d38bb5a2fb14a99c0415caa8dac866e041` | תוכן `7b03da558e0b6144` = ABI id של ה-generator, **זהה ל-1.0.0** — אינו מבדיל גרסאות; הנעילה האמיתית היא ה-SHA של `exefs/main`; נעול ב-Launch.ps1 |

מכולות (לא נדרשות בזמן ריצה) **[מוכח מהתיעוד]**: עדכון `update-2.0.2-20261025/input/Pokemon Legends Z-A v2.0.2.nsp`
(2,122,054,733 B, SHA `a061160c…`, title `0100F43008C44800`, NACP "2.0.2"); DLC
`C:/Users/Tomer/Downloads/Pokemon Legends Z-A [DLC Mega Dimension Full] [0100F43008C45002][v0].nsp` (121,040 B, SHA `39df38f9…`).

**על ה-PS5** (ראו `runtime/platform/ps5.c`): הקבצים יושבים בחלק הקריא-בלבד של ה-title, `/app0/game/{exefs,romfs.bin,aoc}`
(`main()` מקבל את הנתיב כארגומנט; מוחלט → `realpath`), והחלק הכתיב ב-`/download0/zarecomp/` (`LARECOMP_DATA_ROOT`
שמוגדר ב-`plat_init`: `save/`, `cache/`, `larecomp.ini`, `lasrecomp.log`). **[הנחה]** עד שייבדק על הקונסולה.

## 2. הקוד המחולל של 2.0.2 — REFERENCE ONLY (לא מועתק; ~1 GB של C)

`research/pokeza-pc/update-2.0.2-20261025/aot/` **[מוכח: `build-result.json`, `inputs.json`, `gen_main.log`]**:

- `main/`: 1,206 קבצים (`main_000.c … main_1204.c` + `main_table.c`), 898,760,063 B, 230,332 פונקציות, 1,205 chunks (167 s חילול).
- `sdk/`: 205 קבצים, 120,478,288 B.
- 1,412 יחידות קומפילציה (1,252 ב-`-O1`, 160 ב-`-O0` — מדיניות "giant functions" של `runtime/gamebuild.c`),
  16 jobs, 2026-10-25 16:08:42 → 16:23:35 UTC (14:53 דקות, zig cc ל-x86-64 Windows), אובייקטים 442 MB.
- generator revision `cf910d1315fff0ead7d782c9d752a075a9b777f7`, ABI `7b03da558e0b6144`, דגלים
  `-O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label -fvisibility=hidden -Iruntime -D_FILE_OFFSET_BITS=64 -march=x86-64-v3`.
- `gen_main.log`: `main: not Link's Awakening (main build b1f12fd919eae86a): no game patches` → **ה-hook של קצב הפריימים לא הוחל** (סעיף 4).
- `aot/source/` = snapshot של 14 קובצי ה-ABI של ה-generator — זהה לקבצים בעץ הזה (`runtime/cpu.h`, `simd.h`, `simd_fp.h`,
  `gamelib.h`, `tools/gamelib_entry.c`, `hle/hle_symbols.txt`, `tools/*.py`) **[מוכח: diff ריק, לפי `game-version-inventory.md`]**.

שימוש מכאן: ב-`PLATFORM=ps5` ה-Makefile קורא את הקוד המחולל מ-`AOT_DIR` (ברירת המחדל: הנתיב שלמעלה; `GEN=<נתיב>` הוא אותו
כפתור בשמו הישן), האובייקטים ב-`build/ps5/gen/` (`B=build/ps5` כברירת מחדל, כדי שדבר לא ייכנס ל-`aot/`) והארכיון `build/ps5/liblasgame.a`:
`make PLATFORM=ps5 -j16 ps5-gamelib` (ב-WSL; מדפיס סיכום של זמן, מספר היחידות בכל רמת אופטימיזציה וגודל האובייקטים; `ps5-gen-objs` —
אובייקטים בלבד; `GEN_ONLY="main/main_655 sdk/sdk_090"` לניסוי על יחידות בודדות). מדיניות ה-`-O0` לפונקציות הענקיות של ה-build במחשב
(`runtime/gamebuild.c`, `cold_giant`: יחידה של פונקציה אחת עם יותר מ-1,000 תוויות שאינה ב-`HOT_GIANTS`) מיושמת על ידי
`tools/ps5/giants.sh`, שקורא את הכלל מ-`gamebuild.c` עצמו וכותב `build/ps5/gen/giants.mk` (ה-Makefile כולל אותו ובונה אותו תחילה):
על הסט של 2.0.2 — **160 יחידות ב-`-O0`, בדיוק כמו `build-result.json` של המחשב** **[מוכח]**. `GENOPT` כברירת מחדל `-O1 -DGUEST_VOLATILE`
(כמו ה-build המוכח של 2.0.2). חלופה שוות-ערך **[הנחה]**: חילול מחדש עם `make gen EXEFS=<…>/game/exefs`
(`python -X utf8`, venv עם unicorn/capstone/lz4). ב-PS5 הספרייה היא archive סטטי (`liblasgame.a`) שנקשר לתוך ה-eboot —
title אינו יכול לטעון ספרייה בזמן ריצה (`LARECOMP_STATIC_GAMELIB`, `runtime/gamelib.c`). ה-`GAMELIB_ID` שלה (`cfe9edff99caed63`) שונה מ-`7b03…`
(הדגלים שונים: ללא `-fPIC`/`_FILE_OFFSET_BITS`, עם `-DZA_PS5`) — תקין, כל עוד ה-runtime והספרייה נבנים יחד.

## 3. שמירות 2.0.x (מיקומים בלבד; לעולם לא מועתקות לכאן)

פורמט 2.0.x = 3,186,611 B (1.0.0 = 3,093,124 B; ההמרה חד-כיוונית 1.0.0 → 2.0.x) **[מוכח]**:

- `deliverables/Pokemon-ZA-PC-2.0.2-MegaDimension-r1-20261025/save-city/save_0/main` — 3,186,611 B, SHA
  `f5c64116c3fa0c39b407272b0646212c7bb27fdbb5bfbbf3601e232ecebd3c27` (תבנית Tepig של Quick-Start 1.0.0 שהומרה על ידי 2.0.2; עיר, Mission 03).
- `research/pokeza-pc/update-2.0.2-20261025/runs/01-city/save/save_0/main` (אותה שמירה, בריצת ה-harness).
- `deliverables/…/save-test/save_0/main` — **פורמט 1.0.0** (3,093,124 B, SHA `b0bf729f…`), הועתק מהחבילה הקודמת; 2.0.2 ממיר אותו בשמירה הראשונה.
- פרופילי המשתמש (`%LOCALAPPDATA%\ZA-Randomizer-Manager\profiles\…`) ושמירות ProsperoEden — לא בשימוש בסביבה זו.

ב-PS5: `/download0/zarecomp/save/save_0/main` (`LARECOMP_SAVE_DIR` / `save` ב-data root) **[הנחה]**.

## 4. מה ידוע ולא ידוע על 2.0.2 (הסיכונים של הנעילה)

- **אין hook לקצב פריימים ל-build `b1f12fd9…`**: `tools/patches.py` (`ZA_BUILDS`) מכיר רק את 1.0.0 (`7222e13ecf6adb32`) ו-2.0.0
  (`8a1c86c437394b69`); `_za_frame_cfg` לא הוחל ב-aot של 2.0.2 → **30 fps קבוע** (ההגדרה `fps60` לא משפיעה). חישוב הכתובת
  ל-2.0.2 הוא משימה נפרדת (`local-support-changes.json: frame_patch=false, initial_fps=30`).
- `HOT_GIANTS[]` ב-`runtime/gamebuild.c` הן כתובות 2.0.0; 6 מהן (`f_70000064b0`, `f_700001ee3c`, `f_7000028b70`, `f_7000035f20`,
  `f_7000048720`, `f_700009f010` — `main_001/005/007/011/013/027`) קיימות באותו שם גם ב-2.0.2 ונשארות ב-`-O1`; 11 האחרות לא נמצאו,
  ולכן 160 (ולא 166) יחידות ב-`-O0` — כמו ב-build במחשב **[מוכח: `tools/ps5/giants.sh`]**. ביצועים בלבד, לא תקינות.
- **הראיות מהמחשב דלות**: 4 ריצות קצרות בלבד (`verification.json`): `01-city` 156 s, `02-city-save` 111 s, `03-save-write` 101 s,
  `04-updated-save-reload` 71 s (ועוד `00-runtime-loader`, 5 s, מסך פתיחה) — כולן הסתיימו בתקציב ה-harness בלי fatal markers;
  עיר ב-29.92 fps ממוצע (`city-timing.json`). ה-DLC נרשם וה-RomFS שלו נפתח על ידי המשחק (`dlc_registered`,
  `dlc_storage_opened_by_game`), אך **הקמפיין של ה-DLC לא נבדק** (`dlc_campaign_playtested=false`); אין ראיות ל-intro/קרב ב-2.0.2
  (בניגוד ל-50 ריצות של 1.0.0).
- ה-runtime של 2.0.2 = upstream `4d82d89` + 5 שורות; אין שינויים נוספים ב-`runtime-source` **[מוכח: `diff -rq`]**.
- לנעילה הזו נבחרה 2.0.2 בניגוד להמלצת `game-version-inventory.md` (1.0.0) — ההחלטה של המשתמש; ההשלכה: שמירות ההתקדמות
  האמיתיות (פורמט 2.0.x) ייטענו, אך האימות במחשב ל-A/B יהיה מול 4 הריצות הנ"ל בלבד.

## 5. הפינים בצד ה-PS5 (WSL, `/home/tomer/ps5-za-native/`) **[מוכח: `vk-probe/dist/BUILD-INFO.txt` ו-`PROVENANCE.txt`]**

| רכיב | פין |
|---|---|
| קושחה / title מוכח | 13.60; `PPSA91760` (r4: eboot `135151946d…`, 24,497,189 B; נטען, Vulkan/pad/audio עובדים) |
| PS5 payload SDK (fork של mihawk-99) | `b83202be73e930050e00de0f1b4d9ec46c0391bf` — `PS5_Vulkan/.deps/native/ps5-payload-sdk` (`.ps5-sdk-revision`) |
| PS5_Vulkan | `f410e67a0241b3e8edcdbcd2a9b285dfc4a412ed` |
| PS5_Mesa (RADV, Vulkan 1.4.354) | `1ba9874f478657ccf6da72ce55f0260164cc0bd0` |
| clang | Ubuntu clang 21.1.8, `/usr/bin/clang-21`, דרך `PS5_Vulkan/tooling/prospero-clang18` (`PS5_CLANG=/usr/bin/clang-21`, `PS5_PAYLOAD_SDK=<sdk>`) |
| RADV archive | `PS5_Vulkan/.deps/native/radv-release/lib/libvulkan_radeon.ps5.a`, 273,681,414 B, SHA-256 `0124a06411718e2145fdafc0d54654e9a16a49bbbdc70e9f400a0a433bf08aed` |
| `sce_module/libc.prx` | SHA-256 `e6ff45d16adf687855cc3b33b0c8a4132b6504360b221e0a34c7e99fb3ba0036` |
| תלויות שאין להן build ל-PS5 (עדיין) | SDL3 (ה-runtime צריך 3.4+: `SDL_LoadPNG`), shaderc, FFmpeg — ראו `analysis/ps5-runtime-compile-gaps.md` |

headers אמיתיים לבדיקות קומפילציה בצד המחשב (לא לקישור): SDL3 3.4.18 ב-`research/pokeza-pc/runtime-opt-r1/SDL3-3.4.18/x86_64-w64-mingw32/include`
(אלה ששימשו לבניית ה-exe של 2.0.2); shaderc / FFmpeg (avcodec 62, avformat 62, avutil 60, swscale 9) / VMA ב-`C:/msys64/ucrt64/include`;
Vulkan — של PS5_Mesa (`PS5_Mesa/include`). `tools/ps5/compile-runtime.sh` מאתר אותם לבד.

## 6. מה יש בענף `ps5` (מעבר ל-patch הזיהוי)

- `Makefile`: `make PLATFORM=ps5` (עקיפה מפורשת של זיהוי `uname`): clang 21 ביעד `x86_64-sie-ps5` עם הדגלים המוכחים
  (`-femulated-tls -fno-plt -fno-stack-protector -fdenormal-fp-math=ieee`), `-march=x86-64-v3` (ה-Zen 2 של ה-PS5 הוא superset),
  `-DZA_PS5`, ספריית משחק סטטית, קישור דרך `tools/ps5/link-title.sh`.
- `runtime/platform/ps5.c` + `ps5_compat.h`: 20 פונקציות `platform.h` על הפרימיטיבים שהוכחו ב-r2/r4 (reserve של חלון האורח,
  direct memory לפי אזורים, mprotect, pthread, clock_gettime, קבצים ב-/download0), עם `TODO verify` בכל מקום שלא נבדק על הקונסולה.
- אתרי ה-`#ifdef` של Linux/Windows/macOS הורחבו ב-`ZA_PS5` (sections של ELF, `plat_terminate`, data root, מחסניות host, fibers, gamelib סטטי).
- פערי ה-libc של הדוח (סעיף 3.2 שם) סגורים בצד ה-runtime: `ps5_compat.h` מנתב `opendir…seekdir` ו-`atof`/`strtod`/`strtof` למימושי
  ה-title ב-`ps5.c` (`telldir`/`seekdir` על ה-API של ה-SDK, parser ב-C locale — נקודה עשרונית ריקה בקונסולה), `gamelib.c` שואל cpuid
  ישירות (לא `__cpu_model`), `link`/`fork`/`execvp` אינם מיובאים, ו-`runtime/platform/ps5_fiber.c` מחליף הקשרים ל-fibers ב-asm
  (`ZA_PS5_ASM_FIBERS`, דולק כברירת מחדל; `-DZA_PS5_ASM_FIBERS=0` חוזר ל-ucontext) עם בדיקה עצמית ב-`plat_init` — **[הנחה]** עד שה-probe
  יריץ אותה על הקונסולה. `tools/ps5/link-title.sh` מאמת את קשירת `arc4random` ושות' ל-`ps5_*` ונכשל אם ה-PIE עדיין מייבא אחד מהם.
- `tools/ps5/compile-runtime.sh` — ביקורת קומפילציה (runtime בלבד) ב-WSL: `wsl -d Ubuntu -- bash "/mnt/c/.../pokeza-recomp-ps5/tools/ps5/compile-runtime.sh"`;
  `tools/ps5/time-generated.sh` — מדידת זמן קומפילציה לקבצים מחוללים נבחרים; `tools/ps5/giants.sh` — סיווג היחידות הענקיות ל-`-O0`
  (סעיף 2); `third_party/ps5-stubs/` — stubs מסומנים ל-headers חסרים.
- הדוח: `Pokemon-ZA-Native-Port/analysis/ps5-runtime-compile-gaps.md`.

## 7. כללי העבודה בסביבה

1. לא נוגעים ב-`research/pokeza-recomp`, ב-`research/pokeza-pc` וב-`/home/tomer/ps5-za-native` (SDK, Mesa, Vulkan); משתמשים בהם לקריאה.
2. לא מעתיקים נתוני משחק, שמירות או קוד מחולל לתוך ה-clone; `GEN`/`EXEFS` מצביעים החוצה.
3. commits רק בענף `ps5` של ה-clone הזה; כל הודעת commit מסתיימת בשורה `Co-Authored-By: Claude <noreply@anthropic.com>`.
4. פקודות WSL מורצות מ-PowerShell (`wsl -d Ubuntu -- bash /mnt/c/<script>.sh`), לא מ-Git Bash.

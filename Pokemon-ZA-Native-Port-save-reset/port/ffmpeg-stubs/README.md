# ffmpeg-stubs — תחליף-כישלון ל-24 פונקציות FFmpeg שה-runtime של Pokémon Legends Z-A Recomp קורא

תאריך: 27.10.2026. מצב: **קומפילציה בלבד** (compile-only) עם ה-toolchain של `vk-probe` עברה (`build-check.sh`, חמישה שלבים, `-std=c11 -O2 -Wall -Wextra -Werror` מול ה-headers האמיתיים של FFmpeg): כל 24 הסמלים `av_*`/`avcodec_*`/`avformat_*`/`sws_*` שה-runtime מייבא (`undefined.tsv` של ביקורת הקומפילציה) מוגדרים ב-`ffmpeg_stubs.o`, ו-`runtime/hle/movie.c` עובר `-fsyntax-only` מול אותם headers. **לא הורץ על הקונסולה.**

## מה זה

אין FFmpeg ל-PS5 בבנייה הזאת (ראו `analysis/ps5-runtime-compile-gaps.md` §3.6: פורט מינימלי של FFmpeg 7/8 — `--disable-everything --enable-decoder=vp8,vp9,vorbis --enable-demuxer=matroska` — הוא עבודה נפרדת, 1–2 ימים). עד אז ה-stubs כאן נותנים לקישור את 24 הסמלים ומחזירים **כישלון בדרך של FFmpeg** (קוד `AVERROR` שלילי, `*ps = NULL`), כך שמסלולי הכישלון שכבר קיימים ב-runtime הם שרצים: ניגון סרטונים מדווח "לא זמין" ולא קורס. הפונקציות הטהורות (`av_rescale_q`, `av_gettime_relative`) ממומשות באמת; הקצאה/שחרור עובדים על אובייקטים אמיתיים (מאופסים), כי `movie.c` כותב ל-`ctx->thread_count` **לפני** `avcodec_open2` — stub שמחזיר NULL שם היה קורס.

```
port/ffmpeg-stubs/
├── ffmpeg_stubs.c      24 הפונקציות, עם החתימות של ה-headers האמיתיים (הקובץ מכיל אותם ולכן כל סטייה = שגיאת קומפילציה)
├── symbols.txt         24 השמות, מתוך undefined.tsv
├── test/consumer.c     צרכן שקורא לכולן כמו movie.c ו-launcher.mm (C11 וגם C++20 — launcher.mm הוא C++), compile-only
├── build-check.sh      בדיקה ב-WSL
└── README.md
```

## מקור החתימות

ה-headers ש-`tools/ps5/compile-runtime.sh` של ה-clone מצא ב-`C:/msys64/ucrt64/include` (רק תת-התיקיות `libavcodec`, `libavformat`, `libavutil`, `libswscale` בקישורים סימבוליים — התיקייה כולה מכילה את libc של mingw ואסור שתהיה ב-include path): חבילת MSYS2 `mingw-w64-ucrt-x86_64-ffmpeg-8.0.1-2`, כלומר **FFmpeg 8.0.1**: libavcodec 62.11.100, libavformat 62.3.100, libavutil 60.8.100, libswscale 9.1.100 (לא 7.x — ב-7.1 avcodec הוא 61; הביקורת רשמה "avcodec 62"). ההבדל לא נוגע ל-24 הפונקציות האלה (חתימותיהן זהות ב-7.x ו-8.x), אבל `sizeof` של `AVCodecContext`/`AVFrame`/`AVPacket` שה-stubs מקצים הוא של 8.0.1 — זה בסדר כי אין כאן FFmpeg אחר שיקרא את המבנים. `swresample`: ה-runtime לא מייבא אף `swr_*` (0 ב-undefined.tsv) — אין כאן stubs לזה.

`build-check.sh` מכליל את ה-headers ב-`-isystem` (האזהרות שלהם לא נכנסות ל-`-Werror`; של הקוד שלנו כן). `ZA_MSYS2_INC` מצביע למיקום אחר של אותם headers.

## הטבלה

| פונקציה | מחזירה | הערה |
|---|---|---|
| `avformat_open_input` | `AVERROR(ENOSYS)`, `*ps = NULL` | כמו FFmpeg בכישלון; שורת לוג `[ffmpeg-stubs] avformat_open_input: not available … <path>` (20 הראשונות) |
| `avformat_find_stream_info` | `AVERROR(ENOSYS)` | |
| `av_find_best_stream` | `AVERROR_STREAM_NOT_FOUND`, `*decoder_ret = NULL` | |
| `av_read_frame` | `AVERROR_EOF` | → `ex_fill` מסמן `eof` |
| `av_seek_frame` | `AVERROR(ENOSYS)` | |
| `avformat_close_input` | — | `*s = NULL`; מעולם לא נוצר context |
| `avcodec_find_decoder` | `NULL` | אין מפענחים |
| `avcodec_alloc_context3` | `AVCodecContext` מאופס (`calloc`) | ראו למעלה: `thread_count` נכתב לפניו |
| `avcodec_free_context` | — | `free`, `*avctx = NULL` |
| `avcodec_parameters_to_context` | `AVERROR(ENOSYS)` | |
| `avcodec_open2` | `AVERROR_DECODER_NOT_FOUND` | שורת לוג |
| `avcodec_send_packet` | `AVERROR(EINVAL)` | "codec לא פתוח" כמו FFmpeg |
| `avcodec_receive_frame` | `AVERROR_EOF` | אף פריים לעולם |
| `av_packet_alloc` / `av_packet_free` / `av_packet_unref` | `AVPacket` אמיתי, מאופס לברירות המחדל של FFmpeg (`pts/dts = AV_NOPTS_VALUE`, `pos = -1`) | `unref` מאפס את השדות ש-`movie.c` מציב (`data`, `size`, `pts` לתוך המאגר שלו) — אין refcount |
| `av_frame_alloc` / `av_frame_free` | `AVFrame` אמיתי (`format = -1`, timestamps = `AV_NOPTS_VALUE`) | |
| `av_frame_clone` | `NULL` | לא נגיש (אין פריימים) |
| `av_gettime_relative` | מיקרו-שניות מ-`CLOCK_MONOTONIC` | **ממומש** |
| `av_rescale_q` | `a*bq/cq` ב-128 ביט, עיגול `AV_ROUND_NEAR_INF`, `AV_NOPTS_VALUE` עובר כמו שהוא, `cq=0` → `INT64_MIN` | **ממומש** (מייבא `__divti3` — ב-builtins של clang וגם ב-`libSceLibcInternal`, שניהם ברצפט הקישור) |
| `sws_getContext` | `NULL` | שורת לוג |
| `sws_scale` | `AVERROR(EINVAL)`, היעד לא נגוע | `movie.c` קורא לזה עם ה-NULL שקיבל — רק אם היה מפענח מוגדר, שאי אפשר כאן |
| `sws_freeContext` | — | |

## אילו מסלולים ב-runtime מושפעים

- **`runtime/hle/movie.c` — ה-HLE של `movie::Extractor`** (slot 15, `ex_set_data_source`, שורה 213): `avformat_open_input` נכשל → `LOG("[movie] cannot open <romfs>/.../x.webm")`, המשחק מקבל **1** (כישלון) ו-`e->fmt` נשאר NULL. כל שאר ה-slots כבר מוגנים: `GetTrackCount` → 0 מסלולים, `GetTrackConfig`/`SeekTo` → 1, `GetSampleTrack`/`Read`/`GetSampleTime` → `ex_fill` מקבל `AVERROR_EOF` ומסמן `eof` → 1, `GetCachedDuration` → `INT64_MAX/4`, ה-destructor ו-`movie_reset` בודקים `fmt`/`ctx` לפני השחרור. המסלול של דילוג הפתיחה (`skippable`, `av_gettime_relative`) נדלק רק אחרי פתיחה מוצלחת.
- **`movie::Decoder`** (`dec_configure`, שורה 461): `m->codecpar` מגיע רק מ-`ex_get_track_config` של extractor פתוח → תמיד NULL כאן → `"[movie] Configure without codec parameters"`, מחזיר 1; שום פונקציית FFmpeg לא נקראת. אם בכל זאת (דרך אחרת) — `avcodec_alloc_context3` מחזיר אובייקט אמיתי ו-`avcodec_open2` נכשל: `"[movie] cannot open decoder"`, 1.
- **מה המשחק רואה**: הסרטונים (`rom:/region_common/movie/opening.webm` בהפעלה הראשונה, `title.webm` במסך הפתיחה, וכל `.webm` אחר) לא ינוגנו — ה-player של המשחק מקבל כישלון מ-`SetDataSource`. איך המשחק מגיב לכישלון הזה **לא אומת** (צריך ריצה); ב-52 לוגים של המחשב לא נצפתה פעילות `[movie]` ב-Z-A בכלל (`analysis/pokeza-runtime-platform.md` §7), כך שייתכן שהמסלול לא נדרש לפריים ראשון.
- **`runtime/ui/launcher.mm` `load_background`** (שורה 853): `avformat_open_input` נכשל → חוזר מיד, אין thumbnail של `title.webm` ברקע (`g_bg = 0`). מסך הפתיחה (launcher) ממילא מדולג ל-Z-A (`main.c:243-271`).
- אין שינוי בקוד ה-runtime: החלופה (`-DLARECOMP_NO_FFMPEG`, §3.6) הייתה דורשת 28 stubs ב-`movie.c` עצמו; כאן ה-`#include`-ים של FFmpeg נשארים וה-headers נדרשים בקומפילציה (כמו היום).

## איך בודקים (WSL)

```
wsl -d Ubuntu -- bash "/mnt/c/.../Pokemon-ZA-Native-Port/port/ffmpeg-stubs/build-check.sh"
```

(1) ה-headers נמצאים ומקושרים ל-staging; (2) `ffmpeg_stubs.c` ב-`sh $PS5_VULKAN/tooling/prospero-clang18` (`PS5_CLANG=/usr/bin/clang-21`, sysroot של ה-payload SDK) `-std=c11 -O2 -Wall -Wextra -Werror`; (3) `test/consumer.c` כ-C11 וכ-C++20; (4) `llvm-nm`: הייבוא של ה-consumer, `symbols.txt` ו-`undefined.tsv` (כשנגיש, `POKEZA_RECOMP`) ⊆ המוגדר; הייבוא של ה-stubs עצמם: `calloc clock_gettime fflush fprintf free __divti3 __stderrp` בלבד; (5) `runtime/hle/movie.c` `-fsyntax-only` עם דגלי ה-runtime (`-DZA_PS5 -DLARECOMP_STATIC_GAMELIB`). תיקיית עבודה `/tmp/ffmpeg-stubs-build` (`FFMPEG_STUBS_WORK`).

## שילוב ב-title

לקמפל `ffmpeg_stubs.c` עם אותו include path של FFmpeg שבו מקומפל `movie.c` (`PS5_DEPS_INC` של ה-Makefile / ה-staging של `compile-runtime.sh`) ולהוסיף את האובייקט לקישור (`ZA_PS5_EXTRA_INPUTS` של `tools/ps5/link-title.sh`). כשיהיה FFmpeg אמיתי ל-PS5 — להסיר את האובייקט הזה; אין מאקרו/דגל אחר לשנות.

## פערים ומה לא אומת

1. **לא רץ על הקונסולה**; תגובת המשחק לכישלון `SetDataSource` לא נבדקה (ב-PC נראה רק מסלול "cannot open" לקובץ חסר).
2. `sws_scale` עם context NULL לא כותב ליעד; במסלול הבלתי-נגיש (`dec_get_output_buffer` במצב texture) `d->rgba` היה עולה ל-GPU לא מאותחל.
3. הגדלים של `AVCodecContext`/`AVFrame`/`AVPacket` הם של headers 8.0.1; החלפה ל-headers של גרסה אחרת (7.x) מקמפלת ועובדת, אבל `build-check.sh` מדווח את הגרסה שמצא.
4. `__int128` ב-`av_rescale_q` → `__divti3` (מסופק; §B14 בביקורת מכסה את `__udivti3` של ה-runtime באותו אופן).

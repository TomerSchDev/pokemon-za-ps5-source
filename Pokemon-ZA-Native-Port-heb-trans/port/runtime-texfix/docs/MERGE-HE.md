# MERGE-HE.md — שילוב r28a-play עם חבילת המודלים שנשלחת לקונסולה

לכלי השני של Tomer, ששולח עכשיו חבילת מודלים ל־PPSA91762. r28a-play כולל שני תיקונים ב־**eboot.bin בלבד**:
1. **texfix** — תיקון קריסת הטקסטורות (ארבעה אובייקטים של ה־runtime).
2. **dexcount** — משימות "תפוס N פוקימונים חדשים" סופרות גם מינים מ־Mega Dimension (יחידות משחק + אובייקט אחד).

## מקרה 1: חבילת המודלים משנה רק נתונים (mods / romfs / קבצים ב־app0 או ב־data)
- **קחו את `PPSA91762/eboot.bin` מהחבילה הזו כמו שהוא.** אין תלות בין שני התיקונים לבין קובצי נתונים.
- SHA-256 של ה־eboot: ראו `SHA256SUMS.txt` כאן. אחרי ההעלאה: readback והשוואה.
- אין לשנות קובצי אפשרויות (`perf-r24-options.txt`, `performance-options.txt` = `optimized`, `slot-depth-options.txt`), שמירות או `active.json`.
- אם חבילת המודלים מחליפה את `eboot.bin` משלה **רק כדי לסמן גרסה**: לא לעשות זאת. ה־eboot של r28a הוא הבסיס, ונתונים נטענים ממנו כרגיל.

## מקרה 2: חבילת המודלים נושאת eboot משלה (שינויים בקוד)
אז צריך לבנות eboot אחד שמכיל את שלושת השינויים. **הבסיס הוא העץ הסופי של r28a**, ועליו מוסיפים את שינויי המודלים. אין לבנות מ־r28-play ולהוסיף את שני התיקונים "ביד".

### העץ
- `/home/tomer/ps5-za-native/r28a-play-final-20261030` — **קריאה בלבד.** לכל בנייה נוספת מעתיקים אותו לעץ חדש.
- בתוכו: `source/` (ה־runtime עם texfix כבר מוחל, ואובייקטיו ב־`source/build/ps5/rt/`), `r28a/objects/` (אובייקטי ה־title של r28), `r28a/liblasgame-r28.a` (ארכיון r28 המקורי), `rando-dexcount/` (הפלט של dexcount: הארכיון המתוקן ו־`za_dexcount.o`), `rando-dexcount-src/` (צילום של הסקריפט והמקורות שרצו), ו־`r28a/evidence/`.

### מה כל סקריפט משנה (כדי לשלב בלי לנחש)

**A. texfix — `port/runtime-texfix/apply-runtime-texfix.py <tree>/source/runtime`**
- עורך 5 קבצים ב־`runtime/`: `nvn/nvn.h`, `nvn/objects.c`, `nvn/vulkan/textures.c`, `nvn/vulkan/exec.c`, `nvn/vulkan/device.c`; מוסיף 4 headers: `nvn/za_texguard_api_r28a.h`, `nvn/za_texquarantine_r28a.h`, `nvn/vulkan/za_texlive_r28a.h`, `nvn/vulkan/za_texguard_r28a.h`.
- **האובייקטים שמשתנים:** `build/ps5/rt/nvn/objects.o`, `build/ps5/rt/nvn/vulkan/textures.o`, `build/ps5/rt/nvn/vulkan/exec.o`, `build/ps5/rt/nvn/vulkan/device.o`. אלה כבר מקומפלים בעץ הסופי; אם חבילת המודלים נוגעת באחד מחמשת קובצי המקור האלה, מחילים את `apply-runtime-texfix.py` **אחרי** שינויי המודלים (הוא עובד בעוגני טקסט מדויקים ומסרב אם עוגן חסר) ומקמפלים מחדש את ארבעת האובייקטים בפקודת ה־runtime של r26 (ראו `build-r28a-candidate.sh`, הפונקציה `cc_rt`; הבקרה בשלב 2 שם מוכיחה שהפקודה נכונה).
- לא נוגע בארכיון המשחק, באובייקטי ה־title או בשורת הקישור.

**B. dexcount — `port/rando-dexcount/ps5/apply-r28a.sh <tree> <out>`** (להריץ מצילום של התיקייה, לא מהתיקייה החיה; הסקריפט המאושר: SHA-256 ‏`ea70cc667b10c61157eb268189b0df61c5f2f4106f6ee5c6125bdc57c84313ad`)
- פרטים מלאים ב־`port/rando-dexcount/ps5/HANDOFF.json` ובמניפסט `<out>/dexcount-r28a-manifest.json`.
- **הארכיון:** עותק של `liblasgame-r28.a` ‏(`a86c3134…`) שבו הוחלפו **שני** חברים: `main_310.o` ‏(`a0abfe00…` → `9fe2a40b…`) ו־`main_261.o` ‏(`862beb9d…` → `39c40977…`); התוצאה `<out>/liblasgame-r28-dexcount.a` = ‏`1f0c586e721f93b80cd86b9b3675a18d95bca338952b5b3d01e7518bcc9a41cc`; 1410 החברים האחרים זהים בית־בבית, אותו סדר.
- **אובייקט חדש:** `<out>/za_dexcount.o` ‏(`207e7a1ad5d8f26a8d95673b7d6414df6af99f36201168c412a5c4df9b9ce06f`), שמתווסף לסוף `ZA_PS5_EXTRA_INPUTS`. הוא מייבא `__stderrp fflush fputs sceKernelDebugOutText snprintf` — כולם כבר imports של r28, ולכן רשימת ה־imports של ה־PIE לא משתנה (זו דרישה: `verify-r28a.py image` נכשל אם היא משתנה).
- היחידות המתוקנות מייבאות רק `za_dexcount_combine` / `za_dexcount_display` / `za_dexcount_extra_enabled`.
- לא נוגע ב־runtime, באובייקטי ה־title או בתפריט.
- **לא להשתמש** ב־`/home/tomer/ps5-za-native/rando-dexcount-r28a-20261030` (הפלט שהסוכן השני הכין מול המועמד) או ב־`…-superseded-noklog` כקלט לבנייה משולבת: בונים מחדש מצילום, ומשווים את ה־SHA של הארכיון והאובייקט לערכים שלמעלה (העץ הסופי `rando-dexcount/` נבנה בדיוק כך).

**C. שינויי המודלים (של הכלי השני)** — לפי מה שהם משנים:
- **יחידות משחק נוספות:** להחליף אותן בעותק של `liblasgame-r28-dexcount.a` (לא של `liblasgame-r28.a`), בדיוק כמו ש־apply-r28a.sh עושה: `llvm-ar rcs <copy>.a <unit>.o`, ואז `compare_ar.py` עם רשימת החברים המותרים של **שני** השינויים.
- **אם הם נוגעים באותה יחידה שה־dexcount מתקן** (למשל `main_310` או `main_261`): אי אפשר להחליף פעמיים. צריך להחיל את שני ה־patchers על אותו `.c` ברצף (`prepare-dexcount-hooks.py` של dexcount עובד על ה־`.c` המקורי ב־`aot/main` ומייצר `gen/<unit>.c`; את ה־patcher של המודלים מריצים על הפלט הזה, או להפך), ולקמפל פעם אחת. לבדוק עם `llvm-nm -u` שהיחידה מייבאת את הסמלים של שני הצדדים.
- **אובייקטי title / runtime חדשים:** להוסיף ל־`ZA_PS5_EXTRA_INPUTS` אחרי `za_dexcount.o`.
- **קובצי runtime:** ראו A.

### פקודות הבנייה המשולבת (WSL)
```
cand=/home/tomer/ps5-za-native/r28a-play-final-20261030        # קריאה בלבד
work=/home/tomer/ps5-za-native/r28a-models-$(date +%Y%m%d)     # חדש
cp -a "$cand/source" "$work/source"; cp -a "$cand/port" "$work/port"; cp -a "$cand/inc" "$work/inc"
mkdir -p "$work/r28a"; cp -a "$cand/r28a/objects" "$work/r28a/objects"; cp "$cand/r28a/liblasgame-r28.a" "$work/r28a/"
# 1. (רק אם המודלים משנים קובצי runtime) שינויי המודלים ב-$work/source/runtime, ואז:
python3 port/runtime-texfix/apply-runtime-texfix.py "$work/source/runtime"      # מדלג על מה שכבר מוחל
#    וקומפילציה מחדש של האובייקטים שנגעו בהם (cc_rt של build-r28a-candidate.sh)
# 2. dexcount מצילום:
snap=$work/rando-dexcount-src; mkdir -p "$snap/ps5"
cp port/rando-dexcount/ps5/{apply-r28a.sh,compare_ar.py} "$snap/ps5/"
cp port/rando-dexcount/{za_dexcount.c,za_dexcount.h,prepare-dexcount-hooks.py} "$snap/"
BASE_ARCHIVE="$work/r28a/liblasgame-r28.a" bash "$snap/ps5/apply-r28a.sh" "$work" "$work/rando-dexcount"
# 3. יחידות המשחק של המודלים -> עותק של $work/rando-dexcount/liblasgame-r28-dexcount.a (llvm-ar rcs), compare_ar.py
# 4. קישור: הרשימה והשורה של r28a, בתוספת האובייקטים החדשים
mapfile -t rt < "$cand/r28a/evidence/runtime-inputs.txt"
runtime=(); for p in "${rt[@]}"; do runtime+=("$work/source/$p"); done
extra=$(cat "$cand/r28a/evidence/link-inputs.txt"); extra=${extra//"$cand/r28a/objects/"/"$work/r28a/objects/"}
export ZA_PS5_EXTRA_INPUTS="$extra <אובייקטי המודלים>"      # (link-inputs.txt של r28a כבר כולל את za_dexcount.o)
cd "$work/source" && bash tools/ps5/link-title.sh "$work/r28a/llvm-pie.elf" "${runtime[@]}" "<הארכיון המשולב>.a"
# 5. בדיקות התמונה: port/runtime-texfix/verify-r28a.py image <r28 PIE> <PIE חדש> <evidence> <project>
#    ואז llvm-strip, ps5-native-tool link / self --sign כמו בשלב 4 של build-r28a-final.sh
```
- `link-inputs.txt` של העץ הסופי מכיל כבר את `--wrap=…` ואת `za_dexcount.o` בסופו; `runtime-inputs.txt` הוא רשימת 64 אובייקטי ה־runtime.
- **אימות חובה לפני התקנה:** ה־imports זהים ל־r28 (או שינויים צפויים ומתועדים), הרישום (`verify-registration.py`) נשמר, ו־`verify-r28a.py image` עובר (36 הקריאות המקושרות של r28a).

## מה אסור
- לא לבנות מ־r28-play ולהשמיט את אחד התיקונים "זמנית".
- לא להחליף רק חלק מארבעת אובייקטי ה־texfix: הם מניחים זה על זה (`za_guard`, הנעילה, הקריאות ההדדיות).
- לא לערוך את התיקייה `port/rando-dexcount/` או `port/runtime-texfix/` תוך כדי בנייה.

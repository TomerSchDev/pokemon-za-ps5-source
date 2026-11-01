# MERGE-HE.md — שילוב r28b-play עם חבילת המודלים שנשלחת לקונסולה

לכלי השני של Tomer, ששולח חבילת מודלים ל־PPSA91762. r28b-play כולל **שלושה** תיקונים ב־**eboot.bin בלבד**:
1. **texfix** (r28a) — תיקון קריסת הטקסטורות (ארבעה אובייקטים של ה־runtime).
2. **dexcount** (r28a) — משימות "רשום N מינים" סופרות גם מינים מ־Mega Dimension (יחידות משחק `main_310.o`, ‏`main_261.o` + ‏`za_dexcount.o`).
3. **dexopen** (r28b, חדש) — רשימת ה־Hyperspace Pokédex פתוחה מההתחלה (יחידות משחק `main_287.o`, ‏`main_115.o` + ‏`za_dexopen.o`).

## מקרה 1: חבילת המודלים משנה רק נתונים (mods / romfs / קבצים ב־app0 או ב־data)
- **קחו את `PPSA91762/eboot.bin` מהחבילה הזו כמו שהוא.** אין תלות בין שלושת התיקונים לבין קובצי נתונים.
- SHA-256 של ה־eboot: `ffd2cf18fc513ec4400d949325a5db2771336adb479b71026c7063280dd6aa26` (גם ב־`SHA256SUMS.txt`). אחרי ההעלאה: readback והשוואה.
- אין לשנות קובצי אפשרויות (`perf-r24-options.txt`, `performance-options.txt` = `optimized`, `slot-depth-options.txt`), שמירות או `active.json`.
- אם חבילת המודלים מחליפה את `eboot.bin` משלה **רק כדי לסמן גרסה**: לא לעשות זאת. ה־eboot של r28b הוא הבסיס.

## מקרה 2: חבילת המודלים נושאת eboot משלה (שינויים בקוד)
אז צריך לבנות eboot אחד שמכיל את ארבעת השינויים. **הבסיס הוא העץ הסופי של r28b**, ועליו מוסיפים את שינויי המודלים. אין לבנות מ־r28a או מ־r28 ולהוסיף את התיקונים "ביד".

### העץ
- `/home/tomer/ps5-za-native/r28b-play-20261030` — **קריאה בלבד.** לכל בנייה נוספת מעתיקים אותו לעץ חדש (כ־3.4 GB בתוך ה־VHDX של WSL; **דיסק C: היה מלא ב־30.10 — לבדוק מקום פנוי לפני שמעתיקים**). עץ השחזור `…-repro` נמחק.
- בתוכו: `source/` (ה־runtime עם texfix כבר מוחל, ואובייקטיו ב־`source/build/ps5/rt/`), `r28b/objects/` (אובייקטי ה־title של r28), `rando-dexcount/` (הארכיון של r28a `liblasgame-r28-dexcount.a` ו־`za_dexcount.o`), `rando-dexopen/` (הפלט של dexopen: `liblasgame-r28-dexopen.a` ו־`za_dexopen.o`), `rando-dexopen-src/` (צילום של הסקריפט והמקורות שרצו), ו־`r28b/evidence/`. הארכיון המקורי `liblasgame-r28.a` נשאר בעץ r28a (`/home/tomer/ps5-za-native/r28a-play-final-20261030/r28a/`, קריאה בלבד).

### מה כל סקריפט משנה (כדי לשלב בלי לנחש)

**A. texfix — `port/runtime-texfix/apply-runtime-texfix.py <tree>/source/runtime`** (כמו ב־r28a)
- עורך 5 קבצים ב־`runtime/` (`nvn/nvn.h`, `nvn/objects.c`, `nvn/vulkan/textures.c`, `nvn/vulkan/exec.c`, `nvn/vulkan/device.c`) ומוסיף 4 headers. **האובייקטים שמשתנים:** `build/ps5/rt/nvn/objects.o`, `…/vulkan/textures.o`, `…/vulkan/exec.o`, `…/vulkan/device.o` — כבר מקומפלים בעץ. אם חבילת המודלים נוגעת באחד מחמשת קובצי המקור האלה, מחילים את `apply-runtime-texfix.py` **אחרי** שינויי המודלים ומקמפלים מחדש את ארבעת האובייקטים בפקודת `cc_rt` של `port/runtime-texfix/build-r28a-candidate.sh` (הבקרה שם מוכיחה שהפקודה נכונה).
- לא נוגע בארכיון המשחק, באובייקטי ה־title או בשורת הקישור.

**B. dexcount — `port/rando-dexcount/ps5/apply-r28a.sh <tree> <out>`** (כמו ב־r28a; סקריפט מאושר SHA-256 ‏`ea70cc667b10c61157eb268189b0df61c5f2f4106f6ee5c6125bdc57c84313ad`)
- עותק של `liblasgame-r28.a` ‏(`a86c3134…`) שבו הוחלפו `main_310.o` ‏(→ ‏`9fe2a40b…`) ו־`main_261.o` ‏(→ ‏`39c40977…`); התוצאה `liblasgame-r28-dexcount.a` = ‏`1f0c586e721f93b80cd86b9b3675a18d95bca338952b5b3d01e7518bcc9a41cc`. אובייקט חדש `za_dexcount.o` ‏(`207e7a1ad5d8f26a8d95673b7d6414df6af99f36201168c412a5c4df9b9ce06f`) על שורת הקישור. היחידות מייבאות רק `za_dexcount_combine` / `za_dexcount_display` / `za_dexcount_extra_enabled`.
- **בעץ r28b הפלט הזה כבר קיים** (`rando-dexcount/`), ואין צורך להריץ את B שוב אלא אם בונים מהתחלה.

**C. dexopen — `port/rando-dexopen/ps5/apply-r28b.sh <tree> <out>`** (חדש; להריץ מצילום של התיקייה, לא מהתיקייה החיה)
- פרטים מלאים ב־`port/rando-dexopen/README-HE.md`, במניפסט `<out>/dexopen-r28b-manifest.json` וב־`BUILD-INFO.json` כאן (סעיף `dexopen`).
- **הארכיון:** עותק של `liblasgame-r28-dexcount.a` ‏(`1f0c586e…`, הבסיס נעול ב־SHA-256) שבו הוחלפו **שני** חברים: `main_287.o` ‏(`f8398bf6569a3de60a8ed60fb7a111b5102604f5b2c89975377bf204f2f65d38` → ‏`ae020153406b53df733916d2406e5cf33c2bcff98637121721f9dcb4c7ca5f29`) ו־`main_115.o` ‏(`ca1c1ca07c3fd1e73632eea3b79ebf732ae253414c9a0535f5804690db2f5b5d` → ‏`630b180af6977b4fb25d820702fff878aeeea8d486f7ac1175e377acb660912c`); התוצאה `<out>/liblasgame-r28-dexopen.a` = ‏`7a2e71bc89c0d0af9b2c3aab53a4f4f26258fba049cdb2fcfa03beed6f14d90b`; 1410 החברים האחרים זהים בית־בבית, אותו סדר (כולל `main_310.o` ו־`main_261.o` של dexcount).
- **אובייקט חדש:** `<out>/za_dexopen.o` ‏(`467e7e5dc8894acd5bcdc3868aecb3d68cf005c0ebb04273924469513a3f14bb`), שמתווסף לסוף `ZA_PS5_EXTRA_INPUTS` אחרי `za_dexcount.o`. הוא מייבא `__stderrp fflush fputs sceKernelDebugOutText snprintf` — כולם כבר imports של r28, ולכן רשימת ה־imports של ה־PIE לא משתנה (`verify-r28b.py image` ו־`verify-r28a.py image` נכשלים אם היא משתנה).
- היחידות המתוקנות מייבאות רק `za_dexopen_hyperspace_dex_enabled` ‏(main_287) ו־`za_dexopen_mega_dex_flag` ‏(main_115).
- לא נוגע ב־runtime, באובייקטי ה־title, בתפריט או ביחידות של dexcount.
- `BASE_ARCHIVE=… BASE_ARCHIVE_SHA256=…` מאפשרים להניח את dexopen על ארכיון אחר (למשל ארכיון שכבר כולל את יחידות המודלים) — ואז `compare_ar.py` חייב לקבל את רשימת החברים המותרים של **כל** השינויים.

**D. שינויי המודלים (של הכלי השני)** — לפי מה שהם משנים:
- **יחידות משחק נוספות:** להחליף אותן בעותק של `liblasgame-r28-dexopen.a` (לא של `liblasgame-r28.a` ולא של `…-dexcount.a`), בדיוק כמו ש־apply-r28b.sh עושה: `llvm-ar rcs <copy>.a <unit>.o`, ואז `compare_ar.py` עם רשימת החברים המותרים של **כל** השינויים.
- **אם הם נוגעים באותה יחידה שאחד התיקונים מתקן** (`main_310`, ‏`main_261`, ‏`main_287`, ‏`main_115`): אי אפשר להחליף פעמיים. צריך להחיל את שני ה־patchers על אותו `.c` ברצף (ה־patcher של dexopen, `prepare-dexopen-hooks.py`, עובד על ה־`.c` המקורי ב־`aot/main` ומייצר `gen/<unit>.c`; את ה־patcher של המודלים מריצים על הפלט הזה — או להפך — ושימו לב שהוא נועל SHA-256 של הקלט, ולכן בסדר "מודלים קודם" צריך לעדכן את הנעילה במכוון), ולקמפל פעם אחת במתכון `cc_unit`. לבדוק עם `llvm-nm -u` שהיחידה מייבאת את הסמלים של שני הצדדים.
- **אובייקטי title / runtime חדשים:** להוסיף ל־`ZA_PS5_EXTRA_INPUTS` אחרי `za_dexopen.o`.
- **קובצי runtime:** ראו A.

### פקודות הבנייה המשולבת (WSL)
```
base=/home/tomer/ps5-za-native/r28b-play-20261030                 # קריאה בלבד
work=/home/tomer/ps5-za-native/r28b-models-$(date +%Y%m%d)        # חדש
cp -a "$base/source" "$work/source"; cp -a "$base/port" "$work/port"; cp -a "$base/inc" "$work/inc"
mkdir -p "$work/r28b"; cp -a "$base/r28b/objects" "$work/r28b/objects"
cp -a "$base/rando-dexcount" "$work/rando-dexcount"                # הארכיון של r28a + za_dexcount.o (לא נבנה מחדש)
# 1. (רק אם המודלים משנים קובצי runtime) שינויי המודלים ב-$work/source/runtime, ואז:
python3 port/runtime-texfix/apply-runtime-texfix.py "$work/source/runtime"      # מדלג על מה שכבר מוחל
#    וקומפילציה מחדש של האובייקטים שנגעו בהם (cc_rt של build-r28a-candidate.sh)
# 2. dexopen מצילום (על הארכיון של dexcount):
snap=$work/rando-dexopen-src; mkdir -p "$snap/ps5"
cp port/rando-dexopen/ps5/{apply-r28b.sh,compare_ar.py} "$snap/ps5/"
cp port/rando-dexopen/{za_dexopen.c,za_dexopen.h,prepare-dexopen-hooks.py} "$snap/"
bash "$snap/ps5/apply-r28b.sh" "$work" "$work/rando-dexopen"       # הבסיס: $work/rando-dexcount/liblasgame-r28-dexcount.a (נעול)
# 3. יחידות המשחק של המודלים -> עותק של $work/rando-dexopen/liblasgame-r28-dexopen.a (llvm-ar rcs), compare_ar.py
# 4. קישור: הרשימה והשורה של r28b, בתוספת האובייקטים החדשים
mapfile -t rt < "$base/r28b/evidence/runtime-inputs.txt"
runtime=(); for p in "${rt[@]}"; do runtime+=("$work/source/$p"); done
extra=$(cat "$base/r28b/evidence/link-inputs.txt")
extra=${extra//"$base/r28b/objects/"/"$work/r28b/objects/"}
extra=${extra//"$base/rando-dexcount/"/"$work/rando-dexcount/"}
extra=${extra//"$base/rando-dexopen/"/"$work/rando-dexopen/"}
export ZA_PS5_EXTRA_INPUTS="$extra <אובייקטי המודלים>"      # (link-inputs.txt של r28b כבר כולל את za_dexcount.o ו-za_dexopen.o)
cd "$work/source" && bash tools/ps5/link-title.sh "$work/r28b/llvm-pie.elf" "${runtime[@]}" "<הארכיון המשולב>.a"
# 5. בדיקות התמונה: port/runtime-texfix/verify-r28a.py image <r28 PIE> <PIE חדש> <evidence> <project>
#    port/rando-dexopen/verify-r28b.py image <r28a PIE> <PIE חדש> <evidence>   (ה-globals הנוספים של המודלים יכשילו את
#    בדיקת "רק za_dexopen" - אז משווים ידנית: imports זהים, שום global של r28a לא נעלם, 6 הקריאות של dexcount+dexopen קיימות)
#    ואז llvm-strip, ps5-native-tool link / self --sign כמו בשלב 4 של build-r28b.sh
```
- `link-inputs.txt` של העץ הסופי מכיל כבר את `--wrap=…`, את `za_dexcount.o` ואת `za_dexopen.o` בסופו; `runtime-inputs.txt` הוא רשימת 64 אובייקטי ה־runtime.
- **אימות חובה לפני התקנה:** ה־imports זהים ל־r28 (או שינויים צפויים ומתועדים), הרישום (`verify-registration.py`) נשמר, `verify-r28a.py image` עובר (36 הקריאות המקושרות של r28a), והקריאות `f_70008d4178 → za_dexopen_hyperspace_dex_enabled` ו־`f_700033f8d8 → za_dexopen_mega_dex_flag` קיימות (ראו `verify-r28b.py image`).

## מה אסור
- לא לבנות מ־r28a או מ־r28-play ולהשמיט את אחד התיקונים "זמנית".
- לא להחליף רק חלק מארבעת אובייקטי ה־texfix: הם מניחים זה על זה.
- לא להחליף רק אחת משתי היחידות של dexopen (או של dexcount): שני הקוראים של הדגל צריכים להסכים, אחרת רשימה פתוחה עם ספירה סגורה (או להפך).
- לא לערוך את התיקיות `port/rando-dexopen/`, `port/rando-dexcount/` או `port/runtime-texfix/` תוך כדי בנייה.

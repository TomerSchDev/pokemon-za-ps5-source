# port/ui-v2 — עיצוב מחדש של תפריטי הפורט (שלב 1: עיצוב ומוקאפים)

המסמך המלא: `analysis/UI-V2-DESIGN-HE.md`. התיקייה הזאת מכילה את הרסטרייזר החדש, מודל התפריט, קוד המסכים, בדיקות ה-host והמוקאפים — **שום דבר כאן לא נבנה לקונסולה, לא נארז ולא הותקן.** אף קובץ קיים ב-`port/` לא שונה; הקוד הקיים נקרא לפי נתיב (`-I`) ולא הועתק.

## תוכן
| נתיב | תפקיד |
|---|---|
| `src/ui_canvas.{h,cpp}` | קנבס RGBA (premultiplied), פרימיטיבים עם anti-aliasing, טקסט דרך stb_truetype, מטמון גליפים |
| `src/ui_widgets.{h,cpp}`, `src/ui_theme.h` | גליפי PlayStation, pills, footer, toasts, scrollbar, נקודות דירוג; פלטה/טיפוגרפיה/ריווח |
| `src/ui_model.{h,cpp}` | **מודל התפריט כנתונים**: עמודים, שורות, רמות עם תיאורים, זמינות (Now/Phase2), ערכים, JSON ל-report.json, מכונת הניווט |
| `src/items_picker.{h,cpp}` | בורר הפריטים: טאבים לפי כיס, סמן/גלילה, קפיצות, מועדפים/אחרונים, presets של כמות, סריאליזציה. קורא את `port/cheats-r28/items.inc` לפי נתיב |
| `src/ui_launcher.{h,cpp}` | מסכי הלאנצ'ר (הגדרות, seed, כרטיסי ריצות, אישור, יצירה) |
| `src/ui_overlay.{h,cpp}` | ה-overlay בתוך המשחק (טאב Cheats, טאבי פריטים, readout, toasts) וקלט |
| `src/legacy_look.{h,cpp}` | **המראה הנוכחי** — עותקים של `Display::rect/text` ושל `Canvas::rect/encode` הקיימים, לרינדור "היום מול מחר" |
| `src/png_write.{h,cpp}`, `src/mockups_main.cpp` | כתיבת PNG (zlib) ויצירת כל המוקאפים |
| `test/test_ui.cpp` | בדיקות host: מודל, בורר, קלט, קנבס, דטרמיניזם, PNG, זמני ציור |
| `tools/build-host.sh` | בנייה ב-WSL (`clang++-21`, ‏`-Werror -fno-exceptions -fno-rtti`), הרצת הבדיקות, יצירת המוקאפים; `PS5_CHECK=1` מקמפל גם עם `prospero-clang18` (אובייקטים בלבד) |
| `tools/subset-fonts.py` | תת-קבוצה לטינית של Noto Sans (fontTools מה-venv של hebrew-lab) |
| `fonts/` | `NotoSans-{Regular,Bold}-latin.ttf` (‏28.6 KB כל אחד), `OFL.txt`, ‏`PROVENANCE.txt` |
| `third_party/stb/` | `imstb_truetype.h` (stb_truetype 1.26, public domain) + `PROVENANCE.txt` |
| `mockups/` | 22 PNG ב-1920x1080 + `SHA256SUMS.txt` (רשימה ותיאור במסמך העיצוב, סעיף 2) |

## איך מריצים
```
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash "/mnt/c/.../Pokemon-ZA-Native-Port/port/ui-v2/tools/build-host.sh" /home/tomer/ui-v2-build
PS5_CHECK=1 ... (בדיקת קומפילציה ל-PS5 בלבד)
```
הפלט (בינארים, לוגים) נכתב מחוץ ל-git; המוקאפים מתחדשים ב-`mockups/`.

## מה הוכח כאן ומה לא
עובר: הבנייה, `test_ui`, 22 מוקאפים דטרמיניסטיים, קומפילציה של ששת קובצי צד הכותר עם toolchain ה-PS5. לא הוכח: שום דבר בקונסולה (ראו סעיף 10 במסמך העיצוב).

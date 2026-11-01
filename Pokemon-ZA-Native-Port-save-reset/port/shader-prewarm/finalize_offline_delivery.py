"""Finalize the user report from measured compile/install receipts, then hash files."""
import json,shutil,zipfile
from pathlib import Path
from forecast import ROOT
from install_offline_cache import file_digest


def main():
    ev=ROOT/'evidence/offline-shaders-20261028'
    package=json.loads((ev/'package.json').read_bytes());dest=Path(package['path'])
    audit=json.loads((ev/'audit-inventory.json').read_bytes())
    install_path=ev/'installation.json'
    install=json.loads(install_path.read_bytes()) if install_path.exists() else None
    installed=bool(install and install.get('complete'))
    if installed:
        status=f"הועברו ל־PS5 ונבדקו בקריאה חוזרת {len(install['uploaded']):,} קבצים. מספר הקבצים במטמון המותקן עלה מ־{install['before_spv_count']:,} ל־{install['after_spv_count']:,}."
    else:
        status='החבילה מוכנה מקומית; ההעברה ל־PS5 לא הושלמה. אין להסיק שהקבצים מותקנים מהצלחת הקימפול בלבד.'
    text=f'''הכנת שיידרים מראש — Pokémon Legends: Z-A Randomizer r15
28 באוקטובר 2026

{status}

הספירה השיטתית מצאה {audit['unique_full_code_blobs']:,} קטעי קוד Maxwell ייחודיים של הסוויץ׳,
בתוך {audit['total_containers']:,} ארכיוני BNSH ו־{audit['variation_records']:,} רשומות של תוכניות גרפיות.
רשומות כוללות כפילויות וזוגות Vertex/Fragment, ולכן אלה יחידות ספירה שונות.
אלה שיידרים שכבר היו מקומפלים ל־GPU של הסוויץ׳; הפורט מתרגם אותם ל־Vulkan של ה־PS5.
סוכן נוסף בדק את הספירה וסרק גם חתימות קוד מחוץ לארכיונים: 238,567 קבצים
ותמונות קוד מפוענחות, כ־19.19GB, ללא שגיאות וללא מועמד נוסף עם כותרת שיידר תקינה.
שני קובצי זרם אודיו גדולים לא נסרקו; הפורמטים והמגבלות מפורטים בדוח הביקורת.

הכנו {package['validated_total']:,} קובצי SPIR-V שעברו קימפול ואימות spirv-val,
מהם {package['new_files']:,} תוספות מעבר למטמון הקודם. שגיאות קימפול/אימות: {package['compiler_failures']}.
נכללו גם 36 שיידרי עזר של הפורט ו־28 וריאציות XFB שהוגדרו בקובצי המשחק.
כל 62 המקורות שנאספו בעבר ולא שוחזרו בסריקה החדשה כבר נכללו במטמון הקודם שנשמר.

כל קובץ נבדק לפי SHA-256 ומזהה המקור שבו משתמש הפורט. קומפיילר glslang 16.2.0,
יעד Vulkan 1.3 / SPIR-V 1.6, ללא אופטימיזציה. בדיקת 12 מקורות שנאספו ממשחק
הפיקה תוצאה זהה לכלי הקודם. כלי ההעברה עבר 8 בדיקות לשמירת קבצים קיימים,
זיהוי גרסה שונה, מניעת נתיבים שגויים וזיהוי שחיתות בהעברה.

החבילה מיועדת ל־PPSA91762, קובץ התוכנית r15 המדויק, וגרסת המשחק 2.0.2.
העברה מוסיפה רק קבצים חסרים ל־/data/homebrew/PPSA91762/cache/spirv.
קובץ המשחק, השמירה, הריצה הפעילה והמטמון החי נשארים ללא שינוי.
לא הותקן קומפיילר מקומי על ה־PS5 במסגרת העבודה הזאת.

מה עדיין לא מכוסה:
• שבע תוכניות Maxwell (שש Compute ואחת Fragment), המשמשות ב־29 רשומות,
  כוללות הוראות שהמתרגם הקיים אינו תומך בהן. הן תועדו ולא הוחלפו בתוצאה משוערת.
• מצבי ציור דינמיים, כגון סוגי טקסטורות/קלטים שלמים והיפוך תמונה,
  עשויים ליצור וריאציות נוספות. הספירה אינה כל הצירופים האפשריים של מצבים אלה.
• ה־PS5 עדיין צריך ליצור pipelines של הדרייבר לפי מצב הציור בפועל.
  קובצי SPIR-V אינם מטמון הדרייבר. הם חוסכים את שלב הקימפול של המקור המתאים.
• אימות הקבצים אינו בדיקה חזותית של כל המשחק. צריך לבדוק אזורים/אפקטים חדשים
  ולבחון את הלוג אם נשארת תקיעה; לא כל תקיעה נגרמת משיידר חסר.

הנתונים מתייחסים לתוכן המקומי שנבדק, כולל קובצי DLC הקיימים בו,
ולא לגרסאות אחרות או לתוכן שלא נמצא בהתקנה הזאת.

הארכיון: {Path(package['archive']).name}
נפח הקבצים החדשים לפני דחיסה: {package['uncompressed_bytes']:,} בתים.
SHA-256 של הארכיון: {package['sha256']}

מצורפים manifest.json, כלי התקנה עם בדיקת גרסה, קוד כלי ההכנה ודוח הביקורת.
הכנה חוזרת משתמשת ברשימת מעקב ובודקת תוצאות קיימות במקום לקמפל אותן מחדש.
'''
    (dest/'Shader-Preparation-HE.txt').write_text(text,encoding='utf-8-sig')
    if install_path.exists():shutil.copy2(install_path,dest/'INSTALL-VERIFIED.json')
    for name in ('audit-coverage.txt','audit-coverage.json','audit-raw-sph.json','audit-raw-sph.txt'):
        if (ev/name).exists():shutil.copy2(ev/name,dest/name)
    with zipfile.ZipFile(dest/'Offline-Shader-Tools.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(Path(__file__).parent.iterdir()):
            if p.is_file() and (p.suffix in ('.py','.c','.h','.sh','.txt') or p.name=='CMakeLists.txt'):
                archive.write(p,'port/shader-prewarm/'+p.name)
        for pattern in ('audit-*.json','audit-*.txt'):
            for p in sorted(ev.glob(pattern)):archive.write(p,'evidence/'+p.name)
        for name in ('bnsh-scan-all.json','exefs-containers.json','compile-validation.json','tool-verification.json'):
            archive.write(ev/name,'evidence/'+name)
    package['console_uploaded']=installed
    (dest/'PACKAGE-VERIFIED.json').write_text(json.dumps(package,indent=2))
    lines=[file_digest(p)+'  '+p.name for p in sorted(dest.iterdir()) if p.is_file() and p.name not in ('SHA256SUMS.txt','NAS-COPY-VERIFIED.json')]
    (dest/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(folder=str(dest),installed=installed,files=len(lines))))


if __name__=='__main__':main()

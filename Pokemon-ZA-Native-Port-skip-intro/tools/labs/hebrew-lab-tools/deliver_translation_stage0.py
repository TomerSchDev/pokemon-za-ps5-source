"""Private stage-zero handoff and glossary-review bundle, excluding games, saves, models and credentials."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

LAB=Path(__file__).resolve().parents[1]
VERSION='Hebrew-Translation-20261029-r1'
DEST=LAB/'deliverables'/VERSION
NAS=Path(r'\\TheOnePiece\Software\PS5-13.60\Hebrew-Translation-20261029')/VERSION

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    if DEST.exists():raise FileExistsError('Choose a new delivery revision; preserve existing files')
    glossary=json.loads((LAB/'reports/glossary-build.json').read_text(encoding='utf-8'))
    memory=json.loads((LAB/'reports/translation-memory.json').read_text(encoding='utf-8'))
    batches=LAB/'batches/source-glossary-final-20261029/manifest.json'
    batch=json.loads(batches.read_text(encoding='utf-8'))
    qa=json.loads((LAB/'reports/qa-translation-pipeline-poc-20261029.json').read_text(encoding='utf-8'))
    assert glossary['glossary_sha256']==sha(LAB/'glossary.tsv')==batch['glossary_sha256']
    assert memory['tm_sha256']==sha(LAB/'memory/english-source.jsonl')==batch['tm_sha256']
    assert batch.get('inputs_verified_unchanged') is True
    assert qa['automation_passed'] and qa['critical_hashes_unchanged'] and qa['test_save_source_unchanged']
    assert not (LAB/'glossary-approval.json').exists(),'Human approval has not yet been requested for this draft'
    DEST.mkdir(parents=True)
    for name in ('glossary.tsv','review-glossary.html','requirements-lock.txt'):shutil.copyfile(LAB/name,DEST/name)
    screenshot_dir=DEST/'screenshots';screenshot_dir.mkdir()
    for old,new in [('frame_01050.png','menu.png'),('frame_01500.png','save.png')]:
        shutil.copyfile(LAB/'runs/translation-pipeline-poc-20261029/build/frames'/old,screenshot_dir/new)
    authored=sum(v for k,v in glossary['origins'].items() if k not in ('local_marian','proper_fallback','machine_requires_manual_translation'))
    text=f'''# תרגום Pokémon Legends: Z-A — כלים ומילון לבדיקה

29.10.2026. השלב הנוכחי הוא הכנת הכלים והמילון. תרגום האצוות והתקנה ב-PS5 עדיין לא בוצעו.

## המילון המשותף

- `review-glossary.html` — עמוד מקומי לחיפוש לפי מונח, קטגוריה ומצב בדיקה. נפתח ללא שרת וללא חיבור לרשת.
- `glossary.tsv` — מקור האמת המשותף, עם english, hebrew, category, note. מכיל {glossary['terms']:,} רשומות;
  {glossary['filled']:,} עם הצעה ו-{glossary['untranslated']:,} שטרם נקבע להן תרגום. רשומות טכניות/לא מילוניות מסומנות לבדיקה.
- {authored:,} רשומות מקורן במונחי הפרומפט ובהצעות סוכנים/תבניות סמנטיות, {glossary['origins'].get('proper_fallback',0):,}
  בתעתיק אוטומטי משוער, ו-{glossary['origins'].get('local_marian',0):,} בתרגום מכונה מקומי. אף טיוטה לא מוצגת כאישור אנושי או כתרגום רשמי.
- `terminology/seed.tsv` מכיל רק את הכתיבים המחייבים מהפרומפט. `terminology/shared-terms.tsv` מרכז החלטות תיאום מוצעות.
- הצעות מילים חדשות נכנסות לקבצים נפרדים, נבדקות להתנגשויות ומאוחדות בידי המתאם. הבדלי משמעות בין קטגוריות נשמרים.
- לפי הפרומפט: **Tomer מאשר את המילון לפני שלב 2**. לא נוצר אישור ולא התחיל תרגום המוני.

SHA-256 של טיוטת המילון: `{glossary['glossary_sha256']}`.

## הכלים והבדיקות

- זיכרון תרגום: {memory['records']:,} רשומות ב-{memory['files']} קבצים; {memory['nonempty_records']:,} מכילות טקסט נראה.
  כל {memory['roundtrip_files_passed']} הקבצים שוחזרו byte-for-byte. תוויות כפולות נשמרות באמצעות line_index נוסף במפתח.
- הוכנו {batch['batches']:,} אצוות מקור בלבד, 40–60 רשומות לאצווה. המילון והמקור נקשרים באמצעות SHA-256.
- בדיקות מפתחות, tokens/אייקונים/עמודים/צבעים, ניקוד, שאריות כתב, רוחב, הצעות מונחים ושתי חזרות תיקון לכל היותר.
- 66 בדיקות אוטומטיות משולבות עברו; דוח הבדיקה והלוג מצורפים.
- עטיפה לפי רוחב → סדר ויזואלי RTL → קידוד GFMSG → `mods/hebrew/romfs`, עם גופנים ורישיונות OFL.
- אריזה אמיתית דורשת אישור מילון תואם ותרגומים שעברו בדיקות; תרגום חדש לא נארז במסגרת שלב זה.
- ניסוי PC בן 200 שניות ארז רק 60 תרגומי PoC קיימים, בתיקיית נתונים ושמירה מועתקת נפרדות.
  התפריט והשמירה נבדקו בתמונות המצורפות. קובצי הייחוס והשמירה המקורית לבדיקה לא השתנו.

## מה עדיין דורש עבודה

טקסטורות הכותרות האפויות עדיין באנגלית; היישור והחשיפה ההדרגתית כפופים למגבלות ה-PoC.
רוחבי החלונות הם אומדנים לפי מדדי גופן, לא מדידה של כל מסך. הסתעפויות inline של מגדר/מספר וקודים לא מוכרים
דורשים טיפול ידני בטוח. מסלולי תיק, קרב ועלילה ייבדקו לאחר שיש תרגומים מאושרים ודגימות משחק מתאימות.
אין כאן תרגום מלא של המשחק ואין התקנה חדשה בקונסולה.

## שחזור בסביבה המקומית

הקבצים נשארו ב-`hebrew-lab`; עצי המשחק המקוריים לקריאה בלבד. השתמשו ב-`venv/Scripts/python.exe -X utf8`.
המקורות, הבדיקות, המילון, ה-TM, האצוות, דוחות הבדיקה וחבילת PoC פרטית נמצאים בארכיון.
הארכיון אינו כולל את קובצי המשחק המלאים, שמירות, סודות, מפתחות, סביבת Python, cache או משקולות מודל.
להפעלת כלי האריזה נדרשים החילוץ, הגופנים ו-runtime ה-PC הקיימים במעבדה.
מנוע טיוטת המונחים פעל מקומית. המקורות הטכניים: [מודל OPUS-MT](https://huggingface.co/Helsinki-NLP/opus-mt-en-he)
ו-[תיעוד CTranslate2](https://opennmt.net/CTranslate2/guides/transformers.html#marianmt).

שימוש אישי בלבד; אין להעלות את טקסט המשחק או קובצי המוד לריפו או לפרסום.
עותק אישי ב-NAS: `{NAS}`.
'''
    (DEST/'README-HE.md').write_text(text,encoding='utf-8')
    sources=set()
    for folder,patterns in [('tools',('*.py',)),('tests',('test_*.py',)),('coordination',('*.md',)),
                            ('terminology',('*.tsv','*.json','*.jsonl','*.py')),('reports',('*.json',)),
                            ('batches/source-glossary-final-20261029',('*.json','*.jsonl')),
                            ('build/pipeline-poc-20261029',('*',))]:
        for pattern in patterns:
            for p in (LAB/folder).rglob(pattern):
                if p.is_file() and '__pycache__' not in p.parts:sources.add(p)
    sources.discard(LAB/'terminology/draft.tsv')
    sources.discard(LAB/'terminology/proposals/local-marian-contextual.jsonl')
    sources.update([LAB/'memory/english-source.jsonl',LAB/'models/model-manifest.json'])
    sources.add(LAB/'reports/integration-unit-tests-final.log')
    archive=DEST/(VERSION+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(sources):z.write(p,p.relative_to(LAB).as_posix())
        for p in sorted(DEST.rglob('*')):
            if p.is_file() and p!=archive:z.write(p,p.relative_to(DEST).as_posix())
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    copies=[]
    for p in sorted(DEST.rglob('*')):
        if not p.is_file():continue
        dest=NAS/p.relative_to(DEST);dest.parent.mkdir(parents=True,exist_ok=True);digest=sha(p)
        if dest.exists() and sha(dest)!=digest:dest=dest.with_name(dest.stem+'-'+digest[:12]+dest.suffix)
        if not dest.exists():shutil.copyfile(p,dest)
        assert sha(dest)==digest
        copies.append(dict(file=p.relative_to(DEST).as_posix(),bytes=p.stat().st_size,sha256=digest,nas=str(dest)))
    record=dict(version=VERSION,glossary=glossary,batches=batch['batches'],nas=str(NAS),files=copies,zip_crc_verified=True)
    manifest=DEST/'delivery-manifest.json';manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    target=NAS/manifest.name
    if target.exists():assert sha(target)==sha(manifest)
    else:shutil.copyfile(manifest,target)
    assert sha(target)==sha(manifest)
    print(json.dumps(dict(stage='private review package delivered; NAS SHA256 verified',folder=str(DEST),nas=str(NAS),files=len(copies)),ensure_ascii=False),flush=True)

if __name__=='__main__':main()

"""Package audited experimental registrations, proven samples and explicit limits."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import zipfile
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
NAME='Pokemon-ZA-995-Species-Experimental-20261030-r1'


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def prepack_assets():
    build=ROOT/'build/all-species-r1';audit=json.loads((build/'static-audit.json').read_text())
    assert audit['registered_species']==995 and not audit['model_errors']
    stage=ROOT/'deliveries'/(NAME+'.assets-stage.zip');stage.parent.mkdir(parents=True,exist_ok=True)
    def load_asset(item):
        relative,record=item;data=(build/'all-models/romfs'/relative).read_bytes()
        assert hashlib.sha256(data).hexdigest()==record['sha256'],relative
        return relative,data
    with zipfile.ZipFile(stage,'x',allowZip64=True) as z:
        with ThreadPoolExecutor(max_workers=12) as pool:
            for i,(relative,data) in enumerate(pool.map(load_asset,sorted(audit['files'].items()),buffersize=24),1):
                entry=zipfile.ZipInfo('mods/all-models/romfs/'+relative,date_time=(2026,10,30,0,0,0))
                entry.compress_type=zipfile.ZIP_DEFLATED;entry.compress_level=1
                z.writestr(entry,data)
                if i%10000==0:print('ASSET ZIP',i,'/',len(audit['files']),flush=True)
    result=dict(complete=True,assets=len(audit['files']),audit_sha256=sha(build/'static-audit.json'),bytes=stage.stat().st_size)
    (ROOT/'deliveries'/(NAME+'.assets-stage.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)


def main():
    build=ROOT/'build/all-species-r1'
    audit=json.loads((build/'static-audit.json').read_text())
    registration=json.loads((build/'registration.json').read_text())
    integration=json.loads((build/'integration.json').read_text())
    assert audit['registered_species']==995 and audit['new_species']==631 and not audit['model_errors']
    runs={name:json.loads((ROOT/'qa/runs'/name/'run.json').read_text()) for name in (
        'multi-six-summary-r2','all-995-legacy-render-r4','all-995-smoliv-dex-r1','all-995-pokedex-confirm-r1')}
    assert all(not run['crash_lines'] and run.get('last_frame_line') for run in runs.values())
    assert runs['all-995-pokedex-confirm-r1']['save_before']['sha256']=='00eca682e32abbdca84468cb0ea93fc10e773bf941be92409928a96148f3fe45'
    out=ROOT/'deliveries'/NAME
    if out.exists():raise SystemExit('Version already exists')
    out.mkdir(parents=True)
    evidence=out/'evidence';evidence.mkdir()
    for filename in ('static-audit.json','integration.json','registration.json','spawns.json','icons.json','bridge-repairs.json'):
        shutil.copyfile(build/filename,evidence/filename)
    images={
        'Smoliv-Pokedex-995-species-build.png':'all-995-pokedex-confirm-r1/build/frames/frame_02800.png',
        'Smoliv-captured-summary-full-build.png':'all-995-smoliv-dex-r1/build/frames/frame_02200.png',
        'Caterpie-independent.png':'multi-six-summary-r3/build/frames/frame_02150.png',
        'Sandshrew-independent.png':'multi-six-summary-r2/build/frames/frame_02800.png',
        'Paras-independent.png':'all-995-legacy-render-r4/build/frames/frame_02200.png',
        'Chinchou-independent.png':'multi-six-summary-r2/build/frames/frame_04000.png',
        'Unown-independent.png':'all-995-smoliv-dex-r1/build/frames/frame_03100.png',
        'Rowlet-independent.png':'multi-six-summary-r2/build/frames/frame_05200.png'}
    for name,path in images.items():shutil.copyfile(ROOT/'qa/runs'/path,evidence/name)
    for filename in ('smoliv-real-capture-after.json','captured-smoliv-unown-fixture.json'):
        shutil.copyfile(ROOT/'evidence'/filename,evidence/filename)
    for name,run in runs.items():(evidence/(name+'-run.json')).write_text(json.dumps(run,indent=1),encoding='utf-8')
    authored=out/'authored-tools';authored.mkdir()
    for name in ('integrate_model_assets.py','native_donors.py','register_species.py','import_source_icons.py',
                 'repair_model_bridges.py','expand_wild_encounters.py','audit_registered_species.py','package_all_models.py',
                 'build_smoliv_model.py','catalog_inventory.py','source_archives.py','sword_assets.py','sword_animation.py'):
        shutil.copyfile(ROOT/'tools'/name,authored/name)
    unsupported=sorted({m['national'] for m in integration['skipped']})
    icons_missing=[m for m in integration['models'] if not m['icon_authentic']]
    info=dict(game='Pokemon Legends Z-A 2.0.2',experimental=True,registered_species=995,new_species=631,
        new_model_variants=833,native_species_preserved=364,native_catalog_entries_preserved=637,
        wild_species_assignments=631,extra_missing_forms_of_native_species_not_merged=True,
        converted_source_models=856,models_requiring_engine_extension=integration['skipped'],
        species_requiring_engine_extension=unsupported,missing_source_species=[19,20,21,22,165,166,276,277,300,301,327,351,366,367,368],
        native_pokedex_entries_preserved=364,new_pokedex_entries=631,
        descriptions_using_metadata_summary=len(registration['descriptions_using_metadata_summary']),
        genuine_flavor_text_for_every_species=False,variants_missing_UI_icon=len(icons_missing),shiny_UI_icons_distinct=False,
        added_description_languages=['English'],
        runtime_tested='Windows PC recompiled build',all_species_individually_runtime_tested=False,ps5_tested=False,
        broad_encounter_profile_runtime_visited=False,
        fixture_evidence='Six model UI pilots use injected copies of the Test save, not claimed as catches',
        actual_capture_evidence='Exact earlier captured Test save reloaded for Pokedex in full 995-species build; separate mixed fixture preserved Smoliv PID F0D61EB8 and appended one injected Unown',
        limitations=['Native controls/AI/collisions and effect timing adapted from ranked donor species',
                     'Source animation fallbacks are listed per model; unique mechanics not validated',
                     'Arceus deferred-lighting material category translated from LA 2 to native ZA 6',
                     'Sword material-only animation tracks are not converted',
                     'Cry audio coverage and player-directed battle not validated for all species',
                     'Special evolutions/forms, achievement/research rewards and all encounter locations require further QA'])
    (out/'BUILD-INFO.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    (out/'README-HE.md').write_text('''# ZA — חבילת ניסוי של 995 מינים רשומים

631 מינים חדשים נוספו כמינים עצמאיים לצד 364 מיני המקור. החבילה כוללת 833
וריאנטים של מודלים, גיאומטריה ושלדים שמקורם ב־Violet, Sword ו־Arceus,
חומרים מותאמים, אנימציות מקור ומיפוי שלהן לבקרי ZA, טבלאות תנועה והתנהגות,
למידת מתקפות מסוננת למתקפות הקיימות והתפתחויות רק למינים/צורות שרשומים בחבילה.
637 רשומות הקטלוג וכל המינים שהיו פעילים במקור נשמרו. אף מין חדש אינו
משתמש במודל גוף של מין מקור רק עם שינוי שם.

נוספו 631 רשומות פוקדקס. Smoliv נשאר מספר 365; שאר המספרים החדשים 366–995.
תיאורים מקוריים באנגלית נלקחו מהמשחקים הזמינים. ל־52 שדות תיאור שאין להם טקסט מקור
זמין נוסף משפט עובדתי המבוסס על שם וסוגי הפוקימון; אלה מסומנים בדוח registration.
אייקונים אותנטיים יובאו כאשר נמצאו. ל־108 וריאנטים עדיין חסר אייקון, ואייקון
Shiny אינו נבדל מהרגיל. קול מלא לכל המינים עדיין אינו מאומת.

טבלת הופעות הניסוי משייכת את המינים החדשים ל־630 משבצות ect_outzone קיימות,
בנוסף למפגש Smoliv הרגיל באזור פרא 1. מפגשי הסיפור והמדריך נשמרו, וכך גם
לפחות רשומה מקורית אחת לכל זהות מין/צורה מקורית. כל המקומות טרם נבדקו בשטח;
טבלת שיבוץ אינה הוכחה שכל המינים כבר נלכדו או זמינים בכל שלב בסיפור.

זוהי גרסת פיתוח שנבדקה ב־PC מול ZA 2.0.2. היא אינה גרסה מאושרת לכל המינים
ואינה נבדקה ב־PS5. Caterpie, Sandshrew, Paras, Chinchou, Unown ו־Rowlet הוצגו
במסכי המשחק מתוך שמירת Test מוזרקת ונפרדת. אין לטעון שנלכדו בבדיקות אלו.
Smoliv נלכד במשחק בפיילוט הקודם; בבדיקת המאגר המלא נשמר אותו פרט עם PID
F0D61EB8, הועבר למקום הראשון בשמירת Test ונוסף Unown מוזרק לצורך בדיקת תצוגה.
בדיקת פוקדקס נפרדת נטענה משמירת הלכידה המקורית ללא שינוי.
evidence מכילה צילומים מקוריים ודוחות בדיקה מפורטים.
טעינה מול כ־162 אלף קובצי מוד עשויה להימשך מספר דקות במצב הנוכחי.

למודלי Arceus הותאם סיווג התאורה של החומר לסיווג הפוקימונים של ZA. לכל מודל יש תבנית
ZA של בקר, AI ונפחי פגיעה עם מיפויי אנימציות חלופיים המתועדים ב־integration.
יש להמשיך לבדוק קרבות, קול, התפתחויות מיוחדות, תצורות, משימות פוקדקס ומיקומי
הופעות. בדיקת קבצים גורפת אינה תחליף לבדיקה של כל מין במשחק.

15 מינים נוספים, 1011–1025, הומרו לנכסי מודל אך אינם מופעלים בחבילה משום
שנדרשת הרחבה של מזהי המנוע וטבלאות/שמירות. ל־15 מינים אחרים אין מודל פיזי
במשחקי המקור שסופקו; הרשימה המדויקת מופיעה ב־BUILD-INFO.json.
צורות נוספות שחסרות למינים שכבר היו פעילים ב־ZA עדיין לא מוזגו בשלב זה.

להפעלה במנגנון המודים של ה־runtime: תיקיית mods/all-models. יש להפעיל גרסה
אחת של טבלאות המינים בלבד; אל תפעיל יחד עם הפיילוט הנפרד של Smoliv או עם
רנדומייזר שמשנה אותן טבלאות ללא מיזוג. החבילה אינה כוללת שמירות, מפתחות,
משחק מלא או קובץ הרצה. authored-tools הם קוד ההתאמה בפרויקט המקומי ודורשים
את משחקי המקור, הסכמות והכלים הקיימים בפרויקט כדי לבנות מחדש.
''',encoding='utf-8')
    # Hash the exact bytes written to ZIP against the audit, including late
    # material changes, without an additional full read of every asset.
    archive=out.parent/(NAME+'.zip')
    stage=out.parent/(NAME+'.assets-stage.zip');prepacked=stage.is_file()
    if prepacked:
        stage_info=json.loads(stage.with_suffix('.json').read_text())
        assert stage_info['complete'] and stage_info['audit_sha256']==sha(build/'static-audit.json')
        assert not archive.exists();stage.rename(archive)
    with zipfile.ZipFile(archive,'a' if prepacked else 'x',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
        paths=[(p,p.relative_to(out).as_posix()) for p in sorted(out.rglob('*')) if p.is_file()]
        if not prepacked:paths += [(build/'all-models/romfs'/relative,'mods/all-models/romfs/'+relative) for relative in sorted(audit['files'])]
        for i,(path,relative) in enumerate(paths,1):
            entry=zipfile.ZipInfo(relative,date_time=(2026,10,30,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED;entry.compress_level=4
            digest=hashlib.sha256()
            with path.open('rb') as source,z.open(entry,'w',force_zip64=True) as dest:
                while chunk:=source.read(512*1024):digest.update(chunk);dest.write(chunk)
            prefix='mods/all-models/romfs/'
            if relative.startswith(prefix):assert digest.hexdigest()==audit['files'][relative[len(prefix):]]['sha256'],relative
            if i%10000==0:print('ZIP',i,'/',len(paths),flush=True)
        for entry in z.infolist():entry.create_system=3;entry.external_attr=0o100644<<16
    print('Checking complete archive CRC...',flush=True)
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    digest=archive.with_suffix('.zip.sha256');digest.write_text(sha(archive)+'  '+archive.name+'\n')
    nas=Path(r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\20261030-v1')/NAME;nas.mkdir(parents=True,exist_ok=True)
    files=[archive,digest,out/'README-HE.md',out/'BUILD-INFO.json',*evidence.glob('*.png')]
    for path in files:
        dest=nas/path.name
        print('NAS',path.name,flush=True)
        if dest.exists():assert sha(path)==sha(dest),'Different file at versioned destination'
        else:shutil.copyfile(path,dest)
        assert sha(path)==sha(dest)
    result=dict(archive=str(archive),sha256=sha(archive),bytes=archive.stat().st_size,NAS=str(nas),NAS_files_verified=len(files))
    (ROOT/'evidence/all-species-delivery.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    if '--assets-only' in sys.argv:prepack_assets()
    else:main()

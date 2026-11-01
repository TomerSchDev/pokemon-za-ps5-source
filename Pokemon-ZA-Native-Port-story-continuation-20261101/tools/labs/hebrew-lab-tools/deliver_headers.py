"""Package only final header deliverables and verify a versioned private NAS copy."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

LAB=Path(__file__).resolve().parents[1]
VERSION='Hebrew-Headings-20261029-r5'
BUILD=LAB/'headers/build/headings-r5'
DEST=LAB/'deliverables'/VERSION
NAS=Path(r'\\TheOnePiece\Software\PS5-13.60')/VERSION

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,obj):Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    if DEST.exists():raise FileExistsError('Preserve existing delivery revision')
    audit=read(LAB/'headers/reports/integration-r5.json')
    assert not audit['discrepancies']
    menu=read(LAB/'headers/reports/qa-headers-r4-menu-save.json')
    appearance=read(LAB/'headers/reports/qa-headers-r5-appearance-confirm.json')
    for record in (menu,appearance):
        assert record['automation_passed'] and record['visual_review']['passed']
    # MENU/report QA used r4. Require identical final bytes, not just same labels.
    for p in (BUILD/'mods/hebrew-headers/romfs/ui/data/main_menu').glob('*.arc'):
        prior=LAB/'headers/build/headings-r4'/p.relative_to(BUILD)
        assert p.read_bytes()==prior.read_bytes()
    manifest=read(BUILD/'manifest.json')
    assert len(manifest['archives'])==8 and len(manifest['textures'])==22
    files=DEST/'files';files.mkdir(parents=True)
    shutil.copytree(BUILD/'mods',files/'mods')
    shutil.copyfile(BUILD/'heading-terms.tsv',files/'heading-terms.tsv')
    qa=files/'QA';qa.mkdir()
    for name in ('integration-r5.json','qa-headers-r4-menu-save.json','qa-headers-r5-appearance-confirm.json'):
        shutil.copyfile(LAB/'headers/reports'/name,qa/name)
    for record in (menu,appearance):
        for frame in record['visual_review']['reviewed_frames']:
            p=LAB/'runs'/record['name']/'build/frames'/f'frame_{frame:05d}.png'
            shutil.copyfile(p,qa/f'{record["name"]}-{frame:05d}.png')
    preview=files/'previews';preview.mkdir()
    seen=set()
    for t in manifest['textures']:
        if t['role']!='primary' or t['english'] in seen:continue
        seen.add(t['english'])
        p=BUILD/'previews'/Path(t['archive']).stem/(t['texture'].replace('^','_')+'.png')
        shutil.copyfile(p,preview/(t['english'].replace(' ','-')+'.png'))
    summary='בדיקות PC עברו עם תיקיית נתונים ושמירת בדיקה נפרדות. אומתו חזותית: '+', '.join(
        dict.fromkeys(menu['visual_review']['visible_titles']+appearance['visual_review']['visible_titles']))+'.\n\n'
    summary+='כותרות גיבוי וגרסאות אנגליות שלא הופיעו במסלולי הבדיקה נבדקו בקובצי המסכות ובאימות המבנה, אך לא בצילום מסך מתוך המשחק.\n'
    summary+='האפקטים הרכים נבנו מחדש בהתאמה למסכות המקור; קצב פסי הסריקה נשמר לכל כותרת. צילומי הבדיקה נמצאים בתיקיית `QA`.'
    readme=(LAB/'headers/README-HEADERS-HE-r4.md').read_text(encoding='utf-8').replace('20261029-r4','20261029-r5').replace('{{QA_SUMMARY}}',summary)
    (files/'README-HE.md').write_text(readme,encoding='utf-8')
    manifest.update(hardware_status='Selected PC headings visually verified; PS5 not installed or hardware tested',
        pc_visible_titles=menu['visual_review']['visible_titles']+appearance['visual_review']['visible_titles'],
        qa_files=['QA/integration-r5.json','QA/qa-headers-r4-menu-save.json','QA/qa-headers-r5-appearance-confirm.json'],
        effects_note='Source-fitted soft halos; native stripe periods preserved, not original authoring source')
    write(files/'manifest.json',manifest)
    native=[p for p in (files/'mods').rglob('*.arc')]
    assert len(native)==8
    for a in manifest['archives']:assert sha(files/a['file'])==a['replacement_sha256']
    sums=''.join(f'{sha(p)}  {p.relative_to(files).as_posix()}\n' for p in sorted(files.rglob('*')) if p.is_file())
    (files/'SHA256SUMS.txt').write_text(sums,encoding='utf-8')
    archive=DEST/(VERSION+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(files.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(files).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for p in files.rglob('*'):
            if p.is_file():assert hashlib.sha256(z.read(p.relative_to(files).as_posix())).hexdigest()==sha(p)
    shutil.copyfile(files/'README-HE.md',DEST/'README-HE.md')
    (DEST/'SHA256SUMS-DELIVERY.txt').write_text(f'{sha(archive)}  {archive.name}\n{sha(DEST/"README-HE.md")}  README-HE.md\n',encoding='utf-8')
    result=dict(created_utc=datetime.now(timezone.utc).isoformat(),local=str(DEST),zip_sha256=sha(archive),nas=str(NAS),nas_verified=False)
    try:
        NAS.mkdir(parents=True,exist_ok=True)
        copied=[]
        for p in sorted(DEST.rglob('*')):
            if not p.is_file():continue
            target=NAS/p.relative_to(DEST);target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if sha(target)!=sha(p):raise FileExistsError('Different NAS version already exists: '+str(target))
            else:shutil.copyfile(p,target)
            assert sha(target)==sha(p)
            copied.append(dict(file=p.relative_to(DEST).as_posix(),sha256=sha(p)))
        result.update(nas_verified=True,verified_files=copied)
    except (OSError,AssertionError) as error:
        result['nas_error']=str(error)
    write(LAB/'headers/reports/delivery-r5.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

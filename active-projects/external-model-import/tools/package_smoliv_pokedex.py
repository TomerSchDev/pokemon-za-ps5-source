"""Deliver the visually verified Pokedex update and verify its NAS copy."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
NAME='Smoliv-Pokedex-ZA-2.0.2-20261030-r3'


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    run=json.loads((ROOT/'qa/runs/smoliv-dex365-r3/run.json').read_text())
    extra=json.loads((ROOT/'qa/runs/smoliv-dex365-extras-r1/run.json').read_text())
    assert not run['crash_lines'] and not extra['crash_lines']
    assert run['save_before']['sha256']=='00eca682e32abbdca84468cb0ea93fc10e773bf941be92409928a96148f3fe45'
    out=ROOT/'deliveries'/NAME
    if out.exists():raise SystemExit('Version already exists')
    shutil.copytree(ROOT/'build/smoliv-dex365-r3/smoliv-independent',out/'mods/smoliv-independent')
    evidence=out/'evidence';evidence.mkdir()
    images={
        'Smoliv-Pokedex-No365.png':'smoliv-dex365-r3/build/frames/frame_02800.png',
        'Smoliv-Pokedex-list.png':'smoliv-dex365-r3/build/frames/frame_02250.png',
        'Smoliv-Pokedex-habitat.png':'smoliv-dex365-extras-r1/build/frames/frame_03250.png',
        'Smoliv-Pokedex-motions.png':'smoliv-dex365-extras-r1/build/frames/frame_04500.png',
        'Smoliv-captured-reloaded.png':'smoliv-captured-reload-r1/build/frames/frame_02100.png'}
    for name,path in images.items():shutil.copyfile(ROOT/'qa/runs'/path,evidence/name)
    shutil.copyfile(ROOT/'build/smoliv-dex365-r3/build.json',evidence/'pokedex-build.json')
    for name in ('smoliv-real-capture-after.json','smoliv-independent-static-audit.json'):
        shutil.copyfile(ROOT/'evidence'/name,evidence/name)
    info=dict(game='Pokemon Legends Z-A 2.0.2',national=928,internal=935,dex=365,
        native_pokedex_entries_preserved=364,actual_captured_pokemon_save=run['save_before']['sha256'],
        visual_QA=['Pokedex list','Full species page and original Violet description','Habitat screen','View motions screen'],
        runtime='Windows PC recompiled build',ps5_tested=False,
        limitations=['Player-directed battle not verified','Dolliv evolution not enabled in this single-species package',
                     'Adapted native controller/AI/hurtbox; 14 source motion fallbacks',
                     'Normal and shiny UI icons shared','Cry audio not verified'])
    (out/'BUILD-INFO.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    (out/'README-HE.md').write_text('''# Smoliv — מין עצמאי עם דף פוקדקס ב־ZA

גרסה זו מוסיפה ל־Smoliv את דף 365 בפוקדקס, עם המודל האמיתי מ־Violet,
Grass/Normal, סיווג Olive Pokémon, גובה, משקל ותיאור המקור. מסכי בית הגידול
והתנועות נבדקו גם הם במשחק. 364 רשומות הפוקדקס ו־637 רשומות הקטלוג המקוריות נשמרו.

הבדיקה נטענה משמירת Test שבה Smoliv נלכד במשחק ונשמר בפועל. השמירה עצמה
אינה כלולה. החבילה נבדקה ב־PC, ולא ב־PS5. הופעת הטבע היא במפגש Bunnelby
הרגיל באזור פרא 1. תיקיית mods/smoliv-independent מיועדת למנגנון המודים של ה־runtime.
הפעל גרסה אחת של טבלאות המינים בכל פעם; שילוב עם רנדומייזר מחייב מיזוג טבלאות.

המגבלות שנותרו: קרב בשליטת השחקן לא אומת, Dolliv אינו מופעל בחבילה זו,
14 פעולות משתמשות באנימציית מקור חלופית, ההתנהגות ונפחי הפגיעה מותאמים
מתבנית ZA, אייקון Shiny משותף לרגיל וקול הפוקימון לא אומת.

evidence כוללת צילומים אמיתיים ודוחות. אין בחבילה מפתחות, שמירות או משחק מלא.
''',encoding='utf-8')
    (out/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(out).as_posix()+'\n' for p in sorted(out.rglob('*')) if p.is_file()),encoding='utf-8')
    archive=out.parent/(NAME+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    digest=archive.with_suffix('.zip.sha256');digest.write_text(sha(archive)+'  '+archive.name+'\n')
    nas=Path(r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\20261030-v1')/NAME
    nas.mkdir(parents=True,exist_ok=True)
    files=[archive,digest,out/'README-HE.md',out/'BUILD-INFO.json',*evidence.glob('*.png')]
    for file in files:
        target=nas/file.name
        if target.exists():assert sha(file)==sha(target),'Different NAS version already exists: '+str(target)
        else:shutil.copyfile(file,target)
        assert sha(file)==sha(target)
    result=dict(archive=str(archive),bytes=archive.stat().st_size,sha256=sha(archive),NAS=str(nas),NAS_files_verified=len(files))
    (ROOT/'evidence/smoliv-pokedex-delivery.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()

"""Package the independent-species pilot only after capture and reload evidence pass."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    before = read(ROOT / 'evidence/smoliv-real-capture-before.json')
    after = read(ROOT / 'evidence/smoliv-real-capture-after.json')
    capture = read(ROOT / 'qa/runs/smoliv-real-capture-r3/run.json')
    reload = read(ROOT / 'qa/runs/smoliv-captured-reload-r1/run.json')
    reloaded_save = read(ROOT / 'evidence/smoliv-captured-reload-after.json')
    audit = read(ROOT / 'evidence/smoliv-independent-static-audit.json')
    assert before['hash_valid'] and after['hash_valid']
    assert not any(m['species_national'] == 928 for m in before['party'])
    caught = [m for m in after['party'] + after['boxed'] if m['species_national'] == 928]
    assert len(caught) == 1 and caught[0]['species_internal_raw'] == 935 and caught[0]['ChecksumValid']
    assert next(d for d in after['dex'] if d['species_national'] == 928)['caught']
    assert not capture['crash_lines'] and not reload['crash_lines']
    assert capture['save_after']['sha256'] == after['sha256']
    assert reload['save_before']['sha256'] == after['sha256']
    assert reloaded_save['hash_valid'] and reloaded_save['sha256'] == after['sha256']
    reloaded_smoliv = next(m for m in reloaded_save['party'] if m['species_national'] == 928)
    assert reloaded_smoliv['pid'] == caught[0]['pid'] and reloaded_smoliv['ChecksumValid']
    assert any('pm0935_00_00.trmbf' in line for line in reload['watched_lines'])
    assert audit['original_catalog_entries_unchanged'] == 637
    name = 'Smoliv-Independent-ZA-2.0.2-20261030-r2'
    output = ROOT / 'deliveries' / name
    if output.exists():
        raise SystemExit('Output already exists: ' + str(output))
    shutil.copytree(ROOT / 'build/smoliv-species-r1/species-pilot', output / 'mods/smoliv-independent')
    evidence = output / 'evidence'
    evidence.mkdir()
    images = {
        'Smoliv-independent-with-native-Mareep.png': 'smoliv-partner-r1/build/frames/frame_00900.png',
        'Smoliv-wild-capture-target.png': 'smoliv-real-capture-r3/build/frames/frame_02550.png',
        'Smoliv-captured-reloaded.png': 'smoliv-captured-reload-r1/build/frames/frame_02100.png',
        'Smoliv-summary-after-game-save-reload.png': 'smoliv-written-save-reload-r1/build/frames/frame_02200.png',
        'Smoliv-capture-save-confirmed.png': 'smoliv-real-capture-r3/build/frames/frame_12200.png',
    }
    for target, source in images.items():
        shutil.copyfile(ROOT / 'qa/runs' / source, evidence / target)
    for filename in ('smoliv-independent-static-audit.json', 'smoliv-capture-qa-static-audit.json',
                     'smoliv-real-capture-before.json', 'smoliv-real-capture-after.json',
                     'smoliv-game-written-save.json', 'smoliv-captured-reload-after.json'):
        shutil.copyfile(ROOT / 'evidence' / filename, evidence / filename)
    for label, data in (('capture-run.json', capture), ('reload-run.json', reload)):
        (evidence / label).write_text(json.dumps(data, indent=2), encoding='utf-8')
    for run_name in ('smoliv-real-capture-r3', 'smoliv-captured-reload-r1'):
        shutil.copyfile(ROOT / 'qa/runs' / run_name / 'QA-STOP.json', evidence / (run_name + '-stop.json'))
    sources = output / 'authored-tools'
    sources.mkdir()
    for filename in ('build_playable_smoliv.py', 'build_smoliv_model.py', 'verify_smoliv_independent.py',
                     'run_render_pilot.py', 'package_smoliv_independent.py'):
        shutil.copyfile(ROOT / 'tools' / filename, sources / filename)
    info = dict(game='Pokemon Legends Z-A 2.0.2', species_national=928, species_internal=935,
                authentic_geometry_skeleton_and_textures=True, independent_catalog_entry=True,
                authentic_source_payloads_verified=len(audit['authentic_geometry_texture_motion_payloads']),
                native_catalog_entries_preserved=637, runtime_platform_tested='Windows PC recompiled runtime',
                real_game_capture_verified=True, captured_save_hash=after['sha256'],
                captured_pokemon=caught[0], reload_verified=True, ps5_tested=False,
                summary_screenshot_fixture='Separate injected Test-party fixture, then saved and reloaded by the game',
                player_directed_battle_verified=False,
                release_encounter='Wild Zone 1 ordinary Bunnelby encounter',
                capture_qa_encounter='First catch tutorial slot, separate QA mod',
                limitations=['ZA controller, AI and hurtbox use adapted native donor data',
                             '14 source-motion fallbacks; player-directed battle not verified',
                             'No Dolliv evolution enabled', 'No new visible Pokedex entry',
                             'Shiny UI icon currently shares the normal icon',
                             'Imported cry audio not implemented or verified'])
    (output / 'BUILD-INFO.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    (output / 'README-HE.md').write_text('''# Smoliv כמין עצמאי ב־ZA — פיילוט ראשון

Smoliv משתמש במספר הלאומי 928 ובמספר הפנימי 935, עם הגיאומטריה, השלד,
הטקסטורות ואנימציות המקור מ־Violet. נוסף לו רישום נפרד בקטלוג ובטבלאות
ההתנהגות והתנועה. נתוני 637 הרשומות המקוריות בקטלוג נשמרו; Mareep נשאר Mareep.

נבדקו תצוגה כמלווה, הופעה בטבע, לכידה במשחק, קובץ שמירה תקין וטעינה מחדש
של הפוקימון שנלכד. בדיקת הלכידה התחילה בשמירת Test עם Tepig בלבד, ללא
Smoliv מוזרק. הפוקימון שנלכד זוהה בשמירה כ־928/935 עם checksum תקין.
הבדיקות והצילומים נעשו ב־PC מול ZA 2.0.2. החבילה לא הותקנה או נבדקה ב־PS5.

תיקיית mods/smoliv-independent מיועדת למנגנון המודים של ה־runtime.
בגרסת המסירה Smoliv מופיע במפגש Bunnelby הרגיל באזור פרא 1.
בדיקת הלכידה השתמשה בגרסה נפרדת ששינתה את מפגש מדריך הלכידה הראשון;
טקסט הסיפור הקבוע עדיין מזכיר Fletchling, ואינו מזהה את הפוקימון שנלכד.
זהותו בפועל נבדקה מקובץ השמירה. לשילוב עם רנדומייזר או מוד אחר שמשנה את
אותן טבלאות נדרש מיזוג נתונים; אל תפעיל שתי גרסאות של טבלאות אלו יחד.

הבקר, ההתנהגות ונפחי הפגיעה מבוססים על נתוני ZA מותאמים. ל־14 פעולות יש
מיפוי חלופי לאנימציית מקור. קרב עם Smoliv בשליטת השחקן טרם אומת. ההתפתחות ל־Dolliv
אינה מופעלת, אין דף פוקדקס גלוי חדש, אייקון Shiny משותף כרגע לגרסה הרגילה,
וקול המקור לא יובא ולא אומת. זה פיילוט של מין עצמאי ראשון, ולא מוד של כל המינים.

evidence מכילה צילומים מקוריים ודוחות בדיקה. authored-tools מכילה את הכלים
שנכתבו במשימה; הם נשענים על תיקיות המקור והכלים הקיימות בפרויקט המקומי.
החבילה אינה כוללת מפתחות, שמירות, משחק מלא או קובץ הרצה.
''', encoding='utf-8')
    entries = sorted(p for p in output.rglob('*') if p.is_file())
    (output / 'SHA256SUMS.txt').write_text(''.join(sha(p) + '  ' + p.relative_to(output).as_posix() + '\n'
                                                  for p in entries), encoding='utf-8')
    archive = output.parent / (name + '.zip')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():
                z.write(p, p.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for p in (output / 'mods/smoliv-independent/romfs').rglob('*'):
            if p.is_file():
                original = ROOT / 'build/smoliv-species-r1/species-pilot/romfs' / p.relative_to(output / 'mods/smoliv-independent/romfs')
                assert sha(p) == sha(original)
    archive.with_suffix('.zip.sha256').write_text(sha(archive) + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps(dict(archive=str(archive), bytes=archive.stat().st_size, sha256=sha(archive)), indent=2))


if __name__ == '__main__':
    main()

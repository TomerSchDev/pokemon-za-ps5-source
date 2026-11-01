"""Package a built Hebrew mod with measured coverage and bounded PC evidence.

No console or network access. Copies only an explicit deliverable allowlist.
The full source-game extraction and original crash logs remain outside it.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from pack_translation import poc_records, sha256
from translation_memory import iter_tm

LAB = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--reviewed-frames', required=True, help='comma-separated frame numbers actually inspected')
    parser.add_argument('--reviewed-ui', action='append', default=[], help='Screen observation actually inspected')
    parser.add_argument('--visible-english', action='append', default=[], help='English actually observed in inspected screens')
    parser.add_argument('--additional-run')
    parser.add_argument('--additional-reviewed-frames',default='')
    parser.add_argument('--unit-tests', type=int, required=True, help='Number of tests observed passing for this checkpoint')
    args = parser.parse_args()
    for value in (args.build, args.name, args.run):
        if Path(value).name != value or '/' in value or '\\' in value or value in ('.', '..'):
            raise ValueError('Use a folder name, not an arbitrary path')
    build = LAB / 'build' / args.build
    folder = LAB / 'deliverables' / args.name
    archive = folder.with_suffix('.zip')
    if folder.exists() or archive.exists():
        raise FileExistsError('Previous deliverables are preserved')
    manifest = read(build / 'manifest.json')
    coverage = read(build / 'coverage.json')
    if not coverage.get('complete') or coverage['remaining_rows']:
        raise ValueError('This release requires complete message-text coverage')
    validations = read(build / 'validation.json')
    run_root = LAB / 'runs' / args.run
    run = read(run_root / 'run.json')
    if any(not row['valid'] for row in validations) or not run.get('terminated_by_harness'):
        raise ValueError('Build validation or bounded PC run is incomplete')
    if run.get('save_before') != run.get('save_after'):
        raise ValueError('The isolated PC test modified its copied save; review first')
    original_save = LAB / 'saves/city-orig/save_0/main'
    if sha256(original_save) != run['save_before']['sha256']:
        raise ValueError('Original city test save changed; review first')
    tested_mods = run_root / 'mods'
    build_mods = build / 'mods'
    build_paths = {p.relative_to(build_mods) for p in build_mods.rglob('*') if p.is_file()}
    tested_paths = {p.relative_to(tested_mods) for p in tested_mods.rglob('*') if p.is_file()}
    if build_paths != tested_paths or any(sha256(build_mods / p) != sha256(tested_mods / p) for p in build_paths):
        raise ValueError('The PC run used different mod assets')
    records = {r['key']: r for r in iter_tm(LAB / 'memory/english-source.jsonl')}
    logical = {r['key']: r for r in poc_records(LAB / 'extract')[1]}
    for batch in ('opening-20261030-r2.jsonl', args.build + '.jsonl'):
        for row in iter_tm(LAB / 'translations' / batch):
            logical[row['key']] = row
    for key, row in logical.items():
        # Retain neutral_gender_rewrite, bound to this exact source hash.
        row['source_text_sha256'] = hashlib.sha256(records[key]['source'].encode('utf-8')).hexdigest()
    folder.mkdir(parents=True)
    shutil.copytree(build / 'mods', folder / 'mods')
    verification = folder / 'verification'
    verification.mkdir()
    for filename in ('manifest.json', 'validation.json', 'layout.json'):
        shutil.copyfile(build / filename, verification / filename)
    write(verification / 'coverage-summary.json', {k: v for k, v in coverage.items() if k != 'missing_keys'})
    write(verification / 'native-headings.json', manifest['native_heading_archives'])
    if (build/'native-text-review.json').exists():
        shutil.copyfile(build/'native-text-review.json',verification/'native-image-text.json')
        shutil.copyfile(LAB/'coordination/native-ui-review-r15.json',verification/'native-image-review.json')
    if (build/'native-font-selection.json').exists():
        shutil.copyfile(build/'native-font-selection.json',verification/'native-font-selection.json')
        shutil.copyfile(LAB/'coordination/bitmap-font-audit.json',verification/'bitmap-font-audit.json')
    source = folder / 'source'
    (source / 'translations').mkdir(parents=True)
    exported = source / 'translation-memory-reviewed.jsonl'
    exported.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in
                               sorted(logical.values(), key=lambda r: (records[r['key']]['file'], records[r['key']]['line_index']))),
                        encoding='utf-8')
    modules = ['opening-20261030-r1.py', *manifest['editorial_sources']]
    for filename,digest in manifest['editorial_sources'].items():
        if sha256(LAB/'translations'/filename)!=digest:
            raise ValueError('Editorial source changed after the tested build: '+filename)
    for filename in [*modules, args.build + '.jsonl', args.build + '-terms.tsv']:
        shutil.copyfile(LAB / 'translations' / filename, source / 'translations' / filename)
    from build_hebrew_project import load_module
    for name in manifest['editorial_sources']:
        data_file = getattr(load_module(name), 'DATA_FILE', None)
        if data_file:
            if Path(data_file).name != data_file:
                raise ValueError('Expected a neighboring frozen translation data file')
            shutil.copyfile(LAB/'translations'/data_file, source/'translations'/data_file)
    tool_names = ['build_hebrew_project', 'deliver_hebrew_project', 'pack_translation',
                  'translation_memory', 'translation_validate', 'audit_text_coverage',
                  'gfmsg', 'bfttf', 'build_font', 'rtl', 'text_layout', 'make_poc_mod',
                  'build_interface_headings', 'build_header_mod', 'ui_header_codec',
                  'ui_header_extract', 'ui_lang_archives', 'za_romfs', 'reuse_translation_memory',
                  'localization_exemptions', 'battle_set_templates', 'build_shared_headings',
                  'prepare_item_descriptions', 'prepare_donut_flavor', 'prepare_pokedex_forms',
                  'prepare_pokedex_categories', 'prepare_place_names', 'prepare_donut_names',
                  'ui_layout_overrides', 'prepare_apparel_names', 'prepare_rogue_battle',
                  'prepare_battle_state', 'prepare_npc_names', 'prepare_credits',
                  'glossary_manager', 'glossary_review', 'run_poc', 'build_opening_phase',
                  'prepare_battle_set_editorial', 'prepare_items_editorial',
                  'prepare_moves_editorial', 'prepare_species_editorial', 'apply_final_editorial',
                  'ui_color_codec', 'ui_text_terms', 'build_full_ui_text', 'apply_native_ui_build',
                  'inventory_ui_text', 'inventory_common_ui_text', 'ui_nested_terms',
                  'inventory_nested_ui_text', 'patch_bitmap_text_fonts']
    (source / 'tools').mkdir()
    for name in tool_names:
        shutil.copyfile(LAB / 'tools' / (name + '.py'), source / 'tools' / (name + '.py'))
    # Human-authored generator inputs and the exact credit attribution catalog.
    # No machine-reading drafts, private stores, runtime, save, or console logs.
    extra_sources = [
        'opening-20261030-r2.jsonl', 'credit-attributions-reviewed-20261030-r1.json',
        'npc-names-known-20261030-r1.json', 'npc-names-editorial-additions-20261030-r1.txt',
        'item-descriptions-core-20261030-r1.py', 'item-descriptions-held-20261030-r1.py',
        'item-descriptions-za-20261030-r1.txt', 'apparel-explicit-20261030-r2.txt',
        'battle-set-edits-20261030-r1.txt', 'battle-state-reviewed-20261030-r1.txt',
        'rogue-battle-reviewed-20261030-r1.txt', 'donut-flavor-templates-20261030-r1.txt',
        'places-20261030-r2.txt', 'pokedex-categories-20261030-r2.txt',
        'pokedex-forms-20261030-r1.txt',
        'bitmap-font-bindings-reviewed-20261030-r1.json',
    ]
    for name in extra_sources:
        shutil.copyfile(LAB/'translations'/name, source/'translations'/name)
    (source/'coordination').mkdir()
    for name in ('battle-state-source-20261030.json', 'rogue-battle-source-20261030.json',
                 'editorial-final-20261030-r1.json'):
        shutil.copyfile(LAB/'coordination'/name, source/'coordination'/name)
    (source/'requirements-native-ui.txt').write_text('ispc_texcomp==1.0.1\nnumpy\nPillow\nfonttools\npython-bidi\n',encoding='utf-8')
    write(verification/'editorial-data-sha256.json',
          {p.relative_to(source).as_posix():sha256(p) for p in sorted(source.rglob('*')) if p.is_file()})
    (source / 'tests').mkdir()
    for test in sorted((LAB / 'tests').glob('test_*.py')):
        shutil.copyfile(test, source / 'tests' / test.name)
    screenshots = folder / 'screenshots'
    screenshots.mkdir()
    reviewed_frames = [int(v) for v in args.reviewed_frames.split(',')]
    for frame in reviewed_frames:
        filename = f'frame_{frame:05d}.png'
        shutil.copyfile(run_root / 'build/frames' / filename, screenshots / filename)
    if args.additional_run:
        if Path(args.additional_run).name!=args.additional_run:raise ValueError('Additional run name must be a basename')
        extra_root=LAB/'runs'/args.additional_run;extra=read(extra_root/'run.json')
        if not extra.get('terminated_by_harness'):raise ValueError('Additional run did not complete')
        if extra.get('save_before')!=extra.get('save_after') or extra.get('save_before')!=run.get('save_before'):
            raise ValueError('Additional run save differs from the unchanged test baseline')
        extra_paths={p.relative_to(extra_root/'mods') for p in (extra_root/'mods').rglob('*') if p.is_file()}
        if extra_paths!=build_paths or any(sha256(extra_root/'mods'/p)!=sha256(build_mods/p) for p in build_paths):
            raise ValueError('Additional run assets differ')
        extra_frames=[int(v) for v in args.additional_reviewed_frames.split(',') if v]
        if not extra_frames:raise ValueError('Additional run requires actually reviewed frames')
        for frame in extra_frames:
            filename=f'frame_{frame:05d}.png'
            shutil.copyfile(extra_root/'build/frames'/filename,screenshots/('additional_'+filename))
        write(verification/'additional-pc-test.json',dict(
            **{k:extra.get(k) for k in ('name','started_utc','elapsed_seconds','input_script','runtime_sha256','save_before','save_after','terminated_by_harness','exit_code')},
            reviewed_frames=extra_frames,tested_mod_assets_match_package=True))
    missing_by_file = Counter(records[key]['file'] for key in coverage['missing_keys'])
    queue = [f for f in ['ik_message/dat/English/script/main_07_01.dat',
             'ik_message/dat/English/script/main_08_01.dat',
             'ik_message/dat/English/script/t1_A02.dat',
             'ik_message/dat/English/common/btl_std.dat',
             'ik_message/dat/English/common/iteminfo.dat'] if missing_by_file[f]]
    warnings = Counter(w['code'] for row in validations for w in row['warnings'])
    progress = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                    status='complete_message_coverage_with_bounded_pc_qa',
                    target='Hebrew across all 409 extracted message tables, including dialogue, story, sidequests and DLC',
                    changed_message_rows=manifest['translations'],
                    additional_changed_rows_since_r8=manifest['translations'] - 803,
                    reviewed_logical_records=len(logical),
                    language_rows_with_hebrew=coverage['changed_rows_with_hebrew'],
                    language_rows_total=coverage['required_rows'],
                    remaining_language_rows=coverage['remaining_rows'],
                    coverage_percent=coverage['coverage_percent'],
                    preserved_credit_attribution_rows=coverage['preserved_credit_attribution_rows'],
                    verified_credit_attribution_rows=coverage['verified_credit_attribution_rows'],
                    full_message_translation=True,
                    completed_message_tables=manifest['table_progress'],
                    next_queue=[dict(file=f, missing_language_rows=missing_by_file[f]) for f in queue],
                    manual_editorial_decisions=[
                        'Player and companion variants reviewed separately; shared choices use neutral Hebrew.',
                        'Declared neutral gender rewrites are individually bound to exact source hashes.',
                        'Number branches use reviewed neutral formulations; original variables are retained.',
                        'Exact-source memory reuse is restricted by context, controls and player variant.',
                        'Only exact app_common internal dummy rows are exempt; original bytes are preserved.',
                        'Exact TM/TR/HM and star identifiers in six item-name tables are verified separately and never counted as Hebrew.',
                        'Colored terms checked in logical text; full scene playback and timed reveal remain pending.',
                        'Proposed Hebrew names are editorial candidates; no user glossary approval is claimed.'],
                    qa=dict(structural_batch_rows=len(validations), invalid_translations=0,
                            warning_counts=dict(warnings), manual_review_flagged_rows=sum(r['manual_review'] for r in validations),
                            unit_tests_observed_passed=args.unit_tests,
                            unit_test_command='venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v',
                            pc_run=args.run, pc_elapsed_seconds=run.get('elapsed_seconds'),
                            pc_closed_by_test_harness=True,
                            copied_test_save_unchanged=True, original_city_save_unchanged=True,
                            tested_mod_assets_match_package=True, reviewed_frames=reviewed_frames,
                            ui_reviewed=args.reviewed_ui,
                            remaining_visible_english=args.visible_english,
                            pending=['dialogue playback in all translated scenes', 'cinematic timing and centering',
                                     'in-game playback of every translated native UI image', 'PS5 installer integration and runtime QA']),
                    ps5_installation_performed=False, exhaustive_gameplay_qa=False,
                    console_logs_included=False, original_crash_root_cause='unknown')
    write(verification / 'project-progress.json', progress)
    # Store bounded QA facts, without including raw logs or unrelated runtime paths.
    write(verification / 'pc-test.json', {k: run.get(k) for k in
          ('name', 'started_utc', 'budget_seconds', 'elapsed_seconds', 'input_script', 'shot_at',
           'runtime_sha256', 'save_before', 'save_after', 'terminated_by_harness', 'exit_code')})
    completed_tables = ', '.join(Path(name).stem for name, details in manifest['table_progress'].items()
                                 if details['complete_message_table'])
    reviewed_ui = '; '.join(args.reviewed_ui) or 'ראה צילומים והערות בדוח; לא הוצהרה בדיקת מסכים נוספת.'
    visible_english = '; '.join(args.visible_english) or 'לא נצפתה אנגלית בתוכן המסכים שנבדקו; אין בכך בדיקה של כל מסכי המשחק.'
    readme = f'''מוד עברית לפוקימון אגדות: Z-A — {args.name}
למשחק 2.0.2 עם הרחבת ממד המגה; מבוסס על {args.build}.

כיסוי מלא של טבלאות הטקסט שחולצו:
{coverage['changed_rows_with_hebrew']:,} מתוך {coverage['required_rows']:,} שורות לשוניות תורגמו לעברית.
כל {coverage['source_message_files']} קובצי ההודעות כלולים; נותרו {coverage['remaining_rows']} שורות לשוניות.
הכיסוי כולל את העלילה הראשית, שיחות ברחבי העיר, משימות הצד, ההרחבה,
הקרבות, הפוקידקס, שמות ותיאורי חפצים, הטיפים, הממשק ותפקידי הקרדיטים.

{coverage['preserved_credit_attribution_rows']:,} שמות יוצרים, חברות וחתימות זכויות בקרדיטים
נשמרו בדיוק במקור ואומתו בנפרד. הם אינם נספרים כתרגום לעברית.
גם קודים טכניים ({coverage.get('preserved_identifier_rows',0):,}), אינדקסי אלפבית וסיסמאות חידה
נשמרו כנדרש, ונבדקים בנפרד. לוגו המותג המקורי נשאר בתמונות המשחק.
כותרות הממשק הגרפיות הכלולות מפורטות ב־verification/native-headings.json.
תרגום הכיתובים שבתמונות כולל משימות, כותרות קרב, שמות מאמנים, מצבי פוקימון,
פוקידקס, דונאטים, טיפים וכותרות ההרחבה, יחד עם שכבות האפקטים שלהן.
לוגואים וסמלים מסחריים, הכתב הבדיוני של חנויות וסימוני דרגות נשמרים במקור.
הכיסוי המספרי מתייחס לקובצי ההודעות, ואינו ספירה של כל כיתוב בתוך תמונות העולם.
תוויות קצרות שהשתמשו בגופן מספרים הועברו לגופנים שתומכים בעברית;
פירוט תיקוני בחירת הגופן נמצא ב־verification/native-font-selection.json.

בדיקות:
{len(validations):,} רשומות באצווה עברו בדיקות מבנה, משתנים, עמודים וגופנים.
{args.unit_tests} בדיקות יחידה עברו. קובצי המוד בהרצת המחשב זהים לקבצים שבחבילה.
נערכה הרצת מחשב מוגבלת בזמן עם עותק שמירה מבודד; השמירה המקורית והעותק לא השתנו.
מה נבדק בפועל בצילומים: {reviewed_ui}
אנגלית שנראתה: {visible_english}

מגבלות תצוגה ובדיקה:
הטקסט מסודר לקריאה בעברית, אך מנגנון חשיפת האותיות של המשחק עדיין פועל משמאל לימין.
שורות קצרות עשויות להיות מיושרות לשמאל, ובועות של דמויות סמוכות עשויות לחפוף.
לא בוצע מעבר משחק מלא בכל הסצנות, בחירות הדמויות והקרבות.
כל מגבלת פריסה שמבוססת על הערכה מסומנת בדוח; כיסוי מלא אינו בדיקת כל מסך בפועל.
לא בוצעה התקנה או בדיקה ב־PS5. סיבת הקריסה המקורית שם אינה מוכחת, ואין טענה שתוקנה.

התקנה במחשב:
1. סגרו את המשחק וחלצו את ה־ZIP.
2. שמרו מוד עברית קודם מחוץ לתיקיית mods, כדי שלא יחליף את אותם קבצים.
3. העתיקו את mods/hebrew אל <LARECOMP_DATA_ROOT>/mods/hebrew.
4. השתמשו במשחק באנגלית (English/en-US); המוד מחליף את משבצת השפה האנגלית.
5. להסרה, סגרו את המשחק והעבירו את hebrew אל מחוץ ל־mods.

תכולה:
mods/hebrew — המוד המצטבר, הכותרות הגרפיות והגופנים עם רישיונותיהם.
source — תרגומים לוגיים, אצוות עריכה, נתונים קפואים וכלי בנייה ובדיקה.
verification — כיסוי, מבנה, פריסה, גיבובים ועובדות מהרצת המחשב.
screenshots — צילומים אמיתיים שנבדקו מתוך ההרצה המצוינת בדוח.
אין בחבילה ROM, שמירות, מפתחות, תוכנית המשחק או לוגים מהקונסולה.
לבנייה מחדש נדרשים החילוץ המקומי, זיכרון המקור, גופני הבסיס וחבילת הבסיס;
אלה אינם מופצים כאן. הנתונים הקפואים המצורפים הם הקלט הנוכחי לבנייה.
לאחר בניית הטקסט והכותרות יש להחיל את patch_bitmap_text_fonts.py עם הקטלוג הקפוא.
כלי prepare_* מתעדים גם שלבי יצירה היסטוריים; אין צורך להריצם מחדש לשימוש במוד.

שילוב ב־PS5:
מתקין Hebrew Trial הישן משתמש בטבלת קבצים ו־SHA-256 המקושרת לתוכנית.
אין בחבילה מתקין PS5 מעודכן; אין להחליף ישירות את נכסי חבילת הניסיון הישנה.
החבילה נועדה לשימוש אישי.
'''
    (folder / 'README-HE.txt').write_text(readme, encoding='utf-8-sig')
    hashes = {p.relative_to(folder).as_posix(): sha256(p) for p in sorted(folder.rglob('*')) if p.is_file()}
    write(folder / 'SHA256.json', hashes)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                if path.suffix.lower() in ('.exe', '.bin', '.log', '.key'):
                    raise ValueError('Unexpected non-deliverable: ' + str(path))
                out.write(path, folder.name + '/' + path.relative_to(folder).as_posix())
    with zipfile.ZipFile(archive) as packed:
        if packed.testzip() is not None:
            raise ValueError('ZIP CRC verification failed')
        for path, digest in hashes.items():
            if hashlib.sha256(packed.read(folder.name + '/' + path)).hexdigest() != digest:
                raise ValueError('ZIP payload mismatch: ' + path)
    print(json.dumps(dict(archive=str(archive), bytes=archive.stat().st_size, sha256=sha256(archive),
                          changed_rows=manifest['translations'], progress=str(verification / 'project-progress.json')),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

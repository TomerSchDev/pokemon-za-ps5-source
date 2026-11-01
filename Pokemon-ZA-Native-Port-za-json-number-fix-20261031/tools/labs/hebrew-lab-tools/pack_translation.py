"""Build a private English-slot LayeredFS candidate from approved, validated keyed translations.

`--existing-poc` is a narrowly bounded integration fixture: it loads only the exact translations
already present in make_poc_mod.POC. It cannot accept arbitrary translation files or fake approval.
`--reviewed-candidate` builds a partial editorial candidate without claiming that
the user approved its glossary; structural validation and visual QA still apply.
All writes stay in hebrew-lab. Nothing is installed in the source game or PS5.
"""
import argparse
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
from datetime import datetime, timezone

from fontTools.ttLib import TTFont
import bfttf
from gfmsg import MsgFile, encode_text, decode_units, read_tbl
from rtl import to_visual
from text_layout import FontMeasure, layout_translation, LayoutError

LAB = Path(__file__).resolve().parents[1]
FONT_SOURCES = (
    ('uifontbinFOT-UDKakugoC80Pro-DB.bfotf/ad10e404f1075731.bin', 'ZAHebrewSans-Regular.ttf'),
    ('uifontbinFOT-UDKakugoC80Pro-B.bfotf/0109c54073624581.bin', 'ZAHebrewSans-Bold.ttf'),
)


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def local(path):
    path = Path(path).resolve()
    if not path.is_relative_to(LAB):
        raise ValueError('All translation reads/writes must remain inside hebrew-lab')
    return path


def source_path(extract, file):
    path = PurePosixPath(file)
    if '\\' in file or ':' in file or path.is_absolute() or '..' in path.parts or path.suffix != '.dat':
        raise ValueError('Unsafe or non-message source path')
    if path.parts[:3] != ('ik_message', 'dat', 'English'):
        raise ValueError('Only the English text slot is supported')
    result = (extract / 'romfs' / Path(*path.parts)).resolve()
    if not result.is_relative_to(extract / 'romfs'):
        raise ValueError('Source escaped extraction root')
    return result


def read_jsonl(path):
    seen = set()
    out = []
    with local(path).open(encoding='utf-8-sig') as f:
        for index, line in enumerate(f, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get('key'), str):
                raise ValueError(f'Invalid keyed JSONL row {index}')
            if value['key'] in seen:
                raise ValueError('Duplicate translation key: '+value['key'])
            seen.add(value['key'])
            out.append(value)
    return out


def font_with_metrics(ttf_path, original):
    font = TTFont(ttf_path, recalcTimestamp=False)
    reference = TTFont(io.BytesIO(bfttf.decode(original)), recalcTimestamp=False)
    for attr in ('ascent', 'descent', 'lineGap'):
        setattr(font['hhea'], attr, getattr(reference['hhea'], attr))
    for attr in ('sTypoAscender', 'sTypoDescender', 'sTypoLineGap', 'usWinAscent', 'usWinDescent'):
        setattr(font['OS/2'], attr, getattr(reference['OS/2'], attr))
    if 'glyf' not in font:
        raise ValueError('Hebrew fallback must contain TrueType glyf outlines')
    cmap = font.getBestCmap()
    if any(code not in cmap for code in range(0x05D0, 0x05EB)):
        raise ValueError('Incomplete Hebrew font coverage')
    data = io.BytesIO()
    font.save(data)
    wrapped = bfttf.encode(original[:4], data.getvalue())
    assert bfttf.decode(wrapped)[:len(data.getvalue())] == data.getvalue()
    return wrapped


def poc_records(extract):
    from make_poc_mod import POC
    records, translations = {}, []
    for basename, values in POC.items():
        file = 'ik_message/dat/English/common/'+basename+'.dat'
        source = source_path(extract, file)
        message = MsgFile(source.read_bytes())
        labels = [label for _, label in read_tbl(source.with_suffix('.tbl').read_bytes())]
        for label, he in values.items():
            index = labels.index(label)
            key = file+':'+label
            records[key] = dict(key=key, file=file, label=label, line_index=index,
                                source=decode_units(message.lines[index]),
                                context=dict(window_type='existing_poc'), width_hint=None)
            translations.append(dict(key=key, he=he, new_terms=[], note='Existing PoC; no new batch translation'))
    return records, translations


def build_package(*, output, extract=None, tm=None, translations=None, glossary=None,
                  approval=None, existing_poc=False, layout_overrides=None,
                  reviewed_candidate=False):
    output = local(output)
    extract = local(extract or LAB/'extract')
    if output.exists():
        raise FileExistsError('Refusing to overwrite an existing package: '+str(output))
    from translation_validate import validate_translation
    from translation_memory import load_tm, load_glossary
    if existing_poc:
        if reviewed_candidate or any(value is not None for value in (tm, translations, approval)):
            raise ValueError('Existing-PoC fixture cannot be combined with arbitrary translations/approval')
        records, translated = poc_records(extract)
        terms = load_glossary(local(glossary)) if glossary else {}
        approval_record = dict(scope='exact_existing_poc_only', approved_for_bulk_translation=False)
    else:
        if reviewed_candidate:
            if approval is not None or not all(value is not None for value in (tm, translations, glossary)):
                raise ValueError('Reviewed candidates require TM, translations and glossary, without an approval claim')
            approval_record = dict(approved=False, scope='assistant_reviewed_partial_candidate',
                                   user_approval_claimed=False, requires_visual_qa=True)
        elif not all(value is not None for value in (tm, translations, glossary, approval)):
            raise ValueError('Approved packaging requires TM, translations, glossary and its matching approval')
        else:
            from glossary_manager import check_approval
            if not check_approval(local(glossary), local(approval)):
                raise ValueError('Glossary is not approved, or its SHA-256 changed')
            approval_record = json.loads(local(approval).read_text(encoding='utf-8-sig'))
        records = load_tm(local(tm))
        translated = read_jsonl(translations)
        terms = load_glossary(local(glossary))
    if not translated:
        raise ValueError('No translations supplied')
    measure = FontMeasure(LAB/'build/ZAHebrewSans-Regular.ttf')
    grouped = defaultdict(list)
    validations, layout = [], []
    for translation in translated:
        key = translation['key']
        if key not in records:
            raise ValueError('Translation key is not in this TM: '+key)
        record = records[key]
        expected_key=record['file']+':'+record['label']
        if record.get('duplicate_label'):
            expected_key+='#line='+str(record['line_index'])
        if record['key'] != expected_key:
            raise ValueError('TM key/file/label mismatch: '+key)
        verdict = validate_translation(record, translation, glossary=terms, check_width=not existing_poc)
        validations.append(verdict)
        if not verdict['valid']:
            raise ValueError('Translation failed validation: '+json.dumps(verdict, ensure_ascii=False))
        he = translation['he']
        if existing_poc:
            # Preserve exactly the already-reviewed PoC line breaks as an integration control.
            visual = to_visual(he)
            shaped = dict(key=key, logical=he, visual=visual, profile='existing_poc_explicit_breaks',
                          needs_visual_qa=True, budget={'provenance':'existing_poc_not_general_window_budget'})
        else:
            try:
                shaped = dict(key=key, **layout_translation(record, he, measure,
                              override=(layout_overrides or {}).get(key)))
            except LayoutError as exc:
                raise LayoutError(exc.code, key+': '+str(exc)) from exc
        grouped[record['file']].append((record, translation, shaped))
        layout.append(shaped)
    prepared = []
    source_records = []
    for file, changes in sorted(grouped.items()):
        source = source_path(extract, file)
        table = source.with_suffix('.tbl')
        original = source.read_bytes()
        message = MsgFile(original)
        baseline_lines = [list(line) for line in message.lines]
        baseline_params = list(message.params)
        labels = [label for _, label in read_tbl(table.read_bytes())]
        if len(labels) != len(message.lines)+1:
            raise ValueError('Unexpected GFMSG table/sentinel correspondence: '+file)
        changed = set()
        for record, translation, shaped in changes:
            index=record.get('line_index')
            if type(index) is not int or not 0<=index<len(message.lines) or labels[index]!=record['label']:
                raise ValueError('TM line index/label does not match original: '+record['key'])
            duplicate=labels[:-1].count(record['label'])>1
            if duplicate!=bool(record.get('duplicate_label',False)):
                raise ValueError('TM duplicate-label disambiguation does not match original: '+record['key'])
            if index in changed:
                raise ValueError('Multiple translations point to the same source line: '+record['key'])
            if decode_units(baseline_lines[index]) != record['source']:
                raise ValueError('Source has changed since TM extraction: '+record['key'])
            message.lines[index] = encode_text(shaped['visual'])
            if decode_units(message.lines[index]) != shaped['visual']:
                raise ValueError('Text/token codec did not round-trip: '+record['key'])
            changed.add(index)
        encoded = message.encode()
        decoded = MsgFile(encoded)
        if decoded.lines != message.lines or decoded.params != baseline_params:
            raise ValueError('Packaged GFMSG did not round-trip: '+file)
        if any(decoded.lines[index] != line for index,line in enumerate(baseline_lines) if index not in changed):
            raise ValueError('An untouched GFMSG line changed: '+file)
        source_records.append(dict(file=file, original_sha256=hashlib.sha256(original).hexdigest(),
                                   table_sha256=sha256(table), changed_lines=len(changed),
                                   total_lines=len(message.lines), params_preserved=True, untouched_lines_preserved=True))
        prepared.append((file, encoded))
    output.mkdir(parents=True)
    romfs = output/'mods/hebrew/romfs'
    for file, data in prepared:
        target = romfs/Path(*PurePosixPath(file).parts)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    fontdir = romfs/'ui/font/bin'
    fontdir.mkdir(parents=True)
    for source_name, ttf_name in FONT_SOURCES:
        source = extract/'fonts'/source_name
        target = fontdir/source_name.split('/')[0][len('uifontbin'):]
        target.write_bytes(font_with_metrics(LAB/'build'/ttf_name, source.read_bytes()))
    licenses = output/'mods/hebrew/licenses'
    licenses.mkdir()
    shutil.copyfile(LAB/'fonts-src/OFL.txt', licenses/'Noto-OFL.txt')
    (licenses/'FONT-NOTICE.txt').write_text('ZA Hebrew Sans is a modified font built from Noto Sans, Noto Sans Hebrew and Noto Sans Math.\nLicensed under SIL Open Font License 1.1. The OFL license text is included.\n',encoding='utf-8')
    (output/'layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'validation.json').write_text(json.dumps(validations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest = dict(created_utc=datetime.now(timezone.utc).isoformat(), slot='English',
        status='candidate_requires_visual_qa', scope=('existing_poc_fixture' if existing_poc else
            'assistant_reviewed_partial_candidate' if reviewed_candidate else 'approved_translation_candidate'),
        translations=len(translated), message_files=len(prepared), source_files=source_records,
        glossary_sha256=sha256(local(glossary)) if glossary else None, glossary_approval=approval_record,
        tm_sha256=sha256(local(tm)) if tm else None,
        translations_sha256=sha256(local(translations)) if translations else None,
        no_source_tree_writes=True, no_console_access=True,
        layout_limitations=['Default window profiles are estimates, not measured UI capacities.',
                            'Typewriter reveal remains left-to-right in visual-order text.',
                            'Inline gender/number alternatives are refused for manual review.'],
        files=[dict(path=str(path.relative_to(output)).replace('\\','/'),bytes=path.stat().st_size,sha256=sha256(path))
               for path in sorted(output.rglob('*')) if path.is_file()])
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--extract',type=Path,default=LAB/'extract')
    parser.add_argument('--tm',type=Path)
    parser.add_argument('--translations',type=Path)
    parser.add_argument('--glossary',type=Path)
    parser.add_argument('--approval',type=Path)
    parser.add_argument('--layout-overrides',type=Path)
    parser.add_argument('--existing-poc',action='store_true')
    parser.add_argument('--reviewed-candidate', action='store_true',
                        help='Build a local reviewed partial candidate without claiming user glossary approval')
    args=parser.parse_args()
    overrides=json.loads(local(args.layout_overrides).read_text(encoding='utf-8')) if args.layout_overrides else None
    result=build_package(output=args.out,extract=args.extract,tm=args.tm,translations=args.translations,
        glossary=args.glossary,approval=args.approval,existing_poc=args.existing_poc,layout_overrides=overrides,
        reviewed_candidate=args.reviewed_candidate)
    print(json.dumps({k:result[k] for k in ('status','scope','translations','message_files')},ensure_ascii=False))


if __name__=='__main__':
    main()

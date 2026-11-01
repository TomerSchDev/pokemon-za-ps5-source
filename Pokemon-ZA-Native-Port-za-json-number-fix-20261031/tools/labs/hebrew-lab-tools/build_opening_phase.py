"""Build the first editorial story batch; no console access or glossary approval claim."""
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

from audit_text_coverage import audit
from gfmsg import MsgFile
from pack_translation import build_package, sha256
from translation_memory import iter_tm

LAB = Path(__file__).resolve().parents[1]
REV = 'opening-20261030-r2'
EDITORIAL = 'opening-20261030-r1.py'
TERMS = {
    'Lumiose City': 'לומיוז', 'Lumiose': 'לומיוז', 'Hotel Z': 'מלון זי',
    'Pokémon': 'פוקימון', 'Chikorita': "צ'יקוריטה", 'Tepig': 'טפיג',
    'Totodile': 'טוטודייל', 'Pancham': "פנצ'אם", 'Urbain': 'אורבן',
    'Taunie': 'טוני', 'Andi': 'אנדי', 'Andre': 'אנדרה', 'Z-A Royale': 'רויאל Z-A',
}


def main():
    editorial = LAB / 'translations' / EDITORIAL
    spec = importlib.util.spec_from_file_location('editorial_opening', editorial)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tm = LAB / 'memory/english-source.jsonl'
    records = list(iter_tm(tm))
    story = {r['line_index']: r for r in records if r['file'].endswith('/script/main_01_01.dat')}
    authored = {}
    for indices, text in module.GROUPS:
        for index in indices:
            if index in authored:
                raise ValueError('Duplicate editorial index')
            voices = re.findall(r'\{VAR 0114:[0-9A-F,]+\}', story[index]['source'])
            if '@VOICE@' in text and len(voices) != 1:
                raise ValueError('Expected exactly one source voice control')
            authored[index] = text.replace('@VOICE@', voices[0] if voices else '')
    required = {i for i, r in story.items() if i < 150 and r['requires_translation']}
    if set(authored) != required:
        raise ValueError(f'Opening segment incomplete: missing={required-set(authored)}, extra={set(authored)-required}')
    translated = [dict(key=story[i]['key'], he=text, new_terms=[], note='assistant_editorial_review; story opening phase 1')
                  for i, text in sorted(authored.items())]
    # Names used by the introductory dialogue must also work as runtime variables.
    names = [r for r in records if '/common/' in r['file'] and r['source'] in TERMS]
    translated += [dict(key=r['key'], he=TERMS[r['source']], new_terms=[], note='assistant_reviewed_contextual_name') for r in names]
    tip_prefix = 'ik_message/dat/English/common/tips.dat:'
    tips = {
        'msg_ui_tips_0010_list': 'שמירת התקדמות',
        'msg_ui_tips_0010_page_1': 'שמירת התקדמות',
        'msg_ui_tips_0010_text_1':
            'התכונה {VAR FF00:0006}שמירה אוטומטית{VAR FF00:0000} שומרת את ההתקדמות שלך במהלך המשחק. '
            'אפשר גם לשמור ידנית בלחיצה על {VAR BD0A:0001}R בתפריט הראשי.\n\n'
            'לאחר סגירת המשחק, ההרפתקה תימשך מהמקום שבו נשמרה ההתקדמות בפעם האחרונה.',
    }
    translated += [dict(key=tip_prefix + key, he=value, new_terms=[], note='assistant_editorial_review; first-menu save tutorial')
                   for key, value in tips.items()]
    translation_path = LAB / 'translations' / (REV + '.jsonl')
    translation_path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in translated), encoding='utf-8')
    glossary = LAB / 'translations' / (REV + '-terms.tsv')
    with glossary.open('w', encoding='utf-8', newline='') as out:
        writer = csv.writer(out, delimiter='\t')
        writer.writerow(['english', 'hebrew', 'category', 'note'])
        for english, hebrew in TERMS.items():
            writer.writerow([english, hebrew, 'opening', 'assistant-reviewed subset; no user approval claimed'])
    output = LAB / 'build' / REV
    manifest = build_package(output=output, tm=tm, translations=translation_path,
                             glossary=glossary, reviewed_candidate=True,
                             layout_overrides={tip_prefix + 'msg_ui_tips_0010_text_1':
                                 dict(width_em=31, max_lines=10, scroll=False,
                                      provenance='first-menu tutorial screenshot; paragraph breaks retained; candidate requires render QA')})
    baseline = LAB / 'trial/assets/mods/000-hebrew-trial'
    target = output / 'mods/hebrew'
    overlaps = []
    for path in sorted(baseline.rglob('*')):
        if not path.is_file() or path.name == 'trial-manifest.json':
            continue
        relative = path.relative_to(baseline)
        dest = target / relative
        if dest.exists():
            if dest.read_bytes() == path.read_bytes():
                continue
            if dest.suffix != '.dat' or relative.parts[:2] != ('romfs', 'ik_message'):
                raise ValueError('Unexpected changed overlap: ' + str(relative))
            original = MsgFile((LAB / 'extract' / relative).read_bytes())
            prior, new = MsgFile(path.read_bytes()), MsgFile(dest.read_bytes())
            if not (len(original.lines) == len(prior.lines) == len(new.lines)):
                raise ValueError('Overlapping message line counts differ')
            if not (original.params == prior.params == new.params):
                raise ValueError('Overlapping message flags differ')
            for index, line in enumerate(new.lines):
                if line != original.lines[index]:
                    if prior.lines[index] != original.lines[index] and prior.lines[index] != line:
                        raise ValueError('Translation conflict on previously reviewed line')
                    prior.lines[index] = line
            dest.write_bytes(prior.encode())
            overlaps.append(str(relative))
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
    coverage = audit(tm, target / 'romfs', LAB / 'extract')
    (output / 'coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    changed_lines = 0
    for path in (target / 'romfs/ik_message/dat/English').rglob('*.dat'):
        original = MsgFile((LAB / 'extract' / path.relative_to(target)).read_bytes())
        candidate = MsgFile(path.read_bytes())
        if original.params != candidate.params or len(original.lines) != len(candidate.lines):
            raise ValueError('Final merged GFMSG structure changed')
        changed_lines += sum(a != b for a, b in zip(original.lines, candidate.lines))
    manifest.update(
        scope='partial_editorial_opening_candidate',
        source_batch_translations=len(translated), story_translations=len(authored),
        runtime_name_translations=len(names), retained_existing_sample_translations=60,
        new_tutorial_translations=len(tips),
        translations=changed_lines, additional_changed_lines=changed_lines - 60,
        complete_game_translation=False,
        editorial_source_sha256=sha256(editorial), baseline_manifest_sha256=sha256(baseline / 'trial-manifest.json'),
        merged_message_files=overlaps,
        no_console_access=True, ps5_crash_fixed=False,
        story_scope='main_01_01 message indices 0..149; arrival through first battle briefing; both companion variants',
        visible_qa='pending; existing headings retained; new story dialogue not yet visually accepted',
    )
    manifest['files'] = [dict(path=p.relative_to(output).as_posix(), bytes=p.stat().st_size, sha256=sha256(p))
                         for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'manifest.json']
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: manifest[k] for k in ('scope', 'translations', 'story_translations', 'runtime_name_translations', 'complete_game_translation')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

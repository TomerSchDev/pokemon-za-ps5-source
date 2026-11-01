"""Measure installed message coverage against every English source record.

Reads an isolated LayeredFS romfs and the existing translation memory. It never
connects to a console or changes a mod. A present .dat file does not mean that
all of its messages were translated; count individual visible message rows.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import unicodedata

from gfmsg import MsgFile, decode_units
from translation_memory import iter_tm
from translation_validate import plain_text
from localization_exemptions import preserved_alphabet_index, preserved_story_code, preserved_credit_attribution, preserved_literal

LAB = Path(__file__).resolve().parents[1]
HEBREW = re.compile(r"[\u05d0-\u05ea]")


def internal_placeholder(record):
    # Exact, inspected table/value pair only. Japanese prose elsewhere remains
    # required; this does not turn a missing localization into an exemption.
    return (record['file'] == 'ik_message/dat/English/common/app_common.dat'
            and record['source'] == 'ダミー')


def audit(tm, romfs, extract):
    messages = {}
    categories = defaultdict(Counter)
    missing = []
    malformed = []
    source_files = set()
    overridden_files = set()
    visible_rows = 0
    neutral_rows = 0
    placeholder_rows = 0
    identifiers = 0
    invalid_identifiers = []
    alphabet_indices = 0
    invalid_alphabet_indices = []
    story_codes = 0
    invalid_story_codes = []
    credit_attributions = 0
    invalid_credit_attributions = []
    for record in iter_tm(tm):
        if not record.get('requires_translation'):
            continue
        visible_rows += 1
        if internal_placeholder(record):
            placeholder_rows += 1
            continue
        alphabet_index=preserved_alphabet_index(record)
        story_code=preserved_story_code(record)
        credit_attribution=preserved_credit_attribution(record)
        identifier=preserved_literal(record)
        if identifier is not None:
            if alphabet_index is not None:alphabet_indices+=1
            elif story_code is not None:story_codes+=1
            elif credit_attribution is not None:credit_attributions+=1
            else:identifiers+=1
            path=romfs/record['file']
            if path.is_file():
                if record['file'] not in messages:
                    messages[record['file']] = (MsgFile((extract/'romfs'/record['file']).read_bytes()),MsgFile(path.read_bytes()))
                original,candidate=messages[record['file']]
                actual=decode_units(candidate.lines[record['line_index']]) if len(candidate.lines)==len(original.lines) else None
            else:actual=record['source']
            if actual!=identifier:
                (invalid_alphabet_indices if alphabet_index is not None else
                 invalid_story_codes if story_code is not None else
                 invalid_credit_attributions if credit_attribution is not None else invalid_identifiers).append(record['key'])
            continue
        # Counters, punctuation and button glyphs do not become Hebrew prose.
        # Their source rows should remain intact and must not block completion.
        if not any(unicodedata.category(ch).startswith('L') for ch in plain_text(record['source'])):
            neutral_rows += 1
            continue
        relative = record['file']
        source_files.add(relative)
        category = record['context']['category']
        count = categories[category]
        count['required'] += 1
        path = romfs / relative
        if not path.is_file():
            count['missing_override'] += 1
            missing.append(record['key'])
            continue
        overridden_files.add(relative)
        if relative not in messages:
            original = MsgFile((extract / 'romfs' / relative).read_bytes())
            candidate = MsgFile(path.read_bytes())
            if len(candidate.lines) != len(original.lines):
                malformed.append(relative)
            messages[relative] = original, candidate
        original, candidate = messages[relative]
        index = record['line_index']
        if len(candidate.lines) != len(original.lines):
            count['invalid_file'] += 1
            missing.append(record['key'])
        elif candidate.lines[index] == original.lines[index]:
            count['unchanged_source'] += 1
            missing.append(record['key'])
        elif HEBREW.search(decode_units(candidate.lines[index])):
            count['changed_with_hebrew'] += 1
        else:
            count['changed_without_hebrew'] += 1
            missing.append(record['key'])
    total = sum(c['required'] for c in categories.values())
    translated = sum(c['changed_with_hebrew'] for c in categories.values())
    return dict(
        visible_source_rows=visible_rows,
        language_neutral_rows=neutral_rows,
        internal_placeholder_rows=placeholder_rows,
        preserved_identifier_rows=identifiers,
        invalid_preserved_identifiers=invalid_identifiers,
        preserved_alphabet_index_rows=alphabet_indices,
        invalid_preserved_alphabet_indices=invalid_alphabet_indices,
        preserved_story_code_rows=story_codes,
        invalid_preserved_story_codes=invalid_story_codes,
        preserved_credit_attribution_rows=credit_attributions,
        verified_credit_attribution_rows=credit_attributions-len(invalid_credit_attributions),
        invalid_preserved_credit_attributions=invalid_credit_attributions,
        credit_attribution_policy='1635 individually inspected creator/organization names and copyright-owner signatures in two source-hash/key/index/text-bound catalogs; kept exact, never counted as Hebrew. Credit roles and prose require translation.',
        language_and_attribution_rows=total+credit_attributions,
        accounted_for_language_and_attribution_rows=translated+credit_attributions-len(invalid_credit_attributions),
        story_code_policy='Four exact source-hash/key/index-bound password options in sk/sub_140.dat; case and distractors verified unchanged, never counted as Hebrew',
        alphabet_index_policy='46 exact source-hash/key/index-bound alphabet glyphs in initial.dat; verified unchanged, never counted as Hebrew',
        identifier_policy='Only exact TM/TR/HM and star identifiers in six item-name tables; exact code checked, never counted as Hebrew',
        placeholder_policy='Only exact app_common.dat rows containing ダミー; original bytes preserved',
        required_rows=total,
        changed_rows_with_hebrew=translated,
        remaining_rows=total - translated,
        coverage_percent=round(100 * translated / total, 6) if total else 0,
        complete=bool(total) and not missing and not malformed and not invalid_identifiers and not invalid_alphabet_indices and not invalid_story_codes and not invalid_credit_attributions,
        source_message_files=len(source_files),
        overridden_message_files=len(overridden_files),
        by_category={k: dict(v) for k, v in sorted(categories.items())},
        malformed_message_files=malformed,
        missing_keys=missing,
        limitations=[
            'Hebrew presence does not prove translation accuracy or visual quality.',
            'Text baked into UI textures and randomizer overlay text is outside GFMSG coverage.',
        ],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--romfs', type=Path, required=True)
    parser.add_argument('--tm', type=Path, default=LAB / 'memory/english-source.jsonl')
    parser.add_argument('--extract', type=Path, default=LAB / 'extract')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    result = audit(args.tm, args.romfs, args.extract)
    if args.out:
        destination = args.out.resolve()
        if not destination.is_relative_to(LAB):
            raise ValueError('Audit output must remain inside hebrew-lab')
        if destination.exists():
            raise FileExistsError('Use a new report filename')
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'missing_keys'}, ensure_ascii=False))
    if args.require_complete and not result['complete']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

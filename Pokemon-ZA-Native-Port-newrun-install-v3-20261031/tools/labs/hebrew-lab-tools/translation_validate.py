"""Conservative validators for logical-order Hebrew translator output.

validate_translation(record, translation, glossary=None, check_width=True) returns
{key, valid, errors:[{code,message}], warnings:[{code,message}], manual_review}.
valid means structural checks passed, not that linguistic quality was proved.
Colour meaning, gender, unknown controls and unresolved glossary collisions can
still require human review. No network, game writes or translation is performed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from translation_memory import Glossary, iter_tm, load_glossary, relevant_glossary, token_segments

TOKEN = re.compile(r'\{VAR ([0-9A-F]{4})(?::([0-9A-F]{1,4}(?:,[0-9A-F]{1,4})*))?\}')
OPTIONAL = {0xBD06, 0xBE00, 0x1900, 0x1101, *range(0x1000, 0x1004), *range(0x1300, 0x1304)}
EVENTS = {0xBE02, 0xBE05, 0x0114}
LATIN_ALLOWED = {'Z-A', 'HP', 'PP', 'TM', 'Mega', 'Alpha'}
BRANCHES = {0x1100, 0x1101}
PUA_MIN, PUA_MAX = 0xE300, 0xE34E
HEBREW_FINALS = str.maketrans('ךםןףץ', 'כמנפצ')
INPUT_SYLLABARY_SYMBOLS = frozenset('ヒフヘホマミムメモヤユヨラリルレロワヲン')


def _take_utf16(text, start, count):
    end, units = start, 0
    while end < len(text) and units < count:
        units += 2 if ord(text[end]) > 0xFFFF else 1
        end += 1
    if units != count:
        raise ValueError('BD0A icon name is truncated or splits a UTF-16 character')
    return end


def parse_tokens(text):
    """Exact token spans, with a BD0A payload included in its atomic spelling."""
    tokens, i = [], 0
    while i < len(text):
        if text.startswith(('{{', '}}'), i):
            i += 2
            continue
        if text.startswith('{VAR', i):
            m = TOKEN.match(text, i)
            if not m:
                raise ValueError(f'malformed/noncanonical VAR token at character {i}')
            end, code, args = m.end(), int(m[1], 16), m[2] or ''
            if code == 0xBD0A:
                if not args:
                    raise ValueError('BD0A icon token needs a name length')
                end = _take_utf16(text, end, int(args.split(',')[0], 16))
            tokens.append({'code': code, 'args': args, 'raw': m[0], 'atom': text[i:end], 'start': i, 'end': end})
            i = end
        else:
            i += 1
    return tokens


def plain_text(text, tokens=None):
    tokens = parse_tokens(text) if tokens is None else tokens
    out, last = [], 0
    for token in tokens:
        out.append(text[last:token['start']]); last = token['end']
    out.append(text[last:])
    return ''.join(out).replace('{{', '{').replace('}}', '}')


def _pages(text):
    return re.split(r'\{VAR BE01(?::[0-9A-F,]+)?\}', text)


def _event_edge(text, token):
    start = max(text.rfind('\n', 0, token['start']), text.rfind('{VAR BE01}', 0, token['start']))
    start = start + (len('{VAR BE01}') if text.startswith('{VAR BE01}', start) else 1) if start >= 0 else 0
    newline = text.find('\n', token['end'])
    page = text.find('{VAR BE01}', token['end'])
    ends = [x for x in (newline, page) if x >= 0]
    end = min(ends) if ends else len(text)
    before = plain_text(text[start:token['start']]).strip()
    after = plain_text(text[token['end']:end]).strip()
    return 'only' if not before and not after else 'prefix' if not before else 'suffix' if not after else 'inline'


def _latin_words(text):
    """Latin letters including accents; hyphens within Z-A are retained."""
    out, current = [], ''
    for char in text:
        latin = unicodedata.category(char).startswith('L') and 'LATIN' in unicodedata.name(char, '')
        if latin or (char == '-' and current):
            current += char
        elif current:
            out.append(current.rstrip('-')); current = ''
    if current:
        out.append(current.rstrip('-'))
    return out


def hebrew_term_present(term, text):
    """Allow final-letter inflection and a definite article in construct phrases.

    The lexical words must still occur in the same order. This permits טבעת
    המגה for טבעת מגה without disabling terminology validation for that concept.
    """
    term, text = term.translate(HEBREW_FINALS), text.translate(HEBREW_FINALS)
    if term in text:
        return True
    words = term.split(' ')
    if len(words) < 2 or any(not word for word in words):
        return False
    pattern = re.escape(words[0]) + ''.join(r'\s+ה?' + re.escape(word) for word in words[1:])
    return re.search(pattern, text) is not None


def _visible_budgets(text):
    width, maximum = 0, 0
    for atom in token_segments(text):
        if atom == '\n':
            maximum = max(maximum, width); width = 0
        elif isinstance(atom, tuple):
            width += atom[1]
        elif not unicodedata.combining(atom):
            width += 1
    return max(width, maximum)


def _known(code):
    return (0x0100 <= code <= 0x02FF or code in OPTIONAL or code in BRANCHES or code in EVENTS or
            code in {0xFF00, 0xBD0A, 0xBDFF, 0xBD03, 0xBE01})


def validate_translation(record, translation, glossary=None, *, check_width=True):
    if not isinstance(record, dict) or not isinstance(record.get('source'), str) or not isinstance(record.get('key'), str):
        raise ValueError('TM record requires string key and source')
    if isinstance(translation, str):
        translation = {'key': record['key'], 'he': translation}
    key, source = record['key'], record['source']
    result = {'key': key, 'valid': False, 'errors': [], 'warnings': [], 'manual_review': False}

    def issue(code, message, *, warning=False, manual=False):
        result['warnings' if warning else 'errors'].append({'code': code, 'message': message})
        result['manual_review'] |= manual

    if not isinstance(translation, dict):
        issue('schema', 'translation must be an object'); return result
    if translation.get('key') != key:
        issue('key_mismatch', 'output key differs from the source key')
    he = translation.get('he')
    if not isinstance(he, str):
        issue('schema', 'he must be a string'); return result
    if not isinstance(translation.get('new_terms', []), list) or any(
            not isinstance(t, dict) or not isinstance(t.get('en'), str) or not isinstance(t.get('he'), str)
            for t in translation.get('new_terms', []) if isinstance(translation.get('new_terms', []), list)):
        issue('schema', 'new_terms must be a list of {en,he} strings')
    if not isinstance(translation.get('note', ''), str):
        issue('schema', 'note must be a string')
    try:
        src_tokens, dst_tokens = parse_tokens(source), parse_tokens(he)
    except ValueError as error:
        issue('malformed_token', str(error)); return result
    src, dst = Counter(t['atom'] for t in src_tokens), Counter(t['atom'] for t in dst_tokens)
    optional_atoms = {t['atom'] for t in src_tokens if t['code'] in OPTIONAL}
    neutral_gender_atoms = set()
    neutral = translation.get('neutral_gender_rewrite')
    if neutral is not None:
        allowed = {t['atom'] for t in src_tokens if t['code'] == 0x1100}
        requested = neutral.get('omitted_tokens') if isinstance(neutral, dict) else None
        if (not isinstance(neutral, dict) or neutral.get('source_sha256') != hashlib.sha256(source.encode('utf-8')).hexdigest()
                or not isinstance(requested, list) or not requested
                or any(not isinstance(t, str) for t in requested) or len(requested) != len(set(requested))
                or not set(requested).issubset(allowed) or any(t in dst for t in requested)
                or not isinstance(neutral.get('reason'), str) or len(neutral['reason'].strip()) < 10
                or not re.search('[א-ת]', plain_text(he, dst_tokens))):
            issue('invalid_gender_neutralization', 'gender-neutral rewrite must bind the exact source and omit only declared 1100 grammar tokens')
        else:
            neutral_gender_atoms = set(requested)
            issue('neutral_gender_rewrite_review', '1100 grammar omitted for explicitly reviewed gender-neutral Hebrew wording', warning=True, manual=True)
    for atom, count in (dst - src).items():
        issue('unexpected_token', f'added/changed token or icon payload: {atom} (extra {count})')
    for atom, count in (src - dst).items():
        if atom not in optional_atoms and atom not in neutral_gender_atoms:
            issue('missing_token', f'required token/icon payload missing: {atom} (missing {count})')
        elif any(t['atom'] == atom and t['code'] == 0x1101 for t in src_tokens):
            issue('plural_branch_omitted', 'omitted 1101 requires confirmation of a number-neutral formulation', warning=True, manual=True)

    source_pua = Counter(c for c in source if PUA_MIN <= ord(c) <= PUA_MAX)
    target_pua = Counter(c for c in he if PUA_MIN <= ord(c) <= PUA_MAX)
    if source_pua != target_pua:
        issue('pua_mismatch', 'PUA icon code points or multiplicities changed')
    all_source_pua = Counter(c for c in source if unicodedata.category(c) == 'Co')
    all_target_pua = Counter(c for c in he if unicodedata.category(c) == 'Co')
    if all_source_pua != all_target_pua and source_pua == target_pua:
        issue('private_use_mismatch', 'other private-use code points changed or were introduced')
    if any(unicodedata.category(c) == 'Cs' for c in he):
        issue('raw_surrogate', 'unpaired surrogate character is not valid translator output')
    src_plain, dst_plain = plain_text(source, src_tokens), plain_text(he, dst_tokens)
    if src_plain.strip() and not dst_plain.strip():
        issue('empty_translation', 'visible source text became empty')
    if he.count('\n') > source.count('\n'):
        issue('added_newline', 'translator added hard newlines; wrapping belongs to the layout stage')
    if any(0x0591 <= ord(c) <= 0x05C7 and unicodedata.category(c).startswith('M') for c in dst_plain):
        issue('niqqud', 'Hebrew marks/niqqud are not supported')
    if any(ord(c) in {*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F} for c in dst_plain):
        issue('bidi_control', 'logical translation must not inject bidi direction controls')
    if any(ord(c) < 32 and c not in '\n\t\r' for c in he):
        issue('raw_control', 'unexpected raw control character')
    foreign_letters = {c for c in dst_plain if unicodedata.category(c).startswith('L') and
                       'LATIN' not in unicodedata.name(c, '') and 'HEBREW' not in unicodedata.name(c, '')}
    if foreign_letters:
        if (source == he and source in INPUT_SYLLABARY_SYMBOLS and
                (record.get('context', {}).get('category') == 'ui' or Path(record.get('file', '')).stem == 'strinput')):
            issue('nonlexical_input_symbol', 'original kana keyboard symbol preserved; it is not Hebrew vocabulary and needs keyboard QA', warning=True, manual=True)
        else:
            codes = ', '.join(f'U+{ord(c):04X}' for c in sorted(foreign_letters))
            issue('unsupported_script', 'non-Hebrew/nonapproved-Latin letters require manual translation/review: '+codes, manual=True)

    dictionary = glossary if glossary is not None else record.get('glossary', {})
    allowed = set(LATIN_ALLOWED)
    if isinstance(dictionary, Glossary):
        contextual = dictionary.for_record(record)
        if dictionary.pattern:
            for match in dictionary.pattern.finditer(source):
                folded = match[0].casefold()
                if folded in dictionary.conflicts and not any(en.casefold() == folded for en in contextual):
                    issue('glossary_collision', f'English term needs category disambiguation: {match[0]}', warning=True, manual=True)
    else:
        contextual = dictionary or {}
    # A large immutable name table is shared by thousands of records. Cache
    # its approved Latin identifiers rather than rescanning every name per row.
    if isinstance(dictionary, Glossary):
        if not hasattr(dictionary, '_approved_latin_cache'):
            dictionary._approved_latin_cache = {}
        context_id=id(contextual)
        if context_id not in dictionary._approved_latin_cache:
            dictionary._approved_latin_cache[context_id]=frozenset(
                word for value in contextual.values() if isinstance(value,str) for word in _latin_words(value))
        allowed.update(dictionary._approved_latin_cache[context_id])
    else:
        for value in contextual.values():
            if isinstance(value, str):
                allowed.update(_latin_words(value))
    leftover = sorted(set(_latin_words(dst_plain)) - allowed)
    if leftover:
        issue('latin_not_allowed', 'unapproved Latin words: ' + ', '.join(leftover))
    for english, hebrew in relevant_glossary(source, dictionary, record).items():
        if not hebrew_term_present(hebrew, dst_plain):
            issue('glossary_term_missing', f'canonical glossary term missing for {english}')

    source_pages, target_pages = _pages(source), _pages(he)
    if len(source_pages) != len(target_pages):
        issue('page_count', 'BE01 page boundaries changed')
    else:
        for n, (sp, tp) in enumerate(zip(source_pages, target_pages)):
            st, tt = parse_tokens(sp), parse_tokens(tp)
            a = Counter(t['atom'] for t in st if t['code'] not in OPTIONAL | {0xFF00} and t['atom'] not in neutral_gender_atoms)
            b = Counter(t['atom'] for t in tt if t['code'] not in OPTIONAL | {0xFF00} and t['atom'] not in neutral_gender_atoms)
            if a != b:
                issue('token_crossed_page', f'nonoptional tokens moved across BE01 boundary on page {n+1}')
            if plain_text(sp, st).strip() and not plain_text(tp, tt).strip():
                issue('empty_page', f'visible page {n+1} became empty or its text crossed BE01')

    target_events = {}
    for token in dst_tokens:
        if token['code'] in EVENTS:
            target_events.setdefault(token['atom'], []).append(token)
    seen_events = Counter()
    for token in src_tokens:
        if token['code'] not in EVENTS:
            continue
        occurrence = seen_events[token['atom']]; seen_events[token['atom']] += 1
        candidates = target_events.get(token['atom'], [])
        if occurrence >= len(candidates):
            continue
        src_edge, dst_edge = _event_edge(source, token), _event_edge(he, candidates[occurrence])
        if src_edge in {'prefix', 'suffix', 'only'} and src_edge != dst_edge and dst_edge != 'only':
            issue('event_placement', f'{token["raw"]} moved away from its original line/sentence edge')
        elif src_edge == 'inline':
            issue('inline_event_review', f'{token["raw"]} attachment needs linguistic review', warning=True, manual=True)

    for token in dst_tokens:
        if token['code'] in BRANCHES:
            issue('unsupported_inline_branch', 'existing gender/plural branch needs a proved branch-aware layout path', manual=True)
        elif not _known(token['code']):
            issue('unknown_control', f'unknown control {token["raw"]} preserved; semantics need review', warning=True, manual=True)
    colored = [t for t in src_tokens if t['code'] == 0xFF00 and t['args'].split(',')[0] != '0000']
    if colored:
        issue('color_span_semantics', 'FF00 multiplicity is checked; matching the translated coloured words needs review', warning=True, manual=True)
    for n, token in enumerate(dst_tokens):
        if token['code'] == 0xFF00 and token['args'].split(',')[0] != '0000':
            next_color = next((t for t in dst_tokens[n+1:] if t['code'] == 0xFF00), None)
            between = he[token['end']:next_color['start'] if next_color else len(he)]
            if not plain_text(between).strip() and not parse_tokens(between):
                issue('empty_color_span', 'a nondefault FF00 colour span contains no translated content')

    if re.search(r'(?<![א-ת])(?:אתה|לחץ|בחר|השתמש|נסה|תוכל|עליך)(?![א-ת])', dst_plain):
        issue('gendered_address_review', 'possible singular/gendered address; prefer neutral/plural wording', warning=True, manual=True)
    for opening, closing in [('(', ')'), ('[', ']')]:
        if dst_plain.count(opening) != dst_plain.count(closing):
            issue('unbalanced_punctuation', f'unbalanced {opening}{closing} in logical translation', warning=True, manual=True)
    if check_width and isinstance(record.get('width_hint'), (float, int)) and record['width_hint'] > 0:
        if _visible_budgets(he) > record['width_hint']:
            issue('width_hint_exceeded', 'logical text exceeds source-derived character hint; wrapping and screen QA are required', warning=True)
    result['valid'] = not result['errors']
    return result


def validate_batch(records, outputs, glossary=None):
    records, outputs = list(records), list(outputs)
    report = {'valid': False, 'errors': [], 'results': [], 'counts': {}}
    expected = [r['key'] for r in records]
    keys = [r.get('key') if isinstance(r, dict) else None for r in outputs]
    if len(expected) != len(set(expected)):
        report['errors'].append({'code': 'duplicate_source_key', 'message': 'source batch keys are not unique'})
    if len(keys) != len(set(keys)):
        report['errors'].append({'code': 'duplicate_output_key', 'message': 'output repeats a key'})
    if expected != keys:
        report['errors'].append({'code': 'batch_key_order', 'message': 'output keys/count/order differ from source packet'})
    mapped = {o['key']: o for o in outputs if isinstance(o, dict) and isinstance(o.get('key'), str)}
    for record in records:
        if record['key'] in mapped:
            report['results'].append(validate_translation(record, mapped[record['key']], glossary))
    report['counts'] = {'sources': len(records), 'outputs': len(outputs), 'checked': len(report['results']),
                        'valid': sum(r['valid'] for r in report['results']),
                        'invalid': sum(not r['valid'] for r in report['results']),
                        'manual_review': sum(r['manual_review'] for r in report['results'])}
    report['valid'] = not report['errors'] and len(report['results']) == len(records) and all(r['valid'] for r in report['results'])
    return report


def audit_source_records(records):
    """Audit parser coverage using source data only; this does NOT certify translations."""
    report = {'scope': 'source_parser_only_no_translation', 'records': 0, 'parse_errors': [],
              'control_types': {}, 'unknown_control_types': {}, 'inline_branch_records': 0,
              'color_records': 0, 'icon_records': 0}
    types, unknown = Counter(), Counter()
    for record in records:
        report['records'] += 1
        try:
            tokens = parse_tokens(record['source'])
        except ValueError as error:
            report['parse_errors'].append({'key': record['key'], 'message': str(error)})
            continue
        codes = {t['code'] for t in tokens}
        report['inline_branch_records'] += bool(codes & BRANCHES)
        report['color_records'] += 0xFF00 in codes
        report['icon_records'] += 0xBD0A in codes
        for token in tokens:
            types[f'{token["code"]:04X}'] += 1
            if not _known(token['code']):
                unknown[f'{token["code"]:04X}'] += 1
    report['control_types'] = dict(sorted(types.items()))
    report['unknown_control_types'] = dict(sorted(unknown.items()))
    report['parser_passed'] = not report['parse_errors']
    return report


def prepare_repair_queue(records, outputs, glossary=None, attempts=None, max_retries=2):
    """Plan local repair packets; never invokes a translator or fabricates approval.

    attempts counts retries already actually executed by the caller. Structural
    failures receive at most two repair attempts; unresolved failures then move
    to manual review. Pure semantic warnings and unsupported branch layout are
    manual immediately because retranslating cannot prove those properties.
    """
    if max_retries != 2:
        raise ValueError('the project repair budget is exactly two retries')
    records, outputs = list(records), list(outputs)
    attempts = attempts or {}
    if any(not isinstance(n, int) or n < 0 for n in attempts.values()):
        raise ValueError('attempt counts must be nonnegative integers')
    report = validate_batch(records, outputs, glossary)
    indexed = {o['key']: o for o in outputs if isinstance(o, dict) and isinstance(o.get('key'), str)}
    checked = {r['key']: r for r in report['results']}
    plan = {'scope': 'repair_plan_only_no_translation', 'max_retries': 2, 'batch_errors': report['errors'],
            'retry': [], 'manual_review': [], 'accepted': []}
    for record in records:
        key = record['key']
        result = checked.get(key, {'valid': False, 'errors': [{'code': 'missing_output', 'message': 'missing translation'}],
                                   'warnings': [], 'manual_review': False})
        used = attempts.get(key, 0)
        if result['valid'] and not result['manual_review']:
            plan['accepted'].append(key)
        elif result['valid'] or used >= max_retries or any(e['code'] == 'unsupported_inline_branch' for e in result['errors']):
            plan['manual_review'].append({'key': key, 'attempts_used': used, 'validation': result})
        else:
            plan['retry'].append({'key': key, 'source': record['source'], 'context': record.get('context', {}),
                                  'width_hint': record.get('width_hint'),
                                  'glossary': relevant_glossary(record['source'], glossary or record.get('glossary', {}), record),
                                  'previous_output': indexed.get(key), 'errors': result['errors'],
                                  'warnings': result['warnings'], 'retry_number': used + 1})
    return plan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--translations', type=Path)
    p.add_argument('--audit-source', action='store_true')
    p.add_argument('--glossary', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.audit_source:
        report = audit_source_records(iter_tm(a.source))
    else:
        if not a.translations:
            p.error('--translations is required unless --audit-source is selected')
        report = validate_batch(iter_tm(a.source), iter_tm(a.translations), load_glossary(a.glossary) if a.glossary else None)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if a.audit_source:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report['parser_passed'] else 1)
    print(json.dumps({'valid': report['valid'], 'counts': report['counts'], 'errors': report['errors']}, ensure_ascii=False))
    raise SystemExit(0 if report['valid'] else 1)


if __name__ == '__main__':
    main()

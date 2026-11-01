"""Private terminology inventory and conflict-aware draft workflow.

Only --extract reads game data. No network, game writes, approval fabrication or
implicit master writes. Root integrates reviewed candidates into glossary.tsv.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata

LAB = Path(__file__).resolve().parents[1]
FIELDS = ('english', 'hebrew', 'category', 'note')
TOKEN = re.compile(r'\{VAR [0-9A-Fa-f]{4}(?::[0-9A-Fa-f,]*)?\}')
TABLES = {
    'monsname': 'pokemon', 'event_pokename': 'pokemon_nickname',
    'wazaname': 'move', 'tokusei': 'ability', 'itemname': 'item',
    'itemname_plural': 'item_plural', 'dressup_item_name': 'clothing',
    'place_name': 'place', 'place_name_indirect': 'place_phrase',
    'place_name_out': 'place_phrase', 'place_name_spe': 'place_phrase',
    'place_name_per': 'place_phrase', 'trname': 'character',
    'namelist': 'character', 'trtype': 'trainer_class', 'typename': 'type',
    'statusname': 'stat', 'seikaku': 'nature', 'nuts_name': 'berry',
    'zkn_form': 'pokemon_form', 'zkn_type': 'species_class',
}
UI_TABLES = ('app_common', 'appli_header', 'bag_pocket', 'common_text',
             'initial', 'money_window', 'option_top', 'main_menu', 'option',
             'pokedex', 'status', 'pokelist', 'bag', 'box')
ITEM_FORMS = ('itemname', 'itemname_plural', 'itemname_acc',
              'itemname_classified', 'itemname_acc_classified',
              'itemname_plural_classified')


def normalize(s):
    return unicodedata.normalize('NFC', s).strip()


def read_glossary(path, allow_blank=True):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter='\t')
        if reader.fieldnames != list(FIELDS):
            raise ValueError('Expected four TSV columns: '+', '.join(FIELDS))
        rows = []
        for row in reader:
            if None in row: raise ValueError('Unexpected extra TSV fields')
            rows.append({k: normalize(row[k] or '') for k in FIELDS})
    validate_rows(rows, allow_blank=allow_blank)
    return rows


def validate_rows(rows, allow_blank=True):
    seen = {}
    for index, row in enumerate(rows, 2):
        if not row['english'] or not row['category']:
            raise ValueError(f'Empty term/category at TSV line {index}')
        if not allow_blank and not row['hebrew']:
            raise ValueError(f'Untranslated term at TSV line {index}')
        if any('\n' in row[k] or '\t' in row[k] for k in FIELDS):
            raise ValueError(f'Embedded delimiter/newline at TSV line {index}')
        key = (row['english'], row['category'])
        if key in seen:
            raise ValueError(f'Duplicate term/category {key!r}')
        seen[key] = row
        if any('\u0591' <= c <= '\u05c7' and unicodedata.category(c).startswith('M') for c in row['hebrew']):
            raise ValueError(f'Niqqud not allowed at TSV line {index}')
    return rows


def write_glossary(path, rows):
    rows = sorted(rows, key=lambda r: (r['category'], r['english'].casefold(), r['english']))
    validate_rows(rows)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, FIELDS, delimiter='\t', lineterminator='\n')
        w.writeheader(); w.writerows(rows)


def glossary_digest(path):
    """Digest exact bytes, matching packager approval sidecars; edits invalidate approval."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_approval(glossary_path, approval_path):
    approval = json.loads(Path(approval_path).read_text(encoding='utf-8'))
    expected = glossary_digest(glossary_path)
    return approval.get('approved') is True and approval.get('glossary_sha256') == expected


def merge_proposals(master_rows, proposals, locked_rows=()):
    """Keep accepted values, add unambiguous proposals; never silently resolve conflict.

    Return candidate rows and conflicts. Exact (English, category) is the key.
    A conflicting proposal against a locked spelling is recorded and rejected.
    Empty Hebrew is an explicit queue entry, never a translation.
    """
    result = {(r['english'], r['category']): dict(r) for r in master_rows}
    locked = {(r['english'], r['category']): dict(r) for r in locked_rows}
    conflicts = []
    for key, seed in locked.items():
        old = result.get(key)
        if old and old['hebrew'] and old['hebrew'] != seed['hebrew']:
            conflicts.append(dict(english=key[0], category=key[1], accepted=seed['hebrew'],
                                  proposed=[old['hebrew']], reason='locked_existing_mismatch'))
    result.update(locked)
    proposals_by_key = defaultdict(list)
    for r in proposals:
        proposals_by_key[(r['english'], r['category'])].append(r)
    for key, candidates in sorted(proposals_by_key.items()):
        translations = {r['hebrew'] for r in candidates if r['hebrew']}
        old = result.get(key)
        if old and old['hebrew']:
            if translations - {old['hebrew']}:
                conflicts.append(dict(english=key[0], category=key[1], accepted=old['hebrew'],
                                      proposed=sorted(translations), reason='locked' if key in locked else 'existing_translation'))
            continue
        if len(translations) > 1:
            conflicts.append(dict(english=key[0], category=key[1], accepted='',
                                  proposed=sorted(translations), reason='competing_proposals'))
            if old is None:
                result[key] = dict(english=key[0], hebrew='', category=key[1], note='status=conflict; manual decision required')
        elif translations:
            he = next(iter(translations)); chosen = next(r for r in candidates if r['hebrew'] == he)
            result[key] = dict(chosen)
        elif old is None:
            result[key] = dict(candidates[0])
    rows = sorted(result.values(), key=lambda r: (r['category'], r['english'].casefold(), r['english']))
    validate_rows(rows)
    return rows, conflicts


def ingest_new_terms(records, default_category='unclassified'):
    """Convert translator new_terms into a review queue, not accepted terminology.

    Returns unambiguous rows and explicit conflict records. Contextual category
    must be supplied by the caller or reviewed; the default never guesses it.
    """
    proposals = []
    for record in records:
        key = str(record.get('key', 'unknown'))
        for term in record.get('new_terms', []):
            en, he = term.get('en'), term.get('he')
            if not isinstance(en, str) or not isinstance(he, str) or not en.strip() or not he.strip():
                raise ValueError(f'Invalid new_terms entry in {key}')
            candidate = dict(english=normalize(en), hebrew=normalize(he),
                             category=normalize(term.get('category', default_category)),
                             note='status=new_term_proposal; not_approved; source_key='+key)
            validate_rows([candidate], allow_blank=False)
            proposals.append(candidate)
    return merge_proposals([], proposals)


def category_collisions(rows):
    groups = defaultdict(list)
    for row in rows: groups[row['english']].append(row)
    return [dict(english=en, categories={r['category']: r['hebrew'] for r in rs})
            for en, rs in sorted(groups.items()) if len({r['hebrew'] for r in rs if r['hebrew']}) > 1]


def _read_table(path):
    from gfmsg import MsgFile, decode_units, read_tbl
    m = MsgFile(path.read_bytes()); labels = [label for _, label in read_tbl(path.with_suffix('.tbl').read_bytes())]
    if len(labels) != len(m.lines) + 1: raise ValueError(f'Table cardinality: {path}')
    return [(label, decode_units(units), m.params[i], i) for i, (label, units) in enumerate(zip(labels, m.lines))]


def extract_inventory(extract=LAB/'extract', out=LAB/'terminology'):
    source_root = Path(extract)/'romfs'; english_root = source_root/'ik_message/dat/English'
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    indexed = {}; excluded = []; tables = {}; forms = defaultdict(dict)
    for name in ITEM_FORMS:
        p = english_root/'common'/(name+'.dat')
        if p.exists():
            for label, text, flags, index in _read_table(p): forms[label][name] = text
    candidates = [(english_root/'common'/(n+'.dat'), cat, False) for n, cat in TABLES.items()]
    candidates += [(english_root/'common'/(n+'.dat'), 'ui', True) for n in UI_TABLES]
    candidates += [(english_root/'sk/donut_name.dat', 'donut', False)]
    for path, category, short_only in candidates:
        if not path.exists(): continue
        rows = _read_table(path); counts = Counter()
        for label, text, flags, index in rows:
            text = normalize(text)
            reason = None
            if not text: reason = 'empty'
            elif TOKEN.search(text): reason = 'contains_control_tokens'
            elif not any(c.isalpha() for c in text): reason = 'placeholder_or_numeric'
            elif short_only and (len(text) > 48 or len(text.split()) > 5 or any(c in text for c in '\n?!') or text.endswith(('.', '…'))):
                reason = 'not_short_ui_term'
            ref = dict(file=path.relative_to(source_root).as_posix(), label=label, index=index, flags=flags)
            if reason:
                counts[reason] += 1; excluded.append(dict(source=text, reason=reason, **ref)); continue
            cat = 'pokemon_state' if path.stem == 'monsname' and index == 0 else category
            key = (text, cat)
            rec = indexed.setdefault(key, dict(english=text, category=cat, sources=[]))
            rec['sources'].append(ref); counts['included'] += 1
            if cat in ('item', 'item_plural'):
                related = forms[label]
                rec.setdefault('forms', []).append(dict(label=label, singular=related.get('itemname', ''),
                    plural=related.get('itemname_plural', ''), variants=related))
        tables[path.relative_to(source_root).as_posix()] = dict(counts)
    records = sorted(indexed.values(), key=lambda r: (r['category'], r['english'].casefold(), r['english']))
    with (out/'inventory.jsonl').open('w', encoding='utf-8') as f:
        for rec in records: f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True)+'\n')
    with (out/'excluded.jsonl').open('w', encoding='utf-8') as f:
        for rec in excluded: f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True)+'\n')
    counts = dict(Counter(r['category'] for r in records))
    summary = dict(unique_term_categories=len(records), category_counts=counts, source_tables=tables,
                   excluded_counts=dict(Counter(r['reason'] for r in excluded)),
                   provenance='Decoded English 2.0.2 GFMSG label tables; no inferred names or fabricated row counts.')
    (out/'inventory-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    queues = out/'queues'; queues.mkdir(exist_ok=True)
    for cat in counts:
        with (queues/(cat+'.jsonl')).open('w', encoding='utf-8') as f:
            for rec in records:
                if rec['category'] == cat: f.write(json.dumps(rec, ensure_ascii=False)+'\n')
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    e = sub.add_parser('extract'); e.add_argument('--extract', type=Path, default=LAB/'extract'); e.add_argument('--out', type=Path, default=LAB/'terminology')
    d = sub.add_parser('digest'); d.add_argument('path', type=Path)
    m = sub.add_parser('merge'); m.add_argument('--master', type=Path, required=True); m.add_argument('--proposal', type=Path, action='append', required=True)
    m.add_argument('--locked', type=Path, default=LAB/'terminology/seed.tsv'); m.add_argument('--out', type=Path, required=True); m.add_argument('--conflicts', type=Path, required=True)
    n = sub.add_parser('ingest-new-terms'); n.add_argument('--input',type=Path,required=True)
    n.add_argument('--out',type=Path,required=True); n.add_argument('--conflicts',type=Path,required=True)
    n.add_argument('--category',default='unclassified')
    a = p.parse_args()
    if a.command == 'extract': print(json.dumps(extract_inventory(a.extract, a.out), ensure_ascii=False, indent=2))
    elif a.command == 'digest': print(glossary_digest(a.path))
    elif a.command == 'ingest-new-terms':
        if a.out.resolve() == (LAB/'glossary.tsv').resolve():p.error('Root owns glossary.tsv; ingest to a proposal queue')
        records=[json.loads(line) for line in a.input.read_text(encoding='utf-8').splitlines() if line.strip()]
        rows,conflicts=ingest_new_terms(records,a.category);write_glossary(a.out,rows)
        a.conflicts.parent.mkdir(parents=True,exist_ok=True)
        a.conflicts.write_text(json.dumps(conflicts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(proposed=len(rows),conflicts=len(conflicts))))
    else:
        if a.out.resolve() == (LAB/'glossary.tsv').resolve(): p.error('Root owns glossary.tsv; merge to a review candidate instead')
        proposals = [r for path in a.proposal for r in read_glossary(path)]
        rows, conflicts = merge_proposals(read_glossary(a.master), proposals, read_glossary(a.locked))
        write_glossary(a.out, rows); a.conflicts.parent.mkdir(parents=True, exist_ok=True)
        a.conflicts.write_text(json.dumps(dict(conflicts=conflicts, category_collisions=category_collisions(rows)), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(dict(rows=len(rows), conflicts=len(conflicts), sha256=glossary_digest(a.out))))

if __name__ == '__main__': main()

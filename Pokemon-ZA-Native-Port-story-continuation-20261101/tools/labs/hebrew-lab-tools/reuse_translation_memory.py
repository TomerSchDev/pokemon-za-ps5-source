"""Conservative reuse of identical, previously edited messages.

Never reuse a generic word such as Move or Next across UI meanings. Story
messages require an identical source, control stream, category, window type and
player-gender suffix; conflicting edited versions remain a manual decision.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import re

UI_SAFE = frozenset(('Yes', 'No', 'Cancel', 'Confirm', 'Back', 'Close', 'Sort',
                     'Select', 'Reset'))


def signature(record):
    gender = re.search(r'_([fm])$', record.get('label', ''))
    context = record.get('context', {})
    return (record['source'], context.get('category'), context.get('window_type'),
            gender[1] if gender else '')


def reuse(records, edited):
    keyed = {row['key']: row for row in records}
    memory = defaultdict(dict)
    for key, row in edited.items():
        if key in keyed and re.search('[א-ת]', row['he']):
            memory[signature(keyed[key])].setdefault(row['he'], row)
    output = []
    for record in records:
        if record['key'] in edited or not record.get('requires_translation'):
            continue
        category = record.get('context', {}).get('category')
        if not (category == 'story' or category == 'ui' and record['source'] in UI_SAFE):
            continue
        candidates = memory.get(signature(record), {})
        if len(candidates) != 1:
            continue
        exemplar = next(iter(candidates.values()))
        row = deepcopy(exemplar)
        row.update(key=record['key'], new_terms=[], note='Exact edited translation-memory reuse; context and player-gender bucket matched',
                   reuse_provenance=dict(exemplar_key=exemplar['key'],
                                         source_sha256=hashlib.sha256(record['source'].encode('utf-8')).hexdigest(),
                                         exact_source_and_controls=True,
                                         category=category,
                                         visual_qa_pending=True))
        output.append(row)
    return output

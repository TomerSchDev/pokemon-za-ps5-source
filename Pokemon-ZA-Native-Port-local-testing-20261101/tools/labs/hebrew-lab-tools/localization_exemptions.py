"""Narrow source-bound identifiers and attribution names; never exempt arbitrary prose."""
from functools import lru_cache
import json
from pathlib import Path
import re

ITEM_TABLES=frozenset('ik_message/dat/English/common/'+stem+'.dat' for stem in (
    'itemname','itemname_acc','itemname_classified','itemname_acc_classified',
    'itemname_plural','itemname_plural_classified'))
CODE=re.compile(r'(?:TM|TR|HM)\d{2,3}|★[A-Z][A-Za-z]{1,2}\d{1,4}')

def preserved_item_identifier(record):
    if record.get('file') not in ITEM_TABLES:return None
    source=record.get('source','')
    if '_plural' in record['file'] and source.endswith('s'):source=source[:-1]
    return source if CODE.fullmatch(source) else None


ALPHABET_FILE='ik_message/dat/English/common/initial.dat'
ALPHABET_SOURCE_SHA256='85f157279d39f95cef4464d8f12a5ccdfd6ff7635e295d3473f89a1e19dd03a2'
ALPHABET_GLYPHS='ABCDEFGHIJKLMNOPQRSTUVWXYZヒフヘホマミムメモヤユヨラリルレロワヲン'

def preserved_alphabet_index(record):
    """Exact alphabet index glyphs; row zero (Numbers) remains prose.

    Keep the native index alphabet intact. File hash, key, index and glyph
    must all match the inspected source table. Never counted as Hebrew.
    """
    index=record.get('line_index')
    if (record.get('file')!=ALPHABET_FILE or record.get('source_file_sha256')!=ALPHABET_SOURCE_SHA256
            or not isinstance(index,int) or not 1<=index<=len(ALPHABET_GLYPHS)):
        return None
    glyph=ALPHABET_GLYPHS[index-1]
    if (record.get('key')!=ALPHABET_FILE+f':initial_{index-1:02d}'
            or record.get('source')!=glyph):
        return None
    return glyph


STORY_CODE_FILE='ik_message/dat/English/sk/sub_140.dat'
STORY_CODE_SOURCE_SHA256='f14f78176809f09e96374eb831e2d041d66acdeb25be924065c23f57a32545b5'
STORY_CODES={20:'Gp5BIatW',21:'Gp58JatW',22:'GqS8JatM',23:'GqSBLatM'}

def preserved_story_code(record):
    """Four case-sensitive puzzle answers, including distractors, are not prose.

    The surrounding password instructions still require Hebrew. Only the four
    exact inspected source rows are exempt, and their installed values must be
    identical. This never exempts arbitrary Latin dialogue or other passwords.
    """
    index=record.get('line_index')
    if (record.get('file')!=STORY_CODE_FILE or record.get('source_file_sha256')!=STORY_CODE_SOURCE_SHA256
            or index not in STORY_CODES):
        return None
    code=STORY_CODES[index]
    if (record.get('key')!=STORY_CODE_FILE+f':msg_Ev_sub_140_10_select_{index-19:02d}'
            or record.get('source')!=code):
        return None
    return code


CREDIT_CATALOG=Path(__file__).resolve().parents[1]/'translations/credit-attributions-reviewed-20261030-r1.json'
CREDIT_FILES=frozenset(('ik_message/dat/English/common/staff_list.dat','ik_message/dat/English/sk/sa_staff_list.dat'))

@lru_cache(maxsize=1)
def _credit_catalog():
    data=json.loads(CREDIT_CATALOG.read_text(encoding='utf-8'))
    rows={r['key']:r for r in data['rows']}
    if len(rows)!=len(data['rows']):raise ValueError('Duplicate reviewed credit attribution')
    if any(r['file'] not in CREDIT_FILES or r['kind'] not in
           {'person_name','organization_name','copyright_attribution'} for r in rows.values()):
        raise ValueError('Invalid reviewed credit attribution category')
    return rows

def preserved_credit_attribution(record):
    """Exact inspected creator names/owner signatures only; never roles or sentences.

    Titles, LEAD prefixes, generic company labels and rights prose are Hebrew.
    These fixed rows keep original attribution spelling and are verified intact,
    separately from translated language coverage. New source tables fail closed.
    """
    if record.get('file') not in CREDIT_FILES:return None
    approved=_credit_catalog().get(record.get('key'))
    if approved is None:return None
    if any(record.get(field)!=approved[field] for field in
           ('file','line_index','source_file_sha256','source')):return None
    return approved['source']

def preserved_literal(record):
    """An exact identifier/attribution to verify, or None for ordinary language."""
    return (preserved_item_identifier(record) or preserved_alphabet_index(record)
            or preserved_story_code(record) or preserved_credit_attribution(record))

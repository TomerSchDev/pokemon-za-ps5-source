"""Freeze the inspected move lexicon and expand four exact battle templates.

All source/target move pairs were read during the editorial pass. This uses no
machine translation. It preserves names already used by the story modules.
"""
import csv
import json
from pathlib import Path
import re
from build_hebrew_project import MODULES, load_module
from translation_memory import iter_tm

LAB = Path(__file__).resolve().parents[1]
CORRECTIONS = {
    'Disable': 'השבתה', 'Mirror Move': 'מתקפת מראה', 'Tri Attack': 'מתקפה משולשת',
    'Twister': 'סחרור', 'Whirlpool': 'מערבולת מים', 'Sky Uppercut': 'אגרוף שמימי',
    'Assurance': 'וידוא פגיעה', 'Vacuum Wave': 'גל ואקום',
    'Flare Blitz': 'הסתערות לוהטת', 'Reflect Type': 'שיקוף סוג',
    'Mat Block': 'חסימה במחצלת', 'Multi-Attack': 'מתקפה רב-סוגית',
    'Population Bomb': 'התפוצצות אוכלוסין', 'Kowtow Cleave': 'שיסוף קידה',
    'Chilly Reception': 'קבלת פנים קרירה', 'Supercell Slam': 'הטחת סופת על',
}

def main():
    target = LAB/'translations/moves-battle-editorial-20261030-r1.json'
    if target.exists():
        raise FileExistsError('Preserve the frozen editorial snapshot')
    names = {r['english']: r['hebrew'] for r in csv.DictReader(
        (LAB/'glossary.tsv').open(encoding='utf-8-sig'), delimiter='\t') if r['category']=='move'}
    names.update(CORRECTIONS)
    for name in MODULES:
        module=load_module(name)
        for table in getattr(module,'TABLES',[module]):
            for en,he in table.TERMS.items():
                if en in names:
                    names[en]=he
    records=list(iter_tm(LAB/'memory/english-source.jsonl'))
    tables={}
    for r in records:
        if not r['requires_translation']:
            continue
        file=Path(r['file']).name
        if file=='wazaname.dat':
            he=names.get(r['source'])
            if he is None:
                if r['source']!='———':raise ValueError(r['key'])
                he=r['source']
        elif file=='btl_attack.dat':
            source=r['source']
            if source=='!':he='!'
            else:
                m=re.fullmatch(r'(\{VAR 0102:0000\}|The wild \{VAR 0102:0000\}|The opposing \{VAR 0102:0000\}|\{VAR 0100:000A\}’s \{VAR 0102:0000\}) used (.+)!',source)
                if not m or m[2] not in names:raise ValueError('Unreviewed battle template: '+r['key'])
                subject={'{VAR 0102:0000}':'{VAR 0102:0000}',
                         'The wild {VAR 0102:0000}':'{VAR 0102:0000} הפראי',
                         'The opposing {VAR 0102:0000}':'{VAR 0102:0000} היריב',
                         '{VAR 0100:000A}’s {VAR 0102:0000}':'{VAR 0102:0000} של {VAR 0100:000A}'}[m[1]]
                he=subject+' השתמש במתקפה '+names[m[2]]+'!'
        elif file=='zkn_weight.dat':
            m=re.fullmatch(r'([0-9?,.]+) lbs\.',r['source'])
            if not m:raise ValueError('Unreviewed unit pattern: '+r['key'])
            he=m[1]+' ליברות'
        else:continue
        tables.setdefault(r['file'],[]).append(dict(index=r['line_index'],source=r['source'],he=he))
    target.write_text(json.dumps(dict(status='assistant_editorial_candidate',
        review='Every move pair inspected; fixed battle subjects preserve nickname and owner variables; original weight numbers and imperial units retained',
        visual_qa_pending=True,tables=tables),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:len(v) for k,v in tables.items()}))

if __name__=='__main__':main()

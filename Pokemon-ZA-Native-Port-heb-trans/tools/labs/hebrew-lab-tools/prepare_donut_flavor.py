"""Compile complete reviewed donut effect families, frozen to every source row."""
import json
import re
from pathlib import Path
from translation_memory import iter_tm

LAB=Path(__file__).resolve().parents[1]
FILE='ik_message/dat/English/sk/donut_flavor.dat'
OUTPUT=LAB/'translations/donut-flavor-editorial-20261030-r1.json'
TYPES={'Normal':'רגיל','Fire':'אש','Water':'מים','Electric':'חשמל','Grass':'עשב','Ice':'קרח',
       'Fighting':'לחימה','Poison':'רעל','Ground':'אדמה','Flying':'מעופף','Psychic':'על־חושי',
       'Bug':'חרק','Rock':'סלע','Ghost':'רוח','Dragon':'דרקון','Dark':'אופל','Steel':'פלדה','Fairy':'פיה'}
AMOUNTS={'a little':'מעט','quite a bit':'במידה ניכרת','a lot':'מאוד'}
NAMES={
 'Alpha Power':'כוח אלפא','Sparkling Power: @TYPE@':'כוח זוהר: @TYPE@',
 'Sparkling Power: All Types':'כוח זוהר: כל הסוגים','Attack Power':'כוח התקפה',
 'Sp. Atk Power':'כוח התקפה מיוחדת','Move Power: @TYPE@':'כוח מתקפה: @TYPE@',
 'Speed Power':'כוח מהירות','Big Haul Power':'כוח שלל רב',
 'Item Power: Berries':'כוח חפצים: פירות יער','Item Power: Candies':'כוח חפצים: סוכריות',
 'Item Power: Treasure':'כוח חפצים: אוצרות','Item Power: Poké Balls':'כוח חפצים: פוקדורים',
 'Item Power: Special':'כוח חפצים: מיוחדים','Item Power: Coins':'כוח חפצים: מטבעות',
 'Mega Power Charging':'טעינת כוח מגה','Mega Power Conservation':'שימור כוח מגה',
 'Defense Power':'כוח הגנה','Sp. Def Power':'כוח הגנה מיוחדת',
 'Resistance Power: @TYPE@':'כוח עמידות: @TYPE@','Humungo Power':'כוח ענקים','Teensy Power':'כוח זעירים',
 'Encounter Power':'כוח מפגשים','Catching Power: @TYPE@':'כוח לכידה: @TYPE@',
 'Catching Power: All Types':'כוח לכידה: כל הסוגים','Pitch-Black Power':'כוח שחור משחור',
 'Ruby-Red Power':'כוח אדום כאודם','Sapphire-Blue Power':'כוח כחול כספיר',
 'Emerald-Green Power':'כוח ירוק כאזמרגד','Thunderclap Power':'כוח רעם',
}

def compile_text(source,templates):
    text=re.sub(r'\s+',' ',source).strip();subs={}
    def type_sub(m):
        if '@TYPE@' in subs:raise ValueError('Unexpected repeated type')
        subs['@TYPE@']=TYPES[m[0]];return '@TYPE@'
    text=re.sub(r'\b(?:'+'|'.join(TYPES)+r')\b',type_sub,text)
    level=re.fullmatch(r'(.+) \(Lv\. ([123])\)',text)
    name=level[1] if level else text
    if name in NAMES:
        result=NAMES[name]+(f' (רמה {level[2]})' if level else '')
    else:
        def amount_sub(m):
            if '@A@' in subs:raise ValueError('Unexpected repeated intensity')
            subs['@A@']=AMOUNTS[m[0]];return '@A@'
        text=re.sub(r'a little|quite a bit|a lot',amount_sub,text)
        if text not in templates:raise ValueError('Unreviewed donut source: '+source)
        result=templates[text]
    for marker,value in subs.items():result=result.replace(marker,value)
    result=re.sub(r'\s+',' ',result.replace('@A@','')).strip()
    if '@TYPE@' in result:raise ValueError('Unbound type')
    return result

def main():
    if OUTPUT.exists():raise FileExistsError('Preserve frozen revision')
    templates={}
    for line in (LAB/'translations/donut-flavor-templates-20261030-r1.txt').read_text(encoding='utf-8').splitlines():
        en,he=line.split('|',1);templates[en]=he
        if ' @A@' in en and 'by @A@' not in en:
            fallback=en.replace(' @A@','')
            templates.setdefault(fallback,he.replace(' @A@',''))
    rows=[dict(index=r['line_index'],source=r['source'],he=compile_text(r['source'],templates))
          for r in iter_tm(LAB/'memory/english-source.jsonl') if r['file']==FILE and r['requires_translation']]
    OUTPUT.write_text(json.dumps(dict(file=FILE,rows=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),source_bound=True)))

if __name__=='__main__':main()

"""Expand explicitly edited battle sentences and inspected stat-change patterns."""
import json
from pathlib import Path
import re
from battle_set_templates import normalize
from build_hebrew_project import MODULES,load_module,authored_rows
from translation_memory import iter_tm

LAB=Path(__file__).resolve().parents[1]
STATS={'Attack':('התקפה','f'),'Defense':('הגנה','f'),'Sp. Atk':('התקפה מיוחדת','f'),
       'Sp. Def':('הגנה מיוחדת','f'),'Speed':('מהירות','f'),'accuracy':('דיוק','m'),
       'evasiveness':('התחמקות','f'),'stats':('נתונים','p')}

def stat_sentence(text):
    m=re.fullmatch(r'(@p[0-9A-F]+@)’s (.+?) (rose|rose sharply|rose drastically|fell|harshly fell|severely fell|won’t go any higher|won’t go any lower|was not lowered|was heightened|returned to normal)!',text)
    if m and m[2] in STATS:
        subject,stat,verb=m.groups();he,gender=STATS[stat]
        forms={
          'rose':('עלה','עלתה'),'rose sharply':('עלה מאוד','עלתה מאוד'),
          'rose drastically':('עלה בצורה קיצונית','עלתה בצורה קיצונית'),
          'fell':('ירד','ירדה'),'harshly fell':('ירד מאוד','ירדה מאוד'),
          'severely fell':('ירד בצורה קיצונית','ירדה בצורה קיצונית'),
          'won’t go any higher':('לא יכול לעלות יותר','לא יכולה לעלות יותר'),
          'won’t go any lower':('לא יכול לרדת יותר','לא יכולה לרדת יותר'),
          'was not lowered':('לא ירד','לא ירדה'),'was heightened':('התגבר','התגברה'),
          'returned to normal':('חזר למצב הרגיל','חזרה למצב הרגיל')}
        return 'ה'+he+' של '+subject+' '+forms[verb][gender=='f']+'!'
    m=re.fullmatch(r'The (\{VAR 0109:0001\}) (?:(sharply|drastically) )?boosted (?:(@p[0-9A-F]+@)’s (.+)|the (.+) of (@p[0-9A-F]+@))!',text)
    if m:
        item,level,subject,stat,stat2,subject2=m.groups();stat=stat or stat2;subject=subject or subject2
        if stat in STATS:
            intensity={None:'','sharply':' מאוד','drastically':' בצורה קיצונית'}[level]
            return 'החפץ '+item+' העלה'+intensity+' את ה'+STATS[stat][0]+' של '+subject+'!'
    m=re.fullmatch(r'(@p[0-9A-F]+@) boosted its (.+?)(?: (sharply|drastically))? using its Z-Power!',text)
    if m and m[2] in STATS:
        intensity={None:'','sharply':' מאוד','drastically':' בצורה קיצונית'}[m[3]]
        return m[1]+' העלה'+intensity+' את ה'+STATS[m[2]][0]+' שלו בעזרת כוח זי!'
    return None

def main():
    out=LAB/'translations/battle-set-editorial-20261030-r2.json'
    if out.exists():raise FileExistsError(out)
    records=list(iter_tm(LAB/'memory/english-source.jsonl'));keyed={r['key']:r for r in records}
    terms={}
    for name in MODULES:
        if name.startswith('battle-set-full-'):continue
        module=load_module(name)
        for table in getattr(module,'TABLES',[module]):
            if any(table.FILE.endswith('/'+n+'.dat') for n in ('tokusei','wazaname','itemname')):
                for row in authored_rows(table,records):terms[keyed[row['key']]['source']]=row['he']
    terms.update({'G-Max Wildfire':'להבת ג׳י-מקס','G-Max Volcalith':'סלעי ג׳י-מקס',
                  'G-Max Vine Lash':'הצלפת גפני ג׳י-מקס','G-Max Cannonade':'מטח ג׳י-מקס'})
    manual={}
    for line in (LAB/'translations/battle-set-edits-20261030-r1.txt').read_text(encoding='utf-8').splitlines():
        indices,he=line.split('|',1)
        for i in map(int,indices.split(',')):
            if i in manual:raise ValueError('duplicate '+str(i))
            manual[i]=he
    used_terms={}
    def expand_term(m):
        he=terms[m[1]];used_terms[m[1]]=he;return he
    file='ik_message/dat/English/common/btl_set.dat';templates={};rows=[];missing=[]
    for r in records:
        if r['file']!=file or not r['requires_translation']:continue
        source,values=normalize(r['source'])
        if source not in templates:
            he=manual.get(r['line_index']) or stat_sentence(source)
            if he is None:missing.append((r['line_index'],source));continue
            templates[source]=re.sub(r'\[\[(.+?)\]\]',expand_term,he)
        he=templates[source]
        he=re.sub(r'@p[0-9A-F]+@',lambda m:values[m[0]].pop(0),he)
        if any(values.values()):raise ValueError((r['line_index'],'unconsumed subject occurrence'))
        if '@p' in he:raise ValueError((r['line_index'],'unresolved subject'))
        rows.append(dict(index=r['line_index'],source=r['source'],he=he))
    if missing:raise ValueError(missing)
    assert len(rows)==2286
    data=dict(status='assistant editorial; all battle set sentences inspected; visual QA pending',
              local_terms=used_terms,tables={file:rows})
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),templates=len(templates),local_terms=used_terms),ensure_ascii=False))

if __name__=='__main__':main()

"""Freeze complete Pokédex category labels from explicitly authored terminology."""
import json
from pathlib import Path
from translation_memory import iter_tm
LAB=Path(__file__).resolve().parents[1]
FILE='ik_message/dat/English/common/zkn_type.dat'
OUTPUT=LAB/'translations/pokedex-categories-editorial-20261030-r2.json'
def main():
    if OUTPUT.exists():raise FileExistsError('Preserve previous frozen revision')
    pairs=[line.split('|',1) for line in (LAB/'translations/pokedex-categories-20261030-r2.txt').read_text(encoding='utf-8').splitlines()]
    terms={en+' Pokémon':'פוקימון '+he for en,he in pairs}
    if len(terms)!=len(pairs):raise ValueError('Duplicate editorial category')
    rows=[];used=set()
    for r in iter_tm(LAB/'memory/english-source.jsonl'):
        if r['file']!=FILE or not r['requires_translation']:continue
        if r['source'] not in terms:raise ValueError('Unreviewed category: '+r['source'])
        used.add(r['source'])
        rows.append(dict(index=r['line_index'],source=r['source'],he=terms[r['source']]))
    if used!=set(terms):raise ValueError('Unused editorial category')
    OUTPUT.write_text(json.dumps(dict(file=FILE,rows=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),unique_categories=len(used),source_bound=True)))
if __name__=='__main__':main()

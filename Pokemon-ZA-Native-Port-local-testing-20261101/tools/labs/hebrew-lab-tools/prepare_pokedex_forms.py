"""Freeze every form label from reviewed names and explicit editorial form terms."""
import json
import re
from pathlib import Path
from translation_memory import iter_tm
from prepare_donut_flavor import TYPES

LAB=Path(__file__).resolve().parents[1]
FILE='ik_message/dat/English/common/zkn_form.dat'
OUTPUT=LAB/'translations/pokedex-forms-editorial-20261030-r1.json'

def main():
    if OUTPUT.exists():raise FileExistsError('Preserve previous frozen revision')
    names_data=json.loads((LAB/'translations/species-editorial-20261030-r1.json').read_text(encoding='utf-8'))
    names={r['source']:r['he'] for rows in names_data['tables'].values() for r in rows}
    terms=dict(line.split('|',1) for line in (LAB/'translations/pokedex-forms-20261030-r1.txt').read_text(encoding='utf-8').splitlines())
    terms.update({'Type: '+en:'סוג: '+he for en,he in TYPES.items()})
    rows=[]
    for r in iter_tm(LAB/'memory/english-source.jsonl'):
        if r['file']!=FILE or not r['requires_translation']:continue
        source=r['source'];he=terms.get(source,names.get(source))
        if he is None and source.startswith('Mega '):
            match=re.fullmatch(r'Mega (.+?)( [XYZ])?',source)
            if match and match[1] in names:he='מגה-'+names[match[1]]+(match[2] or '')
        if he is None:raise ValueError('Unreviewed form: '+source)
        rows.append(dict(index=r['line_index'],source=source,he=he))
    OUTPUT.write_text(json.dumps(dict(file=FILE,rows=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),source_bound=True)))

if __name__=='__main__':main()

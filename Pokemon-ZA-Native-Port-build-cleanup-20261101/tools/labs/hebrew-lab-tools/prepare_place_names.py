"""Freeze all direct and inflected place names with explicit local terminology."""
import csv,json,re
from pathlib import Path
from translation_memory import iter_tm
LAB=Path(__file__).resolve().parents[1]
OUTPUT=LAB/'translations/places-editorial-20261030-r2.json'
DISTRICTS={'Vert':'ור','Bleu':'בלו','Magenta':"מג'נטה",'Rouge':"רוז'",'Jaune':'ז׳ון'}
def main():
    if OUTPUT.exists():raise FileExistsError('Preserve frozen revision')
    known={r['english']:r['hebrew'] for r in csv.DictReader((LAB/'translations/full-hebrew-20261030-r40-terms.tsv').open(encoding='utf-8'),delimiter='\t') if not r['category'].startswith('file:')}
    terms=dict(line.split('|',1) for line in (LAB/'translations/places-20261030-r2.txt').read_text(encoding='utf-8').splitlines())
    records=list(iter_tm(LAB/'memory/english-source.jsonl'))
    direct=[r for r in records if r['file'].endswith('/common/place_name.dat') and r['requires_translation']]
    for r in direct:
        s=r['source']
        if s in terms:continue
        if s in known:terms[s]=known[s];continue
        if s in ('——————','???'):terms[s]=s;continue
        m=re.fullmatch(r'(Vert|Bleu|Magenta|Rouge|Jaune) (Street|Sector (\d+)|Plaza)',s)
        if m:
            d=DISTRICTS[m[1]]
            terms[s]=('רחוב '+d if m[2]=='Street' else 'כיכר '+d if m[2]=='Plaza' else 'אזור '+m[3]+' ב'+d);continue
        m=re.fullmatch(r'(Vert|Bleu|Magenta|Rouge|Jaune|Centrico|Hibernal|Vernal) Pokémon Center',s)
        if m:terms[s]='מרכז הפוקימונים '+{**DISTRICTS,'Centrico':'סנטריקו','Hibernal':'היברנל','Vernal':'ורנל'}[m[1]];continue
        if s=='Magenta Plaza Pokémon Center':terms[s]="מרכז הפוקימונים בכיכר מג'נטה";continue
        m=re.fullmatch(r'Wild Zone (\d+)',s)
        if m:terms[s]='אזור פרא '+m[1];continue
        m=re.fullmatch(r'Room (\d+)',s)
        if m:terms[s]='חדר '+m[1];continue
        raise ValueError('Unreviewed place: '+s)
    inverse={en.casefold():he for en,he in terms.items()}
    indirect_exceptions={
      '空き部屋(廃ビル)':'בחדר ריק (בניין נטוש)',
      '地下水道入口':'בכניסה לביוב',
      'at Nouveau Café’s Truck No. 2':'במשאית מס׳ 2 של קפה נובו',
      'at Nouveau Café’s Truck No. 3':'במשאית מס׳ 3 של קפה נובו',
      'at the entrance to Lysandre Labs':'בכניסה למעבדות ליסנדר',
      'at the entrance to the Lumiose Sewers':'בכניסה לביוב של לומיוז',
      'in the sewers':'בביוב',
    }
    tables={}
    for r in records:
        if not r['requires_translation'] or not any(r['file'].endswith('/common/'+f) for f in ('place_name.dat','place_name_indirect.dat')):continue
        s=r['source']
        if r['file'].endswith('/place_name.dat'):he=terms[s]
        elif s in indirect_exceptions:he=indirect_exceptions[s]
        elif s=='——————':he=s
        else:
            m=re.fullmatch(r'(in|at|on|along) (?:(?:the|a|an) )?(.+)',s)
            if not m or m[2].casefold() not in inverse:raise ValueError('Unreviewed inflection: '+s)
            base=inverse[m[2].casefold()]
            he='לאורך '+base if m[1]=='along' else 'ב'+(base[1:] if base in ('השדרה הדרומית','השדרה הצפונית','הביוב של לומיוז','הביוב','הכניסה למעבדות ליסנדר','הכניסה לביוב של לומיוז') else base)
        tables.setdefault(r['file'],[]).append(dict(index=r['line_index'],source=s,he=he))
    OUTPUT.write_text(json.dumps(dict(tables=tables),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({f:len(rows) for f,rows in tables.items()}))
if __name__=='__main__':main()

"""Freeze full donut names; retain both dynamic name parts and all berry identities."""
import json,re
from pathlib import Path
from translation_memory import iter_tm
LAB=Path(__file__).resolve().parents[1]
FILE='ik_message/dat/English/sk/donut_name.dat'
OUTPUT=LAB/'translations/donut-names-editorial-20261030-r1.json'
KINDS={'Meringue':'מרנג','Curry':'קארי','Jam':'ריבה','Chocolate':'שוקולד','Cream':'קרם','Rainbow':'קשת'}
SPECIAL={
 'Bad Dreams Cruller':'קרולר סיוטים',
 'Omega Old-Fashioned Donut':'דונאט קלאסי אומגה',
 'Alpha Old-Fashioned Donut':'דונאט קלאסי אלפא',
 'Delta Old-Fashioned Donut':'דונאט קלאסי דלתא',
 'Plasma-Glazed Donut':'דונאט בציפוי פלזמה',
 'N/A':'לא זמין',
 ' Imposing':' מרשים',' Sparkly':' נוצץ',' Mighty':' אדיר',' Smart':' חכם',
 ' Movetastic':' מצטיין במתקפות',' Quick':' זריז',' Lavish':' שופע',' Bountiful':' עתיר שלל',
 ' Candied':' מסוכר',' Treasured':' יקר ערך',' Ballistic':' עתיר פוקדורים',
 ' Remarkable':' יוצא דופן',' Gilt':' מוזהב',' Energizing':' ממריץ',' Enduring':' עמיד',
 ' Tough':' קשוח',' Courageous':' אמיץ',' Protective':' מגן',' Humungo':' ענקי',
 ' Teensy':' זעיר',' Tempting':' מפתה',' Inescapable':' שאין ממנו מנוס',
}
def main():
    if OUTPUT.exists():raise FileExistsError('Preserve frozen revision')
    data=json.loads((LAB/'translations/items-editorial-20261030-r1.json').read_text(encoding='utf-8'))
    items={r['source']:r['he'] for rows in data['tables'].values() for r in rows}
    rows=[]
    for r in iter_tm(LAB/'memory/english-source.jsonl'):
        if r['file']!=FILE or not r['requires_translation']:continue
        s=r['source'];he=SPECIAL.get(s)
        if he is None:
            m=re.fullmatch(r'(\{VAR 01D9:0001\}\{VAR 0133:0000\}) ([A-Za-z]+) (Meringue|Curry|Jam|Chocolate|Cream|Rainbow) Donut',s)
            if not m or m[2]+' Berry' not in items:raise ValueError('Unreviewed donut: '+s)
            berry=items[m[2]+' Berry']
            if not berry.startswith('פרי '):raise ValueError('Unexpected reviewed berry morphology')
            # Hebrew adjectives follow the noun. Both dynamic tokens and their
            # indices are preserved, and the inserted adjective has its own space.
            he='דונאט'+m[1]+' '+KINDS[m[3]]+' ו'+berry[4:]
        rows.append(dict(index=r['line_index'],source=s,he=he))
    OUTPUT.write_text(json.dumps(dict(file=FILE,rows=rows,qa_pending=['Dynamic adjective/name assembly and width in donut UI']),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),source_bound=True)))
if __name__=='__main__':main()

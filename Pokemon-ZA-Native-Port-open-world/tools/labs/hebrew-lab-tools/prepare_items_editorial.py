"""Generate frozen item forms from inspected semantic families and spellings.

No reading-draft machine translation is used. Original source labels connect
the six inflected tables; every row is frozen against its exact source text.
"""
import importlib.util
import json
from pathlib import Path
from collections import Counter
from build_hebrew_project import MODULES, load_module, authored_rows
from translation_memory import iter_tm

LAB=Path(__file__).resolve().parents[1]
EDITS='''
None|אין|אין
Terrain Extender|מאריך שדה|מאריכי שדה
Weakness Policy|פוליסת חולשה|פוליסות חולשה
Blunder Policy|פוליסת החטאה|פוליסות החטאה
Loaded Dice|קוביות מוטות|קוביות מוטות
Cell Battery|סוללה|סוללות
Power Anklet|צמיד קרסול עוצמתי|צמידי קרסול עוצמתיים
Lumiose Galette|גאלט לומיוז|גאלטים של לומיוז
Super Lumiose Galette|גאלט לומיוז משופר|גאלטים משופרים של לומיוז
Quick Claw|טופר זריז|טפרים זריזים
Academy Tablecloth|מפת האקדמיה|מפות האקדמיה
Battle Tablecloth|מפת קרב|מפות קרב
Hyperspace Butter|חמאת מרחב-על|חמאות מרחב-על
Eviolite|אבוליט|אבוליטים
'''
BERRIES='''
Aguav|אגואב
Apicot|אפיקוט
Aspear|אספיר
Babiri|באבירי
Belue|בלו
Bluk|בלאק
Charti|צ'רטי
Cheri|צ'רי
Chesto|צ'סטו
Chilan|צ'ילן
Chople|צ'ופל
Coba|קובה
Colbur|קולבר
Cornn|קורן
Custap|קאסטאפ
Durin|דורין
Enigma|אניגמה
Figy|פיגי
Ganlon|גנלון
Grepa|גרפה
Haban|הבן
Hondew|הונדו
Iapapa|יאפאפה
Jaboca|ג'בוקה
Kasib|קסיב
Kebia|קביה
Kee|קי
Kelpsy|קלפסי
Lansat|לנסט
Leppa|לפה
Liechi|ליצ'י
Lum|לאם
Mago|מאגו
Magost|מגוסט
Maranga|מרנגה
Micle|מיקל
Nanab|ננאב
Nomel|נומל
Occa|אוקה
Oran|אורן
Pamtre|פמטר
Passho|פאשו
Payapa|פאיאפה
Pecha|פצ'ה
Persim|פרסים
Petaya|פטאיה
Pinap|פינאפ
Pomeg|פומג
Qualot|קוואלוט
Rabuta|רבוטה
Rawst|רוסט
Razz|ראז
Rindo|רינדו
Roseli|רוזלי
Rowap|רוואפ
Salac|סלק
Shuca|שוקה
Sitrus|סיטרוס
Spelon|ספלון
Starf|סטארף
Tamato|טמטו
Tanga|טנגה
Wacan|וואקן
Watmel|ווטמל
Wepear|וויפיר
Wiki|וויקי
Yache|יאצ'ה
'''

def main():
    target=LAB/'translations/items-editorial-20261030-r1.json'
    if target.exists(): raise FileExistsError(target)
    source=LAB/'terminology/proposals/build_items_reviewed.py'
    spec=importlib.util.spec_from_file_location('item_lexicon',source)
    lex=importlib.util.module_from_spec(spec);spec.loader.exec_module(lex)
    species=json.loads((LAB/'translations/species-editorial-20261030-r1.json').read_text(encoding='utf-8'))
    for rows in species['tables'].values():
        for r in rows:
            lex.proper['pokemon',r['source']]=r['he'];lex.proper_status['pokemon',r['source']]='editorial'
    for line in BERRIES.splitlines():
        if line:
            en,he=line.split('|');lex.proper['berry',en]=he;lex.proper_status['berry',en]='editorial'
    records=list(iter_tm(LAB/'memory/english-source.jsonl'))
    keyed={r['key']:r for r in records}
    current={}
    for name in MODULES:
        module=load_module(name)
        for table in getattr(module,'TABLES',[module]):
            current.update(table.TERMS)
            if table.FILE.endswith('/seikaku.dat'):
                for row in authored_rows(table,records):
                    en=keyed[row['key']]['source']
                    lex.proper['nature',en]=row['he'];lex.proper_status['nature',en]='editorial'
    for en,he in current.items():
        for category in ('pokemon','character','place','berry','nature'):
            if (category,en) in lex.proper:lex.proper[category,en]=he
    fixes={en:(sg,pl) for en,sg,pl in (l.split('|') for l in EDITS.splitlines() if l)}
    sg_records={r['line_index']:r for r in records if r['file'].endswith('/common/itemname.dat')}
    pairs={};families=Counter();missing=[]
    for index,r in sg_records.items():
        if not r['requires_translation']:continue
        name=r['source'];value=lex.translate(name)
        if not any(c.isalpha() for c in name):value=(name,name,'neutral_symbols',None)
        if name in fixes:value=(*fixes[name],'editorial_correction','editorial')
        if value is None:
            inv=next((i for i in lex.inventory if i['category']=='item' and i['english']==name),None)
            if inv and inv.get('forms'):
                sg=lex.curated.get(('item',name));pl=lex.curated.get(('item_plural',inv['forms'][0]['plural']))
                if sg and pl:value=(sg,pl,'curated_pair','editorial')
        if value is None:missing.append((index,name));continue
        sg,pl,family,spelling=value
        if name in current and name not in fixes:
            # Story terms were already edited in context. Require an explicit
            # plural decision whenever that differs from this lexical family.
            old=sg;sg=current[name]
            if old!=sg and old in pl:pl=pl.replace(old,sg)
        if name.endswith(' Canari Plush'):
            color=name.split()[0];forms=lex.COLORS[color]
            sg='בובת קנארי '+forms[1];pl='בובות קנארי '+forms[3]
        if name.startswith('Mega ') and 'Hyperspace' in name:
            sg=sg.replace('על-חלל','מרחב-על');pl=pl.replace('על-חלל','מרחב-על')
        pairs[index]=(sg,pl,family);families[family]+=1
    if missing:raise ValueError(missing)
    tables={}
    for r in records:
        if not r['file'].startswith('ik_message/dat/English/common/itemname') or not r['requires_translation']:continue
        sg,pl,family=pairs[r['line_index']]
        is_plural='_plural' in r['file']
        he=sg if not is_plural or r['source']==sg_records[r['line_index']]['source'] else pl
        tables.setdefault(r['file'],[]).append(dict(index=r['line_index'],source=r['source'],he=he,family=family))
    data=dict(status='assistant_editorial_candidate; full item names; visual QA pending',
              technical_identifiers='Exact TM/TR/HM and star codes preserved; English plural s omitted only in plural tables',
              family_counts=dict(families),tables=tables)
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=sum(map(len,tables.values())),families=families),ensure_ascii=False))

if __name__=='__main__':main()

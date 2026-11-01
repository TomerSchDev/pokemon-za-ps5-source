"""One-time reviewed terminology corrections; preserve prior frozen catalogs."""
import json
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
T = LAB / 'translations'
changes = []

def replace(name, pairs):
    p = T / name
    old = p.read_text(encoding='utf-8')
    new = old
    for before, after in pairs:
        if before not in new:
            raise ValueError((name, 'expected wording absent', before))
        new = new.replace(before, after)
    p.write_text(new, encoding='utf-8')
    changes.append({'file':name, 'replacements':pairs})

def frozen(oldname, newname, edit):
    p = T / newname
    if p.exists():
        raise FileExistsError(p)
    data = json.loads((T / oldname).read_text(encoding='utf-8'))
    edit(data)
    data['editorial_revision_note'] = 'Final consistency review: terminology and recipe/category grammar; original sources and indices preserved.'
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    changes.append({'previous':oldname, 'revised':newname})

for name in ['chapter06-corbeau','chapter07-tournament','chapter08-az-history']:
    pairs=[('כרטיס אתגר','כרטיס מתמודד')]
    if name=='chapter06-corbeau':pairs.append(('כרטיס האתגר','כרטיס המתמודד'))
    replace(name+'-20261030-r1.py',pairs)
replace('royale-hud-20261030-r1.py',[('כרטיס האתגר','כרטיס המתמודד')])
for name in ['dlc05-emma-canari','sidequests-160-162','sidequests-166-167']:
    replace(name+'-20261030-r1.py',[('חוזק הוא כוח','עוצמה היא כוח'),('חוזק הוא צדק','עוצמה היא צדק')])
replace('lumiose-citizens-a02-west-20261030-r1.py',[('פוקימונים זוהרים','פוקימונים נוצצים')])
replace('lumiose-citizens-a05-plazas-20261030-r1.py',[('אלפא זוהר','אלפא נוצץ')])
replace('battle-spot-full-20261030-r1.py',[('אספן זוהרים','אספן נוצצים'),('אספנית זוהרים','אספנית נוצצים'),('פוקימונים זוהרים','פוקימונים נוצצים')])
replace('city-information-boards-20261030-r1.py',[('דונאטס עם כוח זוהר יקלו על מציאת פוקימונים זוהרים','דונאטים עם כוח זוהר יקלו על מציאת פוקימונים נוצצים')])
for name in ['reward-match-dialogues','trainer-messages-a']:
    replace(name+'-20261030-r1.py',[('אליפות חידון קנארי','חידון אלופי קנארי')])
replace('chapter10-legends-20261030-r1.py',[('מהלכי Z','מתקפות Z'),('המהלכים שזיגארד השתמש בהם','המתקפות שזיגארד השתמש בהן')])
replace('sidequests-187-188-20261030-r1.py',[('פוקימון הנכלולי','פוקימון נכלולי'),('פוקימון האכזר','פוקימון אכזר')])

def items(d):
    base={r['index']:r['he'] for r in d['tables']['ik_message/dat/English/common/itemname.dat']}
    count=0
    for rows in d['tables'].values():
        for r in rows:
            if r['source'].endswith((' recipe',' recipes')):
                r['he']=('מתכונים ל' if r['source'].endswith(' recipes') else 'מתכון ל')+base[r['index']]
                count+=1
    assert count==129,count
frozen('items-editorial-20261030-r3.json','items-editorial-20261030-r4.json',items)
replace('items-full-20261030-r1.py',[('items-editorial-20261030-r3.json','items-editorial-20261030-r4.json')])

def categories(d):
    for r in d['rows']:
        if r['source']=='Devious Pokémon':r['he']='פוקימון נכלולי'
        if r['source']=='Cruel Pokémon':r['he']='פוקימון אכזר'
frozen('pokedex-categories-editorial-20261030-r2.json','pokedex-categories-editorial-20261030-r3.json',categories)
replace('pokedex-categories-full-20261030-r2.py',[('pokedex-categories-editorial-20261030-r2.json','pokedex-categories-editorial-20261030-r3.json')])

def donuts(d):
    for r in d['rows']:
        if 'Shiny' in r['source']:r['he']=r['he'].replace('פוקימונים זוהרים','פוקימונים נוצצים')
frozen('donut-flavor-editorial-20261030-r1.json','donut-flavor-editorial-20261030-r2.json',donuts)
replace('donut-flavor-full-20261030-r1.py',[('donut-flavor-editorial-20261030-r1.json','donut-flavor-editorial-20261030-r2.json')])
replace('donut-flavor-templates-20261030-r1.txt',[('פוקימונים זוהרים','פוקימונים נוצצים')])

def battles(d):
    d['local_terms'].update({'Z-Move':'מתקפת Z','Z-Moves':'מתקפות Z'})
    for rows in d['tables'].values():
        for r in rows:
            if 'Z-Move' in r['source']:r['he']=r['he'].replace('מתקפת זי','מתקפת Z')
frozen('battle-set-editorial-20261030-r2.json','battle-set-editorial-20261030-r3.json',battles)
replace('battle-set-full-20261030-r1.py',[('battle-set-editorial-20261030-r2.json','battle-set-editorial-20261030-r3.json')])
replace('battle-set-edits-20261030-r1.txt',[('מתקפת זי','מתקפת Z')])
(LAB/'coordination/editorial-final-20261030-r1.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Updated',len(changes),'editorial sources/catalogs')

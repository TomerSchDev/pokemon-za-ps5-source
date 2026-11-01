"""Freeze reviewed item-description prose and exact, inspected semantic families.

Only iteminfo is eligible. Unknown descriptions stay out of the candidate; the
coverage audit continues to report them. Every emitted row records its source.
"""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from build_hebrew_project import load_module, authored_rows
from translation_memory import iter_tm

LAB = Path(__file__).resolve().parents[1]
FILE = 'ik_message/dat/English/common/iteminfo.dat'
OUTPUT = LAB/'translations/item-descriptions-editorial-20261030-r3.json'
STATS = {'Attack':'ההתקפה','Defense':'ההגנה','Speed':'המהירות',
         'Sp. Atk':'ההתקפה המיוחדת','Sp. Def':'ההגנה המיוחדת'}
TYPES = {'Fire':'אש','Water':'מים','Electric':'חשמל','Grass':'עשב','Ice':'קרח',
         'Fighting':'לחימה','Poison':'רעל','Ground':'אדמה','Flying':'מעופף',
         'Psychic':'על-חושי','Bug':'חרק','Rock':'סלע','Ghost':'רוח','Dragon':'דרקון',
         'Dark':'אופל','Steel':'פלדה','Normal':'רגיל','Fairy':'פיה'}
ESSENCES = {'fire':'האש','water':'המים','electricity':'החשמל','plants':'הצמחים',
            'ice':'הקרח','fighting spirit':'רוח הלחימה','poison':'הרעל',
            'earth':'האדמה','flight':'התעופה','psychic energy':'האנרגיה העל-חושית',
            'bugs':'החרקים','rock':'הסלע','ghosts':'הרוחות','dragons':'הדרקונים',
            'darkness':'האופל','steel':'הפלדה','normality':'הרגילות','fairies':'הפיות'}
EXACT = {
 'N/A':'לא זמין',
 '- - -':'-\n-\n-',
 'An item that causes {VAR 0101:0000} to appear from the Watchtower Lair in the Wild Area until the end of the day.':
 'חפץ שגורם ל{VAR 0101:0000} להופיע ממאורת מגדל השמירה באזור הפרא עד סוף היום.',
 'Material accidentally dropped by a Pokémon. It can be used to make TMs.':
 'חומר שנשמט בטעות מפוקימון. אפשר להשתמש בו להכנת מכונות מתקפה.',
 'A candy that is packed with energy. When given to certain Pokémon, it will increase all their stats at once.':
 'סוכרייה עתירת אנרגיה. כשנותנים אותה לפוקימונים מסוימים, היא מעלה את כל נתוניהם בבת אחת.',
 'Part of a series of old poems that have been unearthed around the Hisui region. Judging from the handwriting, it appears they were all written by the same person.':
 'חלק מסדרת שירים עתיקים שהתגלו ברחבי מחוז היסוי. לפי כתב היד, נראה שכולם נכתבו בידי אותו אדם.',
 'On rare occasions, these shards form when a Tera Pokémon falls in battle and its Tera Jewel shatters.':
 'לעיתים נדירות נוצרים רסיסים כאלה כשפוקימון טרה נופל בקרב ותכשיט הטרה שלו מתנפץ.',
 'A popular option among hikers. It’s made with titanium, so it doesn’t rust even if it’s used to hold drinks with high sodium content.':
 'בחירה פופולרית בקרב מטיילים. עשוי מטיטניום, ולכן אינו מחליד גם כשממלאים אותו במשקאות עתירי נתרן.',
 'A mysterious charm that tends to be lost before any other item when you faint in the field. This type of charm comes in five different colors.':
 'קמע מסתורי שנוטה ללכת לאיבוד לפני כל חפץ אחר כשמאבדים הכרה בשטח. קמע מסוג זה מגיע בחמישה צבעים.',
 'A mysterious charm that holds the power to protect a person from fainting while out in the field. This type of charm comes in five different colors.':
 'קמע מסתורי שבכוחו להגן על אדם מפני איבוד הכרה בשטח. קמע מסוג זה מגיע בחמישה צבעים.',
 'A mysterious charm that holds the power to protect a person from being afflicted with status conditions. This type of charm comes in five different colors.':
 'קמע מסתורי שבכוחו להגן על אדם מפני בעיות מצב. קמע מסוג זה מגיע בחמישה צבעים.',
 'A satchel that someone dropped.':'תיק שמישהו איבד.',
 'A key that opens a door inside Sea Mauville.':'מפתח שפותח דלת בתוך מאוויל הימית.',
 'Having a Pokémon smell this mint will cause its Attack, Defense, Sp. Atk, Sp. Def, and Speed stats to grow at an equal rate.':
 'ריח הנענע גורם לנתוני ההתקפה, ההגנה, ההתקפה המיוחדת, ההגנה המיוחדת והמהירות של פוקימון לצמוח בקצב שווה.',
}
DONUT_BASE = 'A mysterious Berry found in Hyperspace Lumiose that’s ideal for making donuts. '
DONUT_HE = 'פרי מסתורי מלומיוז במרחב-על, אידיאלי להכנת דונאטס. '
DONUT_ENDS = {
 'Its spicy kick is great when added to curries.':'חריפותו נהדרת כתוספת לקארי.',
 'Its dry flavor offers a good balance when used in sweet cream.':'טעמו היבש מאזן היטב קרם מתוק.',
 'Its sweet flavor makes it a great ingredient for meringue.':'טעמו המתוק הופך אותו למרכיב נהדר במרנג.',
 'Its bitter bite works beautifully in chocolate.':'מרירותו משתלבת נהדר בשוקולד.',
 'Its sour bite makes it perfect for stewing into a confiture.':'חמיצותו מושלמת לבישול קונפיטורה.',
}
FOODS = {'curries':'קארי','cream':'קרם','meringue':'מרנג','chocolate':'שוקולד','confitures':'קונפיטורה'}


def normalized(text):
    return re.sub(r'\s+', ' ', text).strip()


def family(source, names):
    s = normalized(source)
    if s in EXACT:
        return EXACT[s], 'reviewed exact description'
    match = re.fullmatch(r'One of a variety of mysterious Mega Stones\. An? (.+) holding this stone will be able to Mega Evolve during battle\.', s)
    if match and match[1] in names:
        return f'אחת מאבני המגה המסתוריות. {names[match[1]]} שנושא אבן זו יכול לעבור מגה-התפתחות בקרב.', 'mega-stone exact family'
    match = re.fullmatch(r'Having a Pokémon smell this mint can make its (.+) stat grow stronger\. However, its (.+) stat may suffer\.', s)
    if match and all(x in STATS for x in match.groups()):
        return f'ריח הנענע עשוי לשפר את צמיחת נתון {STATS[match[1]]} של פוקימון, אך לפגוע בצמיחת נתון {STATS[match[2]]} שלו.', 'mint stat-pair exact family'
    match = re.fullmatch(r'(Sharply|Drastically|Immensely) boosts the (.+) of a Pokémon in battle\. This effect disappears if the Pokémon leaves the battle\.', s)
    if match:
        stat = 'הדיוק' if match[2]=='accuracy' else ('נתון '+STATS[match[2].removesuffix(' stat')] if match[2].removesuffix(' stat') in STATS else None)
        if stat:
            amount={'Sharply':'מאוד','Drastically':'באופן דרסטי','Immensely':'במידה עצומה'}[match[1]]
            return f'מעלה {amount} את {stat} של פוקימון בקרב. ההשפעה פגה כשהפוקימון עוזב את הקרב.', 'battle-stat intensity exact family'
    match = re.fullmatch(r'An item to be held by a Pokémon\. This gem is imbued with the essence of (.+) and will boost the power of an? (.+)-type move—but only once\.', s)
    if match and match[1] in ESSENCES and match[2] in TYPES:
        return f'אבן חן רוויה בתמצית {ESSENCES[match[1]]}, לנשיאה בידי פוקימון. מחזקת מתקפה מסוג {TYPES[match[2]]}, פעם אחת בלבד.', 'type gem exact family'
    if s.startswith(DONUT_BASE):
        end = s[len(DONUT_BASE):]
        if end in DONUT_ENDS:
            return DONUT_HE + DONUT_ENDS[end], 'hyperspace berry culinary description'
        match = re.fullmatch(r'It goes well in (.+)\.', end)
        if match:
            parts = re.split(r',? and |, ', match[1])
            if all(x in FOODS for x in parts):
                translated=[FOODS[x] for x in parts]
                joined=translated[0] if len(translated)==1 else ', '.join(translated[:-1])+' ו'+translated[-1]
                return DONUT_HE+'משתלב היטב בהכנת '+joined+'.', 'hyperspace berry exact ingredient list'
    return None


def main():
    if OUTPUT.exists():
        raise FileExistsError('Preserve existing frozen revision')
    records = list(iter_tm(LAB/'memory/english-source.jsonl'))
    target = [r for r in records if r['file']==FILE]
    keyed = {r['key']:r for r in target}
    by_index = {r['line_index']:r for r in target}
    exact = {}
    provenance = []
    def remember(source, he):
        key = normalized(source)
        if key in exact and exact[key]!=he:
            raise ValueError('Conflicting duplicate editorial description: '+key)
        exact[key] = he
    for name in ('item-descriptions-core-20261030-r1.py','item-descriptions-held-20261030-r1.py'):
        path=LAB/'translations'/name
        provenance.append(dict(file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for row in authored_rows(load_module(name),records):
            remember(keyed[row['key']]['source'],row['he'])
    path=LAB/'translations/item-descriptions-za-20261030-r1.txt'
    provenance.append(dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    for line in path.read_text(encoding='utf-8').splitlines():
        if line:
            index,he=line.split('|',1)
            remember(by_index[int(index)]['source'],he)
    species=json.loads((LAB/'translations/species-editorial-20261030-r1.json').read_text(encoding='utf-8'))
    names={r['source']:r['he'] for rows in species['tables'].values() for r in rows}
    output=[]; counts=Counter()
    for row in target:
        if not row['requires_translation']:
            continue
        key=normalized(row['source'])
        result=(exact[key],'reviewed keyed prose / exact same-file reuse') if key in exact else family(row['source'],names)
        if result:
            he,rule=result
            output.append(dict(index=row['line_index'],source=row['source'],he=he,rule=rule))
            counts[rule]+=1
    OUTPUT.write_text(json.dumps(dict(file=FILE,rows=output,rules=dict(counts),authored_sources=provenance,
                         complete_table=False),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(output),rules=dict(counts)),ensure_ascii=False))


if __name__=='__main__':main()

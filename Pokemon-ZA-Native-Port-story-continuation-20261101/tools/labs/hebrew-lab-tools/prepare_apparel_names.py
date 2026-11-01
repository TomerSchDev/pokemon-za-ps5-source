"""Freeze explicitly reviewed clothing names and exact colour/pattern families.

No fallback translation: unknown names are printed and rejected. All 883 source
rows are retained, bound to the original text, and checked before packing.
"""
import json,re
from pathlib import Path
from translation_memory import iter_tm
LAB=Path(__file__).resolve().parents[1]
OUTPUT=LAB/'translations/apparel-editorial-20261030-r2.json'
COLORS=dict(pair.split('|') for pair in '''Ivory|שנהב
Beige|בז׳
Yellow|צהוב
Green|ירוק
Purple|סגול
Black|שחור
Blue|כחול
White|לבן
Red|אדום
Orange|כתום
Pink|ורוד
Gray|אפור
Brown|חום
Navy|כחול כהה
Tan|חום בהיר
Caramel|קרמל
Cream|קרם
Greige|אפור־בז׳
Gold|זהב
Silver|כסף
Cocoa|קקאו
Fern|ירוק שרך
Ink|דיו
Clay|חמרה
Snow|לבן שלג
Tin|בדיל
Strawberry|תות
Midnight|כחול חצות
Maroon|ערמוני
Violet|סגלגל
Emerald|ירוק אזמרגד
Magenta|מג׳נטה
Lime|ירוק ליים
Rose Gold|זהב ורוד
Bronze|ארד
Mustard|חרדל
Marine|כחול ימי
Lavender|לבנדר
Lapis|כחול לפיס
Rainbow|קשת
Platinum|פלטינה
Ash|אפר
Milk tea|תה חלב
Scarlet|שני
Peach|אפרסק
Teal|טורקיז כהה
Turquoise|טורקיז
Mint|מנטה
Aqua|תכלת מים
Sapphire|כחול ספיר
Coral|אלמוג
Rouge|אודם
Lilac|לילך
Ocher|אוכרה
Azure|תכלת
Ultramarine|כחול עמוק
Old Rose|ורוד עתיק
Off-White|לבן שבור
Olive|ירוק זית
Burgundy|בורדו
Indigo|אינדיגו
Bleach|מולבן
Almond|שקד
Ivy|ירוק קיסוס
Lemon|לימון
Emerald Green|ירוק אזמרגד
Cobalt Blue|כחול קובלט
Forest Green|ירוק יער
Pitch Black|שחור משחור
Light Gray|אפור בהיר
Blue-Gray|כחול־אפור
Lemon Yellow|צהוב לימון
Lime Yellow|צהוב ליים
Holo Blue|כחול הולוגרפי
Holo Pink|ורוד הולוגרפי
Black-Gray|שחור־אפור
Gray-Black|אפור־שחור
Pink-Gray|ורוד־אפור
Pink-Brown|ורוד־חום
Wine Red|אדום יין
Lamp Black|שחור פיח
Raven Black|שחור עורב
Mauve Gray|אפור סגלגל
Shell Pink|ורוד צדף
Dusk Blue|כחול דמדומים
Ash brown|חום אפרפר
Poppy red|אדום פרג
Passion pink|ורוד עז
Strawberry Milk|ורוד חלב תות
Baby Pink|ורוד בייבי
Dusty Pink|ורוד מאובק
Sky Gray|אפור שמיים
Sky Blue|כחול שמיים
Smoky Blue|כחול מעושן
Foggy Blue|כחול ערפילי
Taffy Pink|ורוד טופי
Earthenware|טרקוטה'''.splitlines())
COLOR_LOOKUP={k.casefold():v for k,v in COLORS.items()}
PREFIXES=dict(pair.split('|') for pair in '''Argyle|מעוינים
Aromatic|ארומטי
Antique|עתיק
Traditional|מסורתי
Academic|אקדמי
Candy|סוכריות
Cool|מגניב
Clean|נקי
Checkered|משבצות שחמט
Scatterdust|אבק כוכבים
Daunting|מאיים
Psychic|על־חושי
Sand|חולי
Geometric|גאומטרי
Signature|חתימה
Sweet|מתוק
Scary|מפחיד
Mystic|מיסטי
Dark|כהה
Pastel|פסטלי
Floral|פרחוני
Vivid|עז
BRAVELY|ברייבלי
Pale|חיוור
Multicolor|רב־צבעי
Light|בהיר
Overturning|התהפכות
Retro|רטרו
Two-Tone|שני גוונים
Flowery|פרחוני
Moss|טחב
Moon|ירח
Zigzag|זיגזג
Shiny|מבריק'''.splitlines())
SUFFIXES=dict(pair.split('|') for pair in '''Gradient|מעבר גוונים
Plaid|משבצות
Frames|מסגרת
Ribbon|סרט
Lenses|עדשות
Denim|ג׳ינס
Stripes|פסים
Claw|טופר
Cable-Knit|סריגת צמות
Quilting|תפירת קווילט
Graffiti|גרפיטי
Meteorites|מטאוריטים
Shippo|עיטור שיפו
Stitching|תפרים
Spray|רסס
Tartan|משבצות סקוטיות
Damask|עיטור דמשק
Houndstooth|משבצות רגלי תרנגול
Geta|גטה
Ink|דיו
Blossoms|פריחה
Mix|תערובת
Lines|קווים
Knit|סריגה
Leather|עור
Wise-Eyes|עיניים נבונות
Drops|טיפות'''.splitlines())
SPECIES={'Girafarig':'ג\'יראפאריג','Bewear':'ביוור','Avalugg':'אבלאג','Gengar':'גנגאר','Scizor':'סיזור','Gogoat':'גוגוט','Chespin':'צ\'ספין','Pikachu':'פיקאצ\'ו','Eevee':'איווי','Liepard':'לייפרד'}
HOLO={'Striped Trilby':'כובע טרילבי מפוספס','Visor':'מצחייה','Blouson & V-Neck':'ז׳קט וחולצת וי','Blouson & Off-Shoulder':'ז׳קט וחולצת כתפיים חשופות','Skinny Jeans':'ג׳ינס סקיני','Wide-Leg Pants':'מכנסיים רחבים','Mid-Top Sneakers':'נעלי ספורט בגובה בינוני','Sock Sneakers':'נעלי ספורט דמויות גרב','Round Satchel':'תיק צד עגול'}

def colour(s):
    if s.casefold() in COLOR_LOOKUP:return COLOR_LOOKUP[s.casefold()]
    for prefix,he in [('Dark','כהה'),('Light','בהיר'),('Pale','חיוור')]:
        if s.casefold().startswith(prefix.casefold()+' '):
            base=COLOR_LOOKUP.get(s[len(prefix)+1:].casefold())
            if base:return base+' '+he
    return None

def translate(s,explicit):
    if s in explicit:return explicit[s]
    if (c:=colour(s)):return c
    parts=s.split(' / ')
    if len(parts)==2 and all(colour(p) for p in parts):return ' / '.join(colour(p) for p in parts)
    if s.startswith('All-') and (c:=colour(s[4:])):return 'כולו '+c
    for en,he in SUFFIXES.items():
        if s.endswith(' '+en) and (c:=colour(s[:-len(en)-1])):return he+' ב'+('ו'+c if c.startswith('ו') else c)
    for en,he in PREFIXES.items():
        if s.startswith(en+' ') and (c:=colour(s[len(en)+1:])):return he+' — '+c
    for en,he in SPECIES.items():
        if s.startswith(en+' ') and (c:=colour(s[len(en)+1:])):return he+' ב'+('ו'+c if c.startswith('ו') else c)
        if s.endswith(' '+en) and (c:=colour(s[:-len(en)-1])):return he+' ב'+('ו'+c if c.startswith('ו') else c)
    m=re.fullmatch(r'(\w+)-and-(\w+) Stripes',s)
    if m and colour(m[1]) and colour(m[2]):return 'פסים ב'+colour(m[1])+' ו'+colour(m[2])
    m=re.fullmatch(r'Holo-([XY]) (.+)',s)
    if m and m[2] in HOLO:return HOLO[m[2]]+' (הולו-'+m[1]+')'
    m=re.fullmatch(r'(Beauty spot|Freckles) ([IVX]+)',s)
    if m:return {'Beauty spot':'נקודת חן','Freckles':'נמשים'}[m[1]]+' '+m[2]
    return None

def main():
    if OUTPUT.exists():raise FileExistsError('Preserve frozen revision')
    pairs=[line.split('|',1) for line in (LAB/'translations/apparel-explicit-20261030-r2.txt').read_text(encoding='utf-8').splitlines() if line]
    explicit=dict(pairs)
    if len(explicit)!=len(pairs):raise ValueError('Duplicate explicit source')
    records=[r for r in iter_tm(LAB/'memory/english-source.jsonl') if r['file'].endswith('/dressup_item_name.dat') and r['requires_translation']]
    unknown=sorted({r['source'] for r in records if translate(r['source'],explicit) is None})
    if unknown:
        print('\n'.join(unknown));raise ValueError(f'{len(unknown)} unreviewed names')
    unused=set(explicit)-{r['source'] for r in records}
    if unused:raise ValueError('Unknown explicit names: '+repr(unused))
    rows=[dict(index=r['line_index'],source=r['source'],he=translate(r['source'],explicit)) for r in records]
    OUTPUT.write_text(json.dumps(dict(file=records[0]['file'],rows=rows,visual_qa='Pending; inspect clothing names, long labels and mixed Latin model suffixes in game.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),unique=len({r['source'] for r in rows}))))
if __name__=='__main__':main()

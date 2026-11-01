"""Freeze reviewed credit prose and original attribution names from two inspected tables.

Every source row in both tables was read during the editorial pass. The name
catalog is a fixed, source-bound list, not a general exemption for credit files.
Department titles, LEAD prefixes, generic company labels and full rights prose
are translated. Personal/organization names and copyright-owner signatures keep
their exact original spelling. Never infer a new catalog from an updated game.
"""
import hashlib
import json
from pathlib import Path
import re

LAB=Path(__file__).resolve().parents[1]
FILES={
 'ik_message/dat/English/common/staff_list.dat':'99e0f9591775d8aa01411aaf64331926c2f21381cb3a72df3a63a45f23085cd7',
 'ik_message/dat/English/sk/sa_staff_list.dat':'81a6b20474e01f65270bf95252e1c632ce7b43c54c9f486e0e79e59df98f03f7'}
HEADINGS={
 'SENIOR DIRECTOR':'ניהול בכיר',
 'DIRECTOR':'ניהול',
 'PROGRAMMING SECTION DIRECTORS':'ניהול מחלקת התכנות',
 'GRAPHIC DESIGN SECTION DIRECTORS':'ניהול מחלקת העיצוב הגרפי',
 'PLANNING SECTION DIRECTOR':'ניהול מחלקת התכנון',
 'PROGRAMMING SECTION':'מחלקת התכנות',
 'FIELD TEAM':'צוות סביבת המשחק',
 'CHARACTER TEAM':'צוות הדמויות',
 'BATTLE TEAM':'צוות הקרבות',
 'EVENT TEAM':'צוות האירועים',
 'UI TEAM':'צוות ממשק המשתמש',
 'COMMUNICATION FEATURES TEAM':'צוות תכונות התקשורת',
 'PROGRAMMING SECTION SUPERVISOR':'פיקוח על מחלקת התכנות',
 'GRAPHIC DESIGN SECTION':'מחלקת העיצוב הגרפי',
 'CHARACTER MODELING TEAM':'צוות מידול הדמויות',
 'LIGHTING TEAM':'צוות התאורה',
 '3D MAP GRAPHICS TEAM':'צוות גרפיקת מפות בתלת-ממד',
 'MOTION DESIGN TEAM':'צוות עיצוב ההנפשה',
 'MOVIE TEAM':'צוות הסרטונים',
 'MOTION ACTORS':'שחקני לכידת תנועה',
 'SPECIAL EFFECTS GRAPHIC DESIGN TEAM':'צוות עיצוב גרפי לאפקטים מיוחדים',
 'UI GRAPHIC DESIGN TEAM':'צוות העיצוב הגרפי של ממשק המשתמש',
 'POKÉMON 3D VISUAL TEAM':'צוות תלת-ממד לפוקימונים',
 'POKÉMON DATA QA':'אבטחת איכות של נתוני הפוקימונים',
 'PLANNING SECTION':'מחלקת התכנון',
 'MAIN SCENARIO':'התסריט הראשי',
 'STORY TEAM':'צוות העלילה',
 'FIELD & AI TEAM':'צוות סביבת המשחק והבינה המלאכותית',
 'SOUND TEAM':'צוות הסאונד',
 'SOUND COORDINATION':'תיאום סאונד',
 'SOUND EFFECTS COORDINATION':'תיאום אפקטים קוליים',
 'SOUND PROGRAMMING':'תכנות סאונד',
 'SOUND EFFECTS':'אפקטים קוליים',
 'COMPOSERS':'מלחינים',
 'MUSICIANS':'מוזיקאים',
 'VOICE RECORDING':'הקלטת קולות',
 'VOICE':'ביצוע קולי',
 'SOUND ENVIRONMENT SUPPORT':'תמיכה בסביבת הסאונד',
 '”KISEKI” SOUND RECORDING ENGINEER':'הנדסת הקלטת סאונד ל־KISEKI',
 'RECORDING COORDINATOR':'תיאום הקלטות',
 'SOUND PARTNERS':'שותפים לסאונד',
 'CONCEPT & VISUAL STUDIO':'סטודיו לקונספט ולעיצוב חזותי',
 'DESIGN & WORLD CONCEPT SECTION':'מחלקת העיצוב ותפיסת העולם',
 'SUPERVISOR':'פיקוח',
 'SECTION DIRECTOR':'ניהול המחלקה',
 'WORLD, POKÉMON & HUMAN PLANNING':'תכנון העולם, הפוקימונים והדמויות',
 'ポケモン＆じんぶつせってい':'תכנון פוקימונים ודמויות',
 'CONCEPT ART':'אמנות קונספט',
 'POKÉMON & CHARACTER DESIGN':'עיצוב פוקימונים ודמויות',
 'POKÉMON DESIGN':'עיצוב פוקימונים',
 'CHARACTER & COSTUME DESIGN':'עיצוב דמויות ותלבושות',
 'FIELD MAP DESIGN':'עיצוב מפות העולם',
 'DEVELOPMENT SUPPORT':'תמיכה בפיתוח',
 '3D VISUAL SECTION':'מחלקת העיצוב בתלת-ממד',
 'SECTION DIRECTORS':'ניהול המחלקה',
 'MODEL TEAM':'צוות המידול',
 'MOTION TEAM':'צוות ההנפשה',
 'DEBUG TEAM':'צוות איתור ותיקון תקלות',
 'RESEARCH & DEVELOPMENT':'מחקר ופיתוח',
 'GENERAL MANAGER':'ניהול כללי',
 'FRAMEWORK TEAM':'צוות תשתיות התוכנה',
 'POKÉMON & BATTLE SYSTEM TEAM':'צוות מערכות הפוקימונים והקרבות',
 'CG TECHNOLOGY LABORATORY':'מעבדת טכנולוגיית גרפיקה ממוחשבת',
 'DIRECTORS':'ניהול',
 'BASE TECHNOLOGY SECTION':'מחלקת טכנולוגיות הבסיס',
 'GRAPHICS PROGRAMMING TEAM':'צוות תכנות הגרפיקה',
 'LIBRARY TEAM':'צוות ספריות התוכנה',
 'SIMULATION TEAM':'צוות ההדמיה',
 'DCC ENVIRONMENT DEVELOPMENT TEAM':'צוות פיתוח סביבת יצירת התוכן',
 'RIGGING SYSTEM DEVELOPMENT TEAM':'צוות פיתוח מערכות שלד לדמויות',
 'AI SECTION':'מחלקת הבינה המלאכותית',
 'GAME AI TEAM':'צוות הבינה המלאכותית של המשחק',
 'MACHINE LEARNING TEAM':'צוות למידת המכונה',
 'ENVIRONMENT DEVELOPMENT SECTION':'מחלקת פיתוח סביבת העבודה',
 'PIPELINE TEAM':'צוות תהליכי העבודה',
 'QUALITY ASSURANCE SYSTEM TEAM':'צוות מערכות אבטחת האיכות',
 'DEVELOPMENT ASSISTANT':'סיוע בפיתוח',
 'POKÉMON SERIES QA':'אבטחת איכות של סדרת פוקימון',
 'POKÉMON ATTRIBUTE TEAM':'צוות מאפייני הפוקימונים',
 'GROUP MANAGER':'ניהול הקבוצה',
 'PROJECT MANAGEMENT':'ניהול הפרויקט',
 'PROJECT MANAGERS':'מנהלי הפרויקט',
 'ASSISTANTS':'עוזרים',
 'INFORMATION MANAGEMENT':'ניהול מידע',
 'TECHNICAL SUPPORT':'תמיכה טכנית',
 'GAME SERVER DEVELOPMENT':'פיתוח שרתי המשחק',
 'DEBUG MANAGEMENT':'ניהול איתור ותיקון תקלות',
 'DEBUG':'איתור ותיקון תקלות',
 'POKÉMON 3D MODELING':'מידול פוקימונים בתלת-ממד',
 'ART DIRECTOR':'ניהול אמנותי',
 'PROJECT DIRECTOR':'ניהול הפרויקט',
 'PRODUCT MANAGERS':'מנהלי המוצר',
 'POKÉMON MODEL QUALITY ASSURANCE':'אבטחת איכות של מודלי הפוקימונים',
 'POKÉMON CHARACTER MODELING':'מידול דמויות הפוקימונים',
 'POKÉMON CHARACTER MOTION':'הנפשת דמויות הפוקימונים',
 'DCC SUPPORT TEAMS':'צוותי תמיכה ביצירת תוכן דיגיטלי',
 'ENGLISH LOCALIZATION':'התאמה לאנגלית',
 'ENGLISH TRANSLATION':'תרגום לאנגלית',
 'ENGLISH EDITING':'עריכה באנגלית',
 'EUROPEAN LOCALISATION':'התאמה לשפות אירופה',
 'FRENCH TRANSLATION':'תרגום לצרפתית',
 'FRENCH EDITING':'עריכה בצרפתית',
 'GERMAN TRANSLATION':'תרגום לגרמנית',
 'GERMAN EDITING':'עריכה בגרמנית',
 'ITALIAN TRANSLATION':'תרגום לאיטלקית',
 'ITALIAN EDITING':'עריכה באיטלקית',
 'EUROPEAN SPANISH TRANSLATION':'תרגום לספרדית של ספרד',
 'EUROPEAN SPANISH EDITING':'עריכה בספרדית של ספרד',
 'LATIN AMERICAN SPANISH EDITING':'עריכה בספרדית של אמריקה הלטינית',
 'KOREAN TRANSLATION & EDITING':'תרגום ועריכה בקוריאנית',
 'CHINESE LOCALIZATION':'התאמה לסינית',
 'CHINESE TRANSLATION & EDITING':'תרגום ועריכה בסינית',
 'ENGLISH & EUROPEAN LOCALIZATION SUPPORT':'תמיכה בהתאמה לאנגלית ולשפות אירופה',
 'LOCALIZATION SUPPORT (THE AMERICAS)':'תמיכה בהתאמה לשפות אמריקה',
 'LOCALISATION SUPPORT (EUROPE)':'תמיכה בהתאמה לשפות אירופה',
 'LOCALIZATION SUPPORT (ASIA)':'תמיכה בהתאמה לשפות אסיה',
 'LOCALIZATION SUPPORT (KOREA)':'תמיכה בהתאמה לקוריאנית',
 'LOCALIZATION SUPPORT (TRADITIONAL CHINESE)':'תמיכה בהתאמה לסינית מסורתית',
 'LOCALIZATION SUPPORT (SIMPLIFIED CHINESE)':'תמיכה בהתאמה לסינית מפושטת',
 'LANGUAGE QA (THE AMERICAS)':'אבטחת איכות לשונית באמריקה',
 'TESTING (THE AMERICAS)':'בדיקות באמריקה',
 'QA COORDINATION (EUROPE)':'תיאום אבטחת איכות באירופה',
 'QUALITY ASSURANCE (EUROPE)':'אבטחת איכות באירופה',
 'TESTING & QUALITY ASSURANCE (KOREA)':'בדיקות ואבטחת איכות בקוריאה',
 'PRODUCT TESTING (CHINESE)':'בדיקת המוצר בסינית',
 'SPECIAL THANKS—LOCALIZATION':'תודה מיוחדת — התאמה לשפות',
 'ARTWORK':'עבודות אמנות',
 'ENGLISH & EUROPEAN GRAPHIC DESIGN':'עיצוב גרפי לאנגלית ולשפות אירופה',
 'KOREAN ARTWORK':'עבודות אמנות לקוריאנית',
 'SPECIAL THANKS':'תודה מיוחדת',
 'PARTNERS':'שותפים',
 'COORDINATORS':'תיאום',
 'PRODUCERS':'מפיקים',
 'GENERAL PRODUCERS':'מפיקים כלליים',
 'EXECUTIVE PRODUCERS':'מפיקים בפועל',
 'Pokémon Legends: Z-A':'פוקימון אגדות: Z-A',
 'DEVELOPED BY':'פותח בידי',
 'PROGRAMMING TEAM':'צוות התכנות',
 'MOTION DESIGN & MOVIE TEAM':'צוות עיצוב ההנפשה והסרטונים',
 'PLANNING TEAM':'צוות התכנון',
 'SOUND PLANNING':'תכנון סאונד',
 'ART DIRECTION TEAM':'צוות הניהול האמנותי',
 '3D MAP GRAPHICS':'גרפיקת מפות בתלת-ממד',
 'ANIMATION SECTION':'מחלקת ההנפשה',
 'PHYSICS & PROCEDURAL ANIMATION TEAM':'צוות הפיזיקה וההנפשה הפרוצדורלית',
 'INFORMATION COORDINATORS':'תיאום מידע',
 'Mega Dimension':'ממד המגה',
}
for compact,spaced in {
 'LOCALIZATION SUPPORT(KOREA)':'LOCALIZATION SUPPORT (KOREA)',
 'LOCALIZATION SUPPORT(TRADITIONAL CHINESE)':'LOCALIZATION SUPPORT (TRADITIONAL CHINESE)',
 'LOCALIZATION SUPPORT(SIMPLIFIED CHINESE)':'LOCALIZATION SUPPORT (SIMPLIFIED CHINESE)',
 'PRODUCT TESTING(CHINESE)':'PRODUCT TESTING (CHINESE)',
}.items():HEADINGS[compact]=HEADINGS[spaced]

RIGHTS={
 'Nintendo, The Pokémon Company, and':'Nintendo, The Pokémon Company ו־',
 'GAME FREAK inc. are the authors of':'GAME FREAK inc. הם היוצרים של',
 'this software for the purpose of copyright.':'תוכנה זו לעניין זכויות יוצרים.',
 'All rights reserved.':'כל הזכויות שמורות.',
 'Nintendo, The Pokémon Company et':'Nintendo, The Pokémon Company ו־',
 'GAME FREAK inc. sont les auteurs de ce':'GAME FREAK inc. הם היוצרים של',
 'logiciel au regard du droit d’auteur.':'תוכנה זו לעניין זכויות יוצרים.',
 'Tous droits réservés.':'כל הזכויות שמורות.',
 'かぶしきがいしゃ':'חברה בע״מ',
}
# Inspected organization rows (including original Japanese brand readings).
ORGANIZATIONS={
 'staff_list.dat':set(range(313,324))|{526,531,532,947,950,954,955,1144}|set(range(1052,1112)),
 'sa_staff_list.dat':set(range(102,110))|{280,281,656,680,701,705,706,860}|set(range(809,826)),
}
OWNER_SIGNATURES={'staff_list.dat':set(range(1145,1149)),'sa_staff_list.dat':set(range(861,865))}

def freeze(path,value):
    data=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    if path.exists() and path.read_bytes()!=data:raise FileExistsError('Preserve frozen revision: '+str(path))
    if not path.exists():path.write_bytes(data)

def main():
    rows=[];preserved=[];terms={file:{} for file in FILES};seen_headings=set()
    for line in (LAB/'memory/english-source.jsonl').open(encoding='utf-8'):
        r=json.loads(line)
        if r['file'] not in FILES:continue
        if r['source_file_sha256']!=FILES[r['file']]:raise ValueError('Source table changed; review every row again')
        if not r['requires_translation']:continue
        src=r['source'];he=None;file=r['file'];i=r['line_index'];stem=Path(file).name
        match=re.fullmatch(r'(\{VAR FF00:[0-9A-F]{4}\})(.*)(\{VAR FF00:0000\})',src)
        if match:
            text=match[2].strip();seen_headings.add(text)
            if text not in HEADINGS:raise ValueError('Unreviewed heading: '+text)
            he=match[1]+HEADINGS[text]+match[3]
            if 'KISEKI' in text:terms[file]['KISEKI']='KISEKI'
        elif src.startswith('LEAD:'):
            name=src.split(':',1)[1].strip()
            he='הובלת הצוות: '+name
            terms[file][name]=name
        elif src in RIGHTS:
            he=RIGHTS[src]
            for name in ['Nintendo','The Pokémon Company','GAME FREAK inc.']:
                if name in src:terms[file][name]=name
        else:
            kind=('copyright_attribution' if i in OWNER_SIGNATURES[stem]
                  else 'organization_name' if i in ORGANIZATIONS[stem] else 'person_name')
            if kind=='person_name' and (':' in src or '{' in src or '\n' in src):
                raise ValueError('Unexpected attribution shape: '+repr(src))
            preserved.append(dict(key=r['key'],file=file,line_index=i,source=src,
                                  source_file_sha256=FILES[file],kind=kind))
        if he is not None:rows.append(dict(key=r['key'],file=file,line_index=i,source=src,he=he))
    if seen_headings-set(HEADINGS):raise ValueError('Unreviewed headings')
    freeze(LAB/'translations/credits-editorial-20261030-r1.json',dict(
        policy='Translate roles and prose. Preserve original personal/organization spelling in mixed role/name rows.',
        source_files=FILES,local_terms=terms,rows=rows))
    freeze(LAB/'translations/credit-attributions-reviewed-20261030-r1.json',dict(
        policy='Fixed inspected attribution rows only; exact table hash, key, index and source required. Never count these as Hebrew translations. All roles and prose remain language-required.',
        source_files=FILES,rows=preserved))
    print(json.dumps(dict(translated_credit_rows=len(rows),preserved_attribution_rows=len(preserved),
                         total_rows=len(rows)+len(preserved)),ensure_ascii=False))

if __name__=='__main__':main()

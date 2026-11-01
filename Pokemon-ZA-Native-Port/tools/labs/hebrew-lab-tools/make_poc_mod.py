"""Proof of concept: Hebrew main menu / save screen in the Korean text slot, as a LayeredFS mod folder.

usage: python -X utf8 make_poc_mod.py <extract dir> <mod dir>
Reads the game's own Korean message files from the local extraction (never the game's RomFS image), replaces the
lines listed below by label with Hebrew converted to visual order (rtl.py), and writes the changed files to
<mod dir>/romfs/ik_message/dat/Korean/common/. Also writes <mod dir>/../../poc-translation.json (local only).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gfmsg import MsgFile, decode_units, encode_text, read_tbl  # noqa: E402
from rtl import to_visual  # noqa: E402

# label -> Hebrew, logical order (as typed). Gender-neutral wording; numbers / names stay variables.
POC = {
    'main_menu': {
        'main_menu_01_01': 'קופסאות',
        'main_menu_01_02': 'תיק',
        'main_menu_01_03': 'פוקידקס',
        'main_menu_01_04': 'המחקר של מייבל',
        'main_menu_01_05': 'רויאל Z-A',
        'main_menu_01_06': 'משחק מקושר',
        'main_menu_01_07': 'רויאל Z-A האינסופי',
        'main_menu_02_01': 'סגירה',
        'main_menu_02_02': 'ביטול',
        'main_menu_02_03': 'החלפה',
        'main_menu_02_04': 'עזרה והגדרות',
        'main_menu_02_05': 'שמירת התקדמות',
        'main_menu_02_07': 'שינוי מתקפות',
        'main_menu_02_06': 'התפתחות',
        'main_menu_02_08': 'ריפוי אוטומטי',
        'main_menu_02_09': 'החלפת חפצים מוחזקים',
        'main_menu_02_10': 'לבוש ומראה',
        'main_menu_02_11': 'רשימת פרסים',
        'main_menu_02_12': 'מפה',
        'main_menu_07_01': 'יעדים ומשימות',
        'main_menu_07_02': 'פרטי המשימה',
        'main_menu_30_01': 'שעה נוכחית',
        'main_menu_30_02': 'מיקום נוכחי',
        'main_menu_30_04': 'זמן משחק',
        'main_menu_30_05': 'פוקידקס',
        'main_menu_30_07': 'נשמר',   # (a fixed-width label: 'שמירה אחרונה' overlapped the date in poc04)
        'main_menu_30_08': 'דרגת רויאל',
        # date: Israeli order day/month/year (the variables are the same; only their order changes)
        'main_menu_31_01': '{VAR 0201:0002}/{VAR 0201:0001}/{VAR 0203:0000,0000}',
        'main_menu_32_01': 'שמירת התקדמות',
        'main_menu_33_01': 'ביטול',
        'main_menu_34_01': 'שומר את ההרפתקה שלך...\nנא לא לכבות את המכשיר.',
        'main_menu_34_02': 'ההתקדמות שלך נשמרה!{VAR BE01}',
        'main_menu_34_03': 'לא ניתן היה לשמור את ההתקדמות.{VAR BE01}',
        'main_menu_35_01': 'פוקימונים שנתפסו ברמה {VAR 0201:0000} ומטה יצייתו לפקודות שלך',
        'main_menu_35_02': 'כל הפוקימונים יצייתו לפקודות שלך',
    },
    'place_name': {
        'PLACENAME_A01_z01_06': 'רחבת התחנה',
    },
    # new game: the language choice and the first settings screen (the first text a new game shows)
    'language_select': {
        'language_select_guide_01': 'באיזו שפה לשחק?',
        'language_select_01_00': 'חזרה',
    },
    'player_select': {
        'msg_ui_player_select_yes': 'כן',
        'msg_ui_player_select_no': 'לא',
        'msg_ui_player_select_10': 'הכול מוכן, יוצאים לדרך!',
        'msg_ui_player_select_20': 'שומר...',
        'msg_ui_player_select_21': 'כשמופיעה על המסך ההודעה ״שומר...״,\nההתקדמות שלך נשמרת אוטומטית.',
        'player_select_00_00': 'בחרו אפשרות למטה כדי להתחיל.',
        'player_select_00_01': 'השתמשו במוט השמאלי',
        'player_select_01_00': 'אישור ההגדרות',
        'player_select_02_00': 'להמשיך עם ההגדרות האלה?',
        'player_select_02_01': 'לא ניתן לשנות את השפה או את השם אחרי תחילת המשחק.',
        'player_select_03_00': 'שפה',
        'player_select_03_01': 'עברית',
        'player_select_04_00': 'שם',
        'player_select_06_00': 'שינוי צבע שיער',
        'player_select_06_01': 'שינוי מראה',
        'player_select_08_01': 'חזרה',
    },
    'strinput': {
        'msg_ui_strinput_playername_00': 'מה השם שלך?',
        'msg_ui_strinput_playername_02': 'אי אפשר להזין את השם הזה.',
        'msg_ui_strinput_playername_04': 'נא להזין שם.',
    },
    'questlist_main': {
        'msg_mainquest_title_2_1': 'חיים חדשים בעיר לומיוז',
        'msg_mainquest_purpose_2_1_41': 'בקרו באזור פראי כדי לתפוס פוקימונים.',
    },
    'common_text': {
        'msg_ui_common_text_03': 'שומר...',
    },
}


def main():
    extract, mod = sys.argv[1], sys.argv[2]
    report = []
    for name, lines in POC.items():
        src = os.path.join(extract, 'romfs', 'ik_message', 'dat', 'Korean', 'common', name)
        eng = os.path.join(extract, 'romfs', 'ik_message', 'dat', 'English', 'common', name)
        m = MsgFile(open(src + '.dat', 'rb').read())
        e = MsgFile(open(eng + '.dat', 'rb').read())
        labels = [n for _, n in read_tbl(open(src + '.tbl', 'rb').read())]
        for label, heb in lines.items():
            i = labels.index(label)
            vis = to_visual(heb)
            m.lines[i] = encode_text(vis)
            m.params[i] = e.params[i]          # (the Korean slot's grammar flags -> the English ones)
            report.append(dict(file=name, label=label, index=i, hebrew=heb, visual=vis,
                               english=decode_units(e.lines[i])))
        out = os.path.join(mod, 'romfs', 'ik_message', 'dat', 'Korean', 'common', name + '.dat')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        data = m.encode()
        assert MsgFile(data).lines == m.lines
        with open(out, 'wb') as f:
            f.write(data)
        print('wrote', out, len(data), 'bytes,', len(lines), 'lines replaced')
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(mod))), 'poc-translation.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()

"""Checks for rtl.py (run: python -X utf8 tools/test_rtl.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rtl import to_visual, wrap, Measure  # noqa: E402

CASES = [
    ('שמירת התקדמות', 'תומדקתה תרימש'),
    ('רויאל Z-A', 'Z-A לאיור'),
    ('פוקימונים שנתפסו ברמה {VAR 0201:0000} ומטה יצייתו לפקודות שלך',
     'ךלש תודוקפל ותייצי הטמו {VAR 0201:0000} המרב וספתנש םינומיקופ'),
    ('ההתקדמות שלך נשמרה!{VAR BE01}', '!הרמשנ ךלש תומדקתהה{VAR BE01}'),
    ('פגיעה {VAR FF00:0005}קריטית{VAR FF00:0000}!', '!{VAR FF00:0005}תיטירק{VAR FF00:0000} העיגפ'),
    ('(ניסיון) 3 פעמים', 'םימעפ 3 (ןויסינ)'),
    ('{VAR BE05:0005}{VAR 0102:0000} עלה לרמה {VAR 0202:0001}!{VAR BE01}',
     '{VAR BE05:0005}!{VAR 0202:0001} המרל הלע {VAR 0102:0000}{VAR BE01}'),
    ('שומר את ההרפתקה שלך...\nנא לא לכבות את המכשיר.', '...ךלש הקתפרהה תא רמוש\n.רישכמה תא תובכל אל אנ'),
    ('השתמש ב-{VAR BD0A:0006}Cancel כדי לברוח!', '!חורבל ידכ {VAR BD0A:0006}Cancel-ב שמתשה'),
    ('קיבלת {VAR 1001}{VAR 010A:0001}!', '!{VAR 1001}{VAR 010A:0001} תלביק'),
    ('{VAR 0201:0002}/{VAR 0201:0001}/{VAR 0203:0000,0000}', '{VAR 0201:0002}/{VAR 0201:0001}/{VAR 0203:0000,0000}'),
]

bad = 0
for src, want in CASES:
    got = to_visual(src)
    ok = got == want
    bad += not ok
    print('ok ' if ok else 'BAD', repr(src), '->', repr(got), '' if ok else '(want %r)' % want)

here = os.path.dirname(os.path.abspath(__file__))
m = Measure(os.path.join(here, '..', 'build', 'ZAHebrewSans-Regular.ttf'))
w = wrap('{VAR BD06:0000}{VAR 0102:0000} התיידד איתך עוד יותר,{VAR BE00}\nאבל{VAR BE00}\nהנקודות הבסיסיות שלו ירדו קצת.{VAR BE01}',
         m, 18000)
print(repr(w))
print(repr(to_visual(w)))

# dialogue box: 2 lines, then scroll (as the Korean files do)
w2 = wrap('{VAR BD06:0000}מתחת לרציף מחכה רכבת לשדה התעופה. אם תעלו עליה, תעזבו את העיר לומיוז ואת כל החברים שלכם. בטוח שאתם רוצים לעלות?', m, 16000, box_lines=2)
print(repr(w2))
print(repr(to_visual(w2)))
assert w2.count('{VAR BE00}\n') >= 1 and '{VAR BD06' not in w2
sys.exit(1 if bad else 0)

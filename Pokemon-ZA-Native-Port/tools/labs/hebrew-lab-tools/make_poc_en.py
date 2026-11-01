"""Proof of concept, alternative: Hebrew in the ENGLISH slot (works with an existing English save).

usage: python -X utf8 make_poc_en.py <extract dir> <mods dir> <regular.ttf> <bold.ttf>
The English slot's fonts (ui/font/bin/system26_bold_efigs*.bfcpx) chain or_font_eng -> Univers Next (Latin ranges)
-> FOT-UDKakugoC80Pro-DB/B (everything else). Univers has no Hebrew, so Hebrew falls through to UD Kakugo: this
replaces the two UD Kakugo files with the Hebrew font (re-wrapped as .bfotf, UD Kakugo's vertical metrics copied so
lines keep their height), and puts the same Hebrew lines as make_poc_mod.py into the English message files.
"""
import io
import os
import sys

from fontTools.ttLib import TTFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bfttf  # noqa: E402
from gfmsg import MsgFile, encode_text, read_tbl  # noqa: E402
from make_poc_mod import POC  # noqa: E402
from rtl import to_visual  # noqa: E402

def with_metrics(ttf_path, ref_sfnt):
    """our font with the reference font's vertical metrics (hhea / OS/2) so the line height stays the game's"""
    f = TTFont(ttf_path)
    ref = TTFont(io.BytesIO(ref_sfnt))
    for a in ('ascent', 'descent', 'lineGap'):
        setattr(f['hhea'], a, getattr(ref['hhea'], a))
    for a in ('sTypoAscender', 'sTypoDescender', 'sTypoLineGap', 'usWinAscent', 'usWinDescent'):
        setattr(f['OS/2'], a, getattr(ref['OS/2'], a))
    out = io.BytesIO()
    f.save(out)
    return out.getvalue(), (ref['hhea'].ascent, ref['hhea'].descent, ref['hhea'].lineGap)


def main():
    extract, mods, regular, bold = sys.argv[1:5]
    mod = os.path.join(mods, 'hebrew-en', 'romfs')
    fontdir = os.path.join(extract, 'fonts')
    for src_name, ttf in (('uifontbinFOT-UDKakugoC80Pro-DB.bfotf/ad10e404f1075731.bin', regular),
                          ('uifontbinFOT-UDKakugoC80Pro-B.bfotf/0109c54073624581.bin', bold)):
        orig = open(os.path.join(fontdir, src_name), 'rb').read()
        sfnt, metrics = with_metrics(ttf, bfttf.decode(orig))
        out_name = src_name.split('/')[0][len('uifontbin'):]
        out = os.path.join(mod, 'ui', 'font', 'bin', out_name)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        data = bfttf.encode(orig[:4], sfnt)
        assert bfttf.decode(data)[:len(sfnt)] == sfnt
        open(out, 'wb').write(data)
        print('font', out, len(data), 'bytes; vertical metrics from the original:', metrics)
    for name, lines in POC.items():
        src = os.path.join(extract, 'romfs', 'ik_message', 'dat', 'English', 'common', name)
        m = MsgFile(open(src + '.dat', 'rb').read())
        labels = [n for _, n in read_tbl(open(src + '.tbl', 'rb').read())]
        for label, heb in lines.items():
            m.lines[labels.index(label)] = encode_text(to_visual(heb))
        out = os.path.join(mod, 'ik_message', 'dat', 'English', 'common', name + '.dat')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(m.encode())
        print('text', out, len(lines), 'lines')


if __name__ == '__main__':
    main()

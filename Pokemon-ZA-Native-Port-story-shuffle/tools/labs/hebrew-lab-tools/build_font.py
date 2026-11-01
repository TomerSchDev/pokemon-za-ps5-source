"""Build a single TrueType font with Latin + Hebrew + the symbols the game's text uses, from OFL Noto fonts.

usage: python build_font.py <fonts-src dir> <out.ttf> [--weight Regular|Bold]

The game's font engine wants one sfnt with TrueType (glyf) outlines (runtime/hle/pl.c), so:
  Noto Sans (Latin, subset) + Noto Sans Hebrew + Noto Sans Math (only the symbols the game's text uses),
  unhinted, merged with fontTools; U+FF65 / U+30FB (bullets) and U+3000 are mapped onto existing glyphs.
All sources are SIL OFL 1.1; the result is a Modified Version under a new family name (OFL Reserved Font Names
are not used for it).
"""
import argparse
import os

from fontTools import subset
from fontTools.merge import Merger
from fontTools.ttLib import TTFont

LATIN = list(range(0x20, 0x7F)) + list(range(0xA0, 0x250)) + list(range(0x300, 0x370)) + \
    list(range(0x1E00, 0x1F00)) + list(range(0x2000, 0x2070)) + list(range(0x20A0, 0x20C1)) + \
    list(range(0x2100, 0x2150)) + [0x2190, 0x2191, 0x2192, 0x2193, 0x2212]
SYMBOLS = [0x2605, 0x2606, 0x266A, 0x266B, 0x2665, 0x2661, 0x2642, 0x2640, 0x2713, 0x25CF, 0x25CB, 0x25A0, 0x25A1,
           0x25CE, 0x25B3, 0x25B2, 0x25BC, 0x25BD, 0x2192, 0x2190, 0x2191, 0x2193, 0x221E, 0x2227, 0x00D7, 0x00F7]
HEBREW = list(range(0x0590, 0x0600)) + list(range(0xFB1D, 0xFB50)) + [0x200E, 0x200F, 0x20AA]


def sub(path, codes, out):
    opts = subset.Options()
    opts.hinting = False            # unhinted: the hinting programs of different fonts can't be merged
    opts.layout_features = ['*']
    opts.name_IDs = ['*']
    opts.notdef_outline = True
    opts.glyph_names = True
    opts.drop_tables += ['DSIG']
    f = TTFont(path)
    s = subset.Subsetter(opts)
    have = set(f.getBestCmap())
    s.populate(unicodes=[c for c in codes if c in have])
    s.subset(f)
    f.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--weight', default='Regular')
    a = ap.parse_args()
    w = a.weight
    tmp = os.path.dirname(os.path.abspath(a.out))
    parts = [
        sub(os.path.join(a.src, 'NotoSans-%s.ttf' % w), LATIN, os.path.join(tmp, '_latin.ttf')),
        sub(os.path.join(a.src, 'NotoSansHebrew-%s.ttf' % w), HEBREW + [0x20, 0xA0], os.path.join(tmp, '_hebrew.ttf')),
        sub(os.path.join(a.src, 'NotoSansMath-Regular.ttf'), SYMBOLS, os.path.join(tmp, '_symbols.ttf')),
    ]
    merged = Merger().merge(parts)
    for p in parts:
        os.remove(p)
    # bullets / ideographic space used by the English text: aliases of existing glyphs
    best = merged.getBestCmap()
    for t in merged['cmap'].tables:
        if t.isUnicode():
            for alias, target in ((0xFF65, 0x00B7), (0x30FB, 0x00B7), (0x3000, 0x2003)):
                if alias not in t.cmap and target in best:
                    t.cmap[alias] = best[target]
    fam = 'ZA Hebrew Sans'
    sub_name = 'Bold' if w == 'Bold' else 'Regular'
    name = merged['name']
    name.names = [n for n in name.names if n.nameID not in (1, 2, 3, 4, 6, 16, 17)]
    for pid, eid, lid in ((3, 1, 0x409), (1, 0, 0)):
        name.setName(fam, 1, pid, eid, lid)
        name.setName(sub_name, 2, pid, eid, lid)
        name.setName('%s %s; built from Noto Sans, Noto Sans Hebrew, Noto Sans Math (SIL OFL 1.1)' % (fam, sub_name), 3, pid, eid, lid)
        name.setName('%s %s' % (fam, sub_name), 4, pid, eid, lid)
        name.setName(('ZAHebrewSans-' + sub_name), 6, pid, eid, lid)
    merged.save(a.out)
    f = TTFont(a.out)
    cm = f.getBestCmap()
    print('%s: %d glyphs, glyf=%s, hebrew=%d, latin=%d, symbols=%d, upem=%d' % (
        a.out, f['maxp'].numGlyphs, 'glyf' in f, sum(1 for c in cm if 0x590 <= c < 0x600),
        sum(1 for c in cm if c < 0x250), sum(1 for c in SYMBOLS if c in cm), f['head'].unitsPerEm))


if __name__ == '__main__':
    main()

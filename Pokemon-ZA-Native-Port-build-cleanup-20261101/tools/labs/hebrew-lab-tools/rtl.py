"""Logical-order Hebrew message text -> visual order for the game's left-to-right text engine.

Input and output use gfmsg.py's token form ({VAR xxxx:args}, '\\n'). Each displayed line is reordered on its own
with the Unicode Bidirectional Algorithm (UAX #9, paragraph direction RTL, python-bidi's reference implementation),
so line breaks must be decided BEFORE this step (wrap() below, or explicit '\\n' in the translation).

Control sequences are handled as units:
  - name / word variables (0x01xx: player, Pokemon, move, item, place...)  -> one strong-R unit (Hebrew content)
  - number variables (0x02xx)                                            -> one EN unit (digits stay LTR)
  - grammar prefixes (0x1000-0x1003, 0x13xx, 0x1900) stay glued in front of the variable that follows them
  - icon references ({VAR BD0A:n} + n characters of the icon's name)    -> one neutral unit, never reversed
  - colour (0xFF00): the colour of each character is recorded and the switches are re-emitted in visual order
  - page / scroll breaks (0xBE00, 0xBE01) split lines like '\\n'; leading / trailing events keep their place
  - other zero-width events inside a line (waits 0xBE02, sounds 0xBE05, 0x0114...) move with the next character
The dynamic line-wrap marker {VAR BD06:0000} and its soft breaks ({VAR BE00}\\n) must not be used with visual-order
text (the engine would wrap the visual string from its logical end): wrap() replaces them with fixed breaks.
"""
import re

import bidi.algorithm as A

PLACEHOLDER = chr(0xE000)  # (stands for a variable during reordering; never emitted)
TOK = re.compile(r'\{VAR ([0-9A-F]{4})(?::([0-9A-F,]*))?\}')


def _kind(code):
    c = int(code, 16)
    if c == 0x0114:             # voice/event marker, not a substituted word
        return 'event'
    if 0x0200 <= c <= 0x02FF:
        return 'num'
    if 0x0100 <= c <= 0x01FF:
        return 'word'
    if c in (0x1000, 0x1001, 0x1002, 0x1003, 0x1900) or 0x1300 <= c <= 0x13FF:
        return 'prefix'
    if c == 0xFF00:
        return 'color'
    if c == 0xBD0A:
        return 'icon'
    if c in (0xBE00, 0xBE01):
        return 'break'
    if c in (0x1100, 0x1101):
        return 'branch'
    return 'event'


def _units(line):
    """one display line (no breaks) -> [(text_to_emit, bidi_type or None for a plain char, char, color, prefix_events)]"""
    out = []
    color = '0000'
    pending = []          # zero-width events / prefixes waiting for the next unit
    i = 0
    while i < len(line):
        m = TOK.match(line, i)
        if m:
            code, args = m.group(1), m.group(2) or ''
            k = _kind(code)
            tok = m.group(0)
            i = m.end()
            if k == 'color':
                color = args.split(',')[0]
                continue
            if k == 'prefix':
                pending.append(tok)
                continue
            if k == 'icon':
                n = int(args.split(',')[0], 16)
                name = line[i:i + n]
                i += n
                out.append((''.join(pending) + tok + name, 'ON', None, color))
                pending = []
                continue
            if k == 'word':
                out.append((''.join(pending) + tok, 'R', None, color))
                pending = []
                continue
            if k == 'num':
                out.append((''.join(pending) + tok, 'EN', None, color))
                pending = []
                continue
            if k == 'branch':
                raise ValueError('gender/number branches: give each alternative as its own whole word (see plan)')
            pending.append(tok)       # event: travels with the next character
            continue
        ch = line[i]
        i += 1
        if ch in '{}':                # the token form escapes literal braces as {{ }}
            i += 1
        out.append((''.join(pending) + (ch * (2 if ch in '{}' else 1)), None, ch, color))
        pending = []
    return out, ''.join(pending), color


LEAD = re.compile(r'(?:\{VAR (?:BE02|BE05|0114|BDFF|BD03)(?::[0-9A-F,]*)?\})+')


def _visual_line(line):
    lead = ''
    m = LEAD.match(line)
    if m:                         # events at the start of a line keep their place (they run before the reveal)
        lead, line = m.group(0), line[m.end():]
    units, trailing, end_color = _units(line)
    if not units:
        return lead + trailing
    storage = A.get_empty_storage()
    storage['base_level'] = 1
    storage['base_dir'] = 'R'
    for idx, (text, typ, ch, color) in enumerate(units):
        t = typ or A.bidirectional(ch)
        storage['chars'].append({'ch': ch if ch is not None else PLACEHOLDER, 'level': 1, 'type': t, 'orig': t,
                                 'unit': idx})
    A.explicit_embed_and_overrides(storage, False)
    A.resolve_weak_types(storage, False)
    A.resolve_neutral_types(storage, False)
    A.resolve_implicit_levels(storage, False)
    A.reorder_resolved_levels(storage, False)
    A.apply_mirroring(storage, False)
    out = []
    cur = '0000'
    for c in storage['chars']:
        text, typ, ch, color = units[c['unit']]
        if color != cur:
            out.append('{VAR FF00:%s}' % color)
            cur = color
        if ch is not None and c['ch'] != ch:      # mirrored bracket
            text = text[:len(text) - len(ch)] + c['ch']
        out.append(text)
    if cur != '0000' or end_color != '0000':
        out.append('{VAR FF00:0000}')
    return lead + ''.join(out) + trailing


BREAK = re.compile(r'(\{VAR BE0[01]\}\n?|\n)')


def to_visual(text):
    """logical token text (with its final line breaks) -> visual token text"""
    if '{VAR BD06' in text:
        raise ValueError('dynamic wrap marker BD06 in a visual-order line: wrap() first')
    parts = BREAK.split(text)
    out = []
    for p in parts:
        if BREAK.fullmatch(p or 'x'):
            out.append(p)
        elif p:
            out.append(_visual_line(p))
    return ''.join(out)


# ---------------------------------------------------------------------------------------------- line breaking
class Measure:
    """advance widths from a TrueType font, in font units; unknown variables get a fixed budget"""

    def __init__(self, ttf_path, var_widths=None):
        from fontTools.ttLib import TTFont
        f = TTFont(ttf_path)
        self.cmap = f.getBestCmap()
        self.hmtx = f['hmtx']
        self.upem = f['head'].unitsPerEm
        self.var_widths = var_widths or {'word': 12 * 560, 'num': 5 * 560, 'icon': 1000}

    def width(self, text):
        w = 0
        for m in re.finditer(r'\{VAR ([0-9A-F]{4})(?::([0-9A-F,]*))?\}|(.)', text, re.S):
            if m.group(3) is not None:
                g = self.cmap.get(ord(m.group(3)))
                w += self.hmtx[g][0] if g else self.upem // 2
            else:
                w += self.var_widths.get(_kind(m.group(1)), 0)
        return w


def wrap(text, measure, max_width_units, box_lines=None):
    """Greedy word wrap of logical text into lines no wider than max_width_units (font units at size 1 em).
    Removes the dynamic-wrap marker and its soft breaks; keeps page breaks ({VAR BE01}).
    box_lines (dialogue boxes: 2): inside a page, the lines after the box's last one scroll in ({VAR BE00}\\n, the
    text-return the Korean files use) instead of a plain '\\n'. None: plain '\\n' everywhere (menus, descriptions)."""
    text = text.replace('{VAR BD06:0000}', '').replace('{VAR BE00}\n', ' ')
    pages = re.split(r'(\{VAR BE01\}\n?)', text)
    out = []
    for pg in pages:
        if re.fullmatch(r'\{VAR BE01\}\n?', pg or 'x'):
            out.append(pg)
            continue
        lines = []
        for para in pg.split('\n'):
            cur = ''
            for word in para.split(' '):
                cand = word if not cur else cur + ' ' + word
                if cur and measure.width(cand) > max_width_units:
                    lines.append(cur)
                    cur = word
                else:
                    cur = cand
            lines.append(cur)
        page = lines[0] if lines else ''
        for k, ln in enumerate(lines[1:], 1):
            page += ('{VAR BE00}\n' if box_lines and k >= box_lines else '\n') + ln
        out.append(page)
    return ''.join(out)

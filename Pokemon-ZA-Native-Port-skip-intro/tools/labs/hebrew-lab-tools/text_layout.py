"""Font-aware logical wrapping before RTL conversion; all default window limits are heuristics.

No function guesses inline gender/number-branch semantics. Translation tokens are checked before
this render transformation; color switches may be re-emitted to keep a span across wrapped lines.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import io
import unicodedata
import hashlib

from fontTools.ttLib import TTFont
from rtl import TOK, to_visual
from localization_exemptions import preserved_item_identifier

LAB = Path(__file__).resolve().parents[1]
GRAMMAR = {0x1000, 0x1001, 0x1002, 0x1003, 0x1300, 0x1301, 0x1302, 0x1303, 0x1900}
EVENTS = {0x0114, 0xBE02, 0xBE05}
PROFILES = {
    'name': dict(width_em=16, max_lines=1, scroll=False),
    'menu': dict(width_em=20, max_lines=1, scroll=False),
    'battle': dict(width_em=30, max_lines=2, scroll=True),
    'dialogue': dict(width_em=32, max_lines=2, scroll=True),
    'description': dict(width_em=28, max_lines=4, scroll=False),
    'unknown': dict(width_em=30, max_lines=4, scroll=False),
}


class LayoutError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class Atom:
    text: str
    kind: str


def _utf16_end(text, start, count):
    end = start
    consumed = 0
    while end < len(text) and consumed < count:
        consumed += 2 if ord(text[end]) > 0xFFFF else 1
        end += 1
    if consumed != count:
        raise LayoutError('icon_payload', 'BD0A icon payload has an invalid UTF-16-unit length')
    return end


def atoms(text):
    """Lex complete tokens, BD0A+payload and escaped braces as indivisible atoms."""
    out = []
    pos = 0
    while pos < len(text):
        match = TOK.match(text, pos)
        if match:
            code = int(match[1], 16)
            end = match.end()
            if code == 0xBD0A:
                try:
                    count = int((match[2] or '').split(',')[0], 16)
                except ValueError as exc:
                    raise LayoutError('icon_payload', 'BD0A requires its original length argument') from exc
                end = _utf16_end(text, end, count)
                kind = 'icon'
            elif code in (0x1100, 0x1101):
                raise LayoutError('inline_branch', 'Inline 1100/1101 alternatives need manual review before wrapping/RTL')
            elif 0x0200 <= code <= 0x02FF:
                kind = 'number'
            elif 0x0100 <= code <= 0x01FF and code not in EVENTS:
                kind = 'word_variable'
            elif code in (0xBE00, 0xBE01):
                if match[2]:
                    raise LayoutError('break_arguments', 'Break control with arguments is not supported by the proven RTL path')
                kind = 'scroll' if code == 0xBE00 else 'page'
            else:
                if code not in GRAMMAR | EVENTS | {0xFF00,0xBD06,0xBDFF,0xBD03}:
                    raise LayoutError('unsupported_control', f'Control {code:04X} has no proven layout semantics; manual review required')
                if code==0xFF00 and (not match[2] or ',' in match[2]):
                    raise LayoutError('color_arguments', 'FF00 requires its single original color argument')
                kind = 'control'
            out.append(Atom(text[pos:end], kind))
            pos = end
        elif text.startswith('{{', pos) or text.startswith('}}', pos):
            out.append(Atom(text[pos:pos+2], 'literal_brace'))
            pos += 2
        elif text[pos] in '{}':
            raise LayoutError('malformed_token', 'Unescaped brace or malformed control token')
        else:
            ch = text[pos]
            out.append(Atom(ch, 'space' if ch.isspace() else 'char'))
            pos += 1
    return out


class FontMeasure:
    """Normalized em advances; name12/digits5/icon1em reservations are explicit estimates."""
    def __init__(self, font, *, word_chars=12, number_digits=5, icon_em=1.0, primary_font=None):
        self.path = Path(font)
        self.font_chain=[]
        self.metrics=[]
        if primary_font is None:
            candidate=LAB/'extract/fonts/uifontbinUniversNextPro-Cond.bfotf/06a846f4e17cc3ea.bin'
            primary_font=candidate if candidate.exists() else None
        if primary_font:
            import bfttf
            with TTFont(io.BytesIO(bfttf.decode(Path(primary_font).read_bytes()))) as face:
                self.metrics.append((dict(face.getBestCmap()),{k:v[0] for k,v in face['hmtx'].metrics.items()},face['head'].unitsPerEm))
            self.font_chain.append(str(primary_font))
        with TTFont(self.path) as face:
            self.cmap = dict(face.getBestCmap())
            self.widths = {k: v[0] for k, v in face['hmtx'].metrics.items()}
            self.upem = face['head'].unitsPerEm
        self.metrics.append((self.cmap,self.widths,self.upem))
        self.font_chain.append(str(self.path))
        letters = [self.char_width(c) for c in 'אבגדהוזחטיכלמנסעפצקרשת']
        self.word_em = word_chars * max(letters)
        self.number_em = number_digits * max(self.char_width(c) for c in '0123456789')
        self.icon_em = icon_em

    def char_width(self, char):
        for cmap,widths,upem in self.metrics:
            glyph=cmap.get(ord(char))
            if glyph:
                return widths[glyph]/upem
        return 0.6

    def width(self, text):
        result = 0.0
        for atom in atoms(text):
            if atom.kind == 'word_variable':
                result += self.word_em
            elif atom.kind == 'number':
                result += self.number_em
            elif atom.kind == 'icon' or (atom.kind == 'char' and 0xE300 <= ord(atom.text) <= 0xE34E):
                result += self.icon_em
            elif atom.kind == 'literal_brace':
                result += self.char_width(atom.text[0])
            elif atom.kind in ('space', 'char') and atom.text != '\n':
                result += self.char_width(atom.text)
        return result


def strip_grammar(text):
    """Remove only the agreed English grammar prefixes and dynamic-wrap marker."""
    return TOK.sub(lambda m: '' if int(m[1], 16) in GRAMMAR | {0xBD06} else m[0], text)


def _words(text):
    current = []
    out = []
    for atom in atoms(text):
        if atom.kind == 'space':
            if current:
                out.append(''.join(current))
                current = []
        else:
            current.append(atom.text)
    if current:
        out.append(''.join(current))
    return out


def _check_event_boundaries(text):
    # Only leading/terminal wait/voice/sound placement has a proven transformation.
    # Reordering an event in the middle of visible text could change reveal timing.
    for paragraph in re.split(r'\{VAR BE0[01]\}\n?|\n',text):
        sequence=atoms(paragraph)
        visible=[index for index,atom in enumerate(sequence) if atom.kind in ('char','literal_brace','icon','number','word_variable')]
        if not visible:
            continue
        for index,atom in enumerate(sequence):
            match=TOK.fullmatch(atom.text)
            if match and int(match[1],16) in EVENTS and visible[0]<index<visible[-1]:
                raise LayoutError('inline_event', 'Wait/sound/voice inside visible text needs manual review before RTL')


def wrap_logical(text, measure, *, width_em, max_lines=2, scroll=True):
    """Hard pages survive; soft scrolls are recomputed without splitting tokens/icon payloads."""
    atoms(text)  # refuses unsafe branches and malformed controls before modification
    _check_event_boundaries(text)
    text = strip_grammar(text)
    text = re.sub(r'\{VAR BE00\}\n?', ' ', text)
    parts = re.split(r'(\{VAR BE01\}\n?)', text)
    output = []
    all_widths = []
    for part in parts:
        if re.fullmatch(r'\{VAR BE01\}\n?', part):
            output.append(part)
            continue
        lines = []
        for paragraph in part.split('\n'):
            current = ''
            for word in _words(paragraph):
                if measure.width(word) > width_em + 1e-8:
                    raise LayoutError('unbreakable_overflow', 'A word/variable exceeds the estimated line budget; shorten or review the budget')
                candidate = current + ' ' + word if current else word
                if current and measure.width(candidate) > width_em + 1e-8:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            lines.append(current)
        if not scroll and len(lines) > max_lines:
            raise LayoutError('line_count', f'Estimated window allows {max_lines} lines, but needs {len(lines)}')
        all_widths.extend(measure.width(line) for line in lines)
        page = lines[0] if lines else ''
        for index, line in enumerate(lines[1:], 1):
            page += ('{VAR BE00}\n' if scroll and index >= max_lines else '\n') + line
        output.append(page)
    wrapped = ''.join(output)
    # A discarded soft break must not merge a terminal event into visible text.
    _check_event_boundaries(wrapped)
    # rtl._visual_line starts with default color on every line. Re-establish an active
    # logical span at each new line; RTL itself rebuilds its switches in visual order.
    split = re.split(r'(\{VAR BE0[01]\}\n?|\n)', wrapped)
    color = '0000'
    rebased = []
    for part in split:
        if re.fullmatch(r'\{VAR BE0[01]\}\n?|\n', part):
            rebased.append(part)
            continue
        if part and color != '0000':
            rebased.append('{VAR FF00:'+color+'}')
        rebased.append(part)
        for match in TOK.finditer(part):
            if match[1] == 'FF00':
                color = (match[2] or '0000').split(',')[0]
    return ''.join(rebased), all_widths


def reviewed_wait_breaks(record, text, review):
    """Insert only source-bound, explicitly reviewed line breaks after wait tokens."""
    source=record.get('source','')
    if (not isinstance(review,dict)
            or review.get('source_sha256')!=hashlib.sha256(source.encode('utf-8')).hexdigest()
            or not isinstance(review.get('reason'),str) or not review['reason'].strip()):
        raise LayoutError('event_break_review','Wait-line layout requires the exact reviewed source hash and a reason')
    tokens=review.get('after_tokens')
    if (not isinstance(tokens,list) or not tokens or any(not isinstance(t,str) for t in tokens)
            or len(set(tokens))!=len(tokens)):
        raise LayoutError('event_break_review','Wait-line layout requires unique wait tokens')
    for token in tokens:
        if (not re.fullmatch(r'\{VAR BE02:[0-9A-F]{4}\}',token)
                or not source.count(token) or source.count(token)!=text.count(token)):
            raise LayoutError('event_break_review','Only unchanged, reviewed wait tokens can force a line break')
        text=text.replace(token,token+'\n')
    return text


def layout_translation(record, text, measure, *, override=None):
    """Return logical wrapped text, visual text and honest layout provenance."""
    identifier=preserved_item_identifier(record)
    if identifier is not None:
        if text!=identifier:raise LayoutError('identifier_changed','A preserved item code differs from its source identifier')
        return dict(logical=text,visual=text,profile='preserved_item_identifier',needs_visual_qa=False,
                    budget={'provenance':'exact inspected code; no RTL transformation'},warnings=[])
    if text == record.get('source'):
        # An unchanged timed ellipsis, counter or icon is not Hebrew prose.
        # Preserve its original reveal/event order byte for byte. Word variables
        # can expand to Hebrew and are deliberately excluded from this path.
        parsed = atoms(text)
        if (not any(a.kind == 'word_variable' for a in parsed)
                and not any(unicodedata.category(c).startswith('L')
                            for a in parsed if a.kind in ('char', 'literal_brace')
                            for c in a.text)):
            return dict(logical=text, visual=text, profile='preserved_nonlinguistic',
                        needs_visual_qa=False, warnings=[],
                        budget={'provenance':'exact unchanged nonlinguistic source; no RTL transformation'})
    context = record.get('context') or {}
    profile_name = context.get('window_type', 'unknown') if isinstance(context, dict) else 'unknown'
    if any(code in record.get('source', '') for code in ('{VAR BE01', '{VAR BE00', '{VAR BD06')):
        profile_name = 'dialogue' if profile_name != 'battle' else 'battle'
    profile = dict(PROFILES.get(profile_name, PROFILES['unknown']))
    override = dict(override or {})
    for name in ('width_em', 'max_lines', 'scroll'):
        if name in override:
            profile[name] = override[name]
    if profile['width_em'] <= 0 or profile['max_lines'] < 1:
        raise LayoutError('profile', 'Invalid line budget')
    event_break_review=override.get('event_break_review')
    if event_break_review is not None:
        text=reviewed_wait_breaks(record,text,event_break_review)
    logical, widths = wrap_logical(text, measure, **profile)
    return dict(logical=logical, visual=to_visual(logical), profile=profile_name,
                budget={**profile, 'provenance': override.get('provenance', 'heuristic_window_profile_not_measured_ui')},
                line_widths_em=widths, needs_visual_qa=True,
                source_width_em=record.get('width_em'), font=str(measure.path),font_chain=measure.font_chain,
                event_break_review=event_break_review,
                variable_reservations=dict(word_max_glyph_chars=12, number_digits=5, icon_em=measure.icon_em))

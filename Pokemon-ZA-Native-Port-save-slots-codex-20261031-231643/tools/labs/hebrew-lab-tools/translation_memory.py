"""Private deterministic GFMSG translation memory and source-only batch preparation.

No translation service is called. Source batches are not permission to translate:
the separately approved glossary must be checked before translation/packaging.
Widths are original-text advances at nominal 28px, NOT measured window limits.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Iterable

from gfmsg import MsgFile, decode_units, read_tbl

LAB = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r"\{VAR ([0-9A-F]{4})(?::([0-9A-F,]*))?\}")
FONT_SIZE = 28.0
NAMES = {'monsname', 'event_pokename', 'wazaname', 'tokusei', 'typename', 'seikaku',
         'itemname', 'itemname_plural', 'itemname_acc', 'itemname_acc_classified',
         'itemname_classified', 'itemname_plural_classified', 'dressup_item_name',
         'place_name', 'place_name_indirect', 'place_name_out', 'place_name_per',
         'place_name_spe', 'nuts_name', 'another_name', 'namelist', 'emotename', 'boxname'}
LATE = {'iteminfo', 'wazainfo', 'tokuseiinfo', 'load_tips', 'tips', 'staff_list',
        'zukan_comment_A', 'zukan_comment_B', 'zkn_form', 'zkn_height', 'zkn_type', 'zkn_weight'}


def sha256(path: Path) -> str:
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def iter_tm(path: str | Path) -> Iterable[dict]:
    """Read strict JSONL without silently losing blank/malformed records or duplicate keys."""
    seen = set()
    with Path(path).open(encoding='utf-8-sig') as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict) or not isinstance(record.get('key'), str):
                raise ValueError(f'{path}:{line_no}: missing string key')
            if record['key'] in seen:
                raise ValueError(f'{path}:{line_no}: duplicate key {record["key"]}')
            seen.add(record['key'])
            yield record


def load_tm(path: str | Path) -> dict[str, dict]:
    return {r['key']: r for r in iter_tm(path)}


def _trie_pattern(terms):
    tree = {}
    for term in terms:
        node = tree
        for char in term.casefold():
            node = node.setdefault(char, {})
        node[''] = {}
    def pattern(node):
        branches = [re.escape(char) + pattern(child) for char, child in sorted(node.items()) if char]
        body = branches[0] if len(branches) == 1 else '(?:' + '|'.join(branches) + ')' if branches else ''
        return '(?:' + body + ')?' if '' in node and body else body
    return pattern(tree)


NAME_CATEGORY = {'monsname': 'pokemon', 'event_pokename': 'pokemon_nickname', 'wazaname': 'move',
                 'tokusei': 'ability', 'typename': 'type', 'seikaku': 'nature', 'itemname': 'item',
                 'itemname_plural': 'item_plural', 'dressup_item_name': 'clothing', 'trname': 'character',
                 'trtype': 'trainer_class', 'nuts_name': 'berry', 'zkn_form': 'pokemon_form',
                 'zkn_type': 'species_class', 'statusname': 'stat', 'namelist': 'character'}


class Glossary(dict):
    """Dictionary-compatible glossary with contextual collision information.

    Globally ambiguous English terms are absent from normal dictionary lookup.
    for_record resolves only an explicit name-list category, never guesses from a
    sentence. .conflicts retains all candidate rows for manual disambiguation.
    """
    def __init__(self, rows):
        self.rows = rows
        self.file_terms = {}
        global_rows = []
        for row in rows:
            if row['category'].startswith('file:'):
                file = row['category'][5:]
                terms = self.file_terms.setdefault(file, {})
                previous = terms.get(row['english'])
                if previous is not None and previous != row['hebrew']:
                    raise ValueError('conflicting file-scoped term: ' + row['english'])
                if row['hebrew']:
                    terms[row['english']] = row['hebrew']
            else:
                global_rows.append(row)
        self.conflicts = {}
        grouped = {}
        for row in global_rows:
            if row['hebrew']:
                grouped.setdefault(row['english'].casefold(), []).append(row)
        unambiguous = {}
        for folded, candidates in grouped.items():
            same_category = {}
            for row in candidates:
                prior = same_category.get(row['category'])
                if prior is not None and prior != row['hebrew']:
                    raise ValueError(f'conflicting same-category glossary term: {row["english"]} [{row["category"]}]')
                same_category[row['category']] = row['hebrew']
            if len({r['hebrew'] for r in candidates}) == 1:
                unambiguous[candidates[0]['english']] = candidates[0]['hebrew']
            else:
                self.conflicts[folded] = candidates
        super().__init__(unambiguous)
        self.all_terms = {row['english'].casefold(): row['english'] for row in global_rows if row['hebrew']}
        self.pattern = re.compile(r'(?<!\w)(?:' + _trie_pattern(self.all_terms) + r')(?!\w)', re.I) if self.all_terms else None
        self._context_cache = {}

    @staticmethod
    def _category_for_record(record):
        stem = Path(record.get('file', '')).stem
        category = NAME_CATEGORY.get(stem)
        context = record.get('context', {})
        if category is None and isinstance(context, dict) and context.get('category') == 'ui':
            category = 'ui'
        if stem.startswith('place_name'):
            category = 'place_phrase' if stem == 'place_name_indirect' else 'place'
        if stem.startswith('itemname_') and stem not in NAME_CATEGORY:
            category = 'item_plural' if 'plural' in stem else 'item'
        return category

    def _context_for_record(self, record):
        category = self._category_for_record(record)
        scoped = self.file_terms.get(record.get('file'), {})
        cache_key = (category, record.get('file') if scoped else None)
        if cache_key in self._context_cache:
            return self._context_cache[cache_key]
        result = dict(self)
        for candidates in self.conflicts.values():
            selected = [r for r in candidates if r['category'] == category]
            if selected and len({r['hebrew'] for r in selected}) == 1:
                result[selected[0]['english']] = selected[0]['hebrew']
        # A full name in its own table may translate differently from a word
        # occurring in narrative prose. Never leak these choices to other files.
        result.update(scoped)
        lookup = {en.casefold(): (en, he) for en, he in result.items()}
        # Callers must not mutate a shared cached context. Treat the whole
        # Glossary instance as immutable and reload it after a glossary update.
        pattern = re.compile(r'(?<!\w)(?:' + _trie_pattern(result) + r')(?!\w)', re.I) if result else None
        cached = (MappingProxyType(result), MappingProxyType(lookup), pattern)
        self._context_cache[cache_key] = cached
        return cached

    def for_record(self, record):
        """Read-only context mapping cached by effective name-list/UI category."""
        return self._context_for_record(record)[0]

    def lookup_for_record(self, record):
        """Read-only cached casefold -> (canonical English, Hebrew) lookup."""
        return self._context_for_record(record)[1]

    def match_pattern_for_record(self, record):
        return self._context_for_record(record)[2]


def load_glossary(path: str | Path) -> Glossary:
    """Read shared TSV; retain category collisions, omit blank draft Hebrew cells."""
    out = []
    raw = Path(path).read_bytes()
    with io.StringIO(raw.decode('utf-8-sig'), newline='') as f:
        rows = csv.DictReader(f, delimiter='\t')
        if not {'english', 'hebrew', 'category', 'note'} <= set(rows.fieldnames or []):
            raise ValueError('glossary must have english, hebrew, category, note columns')
        for n, row in enumerate(rows, 2):
            en, he = (row['english'] or '').strip(), (row['hebrew'] or '').strip()
            if not en:
                raise ValueError(f'empty English glossary term on row {n}')
            out.append({'english': en, 'hebrew': he, 'category': row['category'].strip(), 'note': row['note'] or ''})
    glossary = Glossary(out)
    glossary.source_sha256 = hashlib.sha256(raw).hexdigest()
    return glossary


def classify(file: str | Path) -> tuple[int, str, str]:
    p = Path(file)
    name, group = p.stem, p.parent.name
    if group == 'sk':
        return 3, 'dlc', 'dialogue'
    if group == 'script':
        return 2, 'story', 'dialogue'
    if name in NAMES or name.startswith('itemname'):
        return 1, 'names', 'name'
    if name.startswith('btl') or name in {'net_btl', 'vs_demo'}:
        return 1, 'battle', 'battle'
    if name in {'trmsg', 'trname', 'trtype', 'trainermemo'} or name.startswith('questlist'):
        return 2, 'story_support', 'dialogue' if name == 'trmsg' else 'description'
    if name in LATE or name.endswith('info') or name.startswith('zukan_'):
        return 3, 'descriptions', 'description'
    return 1, 'ui', 'menu'


def token_segments(text: str):
    """Yield literal chars or (kind, budget), consuming icon payload atomically."""
    i = 0
    while i < len(text):
        match = TOKEN.match(text, i)
        if match:
            code, args = int(match[1], 16), match[2] or ''
            i = match.end()
            if code == 0xBD0A:
                count = int(args.split(',')[0], 16) if args else 0
                i += count  # current extracted button names are ASCII
                yield ('icon', 1)
            elif 0x0100 <= code <= 0x01FF and code != 0x0114:
                yield ('word', 12)
            elif 0x0200 <= code <= 0x02FF:
                yield ('num', 5)
            elif code in (0xBE00, 0xBE01):
                yield '\n'
            continue
        if text.startswith(('{{', '}}'), i):
            yield text[i]
            i += 2
        else:
            yield text[i]
            i += 1


def needs_translation(text: str) -> bool:
    return bool(''.join(atom for atom in token_segments(text) if isinstance(atom, str)).strip())


class SourceMeasure:
    """Source Latin Univers metrics plus Hebrew fallback average, normalized to px.

    Kerning, per-widget scaling, live variable values and actual layout boxes are
    unavailable here. These values are provenance-tagged hints for later QA.
    """
    def __init__(self, extract: Path, hebrew_font: Path | None = None):
        import bfttf
        from fontTools.ttLib import TTFont
        candidates = sorted((extract / 'fonts' / 'uifontbinUniversNextPro-Cond.bfotf').glob('*.bin'))
        if len(candidates) != 1:
            raise ValueError('exactly one extracted UniversNextPro-Cond.bfotf is required')
        self.font_path = candidates[0]
        data = bfttf.decode(self.font_path.read_bytes())
        self.font = TTFont(io.BytesIO(data))
        self.cmap = self.font.getBestCmap()
        self.metrics = self.font['hmtx'].metrics
        self.upem = self.font['head'].unitsPerEm
        self.avg = sum(self.char_width(c) for c in 'abcdefghijklmnopqrstuvwxyz') / 26
        self.hebrew_avg = self.avg
        self.hebrew_path = hebrew_font
        if hebrew_font and hebrew_font.exists():
            hf = TTFont(hebrew_font)
            cmap, met, upem = hf.getBestCmap(), hf['hmtx'].metrics, hf['head'].unitsPerEm
            self.hebrew_avg = sum(met[cmap[ord(c)]][0] / upem * FONT_SIZE for c in 'אבגדהוזחטיכלמנסעפצקרשת') / 22
        self.unknown_chars = Counter()

    def char_width(self, c: str) -> float:
        glyph = self.cmap.get(ord(c))
        if glyph:
            return self.metrics[glyph][0] / self.upem * FONT_SIZE
        return FONT_SIZE * 0.5

    def measure(self, text: str) -> dict:
        lines, width = [], 0.0
        has_variables = False
        for atom in token_segments(text):
            if atom == '\n':
                lines.append(width)
                width = 0.0
            elif isinstance(atom, tuple):
                has_variables = True
                kind, count = atom
                width += FONT_SIZE if kind == 'icon' else count * self.avg
            elif atom == '\t':
                width += self.char_width(' ') * 4
            else:
                if ord(atom) not in self.cmap and not atom.isspace():
                    self.unknown_chars[f'U+{ord(atom):04X}'] += 1
                width += self.char_width(atom)
        lines.append(width)
        max_width = max(lines, default=0.0)
        return {'width_px': round(max_width, 3), 'width_em': round(max_width / FONT_SIZE, 6),
                'width_hint': max(1, math.ceil(max_width / self.hebrew_avg)) if text else 0,
                'font_size_px': FONT_SIZE,
                'width_source': 'original_source_advance_at_nominal_28px_not_verified_window',
                'width_has_variable_budgets': has_variables,
                'width_has_auto_wrap': '{VAR BD06' in text}


def extract_tm(extract: str | Path, output: str | Path, summary: str | Path | None = None) -> dict:
    extract, output = Path(extract), Path(output)
    english = extract / 'romfs' / 'ik_message' / 'dat' / 'English'
    files = sorted(english.glob('*/*.dat'), key=lambda p: (classify(p)[0], classify(p)[1], p.as_posix()))
    if not files:
        raise ValueError(f'no English source messages at {english}')
    measure = SourceMeasure(extract, LAB / 'build' / 'ZAHebrewSans-Regular.ttf')
    counts, nonempty, raw_nonempty, roundtrips, total = Counter(), Counter(), Counter(), 0, 0
    duplicate_labels = []
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f'refusing to overwrite existing TM: {output}')
    temporary = output.with_name(output.name + '.building')
    if temporary.exists():
        raise FileExistsError(f'previous interrupted extraction needs review: {temporary}')
    with temporary.open('w', encoding='utf-8', newline='\n') as target:
        for path in files:
            raw = path.read_bytes()
            msg = MsgFile(raw)
            if msg.encode() != raw:
                raise ValueError(f'GFMSG round-trip failed: {path.name}')
            roundtrips += 1
            labels = [n for _, n in read_tbl(path.with_suffix('.tbl').read_bytes())]
            if len(labels) != len(msg.lines) + 1:
                raise ValueError(f'label table mismatch: {path.name}')
            source = [decode_units(u) for u in msg.lines]
            stage, category, window = classify(path)
            relative = path.relative_to(extract / 'romfs').as_posix()
            digest = hashlib.sha256(raw).hexdigest()
            label_counts = Counter(labels[:-1]); occurrences = Counter()
            for label, count in label_counts.items():
                if count > 1:
                    duplicate_labels.append({'file': relative, 'label': label,
                                             'line_indices': [j for j,l in enumerate(labels[:-1]) if l == label]})
            for index, text in enumerate(source):
                label = labels[index]
                duplicate = label_counts[label] > 1
                key = relative + ':' + label + (f'#line={index}' if duplicate else '')
                record = {'key': key, 'file': relative, 'label': label,
                          'label_occurrence': occurrences[label], 'duplicate_label': duplicate,
                          'requires_translation': needs_translation(text),
                          'line_index': index, 'source': text, 'source_flags': msg.params[index],
                          'source_file_sha256': digest, 'stage': stage,
                          'context': {'category': category, 'previous': source[index-1] if index else None,
                                      'next': source[index+1] if index+1 < len(source) else None,
                                      'speaker': None, 'speaker_source': 'not_inferred', 'window_type': window,
                                      'window_source': 'filename_heuristic_requires_screen_QA'},
                          **measure.measure(text)}
                target.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
                total += 1
                counts[category] += 1
                nonempty[category] += needs_translation(text)
                raw_nonempty[category] += bool(text)
                occurrences[label] += 1
    temporary.rename(output)
    result = {'files': len(files), 'records': total, 'nonempty_records': sum(nonempty.values()),
              'raw_nonempty_records': sum(raw_nonempty.values()),
              'control_only_nonempty_records': sum(raw_nonempty.values()) - sum(nonempty.values()),
              'roundtrip_files_passed': roundtrips, 'by_category': dict(counts),
              'nonempty_by_category': dict(nonempty), 'tm_sha256': sha256(output),
              'width_font_file': measure.font_path.relative_to(extract).as_posix(),
              'width_font_sha256': sha256(measure.font_path), 'font_size_px': FONT_SIZE,
              'width_status': 'original text advance only; no actual window capacities measured',
              'variable_budgets': {'word_chars': 12, 'number_digits': 5, 'icon_em': 1},
              'source_missing_glyph_counts': dict(measure.unknown_chars),
              'duplicate_labels': duplicate_labels,
              'key_scheme': 'file:label; duplicate labels only use file:label#line=<zero-based index>',
              'game_translation_performed': False}
    if summary:
        p = Path(summary); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def relevant_glossary(source: str, glossary: dict[str, str], record: dict | None = None) -> dict[str, str]:
    """Whole source-term matches; longest first, deterministic. Does not guess morphology."""
    if isinstance(glossary, Glossary):
        lookup = glossary.lookup_for_record(record or {})
        pattern = glossary.match_pattern_for_record(record or {})
    else:
        lookup = {en.casefold(): (en, he) for en, he in glossary.items()}
        pattern = re.compile(r'(?<!\w)(?:' + _trie_pattern(glossary) + r')(?!\w)', re.I) if glossary else None
    matches = []
    if pattern:
        for match in pattern.finditer(source):
            pair = lookup.get(match[0].casefold())
            if pair and pair not in matches:
                matches.append(pair)
    return dict(sorted(matches, key=lambda item: (-len(item[0]), item[0].casefold(), item[0])))


def _batch_sizes(n: int, size: int) -> list[int]:
    if not 40 <= size <= 60:
        raise ValueError('batch size must be between 40 and 60')
    if not n:
        return []
    if n < 40:
        return [n]  # explicitly marked insufficient remainder in the manifest
    if 60 < n < 80:
        raise ValueError('61-79 records cannot be partitioned into complete batches of 40-60')
    count = max(1, math.ceil(n / size))
    while count > 1 and n // count < 40:
        count -= 1
    while math.ceil(n / count) > 60:
        count += 1
    return [n // count + (k < n % count) for k in range(count)]


def create_batches(tm_path: str | Path, glossary_path: str | Path, out_dir: str | Path, size: int = 50) -> dict:
    """Create source packets only. Packet manifest explicitly says glossary approval is pending.

    Each stage is separate so a small stage remainder never changes project order.
    Packet sizes are balanced to 40-60 when a stage has at least 40 records.
    """
    tm_path, glossary_path, out_dir = Path(tm_path), Path(glossary_path), Path(out_dir)
    # Bind packets to the input versions that were actually loaded, never to
    # whichever file contents happen to exist after a long batch generation.
    tm_digest, glossary_digest = sha256(tm_path), sha256(glossary_path)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f'batch output is not empty: {out_dir}')
    out_dir.mkdir(parents=True, exist_ok=True)
    glossary = load_glossary(glossary_path)
    if glossary.source_sha256 != glossary_digest:
        raise RuntimeError('glossary changed while loading; no batch manifest was published')
    records = [r for r in iter_tm(tm_path) if needs_translation(r.get('source', ''))]
    if sha256(tm_path) != tm_digest:
        raise RuntimeError('TM changed while loading; no batch manifest was published')
    priority = {'ui': 0, 'names': 1, 'battle': 2, 'story': 3, 'story_support': 4, 'dlc': 5, 'descriptions': 6}
    records.sort(key=lambda r: (r['stage'], priority.get(r.get('context', {}).get('category'), 99),
                                r.get('file', ''), r.get('line_index', 0)))
    groups = {stage: [r for r in records if r['stage'] == stage] for stage in (1, 2, 3)}
    index, ordinal = [], 0
    for stage, rows in groups.items():
        offset = 0
        for batch_size in _batch_sizes(len(rows), size):
            ordinal += 1
            chosen = rows[offset:offset+batch_size]; offset += batch_size
            name = f'stage{stage}-batch{ordinal:04d}.jsonl'
            path = out_dir / name
            with path.open('w', encoding='utf-8', newline='\n') as f:
                for record in chosen:
                    packet = {k: record[k] for k in ('key', 'file', 'label', 'line_index', 'stage', 'source',
                                                       'context', 'width_hint', 'width_px', 'width_em',
                                                       'font_size_px', 'width_source') if k in record}
                    packet['glossary'] = relevant_glossary(record['source'], glossary, record)
                    if glossary.pattern:
                        unresolved = {m[0].casefold() for m in glossary.pattern.finditer(record['source'])
                                      if m[0].casefold() in glossary.conflicts and
                                      not any(k.casefold() == m[0].casefold() for k in packet['glossary'])}
                        if unresolved:
                            packet['glossary_conflicts'] = {key: glossary.conflicts[key] for key in sorted(unresolved)}
                    f.write(json.dumps(packet, ensure_ascii=False, separators=(',', ':')) + '\n')
            index.append({'file': name, 'stage': stage, 'records': batch_size,
                          'size_exception': None if 40 <= batch_size <= 60 else 'stage has fewer than 40 records',
                          'first_key': chosen[0]['key'], 'last_key': chosen[-1]['key'], 'sha256': sha256(path)})
    if sha256(tm_path) != tm_digest or sha256(glossary_path) != glossary_digest:
        raise RuntimeError('TM/glossary changed during generation; incomplete packets are quarantined and no manifest was published')
    manifest = {'schema': 1, 'tm_sha256': tm_digest, 'glossary_sha256': glossary_digest,
                'inputs_verified_unchanged': True,
                'glossary_approval': 'required_before_translation', 'translation_performed': False,
                'records': len(records), 'batches': len(index), 'by_stage': {str(k): len(v) for k,v in groups.items()},
                'batch_index': index}
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='op', required=True)
    extract = sub.add_parser('extract')
    extract.add_argument('--extract', type=Path, default=LAB/'extract')
    extract.add_argument('--out', type=Path, required=True)
    extract.add_argument('--summary', type=Path)
    batches = sub.add_parser('batches')
    batches.add_argument('--tm', type=Path, required=True)
    batches.add_argument('--glossary', type=Path, required=True)
    batches.add_argument('--out', type=Path, required=True)
    batches.add_argument('--size', type=int, default=50)
    args = parser.parse_args()
    result = extract_tm(args.extract, args.out, args.summary) if args.op == 'extract' else create_batches(args.tm, args.glossary, args.out, args.size)
    print(json.dumps({k:v for k,v in result.items() if k != 'batch_index'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

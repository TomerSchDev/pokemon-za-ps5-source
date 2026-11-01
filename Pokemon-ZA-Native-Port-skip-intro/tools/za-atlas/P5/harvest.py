#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P5 of the za-atlas: harvest the names the existing research already established into annotations.jsonl.

Inputs (all read-only): knowledge.py (curated rows with their file:line sources), the block-key site scan of
rando-v2 (port/rando-v2/research/block-key-sites-2.0.2.json), PKHeX's SaveBlockAccessor9ZA.cs (key values for
the notes) and the function index built by index_functions.py. Every address is verified to exist in the
translated code: as a function definition (index), a label (^L_<addr>:) or a literal / ADRP+ADD constant, with one
ripgrep pass over the AOT tree at BelowNormal priority. Rows that fail go to unverified.jsonl, not annotations.

usage: harvest.py --repo REPO --aot AOT_DIR --out PARTS_P5_DIR --agent ID
"""
import argparse
import collections
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import knowledge  # noqa: E402

FIELDS = ('addr', 'name', 'subsystem', 'confidence', 'source', 'note')
BLOCK_SITES = 'port/rando-v2/research/block-key-sites-2.0.2.json'
ACCESSOR = 'save-workbench/deps/PKHeX/PKHeX.Core/Saves/Access/SaveBlockAccessor9ZA.cs'
AGGREGATE_ABOVE = 4  # a function with more key sites than this gets one aggregated record


def lower_priority():
    if os.name == 'nt':
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL_PRIORITY_CLASS
        except Exception:
            pass
    else:
        try:
            os.nice(10)
        except Exception:
            pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_index(path):
    idx = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            r = json.loads(line)
            idx[r['addr']] = (r['module'], r['unit'], r['line'])
    return idx


def accessor_keys(repo):
    text = (repo / ACCESSOR).read_text('utf-8')
    keys = {}
    for i, line in enumerate(text.splitlines(), 1):
        m = re.search(r'const\s+uint\s+(K\w+)\s*=\s*0x([0-9A-Fa-f]{8})\s*;\s*(?://\s*(.*))?', line)
        if m:
            keys[m.group(1)] = (m.group(2).upper(), (m.group(3) or '').strip(), i)
    return keys


def block_site_rows(repo, keys):
    """One row per block-key site (or one per function when it has many), sourced to the scan JSON's line."""
    path = repo / BLOCK_SITES
    text = path.read_text('utf-8')
    site_re = re.compile(r'\{\s*"key": "(\w+)",\s*"name": "(\w+)",\s*"file": "([^"]+)",\s*"line": (\d+),\s*'
                         r'"function": "(f_[0-9a-f]+)",\s*"next_call": (null|"f_[0-9a-f]+")\s*\}')
    sites = []
    for m in site_re.finditer(text):
        json_line = text.count('\n', 0, m.start()) + 1
        nxt = None if m.group(6) == 'null' else m.group(6).strip('"')
        sites.append(dict(key=m.group(1), name=m.group(2), unit=m.group(3), line=int(m.group(4)),
                          func=m.group(5)[2:], next_call=nxt, json_line=json_line))
    by_func = collections.defaultdict(list)
    for s in sites:
        by_func[s['func']].append(s)
    rows = []
    for func, group in by_func.items():
        areas = sorted({knowledge.KEY_AREA.get(s['name'], 'save-blocks') for s in group})
        subsystem = areas[0] if len(areas) == 1 else 'save-blocks'
        if len(group) > AGGREGATE_ABOVE:
            names = [s['name'] for s in group]
            prefixes = sorted({re.match(r'K[A-Z][a-z]+', n).group(0) if re.match(r'K[A-Z][a-z]+', n) else n for n in names})
            unit = group[0]['unit']
            first, last = min(s['line'] for s in group), max(s['line'] for s in group)
            calls = sorted({s['next_call'] for s in group if s['next_call']})
            note = (f'Builds {len(group)} save-block keys as immediates (MOVZ+MOVK or imm32) in {unit}:{first}-{last}: '
                    + ', '.join(f"{s['name']}=0x{s['key']}" for s in group)
                    + ('. Next calls after the keys: ' + ', '.join(calls) if calls else '')
                    + '. Load/save direction not researched; see PKHeX SaveBlockAccessor9ZA.cs for the block layouts.')
            rows.append((func, f"SaveBlock::{'/'.join(prefixes)}* ({len(group)} keys)", subsystem, 'proven',
                         f"{BLOCK_SITES}:{group[0]['json_line']}", note))
        else:
            for s in group:
                comment = keys.get(s['name'], ('', '', 0))[1]
                note = (f"References save block {s['name']} = 0x{s['key']} (immediate at {s['unit']}:{s['line']})"
                        + (f"; next call f_{s['next_call'][2:]}" if s['next_call'] else '')
                        + (f". PKHeX: {comment}" if comment else '')
                        + '. Role (load/save/other) only where another annotation says so.')
                rows.append((func, f"SaveBlock::{s['name']}", knowledge.KEY_AREA.get(s['name'], 'save-blocks'), 'proven',
                             f"{BLOCK_SITES}:{s['json_line']}", note))
    # next-call helpers that no curated row names: keep them findable, clearly marked assumed
    data = json.loads(text)
    curated = {r[0] for r in knowledge.CURATED}
    examples = collections.defaultdict(list)
    for s in sites:
        if s['next_call']:
            examples[s['next_call'][2:]].append(s['name'])
    for fn, count in data['next_calls'].items():
        addr = fn[2:]
        if addr in curated or count < 2:
            continue
        ex = sorted(set(examples[addr]))
        rows.append((addr, 'SaveBlock::KeyedAccessHelper', 'save-blocks', 'assumed', f'{BLOCK_SITES}:102-128',
                     f'First call after a save-block key constant at {count} sites (keys: ' + ', '.join(ex[:8])
                     + ('...' if len(ex) > 8 else '') + '); presumably takes &key. Role not researched.'))
    return rows, len(sites), len(by_func), data


def verify(rows, index, aot):
    """Classify every address: function (index), label / literal / ADRP+ADD (one ripgrep pass), or region."""
    regions = {r[0] for r in knowledge.REGIONS}
    result = {}
    needles = []
    for addr, *_ in rows:
        if addr in index:
            mod, unit, line = index[addr]
            result[addr] = ('function', f'{unit}:{line}', 1)
        elif addr in regions:
            result[addr] = ('region', 'runtime memory-map constant, not a code reference', 0)
        else:
            needles.append(addr)
    needles = sorted(set(needles))
    counts = collections.Counter()
    where = {}
    if needles:
        pats = []
        for a in needles:
            pats.append(rf'^L_{a}:')
            pats.append(rf'0x{a}ull')
            page, off = a[:-3] + '000', int(a[-3:], 16)
            if off:  # ADRP page, then the ADD / LDR offset within the next 4 lines
                pats.append(rf'0x{page}ull\);\r?\n([^\n]*\n){{0,3}}[^\n]*\+ 0x{off:x}ull')
        pattern = '|'.join(pats)
        cmd = ['rg', '--json', '-U', '--threads', '3', '-e', pattern, str(aot / 'main'), str(aot / 'sdk')]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if proc.returncode not in (0, 1):
            raise RuntimeError('rg failed: ' + proc.stderr[-2000:])
        for line in proc.stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get('type') != 'match':
                continue
            path = Path(ev['data']['path']['text']).name
            for sm in ev['data']['submatches']:
                t = sm['match']['text']
                if t.startswith('L_'):
                    addr, kind = t[2:-1], 'label'
                else:
                    hexes = re.findall(r'0x([0-9a-f]+)ull', t)
                    if len(hexes) >= 2:  # page constant first, the '+ 0x<off>ull' the pattern ends with last
                        addr, kind = f'{int(hexes[0], 16) + int(hexes[-1], 16):x}', 'adrp_add'
                    else:
                        addr, kind = hexes[0], 'literal'
                if addr in needles:
                    counts[(addr, kind)] += 1
                    where.setdefault((addr, kind), f"{path}:{ev['data']['line_number']}")
    for a in needles:
        kinds = [k for k in ('label', 'literal', 'adrp_add') if counts[(a, k)]]
        if not kinds:
            result[a] = ('missing', 'not found in the translated code', 0)
        elif 'label' in kinds:
            result[a] = ('label', where[(a, 'label')], counts[(a, 'label')])
        else:
            n = sum(counts[(a, k)] for k in kinds)
            result[a] = ('data', f"{'+'.join(kinds)} refs, first {where[(a, kinds[0])]}", n)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--aot', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--agent', required=True)
    a = ap.parse_args()
    lower_priority()
    t0 = time.time()
    started = time.strftime('%Y-%m-%dT%H:%M:%S')
    index_path = a.out / '.work' / 'func-index.jsonl'
    index = load_index(index_path)
    keys = accessor_keys(a.repo)

    rows = list(knowledge.CURATED)
    # giant single-function units named by the compile-gaps research: sdk_090.c has exactly one function
    sdk090 = [addr for addr, (mod, unit, line) in index.items() if unit == 'sdk_090.c']
    if len(sdk090) == 1:
        rows.append((sdk090[0], 'giant:sdk_090 (1,937 labels)', 'build-giants', 'proven',
                     'analysis/ps5-runtime-compile-gaps.md:203',
                     'The only function of sdk_090.c (228,550 bytes of C, 1,937 labels): -O1 takes 37.7 s, so the giant policy compiles it at -O0.'))
    site_rows, n_sites, n_site_funcs, sites_json = block_site_rows(a.repo, keys)
    rows += site_rows
    rows += list(knowledge.REGIONS)

    ver = verify(rows, index, a.aot)
    annotations, unverified = [], []
    for addr, name, subsystem, confidence, source, note in rows:
        kind, detail, n = ver[addr]
        if kind == 'function':
            suffix = f' [function, defined {detail}]'
        elif kind == 'label':
            suffix = f' [label L_{addr} in {detail}]'
        elif kind == 'data':
            suffix = f' [data address, {n} {detail}]'
        elif kind == 'region':
            suffix = f' [region: {detail}]'
        else:
            suffix = ' [UNVERIFIED: not found in the translated code]'
        rec = dict(addr=addr, name=name, subsystem=subsystem, confidence=confidence, source=source, note=note + suffix)
        (unverified if kind == 'missing' else annotations).append(rec)
    annotations.sort(key=lambda r: (r['addr'], r['name']))

    a.out.mkdir(parents=True, exist_ok=True)
    ann_path = a.out / 'annotations.jsonl'
    with ann_path.open('w', encoding='utf-8', newline='\n') as fh:
        for rec in annotations:
            fh.write(json.dumps({k: rec[k] for k in FIELDS}, ensure_ascii=False) + '\n')
    unv_path = a.out / 'unverified.jsonl'
    with unv_path.open('w', encoding='utf-8', newline='\n') as fh:
        for rec in unverified:
            fh.write(json.dumps({k: rec[k] for k in FIELDS}, ensure_ascii=False) + '\n')

    kinds = collections.Counter(ver[r['addr']][0] for r in annotations)
    by_sub = collections.Counter(r['subsystem'] for r in annotations)
    by_conf = collections.Counter(r['confidence'] for r in annotations)
    distinct = len({r['addr'] for r in annotations})
    seconds = round(time.time() - t0, 1)
    done = {
        'package': 'P5', 'agent': a.agent, 'started': started, 'finished': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'seconds': seconds,
        'files': {p.name: {'records': n, 'bytes': p.stat().st_size, 'sha256': sha256_file(p)}
                  for p, n in ((ann_path, len(annotations)), (unv_path, len(unverified)))},
        'records': {'annotations': len(annotations), 'distinct_addresses': distinct, 'unverified_excluded': len(unverified),
                    'by_kind': dict(kinds), 'by_confidence': dict(by_conf), 'by_subsystem': dict(sorted(by_sub.items()))},
        'unverified': [{'addr': r['addr'], 'name': r['name'], 'source': r['source']} for r in unverified],
        'inputs': {
            'curated_rows': len(knowledge.CURATED), 'region_rows': len(knowledge.REGIONS),
            'block_key_sites': {'sites': n_sites, 'functions': n_site_funcs, 'keys_found': len(sites_json['keys_found']),
                                'keys_not_found': sites_json['keys_not_found'],
                                'aggregated_when_more_than': AGGREGATE_ABOVE},
            'pkhex_block_keys': len(keys), 'function_index': {'path': str(index_path), 'functions': len(index)},
        },
        'verification': 'every address checked against the translated code: function definition (index of all 1,411 '
                        'units), label ^L_<addr>:, or literal 0x<addr>ull / ADRP+ADD page+offset (one ripgrep pass); '
                        'region rows are runtime constants and are marked as such',
        'limits': [
            'Names come only from the existing research documents and scripts (listed in knowledge.py); nothing was '
            're-derived from the game code beyond verifying that each address exists.',
            'Music/Wwise: the music randomizer works on BGM.bnk and bgm_command.bin data through the LayeredFS; the '
            'research names no translated game function, so the subsystem has no code annotations.',
            'Battle: only the capture formula and the Royale save blocks are annotated; no battle-engine functions were '
            'identified by the research. Spawn/encounters: FixInitSpec and the spawner save blocks only; the 238 alpha '
            '(oyabunProbability) candidate functions of cheats-r28 are unverified heuristics and were not annotated.',
            'EXP formula, Mega gauge setter, Pokedex runtime layout and the KEventFlag/KEventWork/KSaveRevision access '
            'paths (19 keys not built as immediates) were not found by the research and are absent here.',
            'Render thread / NVN: only the three hot -O0 giants of the r24prof profile and the present-interval chain are '
            'named; the NVN API itself is HLE in the runtime (P4).',
            'Addresses of other builds (1.0.0 / 2.0.0 patch sites, HOT_GIANTS list) were deliberately excluded.',
            'Block-key sites: load/save direction is stated only where the rando-v2 research proved it; a function with '
            f'more than {AGGREGATE_ABOVE} key sites is one aggregated record with all keys in the note.',
            'Annotations use the exact schema addr/name/subsystem/confidence/source/note; kind (function/label/data/'
            'region) and the defining unit:line are appended to the note.',
        ],
    }
    (a.out / 'DONE.json').write_text(json.dumps(done, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'annotations': len(annotations), 'distinct_addresses': distinct, 'unverified': len(unverified),
                      'kinds': dict(kinds), 'seconds': seconds}))
    for rec in unverified:
        print('UNVERIFIED', rec['addr'], rec['name'], file=sys.stderr)


if __name__ == '__main__':
    main()

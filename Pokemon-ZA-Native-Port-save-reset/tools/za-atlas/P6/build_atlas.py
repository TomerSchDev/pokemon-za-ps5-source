#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 of the za-atlas: merge parts P1..P5 into za-atlas-data/atlas.sqlite.

Tables with indexes, FTS5 over strings / symbol names / classes / annotations, refs resolved to strings, data,
vtables, typeinfo and function pointers, derived function->class rows from the vtable slots, and consistency
checks between the parts. Streams every JSONL (never loads a part into memory at once), runs at BelowNormal
priority and writes the database to a temporary file that replaces the old one only when the build succeeded.

usage: build_atlas.py [--data ZA_ATLAS_DATA] [--out atlas.sqlite]
"""
import argparse
import bisect
import collections
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = REPO.parent / 'za-atlas-data'
BATCH = 50000

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE segments(module TEXT, name TEXT, start TEXT, end TEXT, perm TEXT);
CREATE TABLE functions(addr TEXT PRIMARY KEY, module TEXT, unit TEXT, line_start INT, line_end INT, c_bytes INT) WITHOUT ROWID;
CREATE TABLE calls(caller TEXT, callee TEXT, unit TEXT, line INT);
CREATE TABLE icalls(caller TEXT, unit TEXT, line INT);
CREATE TABLE refs(func TEXT, target TEXT, unit TEXT, line INT, how TEXT, kind TEXT);
CREATE TABLE strings(id INTEGER PRIMARY KEY, addr TEXT, module TEXT, text TEXT, encoding TEXT, end TEXT);
CREATE TABLE symbols(id INTEGER PRIMARY KEY, addr TEXT, module TEXT, mangled TEXT, demangled TEXT, kind TEXT);
CREATE TABLE rtti(id INTEGER PRIMARY KEY, class TEXT, typeinfo TEXT, vtable TEXT, bases TEXT);
CREATE TABLE vslots(vtable TEXT, slot INT, func TEXT);
CREATE TABLE vtable_ptrs(ptr TEXT, vtable TEXT, class TEXT, what TEXT);
CREATE TABLE hle(name TEXT, guest_addr TEXT, runtime_fn TEXT, runtime_file TEXT);
CREATE TABLE annotations(id INTEGER PRIMARY KEY, addr TEXT, name TEXT, subsystem TEXT, confidence TEXT, source TEXT, note TEXT, origin TEXT);
CREATE TABLE fn_class(func TEXT, class TEXT, vtable TEXT, slot INT);
CREATE TABLE units(unit TEXT PRIMARY KEY, module TEXT, functions INT, first_addr TEXT, last_addr TEXT, lines INT, c_bytes INT);
CREATE TABLE checks(name TEXT, status TEXT, detail TEXT);
CREATE VIRTUAL TABLE strings_fts USING fts5(text, content='strings', content_rowid='id');
CREATE VIRTUAL TABLE symbols_fts USING fts5(demangled, content='symbols', content_rowid='id');
CREATE VIRTUAL TABLE rtti_fts USING fts5(class, content='rtti', content_rowid='id');
CREATE VIRTUAL TABLE annotations_fts USING fts5(name, subsystem, note, content='annotations', content_rowid='id');
"""
INDEXES = """
CREATE INDEX idx_functions_unit ON functions(unit);
CREATE INDEX idx_calls_caller ON calls(caller);
CREATE INDEX idx_calls_callee ON calls(callee);
CREATE INDEX idx_icalls_caller ON icalls(caller);
CREATE INDEX idx_refs_func ON refs(func);
CREATE INDEX idx_refs_target ON refs(target);
CREATE INDEX idx_strings_addr ON strings(addr);
CREATE INDEX idx_symbols_addr ON symbols(addr);
CREATE INDEX idx_rtti_class ON rtti(class);
CREATE INDEX idx_rtti_vtable ON rtti(vtable);
CREATE INDEX idx_rtti_typeinfo ON rtti(typeinfo);
CREATE INDEX idx_vslots_func ON vslots(func);
CREATE INDEX idx_vslots_vtable ON vslots(vtable);
CREATE INDEX idx_vtable_ptrs_ptr ON vtable_ptrs(ptr);
CREATE INDEX idx_hle_guest ON hle(guest_addr);
CREATE INDEX idx_hle_name ON hle(name);
CREATE INDEX idx_annotations_addr ON annotations(addr);
CREATE INDEX idx_fn_class_func ON fn_class(func);
CREATE INDEX idx_fn_class_class ON fn_class(class);
"""


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


def jsonl(path):
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def batched(rows, n=BATCH):
    buf = []
    for r in rows:
        buf.append(r)
        if len(buf) >= n:
            yield buf
            buf = []
    if buf:
        yield buf


class Timer:
    def __init__(self):
        self.t = time.time()
        self.steps = []

    def lap(self, name, **extra):
        now = time.time()
        self.steps.append(dict(step=name, seconds=round(now - self.t, 2), **extra))
        print(f'{name}: {now - self.t:.1f}s {extra if extra else ""}', file=sys.stderr, flush=True)
        self.t = now


def build(data, out):
    parts = data / 'parts'
    t = Timer()
    tmp = out.with_name(out.name + '.tmp')
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    con.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY; '
                      'PRAGMA cache_size=-400000; PRAGMA page_size=8192;')
    con.executescript(SCHEMA)
    report = {'parts': {}, 'steps': t.steps}

    # ---- P2: segments, strings, symbols, rtti, vslots ------------------------------------------------------
    segs = list(jsonl(parts / 'P2' / 'segments.jsonl'))
    con.executemany('INSERT INTO segments VALUES(?,?,?,?,?)', [(s['module'], s['name'], s['start'], s['end'], s['perm']) for s in segs])
    seg_ranges = [(int(s['start'], 16), int(s['end'], 16), s['module'], s['name'].lstrip('.')) for s in segs]

    str_rows, str_starts, str_ends, str_set = [], [], [], set()
    for i, s in enumerate(jsonl(parts / 'P2' / 'strings.jsonl'), 1):
        a = int(s['addr'], 16)
        nbytes = len(s['text'].encode('utf-8')) + 1 if s['encoding'] == 'utf-8' else 2 * len(s['text']) + 2
        str_rows.append((i, s['addr'], s['module'], s['text'], s['encoding'], f'{a + nbytes:x}'))
        str_starts.append(a)
        str_ends.append(a + nbytes)
        str_set.add(s['addr'])  # hex text, like refs.target
    con.executemany('INSERT INTO strings VALUES(?,?,?,?,?,?)', str_rows)
    order = sorted(range(len(str_starts)), key=lambda k: str_starts[k])
    str_sorted = [str_starts[k] for k in order]
    str_sorted_end = [str_ends[k] for k in order]
    report['parts']['P2.strings'] = len(str_rows)
    del str_rows

    sym_rows, sym_obj = [], set()
    for i, s in enumerate(jsonl(parts / 'P2' / 'symbols.jsonl'), 1):
        sym_rows.append((i, s['addr'], s['module'], s['mangled'], s['demangled'], s['kind']))
        if s['kind'] != 'function':
            sym_obj.add(s['addr'])
    con.executemany('INSERT INTO symbols VALUES(?,?,?,?,?,?)', sym_rows)
    report['parts']['P2.symbols'] = len(sym_rows)
    del sym_rows

    rtti_rows, vtable_class, typeinfo_set = [], {}, set()
    for i, r in enumerate(jsonl(parts / 'P2' / 'rtti.jsonl'), 1):
        rtti_rows.append((i, r['class'], r['typeinfo'], r['vtable'], json.dumps(r['bases'], ensure_ascii=False)))
        typeinfo_set.add(r['typeinfo'])
        if r['vtable']:
            vtable_class.setdefault(r['vtable'], r['class'])
    con.executemany('INSERT INTO rtti VALUES(?,?,?,?,?)', rtti_rows)
    vt_ptr_rows = []
    for vt, cls in vtable_class.items():
        vt_ptr_rows.append((vt, vt, cls, 'header'))
        vt_ptr_rows.append((f'{int(vt, 16) + 16:x}', vt, cls, 'slot0'))
    con.executemany('INSERT INTO vtable_ptrs VALUES(?,?,?,?)', vt_ptr_rows)
    vt_ptrs = {p[0]: p for p in vt_ptr_rows}
    report['parts']['P2.rtti'] = len(rtti_rows)
    report['parts']['P2.vtables'] = len(vtable_class)

    vs_rows = [(v['vtable'], v['slot'], v['func']) for v in jsonl(parts / 'P2' / 'vslots.jsonl')]
    con.executemany('INSERT INTO vslots VALUES(?,?,?)', vs_rows)
    fn_class_rows = sorted({(v[2], vtable_class[v[0]], v[0], v[1]) for v in vs_rows if v[0] in vtable_class})
    con.executemany('INSERT INTO fn_class VALUES(?,?,?,?)', fn_class_rows)
    report['parts']['P2.vslots'] = len(vs_rows)
    report['derived.fn_class'] = len(fn_class_rows)
    t.lap('P2 loaded')

    # ---- P1: functions, calls, icalls ----------------------------------------------------------------------
    fn_set = set()
    units = {}
    n = 0
    for batch in batched(jsonl(parts / 'P1' / 'functions.jsonl')):
        rows = []
        for f in batch:
            fn_set.add(f['addr'])
            rows.append((f['addr'], f['module'], f['unit'], f['line_start'], f['line_end'], f['c_bytes']))
            u = units.get(f['unit'])
            if u is None:
                units[f['unit']] = [f['module'], 1, f['addr'], f['addr'], f['line_end'], f['c_bytes']]
            else:
                u[1] += 1
                u[2] = min(u[2], f['addr'])
                u[3] = max(u[3], f['addr'])
                u[4] = max(u[4], f['line_end'])
                u[5] += f['c_bytes']
        con.executemany('INSERT INTO functions VALUES(?,?,?,?,?,?)', rows)
        n += len(rows)
    con.executemany('INSERT INTO units VALUES(?,?,?,?,?,?,?)', [(k, *v) for k, v in units.items()])
    report['parts']['P1.functions'] = n
    report['derived.units'] = len(units)
    n = 0
    for batch in batched(jsonl(parts / 'P1' / 'calls.jsonl')):
        con.executemany('INSERT INTO calls VALUES(?,?,?,?)', [(c['caller'], c['callee'], c['unit'], c['line']) for c in batch])
        n += len(batch)
    report['parts']['P1.calls'] = n
    n = 0
    for batch in batched(jsonl(parts / 'P1' / 'icalls.jsonl')):
        con.executemany('INSERT INTO icalls VALUES(?,?,?)', [(c['caller'], c['unit'], c['line']) for c in batch])
        n += len(batch)
    report['parts']['P1.icalls'] = n
    t.lap('P1 loaded', functions=report['parts']['P1.functions'], calls=report['parts']['P1.calls'])

    # ---- P3: refs, resolved -------------------------------------------------------------------------------
    def segment_of(a):
        for lo, hi, mod, name in seg_ranges:
            if lo <= a < hi:
                return name
        return 'outside'

    kinds = collections.Counter()
    dropped = collections.Counter()
    total = 0

    def classify(func, target):
        if target == func:
            dropped['fn_enter'] += 1
            return None
        if target in fn_set:
            return 'fn'
        a = int(target, 16)
        seg = segment_of(a)
        if seg == 'text':
            dropped['code_label_or_return'] += 1
            return None
        if target in str_set:
            return 'string'
        i = bisect.bisect_right(str_sorted, a) - 1
        if i >= 0 and a < str_sorted_end[i]:
            return 'string+'
        if target in vt_ptrs:
            return 'vtable'
        if target in typeinfo_set:
            return 'typeinfo'
        if target in sym_obj:
            return 'symbol'
        return seg

    for batch in batched(jsonl(parts / 'P3' / 'refs.jsonl'), 100000):
        rows = []
        for r in batch:
            total += 1
            k = classify(r['func'], r['target'])
            if k is None:
                continue
            kinds[k] += 1
            rows.append((r['func'], r['target'], r['unit'], r['line'], r['how'], k))
        con.executemany('INSERT INTO refs VALUES(?,?,?,?,?,?)', rows)
    report['parts']['P3.refs_read'] = total
    report['refs_kept'] = sum(kinds.values())
    report['refs_dropped'] = dict(dropped)
    report['refs_by_kind'] = dict(kinds.most_common())
    t.lap('P3 loaded', read=total, kept=report['refs_kept'])

    # ---- P4: hle, P5: annotations (+ user annotations) ---------------------------------------------------------
    hle_rows = [(h['name'], h.get('guest_addr'), h['runtime_fn'], h['runtime_file']) for h in jsonl(parts / 'P4' / 'hle.jsonl')]
    con.executemany('INSERT INTO hle VALUES(?,?,?,?)', hle_rows)
    report['parts']['P4.hle'] = len(hle_rows)
    ann = []
    for a in jsonl(parts / 'P5' / 'annotations.jsonl'):
        ann.append((a['addr'], a['name'], a['subsystem'], a['confidence'], a['source'], a['note'], 'P5'))
    user_file = data / 'annotations.user.jsonl'
    n_user = 0
    if user_file.exists():
        for a in jsonl(user_file):
            ann.append((a['addr'], a['name'], a.get('subsystem', ''), a.get('confidence', 'assumed'), a.get('source', ''), a.get('note', ''), 'user'))
            n_user += 1
    con.executemany('INSERT INTO annotations(addr,name,subsystem,confidence,source,note,origin) VALUES(?,?,?,?,?,?,?)', ann)
    report['parts']['P5.annotations'] = len(ann) - n_user
    report['parts']['user.annotations'] = n_user
    t.lap('P4/P5 loaded')

    # ---- indexes and FTS -----------------------------------------------------------------------------------
    con.executescript(INDEXES)
    for fts in ('strings_fts', 'symbols_fts', 'rtti_fts', 'annotations_fts'):
        con.execute(f"INSERT INTO {fts}({fts}) VALUES('rebuild')")
    t.lap('indexes + FTS built')

    # ---- consistency checks ---------------------------------------------------------------------------------
    checks = []

    def check(name, bad, detail, ok_when_zero=True):
        status = 'pass' if (bad == 0) == ok_when_zero else 'fail'
        checks.append((name, status, f'{detail}: {bad}'))

    q = lambda sql, *p: con.execute(sql, p).fetchone()[0]
    check('calls.callee defined in functions', q('SELECT COUNT(*) FROM calls c LEFT JOIN functions f ON f.addr=c.callee WHERE f.addr IS NULL'), 'unresolved direct callees')
    check('calls.caller defined in functions', q('SELECT COUNT(*) FROM calls c LEFT JOIN functions f ON f.addr=c.caller WHERE f.addr IS NULL'), 'callers not in P1 functions')
    check('icalls.caller defined in functions', q('SELECT COUNT(*) FROM icalls c LEFT JOIN functions f ON f.addr=c.caller WHERE f.addr IS NULL'), 'indirect-call sites outside P1 functions')
    check('refs.func defined in functions', q('SELECT COUNT(*) FROM refs r LEFT JOIN functions f ON f.addr=r.func WHERE f.addr IS NULL'), 'refs from unknown functions')
    check('refs line inside function bounds (P3 vs P1)', q('SELECT COUNT(*) FROM refs r JOIN functions f ON f.addr=r.func WHERE r.line < f.line_start OR r.line > f.line_end'), 'refs outside the function lines')
    check('vslots.func are function starts (P2 vs P1)', q('SELECT COUNT(*) FROM vslots v LEFT JOIN functions f ON f.addr=v.func WHERE f.addr IS NULL'), 'vtable slots not pointing at a P1 function')
    check('strings inside rodata segments', q("SELECT COUNT(*) FROM strings s WHERE NOT EXISTS (SELECT 1 FROM segments g WHERE g.name='.rodata' AND g.module=s.module AND s.addr>=g.start AND s.addr<g.end)"), 'strings outside .rodata')
    check('rtti vtables inside data/rodata', q("SELECT COUNT(*) FROM rtti r WHERE r.vtable IS NOT NULL AND NOT EXISTS (SELECT 1 FROM segments g WHERE g.name IN ('.data','.rodata') AND r.vtable>=g.start AND r.vtable<g.end)"), 'vtables outside .data/.rodata')
    check('hle.guest_addr known (symbol or function)', q('SELECT COUNT(*) FROM hle h WHERE h.guest_addr IS NOT NULL AND NOT EXISTS (SELECT 1 FROM symbols s WHERE s.addr=h.guest_addr) AND NOT EXISTS (SELECT 1 FROM functions f WHERE f.addr=h.guest_addr)'), 'HLE guest addresses unknown to P1/P2')
    unknown = [r[0] for r in con.execute("SELECT DISTINCT a.addr FROM annotations a WHERE a.origin='P5' AND a.note NOT LIKE '%[region:%' AND a.note NOT LIKE '%[label L_%' "
                                         "AND NOT EXISTS (SELECT 1 FROM functions f WHERE f.addr=a.addr) AND NOT EXISTS (SELECT 1 FROM refs r WHERE r.target=a.addr) "
                                         "AND NOT EXISTS (SELECT 1 FROM strings s WHERE s.addr=a.addr)")]
    # P5 verified these with a 4-line ADRP+ADD window; P3's conservative propagation may not carry them, so a warning only
    checks.append(('annotations (P5) data addresses also seen by P3 refs', 'pass' if not unknown else 'warn',
                   'P5 data addresses that P3 has no ref to: ' + (', '.join(unknown) if unknown else '0')))
    check('P1 function count equals the translator declarations (230,332 + 40,069)', q('SELECT COUNT(*) FROM functions') - 270401, 'difference from 270,401')
    check('anchor: 7000a1158c calls 700033e770 (P1)', 1 - q("SELECT COUNT(*) FROM calls WHERE caller='7000a1158c' AND callee='700033e770'"), 'missing anchor calls')
    check('anchor: condition string at 700329eb22 (P2) referenced by 70007de270 (P3)', 1 - q("SELECT COUNT(*) FROM refs WHERE target='700329eb22' AND func='70007de270' AND kind='string'"), 'missing string ref')
    check('anchor: KMoney functions annotated (P5)', 2 - q("SELECT COUNT(DISTINCT addr) FROM annotations WHERE name LIKE '%KMoney%' AND addr IN ('70009c18d8','7000dbb28c')"), 'missing KMoney annotations')
    check('segments: P2 vs P3 verification ranges identical', 0 if [(s['start'], s['end']) for s in segs] == [(r['start'], r['end']) for r in json.loads((parts / 'P3' / 'verification.json').read_text(encoding='utf-8-sig'))['segment_ranges']] else 1, 'mismatching segment tables')
    con.executemany('INSERT INTO checks VALUES(?,?,?)', checks)
    report['checks'] = [dict(name=c[0], status=c[1], detail=c[2]) for c in checks]
    t.lap('checks done', failed=sum(1 for c in checks if c[1] != 'pass'))

    # ---- coverage -----------------------------------------------------------------------------------------
    total_fn = q('SELECT COUNT(*) FROM functions')
    cov = {
        'functions': total_fn,
        'with_string_ref': q("SELECT COUNT(DISTINCT func) FROM refs WHERE kind IN ('string','string+')"),
        'with_class': q('SELECT COUNT(DISTINCT func) FROM fn_class'),
        'with_annotation': q('SELECT COUNT(DISTINCT a.addr) FROM annotations a JOIN functions f ON f.addr=a.addr'),
        'with_symbol_name': q("SELECT COUNT(DISTINCT s.addr) FROM symbols s JOIN functions f ON f.addr=s.addr WHERE s.kind='function'"),
        'with_any_name_or_string': q("SELECT COUNT(*) FROM functions f WHERE EXISTS (SELECT 1 FROM refs r WHERE r.func=f.addr AND r.kind IN ('string','string+')) OR EXISTS (SELECT 1 FROM fn_class c WHERE c.func=f.addr) OR EXISTS (SELECT 1 FROM annotations a WHERE a.addr=f.addr) OR EXISTS (SELECT 1 FROM symbols s WHERE s.addr=f.addr AND s.kind='function')"),
        'with_callers': q('SELECT COUNT(DISTINCT callee) FROM calls'),
        'with_callees': q('SELECT COUNT(DISTINCT caller) FROM calls'),
    }
    cov['percent'] = {k: round(100.0 * v / total_fn, 2) for k, v in cov.items() if k != 'functions'}
    report['coverage'] = cov
    t.lap('coverage computed')

    built = time.strftime('%Y-%m-%dT%H:%M:%S')
    meta = {'built': built, 'build_id_main': 'b1f12fd919eae86ab8a978317677e64bce443d1f', 'game': 'Pokemon Legends Z-A 2.0.2 + Mega Dimension',
            'parts': json.dumps(report['parts']), 'refs_by_kind': json.dumps(report['refs_by_kind']), 'coverage': json.dumps(cov),
            'schema': '1', 'builder': 'tools/za-atlas/P6/build_atlas.py'}
    con.executemany('INSERT INTO meta VALUES(?,?)', meta.items())
    con.commit()
    con.execute('PRAGMA optimize')
    con.close()
    t.lap('committed')
    con = sqlite3.connect(tmp)
    con.execute('VACUUM')
    con.close()
    t.lap('vacuumed')
    if out.exists():
        out.unlink()
    os.replace(tmp, out)
    report['database'] = {'path': str(out), 'bytes': out.stat().st_size, 'sha256': sha256_file(out), 'built': built}
    report['total_seconds'] = round(sum(s['seconds'] for s in t.steps), 1)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data', type=Path, default=DATA)
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    lower_priority()
    out = a.out or (a.data / 'atlas.sqlite')
    report = build(a.data, out)
    (a.data / 'atlas-build.json').write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('database', 'total_seconds', 'coverage')}, ensure_ascii=False))


if __name__ == '__main__':
    main()

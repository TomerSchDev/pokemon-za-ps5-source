#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""za-atlas: the code map of Pokemon Legends: Z-A 2.0.2 (translated C), queried from za-atlas-data/atlas.sqlite.

  fn <addr|name>          location, size, callers, callees, strings, class, annotations
  who-calls <addr|name>   direct callers (+ vtable slots and address-taken sites)
  callees <addr|name>     direct callees (+ indirect call sites)
  str <text>              strings matching the text and the functions that use them
  find <word>             annotations, symbols, classes, strings, HLE names and units matching a word
  path <a> <b>            shortest direct-call path from a to b
  unit <file>             summary of one translated unit (main_310 / main_310.c)
  class <name>            RTTI class: typeinfo, vtables, slots -> functions, derived classes
  crash <klog> --elf ELF  decode a console crash log with the matching llvm-pie.elf (P4 decoder)
  annotate <addr> <name>  add a name to the dictionary (annotations.user.jsonl + database)
  stats | systems | build

Short output by default (counts + first rows); --all prints everything; --json for machines. Addresses are guest
addresses as hex (7000a1158c, 0x7000a1158c or f_7000a1158c). Build the database with `build` (P6 build_atlas.py).
"""
import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
from collections import OrderedDict, deque
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = REPO.parent / 'za-atlas-data'
DB = DATA / 'atlas.sqlite'
USER_ANN = DATA / 'annotations.user.jsonl'
CRASH_PY = REPO / 'tools' / 'za-atlas' / 'P4' / 'crash.py'
LIMIT = 15
CHUNK = 500


# ----------------------------------------------------------------------------------------------- helpers
def open_db(path, write=False):
    if not Path(path).is_file():
        sys.exit(f'database not found: {path}\nbuild it first: py -3 -I tools\\za-atlas\\P6\\za_atlas.py build')
    if write:
        return sqlite3.connect(path)
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def norm_addr(token):
    t = token.strip().lower()
    t = re.sub(r'^(0x|f_|l_)', '', t)
    if re.fullmatch(r'[0-9a-f]{6,12}', t):
        return t.rjust(10, '0') if len(t) < 10 else t
    return None


def chunks(seq, n=CHUNK):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def in_clause(values):
    return '(' + ','.join('?' * len(values)) + ')'


def names_for(con, addrs):
    """addr -> ordered list of display names: annotations, symbol, class slot, HLE."""
    out = {a: [] for a in addrs}
    for part in chunks(addrs):
        for a, n in con.execute(f'SELECT addr, name FROM annotations WHERE addr IN {in_clause(part)} ORDER BY id', part):
            if n not in out[a]:
                out[a].append(n)
        for a, d in con.execute(f"SELECT addr, demangled FROM symbols WHERE kind='function' AND addr IN {in_clause(part)}", part):
            if d not in out[a]:
                out[a].append(d)
        for a, c, s in con.execute(f'SELECT func, class, slot FROM fn_class WHERE func IN {in_clause(part)} ORDER BY class, slot', part):
            tag = f'{c} vslot {s}'
            if tag not in out[a]:
                out[a].append(tag)
        for a, n in con.execute(f'SELECT guest_addr, runtime_fn FROM hle WHERE guest_addr IN {in_clause(part)}', part):
            tag = f'HLE {n}'
            if tag not in out[a]:
                out[a].append(tag)
    return out


def label(addr, names, width=1):
    ns = names.get(addr) or []
    return f'f_{addr}' + (f'  {ns[0]}' if ns else '') + (f'  (+{len(ns) - 1} names)' if len(ns) > width else '')


def resolve(con, token, want='function'):
    """A hex address, or a name from annotations / symbols. Prints candidates and exits when ambiguous."""
    a = norm_addr(token)
    if a:
        return a
    rows = OrderedDict()
    for addr, name in con.execute('SELECT addr, name FROM annotations WHERE lower(name)=lower(?)', (token,)):
        rows.setdefault(addr, name)
    for addr, name in con.execute("SELECT addr, demangled FROM symbols WHERE kind='function' AND demangled=?", (token,)):
        rows.setdefault(addr, name)
    if not rows:
        like = f'%{token}%'
        for addr, name in con.execute('SELECT addr, name FROM annotations WHERE name LIKE ? ORDER BY id LIMIT 50', (like,)):
            rows.setdefault(addr, name)
        for addr, name in con.execute("SELECT addr, demangled FROM symbols WHERE kind='function' AND demangled LIKE ? LIMIT 50", (like,)):
            rows.setdefault(addr, name)
    if len(rows) == 1:
        return next(iter(rows))
    if not rows:
        sys.exit(f'no function or name matches "{token}"')
    print(f'"{token}" is ambiguous ({len(rows)} candidates):')
    for addr, name in list(rows.items())[:30]:
        print(f'  {addr}  {name}')
    sys.exit(2)


def trunc(s, n=90):
    s = s.replace('\n', ' ')
    return s if len(s) <= n else s[:n - 3] + '...'


def show(rows, all_rows, fmt, limit=LIMIT):
    for r in (rows if all_rows else rows[:limit]):
        print('   ' + fmt(r))
    if not all_rows and len(rows) > limit:
        print(f'   ... {len(rows) - limit} more (use --all)')


def fn_row(con, addr):
    return con.execute('SELECT addr, module, unit, line_start, line_end, c_bytes FROM functions WHERE addr=?', (addr,)).fetchone()


# ----------------------------------------------------------------------------------------------- commands
def cmd_fn(con, a):
    addr = resolve(con, a.target)
    f = fn_row(con, addr)
    out = {'addr': addr}
    if f:
        print(f'f_{addr}  {f[1]}  {f[2]}:{f[3]}-{f[4]}  ({f[5]:,} bytes of C)')
        out.update(module=f[1], unit=f[2], line_start=f[3], line_end=f[4], c_bytes=f[5])
    else:
        seg = con.execute('SELECT module, name FROM segments WHERE ? >= start AND ? < end', (addr, addr)).fetchone()
        print(f'{addr}  not a function start' + (f'  ({seg[0]} {seg[1]})' if seg else ''))
        s = con.execute('SELECT text, encoding FROM strings WHERE addr=?', (addr,)).fetchone()
        if s:
            print(f'string ({s[1]}): {trunc(s[0])}')
        v = con.execute('SELECT class, vtable, what FROM vtable_ptrs WHERE ptr=?', (addr,)).fetchone()
        if v:
            print(f'vtable of {v[0]} ({v[2]}, header {v[1]})')
    ann = con.execute('SELECT name, subsystem, confidence, source, note, origin FROM annotations WHERE addr=? ORDER BY id', (addr,)).fetchall()
    out['annotations'] = [dict(name=r[0], subsystem=r[1], confidence=r[2], source=r[3], note=r[4], origin=r[5]) for r in ann]
    for r in ann:
        print(f'name: {r[0]}  [{r[1]}, {r[2]}]  <- {r[3]}')
    sym = con.execute('SELECT demangled, kind, module FROM symbols WHERE addr=?', (addr,)).fetchall()
    for r in sym:
        print(f'symbol: {r[0]}  ({r[2]} {r[1]})')
    out['symbols'] = [r[0] for r in sym]
    hle = con.execute('SELECT name, runtime_fn, runtime_file FROM hle WHERE guest_addr=?', (addr,)).fetchall()
    for r in hle:
        print(f'HLE: {r[1]}  in {r[2]}  (import {r[0]})')
    cls = con.execute('SELECT class, vtable, slot FROM fn_class WHERE func=? ORDER BY class, slot', (addr,)).fetchall()
    out['class'] = [dict(name=r[0], vtable=r[1], slot=r[2]) for r in cls]
    print('class: ' + ('; '.join(f'{r[0]} (vtable {r[1]} slot {r[2]})' for r in cls) if cls else '-'))

    callers = con.execute('SELECT caller, COUNT(*) FROM calls WHERE callee=? GROUP BY caller ORDER BY caller', (addr,)).fetchall()
    callees = con.execute('SELECT callee, COUNT(*) FROM calls WHERE caller=? GROUP BY callee ORDER BY MIN(line)', (addr,)).fetchall()
    icalls = con.execute('SELECT COUNT(*) FROM icalls WHERE caller=?', (addr,)).fetchone()[0]
    taken = con.execute("SELECT func, COUNT(*) FROM refs WHERE target=? AND kind='fn' GROUP BY func", (addr,)).fetchall()
    names = names_for(con, [r[0] for r in callers] + [r[0] for r in callees] + [r[0] for r in taken])
    print(f'callers ({len(callers)}):')
    show(callers, a.all, lambda r: label(r[0], names) + (f'  x{r[1]}' if r[1] > 1 else ''))
    print(f'callees ({len(callees)}):')
    show(callees, a.all, lambda r: label(r[0], names) + (f'  x{r[1]}' if r[1] > 1 else ''))
    print(f'indirect call sites: {icalls}')
    if taken:
        print(f'address taken by ({len(taken)}):')
        show(taken, a.all, lambda r: label(r[0], names))
    out['callers'] = [r[0] for r in callers]
    out['callees'] = [r[0] for r in callees]
    out['icalls'] = icalls
    out['address_taken_by'] = [r[0] for r in taken]

    strs = con.execute("SELECT DISTINCT s.addr, s.text, r.kind FROM refs r JOIN strings s ON s.addr=r.target WHERE r.func=? AND r.kind='string' "
                       "UNION SELECT DISTINCT s.addr, s.text, r.kind FROM refs r JOIN strings s ON r.target>=s.addr AND r.target<s.end "
                       "WHERE r.func=? AND r.kind='string+' ORDER BY 1", (addr, addr)).fetchall()
    print(f'strings ({len(strs)}):')
    show(strs, a.all, lambda r: f'{r[0]}  {trunc(r[1])}' + ('  (inside)' if r[2] == 'string+' else ''))
    out['strings'] = [dict(addr=r[0], text=r[1]) for r in strs]

    data = con.execute("SELECT target, kind, COUNT(*) FROM refs WHERE func=? AND kind NOT IN ('string','string+') GROUP BY target, kind ORDER BY kind, target", (addr,)).fetchall()
    kinds = {}
    for r in data:
        kinds[r[1]] = kinds.get(r[1], 0) + 1
    tnames = names_for(con, [r[0] for r in data if r[1] == 'fn'])
    vt = {r[0]: r for r in con.execute(f"SELECT ptr, class, what FROM vtable_ptrs WHERE ptr IN {in_clause([r[0] for r in data])}", [r[0] for r in data])} if data else {}
    ti = {r[0]: r[1] for r in con.execute(f"SELECT typeinfo, class FROM rtti WHERE typeinfo IN {in_clause([r[0] for r in data])}", [r[0] for r in data])} if data else {}
    dann = names_for(con, [r[0] for r in data if r[1] not in ('fn',)])
    sym = {r[0]: r[1] for r in con.execute(f"SELECT addr, demangled FROM symbols WHERE addr IN {in_clause([r[0] for r in data])}", [r[0] for r in data])} if data else {}

    def describe(r):
        t, k = r[0], r[1]
        if k == 'fn':
            return f'{t}  fn-pointer  {label(t, tnames)}'
        if k == 'vtable' and t in vt:
            return f'{t}  vtable  {vt[t][1]} ({vt[t][2]})'
        if k == 'typeinfo' and t in ti:
            return f'{t}  typeinfo  {ti[t]}'
        extra = (dann.get(t) or [sym.get(t, '')])[0] if (dann.get(t) or sym.get(t)) else ''
        return f'{t}  {k}  {extra}'.rstrip()

    named = [r for r in data if r[1] in ('fn', 'vtable', 'typeinfo', 'symbol') or dann.get(r[0])]
    print(f'data refs ({len(data)}): ' + ', '.join(f'{k} {v}' for k, v in sorted(kinds.items())))
    show(named, a.all, describe)
    if a.all:
        rest = [r for r in data if r not in named]
        show(rest, True, describe)
    out['data_refs'] = [dict(target=r[0], kind=r[1], count=r[2]) for r in data]
    for r in ann:
        print(f'note ({r[0]}): ' + (r[4] if a.all else trunc(r[4], 400)))
    return out


def cmd_who_calls(con, a):
    addr = resolve(con, a.target)
    callers = con.execute('SELECT caller, COUNT(*), MIN(unit), MIN(line) FROM calls WHERE callee=? GROUP BY caller ORDER BY caller', (addr,)).fetchall()
    slots = con.execute('SELECT c.class, c.vtable, c.slot FROM fn_class c WHERE c.func=? ORDER BY class, slot', (addr,)).fetchall()
    taken = con.execute("SELECT func, unit, MIN(line) FROM refs WHERE target=? AND kind='fn' GROUP BY func ORDER BY func", (addr,)).fetchall()
    names = names_for(con, [addr] + [r[0] for r in callers] + [r[0] for r in taken])
    print(f'{label(addr, names)}')
    print(f'direct callers ({len(callers)}):')
    show(callers, a.all, lambda r: label(r[0], names) + f'  ({r[2]}:{r[3]}' + (f', x{r[1]})' if r[1] > 1 else ')'))
    if slots:
        print(f'virtual slots ({len(slots)}): ' + '; '.join(f'{r[0]} slot {r[2]} (vtable {r[1]})' for r in slots))
    if taken:
        print(f'address taken by ({len(taken)}):')
        show(taken, a.all, lambda r: label(r[0], names) + f'  ({r[1]}:{r[2]})')
    return {'addr': addr, 'callers': [dict(addr=r[0], sites=r[1], unit=r[2], line=r[3], names=names.get(r[0], [])) for r in callers],
            'vslots': [dict(cls=r[0], vtable=r[1], slot=r[2]) for r in slots], 'address_taken_by': [r[0] for r in taken]}


def cmd_callees(con, a):
    addr = resolve(con, a.target)
    callees = con.execute('SELECT callee, COUNT(*), MIN(line) FROM calls WHERE caller=? GROUP BY callee ORDER BY MIN(line)', (addr,)).fetchall()
    icalls = con.execute('SELECT line FROM icalls WHERE caller=? ORDER BY line', (addr,)).fetchall()
    names = names_for(con, [addr] + [r[0] for r in callees])
    print(f'{label(addr, names)}')
    print(f'direct callees ({len(callees)}):')
    show(callees, a.all, lambda r: label(r[0], names) + f'  (line {r[2]}' + (f', x{r[1]})' if r[1] > 1 else ')'))
    print(f'indirect call sites ({len(icalls)})' + (': lines ' + ', '.join(str(r[0]) for r in icalls[:LIMIT]) if icalls else ''))
    return {'addr': addr, 'callees': [dict(addr=r[0], sites=r[1], line=r[2], names=names.get(r[0], [])) for r in callees], 'icall_lines': [r[0] for r in icalls]}


def string_users(con, saddr, send):
    return con.execute("SELECT func, COUNT(*) FROM refs WHERE kind IN ('string','string+') AND target>=? AND target<? GROUP BY func ORDER BY func", (saddr, send)).fetchall()


def cmd_str(con, a):
    text = a.text
    rows = con.execute('SELECT addr, module, text, encoding, end FROM strings WHERE text=? ORDER BY addr', (text,)).fetchall()
    exact = bool(rows)
    if not rows:
        rows = con.execute('SELECT addr, module, text, encoding, end FROM strings WHERE text LIKE ? ORDER BY length(text), addr LIMIT 500', (f'%{text}%',)).fetchall()
    print(f'strings matching "{text}": {len(rows)}' + ('' if exact else ' (substring)'))
    result = []
    for r in (rows if a.all else rows[:LIMIT]):
        users = string_users(con, r[0], r[4])
        names = names_for(con, [u[0] for u in users])
        print(f'{r[0]}  {r[1]} {r[3]}  {trunc(r[2])}')
        print(f'   used by ({len(users)}):')
        for u in (users if a.all else users[:LIMIT]):
            f = fn_row(con, u[0])
            print(f'      {label(u[0], names)}  ({f[2]}:{f[3]})' if f else f'      {label(u[0], names)}')
        if not a.all and len(users) > LIMIT:
            print(f'      ... {len(users) - LIMIT} more (use --all)')
        result.append(dict(addr=r[0], text=r[2], users=[u[0] for u in users]))
    if not a.all and len(rows) > LIMIT:
        print(f'... {len(rows) - LIMIT} more strings (use --all)')
    ann = con.execute('SELECT addr, name, subsystem FROM annotations WHERE name LIKE ? OR note LIKE ? ORDER BY id', (f'%{text}%', f'%{text}%')).fetchall()
    if ann:
        print(f'annotations mentioning it ({len(ann)}):')
        show(ann, a.all, lambda r: f'f_{r[0]}  {r[1]}  [{r[2]}]')
    return {'text': text, 'exact': exact, 'strings': result, 'annotations': [dict(addr=r[0], name=r[1]) for r in ann]}


def cmd_find(con, a):
    word = a.word
    like = f'%{word}%'
    out = {}
    ann = con.execute('SELECT addr, name, subsystem, confidence FROM annotations WHERE name LIKE ? OR note LIKE ? OR subsystem LIKE ? ORDER BY (name LIKE ?) DESC, id',
                      (like, like, like, like)).fetchall()
    print(f'annotations ({len(ann)}):')
    show(ann, a.all, lambda r: f'f_{r[0]}  {r[1]}  [{r[2]}, {r[3]}]')
    out['annotations'] = [dict(addr=r[0], name=r[1], subsystem=r[2]) for r in ann]
    sym = con.execute("SELECT addr, demangled, kind, module FROM symbols WHERE demangled LIKE ? ORDER BY kind='function' DESC, addr LIMIT 2000", (like,)).fetchall()
    print(f'symbols ({len(sym)}):')
    show(sym, a.all, lambda r: f'{r[0]}  {trunc(r[1], 110)}  ({r[3]} {r[2]})')
    out['symbols'] = [dict(addr=r[0], name=r[1]) for r in sym[:LIMIT if not a.all else None]]
    cls = con.execute('SELECT class, typeinfo, vtable FROM rtti WHERE class LIKE ? ORDER BY class', (like,)).fetchall()
    print(f'classes ({len(cls)}):')
    show(cls, a.all, lambda r: f'{r[0]}  (typeinfo {r[1]}' + (f', vtable {r[2]})' if r[2] else ')'))
    out['classes'] = [r[0] for r in cls]
    strs = con.execute('SELECT addr, text, end FROM strings WHERE text LIKE ? ORDER BY length(text), addr LIMIT 2000', (like,)).fetchall()
    print(f'strings ({len(strs)}):')

    def strfmt(r):
        n = con.execute("SELECT COUNT(DISTINCT func) FROM refs WHERE kind IN ('string','string+') AND target>=? AND target<?", (r[0], r[2])).fetchone()[0]
        return f'{r[0]}  {trunc(r[1], 100)}  (used by {n})'
    show(strs, a.all, strfmt)
    out['strings'] = [dict(addr=r[0], text=r[1]) for r in strs[:LIMIT if not a.all else None]]
    hle = con.execute('SELECT name, guest_addr, runtime_fn, runtime_file FROM hle WHERE name LIKE ? OR runtime_fn LIKE ? ORDER BY runtime_fn', (like, like)).fetchall()
    if hle:
        print(f'HLE ({len(hle)}):')
        show(hle, a.all, lambda r: f'{r[2]}  {r[3]}  ' + (f'guest {r[1]}  ' if r[1] else '') + trunc(r[0], 80))
    out['hle'] = [dict(runtime_fn=r[2], guest_addr=r[1]) for r in hle]
    units = con.execute('SELECT unit, module, functions FROM units WHERE unit LIKE ? ORDER BY unit', (like,)).fetchall()
    if units:
        print(f'units ({len(units)}):')
        show(units, a.all, lambda r: f'{r[0]}  {r[1]}  {r[2]} functions')
    out['units'] = [r[0] for r in units]
    return out


def cmd_path(con, a):
    src, dst = resolve(con, a.src), resolve(con, a.dst)
    if src == dst:
        print(f'f_{src}')
        return {'path': [src]}
    max_depth = a.depth
    fwd, bwd = {src: None}, {dst: None}
    ffront, bfront = [src], [dst]
    meet = None
    for depth in range(max_depth):
        if len(ffront) <= len(bfront):
            nxt = []
            for part in chunks(ffront):
                for caller, callee in con.execute(f'SELECT DISTINCT caller, callee FROM calls WHERE caller IN {in_clause(part)}', part):
                    if callee not in fwd:
                        fwd[callee] = caller
                        nxt.append(callee)
                        if callee in bwd:
                            meet = callee
                            break
                if meet:
                    break
            ffront = nxt
        else:
            nxt = []
            for part in chunks(bfront):
                for caller, callee in con.execute(f'SELECT DISTINCT caller, callee FROM calls WHERE callee IN {in_clause(part)}', part):
                    if caller not in bwd:
                        bwd[caller] = callee
                        nxt.append(caller)
                        if caller in fwd:
                            meet = caller
                            break
                if meet:
                    break
            bfront = nxt
        if meet or not ffront or not bfront or len(fwd) + len(bwd) > a.max_nodes:
            break
    if not meet:
        print(f'no direct-call path from f_{src} to f_{dst} within depth {max_depth} ({len(fwd) + len(bwd):,} nodes explored); '
              'indirect calls (dispatch) are not followed')
        return {'path': None}
    chain = []
    n = meet
    while n is not None:
        chain.append(n)
        n = fwd[n]
    chain.reverse()
    n = bwd[meet]
    while n is not None:
        chain.append(n)
        n = bwd[n]
    names = names_for(con, chain)
    print(f'path ({len(chain) - 1} calls):')
    for i, n in enumerate(chain):
        f = fn_row(con, n)
        print(('   ' if i == 0 else '   -> ') + label(n, names) + (f'  ({f[2]})' if f else ''))
    return {'path': chain}


def cmd_unit(con, a):
    unit = a.unit if a.unit.endswith('.c') else a.unit + '.c'
    u = con.execute('SELECT unit, module, functions, first_addr, last_addr, lines, c_bytes FROM units WHERE unit=?', (unit,)).fetchone()
    if not u:
        sys.exit(f'unknown unit {unit}')
    print(f'{u[0]}  {u[1]}  {u[2]:,} functions  f_{u[3]}..f_{u[4]}  {u[5]:,} lines  {u[6]:,} bytes of C')
    ann = con.execute('SELECT a.addr, a.name, a.subsystem, f.line_start FROM annotations a JOIN functions f ON f.addr=a.addr WHERE f.unit=? ORDER BY f.line_start, a.id', (unit,)).fetchall()
    print(f'annotated functions ({len(ann)}):')
    show(ann, a.all, lambda r: f'f_{r[0]}  {r[1]}  [{r[2]}]  (line {r[3]})')
    cls = con.execute('SELECT DISTINCT c.class FROM fn_class c JOIN functions f ON f.addr=c.func WHERE f.unit=? ORDER BY c.class', (unit,)).fetchall()
    print(f'classes with virtual functions here ({len(cls)}):')
    show(cls, a.all, lambda r: r[0])
    rows = con.execute('SELECT addr, line_start, line_end, c_bytes FROM functions WHERE unit=? ORDER BY line_start', (unit,)).fetchall()
    funcs = [r[0] for r in rows]
    strs, ncalls_out, ncalls_in = set(), 0, 0
    for part in chunks(funcs):  # indexed lookups per function instead of scanning the whole refs/calls tables
        strs.update(r[0] for r in con.execute(f"SELECT DISTINCT target FROM refs WHERE kind IN ('string','string+') AND func IN {in_clause(part)}", part))
        ncalls_out += con.execute(f'SELECT COUNT(*) FROM calls WHERE caller IN {in_clause(part)}', part).fetchone()[0]
        ncalls_in += con.execute(f'SELECT COUNT(*) FROM calls WHERE callee IN {in_clause(part)} AND unit<>?', part + [unit]).fetchone()[0]
    print(f'strings used: {len(strs):,}   calls out of its functions: {ncalls_out:,}   calls into it from other units: {ncalls_in:,}')
    if a.all:
        names = names_for(con, funcs)
        print(f'functions ({len(rows)}):')
        for r in rows:
            print(f'   {label(r[0], names)}  lines {r[1]}-{r[2]}  {r[3]:,} B')
    return {'unit': u[0], 'module': u[1], 'functions': u[2], 'annotated': [dict(addr=r[0], name=r[1]) for r in ann]}


def cmd_class(con, a):
    rows = con.execute('SELECT id, class, typeinfo, vtable, bases FROM rtti WHERE class=? ORDER BY id', (a.name,)).fetchall()
    if not rows:
        rows = con.execute('SELECT id, class, typeinfo, vtable, bases FROM rtti WHERE class LIKE ? ORDER BY class, id', (f'%{a.name}%',)).fetchall()
        classes = sorted({r[1] for r in rows})
        if len(classes) != 1:
            print(f'classes matching "{a.name}": {len(classes)}')
            show(classes, a.all, lambda c: c, limit=40)
            return {'classes': classes}
    cls = rows[0][1]
    bases = json.loads(rows[0][4])
    print(f'class {cls}  typeinfo {rows[0][2]}' + (f'  bases: {", ".join(bases)}' if bases else ''))
    out = {'class': cls, 'typeinfo': rows[0][2], 'bases': bases, 'vtables': []}
    for r in rows:
        if not r[3]:
            print('   (no proven vtable group)')
            continue
        slots = con.execute('SELECT slot, func FROM vslots WHERE vtable=? ORDER BY slot', (r[3],)).fetchall()
        names = names_for(con, [s[1] for s in slots])
        print(f'vtable {r[3]} ({len(slots)} slots):')
        show(slots, a.all, lambda s: f'slot {s[0]:>3}  {label(s[1], names)}')
        out['vtables'].append(dict(vtable=r[3], slots=[dict(slot=s[0], func=s[1]) for s in slots]))
    derived = con.execute('SELECT DISTINCT class FROM rtti WHERE bases LIKE ? ORDER BY class', (f'%{json.dumps(cls)}%',)).fetchall()
    print(f'derived classes ({len(derived)}):')
    show(derived, a.all, lambda r: r[0])
    out['derived'] = [r[0] for r in derived]
    return out


def cmd_crash(con, a):
    spec = importlib.util.spec_from_file_location('atlas_crash', CRASH_PY)
    crash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(crash)
    work = DATA / 'crash-cache'
    work.mkdir(parents=True, exist_ok=True)
    report = crash.analyze(a.log, a.elf, base=a.base, db=a.db, distro=a.wsl_distro, work_dir=work, refresh=a.refresh)
    if not a.json:
        print(crash.format_report(report, a.all))
    return report


def cmd_annotate(con, a):
    addr = norm_addr(a.addr)
    if not addr:
        sys.exit('annotate needs a guest address (hex)')
    known = fn_row(con, addr) or con.execute('SELECT 1 FROM refs WHERE target=? LIMIT 1', (addr,)).fetchone() \
        or con.execute('SELECT 1 FROM strings WHERE addr=? LIMIT 1', (addr,)).fetchone() or con.execute('SELECT 1 FROM vtable_ptrs WHERE ptr=? LIMIT 1', (addr,)).fetchone()
    if not known and not a.force:
        sys.exit(f'{addr} is not a known function, reference target, string or vtable in the atlas; use --force to add it anyway')
    rec = dict(addr=addr, name=a.name, subsystem=a.subsystem, confidence=a.confidence, source=a.source, note=a.note)
    con.close()
    with open(USER_ANN, 'a', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    w = open_db(a.db, write=True)
    cur = w.execute('INSERT INTO annotations(addr,name,subsystem,confidence,source,note,origin) VALUES(?,?,?,?,?,?,?)',
                    (addr, a.name, a.subsystem, a.confidence, a.source, a.note, 'user'))
    w.execute('INSERT INTO annotations_fts(rowid, name, subsystem, note) VALUES(?,?,?,?)', (cur.lastrowid, a.name, a.subsystem, a.note))
    w.commit()
    w.close()
    print(f'annotated f_{addr}: {a.name}  [{a.subsystem}, {a.confidence}]  -> {USER_ANN.name} + database')
    return rec


def cmd_stats(con, a):
    meta = dict(con.execute('SELECT key, value FROM meta').fetchall())
    counts = {t: con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in
              ('functions', 'calls', 'icalls', 'refs', 'strings', 'symbols', 'rtti', 'vslots', 'hle', 'annotations', 'fn_class', 'units')}
    cov = json.loads(meta.get('coverage', '{}'))
    checks = con.execute('SELECT name, status, detail FROM checks').fetchall()
    size = Path(a.db).stat().st_size
    print(f"atlas.sqlite  {size / 1e6:,.1f} MB  built {meta.get('built')}  game {meta.get('game')}  main build {meta.get('build_id_main')}")
    print('rows: ' + ', '.join(f'{k} {v:,}' for k, v in counts.items()))
    print('refs by kind: ' + ', '.join(f'{k} {v:,}' for k, v in json.loads(meta.get('refs_by_kind', '{}')).items()))
    if cov:
        p = cov['percent']
        print(f"functions {cov['functions']:,}: with a string {p['with_string_ref']}%, with a class {p['with_class']}%, "
              f"with an annotation {p['with_annotation']}%, with an SDK symbol name {p['with_symbol_name']}%, any of these {p['with_any_name_or_string']}%")
    print(f"checks: {sum(1 for c in checks if c[1] == 'pass')}/{len(checks)} pass")
    for c in checks:
        if c[1] != 'pass' or a.all:
            print(f'   {c[1]:4}  {c[0]}  ({c[2]})')
    return {'size_bytes': size, 'meta': meta, 'counts': counts, 'coverage': cov, 'checks': [dict(name=c[0], status=c[1], detail=c[2]) for c in checks]}


def cmd_systems(con, a):
    subs = con.execute("SELECT subsystem, COUNT(*), COUNT(DISTINCT addr) FROM annotations GROUP BY subsystem ORDER BY subsystem").fetchall()
    out = {}
    if a.md:
        print('| מערכת | רשומות | נקודות כניסה עיקריות (כתובת — שם) |')
        print('|---|---|---|')
    for s, n, d in subs:
        rows = con.execute("SELECT addr, name, confidence FROM annotations WHERE subsystem=? ORDER BY CASE confidence WHEN 'proven' THEN 0 WHEN 'derived' THEN 1 ELSE 2 END, "
                           "CASE WHEN name LIKE 'site:%' OR name LIKE 'data:%' OR name LIKE 'global:%' OR name LIKE 'got:%' OR name LIKE 'vtable:%' OR name LIKE 'region:%' "
                           "OR name LIKE 'typeinfo:%' OR name LIKE 'string:%' OR name LIKE 'SaveBlock::K%' THEN 1 ELSE 0 END, id", (s,)).fetchall()
        out[s] = [dict(addr=r[0], name=r[1], confidence=r[2]) for r in rows]
        top = rows if a.all else rows[:a.top]
        if a.md:
            print(f'| `{s}` | {n} | ' + '; '.join(f'`{r[0]}` {r[1]}' for r in top) + (f'; ... (+{len(rows) - len(top)})' if len(rows) > len(top) else '') + ' |')
        else:
            print(f'{s}  ({n} records, {d} addresses)')
            for r in top:
                print(f'   f_{r[0]}  {r[1]}  [{r[2]}]')
    return out


def cmd_build(con, a):
    spec = importlib.util.spec_from_file_location('atlas_build', Path(__file__).with_name('build_atlas.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.lower_priority()
    report = mod.build(DATA, Path(a.db))
    (DATA / 'atlas-build.json').write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('database', 'total_seconds', 'coverage')}, ensure_ascii=False))
    return report


# ----------------------------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(prog='za-atlas', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', default=str(DB))
    ap.add_argument('--all', action='store_true', help='print every row, not only the first ones')
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('fn'); p.add_argument('target')
    p = sub.add_parser('who-calls'); p.add_argument('target')
    p = sub.add_parser('callees'); p.add_argument('target')
    p = sub.add_parser('str'); p.add_argument('text')
    p = sub.add_parser('find'); p.add_argument('word')
    p = sub.add_parser('path'); p.add_argument('src'); p.add_argument('dst'); p.add_argument('--depth', type=int, default=12); p.add_argument('--max-nodes', type=int, default=400000)
    p = sub.add_parser('unit'); p.add_argument('unit')
    p = sub.add_parser('class'); p.add_argument('name')
    p = sub.add_parser('crash'); p.add_argument('log', type=Path); p.add_argument('--elf', required=True)
    p.add_argument('--base', type=lambda v: int(v, 0), default=0x400000); p.add_argument('--wsl-distro', default='Ubuntu'); p.add_argument('--refresh', action='store_true')
    p = sub.add_parser('annotate'); p.add_argument('addr'); p.add_argument('name'); p.add_argument('--subsystem', default='misc')
    p.add_argument('--confidence', choices=('proven', 'derived', 'assumed'), default='assumed'); p.add_argument('--source', default=''); p.add_argument('--note', default='')
    p.add_argument('--force', action='store_true')
    sub.add_parser('stats')
    p = sub.add_parser('systems'); p.add_argument('--md', action='store_true'); p.add_argument('--top', type=int, default=6)
    sub.add_parser('build')
    a = ap.parse_args(argv)
    try:  # Hebrew notes and symbol names: always emit UTF-8, whatever the console code page is
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass
    t0 = time.perf_counter()
    if a.cmd == 'build':
        return cmd_build(None, a)
    con = open_db(a.db)
    con.row_factory = None
    handler = {'fn': cmd_fn, 'who-calls': cmd_who_calls, 'callees': cmd_callees, 'str': cmd_str, 'find': cmd_find, 'path': cmd_path,
               'unit': cmd_unit, 'class': cmd_class, 'crash': cmd_crash, 'annotate': cmd_annotate, 'stats': cmd_stats, 'systems': cmd_systems}[a.cmd]
    if a.json:
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = handler(con, a)
        result = result if isinstance(result, dict) else {'result': result}
        result['seconds'] = round(time.perf_counter() - t0, 3)
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        handler(con, a)
        print(f'({time.perf_counter() - t0:.3f}s)')


if __name__ == '__main__':
    main()

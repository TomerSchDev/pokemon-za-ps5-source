#!/usr/bin/env python3
"""Symbolize r24-prof sample files (za_prof.c / za_prof_core.h layout) against the EXACT PIE of the build.

  python3 symbolize_samples.py --pie artifacts/randomizer-r24-prof/llvm-pie-r24prof.elf samples-b*.bin
        [--from-ns N --to-ns N] [--top 25] [--pairs 15] [--json out.json]
        [--nm /usr/lib/llvm-21/bin/llvm-nm] [--symbolizer /usr/lib/llvm-21/bin/llvm-symbolizer]

Image base = runtime address of za_prof_anchor (file header) - its address in the PIE; a sample's PIE address =
RIP - base. RIPs outside the PIE's executable LOAD range are system modules (libkernel waits and syscalls, libc).
Function names come from the PIE's symbol table (nearest preceding function symbol within its size); source files
from llvm-symbolizer, one query per function. Groups: game (translated f_<addr>), runtime/<file>, radv, port/<file>,
c++/builtins, ext (outside the image), other. --from-ns/--to-ns keep only files whose window overlaps that
CLOCK_MONOTONIC range (the observer's measurement CSV uses the same clock). Never touches the console.
"""
import argparse
import bisect
import collections
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

HEADER = 128
THREAD = 96
RECORD = 24
KINDS = {0: 'guest', 1: 'render', 2: 'radv-kick', 3: 'other'}
F_IN_TEXT, F_CALLER, F_TEXT_KNOWN = 1, 2, 4


def parse_file(path):
    data = Path(path).read_bytes()
    if len(data) < HEADER or data[:8] != b'ZAPROF1\0':
        raise ValueError(f'{path}: not an r24-prof sample file')
    version, header_bytes = struct.unpack_from('<II', data, 8)
    if version != 1:
        raise ValueError(f'{path}: unsupported version {version}')
    (boot, window, t0, t1, anchor, text_lo, text_hi) = struct.unpack_from('<7Q', data, 16)
    (period_us, nthreads, nrecords, dropped, skipped, kill_errors, flags, sent, render_slot) = struct.unpack_from('<9I', data, 72)
    if header_bytes != HEADER + nthreads * THREAD or len(data) != header_bytes + nrecords * RECORD:
        raise ValueError(f'{path}: sizes do not match the header ({len(data)} bytes)')
    threads = {}
    for i in range(nthreads):
        o = HEADER + i * THREAD
        index, kind, gid, entry, lo, hi, prio, samples, ext, nofp = struct.unpack_from('<IIQQQQiIII', data, o)
        name = data[o + 56:o + 88].split(b'\0', 1)[0].decode('utf-8', 'replace')
        threads[index] = dict(index=index, kind=KINDS.get(kind, str(kind)), gid=gid, entry=entry, stack=(lo, hi),
                              prio=prio, samples=samples, ext=ext, nofp=nofp, name=name)
    records = []
    o = header_bytes
    for _ in range(nrecords):
        thread, rflags, _zero, rip, caller = struct.unpack_from('<HHIQQ', data, o)
        records.append((thread, rflags, rip, caller))
        o += RECORD
    return dict(path=str(path), boot=boot, window=window, t0=t0, t1=t1, anchor=anchor, text=(text_lo, text_hi),
                period_us=period_us, flags=flags, sent=sent, dropped=dropped, skipped=skipped, kill_errors=kill_errors,
                render_slot=None if render_slot == 0xffffffff else render_slot, threads=threads, records=records)


def elf_exec_ranges(pie):
    """[(vaddr, vaddr+memsz)] of the executable PT_LOAD segments (ELF64 little endian)."""
    with open(pie, 'rb') as f:
        ident = f.read(64)
        if ident[:4] != b'\x7fELF' or ident[4] != 2 or ident[5] != 1:
            raise ValueError(f'{pie}: not an ELF64 LE file')
        phoff, = struct.unpack_from('<Q', ident, 32)
        phentsize, phnum = struct.unpack_from('<HH', ident, 54)
        f.seek(phoff)
        table = f.read(phentsize * phnum)
    ranges = []
    for i in range(phnum):
        p_type, p_flags, _off, vaddr, _paddr, _filesz, memsz, _align = struct.unpack_from('<IIQQQQQQ', table, i * phentsize)
        if p_type == 1 and p_flags & 1:
            ranges.append((vaddr, vaddr + memsz))
    return ranges


def read_symbols(nm, pie):
    out = subprocess.run([nm, '--defined-only', '--numeric-sort', '--print-size', pie], check=True,
                         capture_output=True, text=True).stdout
    starts, entries, anchor = [], [], None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4:
            addr, size, kind, name = parts
        elif len(parts) == 3:
            addr, kind, name = parts
            size = '0'
        else:
            continue
        if name == 'za_prof_anchor':
            anchor = int(addr, 16)
        if kind not in 'tTwW':
            continue
        starts.append(int(addr, 16))
        entries.append((int(addr, 16), int(size, 16), name))
    return starts, entries, anchor


class Symbols:
    def __init__(self, pie, nm, symbolizer):
        self.pie, self.symbolizer = pie, symbolizer
        self.starts, self.entries, self.anchor = read_symbols(nm, pie)
        self.ranges = elf_exec_ranges(pie)
        self.files = {}

    def in_image(self, vaddr):
        return any(lo <= vaddr < hi for lo, hi in self.ranges)

    def function(self, vaddr):
        i = bisect.bisect_right(self.starts, vaddr) - 1
        if i < 0:
            return None
        start, size, name = self.entries[i]
        if size and vaddr >= start + size:
            return None
        return start, name

    def resolve_files(self, starts):
        todo = sorted(s for s in starts if s not in self.files)
        if not todo:
            return
        try:
            proc = subprocess.run([self.symbolizer, '--obj=' + self.pie, '--output-style=JSON', '--functions=linkage',
                                   '--inlining=false'], input=''.join(f'0x{a:x}\n' for a in todo),
                                  capture_output=True, text=True, check=True)
            lines = [l for l in proc.stdout.splitlines() if l.strip()]
            for addr, line in zip(todo, lines):
                sym = (json.loads(line).get('Symbol') or [{}])[0]
                self.files[addr] = sym.get('FileName') or ''
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f'warning: llvm-symbolizer failed ({e}); grouping by name only', file=sys.stderr)
            for addr in todo:
                self.files.setdefault(addr, '')


def group_of(name, path, in_image):
    if not in_image:
        return 'ext (system modules: libkernel waits/syscalls, libc)'
    if name and re.fullmatch(r'f_[0-9a-f]+', name):
        return 'game (translated code)'
    p = path.replace('\\', '/')
    m = re.search(r'/source/runtime/(.+)$', p) or re.search(r'/runtime/(.+)$', p)
    if m and 'PS5_Mesa' not in p:
        return 'runtime/' + m.group(1)
    if 'PS5_Mesa' in p or '/mesa/' in p or '/radv' in p or (name or '').startswith(('radv_', 'vk_', 'ac_', 'aco')):
        return 'radv'
    m = re.search(r'/port/(.+)$', p)
    if m:
        return 'port/' + m.group(1)
    if 'libcxx' in p or 'compiler-rt' in p or (name or '').startswith(('_ZNSt', '_ZSt', '__cxa', '__')):
        return 'c++/builtins'
    return 'other' + (f' ({Path(p).name})' if p else '')


def top_level(group):
    return group.split('/', 1)[0].split(' ', 1)[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+')
    ap.add_argument('--pie', required=True)
    ap.add_argument('--nm', default='/usr/lib/llvm-21/bin/llvm-nm')
    ap.add_argument('--symbolizer', default='/usr/lib/llvm-21/bin/llvm-symbolizer')
    ap.add_argument('--from-ns', type=int)
    ap.add_argument('--to-ns', type=int)
    ap.add_argument('--top', type=int, default=25)
    ap.add_argument('--pairs', type=int, default=15)
    ap.add_argument('--json')
    a = ap.parse_args()

    files = [parse_file(p) for p in a.files]
    if a.from_ns is not None or a.to_ns is not None:
        lo, hi = a.from_ns or 0, a.to_ns or (1 << 64)
        files = [f for f in files if f['t1'] >= lo and f['t0'] <= hi]
    if not files:
        raise SystemExit('no sample file in range')
    syms = Symbols(a.pie, a.nm, a.symbolizer)
    if syms.anchor is None:
        raise SystemExit(f'{a.pie}: no za_prof_anchor symbol (not the r24-prof PIE?)')
    notes = []
    bases = {f['anchor'] - syms.anchor for f in files}
    if len(bases) != 1:
        notes.append(f'files from different image bases: {sorted(hex(b) for b in bases)}')
    for f in files:
        base = f['anchor'] - syms.anchor
        if f['text'][1] and f['text'][0] != base:
            notes.append(f"{Path(f['path']).name}: VirtualQuery text start {f['text'][0]:#x} != anchor base {base:#x}")

    per_thread = collections.defaultdict(lambda: dict(samples=0, functions=collections.Counter(),
                                                      pairs=collections.Counter(), groups=collections.Counter()))
    names = {}
    all_fn, all_pairs, all_groups = collections.Counter(), collections.Counter(), collections.Counter()
    starts_needed = set()
    decoded = []
    for f in files:
        base = f['anchor'] - syms.anchor
        for thread, rflags, rip, caller in f['records']:
            info = f['threads'].get(thread, {})
            key = (f['boot'], thread, info.get('gid', 0), info.get('name', '?'))
            names[key] = info
            v = rip - base
            inside = syms.in_image(v)
            fn = syms.function(v) if inside else None
            cfn = None
            if caller:
                cv = caller - base
                cfn = syms.function(cv) if syms.in_image(cv) else None
            for x in (fn, cfn):
                if x:
                    starts_needed.add(x[0])
            decoded.append((key, inside, fn, cfn, caller))
    syms.resolve_files(starts_needed)
    for key, inside, fn, cfn, caller in decoded:
        name = fn[1] if fn else ('<ext>' if not inside else '<unknown>')
        group = group_of(fn[1] if fn else None, syms.files.get(fn[0], '') if fn else '', inside)
        t = per_thread[key]
        t['samples'] += 1
        t['functions'][(name, group)] += 1
        t['groups'][top_level(group)] += 1
        all_fn[(name, group)] += 1
        all_groups[top_level(group)] += 1
        if caller:
            cname = cfn[1] if cfn else '<ext or unknown>'
            t['pairs'][(cname, name)] += 1
            all_pairs[(cname, name)] += 1

    total = sum(t['samples'] for t in per_thread.values())
    report = dict(files=[Path(f['path']).name for f in files], pie=a.pie, total_samples=total, notes=notes,
                  windows=[dict(file=Path(f['path']).name, boot=f['boot'], window=f['window'], t0=f['t0'], t1=f['t1'],
                                records=len(f['records']), sent=f['sent'], dropped=f['dropped'], skipped=f['skipped'],
                                kill_errors=f['kill_errors'], period_us=f['period_us']) for f in files],
                  threads=[], all=None)

    def block(title, t, n):
        print(f'\n== {title}: {t["samples"]} samples')
        for g, c in t['groups'].most_common():
            print(f'   {c * 100 / t["samples"]:5.1f}%  {g}')
        print('   top functions (self):')
        for (name, group), c in t['functions'].most_common(n):
            print(f'   {c * 100 / t["samples"]:5.1f}%  {c:7d}  {name}  [{group}]')
        if t['pairs']:
            print('   top caller -> function:')
            for (cname, name), c in t['pairs'].most_common(a.pairs):
                print(f'   {c * 100 / t["samples"]:5.1f}%  {c:7d}  {cname} -> {name}')
        return dict(samples=t['samples'], groups=dict(t['groups']),
                    functions=[dict(name=k[0], group=k[1], samples=c) for k, c in t['functions'].most_common(n)],
                    pairs=[dict(caller=k[0], function=k[1], samples=c) for k, c in t['pairs'].most_common(a.pairs)])

    print(f'{len(files)} file(s), {total} samples; PIE {a.pie}')
    for note in notes:
        print('note:', note)
    for key in sorted(per_thread, key=lambda k: -per_thread[k]['samples']):
        info = names[key]
        title = f"thread {key[3]} ({info.get('kind', '?')}, boot {key[0]} slot {key[1]}, guest entry {info.get('entry', 0):#x})"
        entry = block(title, per_thread[key], a.top)
        entry.update(name=key[3], kind=info.get('kind'), boot=key[0], slot=key[1], gid=info.get('gid'), entry=info.get('entry'))
        report['threads'].append(entry)
    if per_thread:
        report['all'] = block('all threads', dict(samples=total, functions=all_fn, pairs=all_pairs, groups=all_groups), a.top)
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

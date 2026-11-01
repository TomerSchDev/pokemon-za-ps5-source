#!/usr/bin/env python3
"""P5 helper: index every translated function definition (addr -> module, unit, line) in the AOT tree.

Read-only over the game code. Output is a JSONL of addresses and unit names only (no game content), used by
harvest.py to verify that each annotated address exists in the translated code. Runs at BelowNormal priority,
streaming one unit at a time with a small worker pool, because other agents share this machine.

usage: index_functions.py AOT_DIR OUT_JSONL [--workers N]
"""
import argparse
import json
import os
import re
import sys
import time
from multiprocessing import Pool
from pathlib import Path

FUNC_RE = re.compile(rb'^void (f_[0-9a-f]+)\(Cpu \*c\) \{', re.M)


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


def scan_unit(args):
    module, path = args
    lower_priority()
    data = Path(path).read_bytes()
    unit = Path(path).name
    out = []
    # line numbers: count newlines up to each match (incremental, one pass)
    last_pos, line = 0, 1
    for m in FUNC_RE.finditer(data):
        line += data.count(b'\n', last_pos, m.start())
        last_pos = m.start()
        out.append((m.group(1)[2:].decode(), module, unit, line))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('aot', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--workers', type=int, default=3)
    a = ap.parse_args()
    lower_priority()
    t0 = time.time()
    jobs = []
    for module in ('main', 'sdk'):
        d = a.aot / module
        for p in sorted(d.glob(f'{module}_*.c')):
            jobs.append((module, str(p)))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_suffix('.tmp')
    n = 0
    seen = set()
    dups = 0
    with Pool(a.workers) as pool, tmp.open('w', encoding='utf-8') as fh:
        for i, rows in enumerate(pool.imap_unordered(scan_unit, jobs, chunksize=4), 1):
            for addr, module, unit, line in rows:
                if addr in seen:
                    dups += 1
                seen.add(addr)
                fh.write(json.dumps({'addr': addr, 'module': module, 'unit': unit, 'line': line}) + '\n')
                n += 1
            if i % 100 == 0:
                print(f'{i}/{len(jobs)} units, {n} functions, {time.time() - t0:.0f}s', file=sys.stderr, flush=True)
    os.replace(tmp, a.out)
    print(json.dumps({'units': len(jobs), 'functions': n, 'duplicate_addrs': dups, 'seconds': round(time.time() - t0, 1)}))


if __name__ == '__main__':
    main()

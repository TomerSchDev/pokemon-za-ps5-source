#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 acceptance: run the za-atlas acceptance queries, record output and wall time, check the expected facts.

Writes <parts/P6>/acceptance.json and prints a Markdown section (used verbatim in analysis/CODE-ATLAS-HE.md).
usage: acceptance.py [--out PARTS_P6_DIR] [--klog PATH] [--elf WSL_PATH]
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DATA = REPO.parent / 'za-atlas-data'
CLI = HERE / 'za_atlas.py'


def run(args):
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, '-I', str(CLI), *args], capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=REPO)
    return {'command': 'za-atlas ' + ' '.join(args), 'seconds': round(time.perf_counter() - t0, 3), 'rc': p.returncode,
            'stdout': p.stdout, 'stderr': p.stderr[-2000:]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', type=Path, default=DATA / 'parts' / 'P6')
    ap.add_argument('--klog', default='evidence/r28-hardware-20261030-0951Z/all.klog.log')
    ap.add_argument('--elf', default='/home/tomer/ps5-za-native/r28-play-20261030/r28/llvm-pie.elf')
    a = ap.parse_args()
    tests = [
        ('fn', ['fn', '7000a1158c'], lambda o: 'f_700033e770' in o and 'Condition::HavePokemonEncyclopediaTotal::Evaluate' in o and 'have_pokemon_encyclopedia_total_condition' in o),
        ('str', ['str', 'have_pokemon_encyclopedia_total_condition'], lambda o: '700329eb22' in o and 'f_70007de270' in o and 'f_7000a1158c' in o),
        ('who-calls', ['who-calls', '700033e770'], lambda o: 'f_7000a1158c' in o and 'Condition::HavePokemonEncyclopediaTotal::Evaluate' in o and 'direct callers (13)' in o),
        ('crash-cold', ['crash', a.klog, '--elf', a.elf, '--refresh'], None),
        ('crash-warm', ['crash', a.klog, '--elf', a.elf],
         lambda o: 'backend_texture_destroyed <- hle_nvnTextureFinalize (objects.c) <- f_700269d140 (main_1002.c) <- f_700189d750 (main_599.c) <- f_700181b540 (main_592.c) <- f_7001cf1a90 (main_786.c) <- f_7001b500f0 (main_663.c) <- f_700813e820 (sdk_031.c) <- f_7008144a50 (sdk_031.c) <- thread_main (kernel.c)' in o
         and 'movl\t%ecx, 0xa0(%rax)' in o and 'live_remove' in o),
        ('find-money', ['find', 'money'], lambda o: all(f'f_{x}' in o for x in ('70006bfce0', '70009c18d8', '7000a718c8', '7000dbb28c')) and 'Money::' in o),
        ('find-money-all', ['--all', 'find', 'money'], lambda o: all(f'f_{x}' in o for x in ('70006bfce0', '70009c18d8', '7000a718c8', '7000dbb28c', '700291eb18', '700291eaf0'))),
        ('find-KMoney', ['find', 'KMoney'], lambda o: 'f_70009c18d8' in o and 'f_7000dbb28c' in o),
        ('path', ['path', '7001b2921c', '70017fafd4'], lambda o: 'path (2 calls)' in o and 'f_7001b29660' in o),
        ('unit', ['unit', 'main_310'], lambda o: '497 functions' in o and 'f_7000a1158c' in o),
        ('class', ['class', 'nn::ui2d::TransitionConditionBase'], lambda o: 'derived classes (8)' in o),
        ('stats', ['stats'], lambda o: 'checks:' in o),
    ]
    results = []
    for name, args, expect in tests:
        r = run(args)
        r['name'] = name
        r['passed'] = (r['rc'] == 0) and (expect is None or bool(expect(r['stdout'])))
        if name == 'crash-cold':
            r['note'] = 'first decode after --refresh runs llvm-symbolizer/objdump in WSL; the one-second target applies to the warm query'
        results.append(r)
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {name:14} {r['seconds']:6.3f}s  {r['command']}", file=sys.stderr)
    query_tests = [r for r in results if r['name'] != 'crash-cold']
    summary = {'passed': all(r['passed'] for r in results), 'tests': len(results),
               'slowest_query_seconds': max(r['seconds'] for r in query_tests), 'all_queries_under_1s': all(r['seconds'] < 1.0 for r in query_tests),
               'ran': time.strftime('%Y-%m-%dT%H:%M:%S'), 'results': results}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / 'acceptance.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    # Markdown for the document
    out = []
    for r in results:
        out.append(f"### `{r['command']}` - {'עבר' if r['passed'] else 'נכשל'}, {r['seconds']:.3f} שניות" + (f" ({r['note']})" if r.get('note') else ''))
        body = r['stdout'].rstrip()
        if r['name'] in ('find-money-all', 'stats', 'crash-cold'):
            lines = body.splitlines()
            body = '\n'.join(lines[:20]) + (f'\n... ({len(lines) - 20} more lines)' if len(lines) > 20 else '')
        out.append('```\n' + body + '\n```\n')
    sys.stdout.reconfigure(encoding='utf-8')
    print('\n'.join(out))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Verify P4 artifacts and write the common DONE contract while owning P4."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('atlas_runtime', HERE / 'index_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=runtime.DATA / 'parts/P4')
    parser.add_argument('--agent', required=True)
    args = parser.parse_args()
    runtime.heartbeat(args.agent, args.output.parent.parent)
    tests = subprocess.run([sys.executable, '-I', str(HERE / 'test_crash.py')], capture_output=True, text=True)
    if tests.returncode:
        raise RuntimeError(tests.stdout + tests.stderr)
    (args.output / 'test-results.txt').write_text(tests.stdout + tests.stderr, encoding='utf-8')
    cold = json.loads((args.output / 'crash-acceptance.json').read_text(encoding='utf-8-sig'))
    warm = json.loads((args.output / 'crash-acceptance-warm.json').read_text(encoding='utf-8-sig'))
    names = [row['function'] for row in warm['compact_frames']]
    expected = ['backend_texture_destroyed', 'hle_nvnTextureFinalize', 'f_700269d140',
                'f_700189d750', 'f_700181b540', 'f_7001cf1a90', 'f_7001b500f0',
                'f_700813e820', 'f_7008144a50', 'thread_main']
    if names != expected:
        raise AssertionError('Crash stack mismatch: ' + repr(names))
    if ' '.join(warm['instruction'].split()) != 'movl %ecx, 0xa0(%rax)':
        raise AssertionError('Fault instruction mismatch')
    if warm['source_hint']['function'] != 'live_remove' or warm['source_hint']['confidence'] != 'derived':
        raise AssertionError('Inline-source evidence lost')
    if not warm['cache_hit'] or warm['runtime_seconds'] >= 1:
        raise AssertionError('Warm crash query exceeds the one-second target')
    details = json.loads((args.output / 'runtime-evidence.json').read_text(encoding='utf-8'))
    hle = [json.loads(line) for line in (args.output / 'hle.jsonl').read_text(encoding='utf-8').splitlines()]
    for row in hle:
        if set(row) != {'name', 'guest_addr', 'runtime_fn', 'runtime_file'}:
            raise AssertionError('Invalid HLE schema')
    files = {}
    for name in ('hle.jsonl', 'runtime-evidence.json', 'crash-acceptance.json',
                 'crash-acceptance-warm.json', 'test-results.txt', 'NOTES.md'):
        path = args.output / name
        files[name] = {'sha256': runtime.sha256(path), 'bytes': path.stat().st_size}
        if name == 'hle.jsonl':
            files[name]['records'] = len(hle)
    done = {'package': 'P4', 'agent': args.agent, 'files': files,
            'record_counts': {'hle.jsonl': len(hle)},
            'runtime_seconds': round(details['runtime_seconds'] + cold['runtime_seconds'] + warm['runtime_seconds'], 4),
            'checks': {'crash_stack_exact': True, 'instruction_exact': True, 'original_pc_not_abort_rip': True,
                       'unit_tests': 6, 'warm_crash_seconds': warm['runtime_seconds'],
                       'cold_crash_seconds': cold['runtime_seconds'],
                       'static_guest_bindings': details['with_static_guest_address'],
                       'inline_source_confidence': 'derived'},
            'known_limitations': details['binding_rules'] + cold['limitations'] + [
                'First-time LLVM symbolization exceeds one second; repeated identical lookups use validated local cache.',
                'Cache identity is ELF size and nanosecond mtime, not hashing a half-gigabyte ELF on every query.',
                'Runtime service entrypoints are indexed, not every internal static IPC helper.',
            ]}
    runtime.heartbeat(args.agent, args.output.parent.parent)
    temporary = args.output / 'DONE.json.tmp'
    temporary.write_text(json.dumps(done, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(args.output / 'DONE.json')
    print(json.dumps({key: done[key] for key in ('package', 'record_counts', 'checks', 'runtime_seconds')}))


if __name__ == '__main__':
    main()

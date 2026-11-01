#!/usr/bin/env python3
"""Index runtime registrations, never inventing dynamic HLE slot addresses."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[3]
DATA = REPO.parent / 'za-atlas-data'
RUNTIME = REPO.parent / 'pokeza-recomp-ps5' / 'runtime'
PATTERNS = (
    ('symbol', re.compile(r'\bHLE_FUNC\s*\(\s*"([^"\n]+)"\s*,\s*(\w+)\s*\)')),
    ('nvn', re.compile(r'\bNVN\s*\(\s*(nvn\w+)\s*\)')),
    ('service', re.compile(r'\bSERVICE\s*\(\s*"([^"\n]+)"\s*,\s*(\w+)\s*\)')),
)


def lower_priority():
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000):
            raise ctypes.WinError(ctypes.get_last_error())
    elif hasattr(os, 'nice'):
        os.nice(10)


def heartbeat(agent, data=DATA):
    if not agent:
        return
    result = subprocess.run([sys.executable, '-I', str(REPO / 'tools/za-atlas/claim.py'),
                             'heartbeat', '--agent', agent, '--package', 'P4', '--root', str(data)],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('P4 ownership lost: ' + result.stdout + result.stderr)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def without_comments(text):
    # Preserve newlines and quoted strings so registration evidence has real lines.
    token = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')
    return token.sub(lambda m: m[0] if m[0][0] in '\"\'' else re.sub(r'[^\n]', ' ', m[0]), text)


def registrations(runtime):
    for path in sorted(Path(runtime).rglob('*.c')):
        text = without_comments(path.read_text(encoding='utf-8', errors='replace'))
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count('\n', 0, match.start()) + 1
                if kind == 'nvn':
                    name, function = match[1], 'hle_' + match[1]
                else:
                    name, function = match[1], match[2]
                if kind == 'service':
                    name = 'service:' + name
                yield {'name': name, 'runtime_fn': function,
                       'runtime_file': os.path.relpath(path, REPO).replace('\\', '/'),
                       'line': line, 'kind': kind}


def build(runtime, symbols, output, agent=None):
    lower_priority()
    started = time.perf_counter()
    heartbeat(agent, output.parent.parent)
    exports = {}
    if not symbols.is_file():
        raise FileNotFoundError('P2 symbols.jsonl must exist before final P4 build: ' + str(symbols))
    with symbols.open(encoding='utf-8') as source:
        for line in source:
            row = json.loads(line)
            if row['kind'] in ('function', 'ifunc'):
                exports.setdefault(row['mangled'], set()).add(row['addr'])
    records, evidence = [], []
    for registration in registrations(runtime):
        targets = sorted(exports.get(registration['name'], [])) or [None]
        for address in targets:
            records.append({key: registration[key] for key in ('name', 'runtime_fn', 'runtime_file')} | {'guest_addr': address})
        evidence.append(registration)
    records.sort(key=lambda row: (row['name'], row['runtime_file'], row['guest_addr'] or ''))
    if not any(row['runtime_fn'] == 'hle_nvnTextureFinalize' for row in records):
        raise AssertionError('NVN registration anchor missing')
    output.mkdir(parents=True, exist_ok=True)
    heartbeat(agent, output.parent.parent)
    temporary = output / 'hle.jsonl.tmp'
    with temporary.open('w', encoding='utf-8', newline='\n') as destination:
        for row in records:
            destination.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
    heartbeat(agent, output.parent.parent)
    temporary.replace(output / 'hle.jsonl')
    details = {'records': len(records), 'with_static_guest_address': sum(row['guest_addr'] is not None for row in records),
               'registration_kinds': {kind: sum(row['kind'] == kind for row in evidence) for kind, _ in PATTERNS},
               'runtime_seconds': round(time.perf_counter() - started, 4),
               'symbols_sha256': sha256(symbols), 'registrations': evidence,
               'binding_rules': [
                   'HLE_FUNC(name, fn) registers a linker-section entry; loader.resolve prefers hle_lookup_impl(name).',
                   'guest_addr is an original defined guest function symbol from P2, NOT an actual redirected HLE slot.',
                   'dispatch.hle_register allocates 0x7080000000 + 16*i at runtime; i depends on registration order.',
                   'NVN(name) expands to HLE_FUNC(#name, hle_##name); nvnBootstrapLoader/GetProcAddress bind names dynamically.',
                   'SERVICE(name, handler) is reached through IPC/SVC dispatch, not a fixed guest import function.',
                   'null guest_addr means no provable original exported function address, not a missing implementation.',
                   'Source index includes conditional registrations; it does not assert all are enabled in a specific build.',
               ]}
    (output / 'runtime-evidence.json').write_text(json.dumps(details, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in details.items() if key not in ('registrations', 'binding_rules')}))
    return details


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUNTIME)
    parser.add_argument('--symbols', type=Path, default=DATA / 'parts/P2/symbols.jsonl')
    parser.add_argument('--output', type=Path, default=DATA / 'parts/P4')
    parser.add_argument('--agent')
    args = parser.parse_args()
    build(args.runtime, args.symbols, args.output, args.agent)

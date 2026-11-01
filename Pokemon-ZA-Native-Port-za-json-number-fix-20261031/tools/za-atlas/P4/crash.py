#!/usr/bin/env python3
"""Decode local crash logs against the exact ELF; never contacts a console."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[3]
DATA = REPO.parent / 'za-atlas-data'
BRIDGE = Path(__file__).with_name('llvm_bridge.sh')
BASE = 0x400000
FAULT = re.compile(r'\[za-native-fault\].*?\bsig=(\d+).*?\bfa=(?:0x)?([0-9a-fA-F]+).*?\bpc=(?:0x)?([0-9a-fA-F]+)')
HOST_PC = re.compile(r'\bhost pc\s+(?:0x)?([0-9a-fA-F]+)')
HOST_FRAME = re.compile(r'\[zarecomp\]\s+#\d+\s+(?:0x)?([0-9a-fA-F]{6,16})')
KERNEL_FRAME = re.compile(r'^#\s+(?:0x)?([0-9a-fA-F]{8,16})\s*$')


def parse_log(text, base=BASE):
    """Use the last fault event and distinguish original PC from abort-handler RIP."""
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if FAULT.search(line)]
    if not starts:
        starts = [index for index, line in enumerate(lines) if '*** signal' in line]
    if not starts:
        raise ValueError('No za-native-fault or *** signal event in this log')
    begin = starts[-1]
    fault = FAULT.search(lines[begin])
    signal, accessed, pc = (int(fault[1]), int(fault[2], 16), int(fault[3], 16)) if fault else (None, None, None)
    backtrace = False
    frames = []
    image_end = None
    image_line = False
    for line in lines[begin:]:
        if pc is None and (match := HOST_PC.search(line)):
            pc = int(match[1], 16)
        if '/app0/eboot.bin' in line:
            image_line = True
        elif image_line and (match := re.search(r'xotext:\s*([0-9a-fA-F]+):([0-9a-fA-F]+)', line)):
            image_end = int(match[2], 16)
            image_line = False
        if re.match(r'^#\s*backtrace:', line):
            backtrace = True
            continue
        if backtrace and ('dynamic libraries:' in line or line.strip() == '#'):
            backtrace = False
        match = KERNEL_FRAME.match(line) if backtrace else HOST_FRAME.search(line)
        if match:
            frames.append((int(match[1], 16), 'kernel' if backtrace else 'host'))
    if pc is None:
        # A system-only log has no original signal PC. Do not substitute abort's RIP.
        raise ValueError('Signal event has no original host PC; abort RIP is not the faulting instruction')
    addresses, seen = [], set()
    for address, source in [(pc, 'fault')] + frames:
        if address < base or (image_end is not None and address >= image_end) or address in seen:
            continue
        # Without a module map, only low-address eboot frames are eligible.
        if image_end is None and address >= 0x80000000:
            continue
        seen.add(address)
        addresses.append({'absolute': f'{address:x}', 'relative': f'{address - base:x}', 'source': source})
    if not addresses or addresses[0]['source'] != 'fault':
        raise ValueError('Original fault PC is outside the selected eboot image/base')
    return {'signal': signal, 'accessed': None if accessed is None else f'{accessed:x}',
            'base': f'{base:x}', 'event_line': begin + 1, 'frames': addresses}


def wsl_path(path):
    path = str(Path(path).resolve())
    if len(path) > 2 and path[1] == ':':
        return '/mnt/' + path[0].lower() + path[2:].replace('\\', '/')
    return path


def elf_identity(elf, distro):
    """Stat the real ELF on every lookup, including through the WSL filesystem."""
    path = Path(elf)
    if os.name == 'nt' and str(elf).startswith('/'):
        path = Path('\\\\wsl.localhost\\' + distro + str(elf).replace('/', '\\'))
    info = path.stat()
    return {'path': str(path), 'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns}


def llvm(mode, elf, extra, distro='Ubuntu'):
    env = os.environ.copy()
    if os.name == 'nt' and str(elf).startswith('/'):
        env['MSYS_NO_PATHCONV'] = '1'
        arguments = [wsl_path(value) if isinstance(value, Path) else str(value) for value in extra]
        command = ['wsl', '-d', distro, '--', 'bash', wsl_path(BRIDGE), mode, str(elf), *arguments]
    else:
        tool = 'llvm-symbolizer-21' if mode == 'symbolize' else 'llvm-objdump-21'
        binary = shutil.which(tool) or shutil.which(tool.rsplit('-', 1)[0])
        if not binary:
            raise FileNotFoundError(tool + ' is required')
        if mode == 'symbolize':
            with Path(extra[0]).open(encoding='utf-8') as source:
                result = subprocess.run([binary, '--obj=' + str(elf), '--output-style=JSON', '--inlines'],
                                        stdin=source, capture_output=True, text=True, encoding='utf-8', timeout=90)
            if result.returncode:
                raise RuntimeError(result.stderr)
            return result.stdout
        command = [binary, '--disassemble', '--start-address=' + str(extra[0]), '--stop-address=' + str(extra[1]), str(elf)]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout


def annotations_for(addresses, db=None, annotations=None):
    found = {}
    wanted = set(addresses)
    if db and Path(db).is_file():
        # Read-only URI prevents accidental database creation or modification.
        connection = sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            for addr in wanted:
                rows = connection.execute('SELECT name FROM annotations WHERE addr=?', (addr,)).fetchall()
                if rows:
                    found[addr] = [row[0] for row in rows]
        finally:
            connection.close()
    elif annotations and Path(annotations).is_file():
        with Path(annotations).open(encoding='utf-8') as source:
            for line in source:
                row = json.loads(line)
                if row['addr'] in wanted:
                    found.setdefault(row['addr'], []).append(row['name'])
    return found


def disassembly_excerpt(text, pc):
    rows = []
    for line in text.splitlines():
        match = re.match(r'^\s*([0-9a-fA-F]+):\s*(.*)$', line)
        if match and pc - 32 <= int(match[1], 16) <= pc + 32:
            instruction = re.sub(r'^(?:[0-9a-fA-F]{2}\s+)+', '', match[2]).strip()
            rows.append({'addr': match[1].lower(), 'instruction': instruction,
                         'fault': int(match[1], 16) == pc})
    if not any(row['fault'] for row in rows):
        raise ValueError('Disassembler did not decode the original fault PC')
    return rows


def source_hint(frame, instruction, runtime):
    # This is explicitly a source-derived hint, not an invented DWARF inline frame.
    if frame['function'] != 'backend_texture_destroyed' or not re.search(r'\bmovl\s+%ecx,\s*0xa0\(%rax\)', instruction):
        return None
    path = Path(runtime) / 'nvn/vulkan/textures.c'
    if not path.is_file():
        return None
    text = path.read_text(encoding='utf-8')
    match = re.search(r'static void live_remove\([^)]*\)\s*\{([\s\S]*?)\n\}', text)
    if not match or '((TexBackend *)last->backend)->reg = b->reg;' not in match[1]:
        return None
    statement = text.index('((TexBackend *)last->backend)->reg = b->reg;', match.start())
    return {'function': 'live_remove', 'confidence': 'derived',
            'source': str(path) + ':' + str(text.count('\n', 0, statement) + 1),
            'note': 'ELF names backend_texture_destroyed; source identifies the inlined live_remove reg write. No inline DWARF location available.'}


def analyze(log, elf, *, base=BASE, db=None, annotations=None, distro='Ubuntu',
            work_dir=None, runtime=None, refresh=False):
    started = time.perf_counter()
    parsed = parse_log(Path(log).read_text(encoding='utf-8', errors='replace'), base)
    work_dir = Path(work_dir or DATA / 'parts/P4')
    work_dir.mkdir(parents=True, exist_ok=True)
    identity = elf_identity(elf, distro)
    signature = {'elf': identity, 'addresses': [row['relative'] for row in parsed['frames']],
                 'decoder_sha256': hashlib.sha256(Path(__file__).read_bytes() + BRIDGE.read_bytes()).hexdigest()}
    key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    cache_dir = work_dir / 'cache'
    cache_dir.mkdir(exist_ok=True)
    cache = cache_dir / (key + '.json')
    cached = None
    if cache.is_file() and not refresh:
        try:
            cached = json.loads(cache.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    with tempfile.TemporaryDirectory(prefix='crash-', dir=work_dir) as scratch:
        if cached:
            symbols = cached['symbols']
        else:
            address_file = Path(scratch) / 'addresses.txt'
            address_file.write_text(''.join('0x' + row['relative'] + '\n' for row in parsed['frames']), encoding='utf-8')
            symbols = [json.loads(line) for line in llvm('symbolize', elf, [address_file], distro).splitlines() if line.strip()]
        if len(symbols) != len(parsed['frames']):
            raise ValueError('Symbolizer returned a different frame count')
        for frame, result in zip(parsed['frames'], symbols):
            entries = result.get('Symbol') or []
            symbol = entries[0] if entries else {}
            frame.update({'function': symbol.get('FunctionName') or '??', 'file': symbol.get('FileName') or '',
                          'line': symbol.get('Line') or 0, 'inlines': entries,
                          'symbol_start': symbol.get('StartAddress') or ''})
            guest = re.fullmatch(r'f_([0-9a-fA-F]+)', frame['function'])
            frame['guest_addr'] = guest[1].lower() if guest else None
        pc = int(parsed['frames'][0]['relative'], 16)
        first = parsed['frames'][0]
        start = int(first['symbol_start'], 16) if first['symbol_start'] else pc
        if pc - start > 65536:
            start = pc
        if cached:
            parsed['disassembly'] = cached['disassembly']
        else:
            parsed['disassembly'] = disassembly_excerpt(llvm('disassemble', elf, [hex(start), hex(pc + 36)], distro), pc)
            temporary = cache_dir / (key + '.' + uuid.uuid4().hex + '.tmp')
            temporary.write_text(json.dumps({'symbols': symbols, 'disassembly': parsed['disassembly'],
                                             'identity': identity}, ensure_ascii=False), encoding='utf-8')
            temporary.replace(cache)
    parsed['cache_hit'] = bool(cached)
    parsed['elf_identity'] = identity
    lookup = annotations_for([row['guest_addr'] for row in parsed['frames'] if row['guest_addr']], db, annotations)
    for frame in parsed['frames']:
        frame['annotations'] = lookup.get(frame['guest_addr'], [])
    parsed['instruction'] = next(row['instruction'] for row in parsed['disassembly'] if row['fault'])
    parsed['source_hint'] = source_hint(first, parsed['instruction'], runtime or REPO.parent / 'pokeza-recomp-ps5/runtime')
    compact = [first] + [row for row in parsed['frames'][1:]
                         if row['function'].startswith(('hle_', 'f_')) or row['function'] == 'thread_main']
    parsed['compact_frames'] = compact
    parsed['elf'] = str(elf)
    parsed['runtime_seconds'] = round(time.perf_counter() - started, 4)
    parsed['limitations'] = [
        'Only the last native fault event is selected; system abort RIP is not treated as the original PC.',
        'Host addresses are eboot absolute addresses minus the explicit base (default 0x400000).',
        'This ELF must match the crashing build. Source-derived hints are labeled and are not DWARF frames.',
        'Compact output hides signal-handler and guest_call wrappers; --all retains every eligible eboot frame.',
        'Return addresses are symbolized unchanged; they represent return sites rather than exact call instructions.',
    ]
    return parsed


def format_report(report, all_frames=False):
    first = report['frames'][0]
    header = f"SIG{report['signal']} PC=0x{first['absolute']} rel=0x{first['relative']} {first['function']}: {report['instruction']}"
    if report['source_hint']:
        header += ' [source-derived inline: ' + report['source_hint']['function'] + ']'
    lines = [header]
    for row in report['disassembly']:
        lines.append(('=> ' if row['fault'] else '   ') + row['addr'] + ': ' + row['instruction'])
    frames = report['frames'] if all_frames else report['compact_frames']
    labels = []
    for row in frames:
        label = row['function']
        if row['file']:
            label += ' (' + Path(row['file']).name + (':' + str(row['line']) if row['line'] else '') + ')'
        if row['annotations']:
            label += ' [' + '; '.join(row['annotations']) + ']'
        labels.append(label)
    lines.append(' <- '.join(labels))
    lines.append(f"{len(report['frames'])} eboot frames; {report['runtime_seconds']:.3f}s; ELF={report['elf']}")
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--base', type=lambda value: int(value, 0), default=BASE)
    parser.add_argument('--db', type=Path)
    parser.add_argument('--annotations', type=Path, default=DATA / 'parts/P5/annotations.jsonl')
    parser.add_argument('--work-dir', type=Path, default=DATA / 'parts/P4')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--wsl-distro', default='Ubuntu')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--refresh', action='store_true', help='Re-run LLVM despite a valid local cache')
    args = parser.parse_args(argv)
    report = analyze(args.log, args.elf, base=args.base, db=args.db, annotations=args.annotations,
                     distro=args.wsl_distro, work_dir=args.work_dir, runtime=args.runtime, refresh=args.refresh)
    print(json.dumps(report, ensure_ascii=False) if args.json else format_report(report, args.all))
    return report


if __name__ == '__main__':
    main()

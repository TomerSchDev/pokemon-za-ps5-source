"""Verify linked early-DLC-Dex hook and preserve the supplied base's globals/imports."""
from pathlib import Path
import argparse
import hashlib
import json
import mmap
import re
import subprocess

NM = '/usr/lib/llvm-21/bin/llvm-nm'
OBJDUMP = '/usr/lib/llvm-21/bin/llvm-objdump'
REQUIRED = [
    ('f_70008d4178', 'za_dlc_dex_unlock_pump'),
    ('za_dlc_dex_unlock_pump', 'f_70000393b8'),
    ('za_dlc_dex_unlock_pump', 'f_70009d0114'),
]


def command(*arguments):
    return subprocess.check_output([str(value) for value in arguments], text=True)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(base, image, evidence):
    def imports(path):
        return sorted(line.split()[-1] for line in command(NM, '-D', '--undefined-only', path).splitlines() if line.split())

    def globals(path):
        return {parts[-1] for line in command(NM, '--defined-only', '--extern-only', path).splitlines()
                if len(parts := line.split()) == 3 and parts[1] in 'ABCDGRST'}

    base_imports, new_imports = imports(base), imports(image)
    if base_imports != new_imports:
        raise ValueError('dynamic imports changed from supplied base')
    before, after = globals(base), globals(image)
    if before - after:
        raise ValueError('base global definitions were lost: ' + ','.join(sorted(before - after)))
    callers = sorted({caller for caller, callee in REQUIRED})
    assembly = command(OBJDUMP, '-d', '--no-show-raw-insn', '--disassemble-symbols=' + ','.join(callers), image)
    seen, caller = set(), None
    for line in assembly.splitlines():
        if match := re.match(r'^\s*[0-9a-f]+ <([^>]+)>:$', line):
            caller = match[1]
        elif caller and re.search(r'\b(?:callq?|jmpq?)\b', line):
            if match := re.search(r'<([^>]+)>', line):
                seen.add((caller, match[1]))
    missing = [pair for pair in REQUIRED if pair not in seen]
    if missing:
        raise ValueError('required feature linked calls missing: ' + repr(missing))
    with image.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        markers = {text: data.find(text.encode()) >= 0 for text in ('[dlc-dex-unlock-r1]', '[za-texguard] r28a texfix active', '[dexcount]')}
    if not all(markers.values()):
        raise ValueError('feature or preserved-feature trace marker missing: ' + repr(markers))
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'feature-callers.s').write_text(assembly)
    report = {'base_pie_sha256': sha(base), 'new_pie_sha256': sha(image),
              'dynamic_imports_preserved': True, 'dynamic_import_count': len(new_imports),
              'base_globals_removed': [], 'globals_added': sorted(after - before),
              'required_calls': REQUIRED, 'required_calls_present': True,
              'markers': markers, 'console_tested': False, 'in_game_pc_tested': False}
    (evidence / 'feature-image-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('image', type=Path)
    parser.add_argument('evidence', type=Path)
    options = parser.parse_args()
    verify(options.base, options.image, options.evidence)

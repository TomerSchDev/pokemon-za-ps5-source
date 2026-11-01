#!/usr/bin/env python3
"""Fail-closed structural checks and source-bound PC-proof gate for build-r27-play.sh."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

BASE_PIE_SHA = '4eea1378eae9c0914501e3ae1134517d2e4b3bc5a3accedad4980b12581ea787'
BASE_EBOOT_SHA = 'c382275b90704d50e50e57875116bd69341e6c6b9c9c4e4d43223b367e19f7fa'
BASE_ARCHIVE_SHA = 'dc7fb1cf908fe0af17d6997155897e3c71c9e866dfa9e524a9a2ec87583b1626'
MONEY_MEMBERS = {
    'main_220.o': '40d02ae57e4464b92957feb74bc526686f2de2cbb38ae4f8511456f74338175d',
    'main_303.o': '11496c6757ab5245677f3e1b98000125e1a666143ec735475c18819f0e7ca2b7',
    'main_315.o': '88c4a903e35afa399308d6f9e845f3ba36823280022969bae96740e5170d886d',
    'main_384.o': '6f8fc2f5cf7c301fc9bf6d730598494b328ebf4bb88bc32d2b72a737a7b0f70a',
    'main_1035.o': 'f9c4782d6e34def0ae056703616f0b076962a5233e26029d7d90d981fb62cebc',
}
OBJECT_CHANGES = ['cheats.o', 'native_menu.o', 'title_entry.o']
OBJECT_ADDITIONS = ['name_keyboard.o', 'run_name.o', 'za_money.o', 'za_player_name.o']
NM = '/usr/lib/llvm-21/bin/llvm-nm'
OBJDUMP = '/usr/lib/llvm-21/bin/llvm-objdump'
TIMING_CALLS = [
    ('f_7001b29660', 'za_dt_frame_cfg'), ('f_7001b29660', 'za_dt_present_mode'),
    ('f_7001b2a0e4', 'za_dt_step_ns'), ('f_7001b5407c', 'za_dt_step_ns'),
    ('f_70029f4214', 'za_dt_step_ns'), ('f_7001015260', 'za_dt_anim_table_ns'),
    ('f_70010273f0', 'za_dt_anim_table_ns'), ('za_dt_frame_cfg', '__wrap_za_title_frame_cfg'),
]
MONEY_CALLS = [
    ('f_70006bfce0', 'za_cheat_money_component'),
    ('f_70009c18d8', 'za_cheat_money_component'),
    ('f_7000a718c8', 'za_cheat_money_component'),
    ('f_700291eb18', 'za_cheat_money_component'),
    ('f_7000dbb28c', 'za_money_lifecycle_reset'),
    ('f_7000dbb28c', 'za_cheat_money_component'),
    ('f_700291eaf0', 'za_money_lifecycle_reset'),
    ('menu_handle_event', 'za_money_request'), ('menu_handle_event', 'za_money_set_enabled'),
]
MENU_CALLS = [
    ('menu_handle_event', 'za_performance_request'),
    ('menu_handle_event', '__wrap_za_performance_status'),
    ('menu_render', '__wrap_za_performance_status'),
    ('menu_render', 'renderer_present_count'), ('menu_render', 'SDL_GetTicksNS'),
    ('menu_render', 'vkCmdClearAttachments'), ('backend_present', 'menu_render'),
]


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def source_map(project):
    files = [
        'port/perf-r27/build-r27-play.sh', 'port/perf-r27/verify-r27-build.py',
        'port/perf-r27/cheats-r27.cpp', 'port/cheats-r27/za_money.cpp', 'port/cheats-r27/za_money.h',
        'port/cheats-r27/prepare-money-hooks.py', 'port/perf-r26/title_entry-r26p.c',
        'port/title/package-title.sh', 'port/title/verify-image.py',
        'port/local-shader-r19/verify-registration.py', 'port/shader-probe-r18/verify-image.py',
    ]
    files.extend('port/rando-v2/' + n + '.cpp' for n in ('native_menu', 'za_player_name', 'name_keyboard', 'run_name'))
    # Track direct/local transitive headers without recording unrelated source work.
    for folder in ('rando-v2', 'randomizer', 'randomizer/core', 'title', 'perf-r26', 'perf-r25',
                   'perf-r24clock', 'perf-r24prof', 'perf-r24'):
        for pattern in ('*.h', '*.hpp'):
            files.extend(p.relative_to(project).as_posix() for p in (project / 'port' / folder).glob(pattern))
    return {n: digest(project / n) for n in sorted(set(files))}


def check_sources(project, evidence):
    recorded = read(evidence / 'sources.json')
    require(recorded == source_map(project), 'Build inputs changed after snapshot; use a fresh revision')
    return recorded


def tree_map(root, pattern='*'):
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob(pattern)) if p.is_file()}


def archive_members(path):
    """Hash GNU/BSD ar members, excluding archive bookkeeping, without extracting 535 MiB twice."""
    result = {}
    longnames = b''
    with path.open('rb') as f:
        require(f.read(8) == b'!<arch>\n', f'Not an ordinary archive: {path}')
        while True:
            header = f.read(60)
            if not header:
                break
            require(len(header) == 60 and header[58:] == b'`\n', 'Malformed ar member header')
            name = header[:16].decode('ascii').strip()
            size = int(header[48:58].strip())
            remaining = size
            if name == '//':
                longnames = f.read(size)
                require(len(longnames) == size, 'Truncated ar long-name table')
                remaining = 0
            elif name.startswith('#1/'):
                length = int(name[3:])
                require(length <= size, 'Invalid BSD extended member name')
                name = f.read(length).rstrip(b'\0').decode('utf-8')
                remaining -= length
            elif name.startswith('/') and name[1:].isdigit():
                offset = int(name[1:])
                require(offset < len(longnames), 'Invalid GNU extended name offset')
                name = longnames[offset:].split(b'\n', 1)[0].rstrip(b'/\0').decode('utf-8')
            else:
                name = name[:-1] if name.endswith('/') and name not in ('/', '//', '/SYM64/') else name
            h = hashlib.sha256()
            while remaining:
                data = f.read(min(1 << 20, remaining))
                require(bool(data), 'Truncated archive member')
                h.update(data)
                remaining -= len(data)
            if name not in ('/', '//', '/SYM64/', '__.SYMDEF', '__.SYMDEF SORTED'):
                require(name not in result, f'Duplicate archive member: {name}')
                result[name] = h.hexdigest()
            if size & 1:
                require(len(f.read(1)) == 1, 'Truncated ar alignment')
    return result


def check_archive(base, candidate, units, output):
    require(digest(base) == BASE_ARCHIVE_SHA, 'Unapproved base game archive')
    before, after = archive_members(base), archive_members(candidate)
    require(list(before) == list(after), 'Archive member names/order changed')
    require(all(before[n] == h for n, h in MONEY_MEMBERS.items()), 'MONEY base member pin changed')
    changed = sorted(n for n in before if before[n] != after[n])
    require(changed == sorted(MONEY_MEMBERS), f'Unexpected archive changes: {changed}')
    require(all(after[n] == digest(units / n) for n in MONEY_MEMBERS), 'Patched object/archive mismatch')
    report = dict(base_sha256=digest(base), candidate_sha256=digest(candidate), member_count=len(before),
                  changed=changed, member_order_preserved=True, candidate_members=after)
    write(output, report)
    return report


def object_maps(previous, work):
    before = tree_map(previous / 'objects-r26p1', '*.o')
    after = tree_map(work / 'objects-r27', '*.o')
    added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
    changed = sorted(n for n in before.keys() & after.keys() if before[n] != after[n])
    require(added == OBJECT_ADDITIONS and changed == OBJECT_CHANGES and not removed,
            f'Unexpected title object changes: added={added}, changed={changed}, removed={removed}')
    runtime = tree_map(work / 'source/build/ps5/rt', '*.o')
    require(runtime and runtime == tree_map(previous / 'source/build/ps5/rt', '*.o'), 'Runtime objects changed')
    require(digest(work / 'objects-r27/assets_hashes.h') == digest(previous / 'objects-r26p1/assets_hashes.h'),
            'Randomizer asset hashes changed')
    return dict(added=added, changed=changed, removed=removed, candidate_objects=after, runtime_objects=runtime)


def output(command):
    return subprocess.check_output([str(v) for v in command], text=True)


def check_image(reference, pie, evidence):
    require(digest(reference) == BASE_PIE_SHA, 'Unapproved reference PIE')
    imports = {}
    for label, path in (('r26p1', reference), ('r27', pie)):
        imports[label] = sorted(line.split()[-1] for line in output([NM, '--dynamic', '--undefined-only', path]).splitlines() if line.split())
        (evidence / ('imports-' + label + '.txt')).write_text('\n'.join(imports[label]) + '\n')
    require(imports['r26p1'] == imports['r27'], 'Dynamic imports differ from r26p1')
    symbols = output([NM, '--defined-only', '--extern-only', pie])
    strong = [fields[2] for line in symbols.splitlines()
              if len(fields := line.split()) == 3 and fields[1] in 'ABCDGRST']
    duplicates = sorted(n for n, count in Counter(strong).items() if count > 1)
    require(not duplicates, f'Duplicate strong globals: {duplicates}')
    required = {'za_cheat_money_component', 'za_money_lifecycle_reset', 'za_money_request',
                'za_performance_request', 'za_randomizer_boot'}
    require(required <= set(strong), f'Missing required symbols: {sorted(required-set(strong))}')
    demangled = output([NM, '--defined-only', '--demangle', pie])
    # The linker localizes this hidden wrapper in both r26p1 and r27. It must be
    # defined text, but need not be externally visible. Its actual callers are
    # still mandatory below; public requirements above remain unchanged.
    wrapper_bindings = [fields[1] for line in demangled.splitlines()
                        if len(fields := line.split()) == 3 and fields[2] == '__wrap_za_performance_status']
    require(len(wrapper_bindings) == 1 and wrapper_bindings[0] in ('t', 'T'),
            'Missing or non-text status wrapper definition')
    for name in ('za::native::nameRun(', 'za::native::applyPlayerName(', 'za::native::NameKeyboard::press('):
        require(name in demangled, 'Missing linked NAME implementation: ' + name)
    (evidence / 'key-symbols.txt').write_text('\n'.join(line for line in demangled.splitlines()
        if any(key in line for key in ('za_money_', 'za_cheat_money_', 'za::native::nameRun(',
            'za::native::applyPlayerName(', 'za::native::NameKeyboard::press('))) + '\n')
    calls = TIMING_CALLS + MONEY_CALLS + MENU_CALLS
    functions = sorted({a for a, _ in calls} | {'renderer_stats', 'za_r24_stats', 'za_cheats_init'})
    assembly = output([OBJDUMP, '-d', '--no-show-raw-insn', '--disassemble-symbols=' + ','.join(functions), pie])
    (evidence / 'r27-callers.s').write_text(assembly)
    seen = set()
    caller = None
    for line in assembly.splitlines():
        if m := re.match(r'^\s*[0-9a-f]+ <([^>]+)>:$', line):
            caller = m[1]
        elif caller and re.search(r'\b(?:callq?|jmpq?)\b', line):
            if m := re.search(r'<([^>]+)>', line):
                seen.add((caller, m[1]))
    missing = [pair for pair in calls if pair not in seen]
    require(not missing, f'Required linked calls missing: {missing}')
    require(any((name, 'za_dt_report') in seen for name in ('za_r24_stats', 'renderer_stats')), 'Dynamic stats call missing')
    require(('menu_render', 'za_performance_status') not in seen, 'Overlay bypasses status wrapper')
    require(not any(a.startswith('f_') and b in ('za_title_frame_cfg', '__wrap_za_title_frame_cfg') for a, b in seen),
            'Game code bypasses the preserved dynamic frame hook')
    registrations = read(evidence / 'registration.json')
    require({v['section'] for v in registrations} == {'hle_impls', 'services', 'resets'} and
            all(v['preserved_count'] and v['candidate_bytes'] == v['baseline_bytes'] > 0 for v in registrations),
            'Runtime registrations not preserved')
    return dict(dynamic_imports_preserved=True, strong_duplicates=duplicates,
                status_wrapper_binding=wrapper_bindings[0],
                required_calls=[list(p) for p in calls], observed_calls=[list(p) for p in sorted(seen)],
                registrations=registrations, trainer_name_symbols_present=True)


def verify(project, previous, work, evidence):
    sources = check_sources(project, evidence)
    archive = check_archive(work / 'dyn-r26/liblasgame-r26.a', work / 'money-r27/liblasgame-r27.a',
                            work / 'money-r27', evidence / 'archive.json')
    objects = object_maps(previous, work)
    pie = work / 'source/build/ps5/title/llvm-pie.elf'
    image = check_image(project / 'artifacts/randomizer-r26p1-play/llvm-pie-r26p1.elf', pie, evidence)
    result = dict(verified=True, hardware_verified=False, pc_proof_required_before_package=True,
                  work=str(work), previous=str(previous), candidate_pie_sha256=digest(pie),
                  archive_sha256=archive['candidate_sha256'], sources=sources, **objects, image=image)
    write(evidence / 'build-verification.json', result)
    print('PASS: object/member/runtime/import/registration/name/MONEY/FPS/timing preservation')


def gate(project, previous, work, evidence, proof):
    sources = check_sources(project, evidence)
    build = read(evidence / 'build-verification.json')
    require(build.get('verified') is True and build['work'] == str(work) and build['previous'] == str(previous),
            'Candidate record does not describe this work copy')
    require(build['sources'] == sources, 'Candidate source snapshot mismatch')
    require(build['candidate_pie_sha256'] == digest(work / 'source/build/ps5/title/llvm-pie.elf'), 'Candidate PIE changed')
    require(build['archive_sha256'] == digest(work / 'money-r27/liblasgame-r27.a'), 'Candidate archive changed')
    objects = object_maps(previous, work)
    require(all(build[key] == objects[key] for key in ('candidate_objects', 'runtime_objects')), 'Candidate objects changed')
    pc = read(proof)
    for flag in ('pc_verified', 'ui_verified', 'save_verified', 'off_verified'):
        require(pc.get(flag) is True, f'Actual PC proof lacks {flag}=true')
    for key, file in (('runtime_sha256', 'za_money.cpp'), ('runtime_header_sha256', 'za_money.h'),
                      ('patcher_sha256', 'prepare-money-hooks.py')):
        require(pc.get(key) == sources['port/cheats-r27/' + file], f'PC proof source mismatch: {file}')
    write(evidence / 'pc-proof-accepted.json', dict(proof_path=str(proof), proof_sha256=digest(proof),
          candidate_pie_sha256=build['candidate_pie_sha256'], source_matched=True, proof=pc,
          hardware_verified=False))
    print('PASS: actual PC MONEY proof matches the candidate sources; packaging allowed, hardware acceptance pending')


def package(before, after, evidence):
    # Recheck the candidate and sources after conversion too, before recording acceptance.
    build = read(evidence / 'build-verification.json')
    accepted = read(evidence / 'pc-proof-accepted.json')
    gate(Path(__file__).resolve().parents[2], Path(build['previous']), Path(build['work']), evidence,
         Path(accepted['proof_path']))
    require(digest(before / 'eboot.bin') == BASE_EBOOT_SHA, 'Unapproved package baseline')
    a, b = tree_map(before), tree_map(after)
    require(a.keys() == b.keys(), 'Package file list differs from r26p1')
    changed = sorted(n for n in a if a[n] != b[n])
    require(changed == ['eboot.bin'], f'Package changed more than eboot.bin: {changed}')
    options = (after / 'perf-r24-options.txt').read_text()
    active = dict(line.split('=', 1) for text in options.splitlines() if (line := text.split('#', 1)[0].strip()) and '=' in line)
    require(active == {'scale': '1', 'ticks': 'tsc', 'vkprof': '0', 'submit': 'thread', 'fps': '1'}, 'Play options changed')
    require((after / 'slot-depth-options.txt').read_bytes() == b'64\n', 'Play slot depth changed')
    require((after / 'performance-options.txt').read_bytes() == b'optimized\n', 'r16 options changed')
    write(evidence / 'package-verification.json', dict(verified=True, changed=changed, candidate_files=b,
          pc_proof_sha256=digest(evidence / 'pc-proof-accepted.json'), hardware_verified=False))
    shipped = after.parent / 'evidence/r27'
    shipped.mkdir(parents=True, exist_ok=False)
    names = ('build-verification.json', 'sources.json', 'money-hook-manifest.json', 'archive.json',
             'registration.json', 'pc-proof-accepted.json', 'package-verification.json', 'flags-control.txt')
    for name in names:
        shutil.copyfile(evidence / name, shipped / name)
    write(after.parent / 'r27-package-verification.json', dict(
        version='r27-play', pc_money_proof_accepted=True, base_eboot_sha256=BASE_EBOOT_SHA,
        eboot_sha256=b['eboot.bin'], candidate_pie_sha256=build['candidate_pie_sha256'],
        only_package_changes=changed, hardware_verified=False,
        pc_money_proof=read(evidence / 'pc-proof-accepted.json'), source_sha256=build['sources'],
        evidence={str(Path('evidence/r27') / n): digest(shipped / n) for n in names}))
    print('PASS: only eboot.bin differs; r26p1 assets/options preserved byte-for-byte')


def main():
    mode, *args = sys.argv[1:]
    paths = list(map(Path, args))
    if mode == 'snapshot' and len(paths) == 2:
        write(paths[1], source_map(paths[0]))
    elif mode == 'archive' and len(paths) == 4:
        check_archive(*paths)
    elif mode == 'verify' and len(paths) == 4:
        verify(*paths)
    elif mode == 'gate' and len(paths) == 5:
        gate(*paths)
    elif mode == 'package' and len(paths) == 3:
        package(*paths)
    else:
        raise SystemExit('Expected snapshot PROJECT OUT, archive BASE NEW UNITS OUT, verify PROJECT PREV WORK EVIDENCE,\n'
                         'gate PROJECT PREV WORK EVIDENCE PC_PROOF, or package BASE_APP NEW_APP EVIDENCE')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Build a new-run JSON-number candidate from frozen main-1.1.0; no console access.

Reproduce the unchanged release first, then add exactly one C wrapper object and
two --wrap flags. Neither the release lock nor MAIN is edited. Package is an
eboot-only update: all installed v3 assets, mods, configs and saves stay in place.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-repo', required=True, type=Path)
    parser.add_argument('--wrapper', required=True, type=Path)
    parser.add_argument('--wrapper-sha256', required=True)
    parser.add_argument('--control-proof', type=Path, help='recheck an existing unchanged-base proof instead of relinking it again')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--package', required=True, type=Path)
    args = parser.parse_args()
    repo, wrapper, out, package = (p.resolve() for p in (args.base_repo, args.wrapper, args.out, args.package))
    native = Path('/home/tomer/ps5-za-native')
    if out.exists() or package.exists() or native not in out.parents or native not in package.parents:
        raise ValueError('--out and --package must be separate NEW folders beneath the native build root')
    if out in package.parents or package in out.parents or out == package:
        raise ValueError('package and output must not overlap')
    for path in (out, package):
        for protected in (repo, wrapper.parent, native / 'PS5_Vulkan', native / 'PS5_Mesa'):
            if path == protected or path in protected.parents or protected in path.parents:
                raise ValueError('output overlaps protected inputs')
    spec = importlib.util.spec_from_file_location('frozen_za_engine', repo / 'tools/za/za.py')
    za = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(za)
    if za.sha(wrapper) != args.wrapper_sha256:
        raise ValueError('wrapper differs from the tested source pin')
    name = 'main-1.1.0'
    lock = za.read_lock()
    profile = lock['profiles'][name]
    lock_path = za.lock_path(lock, name)
    lock_sha = za.sha(lock_path)
    main_before = (repo / 'tools/za/releases/MAIN').read_bytes()
    if main_before.strip() != name.encode():
        raise ValueError('MAIN changed: this candidate is only for main-1.1.0')
    before = za.check_files(lock, [name])
    if not before['ok']:
        raise ValueError('base inputs differ: ' + json.dumps(before))
    package_base = za.check_package(lock, name)
    if not package_base or not package_base['ok']:
        raise ValueError('base package differs: ' + json.dumps(package_base))
    out.mkdir()
    evidence = out / 'evidence'
    evidence.mkdir()
    source = out / 'source'
    source.mkdir()
    shutil.copy2(wrapper, source / 'json_number_ps5.c')
    shutil.copy2(__file__, source / Path(__file__).name)
    (source / 'executed-za.py').write_bytes(za.TOOL_SOURCE)
    shutil.copy2(lock_path, source / lock_path.name)
    za.atomic_json(evidence / 'base-before.json', before)
    # The production engine proves unchanged PIE and SELF before the candidate.
    if args.control_proof:
        control = args.control_proof.resolve().parent
        if native not in control.parents:
            raise ValueError('reused control must be under the native build root')
    else:
        control_result = za.reproduce(lock, [name], out / 'control')
        if not control_result or control_result['status'] != 'passed':
            raise ValueError('unchanged main-1.1.0 control did not reproduce')
        control = out / 'control' / name
    proof = za.check_proof(lock, control / 'proof.json')
    za.atomic_json(evidence / 'control-proof-recheck.json', proof)
    shutil.copy2(control / 'proof.json', evidence / 'control-original-proof.json')
    recipe = json.loads((control / 'recipe.json').read_text())
    program = out / 'program'
    program.mkdir()
    link = program / 'ps5-link'
    (link / 'stubs').mkdir(parents=True)
    frozen = Path(za.expand(profile['frozen_link']))
    for filename in ('app_crt.o', 'app_cpp_runtime.o', 'stubs/libSceAgc.so', 'stubs/libSceAgcDriver.so'):
        shutil.copy2(frozen / filename, link / filename)
    fsmap = link / 'title-fs-symbols.map'
    fsmap.write_text('{ local: __wrap_*; za_title_fs_set_root; };\n', encoding='ascii')
    sdk, vulkan = Path(za.expand(lock['sdk'])), Path(za.expand(lock['vulkan']))
    wrapper_object = program / 'json_number_ps5.o'
    commands = []
    with (evidence / 'build.log').open('x', encoding='utf-8') as log:
        def run(argv, output=None):
            argv = list(map(str, argv))
            commands.append(argv)
            print('RUN', ' '.join(argv[:5]), flush=True)
            if output is None:
                za.run(argv, out, log, {**os.environ, 'PS5_CLANG': '/usr/bin/clang-21',
                                      'PS5_VULKAN': str(vulkan), 'PS5_PAYLOAD_SDK': str(sdk)})
            else:
                result = subprocess.run(argv, cwd=out, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                Path(output).write_bytes(result.stdout)
                log.write(result.stderr.decode(errors='replace'))
                log.flush()
        nm = '/usr/lib/llvm-21/bin/llvm-nm'
        run([nm, '--defined-only', za.expand(profile['references']['pie'])], evidence / 'base-defined-symbols.txt')
        base_symbols = {line.split()[-1] for line in (evidence / 'base-defined-symbols.txt').read_text().splitlines() if line.split()}
        if 'plat_strtod' not in base_symbols:
            raise ValueError('base has no proven plat_strtod implementation')
        run(['sh', vulkan / 'tooling/prospero-clang18', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
             '-ffunction-sections', '-fdata-sections', '-c', source / 'json_number_ps5.c', '-o', wrapper_object])
        run([nm, '-u', wrapper_object], evidence / 'wrapper-imports.txt')
        imports = {line.split()[-1] for line in (evidence / 'wrapper-imports.txt').read_text().splitlines() if line.split()}
        if imports != {'plat_strtod'}:
            raise ValueError('unexpected wrapper imports: ' + repr(imports))
        wraps = ['getcwd', 'fopen', 'freopen', 'open', 'opendir', 'realpath', 'unlink',
                 'remove', 'rmdir', 'stat', 'lstat', 'mkdir', 'chmod', 'access', 'rename']
        flags = recipe['radv_link_flags'] + ['--wrap=' + f for f in wraps]
        flags += ['--version-script', str(fsmap)]
        flags += ['--wrap=localeconv', '--wrap=strtod']
        pie = program / 'llvm-pie.elf'
        argv = [sdk / 'bin/prospero-lld', *recipe['radv_linker_script'], '--eh-frame-hdr', *flags,
                '--version-script', vulkan / 'tooling/native/app-symbols.map', '--exclude-libs=ALL', '-e', '_start', '-o', pie,
                link / 'app_crt.o', link / 'app_cpp_runtime.o', *[za.expand(f) for f in profile['runtime']],
                za.expand(profile['archive']), *[za.expand(f) for f in profile['extra']], wrapper_object,
                link / 'stubs/libSceAgc.so', link / 'stubs/libSceAgcDriver.so', *recipe['radv_link_inputs'],
                '--as-needed', *[za.expand(f) for f in lock['sdk_shared_libraries']]]
        run(argv)
        run([nm, '--defined-only', pie], evidence / 'defined-symbols.txt')
        symbols = {line.split()[-1] for line in (evidence / 'defined-symbols.txt').read_text().splitlines() if line.split()}
        lost, added = sorted(base_symbols - symbols), sorted(symbols - base_symbols)
        za.atomic_json(evidence / 'symbol-diff.json', {'lost': lost, 'added': added})
        if lost or not {'__wrap_localeconv', '__wrap_strtod', 'plat_strtod'} <= symbols:
            raise ValueError('lost base symbols or missing required wrapper symbols')
        # Prove actual JSON call targets after linking, not only wrapper presence.
        json_functions = sorted(s for s in symbols if 'nlohmann' in s and
                                any(term in s for term in ('lexer', 'parser', 'parse')))
        if not json_functions:
            raise ValueError('no JSON parser functions available for call-target audit')
        run(['/usr/lib/llvm-21/bin/llvm-objdump', '--disassemble',
             '--disassemble-symbols=' + ','.join(json_functions), pie], evidence / 'json-parser-disassembly.txt')
        assembly = (evidence / 'json-parser-disassembly.txt').read_text()
        call_targets = {}
        for function in ('localeconv', 'strtod'):
            matches = [line for line in assembly.splitlines() if
                       ('call' in line or 'jmp' in line) and '<__wrap_' + function in line]
            if not matches:
                raise ValueError('no proved JSON call to __wrap_' + function)
            call_targets[function] = matches
        run([nm, '-u', pie], evidence / 'candidate-undefined-symbols.txt')
        unresolved = {line.split()[-1] for line in (evidence / 'candidate-undefined-symbols.txt').read_text().splitlines() if line.split()}
        if {'localeconv', 'strtod'} & unresolved:
            raise ValueError('original broken libc number imports remain unresolved')
        za.atomic_json(evidence / 'json-call-targets.json', call_targets)
        run([sys.executable, repo / 'port/local-shader-r19/verify-registration.py',
             za.expand(profile['references']['pie']), pie], evidence / 'registration.json')
        stripped, converted, binary = (program / f for f in ('title-stripped.elf', 'eboot.elf', 'eboot.bin'))
        run([sdk / 'bin/llvm-strip', '--strip-debug', '-o', stripped, pie])
        tool = vulkan / 'build/host/ps5-native-tool'
        run([tool, 'link', '--in', stripped, '--out', converted, '--stub-dir', sdk / 'target/lib',
             '--stub', link / 'stubs/libSceAgc.so', '--stub', link / 'stubs/libSceAgcDriver.so',
             '--module-sdk', '0x02000009', '--companion-sdk', '0x08050001', '--file-name', 'eboot.elf'])
        run([sys.executable, repo / 'port/title/verify-image.py', stripped, converted,
             evidence / 'defined-symbols.txt'], evidence / 'image-preservation.json')
        run([tool, 'self', '--sign', '--in', converted, '--out', binary, '--magic', '0x1D3D154F'])
        run([tool, 'self', '--inspect', '--file', binary], evidence / 'self-inspection.txt')
    after = za.check_files(lock, [name])
    if not after['ok'] or za.sha(lock_path) != lock_sha or (repo / 'tools/za/releases/MAIN').read_bytes() != main_before:
        raise ValueError('base inputs, lock or MAIN changed during the build')
    if za.sha(wrapper) != args.wrapper_sha256:
        raise ValueError('wrapper source changed during the build')
    report = {'schema': 1, 'status': 'candidate-built-not-tested-on-hardware', 'base': name,
              'base_eboot_sha256': lock['files'][profile['references']['eboot']]['sha256'],
              'base_lock_sha256': lock_sha, 'base_inputs_before': before, 'base_inputs_after': after,
              'base_package_verified': package_base, 'base_objects_changed': [],
              'added_object': 'json_number_ps5.o', 'added_link_flags': ['--wrap=localeconv', '--wrap=strtod'],
              'wrapper_source_sha256': args.wrapper_sha256, 'eboot_sha256': za.sha(binary), 'pie_sha256': za.sha(pie),
              'console_access': False, 'hardware_tested': False, 'installed': False,
              'package_kind': 'eboot-only update; keep installed main-1.1.0 assets, mods, configs and saves'}
    za.atomic_json(evidence / 'commands.json', commands)
    za.atomic_json(evidence / 'build-result.json', report)
    package.mkdir()
    shutil.copy2(binary, package / 'eboot.bin')
    shutil.copytree(evidence, package / 'evidence')
    shutil.copytree(source, package / 'source')
    (package / 'README-HE.txt').write_text(
        'מועמד לתיקון קריסה ביצירת ריצה חדשה — בסיס main-1.1.0. טרם נבדק בחומרה.\n'
        'השינוי היחיד: עטיפות localeconv ו-strtod לקריאת מספרים עשרוניים ב-JSON.\n'
        'חבילת עדכון eboot בלבד. יש לשמור את נכסי v3, העברית, המודים והאפשרויות הקיימים.\n'
        'התקנה מתואמת בלבד: לסגור את המשחק, לתפוס תור zw queue ולגבות שמירות עדכניות בקריאה כפולה והשוואת SHA-256.\n'
        'לשמור עותק rollback של eboot המותקן (main-1.1.0, 7d837a58...), להעלות eboot.bin.new, לקרוא חזרה ולאמת SHA-256,\n'
        'לבצע rename ולקרוא שוב. אין להחליף assets, mods או שמירות.\n'
        'בדיקה: לתעד klog כולל backlog, ליצור ריצה חדשה, להיכנס למשחק, לשמור ולטעון שוב.\n'
        'חזרה: כשהמשחק סגור, להחזיר רק את eboot המגובה באותו נוהל ולוודא SHA-256. אין להחזיר שמירה ישנה מעל התקדמות חדשה.\n',
        encoding='utf-8')
    sums = {str(p.relative_to(package)): za.sha(p) for p in sorted(package.rglob('*')) if p.is_file()}
    za.atomic_json(package / 'SHA256SUMS.json', sums)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

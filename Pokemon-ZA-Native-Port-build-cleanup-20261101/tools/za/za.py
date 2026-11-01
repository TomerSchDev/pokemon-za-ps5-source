#!/usr/bin/env python3
"""One offline entry point for pinned Z-A release verification and relinking."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from build_cleanup import SOURCE_BYTES as CLEANUP_SOURCE, SOURCE_SHA256 as CLEANUP_SHA, cleanup_conversion_intermediates

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
NATIVE = Path('/home/tomer/ps5-za-native')
LOCK = HERE / 'profiles.lock.json'
RELEASES = HERE / 'releases'
SCHEMA = 1
# Pin the running process once. Reading __file__ later can report a concurrently edited
# on-disk dispatcher rather than the code this Python process actually loaded.
TOOL_SOURCE = Path(__file__).read_bytes()
TOOL_SHA = hashlib.sha256(TOOL_SOURCE).hexdigest()
RECIPE_SOURCE = (HERE / 'recipe.sh').read_bytes()
RECIPE_SHA = hashlib.sha256(RECIPE_SOURCE).hexdigest()


class ZaError(Exception):
    pass


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def expand(value):
    return str(value).replace('{repo}', str(REPO)).replace('{native}', str(NATIVE))


def cli_path(value):
    if len(value) >= 3 and value[1] == ':' and value[2] in '\\/':
        return '/mnt/' + value[0].lower() + value[2:].replace('\\', '/')
    return value


def tokenize(value):
    return str(value).replace(str(REPO), '{repo}').replace(str(NATIVE), '{native}')


def read_lock():
    data = json.loads(LOCK.read_text(encoding='utf-8'))
    if data.get('schema') != SCHEMA:
        raise ZaError('Unsupported profile lock schema')
    # Release locks (tools/za/releases/<name>.lock.json) are frozen once each and merged in memory.
    # The base lock stays byte-identical, so proofs of the historical profiles remain valid.
    for path in sorted(RELEASES.glob('*.lock.json')) if RELEASES.is_dir() else []:
        rel = json.loads(path.read_text(encoding='utf-8'))
        if rel.get('schema') != SCHEMA:
            raise ZaError('Unsupported release lock schema: ' + path.name)
        for token, pin in rel['files'].items():
            if data['files'].setdefault(token, pin) != pin:
                raise ZaError(f'{path.name} pins {token} differently from another lock')
        for key in ['shared', 'sdk_shared_libraries']:
            if set(rel[key]) - set(data[key]):
                raise ZaError(f'{path.name} adds {key}; the toolchain must match the base lock')
        for name, profile in rel['profiles'].items():
            if name in data['profiles']:
                raise ZaError('Duplicate profile: ' + name)
            data['profiles'][name] = {**profile, '_lock': str(path)}
    return data


def lock_path(lock, name):
    return Path(lock['profiles'][name].get('_lock', LOCK))


def main_profile():
    name = (RELEASES / 'MAIN').read_text(encoding='utf-8').strip()
    if not name:
        raise ZaError('releases/MAIN is empty')
    return name


def selection(lock, name):
    if name == 'all':
        return list(lock['profiles'])
    if name not in lock['profiles']:
        raise ZaError('Unknown profile: ' + name)
    return [name]


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: an existing different or identical report is never overwritten.
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def check_files(lock, names, refs=True, inputs=True):
    paths = set()
    if inputs:
        paths.update(lock['shared'])
    for name in names:
        p = lock['profiles'][name]
        if inputs:
            paths.update(p['inputs'])
        if refs:
            paths.update(p['references'].values())
            paths.add(p['delivered_eboot'])
    errors = []
    for path in sorted(paths):
        absolute = Path(expand(path))
        expected = lock['files'][path]
        if not absolute.is_file():
            errors.append({'path': path, 'error': 'missing'})
        elif absolute.stat().st_size != expected['size']:
            errors.append({'path': path, 'error': 'size mismatch'})
        else:
            actual = sha(absolute)
            if actual != expected['sha256']:
                errors.append({'path': path, 'error': 'SHA-256 mismatch', 'actual': actual,
                               'expected': expected['sha256']})
    return {'checked_files': len(paths), 'ok': not errors, 'errors': errors}


def run(argv, cwd, log, env=None):
    log.write('\n$ ' + shlex.join(map(str, argv)) + '\n')
    log.flush()
    result = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=log,
                            stderr=subprocess.STDOUT, env=env, check=False)
    log.flush()
    if result.returncode:
        raise ZaError(f'Command exited {result.returncode}: {argv[0]}; see {log.name}')


def equal_bytes(a, b):
    with Path(a).open('rb') as left, Path(b).open('rb') as right:
        while True:
            x = left.read(4 * 1024 * 1024)
            y = right.read(4 * 1024 * 1024)
            if x != y:
                return False
            if not x:
                return True


def new_root(path, lock):
    path = Path(path).expanduser().resolve()
    protected = [Path(expand(p['tree'])).resolve() for p in lock['profiles'].values()]
    protected += [NATIVE / 'PS5_Vulkan', NATIVE / 'PS5_Mesa', NATIVE / 'PS5_PayloadSDK']
    for root in protected:
        if path == root or root in path.parents or path in root.parents:
            raise ZaError('Output would overlap a protected input tree: ' + str(path))
    if path == REPO or path in REPO.parents:
        raise ZaError('Output cannot contain the repository')
    path.mkdir(parents=True, exist_ok=False)
    return path


def relink(lock, name, out):
    p = lock['profiles'][name]
    tree = Path(expand(p['tree']))
    sdk = Path(expand(lock['sdk']))
    vulkan = Path(expand(lock['vulkan']))
    receipt = {'schema': SCHEMA, 'profile': name, 'started_utc': utc(), 'status': 'running',
               'method': 'relink-frozen-objects-and-convert-sign',
               'full_source_rebuild': False,
               'scope': 'PIE and eboot.bin only; no application assets or saves',
               'profile_lock': lock_path(lock, name).name,
               'profile_lock_sha256': sha(lock_path(lock, name)), 'tool_sha256': TOOL_SHA,
               'recipe_helper_sha256': RECIPE_SHA,
               'cleanup_helper_sha256': CLEANUP_SHA,
               'console_access': False, 'output': str(out)}
    try:
        before = check_files(lock, [name])
        receipt['inputs_before'] = before
        if not before['ok']:
            raise ZaError('Pinned prerequisites differ or are missing; no link attempted')
        with (out / 'build.log').open('x', encoding='utf-8', newline='\n') as log:
            (out / 'executed-za.py').write_bytes(TOOL_SOURCE)
            (out / 'executed-build_cleanup.py').write_bytes(CLEANUP_SOURCE)
            recipe_script = out / 'executed-recipe.sh'
            recipe_script.write_bytes(RECIPE_SOURCE)
            # The historical RADV recipe writes a symbol map beneath its ROOT argument.
            # A private facade gives that write its own directory, leaving original trees untouched.
            facade = out / 'vulkan-facade'
            facade.mkdir()
            for sub in ['tooling', '.deps']:
                (facade / sub).symlink_to(vulkan / sub, target_is_directory=True)
            (facade / 'tools').mkdir()
            shutil.copyfile(vulkan / 'tools/radv-link.sh', facade / 'tools/radv-link.sh')
            recipe_json = out / 'recipe.json'
            run(['bash', recipe_script, facade, sdk, expand(lock['radv_archive']),
                 recipe_json], out, log, {**os.environ, 'PS5_CLANG': '/usr/bin/clang-21'})
            recipe = json.loads(recipe_json.read_text())
            link = out / 'ps5-link'
            (link / 'stubs').mkdir(parents=True)
            frozen = Path(expand(p['frozen_link']))
            for f in ['app_crt.o', 'app_cpp_runtime.o', 'stubs/libSceAgc.so',
                      'stubs/libSceAgcDriver.so']:
                shutil.copyfile(frozen / f, link / f)
            fsmap = link / 'title-fs-symbols.map'
            fsmap.write_text('{ local: __wrap_*; za_title_fs_set_root; };\n', encoding='ascii')
            fswraps = ['getcwd', 'fopen', 'freopen', 'open', 'opendir', 'realpath', 'unlink',
                       'remove', 'rmdir', 'stat', 'lstat', 'mkdir', 'chmod', 'access', 'rename']
            flags = recipe['radv_link_flags'] + ['--wrap=' + f for f in fswraps]
            flags += ['--version-script', str(fsmap)]
            pie = out / 'llvm-pie.elf'
            argv = [sdk / 'bin/prospero-lld', *recipe['radv_linker_script'], '--eh-frame-hdr',
                    *flags, '--version-script', vulkan / 'tooling/native/app-symbols.map',
                    '--exclude-libs=ALL', '-e', '_start', '-o', pie,
                    link / 'app_crt.o', link / 'app_cpp_runtime.o',
                    *[expand(f) for f in p['runtime']], expand(p['archive']),
                    *[expand(f) for f in p['extra']], link / 'stubs/libSceAgc.so',
                    link / 'stubs/libSceAgcDriver.so', *recipe['radv_link_inputs'],
                    '--as-needed', *[expand(f) for f in lock['sdk_shared_libraries']]]
            run(argv, tree / 'source', log)
            stripped = out / 'title-stripped.elf'
            converted = out / 'eboot.elf'
            binary = out / 'eboot.bin'
            run([sdk / 'bin/llvm-strip', '--strip-debug', '-o', stripped, pie], out, log)
            tool = vulkan / 'build/host/ps5-native-tool'
            run([tool, 'link', '--in', stripped, '--out', converted, '--stub-dir',
                 sdk / 'target/lib', '--stub', link / 'stubs/libSceAgc.so', '--stub',
                 link / 'stubs/libSceAgcDriver.so', '--module-sdk', '0x02000009',
                 '--companion-sdk', '0x08050001', '--file-name', 'eboot.elf'], out, log)
            run([tool, 'self', '--sign', '--in', converted, '--out', binary,
                 '--magic', '0x1D3D154F'], out, log)
            run([tool, 'self', '--inspect', '--file', binary], out, log)
        comparisons = {}
        for key, generated in [('pie', pie), ('eboot', binary)]:
            ref = p['references'][key]
            expected = lock['files'][ref]['sha256']
            actual = sha(generated)
            comparisons[key] = {'file': generated.name, 'reference': ref,
                                'expected_sha256': expected, 'actual_sha256': actual,
                                'size': generated.stat().st_size,
                                'sha256_matches': actual == expected,
                                'byte_for_byte_equal': equal_bytes(generated, expand(ref))}
        receipt['outputs'] = comparisons
        receipt['inputs_after'] = check_files(lock, [name])
        success = (receipt['inputs_after']['ok'] and
                   all(c['sha256_matches'] and c['byte_for_byte_equal'] for c in comparisons.values()))
        receipt['status'] = 'passed' if success else 'failed'
        if not success:
            raise ZaError('Reproduction did not match the pinned release')
    except (ZaError, OSError, ValueError) as exc:
        receipt['status'] = 'failed'
        receipt['error'] = str(exc)
    receipt['finished_utc'] = utc()
    atomic_json(out / 'proof.json', receipt)
    return receipt


def check_proof(lock, path):
    path = Path(path)
    proof = json.loads(path.read_text(encoding='utf-8'))
    name = proof.get('profile')
    if name not in lock['profiles']:
        raise ZaError('Proof has unknown profile')
    if proof.get('status') != 'passed' or proof.get('profile_lock_sha256') != sha(lock_path(lock, name)):
        raise ZaError('Proof did not pass, or uses a different profile lock')
    if proof.get('method') != 'relink-frozen-objects-and-convert-sign':
        raise ZaError('Unknown proof method')
    comparisons = {}
    for key, filename in [('pie', 'llvm-pie.elf'), ('eboot', 'eboot.bin')]:
        generated = path.parent / filename
        ref = lock['profiles'][name]['references'][key]
        expected = lock['files'][ref]['sha256']
        if not generated.is_file() or sha(generated) != expected:
            raise ZaError('Generated output is absent or differs: ' + filename)
        if sha(expand(ref)) != expected or not equal_bytes(generated, expand(ref)):
            raise ZaError('Reference is absent or differs: ' + ref)
        comparisons[key] = {'sha256': expected, 'byte_for_byte_equal': True}
    return {'profile': name, 'status': 'passed', 'outputs': comparisons}


def cleanup_profiles(lock, names, root, keep_intermediates=None):
    """End-of-success cleanup, with all locked inputs protected and failures explicit."""
    protected = [expand(path) for path in lock['files']]
    reports = {}
    for name in names:
        try:
            reports[name] = cleanup_conversion_intermediates(
                root / name, protected_paths=protected, keep_reason=keep_intermediates)
        except (OSError, ValueError) as exc:
            reports[name] = {'status': 'error', 'deleted': [], 'errors': [str(exc)]}
    return reports


def reproduce(lock, names, out_dir, *, keep_intermediates=None, defer_cleanup=False):
    # Check before creating an output tree; never "repair" or silently rebaseline inputs.
    gate = check_files(lock, names)
    if not gate['ok']:
        print(json.dumps(gate, ensure_ascii=False, indent=2))
        return None
    root = new_root(out_dir, lock)
    proofs = []
    for name in names:
        print('za: reproducing ' + name, flush=True)
        out = root / name
        out.mkdir()
        proofs.append(relink(lock, name, out))
        print('za: ' + name + ': ' + proofs[-1]['status'], flush=True)
    result = {'schema': SCHEMA, 'status': 'passed' if all(p['status'] == 'passed' for p in proofs) else 'failed',
              'method': lock['method'], 'full_source_rebuild': False,
              'profile_lock_sha256': sha(LOCK),
              'profiles': {p['profile']: {'status': p['status'], 'proof': p['profile'] + '/proof.json',
                                          'profile_lock_sha256': p.get('profile_lock_sha256')}
                           for p in proofs}}
    if result['status'] == 'passed' and not defer_cleanup:
        result['cleanup'] = cleanup_profiles(lock, names, root, keep_intermediates)
        if any(c['status'] == 'error' for c in result['cleanup'].values()):
            result['status'] = 'failed'
            result['error'] = 'Reproduction passed, but intermediate cleanup failed; inspect cleanup receipts'
    else:
        result['cleanup'] = {'status': 'deferred_until_package_gate' if defer_cleanup else 'not_run_failed_build'}
    atomic_json(root / 'summary.json', result)
    return result


def check_package(lock, name):
    """Verify every file of the release's delivered package against its pinned SHA256SUMS.json."""
    p = lock['profiles'][name]
    if 'package_sums' not in p:
        return None
    sums_path = Path(expand(p['package_sums']))
    if sha(sums_path) != lock['files'][p['package_sums']]['sha256']:
        raise ZaError('package SHA256SUMS.json differs from its pin')
    sums = json.loads(sums_path.read_text(encoding='utf-8'))
    bad = [rel for rel, digest in sorted(sums.items())
           if not (sums_path.parent / rel).is_file() or sha(sums_path.parent / rel) != digest]
    return {'package': str(sums_path.parent), 'files': len(sums), 'ok': not bad, 'errors': bad}


def build_main(args):
    """za build main: the single front door for the current main release (relink + package check)."""
    lock = read_lock()
    name = main_profile()
    if name not in lock['profiles']:
        raise ZaError('releases/MAIN names an unknown profile: ' + name)
    if args.package and Path(args.package).exists():
        raise ZaError('--package must be a NEW directory')
    result = reproduce(lock, [name], args.out, defer_cleanup=True)
    if result is None:
        return 2
    root = Path(args.out).resolve()
    package = check_package(lock, name)
    result = {'main': name, 'reproduce': result, 'package_check': package}
    if result['reproduce']['status'] == 'passed' and package and package['ok'] and args.package:
        src = Path(expand(lock['profiles'][name]['package_sums'])).parent
        dst = Path(args.package)
        dst.mkdir(parents=True)
        for rel in json.loads((src / 'SHA256SUMS.json').read_text(encoding='utf-8')):
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            # The eboot comes from this relink (proved byte-identical), everything else from the pinned package.
            shutil.copyfile(root / name / 'eboot.bin' if rel == 'eboot.bin' else src / rel, target)
        shutil.copyfile(src / 'SHA256SUMS.json', dst / 'SHA256SUMS.json')
        result['package_out'] = str(dst)
    ok = result['reproduce']['status'] == 'passed' and (package is None or package['ok'])
    if ok:
        result['cleanup'] = cleanup_profiles(lock, [name], root, getattr(args, 'keep_intermediates', None))
        if any(c['status'] == 'error' for c in result['cleanup'].values()):
            ok = False
            result['error'] = 'Build gates passed, but intermediate cleanup failed; inspect cleanup receipts'
    else:
        result['cleanup'] = {'status': 'not_run_failed_build'}
    result['status'] = 'passed' if ok else 'failed'
    atomic_json(root / 'build-main.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 2


def dispatch():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('profiles', help='list unambiguous pinned historical releases')
    for command in ['doctor', 'verify']:
        sp = sub.add_parser(command, help='read-only prerequisite / release verification')
        sp.add_argument('profile', nargs='?', default='all')
        sp.add_argument('--report', help='new JSON report path; existing reports are preserved')
    sp = sub.add_parser('reproduce', help='relink frozen inputs, convert/sign and compare actual bytes')
    sp.add_argument('profile', nargs='?', default='all')
    sp.add_argument('--out', required=True, help='new isolated output directory')
    sp.add_argument('--keep-intermediates', metavar='REASON',
                    help='retain conversion ELF diagnostics for this job with an explicit reason')
    sp = sub.add_parser('check-proof', help='independently rehash and compare generated outputs')
    sp.add_argument('proof')
    sp = sub.add_parser('build', help='main: reproduce the current main release (releases/MAIN) and '
                        'optionally assemble its package; r29-ui: delegate to the audited project builder')
    sp.add_argument('target', choices=['main', 'r29-ui'])
    sp.add_argument('--out', required=True, help='new isolated WSL build directory')
    sp.add_argument('--package', help='new package directory')
    sp.add_argument('--assets', help='verified rando-v3 assets directory')
    sp.add_argument('--tree', help='prepared UI baseline tree')
    sp.add_argument('--keep-intermediates', metavar='REASON',
                    help='main only: retain conversion ELF diagnostics for this job with an explicit reason')
    args = parser.parse_args()
    if getattr(args, 'keep_intermediates', None) is not None and not args.keep_intermediates.strip():
        raise ZaError('--keep-intermediates requires a nonempty diagnostic reason')
    for key in ['out', 'report', 'proof', 'package', 'assets', 'tree']:
        value = getattr(args, key, None)
        if value:
            setattr(args, key, cli_path(value))
    if args.command == 'build' and args.target == 'main':
        return build_main(args)
    if args.command == 'build':
        if args.keep_intermediates is not None:
            raise ZaError('--keep-intermediates is currently supported only by build main and reproduce')
        script = REPO / 'port/ui-v2/tools/build-r29-ui.py'
        if not script.is_file():
            raise ZaError('r29-ui builder is not present; no build started')
        argv = [sys.executable, str(script), '--out', args.out]
        for key in ['package', 'assets', 'tree']:
            value = getattr(args, key)
            if value:
                argv.extend(['--' + key, value])
        # The builder owns HANDOFF, source controls, host/PS5 tests and packaging gates.
        # Preserve its return code and output; do not turn a failed/deferred build into success.
        return subprocess.call(argv, cwd=REPO)
    lock = read_lock()
    if args.command == 'profiles':
        result = {'method': lock['method'], 'profiles': {
            name: {'description': p['description'], 'eboot_sha256':
                   lock['files'][p['references']['eboot']]['sha256'], 'full_source_rebuild': False}
            for name, p in lock['profiles'].items()}, 'installed_variant_covered': False}
    elif args.command in ['verify', 'doctor']:
        names = selection(lock, args.profile)
        result = {'command': args.command, 'profiles': names, 'checked_utc': utc(),
                  **check_files(lock, names, inputs=args.command == 'doctor')}
        if args.command == 'doctor':
            result['reproduction_method'] = lock['method']
            result['full_source_rebuild'] = False
            result['full_source_reason'] = 'Frozen runtime/game objects are inputs; translated AOT sources are not rebuilt.'
        if args.report:
            atomic_json(args.report, result)
    elif args.command == 'check-proof':
        result = check_proof(lock, args.proof)
    else:
        result = reproduce(lock, selection(lock, args.profile), args.out,
                           keep_intermediates=args.keep_intermediates)
        if result is None:
            return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('ok', result.get('status', 'passed') == 'passed') else 2


def windows_forward():
    script = '/mnt/' + str(Path(__file__).resolve()).replace('\\', '/')[0].lower() + str(Path(__file__).resolve()).replace('\\', '/')[2:]
    args = []
    for a in sys.argv[1:]:
        if len(a) >= 3 and a[1] == ':' and a[2] in '\\/':
            a = '/mnt/' + a[0].lower() + a[2:].replace('\\', '/')
        args.append(a)
    return subprocess.call(['wsl', '-d', 'Ubuntu', '--', 'python3', script, *args])


if __name__ == '__main__':
    try:
        sys.exit(windows_forward() if os.name == 'nt' else dispatch())
    except (ZaError, OSError, ValueError) as exc:
        print('za: ' + str(exc), file=sys.stderr)
        sys.exit(2)

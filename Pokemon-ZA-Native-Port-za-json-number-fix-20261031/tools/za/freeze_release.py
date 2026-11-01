#!/usr/bin/env python3
"""Maintainer-only: freeze ONE released build as a za release profile (e.g. main-1.0.0).

Copies every link input of an already-built, hash-identified release into a NEW frozen folder under
/home/tomer/ps5-za-native, then writes tools/za/releases/<name>.lock.json. Never overwrites a lock or folder.
The base profiles.lock.json is not touched, so earlier proofs stay valid.

  python3 tools/za/freeze_release.py --name main-1.0.0 --tree /home/tomer/ps5-za-native/r29ui-codex-20261031-final-01 \
     --link-log evidence/build-resume-link.log --extra evidence/link-inputs.txt --program program \
     --eboot-sha 51b7e65b... --pie-sha bf206bf4... --delivered '{repo}/artifacts/randomizer-r29-ui-codex-20261031-01/eboot.bin' \
     --frozen /home/tomer/ps5-za-native/za-main-1.0.0-frozen-20261031 --description '...' [--package-sums PATH]
--link-log is a build log whose link-title.sh command line is a Python list (port/ui-v2 builders write that form).
"""
import argparse
import ast
import json
from pathlib import Path
import shlex
import shutil
import subprocess

import za


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for a in ['name', 'tree', 'link-log', 'extra', 'program', 'eboot-sha', 'pie-sha', 'delivered', 'frozen', 'description']:
        ap.add_argument('--' + a, required=True)
    ap.add_argument('--package-sums', help='package SHA256SUMS.json to pin (data side of the release)')
    ap.add_argument('--release-json', help='extra release metadata (JSON file) stored verbatim in the lock')
    args = ap.parse_args()
    base = za.read_lock()
    if args.name in base['profiles']:
        raise za.ZaError('profile exists: ' + args.name)
    lock_path = za.RELEASES / (args.name + '.lock.json')
    if lock_path.exists():
        raise za.ZaError('lock exists; a release is frozen once: ' + str(lock_path))
    tree = Path(args.tree)
    log = (tree / args.link_log).read_text(encoding='utf-8').splitlines()
    cmd = [ast.literal_eval(l[2:]) for l in log if l.startswith('$ [') and 'link-title.sh' in l]
    if len(cmd) != 1:
        raise za.ZaError('expected exactly one link-title.sh command in the log')
    cmd = cmd[0]
    runtime, archive = [Path(p) for p in cmd[3:-1]], Path(cmd[-1])
    extra = shlex.split((tree / args.extra).read_text(encoding='utf-8'))
    program = tree / args.program
    refs = {'pie': program / 'llvm-pie.elf', 'eboot': program / 'eboot.bin'}
    for key, want in [('pie', args.pie_sha), ('eboot', args.eboot_sha)]:
        if za.sha(refs[key]) != want:
            raise za.ZaError('reference differs from the released SHA-256: ' + key)
    delivered = Path(za.expand(args.delivered))
    if za.sha(delivered) != args.eboot_sha:
        raise za.ZaError('delivered eboot differs')

    frozen = Path(args.frozen)
    frozen.mkdir(parents=True, exist_ok=False)
    data = dict(schema=za.SCHEMA, created_utc=za.utc(), method=base['method'], full_source_rebuild=False,
                vulkan=base['vulkan'], sdk=base['sdk'], radv_archive=base['radv_archive'],
                profiles={}, files={}, shared=list(base['shared']),
                sdk_shared_libraries=list(base['sdk_shared_libraries']))

    def pin(path):
        path = Path(path)
        token = za.tokenize(path)
        if token not in data['files']:
            data['files'][token] = dict(size=path.stat().st_size, sha256=za.sha(path))
        return token

    for token in data['shared']:   # same toolchain as the historical profiles; refuse silent drift
        if pin(za.expand(token)) and data['files'][token] != base['files'][token]:
            raise za.ZaError('shared toolchain file changed since the base lock: ' + token)

    def freeze(src, dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['cp', '--reflink=auto', '--preserve=mode', str(src), str(dst)], check=True)
        if za.sha(src) != za.sha(dst):
            raise za.ZaError('copy differs: ' + str(src))
        return dst

    src_root = Path(str(runtime[0]).split('/build/ps5/rt/')[0])
    f_runtime = [freeze(p, frozen / 'source' / p.relative_to(src_root)) for p in runtime]
    f_archive = freeze(archive, frozen / 'archive' / archive.name)
    f_extra, n = [], 0
    for tok in extra:
        if tok.startswith('/'):
            f_extra.append(str(freeze(Path(tok), frozen / 'extra' / f'{n:03d}-{Path(tok).name}')))
            n += 1
        else:
            f_extra.append(tok)
    (frozen / 'extra-inputs.txt').write_text(shlex.join(f_extra) + '\n', encoding='utf-8')
    link = frozen / 'ps5-link'
    for f in ['app_crt.o', 'app_cpp_runtime.o', 'stubs/libSceAgc.so', 'stubs/libSceAgcDriver.so']:
        freeze(program / 'ps5-link' / f, link / f)
    f_refs = {k: freeze(v, frozen / 'reference' / v.name) for k, v in refs.items()}
    shutil.copyfile(tree / args.link_log, frozen / 'source-link-command.log')

    inputs = [*f_runtime, f_archive, *[Path(t) for t in f_extra if t.startswith('/')],
              *[link / f for f in ['app_crt.o', 'app_cpp_runtime.o', 'stubs/libSceAgc.so', 'stubs/libSceAgcDriver.so']],
              delivered]
    profile = dict(description=args.description, tree=za.tokenize(frozen), archive=za.tokenize(f_archive),
                   runtime=[za.tokenize(p) for p in f_runtime], extra=[za.tokenize(t) for t in f_extra],
                   references={k: pin(v) for k, v in f_refs.items()}, delivered_eboot=pin(delivered),
                   frozen_link=za.tokenize(link), inputs=list(dict.fromkeys(pin(p) for p in inputs)),
                   frozen_from=za.tokenize(tree))
    if args.package_sums:
        profile['package_sums'] = pin(za.expand(args.package_sums))
    if args.release_json:
        profile['release'] = json.loads(Path(args.release_json).read_text(encoding='utf-8'))
    data['profiles'][args.name] = profile
    za.atomic_json(lock_path, data)
    print(f'froze {args.name}: {len(profile["inputs"])} inputs in {frozen}; lock {lock_path}')


if __name__ == '__main__':
    main()

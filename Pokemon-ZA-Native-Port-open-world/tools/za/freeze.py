#!/usr/bin/env python3
"""Maintainer-only: pin the independently identified historical release inputs once.

This is intentionally separate from za: normal commands never change their trust roots.
Refuses to replace an existing lock. Review all changes if a future release is added.
"""
import json
from pathlib import Path
import shlex
import subprocess

import za

ROOT = za.NATIVE
VULKAN = ROOT / 'PS5_Vulkan'
SDK = VULKAN / '.deps/native/ps5-payload-sdk'

SPECS = {
    'r27b': dict(tree='r27b-play-20261029', directory='source/build/ps5/title',
                 archive='money-r27/liblasgame-r27.a', eboot='package/eboot.bin',
                 eboot_sha='c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153',
                 pie_sha='4e92c0ef09ba948deef36a4cf144a42532705763ef15d7e2a8ab2b41d4338d95',
                 description='Original r27b-play, NAME + MONEY; excludes later Hebrew Trial'),
    'r28': dict(tree='r28-play-20261030', directory='r28', archive='r28/liblasgame-r28.a',
                eboot='r28/eboot.bin',
                eboot_sha='65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568',
                pie_sha='0570bec994a7cbe9512dacb4a6fa8e3bc0340ef3570dd73edf346772928d8288',
                description='r28-play, ITEMS + preserved Hebrew Trial'),
    'r28a': dict(tree='r28a-play-final-20261030', directory='r28a',
                 archive='rando-dexcount/liblasgame-r28-dexcount.a', eboot='r28a/eboot.bin',
                 eboot_sha='5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea',
                 pie_sha='4cb7c2127f12f5f3aa700cb3301c21f6b1c214d464bac4449f43af56685eea85',
                 description='Final r28a-play, texfix + DLC dex count; excludes texfix-only candidate'),
    'r28b': dict(tree='r28b-play-20261030', directory='r28b',
                 archive='rando-dexopen/liblasgame-r28-dexopen.a', eboot='r28b/eboot.bin',
                 eboot_sha='ffd2cf18fc513ec4400d949325a5db2771336adb479b71026c7063280dd6aa26',
                 pie_sha='381c89d0dc33a20c37285ba3314c36f1d04aadffb268400bedc61edfa5e8ab51',
                 description='Historical r28b-play, dexopen readers; excludes installed r28b-dlc-dex-music')
}


def main():
    if za.LOCK.exists():
        raise za.ZaError('Lock exists; review a new explicit version instead of rebaselining')
    data = dict(schema=za.SCHEMA, created_utc=za.utc(), method='relink-frozen-objects-and-convert-sign',
                full_source_rebuild=False, vulkan=za.tokenize(VULKAN), sdk=za.tokenize(SDK),
                radv_archive=za.tokenize(VULKAN / '.deps/native/radv-release/lib/libvulkan_radeon.ps5.a'),
                profiles={}, files={}, shared=[], sdk_shared_libraries=[])

    def pin(path):
        path = Path(path)
        token = za.tokenize(path)
        if token not in data['files']:
            data['files'][token] = dict(size=path.stat().st_size, sha256=za.sha(path))
        return token

    shared = [VULKAN / 'tools/radv-link.sh', VULKAN / 'tooling/native/app-symbols.map',
              VULKAN / 'tooling/psbc/ps5-pie-unwind.ld', VULKAN / 'build/host/ps5-native-tool',
              SDK / 'bin/prospero-lld', SDK / 'bin/llvm-nm', SDK / 'bin/llvm-strip',
              VULKAN / '.deps/native/radv-release/lib/libvulkan_radeon.ps5.a',
              SDK / 'target/lib/libc++.a', SDK / 'target/lib/libc++abi.a',
              SDK / 'target/lib/libunwind.a', SDK / 'target/lib/libps5platform.a',
              Path('/usr/bin/clang-21'),
              Path('/usr/lib/llvm-21/lib/clang/21/lib/linux/libclang_rt.builtins-x86_64.a')]
    for path in sorted((SDK / 'target/lib').glob('*.so')):
        data['sdk_shared_libraries'].append(pin(path))
        shared.append(path)
    data['shared'] = list(dict.fromkeys(pin(p) for p in shared))
    for name, s in SPECS.items():
        print('pinning ' + name, flush=True)
        tree = ROOT / s['tree']
        out = tree / s['directory']
        if name == 'r27b':
            recipe = ('include offline-title.mk\n.PHONY: za-list\nza-list:\n'
                      "\t@printf '%s\\n' $(TITLE_OBJS)\n")
            result = subprocess.run(['make', '-s', '-f', '-', 'PLATFORM=ps5', 'za-list'],
                                    cwd=tree / 'source', input=recipe, text=True,
                                    capture_output=True, check=True)
            runtime = [tree / 'source' / f for f in result.stdout.splitlines() if f.strip()]
            extra_file = za.REPO / 'evidence/perf-r27b/link-inputs.txt'
        else:
            runtime = [tree / 'source' / f for f in (out / 'evidence/runtime-inputs.txt').read_text().splitlines() if f.strip()]
            extra_file = out / 'evidence/link-inputs.txt'
        extra = shlex.split(extra_file.read_text())
        references = dict(pie=pin(out / 'llvm-pie.elf'), eboot=pin(tree / s['eboot']))
        for key in ['eboot', 'pie']:
            if data['files'][references[key]]['sha256'] != s[key + '_sha']:
                raise za.ZaError(name + ' reference does not match published historical SHA-256: ' + key)
        # Also pin the separately delivered release eboot, so a source-tree reference is
        # not the only trust root. No archive/data/saves enter this lock, just hashes.
        delivered = za.REPO / ('artifacts/randomizer-' + name + '-play/PPSA91762/eboot.bin')
        delivered_token = pin(delivered)
        if data['files'][delivered_token]['sha256'] != s['eboot_sha']:
            raise za.ZaError(name + ' delivered eboot disagrees')
        frozen = out / 'ps5-link'
        inputs = [*runtime, tree / s['archive'], extra_file, delivered]
        inputs += [Path(f) for f in extra if f.startswith('/')]
        inputs += [frozen / f for f in ['app_crt.o', 'app_cpp_runtime.o',
                                      'stubs/libSceAgc.so', 'stubs/libSceAgcDriver.so']]
        data['profiles'][name] = dict(description=s['description'], tree=za.tokenize(tree),
                                     archive=za.tokenize(tree / s['archive']),
                                     runtime=[za.tokenize(f) for f in runtime],
                                     extra=[za.tokenize(f) for f in extra],
                                     references=references, delivered_eboot=delivered_token,
                                     frozen_link=za.tokenize(frozen),
                                     inputs=list(dict.fromkeys(pin(f) for f in inputs)))
    za.atomic_json(za.LOCK, data)
    print(f'Pinned {len(data["files"])} unique files in {za.LOCK}')


if __name__ == '__main__':
    main()

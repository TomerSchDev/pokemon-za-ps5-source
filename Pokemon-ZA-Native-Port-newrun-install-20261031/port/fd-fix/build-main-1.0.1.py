#!/usr/bin/env python3
"""main-1.0.1 = main-1.0.0 (r29-ui, eboot 51b7e65b) + the RomFS overlay-fd fix.  WSL only, offline, no console.

  python3 port/fd-fix/build-main-1.0.1.py --out /home/tomer/ps5-za-native/main-1.0.1-build-NEW \
      --main-tar MAIN.tar --fix-tar FIX.tar --fix-commit <runtime fd-fix commit>

MAIN.tar / FIX.tar are `git archive` of runtime pokeza-recomp-ps5 `main` (1655be8, = r29-ui's runtime tree) and of
branch `fd-fix` (main + 57e3b9d/ae5e0bd/5c33e64 cherry-picked; kernel.c keeps r24's klock_take, as in the hardware-run
r28b-dlc-dex-fd-20261031-r1 tree). `git get-tar-commit-id` must name the expected commits.

Steps (every one must pass, nothing is repinned):
  1. za doctor main-1.0.0, then za reproduce main-1.0.0 -> PIE bf206bf4 + eboot 51b7e65b byte for byte (control A).
  2. Both trees get the runtime recipe's header dirs (port/sdl3-shim, port/shaderc-cache, inc) from
     runtime-main-proof-20261031-01; the source diff main..fix must be exactly ipc.c ipc.h kernel.c services/fs.c (+tools/).
  3. Control B: ipc / kernel / services/fs compiled from MAIN rebuild the frozen 1.0.0 objects byte for byte.
  4. Every plain runtime unit compiled from FIX (compile-runtime-object.sh): only ipc, kernel, services/fs may differ
     from the frozen objects (nvn/cmdbuf, nvn/texpatch: machine code equal, the known DWARF-only nvn.h difference;
     the 6 other ipc.h includers: machine code equal, DWARF-only).
     gamelib / gamebuild / nvn/smaa_data / nvn/vulkan/vma need Makefile-only flags: their dependency lists (-MM) must
     not contain a changed file.
  5. Control C: link-title.sh over the unchanged frozen inputs reproduces the 1.0.0 PIE and, signed, the 1.0.0 eboot.
  6. Release link: the same command with ONLY the 3 objects replaced; registration + image verifiers; no base symbol lost.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
NATIVE = Path('/home/tomer/ps5-za-native')
FROZEN = NATIVE / 'za-main-1.0.0-frozen-20261031'
HEADERS = NATIVE / 'runtime-main-proof-20261031-01'      # port/sdl3-shim/include, port/shaderc-cache/include, inc
MAIN_COMMIT = '1655be892b1dbacf1b4c65aca12d621703ca3c24'
BASE_PIE = 'bf206bf4d7fdc30de9e8f9565c0c058b7de0c6cb547416a0a81bdade30dc7a99'
BASE_EBOOT = '51b7e65b0bd930bfe7ede0127d56736ee43d8487310ebff6337c92e11b3e1ab1'
CHANGED = ['ipc', 'kernel', 'services/fs']
CHANGED_SOURCES = {'runtime/ipc.c', 'runtime/ipc.h', 'runtime/kernel.c', 'runtime/services/fs.c'}
DEBUG_ONLY = {'nvn/cmdbuf', 'nvn/texpatch'}       # runtime-main-proof: compiled against the pre-r28a nvn.h
# units that include the changed ipc.h: their machine code must be identical (DWARF records the header's new lines and
# KSession field); the release keeps their frozen objects, exactly as the hardware-run fd build did
IPC_H_DWARF = {'services/acc', 'services/am', 'services/audio', 'services/hid_set', 'services/misc', 'services/time'}
SPECIAL = {'gamelib', 'gamebuild', 'nvn/smaa_data', 'nvn/vulkan/vma'}
VULKAN = NATIVE / 'PS5_Vulkan'
SDK = VULKAN / '.deps/native/ps5-payload-sdk'
CLANG = '/usr/bin/clang-21'
NM = '/usr/lib/llvm-21/bin/llvm-nm'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True)
    ap.add_argument('--main-tar', required=True)
    ap.add_argument('--fix-tar', required=True)
    ap.add_argument('--fix-commit', required=True)
    ap.add_argument('--za-repo', default='/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port')
    a = ap.parse_args()
    out = Path(a.out)
    if not str(out).startswith(str(NATIVE) + '/') or out.exists():
        sys.exit('--out must be a NEW folder under ' + str(NATIVE))
    out.mkdir(parents=True)
    ev = out / 'evidence'
    ev.mkdir()
    log = (ev / 'build.log').open('x', encoding='utf-8')
    result = {'release': 'main-1.0.1', 'base': 'main-1.0.0', 'base_eboot_sha256': BASE_EBOOT,
              'runtime_main_commit': MAIN_COMMIT, 'runtime_fix_commit': a.fix_commit, 'console_access': False}

    def run(cmd, cwd=None, env=None, capture=None, check=True):
        cmd = list(map(str, cmd))
        log.write('\n$ ' + repr(cmd) + '\n')
        log.flush()
        r = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        log.write(r.stdout)
        log.flush()
        if capture:
            Path(capture).write_text(r.stdout, encoding='utf-8')
        if check and r.returncode:
            raise SystemExit(f'FAILED ({r.returncode}): {cmd[:3]}... see {ev / "build.log"}')
        return r

    def step(msg):
        print('== ' + msg, flush=True)
        log.write('\n== ' + msg + '\n')

    # za runs where the released package lives ({repo}/artifacts is not in git): the shared working tree by default.
    za = Path(a.za_repo) / 'tools/za/za.py'
    assert sha(za) == sha(PROJECT / 'tools/za/za.py'), 'za.py of --za-repo differs from this checkout'
    step('1. control A: za doctor + za reproduce main-1.0.0')
    run([sys.executable, za, 'doctor', 'main-1.0.0'], capture=ev / 'za-doctor.json')
    run([sys.executable, za, 'reproduce', 'main-1.0.0', '--out', out / 'control-za'], capture=ev / 'za-reproduce.json')
    proof = json.loads((out / 'control-za/main-1.0.0/proof.json').read_text())
    assert proof['status'] == 'passed' and proof['outputs']['eboot']['actual_sha256'] == BASE_EBOOT, proof
    result['control_za_reproduce'] = {'status': 'passed', 'eboot_sha256': BASE_EBOOT, 'pie_sha256': BASE_PIE}

    step('2. source trees')
    (out / 'inputs').mkdir()
    for t in (a.main_tar, a.fix_tar):
        shutil.copyfile(t, out / 'inputs' / Path(t).name)
    a.main_tar, a.fix_tar = out / 'inputs' / Path(a.main_tar).name, out / 'inputs' / Path(a.fix_tar).name
    for tar, want in [(a.main_tar, MAIN_COMMIT), (a.fix_tar, a.fix_commit)]:
        got = subprocess.run(['git', 'get-tar-commit-id'], stdin=open(tar, 'rb'), capture_output=True, text=True).stdout.strip()
        assert got == want, (tar, got, want)
    trees = {}
    for name, tar in [('main', a.main_tar), ('fix', a.fix_tar)]:
        w = out / ('work-' + name)
        (w / 'source').mkdir(parents=True)
        run(['tar', '-xf', tar, '-C', w / 'source'])
        for d in ['port', 'inc']:
            run(['cp', '-a', HEADERS / d, w / d])
        trees[name] = w
    r = run(['diff', '-rq', trees['main'] / 'source', trees['fix'] / 'source'], check=False)
    diffs = sorted(l.split()[1].split('/source/', 1)[1] if l.startswith('Files') else l for l in r.stdout.splitlines())
    runtime_diffs = {d for d in diffs if not d.startswith('Only in') and d.startswith('runtime/')}
    assert runtime_diffs == CHANGED_SOURCES, diffs
    result['source_diff_main_to_fix'] = diffs
    result['tar_sha256'] = {'main': sha(a.main_tar), 'fix': sha(a.fix_tar)}

    rt = FROZEN / 'source/build/ps5/rt'
    # the link order of main-1.0.0's lock (link order changes the image; sorted order would not reproduce it)
    lock = json.loads((PROJECT / 'tools/za/releases/main-1.0.0.lock.json').read_text(encoding='utf-8'))
    units = [t.replace('{native}', str(NATIVE)).split('/build/ps5/rt/')[1][:-2] for t in lock['profiles']['main-1.0.0']['runtime']]
    assert len(units) == 64 and sorted(units) == sorted(str(p.relative_to(rt))[:-2] for p in rt.rglob('*.o')), units
    compile_sh = PROJECT / 'port/ui-v2/tools/compile-runtime-object.sh'

    step('3. control B: the changed units from MAIN rebuild the frozen objects')
    control = {}
    for u in CHANGED:
        o = out / 'compiled-main' / (u + '.o')
        run(['bash', compile_sh, trees['main'], u, o])
        control[u] = {'sha256': sha(o), 'frozen_sha256': sha(rt / (u + '.o')), 'identical': sha(o) == sha(rt / (u + '.o'))}
        assert control[u]['identical'], (u, control[u])
    result['control_main_units'] = control

    step('4. every plain unit from FIX vs the frozen objects')
    per = {}
    strip = SDK / 'bin/llvm-objcopy'
    for u in units:
        if u in SPECIAL:
            continue
        o = out / 'compiled-fix' / (u + '.o')
        run(['bash', compile_sh, trees['fix'], u, o])
        if sha(o) == sha(rt / (u + '.o')):
            per[u] = 'identical'
        else:
            a1, b1 = out / 'tmp-a.o', out / 'tmp-b.o'
            run([strip, '--strip-debug', o, a1])
            run([strip, '--strip-debug', rt / (u + '.o'), b1])
            per[u] = 'machine-code-identical-dwarf-differs' if sha(a1) == sha(b1) else 'different'
            a1.unlink()
            b1.unlink()
    changed = sorted(u for u, s in per.items() if s == 'different')
    dbg = sorted(u for u, s in per.items() if s == 'machine-code-identical-dwarf-differs')
    assert changed == sorted(CHANGED), changed
    assert set(dbg) <= DEBUG_ONLY | IPC_H_DWARF, dbg
    deps = {}
    for u in sorted(SPECIAL):
        src = trees['fix'] / 'source/runtime' / (u + ('.cpp' if u.endswith('vma') else '.c'))
        cmd = [CLANG, '-target', 'x86_64-sie-ps5', '-isysroot', SDK, '-isystem', SDK / 'target/include/c++/v1',
               '-isystem', SDK / 'target/include', '-MM', '-Iruntime', '-Iruntime/nvn', '-I' + str(NATIVE / 'PS5_Mesa/include'),
               '-I' + str(trees['fix'] / 'port/sdl3-shim/include'), '-I' + str(trees['fix'] / 'port/shaderc-cache/include'),
               '-I' + str(trees['fix'] / 'inc'), '-I' + str(trees['fix'] / 'inc/vma'), '-Ithird_party/ps5-stubs/include',
               '-Ithird_party/smaa/Textures', '-Ibuild/ps5/inc', '-DZA_PS5', '-DLARECOMP_STATIC_GAMELIB',
               '-DGAMELIB_ID="x"', '-DGAMELIB_CFLAGS="x"', '-DGAMELIB_SHARED=""', '-MG', src]
        r = run(cmd, cwd=trees['fix'] / 'source', check=False)
        text = r.stdout.replace('\\\n', ' ')
        hit = sorted(c for c in CHANGED_SOURCES if c in text)
        deps[u] = {'mm_exit': r.returncode, 'depends_on_changed': hit}
        assert r.returncode == 0 and not hit, (u, deps[u])
    result['fix_units'] = {'compiled': len(per), 'identical': sum(s == 'identical' for s in per.values()),
                           'dwarf_only': dbg, 'changed': changed, 'special_dependency_check': deps,
                           'per_unit': per}

    step('5. release tree: 61 frozen objects + 3 rebuilt')
    rel = out / 'release/source/build/ps5/rt'
    for u in units:
        dst = rel / (u + '.o')
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = out / 'compiled-fix' / (u + '.o') if u in CHANGED else rt / (u + '.o')
        run(['cp', '--reflink=auto', src, dst])
    shutil.copytree(trees['fix'] / 'source/tools', out / 'release/source/tools')
    same = [u for u in units if u not in CHANGED and sha(rel / (u + '.o')) == sha(rt / (u + '.o'))]
    assert len(same) == 61, len(same)
    result['runtime_objects'] = {'unchanged_byte_identical': 61,
                                 'replaced': {u: {'old': sha(rt / (u + '.o')), 'new': sha(rel / (u + '.o'))} for u in CHANGED}}

    facade = out / 'vulkan-facade'
    facade.mkdir()
    for sub in ('tooling', '.deps', 'vendor'):
        (facade / sub).symlink_to(VULKAN / sub, target_is_directory=True)
    (facade / 'tools').mkdir()
    shutil.copy2(VULKAN / 'tools/radv-link.sh', facade / 'tools/radv-link.sh')
    extra_text = (FROZEN / 'extra-inputs.txt').read_text(encoding='utf-8')
    env = {**os.environ, 'ZA_PS5_EXTRA_INPUTS': extra_text.strip(), 'PS5_VULKAN': str(facade),
           'PS5_PAYLOAD_SDK': str(SDK), 'PS5_CLANG': CLANG}
    tool = VULKAN / 'build/host/ps5-native-tool'

    def link_and_sign(program, runtime, name):
        program.mkdir()
        pie = program / 'llvm-pie.elf'
        run(['bash', out / 'release/source/tools/ps5/link-title.sh', pie, *runtime, FROZEN / 'archive/liblasgame-base.a'],
            cwd=out / 'release/source', env=env)
        run([SDK / 'bin/llvm-strip', '--strip-debug', '-o', program / 'title-stripped.elf', pie])
        stubs = program / 'ps5-link/stubs'
        run([tool, 'link', '--in', program / 'title-stripped.elf', '--out', program / 'eboot.elf', '--stub-dir',
             SDK / 'target/lib', '--stub', stubs / 'libSceAgc.so', '--stub', stubs / 'libSceAgcDriver.so',
             '--module-sdk', '0x02000009', '--companion-sdk', '0x08050001', '--file-name', 'eboot.elf'])
        run([tool, 'self', '--sign', '--in', program / 'eboot.elf', '--out', program / 'eboot.bin', '--magic', '0x1D3D154F'])
        run([tool, 'self', '--inspect', '--file', program / 'eboot.bin'], capture=ev / f'self-inspection-{name}.txt')
        return sha(pie), sha(program / 'eboot.bin')

    step('6. control C: link-title.sh over the unchanged frozen inputs')
    frozen_rt = [rt / (u + '.o') for u in units]
    cp, ce = link_and_sign(out / 'control-link', frozen_rt, 'control')
    assert (cp, ce) == (BASE_PIE, BASE_EBOOT), (cp, ce)
    result['control_link_title'] = {'pie_sha256': cp, 'eboot_sha256': ce, 'reproduces_1_0_0': True}

    step('7. release link (only ipc.o, kernel.o, services/fs.o differ)')
    (ev / 'link-inputs.txt').write_text(extra_text, encoding='utf-8')
    pie_sha, eboot_sha = link_and_sign(out / 'program', [rel / (u + '.o') for u in units], 'release')
    program = out / 'program'
    run([sys.executable, PROJECT / 'port/local-shader-r19/verify-registration.py', FROZEN / 'reference/llvm-pie.elf',
         program / 'llvm-pie.elf'], capture=ev / 'registration.json')
    run([NM, '--defined-only', program / 'llvm-pie.elf'], capture=ev / 'defined-symbols.txt')
    run([sys.executable, PROJECT / 'port/title/verify-image.py', program / 'title-stripped.elf', program / 'eboot.elf',
         ev / 'defined-symbols.txt'], capture=ev / 'image-preservation.json')
    base_syms = set(l.split()[-1] for l in run([NM, '--defined-only', FROZEN / 'reference/llvm-pie.elf']).stdout.splitlines() if l.strip())
    new_syms = set(l.split()[-1] for l in (ev / 'defined-symbols.txt').read_text().splitlines() if l.strip())
    lost, added = sorted(base_syms - new_syms), sorted(new_syms - base_syms)
    (ev / 'symbols-lost.txt').write_text('\n'.join(lost) + '\n')
    (ev / 'symbols-added.txt').write_text('\n'.join(added) + '\n')
    # Allowed: only names the OLD ipc.o / kernel.o / services/fs.o defined and the rebuilt ones do not - the __LINE__-
    # numbered registration entries (reset_entry_N, svc_def_N: renumbered, the 'resets'/'services' sections keep their
    # byte counts, see registration.json) and statics the compiler now inlines (session_new). Nothing else may go.
    def defs(o):
        return set(l.split()[-1] for l in run([NM, '--defined-only', o]).stdout.splitlines() if l.strip())
    old3 = set().union(*[defs(rt / (u + '.o')) for u in CHANGED])
    new3 = set().union(*[defs(rel / (u + '.o')) for u in CHANGED])
    unexpected = sorted(set(lost) - (old3 - new3))
    assert not unexpected, unexpected[:10]
    reg = json.loads((ev / 'registration.json').read_text())
    assert all(r['preserved_count'] for r in reg), reg
    assert 'ipc_close_session' in new_syms and 'ipc_close_session' not in base_syms
    result.update(pie_sha256=pie_sha, eboot_sha256=eboot_sha, eboot_size=(program / 'eboot.bin').stat().st_size,
                  symbols={'base': len(base_syms), 'release': len(new_syms), 'lost_only_from_changed_objects': lost, 'added': added},
                  hardware_tested=False)
    sums = [f'{sha(p)}  {p.relative_to(out)}' for p in [program / 'eboot.bin', program / 'llvm-pie.elf',
            *[rel / (u + '.o') for u in CHANGED], Path(a.main_tar), Path(a.fix_tar)] if p.exists()]
    (ev / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n')
    (ev / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('eboot_sha256', 'pie_sha256', 'eboot_size', 'symbols')}, indent=2))
    print('main-1.0.1 candidate built and statically verified offline; no console test')


if __name__ == '__main__':
    main()

"""Build the game DLL with the v0.1.3 recipe, limiting concurrent compilers.

Uses the official release generator/compiler; verifies shipped headers against
the pinned source tag and that the derived ABI ID is present in the runtime.
Logs and intermediates are retained for diagnosis. Never reads key files.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import re
from collections import Counter

REVISION = 'cf910d1315fff0ead7d782c9d752a075a9b777f7'
ID_FILES = '''tools/gen.py tools/lifter.py tools/analyze.py tools/nso.py tools/passes.py
tools/patches.py tools/simd_c.py tools/rando/patch_variants.json tools/gamelib_entry.c
runtime/hle/hle_symbols.txt runtime/cpu.h runtime/simd.h runtime/simd_fp.h runtime/gamelib.h'''.split()
GENFLAGS = '-O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label -fvisibility=hidden -Iruntime -D_FILE_OFFSET_BITS=64 -march=x86-64-v3'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--release', required=True, type=Path)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--game', required=True, type=Path)
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--generator-python', type=Path, help='Run the pinned original sources with UTF-8 enabled')
    p.add_argument('--upstream-giants', action='store_true', help='Use v0.1.4 cold-giant O0 policy; retain existing O1 objects')
    a = p.parse_args()
    if not 1 <= a.jobs <= 16:
        p.error('use 1..16 compiler jobs')
    release, repo, game, work = [x.resolve() for x in (a.release, a.repo, a.game, a.work)]
    work.mkdir(parents=True, exist_ok=True)
    sources = {n: subprocess.check_output(['git', '-C', str(repo), 'show', REVISION + ':' + n]) for n in ID_FILES}
    ident = hashlib.sha256(b''.join(sources.values()) + (GENFLAGS + '\n').encode()).hexdigest()[:16]
    if ident.encode() not in (release / 'lasrecomp.exe').read_bytes():
        raise RuntimeError('source/flags do not match the released runtime ABI')
    for name in ID_FILES[8:]:
        if (release / 'gamelib-src' / Path(name).name).read_bytes() != sources[name]:
            raise RuntimeError('shipped source differs: ' + name)
    manifest = dict(revision=REVISION, abi_id=ident, jobs=a.jobs, flags=GENFLAGS,
                    debug_info=False, started_utc=datetime.now(timezone.utc).isoformat(),
                    nsos={n: digest(game / 'exefs' / n) for n in ('main', 'sdk')})
    signature = json.dumps({k: v for k, v in manifest.items() if k not in ('started_utc', 'jobs')}, sort_keys=True)
    stamp = work / 'inputs.json'
    if stamp.exists() and stamp.read_text() != signature:
        raise RuntimeError('work folder belongs to a different build; choose a new folder')
    stamp.write_text(signature)
    env = os.environ.copy()
    env.update(ZIG_GLOBAL_CACHE_DIR=str(work / 'zig-cache'), ZIG_LOCAL_CACHE_DIR=str(work / 'zig-cache'),
               PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    generator = release / 'lasgen/lasgen.exe'
    generator_cmd = [str(generator)]
    if a.generator_python:
        for name, data in sources.items():
            target_source = work / 'source' / name
            target_source.parent.mkdir(parents=True, exist_ok=True)
            target_source.write_bytes(data)
        generator_cmd = [str(a.generator_python.resolve()), '-u', '-X', 'utf8',
                         str(work / 'source/tools/gen.py')]
    zig = release / 'zig/zig.exe'
    for module, base in [('main', '0x7000000000'), ('sdk', '0x7008000000')]:
        marker = work / (module + '.generated')
        if marker.exists():
            continue
        cmd = [*generator_cmd, module, str(game / 'exefs' / module), base, str(work / module)]
        if module == 'sdk':
            cmd += ['--hle', str(release / 'gamelib-src/hle_symbols.txt')]
        print('Generating ' + module, flush=True)
        with (work / ('gen_' + module + '.log')).open('wb') as log:
            subprocess.run(cmd, cwd=work, env=env, stdout=log, stderr=log, check=True, timeout=1800)
        marker.write_text(signature)
    units = sorted([*work.glob('main/*.c'), *work.glob('sdk/*.c')], key=lambda f: f.stat().st_size, reverse=True)
    units += [release / 'gamelib-src/gamelib_entry.c']
    (work / 'obj').mkdir(exist_ok=True)
    (work / 'logs').mkdir(exist_ok=True)
    flags = [f for f in GENFLAGS.split() if f != '-Iruntime']
    flags = ['-mcpu=x86_64_v3' if f == '-march=x86-64-v3' else f for f in flags]
    # No debug data, same as the subsequent upstream gamebuild change; no change to optimisation level.
    flags += ['-g0', '-I' + str(release / 'gamelib-src'), '-DGAMELIB_ID="' + ident + '"']
    policy_revision = '4d82d8998adb75036c27f476e8d8f7e737bed36a'
    policy_source = subprocess.check_output(['git', '-C', str(repo), 'show', policy_revision + ':runtime/gamebuild.c']).decode()
    hot_block = policy_source.split('HOT_GIANTS[] = {', 1)[1].split('};', 1)[0]
    hot_giants = set(re.findall(r'"(f_[0-9a-f]+)"', hot_block))

    def compile_one(src):
        obj = work / 'obj' / (src.stem + '.o')
        ok = obj.with_suffix('.ok')
        opt_file = obj.with_suffix('.opt')
        sig = hashlib.sha256((digest(src) + signature).encode()).hexdigest()
        old_opt = opt_file.read_text() if opt_file.exists() else 'O1'
        if obj.exists() and ok.exists() and ok.read_text() == sig and (a.upstream_giants or old_opt == 'O1'):
            return obj, old_opt
        unit_flags = list(flags)
        opt = 'O1'
        if a.upstream_giants:
            code = src.read_text(encoding='utf-8')
            defs = re.findall(r'^void (f_[0-9a-f]+)\(Cpu \*c\) \{', code, re.M)
            if len(defs) == 1 and defs[0] not in hot_giants and len(re.findall(r'^L_', code, re.M)) > 1000:
                opt = 'O0'
                unit_flags = ['-O0' if f == '-O1' else f for f in unit_flags]
                unit_flags += ['-fno-sanitize=all', '-fno-stack-protector']
        with (work / 'logs' / (src.stem + '.log')).open('wb') as log:
            subprocess.run([str(zig), 'cc', *unit_flags, '-c', str(src), '-o', str(obj)],
                           cwd=work, env=env, stdout=log, stderr=log, check=True, timeout=1800)
        opt_file.write_text(opt)
        ok.write_text(sig)
        return obj, opt

    print(f'Compiling {len(units)} units with {a.jobs} workers; ABI {ident}', flush=True)
    objects = []
    opts = Counter()
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures = [pool.submit(compile_one, src) for src in units]
        for future in as_completed(futures):
            obj, opt = future.result()
            objects.append(obj)
            opts[opt] += 1
            if len(objects) % 25 == 0 or len(objects) == len(units):
                print(f'Compiled {len(objects)}/{len(units)} ({time.monotonic()-start:.0f}s)', flush=True)
    rsp = work / 'objects.rsp'
    rsp.write_text(''.join('"' + o.as_posix() + '"\n' for o in sorted(objects)))
    rt = release / 'zig/rt'
    target = game / 'lasgame.dll'
    if target.exists():
        raise RuntimeError('target library already exists; preserve it before replacing')
    tmp = work / 'lasgame.dll.tmp'
    with (work / 'link.log').open('wb') as log:
        subprocess.run([str(zig), 'lld-link', '@' + str(rt / 'link.rsp'), '-LIBPATH:' + str(rt),
                        '-OUT:' + str(tmp), '@' + str(rsp), str(release / 'lasrecomp.dll.a')],
                       cwd=work, env=env, stdout=log, stderr=log, check=True, timeout=300)
    tmp.replace(target)
    target.with_suffix('.dll.id').write_text(ident + '\n')
    manifest.update(finished_utc=datetime.now(timezone.utc).isoformat(), units=len(units),
                    optimisation_counts=dict(opts), giant_policy_revision=policy_revision if a.upstream_giants else None,
                    library_sha256=digest(target), library_bytes=target.stat().st_size,
                    game_execution_verified=False)
    (work / 'build-result.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest), flush=True)


if __name__ == '__main__':
    main()

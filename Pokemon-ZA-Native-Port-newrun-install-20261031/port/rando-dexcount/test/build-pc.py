"""Relink an isolated diagnostic PC game library for the dex-count proof (never part of the PS5 build).

  --variant baseline : main_310.c recompiled UNCHANGED + the test controller
  --variant fix      : main_310.c patched by prepare-dexcount-hooks.py + za_dexcount.c (trace on) + the controller
Both variants recompile main_310.c with the same MSYS2 Clang and flags, so the only code difference between them is
the patch. Every other generated object is the shipped one (aot/obj). Sources, objects, game data and the runtime are
only read. The output folder must be new and on an ASCII path (MSYS2 dlltool does not open Hebrew paths).
"""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys

p = argparse.ArgumentParser()
p.add_argument('--aot', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--variant', choices=('baseline', 'fix'), required=True)
a = p.parse_args()
aot, out = a.aot.resolve(), a.out.resolve()
own = Path(__file__).resolve().parents[1]
assert str(out).isascii(), 'output path must be ASCII'
out.mkdir(parents=True, exist_ok=False)
(out / 'obj').mkdir()
env = dict(os.environ)
env['PATH'] = 'C:/msys64/ucrt64/bin;' + env['PATH']
cc, cxx = 'C:/msys64/ucrt64/bin/clang.exe', 'C:/msys64/ucrt64/bin/clang++.exe'


def run(args, name):
    with (out / (name + '.log')).open('wb') as f:
        subprocess.run(args, cwd=out, env=env, stdout=f, stderr=f, check=True)


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


unit = aot / 'main/main_310.c'
# test accelerator in BOTH variants: the production capture hook point of port/randomizer/prepare-cheat-hooks.py
capture_unit = out / 'generated-capture/main_145.c'
capture_unit.parent.mkdir(parents=True)
raw145 = (aot / 'main/main_145.c').read_bytes()
assert hashlib.sha256(raw145).hexdigest() == '0b63266d262f3ef96690bddbc8d9a824f113067d380d40d061ce4d745f345374'
t145 = raw145.decode().replace(chr(13) + chr(10), chr(10))
anchor145 = 'L_7000447554:;' + chr(10)
assert t145.count(anchor145) == 1
t145 = t145.replace(anchor145, anchor145 + '    { extern uint32_t za_cheat_capture_score(uint32_t, uint64_t); '
                    'c->v[8] = za_cheat_capture_score((uint32_t)c->v[8], c->x[19]); }' + chr(10))
capture_unit.write_text(t145)
if a.variant == 'fix':
    subprocess.run([sys.executable, str(own / 'prepare-dexcount-hooks.py'), str(aot / 'main'),
                    str(aot.parent / 'game/exefs/main'), str(out / 'generated')], check=True)
    unit = out / 'generated/main_310.c'
entry = (aot / 'source/tools/gamelib_entry.c').read_text()
needle = '    static const GameLibTables t'
assert entry.count(needle) == 1
entry = entry.replace(needle, '    extern void za_dexcount_pc_control_start(void); za_dexcount_pc_control_start();\n' + needle)
(out / 'gamelib_entry.c').write_text(entry)
(out / 'lasrecomp.def').write_text('LIBRARY lasrecomp.exe\nEXPORTS\nfnprof_hit\ng_fnprof DATA\nrt_brk\nrt_dispatch\n'
                                   'rt_setjmp_site\nrt_svc\nrt_ticks\nrt_udf\n')
run(['C:/msys64/ucrt64/bin/dlltool.exe', '-d', str(out / 'lasrecomp.def'), '-l', str(out / 'lasrecomp.dll.a'),
     '-m', 'i386:x86-64'], 'import-library')
flags = ['-O1', '-DGUEST_VOLATILE', '-fno-strict-aliasing', '-Wno-return-type', '-Wno-unused-label',
         '-fvisibility=hidden', '-D_FILE_OFFSET_BITS=64', '-march=x86-64-v3', '-g0', '-I' + str(aot / 'source/runtime'),
         '-I' + str(own), '-DGAMELIB_ID="7b03da558e0b6144"']
sources = [(unit, 'main_310'), (capture_unit, 'main_145'), (out / 'gamelib_entry.c', 'gamelib_entry'),
           (own / 'test/pc_control.c', 'pc_control'), (own / 'test/pc_compat.c', 'pc_compat'),
           (own / 'test/pc_capture.c', 'pc_capture')]
if a.variant == 'fix':
    sources.append((own / 'za_dexcount.c', 'za_dexcount'))
for src, stem in sources:
    extra = ['-std=c11', '-DZA_DEXCOUNT_TRACE=1', '-Wall', '-Wextra', '-Werror'] if stem == 'za_dexcount' else []
    run([cc, *flags, *extra, '-c', str(src), '-o', str(out / 'obj' / (stem + '.o'))], stem)
replaced = {'main_310', 'main_145', 'gamelib_entry'}
lines = []
for line in (aot / 'objects.rsp').read_text().splitlines():
    stem = Path(line.strip('"')).stem
    lines.append('"' + (out / 'obj' / (stem + '.o')).as_posix() + '"' if stem in replaced else line)
for src, stem in sources:
    if stem not in replaced:
        lines.append('"' + (out / 'obj' / (stem + '.o')).as_posix() + '"')
(out / 'objects.rsp').write_text('\n'.join(lines) + '\n')
run([cxx, '-shared', '-fuse-ld=lld', '-static-libstdc++', '-static-libgcc', '-Wl,--stack,8388608',
     '@' + str(out / 'objects.rsp'), str(out / 'lasrecomp.dll.a'), '-o', str(out / 'lasgame.dll')], 'link')
(out / 'lasgame.dll.id').write_text('7b03da558e0b6144\n')
record = dict(variant=a.variant, compiler=subprocess.check_output([cc, '--version'], env=env).decode().splitlines()[0],
              flags=flags, unit_source=str(unit), unit_sha256=sha(unit),
              sources={stem: sha(src) for src, stem in sources}, library_sha256=sha(out / 'lasgame.dll'),
              note='Shipped AOT objects retained except main_310 (recompiled; patched only in the fix variant), '
                   'main_145 (production capture hook point, test accelerator in both variants, active only with '
                   'ZA_DEXCOUNT_PC_CAPTURE=max) and the diagnostic entry/controller. MSYS2 Clang/LLD relink. PC only.')
(out / 'build-result.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))

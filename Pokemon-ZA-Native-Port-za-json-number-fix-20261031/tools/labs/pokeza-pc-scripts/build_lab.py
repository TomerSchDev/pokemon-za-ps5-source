"""Relink a separate diagnostic library with an application-level SDL test controller."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
rel = root / 'release-v0.1.3/ZA Recomp'
work = root / 'aot-v1.0.0'
out = root / 'lab-library'
out.mkdir(exist_ok=True)
entry = (rel / 'gamelib-src/gamelib_entry.c').read_text()
entry = entry.replace('    static const GameLibTables t',
    '    extern void pokelab_control_start(void);\n    pokelab_control_start();\n    static const GameLibTables t')
(out / 'gamelib_entry_lab.c').write_text(entry)
zig = rel / 'zig/zig.exe'
env = os.environ.copy()
env['ZIG_GLOBAL_CACHE_DIR'] = env['ZIG_LOCAL_CACHE_DIR'] = str(work / 'zig-cache')
for src in [out / 'gamelib_entry_lab.c', root / 'lab_control.c']:
    full_cc = root.parent.parent / 'tools/zig/zig-x86_64-windows-0.15.2/zig.exe'
    subprocess.run([str(full_cc), 'cc', '-target', 'x86_64-windows-gnu', '-O2', '-g0', '-mcpu=x86_64_v3',
        '-I' + str(rel / 'gamelib-src'), '-I' + str(root / 'sdl-headers/include'),
        '-DGAMELIB_ID="7b03da558e0b6144"', '-c', str(src), '-o', str(out / (src.stem + '.o'))],
        check=True, env=env)
objects = [p for p in (work / 'objects.rsp').read_text().splitlines() if 'gamelib_entry.o' not in p]
objects += ['"' + (out / (n + '.o')).as_posix() + '"' for n in ['gamelib_entry_lab', 'lab_control']]
(out / 'objects.rsp').write_text('\n'.join(objects))
target = out / 'lasgame-lab.dll'
subprocess.run([str(zig), 'lld-link', '@' + str(rel / 'zig/rt/link.rsp'),
    '-LIBPATH:' + str(rel / 'zig/rt'), '-OUT:' + str(target), '@' + str(out / 'objects.rsp'),
    str(rel / 'lasrecomp.dll.a')], check=True, env=env, timeout=300)
with target.open('rb') as f:
    sha = hashlib.file_digest(f, 'sha256').hexdigest()
(target.with_suffix('.dll.id')).write_text('7b03da558e0b6144\n')
(out / 'manifest.json').write_text(json.dumps(dict(sha256=sha,
    purpose='diagnostic SDL test controller only; original generated game code objects retained',
    original_library_unchanged=True, commercial_game_source_in_extension=False), indent=2))
print(sha)

"""Relink unchanged game objects with an address map for a separate profiling run."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
rel = root / 'release-v0.1.3/ZA Recomp'
work = root / 'aot-v1.0.0'
out = root / 'profile-library'
out.mkdir(exist_ok=True)
target = out / 'lasgame.dll'
if target.exists():
    raise SystemExit('Profile library already exists; preserve it.')
rt = rel / 'zig/rt'
env = os.environ.copy()
env['ZIG_GLOBAL_CACHE_DIR'] = env['ZIG_LOCAL_CACHE_DIR'] = str(work / 'zig-cache')
with (out / 'link.log').open('wb') as log:
    subprocess.run([str(rel / 'zig/zig.exe'), 'lld-link', '@' + str(rt / 'link.rsp'),
        '-LIBPATH:' + str(rt), '-OUT:' + str(target), '-MAP:' + str(out / 'lasgame.map'),
        '@' + str(work / 'objects.rsp'), str(rel / 'lasrecomp.dll.a')],
        cwd=work, env=env, stdout=log, stderr=log, check=True, timeout=300)
target.with_suffix('.dll.id').write_text('7b03da558e0b6144\n')
with target.open('rb') as f:
    sha = hashlib.file_digest(f, 'sha256').hexdigest()
record = dict(sha256=sha, purpose='unchanged generated game objects with linker address map',
              original_library_unchanged=True)
(out / 'manifest.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record), flush=True)

#!/usr/bin/env python3
"""Merge only matching 2.0.2 runs' portable SPIR-V, never GPU pipeline caches."""
import concurrent.futures
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import sys

runs, dest, report = map(pathlib.Path, sys.argv[1:4])
dest.mkdir(parents=True, exist_ok=True)
files = {}
for p in sorted(runs.glob('*/cache/spirv/*.spv')):
    blob = p.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if len(blob) <= 20 or len(blob) % 4 or struct.unpack_from('<I', blob)[0] != 0x07230203:
        raise SystemExit(f'Invalid SPIR-V header: {p}')
    if p.name in files and files[p.name]['sha256'] != digest:
        raise SystemExit(f'Conflicting cache key: {p.name}')
    files[p.name] = {'source': str(p), 'sha256': digest, 'bytes': len(blob)}

def validate(item):
    name, entry = item
    cmd = ['spirv-val', '--target-env', 'vulkan1.3', '--scalar-block-layout', entry['source']]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        return {'name': name, 'error': result.stderr}
    shutil.copyfile(entry['source'], dest / name)
    return None

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    failures = [r for r in pool.map(validate, files.items()) if r]
report.write_text(json.dumps({'files': files, 'count': len(files), 'failures': failures,
    'note': 'Portable SPIR-V only. Coverage on PS5 remains untested; cache misses are expected.'}, indent=2))
print(f'{len(files)} unique SPIR-V modules; {len(failures)} validation failures')
if failures:
    print(json.dumps(failures[:3], indent=2))
    raise SystemExit(1)

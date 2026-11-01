#!/usr/bin/env python3
"""Stage the already selected local 2.0.2 game; reject changed inputs."""
import hashlib
import json
import pathlib
import shutil
import sys

expected = {
    'exefs/main': '2308530d73b7fea60bb845ad57d9b1f10d3ff213f89c01f73627dc8224f43ef9',
    'exefs/sdk': '0449487b457490afae879c08d6a90dd28295eaaa5c55677089a46b13991afbab',
    'exefs/rtld': '714ead44bbd81ccba54509399a5dca59c1a24e068b384292f6755829f1e9d523',
    'exefs/main.npdm': '9960d4579cb8f8aedfac6e51d8452e31c5acdd0e39308cfc0d4a42955d956058',
    'romfs.bin': '0ad824b860ebbd8dc512000a5789917241ef047f1ecea223344c3022a2377e90',
    'aoc/0100f43008c45002.bin': 'f3810c027bef4e7e8709ca1f1b5c7e7713ff499900269cd12df8a88064db0d1a',
}
source, dest, report = map(pathlib.Path, sys.argv[1:4])
def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
for name, sha in expected.items():
    src, dst = source / name, dest / name
    if digest(src) != sha:
        raise SystemExit(f'Source does not match locked game version: {name}')
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if digest(dst) != sha:
            raise SystemExit(f'Refusing to replace different staged content: {dst}')
    else:
        shutil.copyfile(src, dst)
        if digest(dst) != sha:
            raise SystemExit(f'Copy verification failed: {name}')
    print(f'verified {name}', flush=True)
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps({'version': '2.0.2 + Mega Dimension', 'source': str(source), 'sha256': expected}, indent=2))

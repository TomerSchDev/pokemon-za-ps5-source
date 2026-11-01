#!/usr/bin/env python3
"""Fail closed before enabling the generator's advertised UI options or packaging its assets.

Usage: verify-generator-handoff.py HANDOFF.json ASSETS_DIR [--out RECEIPT.json]
Checks the ready flag, exact capabilities/manifest/v3 digests, every manifest file, and every embedded JSON pin.
Only reads generator inputs. A stale handoff or an incomplete asset copy is an error.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(handoff_path, assets):
    handoff_path, assets = Path(handoff_path).resolve(), Path(assets).resolve()
    handoff = json.loads(handoff_path.read_text(encoding='utf-8-sig'))
    if handoff.get('ready_for_ui') is not True:
        raise ValueError('rando-v3 HANDOFF is not marked ready_for_ui')
    capabilities = handoff_path.parent / 'capabilities.json'
    if sha(capabilities) != handoff['capabilities_sha256']:
        raise ValueError('capabilities.json differs from the verified generator handoff')
    expected = handoff['assets']
    manifest_name = expected['manifest_file']
    if Path(manifest_name).name != manifest_name:
        raise ValueError('asset manifest must be a filename')
    manifest_path = assets / manifest_name
    if sha(manifest_path) != expected['manifest_sha256']:
        raise ValueError('asset manifest differs from the verified generator handoff')
    if sha(assets / 'v3.json') != expected['v3_sha256']:
        raise ValueError('v3.json differs from the verified generator handoff')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for name, spec in manifest.items():
        if Path(name).name != name or name in ('.', '..') or '\\' in name:
            raise ValueError('invalid asset filename: ' + name)
        path = assets / name
        if path.stat().st_size != spec['bytes'] or sha(path) != spec['sha256']:
            raise ValueError('asset integrity failure: ' + name)
    pins = dict(re.findall(r'#define\s+(ZA_\w+_SHA256)\s+"([0-9a-f]{64})"',
                           (assets / 'assets_hashes_v3.h').read_text(encoding='ascii')))
    for define, name in {'ZA_TABLES_SHA256': 'tables.json', 'ZA_STARTERS_SHA256': 'starter-deltas.json',
                         'ZA_REWARDS_SHA256': 'research-rewards.json', 'ZA_PROGRESSION_SHA256': 'progression.json',
                         'ZA_V3_SHA256': 'v3.json'}.items():
        if pins.get(define) != sha(assets / name):
            raise ValueError('embedded asset pin mismatch: ' + define)
    return {'ready_for_ui': True, 'handoff_sha256': sha(handoff_path), 'capabilities_sha256': sha(capabilities),
            'manifest_sha256': sha(manifest_path), 'assets_verified': len(manifest), 'assets': str(assets)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('handoff', type=Path)
    parser.add_argument('assets', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = verify(args.handoff, args.assets)
    text = json.dumps(result, indent=2) + '\n'
    if args.out:
        args.out.write_text(text, encoding='utf-8')
    print(text, end='')

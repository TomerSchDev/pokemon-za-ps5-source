"""Pinned, bounded review of Lua constant uses; not a general phase classifier.

The source hash binds all instructions, strings, debug data and constant references.
The reviewed manifest includes every candidate of the old all-order discovery rule.
Unknown sources, mixed namespaces and incomplete use closure fail before any write.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

MANIFEST = Path(__file__).resolve().parent.parent / 'lua-context-manifest.json'
MANIFEST_SHA256 = 'fb213995026909df6de34a7b328db6b0ec4290ffa4ac70388c1c3f7181ae4392'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'story-rando/tools'))
import luadump


def reviewed(data, phase_sha256=None):
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Lua context manifest hash mismatch')
    manifest = json.loads(raw)
    if hashlib.sha256(data).hexdigest() != manifest['input_lua_sha256']:
        raise ValueError('Lua source is outside reviewed context manifest')
    if phase_sha256 is not None and phase_sha256 != manifest['input_phase_sha256']:
        raise ValueError('phase source is outside reviewed Lua context manifest')
    root = luadump.load(data, constant_offsets=True)
    protos = {}
    def walk(proto, path):
        protos[path] = proto
        for i, child in enumerate(proto['p']): walk(child, path + '/' + str(i))
    walk(root, 'r')
    rows, seen = [], set()
    if len(manifest['entries']) != 18: raise ValueError('incomplete reviewed Lua candidate union')
    for entry in manifest['entries']:
        path, index = entry['prototype'], entry['constant_index']
        key = (path, index)
        if key in seen: raise ValueError('duplicate Lua context entry')
        seen.add(key)
        namespace = entry['namespace']
        decision = {'main': 'translate_main_phase', 'dlc': 'preserve_dlc_phase'}
        if len(namespace) != 1 or namespace[0] not in decision or \
           entry['decision'] != decision[namespace[0]] or not entry['bounded_use_closure_complete'] or \
           not entry['direct_references'] or not entry['resolved_uses']:
            raise ValueError('Lua context unknown, mixed or incompletely reviewed')
        proto = protos[path]
        code = struct.pack('<%dI' % len(proto['code']), *proto['code'])
        offset = proto['k_offsets'][index]
        if hashlib.sha256(code).hexdigest() != entry['code_sha256'] or \
           type(proto['k'][index]) is not int or proto['k'][index] != entry['original_value'] or \
           offset is None or struct.unpack_from('<q', data, offset)[0] != entry['original_value']:
            raise ValueError('Lua context prototype/constant mismatch')
        rows.append((entry, offset))
    return manifest, root, rows

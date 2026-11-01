"""Read-only ZARSLOT1.1 inspection for the existing81e2 validation target.

Contract: actual UI/runtime overlay za_slot.h SHA50638231...447bb5.
No game-save decryption, generation, rewriting or source-tree fallback.
"""
import hashlib
import json
import struct
import zlib


class SlotError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def cstring(data, offset, length):
    field = data[offset:offset + length]
    if len(field) != length or b'\0' not in field:
        raise SlotError('Missing bounded NUL-terminated summary string')
    return field.split(b'\0', 1)[0].decode('utf-8', errors='strict')


def parse_slot(raw, *, expected_run_id=None, expected_seed=None):
    if not 64 <= len(raw) <= 48 << 20 or raw[:8] != b'ZARSLOT\0':
        raise SlotError('Missing/oversized ZARSLOT header')
    major, minor, header, count, flags, total, expected_crc = struct.unpack_from('<HHIIIQI', raw, 8)
    if major != 1 or minor > 1 or header != 64 or not 1 <= count <= 16 or flags != 0 or total != len(raw):
        raise SlotError('Unsupported header or incomplete container')
    table_end = header + count * 32
    if table_end > len(raw):
        raise SlotError('Truncated section table')
    crc = zlib.crc32(raw[:32])
    crc = zlib.crc32(raw[header:table_end], crc) & 0xffffffff
    if crc != expected_crc:
        raise SlotError('Section-table CRC mismatch')
    sections, ranges = {}, []
    for i in range(count):
        kind, section_flags, offset, length, section_crc, reserved = struct.unpack_from('<4sIQQII', raw, header + i * 32)
        if kind in sections or section_flags or reserved or offset < table_end or offset > total or length > total - offset:
            raise SlotError('Invalid/duplicate section descriptor')
        if any(offset < end and start < offset + length for start, end in ranges):
            raise SlotError('Overlapping sections')
        body = raw[offset:offset + length]
        if zlib.crc32(body) & 0xffffffff != section_crc:
            raise SlotError('Section CRC mismatch: ' + repr(kind))
        sections[kind] = body
        ranges.append((offset, offset + length))
    if not {b'SUMM', b'RAND', b'SETT', b'SAVE'} <= sections.keys():
        raise SlotError('Required sections missing')
    summary = sections[b'SUMM']
    if len(summary) < 256 or len(summary) > 65536:
        raise SlotError('Unsupported summary size')
    version, present = struct.unpack_from('<II', summary)
    if version not in (1, 2) or version == 2 and len(summary) < 320:
        raise SlotError('Unsupported/truncated summary version')
    save_time, created_time = struct.unpack_from('<QQ', summary, 8)
    save_size = struct.unpack_from('<I', summary, 32)[0]
    save = sections[b'SAVE']
    if not save or len(save) > 32 << 20 or save_size != len(save):
        raise SlotError('Summary/SAVE length mismatch')
    save_hash = summary[40:72].hex()
    if present & 8 and save_hash != digest(save):
        raise SlotError('Summary save SHA mismatch')
    rand = json.loads(sections[b'RAND'].decode('utf-8', errors='strict'))
    settings = json.loads(sections[b'SETT'].decode('utf-8', errors='strict'))
    if not isinstance(rand, dict) or not isinstance(settings, dict):
        raise SlotError('RAND/SETT must be objects')
    run_id = cstring(summary, 72, 48)
    seed = cstring(summary, 120, 24)
    # Wire parsing also accepts the actual C test's deliberately minimal RAND/
    # SETT objects. Production run observations always supply both identities.
    if (expected_run_id is None) != (expected_seed is None):
        raise SlotError('Run identity and seed must be checked together')
    if expected_run_id is not None:
        if (run_id != expected_run_id or rand.get('schema') != 'za-slot-rand-1'
                or rand.get('run_id') != run_id):
            raise SlotError('RAND identity mismatch')
        if (seed != expected_seed or settings.get('schema') != 'za-slot-settings-1'
                or settings.get('seed') != seed):
            raise SlotError('SETT seed mismatch')
    result = {'container_sha256': digest(raw), 'container_bytes': len(raw),
              'summary': {'version': version, 'flags': present, 'run_id': run_id, 'seed': seed,
                          'save_time': save_time, 'created_time': created_time, 'save_size': save_size,
                          'save_sha256': save_hash, 'location': cstring(summary, 144, 32)},
              'section_sha256': {key.decode('ascii'): digest(value) for key, value in sections.items()},
              'save_bytes': save}
    if version == 2:
        result['summary'].update(zip(('story_phase', 'dlc_phase', 'research_level', 'research_points'),
                                     struct.unpack_from('<IIII', summary, 256), strict=True))
    return result

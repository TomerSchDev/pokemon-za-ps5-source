"""Remove only the two conversion intermediates of a verified pinned relink.

This is not a general retention or recursive directory-cleanup utility.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

SOURCE_BYTES = Path(__file__).read_bytes()
SOURCE_SHA256 = hashlib.sha256(SOURCE_BYTES).hexdigest()
INTERMEDIATES = ('title-stripped.elf', 'eboot.elf')
RETAINED = ('llvm-pie.elf', 'eboot.bin', 'proof.json')


def _json_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def _identity(path):
    info = os.stat(path, follow_symlinks=False)
    return {'device': info.st_dev, 'inode': info.st_ino, 'links': info.st_nlink,
            'size': info.st_size, 'mtime_ns': info.st_mtime_ns,
            'allocated_bytes': getattr(info, 'st_blocks', None) * 512
            if hasattr(info, 'st_blocks') else None, 'mode': info.st_mode}


def _link(path):
    return path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())


def _root(path, protected):
    root = Path(path).absolute()
    if not root.is_dir() or any(_link(p) for p in (root, *root.parents)):
        raise ValueError('Cleanup output root must be a real directory without symlink/junction ancestors')
    if root.resolve(strict=True) != root:
        raise ValueError('Cleanup output root is not its resolved absolute path')
    for item in protected:
        target = Path(item).resolve()
        if root == target or target in root.parents or root in target.parents:
            raise ValueError('Cleanup output root overlaps a protected input: ' + str(target))
    return root


def cleanup_conversion_intermediates(output, *, protected_paths=(), keep_reason=None):
    """Called only after the complete build's success gates, never on failed builds.

    A fresh small plan precedes deletion; each successful unlink is journaled and fsynced.
    Required proof outputs are retained, so the existing check-proof contract is unchanged.
    Metadata is not represented as content hashing or guaranteed physical free space.
    """
    protected_paths = tuple(protected_paths)
    root = _root(output, protected_paths)
    original_root = _identity(root)
    if keep_reason is not None and (not isinstance(keep_reason, str) or not keep_reason.strip()):
        raise ValueError('--keep-intermediates requires a nonempty diagnostic reason')
    token = uuid.uuid4().hex
    plan_path = root / ('cleanup-plan-' + token + '.json')
    progress_path = root / ('cleanup-progress-' + token + '.jsonl')
    result_path = root / ('cleanup-result-' + token + '.json')
    result = {'schema': 1, 'scope': 'verified-pinned-relink-conversion-intermediates-only',
              'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'output': str(root),
              'status': 'error', 'keep_reason': keep_reason, 'candidates': [], 'deleted': [],
              'retained': [], 'errors': [], 'receipt': str(result_path),
              'content_hashing': 'Proof JSON hashed; intermediate metadata only, no additional bulk reads',
              'physical_reclaimed_bytes': None}
    try:
        retained_before = {}
        for name in RETAINED:
            item = root / name
            if _link(item) or not item.is_file():
                raise ValueError('Required retained artifact absent or linked: ' + name)
            retained_before[name] = _identity(item)
        proof_bytes = (root / 'proof.json').read_bytes()
        proof = json.loads(proof_bytes)
        if (proof.get('status') != 'passed' or
                proof.get('method') != 'relink-frozen-objects-and-convert-sign' or
                proof.get('inputs_after', {}).get('ok') is not True):
            raise ValueError('Cleanup requires a successful verified relink proof')
        for key, name in (('pie', 'llvm-pie.elf'), ('eboot', 'eboot.bin')):
            observed = proof.get('outputs', {}).get(key, {})
            if (observed.get('file') != name or observed.get('sha256_matches') is not True or
                    observed.get('byte_for_byte_equal') is not True or
                    observed.get('size') != retained_before[name]['size'] or
                    not isinstance(observed.get('actual_sha256'), str) or
                    len(observed['actual_sha256']) != 64 or
                    observed['actual_sha256'] != observed.get('expected_sha256')):
                raise ValueError('Required retained output is not proved: ' + name)
            result['retained'].append({'file': name, 'reason': 'Required by unchanged check-proof',
                                       'sha256_recorded_in_proof': observed['actual_sha256']})
        result['proof_sha256'] = hashlib.sha256(proof_bytes).hexdigest()
        for name in INTERMEDIATES:
            item = root / name
            if not item.exists() and not _link(item):
                continue
            before = _identity(item)
            if (_link(item) or not stat.S_ISREG(before['mode']) or before['links'] != 1 or
                    before['inode'] == 0):
                raise ValueError('Intermediate must be an exclusively linked regular file: ' + name)
            result['candidates'].append({'file': name, 'before': before})
        # Validate every target before unlinking either one; no recursive/glob cleanup.
        _json_new(plan_path, result)
        if keep_reason is not None:
            result['status'] = 'kept_for_debug'
        elif not result['candidates']:
            result['status'] = 'already_clean'
        else:
            with progress_path.open('x', encoding='utf-8', newline='\n') as journal:
                for row in result['candidates']:
                    _root(root, protected_paths)
                    current_root = _identity(root)
                    if any(current_root[k] != original_root[k] for k in ('device', 'inode')):
                        raise ValueError('Cleanup root identity changed before unlink')
                    item = root / row['file']
                    if _identity(item) != row['before'] or _link(item):
                        raise ValueError('Intermediate identity changed before cleanup: ' + row['file'])
                    if any(_identity(root / name) != old for name, old in retained_before.items()):
                        raise ValueError('Required retained artifacts changed before cleanup')
                    item.unlink()
                    result['deleted'].append(row)
                    journal.write(json.dumps({'deleted': row}, ensure_ascii=False) + '\n')
                    journal.flush()
                    os.fsync(journal.fileno())
            result['status'] = 'cleaned'
        if any(_identity(root / name) != old for name, old in retained_before.items()):
            raise ValueError('Required retained artifacts changed during cleanup')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result['status'] = 'error'
        result['errors'].append(str(exc))
    result['logical_bytes_removed'] = sum(row['before']['size'] for row in result['deleted'])
    result['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    # A changed/linked root is not a safe place to write even an error receipt.
    _root(root, protected_paths)
    if any(_identity(root)[k] != original_root[k] for k in ('device', 'inode')):
        raise ValueError('Cleanup root identity changed; no final receipt written into its replacement')
    _json_new(result_path, result)
    return result

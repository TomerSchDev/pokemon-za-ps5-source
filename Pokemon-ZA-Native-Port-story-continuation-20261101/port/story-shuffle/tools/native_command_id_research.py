"""Bounded numeric getter metadata through existing canonical P2 NSO reader.

Searches exact ARM64 MOVZ W0/X0,#ID;RET patterns, not a new decoder.
Hits are candidates, never asserted to be event-command bindings without review.
No game/save/output bytes, builds, raw code windows, or bytecode files are written.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import threading
import time


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--nso', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--input-check', type=Path, required=True)
    ap.add_argument('--input-check-sha256', required=True)
    a = ap.parse_args()
    if a.out.exists():
        ap.error('Output must be new')
    if sha(a.input_check) != a.input_check_sha256:
        ap.error('Input check SHA differs')
    check = json.loads(a.input_check.read_text(encoding='utf-8-sig'))
    if not check.get('allowed_to_start') or check.get('operation') != 'read_only_native_getter_metadata':
        ap.error('Reviewed scoped input check required')
    if sha(a.repo / 'docs/testing/BUILD_DEPENDENCY_MAP.json') != check['map_sha256']:
        ap.error('Canonical dependency map changed; refresh outside queue')
    overrides = [key for key in ('PC_TEST_STATE', 'CONSOLE_INSTALL_STATE', 'ZW_STATE',
                                'PC_TEST_ROOT', 'CONSOLE_INSTALL_ROOT') if os.environ.get(key)]
    if overrides:
        ap.error('State overrides forbidden: ' + ','.join(overrides))
    cache = Path(check['absent_project_pycache_prefix'])
    if not cache.is_absolute() or cache.exists():
        ap.error('Project pycache prefix must be an absent absolute path')
    sys.pycache_prefix = str(cache)
    queue = load('canonical_pc_queue', a.repo / 'tools/console-install-queue/console_queue.py')
    agent, ticket, token = [os.environ.get('PC_TEST_' + key, '') for key in ('AGENT', 'TICKET', 'TOKEN')]
    if not all((agent, ticket, token)):
        ap.error('Canonical PC lease required')
    board = queue.Board(resource='pc')
    board.check(agent, ticket, token)
    watchdog = threading.Timer(45, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()  # Own process only; caller records timeout and releases its lease.
    for row in check['pinned_files']:
        if sha(Path(row['path'])) != row['sha256']:
            raise ValueError('Input changed after review: ' + row['path'])
    runtime = json.loads(Path(check['windows_runtime_manifest']).read_text(encoding='utf-8-sig'))
    if Path(sys.executable).resolve() != Path(runtime['executable']).resolve() or not sys.flags.isolated:
        raise ValueError('Wrong canonical isolated Python runtime')
    for row in runtime['files']:
        path = Path(row['path'])
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('Runtime superset changed: ' + str(path))
    board.heartbeat(agent, ticket, token)
    P2 = load('canonical_p2_extract', a.repo / 'tools/za-atlas/P2/extract.py')
    P2.lower_priority()
    start = time.monotonic()
    nso = P2.Nso(a.nso, 'main')
    if nso.input_sha256 != '2308530d73b7fea60bb845ad57d9b1f10d3ff213f89c01f73627dc8224f43ef9':
        raise ValueError('Wrong original2.0.2 NSO')
    if nso.build_id != 'b1f12fd919eae86ab8a978317677e64bce443d1f':
        raise ValueError('Wrong build ID')
    board.heartbeat(agent, ticket, token)
    _, pointers, unresolved = P2.relocate([nso])
    segment = nso.segments[0]
    data, origin = segment['bytes'], nso.base + segment['off']
    hits = []
    for value in (8, 9, 22, 111, 125, 126, 137):
        for bits, opcode in ((32, 0x52800000), (64, 0xd2800000)):
            pattern = struct.pack('<II', opcode | (value << 5), 0xd65f03c0)
            pos = -1
            while True:
                pos = data.find(pattern, pos + 1)
                if pos < 0:
                    break
                if pos % 4:
                    continue
                address = origin + pos
                refs = sorted(p for p, target in pointers.items() if target == address)
                windows = []
                for ref in refs[:16]:
                    windows.append({'pointer_slot': hex(ref),
                                    'neighbor_relocated_pointers': [
                                        {'slot': hex(ref + delta), 'target': hex(pointers[ref + delta])}
                                        for delta in range(-24, 33, 8) if ref + delta in pointers]})
                hits.append({'constant': value, 'return_bits': bits, 'address': hex(address),
                             'relocation_reference_count': len(refs), 'references': windows,
                             'event_command_binding': 'UNPROVEN'})
                if len(hits) > 256:
                    raise ValueError('Unexpected candidate count exceeds bounded research scope')
    result = {'schema': 'za-native-id-getter-research-1', 'input_nso_sha256': nso.input_sha256,
              'build_id': nso.build_id, 'decoder_sha256': sha(a.repo / 'tools/za-atlas/P2/extract.py'),
              'helper_sha256': sha(Path(__file__)), 'input_check_sha256': sha(a.input_check),
              'hits': hits, 'unresolved_relocations': dict(unresolved),
              'elapsed_seconds': time.monotonic() - start, 'game_started': False,
              'project_pycache_prefix': str(cache), 'project_pycache_path_still_absent': not cache.exists(),
              'windows_runtime_manifest_sha256': sha(Path(check['windows_runtime_manifest'])),
              'runtime_superset_files_verified': len(runtime['files']),
              'raw_code_or_game_bytes_written': False, 'event_command_bindings_proven': False}
    board.check(agent, ticket, token)
    if cache.exists():
        raise ValueError('Unexpected project pycache path appeared')
    watchdog.cancel()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(a.out), 'candidates': len(hits), 'seconds': result['elapsed_seconds']}))


if __name__ == '__main__':
    main()

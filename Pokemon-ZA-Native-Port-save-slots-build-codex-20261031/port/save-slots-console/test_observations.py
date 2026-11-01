"""DRAFT focused tests: existing C-produced synthetic golden + refusal cases.

No fixture generation/compilation, real network, game assets or real saves.
Must be run through the canonical PC queue after scoped input closure.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
import zlib

HERE = Path(__file__).resolve().parent
GOLDEN_SHA = '1e4c115f098a6a84ed583c7293ef97a53515ef9119a95fe8c7f7075ef812d49b'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def crc_table(raw):
    count = struct.unpack_from('<I', raw, 16)[0]
    struct.pack_into('<I', raw, 32, zlib.crc32(raw[64:64 + count * 32], zlib.crc32(raw[:32])) & 0xffffffff)


def mutate_sections(raw, replacements=None, extra=None, minor=None):
    """Mutate a real C-produced wire fixture, never an inverse golden builder."""
    replacements = replacements or {}
    count = struct.unpack_from('<I', raw, 16)[0]
    rows = []
    for i in range(count):
        kind, flags, offset, length, crc, reserved = struct.unpack_from('<4sIQQII', raw, 64 + i * 32)
        rows.append((kind, replacements.get(kind, raw[offset:offset + length])))
    if extra is not None:
        rows.append(extra)
    output = bytearray(raw[:64]) + bytearray(32 * len(rows))
    struct.pack_into('<I', output, 16, len(rows))
    if minor is not None:
        struct.pack_into('<H', output, 10, minor)
    for i, (kind, body) in enumerate(rows):
        struct.pack_into('<4sIQQII', output, 64 + i * 32, kind, 0, len(output), len(body), zlib.crc32(body) & 0xffffffff, 0)
        output.extend(body)
    struct.pack_into('<Q', output, 24, len(output))
    crc_table(output)
    return output


class WireTests(unittest.TestCase):
    golden = None
    fmt = None

    def test_existing_C_golden_exact_pattern_and_fields(self):
        result = self.fmt.parse_slot(self.golden)
        self.assertEqual(result['save_bytes'], bytes((i * 31 + 7) & 255 for i in range(70000)))
        self.assertEqual(result['summary']['run_id'], 'r000000006ae61a20-5c3e9b07')
        self.assertEqual(result['summary']['seed'], '1793440215')
        self.assertEqual(result['summary']['save_time'], 1793440215)
        self.assertEqual(result['summary']['created_time'], 1793400000)
        self.assertEqual(result['summary']['story_phase'], 21160)
        self.assertEqual(result['summary']['research_level'], 4)
        self.assertEqual(result['summary']['research_points'], 1234)

    def test_v1_summary(self):
        summ = bytearray(self.golden[192:192 + 256])
        struct.pack_into('<I', summ, 0, 1)
        parsed = self.fmt.parse_slot(mutate_sections(self.golden, {b'SUMM': summ}, minor=0))
        self.assertEqual(parsed['summary']['version'], 1)
        self.assertNotIn('story_phase', parsed['summary'])

    def test_unknown_section_is_verified_and_preserved(self):
        parsed = self.fmt.parse_slot(mutate_sections(self.golden, extra=(b'FUTR', b'additive-section')))
        self.assertEqual(parsed['section_sha256']['FUTR'], hashlib.sha256(b'additive-section').hexdigest())

    def test_bad_section_crc(self):
        raw = bytearray(self.golden)
        raw[-1] ^= 1
        with self.assertRaises(self.fmt.SlotError): self.fmt.parse_slot(raw)

    def test_bad_table_crc(self):
        raw = bytearray(self.golden)
        raw[72] ^= 1
        with self.assertRaises(self.fmt.SlotError): self.fmt.parse_slot(raw)

    def test_truncated_file(self):
        with self.assertRaises(self.fmt.SlotError): self.fmt.parse_slot(self.golden[:-1])

    def test_overlap_even_with_correct_crcs(self):
        # Two descriptors may individually have valid CRCs while aliasing data.
        raw = bytearray(self.golden)
        raw[104:128] = raw[72:96]  # RAND offset/length/CRC alias SUMM body.
        crc_table(raw)
        with self.assertRaises(self.fmt.SlotError): self.fmt.parse_slot(raw)

    def test_duplicate_section(self):
        raw = mutate_sections(self.golden, extra=(b'SAVE', b'duplicate'))
        with self.assertRaises(self.fmt.SlotError): self.fmt.parse_slot(raw)

    def test_application_identity_not_in_minimal_C_golden(self):
        with self.assertRaises(self.fmt.SlotError):
            self.fmt.parse_slot(self.golden, expected_run_id='foreign', expected_seed='1793440215')

    def test_identity_and_seed_checked_together(self):
        with self.assertRaises(self.fmt.SlotError):
            self.fmt.parse_slot(self.golden, expected_run_id='r000000006ae61a20-5c3e9b07')

    def test_application_identity_valid_and_wrong_seed_rejected(self):
        name, seed = 'r000000006ae61a20-5c3e9b07', '1793440215'
        raw = mutate_sections(self.golden, {b'RAND': json.dumps({'schema': 'za-slot-rand-1', 'run_id': name}).encode(),
            b'SETT': json.dumps({'schema': 'za-slot-settings-1', 'seed': seed}).encode()})
        self.fmt.parse_slot(raw, expected_run_id=name, expected_seed=seed)
        with self.assertRaises(self.fmt.SlotError): self.fmt.parse_slot(raw, expected_run_id=name, expected_seed='0')


class ObservationTests(unittest.TestCase):
    obs = None

    def test_run_path_escape_refused(self):
        for value in ('../PPSA91762', '/absolute', 'a/b', 'a\\b', '', 'A'):
            with self.assertRaises(ValueError): self.obs.run_id(value)

    def test_exact_create_switch_delete(self):
        empty, a, both, only_a = ({'runs': [], 'active': None}, {'runs': ['ra'], 'active': 'ra'},
                                {'runs': ['ra', 'rb'], 'active': 'rb'}, {'runs': ['ra'], 'active': 'ra'})
        self.obs.transition(empty, a, created='ra', active='ra')
        self.obs.transition(a, both, created='rb', active='rb')
        self.obs.transition(both, {**both, 'active': 'ra'}, active='ra')
        self.obs.transition(both, only_a, deleted='rb', active='ra')
        with self.assertRaises(ValueError): self.obs.transition(both, {'runs': [], 'active': None}, deleted='rb')
        with self.assertRaises(ValueError): self.obs.transition(both, only_a, deleted='foreign')

    def test_foreign_pid_param_session_and_mount_refused(self):
        obs = self.obs
        param = b'{"titleId":"PPSA91781"}'
        old_param = obs.PARAM_SHA
        obs.PARAM_SHA = hashlib.sha256(param).hexdigest()
        try:
            identity = {'title': obs.TITLE, 'pid': 123, 'eboot_sha256': obs.EBOOT_SHA,
                        'param_sha256': obs.PARAM_SHA, 'session': 'a' * 16}
            class FakeConsole:
                pid, raw, sid = 123, param, 'a' * 16
                mounted = [obs.TITLE + '_000']
                def read(self, *args): return self.raw
                def listing(self, *args): return self.mounted
            c = FakeConsole()
            m = SimpleNamespace(api=SimpleNamespace(eboot_processes=lambda: [{'pid': c.pid}], process_pid=lambda p: p['pid']),
                    observer=SimpleNamespace(TITLE=obs.TITLE, BASE=obs.SANDBOX + '/download0/zarecomp/observer',
                                             status=lambda ftp: {'session': c.sid}))
            c.ftp = object()
            obs.own(c, identity, m, lambda: None)
            for field, value, restored in [('pid', 999, 123), ('raw', b'{"titleId":"PPSA91762"}', param),
                                          ('sid', 'b' * 16, 'a' * 16),
                                          ('mounted', [obs.TITLE + '_000', 'PPSA91762_000'], [obs.TITLE + '_000'])]:
                setattr(c, field, value)
                with self.assertRaises(RuntimeError): obs.own(c, identity, m, lambda: None)
                setattr(c, field, restored)
        finally:
            obs.PARAM_SHA = old_param

    def test_initial_creation_never_passes_actual_writer(self):
        base = {'run_id': 'ra', 'main_sha256': 'a' * 64, 'report_sha256': 'r', 'tables': {},
                'slot': {'container_sha256': 'c', 'summary': {'run_id': 'ra', 'seed': '1', 'created_time': 2,
                        'flags': 8, 'save_sha256': 'a' * 64}, 'section_sha256': {'RAND': 'r', 'SETT': 's'}}}
        with self.assertRaises(ValueError): self.obs.writer_roundtrip(base, base, '[slot] commit 1: foo rewritten (123 bytes): save ')
        after = deepcopy(base)
        after['main_sha256'] = 'b' * 64
        after['slot']['container_sha256'] = 'd'
        after['slot']['summary']['save_sha256'] = 'b' * 64
        with self.assertRaises(ValueError): self.obs.writer_roundtrip(base, after, 'stale/no writer marker')
        log = '[slot] commit 12: /download0/zarecomp/rando/ra/slot.zrs rewritten (123 bytes): save 456 bytes sha256 bb...'
        self.assertEqual(self.obs.writer_roundtrip(base, after, log)['result'], 'PASS')
        after['slot']['section_sha256']['RAND'] = 'changed'
        with self.assertRaises(ValueError): self.obs.writer_roundtrip(base, after, log)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--queue-sha256', required=True)
    p.add_argument('--golden', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--input-check', type=Path, required=True)
    p.add_argument('--input-check-sha256', required=True)
    args = p.parse_args()
    if os.environ.get('PC_TEST_STATE') or os.environ.get('CONSOLE_INSTALL_STATE'):
        raise ValueError('Only canonical shared resource state is allowed')
    if hashlib.sha256(args.input_check.read_bytes()).hexdigest() != args.input_check_sha256:
        raise ValueError('Reviewed scoped input check changed')
    scoped = json.loads(args.input_check.read_text(encoding='utf-8-sig'))
    if (scoped.get('status') != 'READY_FOR_SCOPED_BUILD' or scoped.get('allowed_to_start') is not True
            or scoped.get('operation') != 'existing-81e2-format-observations-focused-tests'):
        raise ValueError('Exact tests-only input closure is not ready')
    if hashlib.sha256((args.repo / 'docs/testing/BUILD_DEPENDENCY_MAP.json').read_bytes()).hexdigest() != scoped['map_sha256']:
        raise ValueError('Scoped dependency map changed before execution')
    for row in scoped['actual_input_files']:
        if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Exact scoped input changed: ' + row['path'])
    cache_prefix = HERE / '.source-only-no-bytecode-consumption'
    if cache_prefix.exists(): raise ValueError('Source-only cache prefix must remain absent')
    sys.pycache_prefix = str(cache_prefix)
    sys.dont_write_bytecode = True
    queue_path = args.repo / 'tools/console-install-queue/console_queue.py'
    if hashlib.sha256(queue_path.read_bytes()).hexdigest() != args.queue_sha256:
        raise ValueError('Canonical queue source changed')
    queue = load('slot_tests_canonical_queue', queue_path)
    agent, ticket, token = (os.environ.get('PC_TEST_' + k, '') for k in ('AGENT', 'TICKET', 'TOKEN'))
    if not all((agent, ticket, token)): raise ValueError('Canonical PC turn required; no tests executed')
    board = queue.Board(resource='pc')
    board.check(agent, ticket, token)
    golden = args.golden.read_bytes()
    if hashlib.sha256(golden).hexdigest() != GOLDEN_SHA:
        raise ValueError('Existing C-produced synthetic golden changed')
    WireTests.golden, WireTests.fmt = golden, load('slot_tests_format', HERE / 'slot_format.py')
    ObservationTests.obs = load('slot_tests_observations', HERE / 'observations.py')
    suite = unittest.TestSuite((unittest.defaultTestLoader.loadTestsFromTestCase(WireTests),
                               unittest.defaultTestLoader.loadTestsFromTestCase(ObservationTests)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    board.check(agent, ticket, token)
    if args.out.exists(): raise FileExistsError(args.out)
    record = {'schema': 'slots-observer-focused-tests-1', 'status': 'PASS' if result.wasSuccessful() else 'FAIL',
              'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'golden': {'path': str(args.golden.resolve()), 'sha256': GOLDEN_SHA,
                         'source': 'existing actual C test_saves output; synthetic 70000-byte pattern'},
              'source_sha256': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                                for name in ('slot_format.py', 'observations.py', 'test_observations.py')},
              'console_access': False, 'hardware_tested': False, 'fixture_files_created': False}
    args.out.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__': main()

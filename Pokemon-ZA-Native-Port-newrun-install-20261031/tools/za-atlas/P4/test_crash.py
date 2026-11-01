"""Regression checks for real fault-PC semantics, filtering and cache identity."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('atlas_crash', HERE / 'crash.py')
crash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crash)
spec_runtime = importlib.util.spec_from_file_location('atlas_runtime', HERE / 'index_runtime.py')
runtime = importlib.util.module_from_spec(spec_runtime)
spec_runtime.loader.exec_module(runtime)


class CrashTests(unittest.TestCase):
    def test_original_pc_wins_over_abort_rip_and_shared_libraries(self):
        result = crash.parse_log('''[za-native-fault] sig=11 fa=a2 pc=489215 sp=782818fda0
[zarecomp] *** signal 11 accessing 0xa2
# rip: 00000008000b90c0
# backtrace:
# 000000000043b15b
# 000000080000cc3f
# 0000000000000000
#
# dynamic libraries:
# /app0/eboot.bin
#  xotext: 0000000000400000:00000000156b0000 nsegs: 4
''')
        self.assertEqual(result['frames'][0]['relative'], '89215')
        self.assertEqual([row['absolute'] for row in result['frames']], ['489215', '43b15b'])

    def test_last_event_only(self):
        result = crash.parse_log('''[za-native-fault] sig=11 fa=0 pc=400100
[zarecomp]   #0  0000000000400200
[za-native-fault] sig=4 fa=1 pc=400300
[zarecomp]   #0  0000000000400400
''')
        self.assertEqual(result['signal'], 4)
        self.assertEqual([row['relative'] for row in result['frames']], ['300', '400'])

    def test_legacy_signal_and_no_fake_abort_pc(self):
        result = crash.parse_log('*** signal 11\n[zarecomp] host pc 400100 (?+0)\n')
        self.assertEqual(result['frames'][0]['relative'], '100')
        with self.assertRaisesRegex(ValueError, 'original host PC'):
            crash.parse_log('*** signal 11\n# rip: 00000008000b90c0\n')

    def test_instruction_bytes_removed_and_fault_required(self):
        result = crash.disassembly_excerpt('  89215: 89 88 a0 00 00 00\t movl\t%ecx, 0xa0(%rax)\n', 0x89215)
        self.assertEqual(result[0]['instruction'], 'movl\t%ecx, 0xa0(%rax)')
        self.assertTrue(result[0]['fault'])
        with self.assertRaises(ValueError):
            crash.disassembly_excerpt('  89200: 90 nop\n', 0x89215)

    def test_elf_identity_changes_after_replacement(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / 'candidate.elf'
            path.write_bytes(b'one')
            first = crash.elf_identity(path, 'Ubuntu')
            path.write_bytes(b'another')
            self.assertNotEqual(first, crash.elf_identity(path, 'Ubuntu'))

    def test_registration_comments_do_not_become_functions(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / 'a.c'
            path.write_text('// HLE_FUNC("fake", wrong)\nHLE_FUNC("actual", actual_fn) {}\nNVN(nvnDemo) {}\nSERVICE("aud", audio) {}\n', encoding='utf-8')
            rows = list(runtime.registrations(Path(scratch)))
            self.assertEqual([row['name'] for row in rows], ['actual', 'nvnDemo', 'service:aud'])
            self.assertEqual(rows[0]['line'], 2)


if __name__ == '__main__':
    unittest.main()

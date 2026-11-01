"""Offline tests for zw: no console, no game, no WSL."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('zw', HERE / 'zw.py')
zw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zw)


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = zw.main(list(argv))
    return code, out.getvalue()


class Cards(unittest.TestCase):
    def test_every_kit_card_exists(self):
        for task, cards in zw.KITS.items():
            for name in cards:
                self.assertTrue((zw.CARDS / (name + '.md')).is_file(), f'{task}: {name}')

    def test_card_cross_references_exist(self):
        for card in zw.CARDS.glob('*.md'):
            for ref in re.findall(r'cards/([a-z\-]+)\.md', card.read_text(encoding='utf-8')):
                self.assertTrue((zw.CARDS / (ref + '.md')).is_file(), f'{card.name} -> {ref}')

    def test_cards_name_only_known_verbs(self):
        verbs = set(zw.FORWARD) | set(zw.COMPOSITE)
        for card in zw.CARDS.glob('*.md'):
            for verb in re.findall(r'`zw ([a-z\-]+)', card.read_text(encoding='utf-8')):
                self.assertIn(verb, verbs, f'{card.name}: zw {verb}')

    def test_brief_starts_with_rules_and_stays_small(self):
        for task in zw.KITS:
            code, text = run('brief', task)
            self.assertEqual(code, 0)
            self.assertLess(text.index('# Rules'), text.index('# Card'))
            self.assertLess(len(text), 16000, task)

    def test_unknown_card(self):
        with self.assertRaises(zw.ZwError):
            run('card', 'nope')


class ConsoleGate(unittest.TestCase):
    def setUp(self):
        os.environ.pop('ZW_CONSOLE_OK', None)

    def test_console_verbs_refuse_without_flag(self):
        for argv in (['shot', '--out', 'x'], ['fps', 'measure', '5', '--out', 'x'], ['fps', 'set', '1'],
                     ['input', 'A', '4'], ['klog', '--out', 'x'], ['obs', 'status']):
            with self.assertRaisesRegex(zw.ZwError, 'contacts the console'):
                run(*argv)


class Pc(unittest.TestCase):
    def test_fps_summary(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'stderr.log').write_text(
                '[vk] t=2.0 frame 60 30.0 fps max 40.1ms level 0\n'
                '[vk] t=4.0 frame 110 25.0 fps max 80.5ms level 0\n', encoding='utf-8')
            code, text = run('pc', 'fps', d)
        self.assertEqual(code, 0)
        self.assertIn('min 25.0', text)
        self.assertIn('worst frame 80.5 ms', text)

    def test_script_name_is_validated(self):
        with self.assertRaises(zw.ZwError):
            run('hebrew', '..\\evil')


class ResourceGate(unittest.TestCase):
    def test_resource_operations_refuse_without_a_turn(self):
        with patch.dict(os.environ, {}, clear=True):
            for argv in (['pc', 'run', 'test', '--seconds', '1'], ['hebrew', 'run_poc', 'test'],
                         ['ui-new-run-host', '/tmp/no-run'], ['ui-json-test', '/tmp/no-run'],
                         ['shot', '--out', 'x', '--console-ok'], ['doctor', '--console-ok']):
                with self.assertRaisesRegex(zw.ZwError, 'turn first'):
                    run(*argv)

    def test_token_and_deadline_guard_without_running_a_process(self):
        path = zw.REPO / 'tools' / 'console-install-queue' / 'console_queue.py'
        spec = importlib.util.spec_from_file_location('gate_queue_fixture', path)
        queue = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(queue)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = queue.Board(root / 'state', resource='pc')
            job = root / 'job.json'
            job.write_text('{"name":"offline guard fixture"}')
            ticket = board.enqueue('tester', 'guard-fixture', job)['ticket']
            lease = board.claim('tester', ticket)
            env = {'PC_TEST_STATE': str(root / 'state'), 'PC_TEST_AGENT': 'tester',
                   'PC_TEST_TICKET': ticket, 'PC_TEST_TOKEN': lease['token']}
            with patch.dict(os.environ, env, clear=True):
                zw.require_turn('pc')
                with patch.dict(os.environ, {'PC_TEST_TOKEN': 'wrong'}):
                    with self.assertRaisesRegex(zw.ZwError, 'not yours'): zw.require_turn('pc')
                with board.transaction('tester') as state:
                    state['active']['yield_by'] = queue.time.time() - 1
                    board.save(state)
                with patch.dict(os.environ, {'ZW_QUEUE_CLEANUP': '1'}):
                    with self.assertRaisesRegex(zw.ZwError, 'deadline'): zw.require_turn('pc')


if __name__ == '__main__':
    unittest.main()

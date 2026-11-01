"""Offline tests for zw: no console, no game, no WSL."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()

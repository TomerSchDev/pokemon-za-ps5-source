"""Tests for open_world.py. Needs the local PC game copy (romfs.bin); skips otherwise. All output goes to a temp folder
outside git.   py -3 -X utf8 port/open-world/test_open_world.py"""
import hashlib, json, os, shutil, struct, sys, tempfile, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'story-rando', 'tools'))
import open_world as ow  # noqa: E402

HAVE_GAME = os.path.exists(ow.DEFAULT_ROMFS)


def build(out, tier='open', base=()):
    return ow.cmd_build(types.SimpleNamespace(out=out, romfs=ow.DEFAULT_ROMFS, tier=tier, glide_early=False,
                                              base_mod=list(base)))


@unittest.skipUnless(HAVE_GAME, 'no local game copy')
class OpenWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='open-world-test-')
        cls.game = ow.Game(ow.DEFAULT_ROMFS)
        cls.mod = os.path.join(cls.tmp, 'a')
        build(cls.mod)
        cls.log = json.load(open(os.path.join(cls.mod, 'open-world-log.json')))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copy_mod(self, name):
        dst = os.path.join(self.tmp, name)
        shutil.copytree(self.mod, dst)
        return dst

    def test_floors_from_phase_table(self):
        self.assertEqual(ow.floors(self.game.read(ow.PHASE)), {'shop': 10000, 'freeroam': 21110, 'mable': 21600})

    def test_inventory_covers_every_condition(self):
        # every 'phase_condition' string in each table is reached by the structural walker
        for base in ow.TABLES:
            d = self.game.read(base + '.bin')
            self.assertEqual(len(ow.conditions(d)), d.count(b'phase_condition\0'), base)

    def test_expected_change_set(self):
        c = self.log['counts']
        self.assertEqual(c['taxi'], 29)
        self.assertEqual(c['shop'], 38)
        self.assertGreaterEqual(c['side_quest'], 100)
        self.assertEqual(set(self.log['files']), {ow.SHOP, ow.SUBQ, ow.MOMIJI, ow.MAPT})
        keys = {ch['key'] for ch in self.log['changes']}
        for k in ('sub_0001', 'sub_0002', 'sub_0003', 'sub_0118'):   # story-linked side quests stay gated
            self.assertNotIn(k, keys)

    def test_oracle_passes(self):
        self.assertEqual(ow.verify(self.game, self.mod, quiet=True), [])

    def test_deterministic(self):
        b = os.path.join(self.tmp, 'b')
        build(b)
        for p in self.log['files']:
            h = [hashlib.sha256(open(os.path.join(m, 'romfs', p), 'rb').read()).hexdigest() for m in (self.mod, b)]
            self.assertEqual(h[0], h[1], p)

    def test_oracle_rejects_protected_file(self):
        m = self.copy_mod('t1')
        p = 'ik_event/bin/trigger/main/trigger_main_02.bin'
        os.makedirs(os.path.dirname(os.path.join(m, 'romfs', p)), exist_ok=True)
        open(os.path.join(m, 'romfs', p), 'wb').write(self.game.read(p))
        self.assertTrue(any('protected' in x for x in ow.verify(self.game, m, quiet=True)))

    def test_oracle_rejects_wrong_value_and_stray_byte(self):
        m = self.copy_mod('t2')
        f = os.path.join(m, 'romfs', ow.MAPT)
        b = bytearray(open(f, 'rb').read())
        taxi = next(ch for ch in self.log['changes'] if ch['cat'] == 'taxi')
        b[taxi['offset'] + 4:taxi['offset'] + 9] = b'29999'           # not a floor
        b[16] ^= 1                                                     # outside any condition
        open(f, 'wb').write(b)
        bad = ow.verify(self.game, m, quiet=True)
        self.assertTrue(any('not a floor' in x for x in bad))
        self.assertTrue(any('outside any condition' in x for x in bad))

    def test_oracle_rejects_story_gate(self):
        # lower the first kept (non-openable) 5-digit '>=' map gate to the floor and expect a finding
        m = self.copy_mod('t3')
        d = bytearray(open(os.path.join(m, 'romfs', ow.MAPT), 'rb').read())
        sid = ow.story_strings(self.game)
        c = next(c for c in ow.conditions(self.game.read(ow.MAPT))
                 if c['op'] == ow.OP_GE and ow.classify(ow.MAPT, c, sid)[0] is None and len(c['args'][0][1]) == 5
                 and int(c['args'][0][1]) > 21110)
        o = c['args'][0][0]
        d[o + 4:o + 9] = b'21110'
        open(os.path.join(m, 'romfs', ow.MAPT), 'wb').write(d)
        self.assertTrue(any('not openable' in x for x in ow.verify(self.game, m, quiet=True)))

    def test_commutes_with_chapter_swap(self):
        """open-world after a 5<->6 chapter swap == chapter swap after open-world, byte for byte (the swap rewrites
        every phase_condition argument in every table; open-world re-plans on the swapped data)"""
        import chapter_swap
        g2 = ow.Game(ow.DEFAULT_ROMFS)
        for base in ow.TABLES:
            p = base + '.bin'
            s = bytearray(self.game.read(p)); chapter_swap.patch_conditions(s, '5', '6', [], p)
            g2.cache[p] = bytes(s)
        _, changes, _ = ow.plan(g2, 'open')
        swapped_then_open = ow.apply({p: g2.read(p) for p in self.log['files']}, changes)
        self.assertEqual(len(changes), len(self.log['changes']))
        for p in self.log['files']:
            a = bytearray(open(os.path.join(self.mod, 'romfs', p), 'rb').read())
            chapter_swap.patch_conditions(a, '5', '6', [], p)
            self.assertEqual(bytes(a), bytes(swapped_then_open[p]), p)

    def test_on_top_of_a_real_chapter_swap_mod(self):
        """end to end: chapter_swap.py writes a 6-before-5 mod; open-world builds on top of it (--base-mod) and the
        oracle passes against the swapped data; floors are unchanged (chapters 1-2 are fixed)"""
        import subprocess
        swap = os.path.join(self.tmp, 'swap56')
        subprocess.run([sys.executable, '-X', 'utf8', os.path.join(HERE, '..', 'story-rando', 'tools', 'chapter_swap.py'),
                        swap, '--digits', '5:6', '--move', '110:128', '--before', '87'], check=True,
                       stdout=subprocess.DEVNULL)
        out = os.path.join(self.tmp, 'on-swap')
        build(out, base=[swap])
        g = ow.Game(ow.DEFAULT_ROMFS, [swap])
        self.assertEqual(ow.verify(g, out, quiet=True), [])
        log = json.load(open(os.path.join(out, 'open-world-log.json')))
        self.assertEqual(log['floors'], self.log['floors'])
        self.assertEqual(log['counts'], self.log['counts'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

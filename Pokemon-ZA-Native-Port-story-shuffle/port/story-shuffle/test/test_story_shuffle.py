"""story-shuffle tests.  py -3 -m pytest port/story-shuffle/test  (or run this file directly)

Synthetic tests need no game data. The integration tests read the local PC game copy (read-only) and are skipped
when it is missing; they never write anything into the repository.
"""
import itertools, os, struct, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import fbedit as F  # noqa: E402
import story_shuffle as S  # noqa: E402

ROMFS = os.path.join(S.HL, 'qa-game-reference-20261030', 'romfs.bin')


def tab(typ, ints, kids):
    """a table with int32 scalar fields at the given field indices + child fields"""
    nf = max(list(ints) + list(kids)) + 1
    offs = [0] * nf
    inline = bytearray(4)
    for f in range(nf):
        if f in ints or f in kids:
            offs[f] = len(inline)
            inline += struct.pack('<i', ints.get(f, 0))
    return F.Tab(typ, 0, offs, len(inline), bytes(inline), kids)


def synth_phase(ids):
    ents = []
    for i in ids:
        cond = tab('Cond', {1: 1}, {0: F.Str('flag_condition'), 2: F.Vec([F.Str('flag_%d' % i)], 'str')})
        grp = tab('CondGroup', {}, {0: F.Vec([cond], 'Cond')})
        ents.append(tab('Phase', {0: i}, {1: F.Vec([grp], 'CondGroup')}))
    w = F.Writer(); w.put(tab('PhaseRoot', {}, {0: F.Vec(ents, 'Phase')}), root=True)
    return bytes(w.b)


IDS = [0, 10000, 32300, 40100, 42030, 50110, 50200, 53000, 61000, 64000, 70022, 75500, 80100, 87000, 90020, 103000]


class Synthetic(unittest.TestCase):
    def test_roundtrip(self):
        d = synth_phase(IDS)
        r = F.root(d, 'PhaseRoot')
        self.assertEqual([e.i32(0) for e in r.kids[0].items], IDS)
        w = F.Writer(); w.put(r, root=True)
        self.assertEqual(F.to_py(F.root(bytes(w.b), 'PhaseRoot')), F.to_py(r))

    def test_undeclared_field_rejected(self):
        bad = tab('Cmd', {0: 22, 3: 7}, {})
        w = F.Writer(); w.put(tab('PhaseRoot', {}, {0: F.Vec([tab('Phase', {0: 1}, {2: F.Vec([bad], 'Cmd')})], 'Phase')}), root=True)
        with self.assertRaises(ValueError): F.root(bytes(w.b), 'PhaseRoot')

    def test_set_str_shared_is_appended(self):
        s = F.Str('51200')
        w = F.Writer(); w.put(tab('Cond', {1: 5}, {0: F.Str('phase_condition'), 2: F.Vec([s], 'str')}), root=True)
        d = w.b
        slots = [q for q in range(0, len(d) - 3, 4) if struct.unpack_from('<I', d, q)[0] and
                 bytes(d[q + struct.unpack_from('<I', d, q)[0] + 4:][:5]) == b'51200']
        self.assertEqual(F.set_str(w, slots[0], '61200'), 'inplace')
        self.assertEqual(F.set_str(w, slots[0], '612000'), 'appended')

    def test_plan_rules(self):
        p = S.Plan([4, 6, 5, 7, 8], synth_phase(IDS))
        self.assertEqual(p.T('61000'), '51000'); self.assertEqual(p.T('50110'), '60110')
        self.assertEqual(p.T('40100'), '40100'); self.assertEqual(p.T('103000'), '103000')
        self.assertEqual((p.nxt(4), p.nxt(6), p.nxt(5), p.nxt(8)), (6, 5, 7, 9))
        self.assertEqual(p.prev(5), 6)
        # a range over adjacent chapters 6->7 is no longer adjacent (6 is at position 1, 7 at 3): clamped
        self.assertEqual(p.tr_args(8, ['62000', '70021'], 't'), ['52000', '59999'])
        # 5 -> 7 covered chapter 6 in vanilla; in the new order 6 is no longer between them: clamped too
        self.assertEqual(p.tr_args(8, ['53000', '70021'], 't'), ['63000', '69999'])
        # 4 -> 6 (positions 0, 1) is adjacent now but vanilla also covered 5: clamped
        self.assertEqual(p.tr_args(8, ['40800', '61999'], 't'), ['40800', '49999'])
        # open-ended ranges stay content ranges
        self.assertEqual(p.tr_args(8, ['10000', '62900'], 't'), ['10000', '52900'])
        self.assertEqual(p.tr_args(100, ['40450', '101000'], 't'), ['40450', '101000'])
        self.assertEqual(p.tr_args(5, ['51200'], 't'), ['61200'])

    def test_chapter4_fixed_and_seeds(self):
        with self.assertRaises(SystemExit): S.Plan([5, 4, 6, 7, 8], synth_phase(IDS))
        seen = {tuple(S.order_from_seed(s)) for s in range(200)}
        self.assertTrue(all(o[0] == 4 and sorted(o) == [4, 5, 6, 7, 8] for o in seen))
        self.assertEqual(len(seen), 24)
        self.assertEqual(S.order_from_seed(7), S.order_from_seed(7))


@unittest.skipUnless(os.path.exists(ROMFS), 'local PC game copy not present')
class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = S.Romfs(ROMFS)

    def test_identity_is_semantically_vanilla(self):
        files, pj, plan = S.generate(self.g, [4, 5, 6, 7, 8], lua=True)
        self.assertEqual(set(files), {S.PHASE, S.TRAINER})
        self.assertEqual(F.to_py(F.root(files[S.PHASE], 'PhaseRoot')), F.to_py(F.root(self.g.read(S.PHASE), 'PhaseRoot')))
        self.assertEqual(F.to_py(F.root(files[S.TRAINER], 'TrigRoot')), F.to_py(F.root(self.g.read(S.TRAINER), 'TrigRoot')))

    def test_all_24_orders_pass_the_oracle(self):
        import oracle
        for mid in itertools.permutations(S.SHUFFLED):
            order = [4] + list(mid)
            files, pj, plan = S.generate(self.g, order, lua=True)
            res = oracle.check(self.g, files, plan)
            self.assertTrue(res['ok'], (order, res['fails'][:5]))
            for c in S.MIDDLE:
                self.assertEqual(res['chain'][c]['next'], plan.nxt(c))


if __name__ == '__main__':
    unittest.main()

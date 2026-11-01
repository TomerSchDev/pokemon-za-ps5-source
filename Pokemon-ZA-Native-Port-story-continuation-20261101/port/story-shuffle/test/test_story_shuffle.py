"""story-shuffle tests.  py -3 -m pytest port/story-shuffle/test  (or run this file directly)

Synthetic tests need no game data. The integration tests read the local PC game copy (read-only) and are skipped
when it is missing; they never write anything into the repository.
"""
import itertools, os, struct, sys, unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
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

    def test_invalid_order_is_not_an_optimizable_assert(self):
        with self.assertRaises(ValueError): S.Plan([4, 5, 5, 7, 8], synth_phase(IDS))

    def test_cli_refuses_existing_output_before_reading_game(self):
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / 'keep.txt'; marker.write_text('unchanged')
            with patch.object(sys, 'argv', ['story_shuffle', root, '--seed', '1']), patch.object(S, 'Romfs') as game:
                with self.assertRaises(SystemExit): S.main()
                game.assert_not_called()
            self.assertEqual(marker.read_text(), 'unchanged')

    def test_cli_failed_oracle_never_exports_mod(self):
        import oracle
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / 'new-failed-output'
            with patch.object(sys, 'argv', ['story_shuffle', str(out), '--seed', '1']), \
                 patch.object(S, 'Romfs'), patch.object(S, 'generate', return_value=({'unsafe.bin': b'fixture'}, {'warnings': []}, None)), \
                 patch.object(oracle, 'check', return_value={'ok': False, 'summary': 'deliberate failure'}):
                with self.assertRaises(SystemExit) as exc: S.main()
            self.assertEqual(exc.exception.code, 1)
            self.assertTrue((out / 'oracle.json').is_file())
            self.assertFalse((out / 'romfs').exists())

    def test_condition_factories_and_all_arguments_are_distinct(self):
        import oracle
        phase = tab('Cond', {1: 1}, {0: F.Str('phase_condition'), 2: F.Vec([F.Str('40800')], 'str')})
        work = tab('Cond', {1: 1}, {0: F.Str('work_condition'),
                    2: F.Vec([F.Str('SYS_WORK_PHASE'), F.Str('40800'), F.Str('0')], 'str')})
        p, w = oracle.tree_conds(phase)[0], oracle.tree_conds(work)[0]
        self.assertEqual(p.kind, 'phase_condition')
        self.assertEqual(w.kind, 'work_condition')
        self.assertEqual(w.args, ('SYS_WORK_PHASE', '40800', '0'))
        self.assertNotEqual(p, w)
        self.assertEqual(w.evidence()['factory_key'], 'work_condition')
        self.assertEqual(w.evidence()['serialized_operator'], 1)
        self.assertEqual(w.evidence()['runtime_operator'], 2)
        self.assertTrue(w.evidence()['normalization_proven'])

    def test_proved_wire_ranges_include_the_correct_endpoints(self):
        import oracle
        seq = [0, 1, 2, 3, 4]
        expected = {7: {2}, 8: {1, 2, 3}, 100: {1, 2}, 101: {2, 3}}
        for wire, accepted in expected.items():
            self.assertEqual(oracle.ev(wire, ['1', '3'], seq), accepted)
        self.assertEqual([oracle.normalize_wire(i) for i in range(1, 9)], [2, 3, 6, 4, 7, 5, 8, 9])

    def test_serialized_operator_is_a_native_u32(self):
        import oracle
        node = tab('Cond', {1: -1}, {0: F.Str('phase_condition'), 2: F.Vec([F.Str('1')], 'str')})
        record = oracle.tree_conds(node)[0]
        self.assertEqual(record.op, 0xffffffff)
        self.assertEqual(record.evidence()['serialized_operator'], 0xffffffff)
        self.assertEqual(record.evidence()['runtime_operator'], 0xffffffff)

    def test_missing_lua_is_blocked_before_read_or_output(self):
        from types import SimpleNamespace
        game = SimpleNamespace(has=lambda p: False, read=lambda p: self.fail('read before missing-Lua guard'))
        with self.assertRaisesRegex(ValueError, 'Lua source required'): S.generate(game, [4, 6, 5, 7, 8])
        with tempfile.TemporaryDirectory() as parent:
            out = Path(parent) / 'blocked-context'
            with patch.object(sys, 'argv', ['story_shuffle', str(out), '--seed', '1']), patch.object(S, 'Romfs', return_value=game):
                with self.assertRaisesRegex(ValueError, 'Lua source required'): S.main()
            self.assertFalse(out.exists())


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

    def test_all_24_orders_known_invariants_and_unknown_guards(self):
        import oracle
        for mid in itertools.permutations(S.SHUFFLED):
            order = [4] + list(mid)
            files, pj, plan = S.generate(self.g, order, lua=True)
            res = oracle.check(self.g, files, plan)
            self.assertEqual(res['invariant_failures'], [], (order, res['invariant_failures'][:5]))
            self.assertEqual(res['ok'], res['schema_complete'])
            self.assertEqual(res['schema_complete'], not res['unmodeled_conditions'])
            for c in S.MIDDLE:
                self.assertEqual(res['chain'][c]['next'], plan.nxt(c))


@unittest.skipUnless(os.path.exists(ROMFS), 'local PC game copy not present')
class OracleMutations(unittest.TestCase):
    """Corrupt real generated output: the checker must reject each independently.

    STORY_TEST_ORACLE can pin a preserved historical checker for before/after evidence.
    """
    @classmethod
    def setUpClass(cls):
        import oracle
        if os.environ.get('STORY_TEST_ORACLE'):
            import importlib.util
            spec = importlib.util.spec_from_file_location('historical_oracle', os.environ['STORY_TEST_ORACLE'])
            oracle = importlib.util.module_from_spec(spec); spec.loader.exec_module(oracle)
        cls.oracle = oracle
        from audit import Inputs
        cls.g = Inputs(S.Romfs(ROMFS))
        cls.files, cls.pj, cls.plan = S.generate(cls.g, [4, 6, 5, 7, 8], lua=True)

    def rejected(self, files, message):
        res = self.oracle.check(self.g, files, self.plan)
        self.assertFalse(res['ok'], 'corrupted output was accepted')
        self.assertTrue(any(message in f for f in res['fails']), res['fails'][:6])

    def test_changed_condition_operator(self):
        files = dict(self.files)
        path = 'ik_event/bin/trigger/main/trigger_main_06.bin'
        root = F.root(files.get(path, self.g.read(path)), 'TrigRoot')
        found = []
        def change(node, parents):
            if not found and node.type == 'Cond' and node.kids.get(0) and node.kids[0].text() == 'phase_condition' and node.i32(1) == 1:
                node.set_i32(1, 2); found.append(True)
        S.walk(root, change)
        self.assertTrue(found)
        w = F.Writer(); w.put(root, root=True); files[path] = bytes(w.b)
        self.rejected(files, 'operator changed')

    def test_missing_lua_translation(self):
        self.assertTrue(self.pj.get('lua_constants'))
        files = dict(self.files); files.pop(S.LUA, None)
        self.rejected(files, 'Lua constants')

    def test_old_dlc_false_acceptance_is_rejected(self):
        import lua_context
        data = self.g.read(S.LUA)
        _, parsed, entries = lua_context.reviewed(data)
        # The former four-edit swap modified MAIN once and three unrelated DLC K's.
        bad = bytearray(self.files[S.LUA])
        affected = []
        for entry, offset in entries:
            value = entry['original_value']; new = int(self.plan.T(str(value)))
            if entry['namespace'] == ['dlc'] and value != new:
                struct.pack_into('<q', bad, offset, new); affected.append((entry['prototype'], entry['constant_index']))
        self.assertEqual(affected, [('r/2397', 4), ('r/2397', 12), ('r/5884', 8)])
        files = dict(self.files); files[S.LUA] = bytes(bad)
        self.rejected(files, 'DLC/unknown preserved')
        # The original shared predicate predicts this exact corrupt tree (negative control).
        import luadump
        old = luadump.load(data); corrupt = luadump.load(bad)
        ids = {v for c in S.MIDDLE for v in self.plan.block[c]}
        edits = []
        def legacy(proto, changed, path='r'):
            has_phase = any(isinstance(k, str) and 'PHASE' in k for k in proto['k'])
            for i, value in enumerate(proto['k']):
                if type(value) is int and (value in ids or (has_phase and len(str(value)) == 5 and S.chap(str(value)) in S.MIDDLE)):
                    expected = int(self.plan.T(str(value)))
                else: expected = value
                self.assertEqual(changed['k'][i], expected)
                if expected != value: edits.append((path, i))
            for i, (a, b) in enumerate(zip(proto['p'], changed['p'])): legacy(a, b, path + '/' + str(i))
        legacy(old, corrupt)
        self.assertEqual(len(edits), 4)
        # Execute the exact preserved r2 checker, not only the explanatory predicate.
        import importlib.util
        spec = importlib.util.spec_from_file_location('negative_control_r2', Path(HERE) / 'fixtures/legacy_oracle_r2.py')
        old_checker = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = old_checker; spec.loader.exec_module(old_checker)
        self.assertEqual(old_checker.lua_failures(data, bytes(bad), self.plan), [])
        self.assertTrue(old_checker.check(self.g, files, self.plan)['ok'])

    def test_only_reviewed_main_constant_and_all_other_bytes_preserved(self):
        import lua_context, luadump
        original = self.g.read(S.LUA); changed = self.files[S.LUA]
        _, _, entries = lua_context.reviewed(original)
        self.assertEqual(len(entries), 18)
        self.assertEqual(sum(e['namespace'] == ['dlc'] for e, _ in entries), 17)
        self.assertEqual(self.pj['lua_constants'][0]['namespace'], 'main')
        self.assertEqual(len(self.pj['lua_constants']), 1)
        permitted = set()
        for entry, offset in entries:
            self.assertEqual(struct.unpack_from('<q', original, offset)[0], entry['original_value'])
            if entry['namespace'] == ['dlc']: self.assertEqual(original[offset:offset+8], changed[offset:offset+8])
            else: permitted.update(range(offset, offset+8))
        self.assertTrue(all(a == b or i in permitted for i, (a, b) in enumerate(zip(original, changed))))
        self.assertEqual(self.oracle.lua_failures(original, changed, self.plan), [])

    def test_lua_unreviewed_source_and_mixed_or_incomplete_manifest_block(self):
        import hashlib, json, lua_context
        original = self.g.read(S.LUA)
        with self.assertRaisesRegex(ValueError, 'source is outside'): S.lua_patch(self.plan, original + b'unknown', [])
        # Repin the fixture checksum only to exercise the semantic guard, not the integrity guard.
        for mode in ('mixed', 'unknown', 'incomplete'):
            manifest = json.loads(lua_context.MANIFEST.read_bytes())
            if mode == 'incomplete': manifest['entries'][0]['bounded_use_closure_complete'] = False
            else: manifest['entries'][0]['namespace'] = ['main', 'dlc'] if mode == 'mixed' else ['unknown']
            raw = json.dumps(manifest).encode()
            with patch.object(Path, 'read_bytes', return_value=raw), patch.object(lua_context, 'MANIFEST_SHA256', hashlib.sha256(raw).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'unknown, mixed or incompletely'): S.lua_patch(self.plan, original, [])

    def test_unknown_lua_cli_never_creates_output(self):
        from types import SimpleNamespace
        original = self.g.read(S.LUA)
        game = SimpleNamespace(has=self.g.has, read=lambda p: original + b'unknown' if p == S.LUA else self.g.read(p))
        with tempfile.TemporaryDirectory() as parent:
            out = Path(parent) / 'blocked-lua'
            with patch.object(sys, 'argv', ['story_shuffle', str(out), '--seed', '1']), patch.object(S, 'Romfs', return_value=game):
                with self.assertRaisesRegex(ValueError, 'source is outside'): S.main()
            self.assertFalse(out.exists())

    def test_wrong_rank_argument(self):
        files = dict(self.files)
        sf = S.SlotFile(files[S.MAINQ])
        candidates = [sl for t, op, sl in sf.conds('rank_up_point_condition')
                      if len(sl) >= 3 and int(sf.get(sl[0])) in (32000, 35000, 38000, 41000, 45000)]
        self.assertTrue(candidates)
        sf.put(candidates[0][-1], '999')
        files[S.MAINQ] = bytes(sf.w.b)
        self.rejected(files, 'rank-up full arguments')

    def test_wrong_boundary_rank_cap(self):
        files = dict(self.files); root = F.root(files[S.TRAINER], 'TrigRoot')
        found = False
        for wrapper in root.kids[0].items:
            trigger = wrapper.kids.get(0)
            if not trigger or 2 not in trigger.kids: continue
            for case in trigger.kids[2].items:
                if ('phase_condition', 1, ['42030']) not in S.cond_list(case): continue
                for cmd in S.cmd_list(case):
                    if cmd.i32(0) == 111: break
                    if cmd.i32(0) == 18:
                        args = S.cmd_args(cmd); S.set_vstr(cmd, 1, [str(int(args[0]) + 1)] + args[1:]); found = True
        self.assertTrue(found)
        w = F.Writer(); w.put(root, root=True); files[S.TRAINER] = bytes(w.b)
        self.rejected(files, 'boundary rank caps')

    def test_condition_factory_substitution(self):
        files = dict(self.files)
        path = 'ik_event/bin/trigger/main/trigger_main_06.bin'
        root = F.root(files.get(path, self.g.read(path)), 'TrigRoot')
        found = []
        def change(node, parents):
            if not found and node.type == 'Cond' and node.kids.get(0) and node.kids[0].text() == 'phase_condition':
                node.kids[0] = F.Str('work_condition')
                S.set_vstr(node, 2, ['SYS_WORK_PHASE'] + S.sv(node.kids[2]))
                found.append(True)
        S.walk(root, change)
        self.assertTrue(found)
        w = F.Writer(); w.put(root, root=True); files[path] = bytes(w.b)
        self.rejected(files, 'condition factory changed')

    def test_proved_factories_keep_kind_and_unabridged_arguments(self):
        res = self.oracle.check(self.g, self.files, self.plan)
        self.assertTrue(res['ok'], res['fails'][:5])
        rows = res['condition_pairs']
        work = [r for r in rows if r['vanilla']['kind'] == 'work_condition']
        phase = [r for r in rows if r['vanilla']['kind'] == 'phase_condition' and r['vanilla']['operator'] == 101]
        self.assertEqual((len(work), len(phase)), (0, 2))
        scalar_extra = [r for r in rows if r['vanilla']['kind'] == 'phase_condition' and
                        r['vanilla']['operator'] == 1 and len(r['vanilla']['arguments']) == 2]
        self.assertEqual(len(scalar_extra), 8)
        self.assertTrue(all(r['vanilla']['arguments'][0] == 'SYS_WORK_PHASE' and
                            r['vanilla']['arguments'][-1] == '0' for r in work))
        self.assertTrue(all(r['vanilla']['normalization_proven'] for r in rows))
        self.assertEqual({r['vanilla']['operator'] for r in phase}, {101})

    def unknown_fixture(self):
        from types import SimpleNamespace
        files, pj, plan = S.generate(self.g, [4, 5, 6, 7, 8], lua=True)
        path = 'ik_event/bin/trigger/main/trigger_main_06.bin'
        root = F.root(self.g.read(path), 'TrigRoot'); found = []
        def change(node, parents):
            if not found and node.type == 'Cond' and node.kids.get(0) and node.kids[0].text() == 'phase_condition':
                node.set_i32(1, 999); found.append(True)
        S.walk(root, change); self.assertTrue(found)
        w = F.Writer(); w.put(root, root=True); changed = bytes(w.b)
        files[path] = changed
        game = SimpleNamespace(read=lambda p: changed if p == path else self.g.read(p), has=self.g.has)
        return game, files, pj, plan

    def test_untouched_unknowns_are_not_semantic_passes(self):
        game, files, pj, plan = self.unknown_fixture()
        res = self.oracle.check(game, files, plan)
        self.assertFalse(res['ok'])
        self.assertEqual(len(res['unmodeled_conditions']), 1)
        self.assertTrue(all(r['structurally_unchanged'] and not r['semantic_pass']
                            for r in res['unmodeled_conditions']))

    def test_blocked_real_case_cli_never_exports_game_files(self):
        # Real oracle verdict over the real generated tables; only avoid regenerating the same fixture.
        game, files, pj, plan = self.unknown_fixture()
        with tempfile.TemporaryDirectory() as parent:
            out = Path(parent) / 'blocked-output'
            with patch.object(sys, 'argv', ['story_shuffle', str(out), '--order', '4,6,5,7,8']), \
                 patch.object(S, 'Romfs', return_value=game), \
                 patch.object(S, 'generate', return_value=(files, pj, plan)):
                with self.assertRaises(SystemExit) as exc: S.main()
            self.assertEqual(exc.exception.code, 1)
            self.assertTrue((out / 'oracle.json').is_file())
            self.assertFalse((out / 'romfs').exists())
            self.assertEqual(sorted(p.name for p in out.iterdir()), ['oracle.json', 'shuffle-plan.json'])


if __name__ == '__main__':
    unittest.main()

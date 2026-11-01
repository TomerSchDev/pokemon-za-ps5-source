"""Oracle for a story-shuffle patch set: re-reads the patched files and checks them against the vanilla data.

Hard checks (any failure -> ok False):
  phase.bin   ids strictly increasing; same entries as vanilla; each middle block contiguous with digit = position
  conditions  every phase_condition in every table: ==/!= hit the same entries; a single threshold keeps the same
              entries inside its own chapter; nothing that was satisfiable becomes impossible or always-true; ranges
              are not inverted and stay contiguous in the new order
  chain       every chapter-end case: phase == new last(c), the intro after the 111 command is the next chapter's
              intro (events of nxt(c) only), and the new exit flag of last(c) is set by one of the case's own events
  quests      main_05_00 gate = exit flag of the chapter before 5; middle main quests gated inside their own chapter
  rank        rank caps (cmd 18) and SYS_WORK_ROYALE_MATCHING_INFO never decrease along the new phase order;
              rank-up points never decrease by position
Soft findings (reported, not failures): ranges clamped, entries gained/lost by "onward"/"until" ranges.
"""
import re
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
import fbedit as F
import story_shuffle as S

WIRE_TO_RUNTIME = {1: 2, 2: 3, 3: 6, 4: 4, 5: 7, 6: 5, 7: 8, 8: 9}
SEMANTICS_PROFILE = 'za202-condition-numeric-1'
SEMANTICS_NSO_SHA256 = '2308530d73b7fea60bb845ad57d9b1f10d3ff213f89c01f73627dc8224f43ef9'


def normalize_wire(op):
    op &= 0xffffffff
    return WIRE_TO_RUNTIME.get(op, op)


def comparison_arguments(condition):
    args = list(condition.args)
    if condition.kind == 'phase_condition': return args
    # Proven WorkCondition alias in this corpus. Do not extrapolate to other work kinds,
    # selectors or argument layouts. For equality the trailing zero is unused, but retained.
    if condition.kind == 'work_condition' and condition.op == 1 and len(args) == 3 and \
       args[0] == 'SYS_WORK_PHASE' and args[2] == '0': return args[1:]
    return None


def runtime_eval(op, value, args):
    if op == 0: return True
    if op == 1: return False
    if op == 2: return value == args[0]
    if op == 3: return value != args[0]
    if op == 4: return value < args[0]
    if op == 5: return value <= args[0]
    if op == 6: return value > args[0]
    if op == 7: return value >= args[0]
    if op == 8: return args[0] < value < args[1]
    if op == 9: return args[0] <= value <= args[1]
    if op == 100: return args[0] <= value < args[1]
    if op == 101: return args[0] < value <= args[1]
    raise ValueError('unmodeled runtime numeric operator')


@dataclass(frozen=True)
class Condition:
    """The input discriminator identifies the native factory; op numbers are not global enums.

    Keep every original argument, including SYS_WORK_PHASE and any trailing type/mode.
    Native callback addresses belong in separately proved RE evidence, not guessed here.
    """
    kind: str
    op: int
    args: tuple
    table_offset: int

    def evidence(self):
        return {'kind': self.kind, 'factory_key': self.kind,
                'operator': self.op, 'serialized_operator': self.op,
                'runtime_operator': normalize_wire(self.op), 'normalization_proven': True,
                'semantics_profile': SEMANTICS_PROFILE,
                'arguments': list(self.args), 'table_offset': self.table_offset}


def relevant(kind, args):
    return kind == 'phase_condition' or (kind == 'work_condition' and args[:1] == ['SYS_WORK_PHASE'])


def ev(op, args, seq):
    try:
        a = [int(x) for x in args]
    except ValueError:
        return None
    runtime = normalize_wire(op)
    if runtime not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 100, 101): return None
    return {i for i, x in enumerate(seq) if runtime_eval(runtime, x, a)}


def tree_conds(root):
    out = []

    def fn(t, path):
        if t.type == 'Cond' and 0 in t.kids and 2 in t.kids:
            name, args = t.kids[0].text(), S.sv(t.kids[2])
            if relevant(name, args): out.append(Condition(name, (t.i32(1) or 0) & 0xffffffff, tuple(args), t.pos))
    S.walk(root, fn)
    return out


def slot_conds(data):
    sf = S.SlotFile(data)
    out = {}
    for kind in ('phase_condition', 'work_condition'):
        for t, op, slots in sf.conds(kind):
            args = [sf.get(x) for x in slots]
            if relevant(kind, args): out[t] = Condition(kind, (op or 0) & 0xffffffff, tuple(args), t)
    return out


def lua_failures(original, changed, plan):
    """Independent prototype reader: verify every changed constant and unchanged instruction/string.

    Unlike the generator's byte-offset writer this compares the full parsed Lua tree.
    The classification of numeric phase constants is still the shared legacy heuristic,
    not an independent proof of each instruction's semantic/dataflow use.
    It also rejects --no-lua when the chosen order requires a translated constant.
    """
    sys.path.insert(0, str(Path(S.REPO) / 'port/story-rando/tools'))
    import luadump
    a, b = luadump.load(original), luadump.load(changed)
    phase_ids = {i for c in S.MIDDLE for i in plan.block[c]}
    fails = []

    def compare(vanilla, new, path):
        for key in vanilla:
            if key not in ('k', 'p') and vanilla[key] != new.get(key):
                fails.append('Lua instruction/prototype changed: %s %s' % (path, key))
        expected = []
        has_phase = any(isinstance(k, str) and 'PHASE' in k for k in vanilla['k'])
        for value in vanilla['k']:
            if type(value) is int and (value in phase_ids or (has_phase and len(str(value)) == 5 and S.chap(str(value)) in S.MIDDLE)):
                expected.append(int(plan.T(str(value))))
            else: expected.append(value)
        if expected != new['k']: fails.append('Lua constants differ from content translation: ' + path)
        if len(vanilla['p']) != len(new['p']):
            fails.append('Lua prototype count changed: ' + path)
        else:
            for i, (x, y) in enumerate(zip(vanilla['p'], new['p'])): compare(x, y, path + '/' + str(i))
    compare(a, b, 'r')
    return fails


def check(g, files, plan):
    fails, soft = [], []
    unmodeled, input_sha256, condition_counts, condition_pairs, unsupported_messages = [], {}, {}, [], []
    van_ph = F.root(g.read(S.PHASE), 'PhaseRoot')
    new_ph = F.root(files[S.PHASE], 'PhaseRoot')
    vseq = [e.i32(0) or 0 for e in van_ph.kids[0].items]
    nseq = [e.i32(0) or 0 for e in new_ph.kids[0].items]
    inv = {int(plan.T(str(v))): v for v in vseq}
    ident_new = [inv[x] for x in nseq]                      # vanilla identity of each new position
    if any(b <= a for a, b in zip(nseq[1:], nseq[2:])): fails.append('phase ids not strictly increasing')
    if sorted(ident_new) != sorted(vseq): fails.append('phase entries differ from vanilla')
    for c in S.MIDDLE:
        idx = [i for i, x in enumerate(nseq) if S.chap(str(x)) == plan.digit(c) and inv[x] in plan.block[c]]
        if len(idx) != len(plan.block[c]) or idx != list(range(idx[0], idx[0] + len(idx))):
            fails.append('block of chapter %d not contiguous at its position' % c)
    vpos = {v: i for i, v in enumerate(vseq)}
    blocks = {c: {vpos[i] for i in plan.block[c]} for c in S.MIDDLE}

    def ident_set(s, seq_ident): return {vpos[seq_ident[i]] for i in s}

    n_cond = 0
    clamped = {(w['where'], tuple(w['vanilla'])) for w in plan.warn}

    def judge(where, vanilla, changed):
        nonlocal n_cond
        condition_counts[vanilla.kind] = condition_counts.get(vanilla.kind, 0) + 1
        condition_pairs.append({'source': where, 'vanilla': vanilla.evidence(), 'changed': changed.evidence()})
        if changed.kind != vanilla.kind:
            fails.append('%s: condition factory changed %s->%s at%d' %
                         (where, vanilla.kind, changed.kind, vanilla.table_offset))
            return
        if changed.op != vanilla.op:
            fails.append('%s: phase condition operator changed %s->%s at%d' %
                         (where, vanilla.op, changed.op, vanilla.table_offset))
        op = vanilla.op
        va, na = comparison_arguments(vanilla), comparison_arguments(changed)
        # WorkCondition and PhaseCondition are separately registered native factories.
        # Until its evaluator is proved, never apply the phase operator model to work_condition.
        if va is None or na is None:
            reason = 'unproved factory argument layout'
        else:
            runtime = normalize_wire(op)
            valid_arities = (0, 1, 2) if runtime in (0, 1) else (1, 2) if runtime in range(2, 8) else (2,) if runtime in (8, 9, 100, 101) else ()
            # Both native callbacks parse a,b. Scalar comparisons use a and ignore b;
            # an explicit zero b in a phase condition is not a different condition factory.
            reason = ('unsupported phase condition shape' if len(va) not in valid_arities or
                      len(na) not in valid_arities else None)
        if reason:
            record = {'source': where, 'input_sha256': input_sha256[where], 'reason': reason,
                      'vanilla': vanilla.evidence(), 'changed': changed.evidence(),
                      'structurally_unchanged': (vanilla.kind, vanilla.op, vanilla.args) ==
                                                (changed.kind, changed.op, changed.args),
                      'semantic_pass': False}
            unmodeled.append(record)
            message = '%s: %s %s op%s %s->%s at%d' % (reason, where, vanilla.kind, op, va, na, vanilla.table_offset)
            fails.append(message); unsupported_messages.append(message)
            return
        if any(not a.isascii() or not a.isdigit() or not 0 <= int(a) <= 0xffffffff for a in va + na):
            fails.append('unmodeled unsigned phase argument: %s %s->%s' % (where, va, na)); return
        V = ev(op, va, vseq); N = ev(op, na, nseq)
        if V is None or N is None:
            fails.append('uninterpretable phase condition: %s op%s %s->%s' % (where, op, va, na)); return
        n_cond += 1
        Vi = ident_set(V, vseq); Ni = ident_set(N, ident_new)
        tag = '%s op%s %s->%s' % (where, op, va, na)
        if op in (1, 2):
            if Vi != Ni: fails.append('equality changed: ' + tag)
            return
        if V and not N: fails.append('became impossible: ' + tag)
        if len(V) < len(vseq) and len(N) == len(nseq): fails.append('became always true: ' + tag)
        if N and sorted(N) != list(range(min(N), max(N) + 1)): fails.append('not contiguous in the new order: ' + tag)
        if op in S.RANGE_OPS and len(na) == 2 and na[0].isdigit() and na[1].isdigit() and int(na[0]) > int(na[1]):
            fails.append('inverted range: ' + tag)
        c = S.chap(va[0]) if va else None
        if c in S.MIDDLE and (Vi & blocks[c]) != (Ni & blocks[c]):
            if (where, tuple(va)) in clamped: soft.append('clamped range loses entries in its own chapter: ' + tag)
            else: fails.append('own-chapter entries changed: ' + tag)
        if Ni - Vi or Vi - Ni:
            if (where, tuple(va)) in clamped: soft.append('clamped: ' + tag)
            elif op in S.RANGE_OPS or op in (3, 4, 5, 6):
                soft.append('content threshold/range now covers %d entries more, %d fewer (other chapters moved): %s'
                            % (len(Ni - Vi), len(Vi - Ni), tag))

    for p in S.TRIGGERS:
        if not g.has(p): continue
        data = g.read(p)
        input_sha256[p] = hashlib.sha256(data).hexdigest()
        vc = tree_conds(F.root(data, 'TrigRoot'))
        nc = tree_conds(F.root(files[p], 'TrigRoot')) if p in files else vc
        if len(vc) != len(nc): fails.append('%s: condition count changed' % p); continue
        for vanilla, changed in zip(vc, nc): judge(p, vanilla, changed)
    for p in S.OTHER:
        if not g.has(p): continue
        data = g.read(p)
        input_sha256[p] = hashlib.sha256(data).hexdigest()
        vc = slot_conds(data)
        nc = slot_conds(files[p]) if p in files else vc
        for t, vanilla in vc.items():
            if t not in nc: fails.append('%s: condition at %d lost' % (p, t)); continue
            judge(p, vanilla, nc[t])
        for t in nc.keys() - vc.keys(): fails.append('%s: unexpected phase/work condition at%d' % (p, t))

    if g.has(S.LUA):
        fails.extend(lua_failures(g.read(S.LUA), files.get(S.LUA, g.read(S.LUA)), plan))

    # chain
    tr = F.root(files.get(S.TRAINER, g.read(S.TRAINER)), 'TrigRoot')
    van_tr = {S.TRAINER: F.root(g.read(S.TRAINER), 'TrigRoot')}
    vb, _ = S.find_boundaries(van_tr, plan)
    exit_flag = {}
    for e in new_ph.kids[0].items:
        exit_flag[e.i32(0) or 0] = [S.sv(cd.kids[2])[0] for g_ in e.kids[1].items for cd in g_.kids[0].items
                                    if cd.kids[0].text() == 'flag_condition'] if 1 in e.kids else []
    chain = {}
    for c in S.MIDDLE:
        last_new = plan.T(str(plan.block[c][-1]))
        cases = []
        for w in tr.kids[0].items:
            t = w.kids.get(0)
            if t is None or 2 not in t.kids: continue
            for case in t.kids[2].items:
                if ['phase_condition', 1, [last_new]] in [list(x) for x in S.cond_list(case)]:
                    cmds = S.cmd_list(case)
                    if 111 in [x.i32(0) for x in cmds]: cases.append(cmds)
        if len(cases) != 1: fails.append('chapter %d: %d end cases' % (c, len(cases))); continue
        cmds = cases[0]
        k = [x.i32(0) for x in cmds].index(111) + 1
        own_ev, intro_ev = S.events(cmds[:k]), S.events(cmds[k:])
        vanilla_caps = [int(S.cmd_args(x)[0]) for x in vb[c]['own'] if x.i32(0) == 18]
        actual_caps = [int(S.cmd_args(x)[0]) for x in cmds[:k] if x.i32(0) == 18]
        expected_caps = [v + plan.pos[c] - (c - 4) for v in vanilla_caps]
        if actual_caps != expected_caps: fails.append('chapter%d boundary rank caps differ by position' % c)
        nx = plan.nxt(c)
        want = S.events(vb[nx - 1]['intro'])
        chs = {int(e[4:6]) for e in intro_ev if re.match(r'Ev_m\d\d_', e)}
        if chs != {nx} or intro_ev != want: fails.append('chapter %d end runs intro %s, want chapter %d %s' % (c, intro_ev, nx, want))
        xf = exit_flag[int(last_new)]
        if not any('flag_' + e in xf for e in own_ev + intro_ev): fails.append('chapter %d: exit flag %s not set by its own end events %s' % (c, xf, own_ev))
        chain[c] = dict(next=nx, own_events=own_ev, intro_events=intro_ev, exit_flag=xf)
    # rank caps / matching info along the new order
    caps, match = [], []
    for e in new_ph.kids[0].items:
        for x in (e.kids[2].items if 2 in e.kids else []):
            a = S.cmd_args(x)
            if x.i32(0) == 18 and a and a[0].isdigit(): caps.append(int(a[0]))
            if x.i32(0) == 9 and len(a) == 2 and a[0] == 'SYS_WORK_ROYALE_MATCHING_INFO': match.append(int(a[1]))
    if caps != sorted(caps): fails.append('rank caps decrease: %s' % caps)
    if match != sorted(match): fails.append('matching info decreases: %s' % match)
    # quests
    sf = S.SlotFile(files.get(S.MAINQ, g.read(S.MAINQ)))
    pc = plan.prev(5)
    want_gate = exit_flag[int(plan.T(str(plan.block[pc][-1])))][0]
    gate = [sf.get(x) for x in S.quest_start_slots(sf, 'main_05_00')]
    if gate != [want_gate]: fails.append('main_05_00 start gate %s, want %s' % (gate, want_gate))
    vsf = S.SlotFile(g.read(S.MAINQ))
    vpoints = {t: [vsf.get(x) for x in sl] for t, op, sl in vsf.conds('rank_up_point_condition')}
    vpts = {t: int(args[0]) for t, args in vpoints.items()}
    by_chapter = {32000: 4, 35000: 5, 38000: 6, 41000: 7, 45000: 8}
    pts = {t: int(sf.get(sl[0])) for t, op, sl in sf.conds('rank_up_point_condition')}
    full_points = {t: [sf.get(x) for x in sl] for t, op, sl in sf.conds('rank_up_point_condition')}
    point_args_by_chapter = {by_chapter[int(args[0])]: args for args in vpoints.values() if int(args[0]) in by_chapter}
    seq = []
    for t, v in vpts.items():
        c = by_chapter.get(v)
        if c is None: continue
        want = [k for k, cc in by_chapter.items() if cc == 4 + plan.pos[c]][0]
        if pts.get(t) != want: fails.append('rank-up of chapter %d: %s, want %d' % (c, pts.get(t), want))
        if full_points.get(t) != point_args_by_chapter[4 + plan.pos[c]]:
            fails.append('rank-up full arguments differ for chapter%d' % c)
        seq.append((plan.pos[c], pts.get(t)))
    seq.sort()
    if [v for _, v in seq] != sorted(v for _, v in seq): fails.append('rank-up points decrease by position: %s' % seq)
    rank = dict(caps=caps, matching=match, rank_up_points_by_position=seq)
    summary = '%d conditions checked, %d hard failures, %d soft notes' % (n_cond, len(fails), len(soft))
    invariant_failures = [f for f in fails if f not in set(unsupported_messages)]
    return dict(ok=not fails, summary=summary, fails=fails, soft=soft, chain=chain, rank=rank,
                unmodeled_conditions=unmodeled, condition_factory_counts=condition_counts,
                condition_input_sha256=input_sha256, condition_pairs=condition_pairs,
                invariant_failures=invariant_failures, schema_complete=not unmodeled,
                semantics_scope='Proved wire normalization and unsigned numeric PhaseCondition; WorkCondition only the proved SYS_WORK_PHASE equality alias. Unknown layouts remain blocked.',
                semantics_profile=SEMANTICS_PROFILE, semantics_nso_sha256=SEMANTICS_NSO_SHA256,
                lua_validation_scope='Independent tree/byte preservation checks; shared legacy phase-constant classification heuristic, not instruction dataflow proof.',
                phase_domain_scope='Preservation checks enumerate authored phase.bin entries, not every u32 or transient phase value assigned by scripts.',
                new_phase_order=nseq)

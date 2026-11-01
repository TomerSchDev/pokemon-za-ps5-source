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
import fbedit as F
import story_shuffle as S

OPS = {1: lambda x, a: x == a[0], 2: lambda x, a: x != a[0], 3: lambda x, a: x > a[0], 4: lambda x, a: x < a[0],
       5: lambda x, a: x >= a[0], 6: lambda x, a: x <= a[0]}


def ev(op, args, seq):
    try:
        a = [int(x) for x in args]
    except ValueError:
        return None
    if op in OPS and a: return {i for i, x in enumerate(seq) if OPS[op](x, a)}
    if op in S.RANGE_OPS and len(a) == 2: return {i for i, x in enumerate(seq) if a[0] <= x <= a[1]}
    return None


def tree_conds(root):
    out = []

    def fn(t, path):
        if t.type == 'Cond' and 0 in t.kids and t.kids[0].text() == 'phase_condition' and 2 in t.kids:
            out.append((t.i32(1), S.sv(t.kids[2])))
    S.walk(root, fn)
    return out


def slot_conds(data):
    sf = S.SlotFile(data)
    return {t: (op, [sf.get(x) for x in slots]) for t, op, slots in sf.conds('phase_condition')}


def check(g, files, plan):
    fails, soft = [], []
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

    def judge(where, op, va, na):
        nonlocal n_cond
        V = ev(op, va, vseq); N = ev(op, na, nseq)
        if V is None or N is None: return
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
        c = S.chap(va[0])
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
        vc = tree_conds(F.root(g.read(p), 'TrigRoot'))
        nc = tree_conds(F.root(files[p], 'TrigRoot')) if p in files else vc
        if len(vc) != len(nc): fails.append('%s: condition count changed' % p); continue
        for (op, va), (op2, na) in zip(vc, nc): judge(p, op, va, na)
    for p in S.OTHER:
        if not g.has(p): continue
        vc = slot_conds(g.read(p))
        nc = slot_conds(files[p]) if p in files else vc
        for t, (op, va) in vc.items():
            if t not in nc: fails.append('%s: condition at %d lost' % (p, t)); continue
            judge(p, op, va, nc[t][1])

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
    vpts = {t: int(vsf.get(sl[0])) for t, op, sl in vsf.conds('rank_up_point_condition')}
    by_chapter = {32000: 4, 35000: 5, 38000: 6, 41000: 7, 45000: 8}
    pts = {t: int(sf.get(sl[0])) for t, op, sl in sf.conds('rank_up_point_condition')}
    seq = []
    for t, v in vpts.items():
        c = by_chapter.get(v)
        if c is None: continue
        want = [k for k, cc in by_chapter.items() if cc == 4 + plan.pos[c]][0]
        if pts.get(t) != want: fails.append('rank-up of chapter %d: %s, want %d' % (c, pts.get(t), want))
        seq.append((plan.pos[c], pts.get(t)))
    seq.sort()
    if [v for _, v in seq] != sorted(v for _, v in seq): fails.append('rank-up points decrease by position: %s' % seq)
    rank = dict(caps=caps, matching=match, rank_up_points_by_position=seq)
    summary = '%d conditions checked, %d hard failures, %d soft notes' % (n_cond, len(fails), len(soft))
    return dict(ok=not fails, summary=summary, fails=fails, soft=soft, chain=chain, rank=rank,
                new_phase_order=nseq)

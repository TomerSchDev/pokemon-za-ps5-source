"""Shuffle the middle chapters of the Z-A story (data-only patch set, per run) + oracle.

usage: story_shuffle.py OUT (--order 4,6,5,7,8 | --seed N) [--romfs romfs.bin] [--no-lua]
  OUT must be outside git (it holds game data). Writes OUT/romfs/<game path> for every changed file,
  OUT/shuffle-plan.json (what changed, why) and OUT/oracle.json (checks; exit code 1 if any fails).

Chapter 4 stays first: its opening events (Ev_m04_0010/0020, run from trigger_main_03) are what lead into chapter 3's
final Mega Absol battle, whose win (flag_Ev_m03_3010) is chapter 3's exit, and phase 40100 unlocks Mega Evolution.
So the shuffle is over chapters 5-8 (24 orders); --order must start with 4.

What the patch set does (every change is computed from the data, nothing is hard-coded per chapter except the rules):
  phase.bin (re-encoded)   blocks in the new order; ids renumbered so the leading digit = position (4..8), same length;
                           a block's last entry whose exit flag belongs to another chapter (75500 exits on
                           flag_Ev_m08_0020, set by chapter 8's intro) gets the chapter's own last end-event flag;
                           rank caps (cmd 18) and SYS_WORK_ROYALE_MATCHING_INFO by position; capability unlocks
                           (FLAG_ROTOM_GLIDE_ENABLE) also copied to the position where the vanilla game gives them.
  boundary chains          each chapter-end win case = own commands (up to the 111 command) + the intro of the chapter
                           that now follows it (taken from the case that carried it in vanilla). Found by scanning
                           every trigger case for phase == last(c) with events of another chapter.
  phase conditions         every phase_condition / SYS_WORK_PHASE value in the supported tables:
                           single thresholds follow their chapter (content); a range across chapters stays a range
                           over the same chapters, else it is clamped to the block of its lower bound (reported).
  Lua constants           only source-pinned MAIN uses from a reviewed context manifest; DLC is unchanged.
  main_quest               main_05_00 (opened by a flag) re-gated on the exit flag of the chapter before 5;
                           rank_up_point_condition (points, rank) by position.
"""
import argparse, json, os, random, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
HL = os.path.abspath(os.path.join(REPO, '..', 'hebrew-lab'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HL, 'tools'))
import fbedit as F  # noqa: E402

MIDDLE = (4, 5, 6, 7, 8)
SHUFFLED = (5, 6, 7, 8)
PHASE = 'ik_event/bin/phase/phase.bin'
MAINQ = 'ik_event/bin/quest/main_quest.bin'
TRAINER = 'ik_event/bin/trigger/trainer_battle/trigger_trainer_battle_global.bin'
LUA = 'script/lua/bin/release/event_ik/event_ik.blua'
TRIGGERS = ['ik_event/bin/trigger/global/trigger_global', 'ik_event/bin/trigger/map/trigger_map_t2',
            'ik_event/bin/trigger/boss_battle/trigger_boss_battle_global',
            'ik_event/bin/trigger/trainer_battle/trigger_trainer_battle_global',
            'ik_event/bin/trigger/wild_battle/trigger_wild_battle_global',
            'ik_event/bin/trigger/last_battle/trigger_last_battle_global',
            'ik_event/bin/trigger/athletic_time_attack/trigger_athletic_time_attack',
            'ik_event/bin/trigger/minigame/trigger_marugoshi_survivor'] + \
           ['ik_event/bin/trigger/main/trigger_main_%02d' % i for i in range(11)] + \
           ['ik_event/bin/trigger/dlc/trigger_dlc_%02d' % i for i in range(1, 10)]
TRIGGERS = [t + '.bin' for t in TRIGGERS]
OTHER = ['ik_event/bin/quest/main_quest', 'ik_event/bin/quest/sub_quest', 'ik_event/bin/quest/momiji_quest',
         'ik_event/bin/quest/dlc_quest', 'ik_event/bin/event_control/event_control',
         'ik_event/bin/npc_talk_data/npc_talk_data', 'ik_event/bin/npc_talk_data/za_trainer_talk_data',
         'ik_event/bin/return_point/fiexd_return_point', 'ik_event/bin/return_point/return_point',
         'ik_event/bin/return_point/pokecen', 'ik_event/bin/menu_visible_type/menu_visible_type',
         'ik_event/bin/destination_data/destination_data', 'ik_event/bin/mission_card/mission_card',
         'ik_event/bin/title/title', 'ik_event/bin/tips/tips', 'ik_event/bin/hud_tips/hud_tips',
         'ik_event/bin/event_taxi_data/taxi_destination_data',
         'ik_event/bin/door_jump_name_overwrite/door_jump_name_overwrite',
         'ik_event/bin/phase/dlc_phase', 'world/exl/shop/shop_item_lineup/shop_item_lineup']
OTHER = [t + '.bin' for t in OTHER]
CAPABILITIES = {('FLAG_ROTOM_GLIDE_ENABLE', 'TRUE')}
RANGE_OPS = {7, 8, 100, 101}  # proved wire mapping: strict, closed, [a,b), (a,b]


def chap(s):
    """chapter of a phase value given as a string (0 = before the story, 10 = post game, None = not a phase)"""
    if not s.isdigit(): return None
    v = int(s)
    if v < 10000: return 0
    if v < 100000: return v // 10000
    return 10 if v < 110000 else 99


class Plan:
    def __init__(s, order, phase_bin):
        if sorted(order) != list(MIDDLE):
            raise ValueError('order must contain each of chapters4,5,6,7,8 exactly once')
        if order[0] != 4: raise SystemExit('chapter 4 must stay first (see the module docstring); got %s' % order)
        s.order = list(order)
        s.pos = {c: i for i, c in enumerate(order)}
        s.log = []
        s.warn = []
        root = F.root(phase_bin, 'PhaseRoot')
        s.vanilla = [e.i32(0) or 0 for e in root.kids[0].items]
        s.block = {c: [i for i in s.vanilla if chap(str(i)) == c and i] for c in MIDDLE}

    def digit(s, c): return 4 + s.pos[c]

    def ordkey(s, c):
        return 4 + s.pos[c] if c in MIDDLE else c

    def nxt(s, c):
        k = s.pos[c]
        return s.order[k + 1] if k + 1 < len(s.order) else 9

    def prev(s, c):
        k = s.pos[c]
        return s.order[k - 1] if k else 3

    def T(s, v):
        """content translation of one phase value (string)"""
        c = chap(v)
        if c in MIDDLE and len(v) == 5: return str(s.digit(c)) + v[1:]
        return v

    def tr_args(s, op, args, where):
        """translate a phase_condition argument list; returns new list"""
        if op in RANGE_OPS and len(args) == 2 and all(a.isdigit() for a in args):
            a, b = args
            ca, cb = chap(a), chap(b)
            if ca == cb or (ca not in MIDDLE and cb not in MIDDLE):
                return [s.T(a), s.T(b)]
            van = set(range(ca, cb + 1))
            lo, hi = s.ordkey(ca), s.ordkey(cb)
            new = {c for c in range(0, 11) if lo <= s.ordkey(c) <= hi} if lo <= hi else set()
            if van & set(range(0, 11)) == new or cb >= 10 or ca <= 1:
                return [s.T(a), s.T(b)]
            na, nb = (s.T(a), str(s.digit(ca)) + '9999') if ca in MIDDLE else (a, '39999')
            s.warn.append(dict(kind='range clamped to its lower block', where=where, op=op, vanilla=[a, b], new=[na, nb]))
            return [na, nb]
        return [s.T(a) for a in args]


# ---------------------------------------------------------------- tree helpers (trigger files, phase.bin)
def walk(n, fn, path=()):
    if isinstance(n, F.Tab):
        fn(n, path)
        for k, c in n.kids.items(): walk(c, fn, path + (n,))
    elif isinstance(n, F.Vec):
        for c in n.items: walk(c, fn, path)


def sv(v): return [x.text() for x in v.items]


def cond_list(case):
    out = []
    for g in case.kids.get(0, F.Vec([], '')).items:
        for c in g.kids.get(0, F.Vec([], '')).items:
            out.append((c.kids[0].text() if 0 in c.kids else None, c.i32(1), sv(c.kids[2]) if 2 in c.kids else []))
    return out


def cmd_list(case):
    gs = case.kids.get(1, F.Vec([], '')).items
    return [c for g in gs for c in g.kids.get(0, F.Vec([], '')).items]


def cmd_args(c): return sv(c.kids[1]) if 1 in c.kids else []


def events(cmds):
    return [cmd_args(c)[0] for c in cmds if c.i32(0) == 22 and cmd_args(c)]


def set_vstr(tab, f, values):
    tab.kids[f] = F.Vec([F.Str(v) for v in values], 'str')


def translate_tree(plan, root, fname, stats):
    def fn(t, path):
        if t.type == 'Cond' and 0 in t.kids and 2 in t.kids:
            name = t.kids[0].text(); args = sv(t.kids[2])
            if name == 'phase_condition':
                new = plan.tr_args(t.i32(1), args, fname)
            elif name == 'work_condition' and args and args[0] == 'SYS_WORK_PHASE':
                new = [args[0]] + [plan.T(a) for a in args[1:]]
            else:
                return
            if new != args:
                set_vstr(t, 2, new); stats['conds'] = stats.get('conds', 0) + 1
        if t.type == 'Cmd' and t.i32(0) == 9 and 1 in t.kids:
            args = sv(t.kids[1])
            if len(args) == 2 and args[0] == 'SYS_WORK_PHASE' and plan.T(args[1]) != args[1]:
                set_vstr(t, 1, [args[0], plan.T(args[1])]); stats['set_phase'] = stats.get('set_phase', 0) + 1
            if len(args) == 2 and args[0] == 'SYS_WORK_ROYALE_MATCHING_INFO' and args[1] in ('50', '60', '70', '80'):
                nv = str(40 + 10 * plan.pos[int(args[1]) // 10])     # Royale opponents by position
                if nv != args[1]:
                    set_vstr(t, 1, [args[0], nv]); stats['matching'] = stats.get('matching', 0) + 1
    walk(root, fn)


# ---------------------------------------------------------------- boundary model
def find_boundaries(trig_roots, plan):
    """for every chapter c in 4..8: the case that ends c (phase == last(c), events of another chapter after a 111)"""
    out, extra = {}, []
    for fname, root in trig_roots.items():
        for w in root.kids[0].items:
            t = w.kids.get(0)
            if t is None or 2 not in t.kids: continue
            for case in t.kids[2].items:
                conds = cond_list(case)
                phs = [a for n, op, args in conds if n == 'phase_condition' and op == 1 for a in args]
                cmds = cmd_list(case)
                evc = {int(e[4:6]) for e in events(cmds) if re.match(r'Ev_m\d\d_', e)}
                for c in MIDDLE:
                    last = str(plan.block[c][-1])
                    if last in phs and evc - {c}:
                        types = [x.i32(0) for x in cmds]
                        if types.count(111) != 1 or len(case.kids[1].items) != 1:
                            raise SystemExit('boundary case of chapter %d has an unexpected shape' % c)
                        k = types.index(111) + 1
                        if c in out: raise SystemExit('two boundary cases for chapter %d' % c)
                        out[c] = dict(file=fname, case=case, trigger=sv(t.kids[1]) if 1 in t.kids else [],
                                      own=cmds[:k], intro=cmds[k:], next=sorted(evc - {c}))
                # any other case whose phase conditions are in one middle chapter but runs another chapter's events
                pchs = {chap(a) for a in phs}
                if len(pchs) == 1 and (pchs & set(MIDDLE)) and (evc - pchs) and not any(str(plan.block[c][-1]) in phs for c in MIDDLE):
                    extra.append(dict(file=fname, trigger=sv(t.kids[1]) if 1 in t.kids else [], phases=phs, events=sorted(evc)))
    missing = [c for c in MIDDLE if c not in out]
    if missing: raise SystemExit('no boundary case found for chapters %s' % missing)
    return out, extra


# ---------------------------------------------------------------- slot-level edits for tables without a schema
class SlotFile:
    def __init__(s, data):
        s.w = F.Writer(data)
        d = s.w.b
        s.refs = {}
        for q in range(0, len(d) - 3, 4):
            v = struct.unpack_from('<I', d, q)[0]
            if v: s.refs.setdefault(q + v, []).append(q)

    def u32(s, p): return struct.unpack_from('<I', s.w.b, p)[0]
    def i32(s, p): return struct.unpack_from('<i', s.w.b, p)[0]
    def u16(s, p): return struct.unpack_from('<H', s.w.b, p)[0]

    def table_ok(s, t):
        n = len(s.w.b)
        if t < 4 or t % 4 or t + 4 > n: return False
        v = t - s.i32(t)
        if v < 0 or v + 4 > n or v % 2: return False
        vs, ts = s.u16(v), s.u16(v + 2)
        return 4 <= vs <= 256 and vs % 2 == 0 and 4 <= ts <= 8192 and v + vs <= n

    def voff(s, t, i):
        v = t - s.i32(t); vs = s.u16(v)
        return s.u16(v + 4 + 2 * i) if 4 + 2 * i < vs else 0

    def str_at(s, p):
        n = s.u32(p)
        return bytes(s.w.b[p + 4:p + 4 + n]).decode('utf-8', 'replace')

    def conds(s, name):
        """[(table, op, [arg slots])] for every Cond-shaped table whose field 0 is the string NAME"""
        b = name.encode(); pat = struct.pack('<I', len(b)) + b + b'\0'
        d = s.w.b; out = []; i = d.find(pat)
        hits = []
        while i >= 0:
            if i % 4 == 0: hits.append(i)
            i = d.find(pat, i + 1)
        for sp in hits:
            for slot in s.refs.get(sp, []):
                for o in range(4, 68, 4):
                    t = slot - o
                    if s.table_ok(t) and s.voff(t, 0) == o:
                        o1, o2 = s.voff(t, 1), s.voff(t, 2)
                        if not o2: break
                        vec = t + o2 + s.u32(t + o2)
                        n = s.u32(vec)
                        if not 0 < n < 16: break
                        op = s.i32(t + o1) if o1 else None
                        out.append((t, op, [vec + 4 + 4 * k for k in range(n)]))
                        break
        return out

    def get(s, slot): return s.str_at(slot + s.u32(slot))

    def put(s, slot, text):
        old = slot + s.u32(slot)
        r = F.set_str(s.w, slot, text, s.refs)
        if r == 'appended':
            s.refs[old].remove(slot)
            s.refs[slot + s.u32(slot)] = [slot]
        return r


def quest_start_slots(sf, quest):
    """main_quest.bin: the argument string slots of quest QUEST's start condition (field 11 -> groups -> conds)"""
    u = sf.u32
    root = u(0)
    vec = root + sf.voff(root, 0); vec += u(vec)
    out = []
    for k in range(u(vec)):
        e = vec + 4 + 4 * k; q = e + u(e)
        o0 = sf.voff(q, 0)
        if not o0 or sf.get(q + o0) != quest: continue
        o11 = sf.voff(q, 11)
        gv = q + o11 + u(q + o11)
        for gi in range(u(gv)):
            ge = gv + 4 + 4 * gi; gt = ge + u(ge)
            cv = gt + sf.voff(gt, 0); cv += u(cv)
            for ci in range(u(cv)):
                ce = cv + 4 + 4 * ci; c = ce + u(ce)
                o2 = sf.voff(c, 2)
                av = c + o2 + u(c + o2)
                out += [av + 4 + 4 * j for j in range(u(av))]
    return out


def translate_slots(plan, sf, fname, stats):
    """same rules as translate_tree, on a file edited in place (string slots)"""
    done = set()

    def put(x, new, key):
        sf.put(x, new); done.add(x); stats[key] = stats.get(key, 0) + 1
    for t, op, slots in sf.conds('phase_condition'):
        args = [sf.get(x) for x in slots]
        new = plan.tr_args(op, args, fname)
        for x, a, b in zip(slots, args, new):
            done.add(x)
            if a != b: put(x, b, 'conds')
    # ("SYS_WORK_PHASE", value) / ("SYS_WORK_ROYALE_MATCHING_INFO", value) pairs: work conditions and set-work commands
    for name in ('SYS_WORK_PHASE', 'SYS_WORK_ROYALE_MATCHING_INFO'):
        b_ = name.encode(); pat = struct.pack('<I', len(b_)) + b_ + bytes(1)
        d = sf.w.b; i = d.find(pat); hits = []
        while i >= 0:
            if i % 4 == 0: hits.append(i)
            i = d.find(pat, i + 1)
        for sp in hits:
            for slot in list(sf.refs.get(sp, [])):
                x = slot + 4
                if x in done or x + 4 > len(sf.w.b): continue
                tgt = x + sf.u32(x)
                if not (0 < tgt < len(sf.w.b) - 4) or sf.u32(tgt) > 8: continue
                v = sf.get(x)
                if not v.isdigit(): continue
                if name == 'SYS_WORK_PHASE': nv = plan.T(v)
                else: nv = str(40 + 10 * plan.pos[int(v) // 10]) if v in ('50', '60', '70', '80') else v
                done.add(x)
                if nv != v: put(x, nv, 'set_phase' if name == 'SYS_WORK_PHASE' else 'matching')


# ---------------------------------------------------------------- Lua constants
def lua_patch(plan, data, report):
    """Translate only source-pinned constants with complete reviewed MAIN uses."""
    import lua_context
    _, _, entries = lua_context.reviewed(data)
    result = bytearray(data)
    for entry, offset in entries:
        if entry['namespace'] != ['main']: continue
        old = entry['original_value']; new = int(plan.T(str(old)))
        if old != new:
            struct.pack_into('<q', result, offset, new)
            report.append(dict(func=entry['prototype'], constant_index=entry['constant_index'],
                               namespace='main', old=old, new=new,
                               context_manifest_sha256=lua_context.MANIFEST_SHA256))
    return bytes(result)

# ---------------------------------------------------------------- main generator
def generate(g, order, lua=True):
    """g: object with read(path)/has(path). Returns (files{path: bytes}, plan_json, plan)"""
    if not g.has(LUA): raise ValueError('Lua source required for story context validation')
    phase_bin = g.read(PHASE)
    import hashlib, lua_context
    context, _, _ = lua_context.reviewed(g.read(LUA), hashlib.sha256(phase_bin).hexdigest())
    plan = Plan(order, phase_bin)
    files = {}
    pj = dict(order=order, ids={}, boundaries={}, files={})
    pj['lua_context'] = dict(manifest_sha256=lua_context.MANIFEST_SHA256,
                             input_lua_sha256=context['input_lua_sha256'],
                             proof_sha256=context['proof_sha256'],
                             main_candidates=1, dlc_candidates_preserved=17)

    # trigger files (full re-encode)
    trig = {p: F.root(g.read(p), 'TrigRoot') for p in TRIGGERS if g.has(p)}
    bnd, extra = find_boundaries(trig, plan)
    pj['other_cross_chapter_cases'] = extra
    intro = {bnd[c]['next'][0] if len(bnd[c]['next']) == 1 else None: bnd[c]['intro'] for c in MIDDLE}
    if set(intro) != {5, 6, 7, 8, 9}: raise SystemExit('unexpected intro set %s' % sorted(map(str, intro)))
    own_end = {}

    def is_cleanup(x, c):
        """a command of chapter c's intro-successor that undoes a flag chapter c's end set TRUE"""
        if x.i32(0) != 8 or cmd_args(x)[1:] != ['FALSE']: return False
        return cmd_args(x)[0] in {cmd_args(y)[0] for y in bnd[c]['own'] if y.i32(0) == 8 and cmd_args(y)[1:] == ['TRUE']}
    for c in MIDDLE:
        b = bnd[c]
        own = [x.clone() for x in b['own']]
        delta = plan.pos[c] - (c - 4)
        for x in own:   # rank cap command by position
            if x.i32(0) == 18 and cmd_args(x) and cmd_args(x)[0].isdigit():
                set_vstr(x, 1, [str(int(cmd_args(x)[0]) + delta)])
        nx = plan.nxt(c)
        tail = [x.clone() for x in intro[nx] if not (nx - 1 != c and is_cleanup(x, nx - 1))]
        if nx != c + 1:
            for x in intro[c + 1]:
                if is_cleanup(x, c):
                    tail.insert(0, x.clone())
                    pj.setdefault('moved_cleanup', []).append(dict(chapter=c, cmd=cmd_args(x)))
        b['case'].kids[1].items[0].kids[0] = F.Vec(own + tail, 'Cmd')
        evs = [e for e in events(b['own']) if e.startswith('Ev_m%02d_' % c)]
        own_end[c] = 'flag_' + evs[-1]
        pj['boundaries'][c] = dict(file=b['file'], trigger=b['trigger'], next=nx,
                                   commands=len(own) + len(tail), own_events=events(own), intro_events=events(tail))

    # phase.bin (re-encode)
    root = F.root(phase_bin, 'PhaseRoot')
    ents = root.kids[0].items
    byid = {e.i32(0) or 0: e for e in ents}
    pre = [e for e in ents if (e.i32(0) or 0) < 40000]
    post = [e for e in ents if (e.i32(0) or 0) >= 90000]
    new = pre + [byid[i] for c in plan.order for i in plan.block[c]] + post
    assert len(new) == len(ents)
    for c in MIDDLE:
        delta = plan.pos[c] - (c - 4)
        for i in plan.block[c]:
            e = byid[i]
            ni = int(plan.T(str(i)))
            pj['ids'][i] = ni
            e.set_i32(0, ni)
            for x in (e.kids[2].items if 2 in e.kids else []):
                a = cmd_args(x)
                if x.i32(0) == 18 and a and a[0].isdigit(): set_vstr(x, 1, [str(int(a[0]) + delta)])
        last = byid[plan.block[c][-1]]
        for g_ in last.kids[1].items:
            for cd in g_.kids[0].items:
                a = sv(cd.kids[2])
                if cd.kids[0].text() == 'flag_condition' and a and not a[0].startswith('flag_Ev_m%02d_' % c)                         and not a[0].startswith('flag_Ev_m%02d_' % plan.nxt(c)):
                    pj.setdefault('exit_fixed', []).append(dict(phase=plan.block[c][-1], old=a[0], new=own_end[c]))
                    set_vstr(cd, 2, [own_end[c]] + a[1:])
    # capability unlocks: also at the vanilla position (collected from the vanilla actions first)
    caps = []
    for c in SHUFFLED:
        for i in plan.block[c]:
            for x in (byid[i].kids[2].items if 2 in byid[i].kids else []):
                if x.i32(0) == 8 and tuple(cmd_args(x)) in CAPABILITIES: caps.append((c, i, x.clone()))
    for c, i, x in caps:
        host = plan.order[c - 4]
        if host == c: continue
        tgt = byid[plan.block[host][0]]
        if 2 not in tgt.kids:
            offs = list(tgt.offs) + [0] * (3 - len(tgt.offs))
            offs[2] = tgt.tsize
            tgt.offs = offs; tgt.inline += bytes(4); tgt.tsize += 4
            tgt.kids[2] = F.Vec([], 'Cmd')
        tgt.kids[2].items.append(x)
        pj.setdefault('capabilities', []).append(dict(cmd=cmd_args(x), from_phase=i, also_at=plan.block[host][0]))
    exit_flag = {}
    for c in MIDDLE:
        last = byid[plan.block[c][-1]]
        exit_flag[c] = [sv(cd.kids[2])[0] for g_ in last.kids[1].items for cd in g_.kids[0].items
                        if cd.kids[0].text() == 'flag_condition'][0]
    pj['exit_flags'] = exit_flag
    root.kids[0] = F.Vec(new, 'Phase')
    stats = {}
    translate_tree(plan, root, PHASE, stats)
    w = F.Writer(); w.put(root, root=True)
    files[PHASE] = bytes(w.b)
    pj['files'][PHASE] = stats

    # the boundary file is re-encoded (its command lists change length); every other trigger file is edited in place
    for p, r in trig.items():
        stats = {}
        if p == bnd[4]['file']:
            translate_tree(plan, r, p, stats)
            w = F.Writer(); w.put(r, root=True); files[p] = bytes(w.b); pj['files'][p] = stats
            continue
        data = g.read(p)
        sf = SlotFile(data)
        translate_slots(plan, sf, p, stats)
        if bytes(sf.w.b) != data: files[p] = bytes(sf.w.b); pj['files'][p] = stats

    # other tables (slot-level, in place or appended strings)
    for p in OTHER:
        if not g.has(p): continue
        data = g.read(p)
        sf = SlotFile(data)
        stats = {}
        translate_slots(plan, sf, p, stats)
        if p == MAINQ:
            # main_05_00's flag gate -> exit flag of the chapter before 5 (vanilla: end of 4)
            gate_old = 'flag_Ev_m04_5050'
            pc = plan.prev(5)
            gate_new = exit_flag[pc] if pc in MIDDLE else 'flag_Ev_m03_3010'
            # the exit flag actually used by the previous block's last entry
            slots = quest_start_slots(sf, 'main_05_00')
            hits = [x for x in slots if sf.get(x) == gate_old]
            if len(hits) != 1: raise SystemExit('main_05_00 start gate: %d hits' % len(hits))
            if gate_new != gate_old: sf.put(hits[0], gate_new)
            hits = len(hits)
            pj['main_05_00_gate'] = dict(old=gate_old, new=gate_new, hits=hits)
            # rank-up conditions by position: chapter at position k gets vanilla chapter (4+k)'s final rank-up
            ru = []
            for t, op, slots in sf.conds('rank_up_point_condition'):
                ru.append((t, slots, [sf.get(x) for x in slots]))
            final = {}
            for t, slots, a in ru:
                pts = int(a[0])
                c = {32000: 4, 35000: 5, 38000: 6, 41000: 7, 45000: 8}.get(pts)
                if c: final[c] = (slots, a)
            if sorted(final) != list(MIDDLE): raise SystemExit('rank-up conditions not as expected: %s' % sorted(final))
            vals = {c: final[c][1] for c in MIDDLE}
            for c in MIDDLE:
                slots, a = final[c]
                want = vals[4 + plan.pos[c]]
                for x, old, nw in zip(slots, a, want):
                    if old != nw: sf.put(x, nw)
                pj.setdefault('rank_up', {})[c] = dict(position=plan.pos[c], vanilla=a, new=want)
        if bytes(sf.w.b) != data:
            files[p] = bytes(sf.w.b); pj['files'][p] = stats

    if lua and g.has(LUA):
        rep = []
        files[LUA] = lua_patch(plan, g.read(LUA), rep)
        pj['lua_constants'] = rep
        if not rep: del files[LUA]
    pj['warnings'] = plan.warn
    return files, pj, plan


def order_from_seed(seed):
    r = random.Random('za-story-shuffle-1:%d' % seed)
    mid = list(SHUFFLED); r.shuffle(mid)
    return [4] + mid


class Romfs:
    def __init__(s, romfs):
        import za_romfs
        s.g = za_romfs.Game(romfs)
    def read(s, p): return s.g.read(p)
    def has(s, p): return s.g.has(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    choice = ap.add_mutually_exclusive_group(required=True)
    choice.add_argument('--order'); choice.add_argument('--seed', type=int)
    ap.add_argument('--romfs', default=os.path.join(HL, 'qa-game-reference-20261030', 'romfs.bin'))
    ap.add_argument('--no-lua', action='store_true')
    a = ap.parse_args()
    from pathlib import Path
    out = str(Path(a.out).resolve())
    if os.path.exists(out): sys.exit('OUT must be new; existing files are never overwritten')
    if any((p / '.git').exists() for p in (Path(out), *Path(out).parents)):
        sys.exit('OUT must be outside every git checkout')
    order = [int(x) for x in a.order.split(',')] if a.order else order_from_seed(a.seed)
    g = Romfs(a.romfs)
    files, pj, plan = generate(g, order, lua=not a.no_lua)
    import oracle
    res = oracle.check(g, files, plan)
    pj['seed'] = a.seed
    pj['ready_for_ui'] = pj['ready_for_ps5'] = False
    pj['validation_scope'] = 'data oracle only; full chapter playthrough and hardware remain unverified'
    os.makedirs(out)
    json.dump(pj, open(os.path.join(out, 'shuffle-plan.json'), 'w'), indent=1, default=str)
    json.dump(res, open(os.path.join(out, 'oracle.json'), 'w'), indent=1, default=str)
    # A failing oracle produces diagnostics only, never a loadable mod tree.
    if res['ok']:
        for p, d in files.items():
            dst = os.path.join(out, 'romfs', p); os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'xb') as f: f.write(d)
    print('order', order, '|', len(files), 'files |', len(pj['warnings']), 'clamped ranges |',
          'oracle', 'PASS' if res['ok'] else 'FAIL', res['summary'])
    sys.exit(0 if res['ok'] else 1)


if __name__ == '__main__':
    main()

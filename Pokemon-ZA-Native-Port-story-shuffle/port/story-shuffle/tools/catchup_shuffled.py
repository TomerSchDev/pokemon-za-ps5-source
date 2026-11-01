"""za-story-save ops that put a COPIED save at the start of phase TARGET of a shuffled story (PC tests only).

usage: catchup_shuffled.py MODDIR TARGET [--romfs romfs.bin] > ops.txt
  MODDIR: a story_shuffle.py output (its romfs/ overrides the game files). TARGET: a phase id in the NEW numbering.
Ops = the exit flags of every entry before TARGET in the new phase order + their transition actions (cmd 8 flag,
cmd 9 work; last write wins) + every main quest whose start gate is already met = 255 + SYS_WORK_PHASE = TARGET.
Same rules as port/story-rando/tools/catchup.py, but read from the patched phase.bin / main_quest.bin.
"""
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fbedit as F  # noqa: E402
import story_shuffle as S  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mod'); ap.add_argument('target', type=int)
    ap.add_argument('--romfs', default=os.path.join(S.HL, 'qa-game-reference-20261030', 'romfs.bin'))
    a = ap.parse_args()
    g = S.Romfs(a.romfs)

    def rd(p):
        q = os.path.join(a.mod, 'romfs', p)
        return open(q, 'rb').read() if os.path.exists(q) else g.read(p)
    sysflags = set()
    sf_root = g.read('ik_event/bin/flag/system_flag.bin')
    sys.path.insert(0, os.path.join(S.REPO, 'port', 'story-rando', 'tools'))
    import fbdump
    for e in fbdump.dump(sf_root).get(0, []):
        if isinstance(e, dict) and isinstance(e.get(0), str): sysflags.add(e[0])
    kind = lambda n: 'sysflag' if n in sysflags else 'flag'
    ph = F.root(rd(S.PHASE), 'PhaseRoot')
    ops, setflags = {}, set()
    for e in ph.kids[0].items:
        pid = e.i32(0) or 0
        if pid >= a.target: break
        for g_ in (e.kids[1].items if 1 in e.kids else []):
            for c in g_.kids[0].items:
                args = S.sv(c.kids[2]) if 2 in c.kids else []
                if c.kids[0].text() == 'flag_condition' and c.i32(1) == 1 and args:
                    ops['%s:%s' % (kind(args[0]), args[0])] = '1'; setflags.add(args[0])
        for x in (e.kids[2].items if 2 in e.kids else []):
            args = S.cmd_args(x)
            if x.i32(0) == 8 and len(args) == 2:
                ops['%s:%s' % (kind(args[0]), args[0])] = '1' if args[1] == 'TRUE' else '0'
                (setflags.add if args[1] == 'TRUE' else setflags.discard)(args[0])
            if x.i32(0) == 9 and len(args) == 2:
                ops[('quest:' if args[0].startswith('SYS_WORK_QUEST_') else 'work:') + args[0]] = args[1]
    sf = S.SlotFile(rd(S.MAINQ))
    u = sf.u32
    root = u(0); vec = root + sf.voff(root, 0); vec += u(vec)
    for k in range(u(vec)):
        e = vec + 4 + 4 * k; q = e + u(e)
        name = sf.get(q + sf.voff(q, 0))
        work = sf.get(q + sf.voff(q, 5))
        slots = S.quest_start_slots(sf, name)
        args = [sf.get(x) for x in slots]
        done = False
        if len(args) == 1 and args[0].isdigit(): done = int(args[0]) < a.target
        elif args and all(x in setflags for x in args): done = True
        if done: ops['quest:' + work] = '255'
    ops['work:SYS_WORK_PHASE'] = str(a.target)
    print(' '.join('%s=%s' % kv for kv in ops.items()))


if __name__ == '__main__':
    main()

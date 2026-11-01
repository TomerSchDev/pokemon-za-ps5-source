"""Make the chapter-4 start spec (za-chapter4-spec-v1) for za-skip-save from the extracted ik_event tables.

The story part is the catch-up of port/story-rando/tools/catchup.py, computed from phase.bin: the exit flag of every
phase entry before TARGET, every transition action of those entries (type 8 flag, type 9 work; last write wins),
every earlier main quest = 255 and SYS_WORK_PHASE = TARGET. On top of that it adds what the catch-up could not:
the Royale rank and its cap (phase action 18 = rank cap, the last one before TARGET), the rank points of that rank
(trainer_rank.bin), and the run defaults (money, items, starter level, the Absol gift of chapter 3).

    py -3 -I make_spec.py EXTRACT_DIR OUT.json [--phase 40100] [--starter-level 30] [--money 30000]

EXTRACT_DIR = the output of story_extract.py (j/phase.json, j/main_quest.json, j/trainer_rank.json) plus
sysflag_names.txt. Both the input and the output are game-derived: keep them out of git.
"""
import argparse, json, re
from pathlib import Path

# Where the game keeps the Royale rank (see port/story-rando/NOTES-royale-rank.md).
RANK_BLOCK = '1866780C'   # 228-byte object: +0 current rank (1 = Z ... 26 = A, 27 = infinity), +4 rank cap
RANK_OFFSET, CAP_OFFSET = 0, 4

# Run defaults for a chapter-4 start (design decisions, not game data).
ITEMS = [  # item id, count (PKHeX ids): balls and medicine a player has by the end of chapter 3
    (4, 30), (3, 15), (17, 10), (26, 5), (28, 3), (18, 3), (22, 3),
]
ABSOL = {'species': 359, 'level': 30}  # the chapter-3 gift (FLAG_CANT_RELEASE_ABUSORU); PKHeX EncounterGift9a


def story_ops(j: Path, sysflags: set, target: int):
    ph = json.loads((j / 'phase.json').read_text(encoding='utf-8'))['0']
    ops, cap = {}, None
    for e in ph:
        pid = e.get('0') if isinstance(e.get('0'), int) else 0
        if pid >= target:
            break
        for g in e.get('1') or []:
            for c in (g.get('0') if isinstance(g.get('0'), list) else []):
                if c.get('0') == 'flag_condition' and c.get('1') == 1:
                    ops[('sysflag:' if c['2'][0] in sysflags else 'flag:') + c['2'][0]] = '1'
        for c in e.get('2') or []:
            if not isinstance(c, dict):
                continue
            t, a = c.get('0'), c.get('1') or []
            if t == 8 and len(a) == 2:
                ops['%s:%s' % ('sysflag' if a[0] in sysflags else 'flag', a[0])] = '1' if a[1] == 'TRUE' else '0'
            if t == 9 and len(a) == 2:
                ops[('quest:' if a[0].startswith('SYS_WORK_QUEST_') else 'work:') + a[0]] = a[1]
            if t == 18 and len(a) == 1:
                cap = int(a[0])
    mq = json.loads((j / 'main_quest.json').read_text(encoding='utf-8'))['0']
    for q in mq:
        m = re.search(r'"phase_condition", "1": 5, "2": \["(\d+)"\]', json.dumps(q.get('11')))
        if m and int(m.group(1)) < target:
            ops['quest:' + q['5']] = '255'
    ops['work:SYS_WORK_PHASE'] = str(target)
    return ['%s=%s' % kv for kv in ops.items()], cap


def rank_points(j: Path, rank: int) -> int:
    rows = json.loads((j / 'trainer_rank.json').read_text(encoding='utf-8'))['0']
    row = next(r for r in rows if r.get('0') == rank)
    return int(row.get('1', 0))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('extract', type=Path)
    p.add_argument('out', type=Path)
    p.add_argument('--phase', type=int, default=40100)
    p.add_argument('--starter-level', type=int, default=30)
    p.add_argument('--money', type=int, default=30000)
    p.add_argument('--no-absol', action='store_true')
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit('output exists; use a new name')
    j = a.extract / 'j'
    sysflags = set(l.strip() for l in (a.extract / 'sysflag_names.txt').open(encoding='utf-8'))
    ops, cap = story_ops(j, sysflags, a.phase)
    if cap is None:
        raise SystemExit('no rank cap (phase action 18) before the target phase')
    spec = {
        'schema': 1, 'format': 'za-chapter4-spec-v1', 'target_phase': a.phase,
        'ops': ops,
        'raw': [{'block': RANK_BLOCK, 'offset': RANK_OFFSET, 'u32': cap},
                {'block': RANK_BLOCK, 'offset': CAP_OFFSET, 'u32': cap}],
        'ticket_points_note': 'KTicketPointsZARoyale is left as is (0): it counts the points of the current night',
        'rank': cap, 'rank_points_threshold': rank_points(j, cap),
        'money': a.money,
        'items': [{'id': i, 'count': c} for i, c in ITEMS],
        'starter_level': a.starter_level,
        'gifts': [] if a.no_absol else [ABSOL],
    }
    a.out.write_text(json.dumps(spec, indent=1), encoding='utf-8')
    print('ops', len(ops), 'rank cap', cap, 'points threshold', spec['rank_points_threshold'], '->', a.out)


if __name__ == '__main__':
    main()

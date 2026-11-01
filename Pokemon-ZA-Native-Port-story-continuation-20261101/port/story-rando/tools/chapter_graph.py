"""Chapter-level graph from dumped phase.json + main_quest.json: per main quest -> start, end, phase span, unlocks, rank gates."""
import json, re
from phase_summary import cond_text

ph = json.load(open('j/phase.json', encoding='utf-8'))['0']
mq = json.load(open('j/main_quest.json', encoding='utf-8'))['0']
phases = []
for i, e in enumerate(ph):
    pid = e.get('0') if isinstance(e.get('0'), int) else 0
    acts = []
    for c in e.get('2') or []:
        if isinstance(c, dict): acts.append((c.get('0'), c.get('1') or []))
    phases.append(dict(id=pid, exit=cond_text(e.get('1')), actions=acts))
ids = [p['id'] for p in phases]
flag_to_phase = {}
for p in phases:
    for f in re.findall(r'flag_Ev_\w+|flga_Ev_\w+', p['exit']):
        flag_to_phase[f] = p['id']

UNLOCK_NAMES = {8: 'flag', 9: 'work', 18: 'rank_cap', 28: 'clock', 51: 'weather', 29: 'cmd29', 52: 'cmd52', 44: 'cmd44', 50: 'cmd50', 68: 'cmd68', 95: 'cmd95', 117: 'quest_cmd', 30: 'cmd30'}
quests = []
for q in mq:
    start = cond_text(q.get('11'))
    steps = [s for s in (q.get('12') or []) if isinstance(s, dict)]
    flags = []
    ranks = []
    for s in steps:
        t = cond_text(s.get('2')) if s.get('2') else ''
        flags += re.findall(r'fl[ga]{2}_Ev_\w+', t)
        for m in re.finditer(r'rank_up_point_condition>=(\d+),0,(\d+)', t):
            ranks.append((int(m.group(1)), int(m.group(2))))
    m = re.search(r'phase_condition>=(\d+)', start)
    sp = int(m.group(1)) if m else None
    end_phase = max([flag_to_phase.get(f, 0) for f in flags] or [0])
    quests.append(dict(id=q.get('0'), order=q.get('1'), start=start, start_phase=sp, steps=len(steps),
                       last_flag=flags[-1] if flags else None, end_phase=end_phase, rank_gates=ranks))
# actions grouped per phase span of each quest
for q in quests:
    lo = q['start_phase'] or 0; hi = q['end_phase']
    prov = []
    for p in phases:
        if lo <= p['id'] <= hi or (p['id'] == hi):
            for t, a in p['actions']:
                if t == 8 and len(a) == 2 and a[1] == 'TRUE' and not a[0].startswith('flag_Ev_'):
                    prov.append(a[0])
                elif t == 18: prov.append('rank_cap=%s' % a[0])
                elif t == 9 and 'ROYALE' in a[0]: prov.append('%s=%s' % (a[0], a[1]))
    q['provides'] = prov
json.dump(dict(phases=phases, quests=quests), open('chapter_graph.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
for q in quests:
    print(q['id'], q['start_phase'], '->', q['end_phase'], 'steps', q['steps'], 'ranks', q['rank_gates'], 'prov', q['provides'][:8])

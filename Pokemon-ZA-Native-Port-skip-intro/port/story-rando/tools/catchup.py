"""ops to put a save at the START of phase TARGET: exit flags of every earlier entry, their transition actions
(type 8 flag / type 9 work, last write wins), earlier main quests = 255, SYS_WORK_PHASE = TARGET."""
import json, re, sys
target = int(sys.argv[1])
ph = json.load(open('j/phase.json', encoding='utf-8'))['0']
sysflags = set(l.strip() for l in open('sysflag_names.txt'))
ops = {}
for e in ph:
    pid = e.get('0') if isinstance(e.get('0'), int) else 0
    if pid >= target: break
    for g in e.get('1') or []:
        for c in (g.get('0') if isinstance(g.get('0'), list) else []):
            if c.get('0') == 'flag_condition' and c.get('1') == 1:
                ops[('sysflag:' if c['2'][0] in sysflags else 'flag:') + c['2'][0]] = '1'
    for c in e.get('2') or []:
        if not isinstance(c, dict): continue
        t, a = c.get('0'), c.get('1') or []
        if t == 8 and len(a) == 2:
            kind = 'sysflag' if a[0] in sysflags else 'flag'
            ops['%s:%s' % (kind, a[0])] = '1' if a[1] == 'TRUE' else '0'
        if t == 9 and len(a) == 2:
            ops[('quest:' if a[0].startswith('SYS_WORK_QUEST_') else 'work:') + a[0]] = a[1]
mq = json.load(open('j/main_quest.json', encoding='utf-8'))['0']
for q in mq:
    m = re.search(r'"phase_condition", "1": 5, "2": \["(\d+)"\]', json.dumps(q.get('11')))
    if m and int(m.group(1)) < target: ops['quest:' + q['5']] = '255'
ops['work:SYS_WORK_PHASE'] = str(target)
print(' '.join('%s=%s' % kv for kv in ops.items()))

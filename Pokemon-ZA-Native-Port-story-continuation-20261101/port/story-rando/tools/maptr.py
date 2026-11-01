import json,sys,collections
from phase_summary import cond_text, cmd_text
d=json.load(open(sys.argv[1],encoding='utf-8'))
for t in d['0'][:int(sys.argv[2])]:
    t=t.get('0',t)
    if not isinstance(t,dict): continue
    for case in t.get('2') or []:
        if not isinstance(case,dict): continue
        cmds=case.get('1') or []
        cm='; '.join(cmd_text(c.get('0')) for c in cmds if isinstance(c,dict))
        print(t.get('0'), (t.get('1') or ['?'])[0] if isinstance(t.get('1'),list) else t.get('1'), '| IF', cond_text(case.get('0'))[:160], '| DO', cm[:200])

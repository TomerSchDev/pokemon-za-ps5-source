import json, sys
from phase_summary import cond_text

d = json.load(open(sys.argv[1], encoding='utf-8'))
for q in d['0']:
    other = {k: v for k, v in q.items() if k not in ('0', '5', '6', '11', '12')}
    print('== %s work=%s title=%s other=%s' % (q.get('0'), q.get('5'), q.get('6'), json.dumps(other, ensure_ascii=False)[:200]))
    if q.get('11') is not None:
        print('   START IF', cond_text(q.get('11')))
    for st in q.get('12') or []:
        if not isinstance(st, dict): continue
        extra = {k: v for k, v in st.items() if k not in ('0', '1', '2')}
        print('   step %s: done IF %s %s' % (st.get('0'), cond_text(st.get('2')) if st.get('2') else '-', json.dumps(extra, ensure_ascii=False)[:150]))

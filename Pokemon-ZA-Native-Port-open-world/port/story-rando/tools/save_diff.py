"""Diff two `za-story-save dump` JSON files: phase, event/system flags turned on/off, work/quest values changed."""
import json, sys

a, b = (json.load(open(p, encoding='utf-8')) for p in sys.argv[1:3])
print('phase', a['phase'], '->', b['phase'])
for k in ('event_flags_true', 'system_flags_true'):
    sa, sb = set(a[k]), set(b[k])
    print(k, '+', sorted(sb - sa), '-', sorted(sa - sb))
for k in ('system_work', 'quest_work'):
    ch = {n: (a[k].get(n), v) for n, v in b[k].items() if a[k].get(n) != v}
    gone = [n for n in a[k] if n not in b[k]]
    print(k, ch, 'removed', gone)

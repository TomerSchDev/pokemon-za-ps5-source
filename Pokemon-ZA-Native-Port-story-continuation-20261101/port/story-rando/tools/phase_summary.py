import json, sys
from collections import Counter
OPS = {1: '==', 2: '!=', 4: '<', 5: '>=', 0: '?'}


def cond_text(groups):
    if not isinstance(groups, list): return str(groups)
    ors = []
    for g in groups:
        ands = []
        gl = g.get('0') if isinstance(g, dict) else None
        for c in (gl if isinstance(gl, list) else [gl]):
            if not isinstance(c, dict): ands.append(str(c)); continue
            ands.append('%s%s%s' % (c.get('0'), OPS.get(c.get('1'), c.get('1')), ','.join(map(str, c.get('2') or []))))
        ors.append(' & '.join(ands))
    return ' | '.join(ors)


def cmd_text(cmds):
    if not isinstance(cmds, list): return ''
    out = []
    for c in cmds:
        if not isinstance(c, dict): out.append(str(c)); continue
        out.append('%s:%s' % (c.get('0'), '/'.join(map(str, c.get('1') or []))))
    return '; '.join(out)


if __name__ == '__main__':
    d = json.load(open(sys.argv[1], encoding='utf-8'))
    types = Counter()
    for e in d['0']:
        print(e.get('0'), '| IF', cond_text(e.get('1')), '| DO', cmd_text(e.get('2')))
        for c in e.get('2') or []:
            if isinstance(c, dict): types[str(c.get('0'))] += 1
    print(types, file=sys.stderr)

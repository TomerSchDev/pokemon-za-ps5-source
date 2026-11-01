"""Inventory every *_condition node in every dumped table: (file, name, op, args)."""
import json, glob, os, collections

out = collections.defaultdict(list)


def walk(x, f, ctx):
    if isinstance(x, dict):
        n = x.get('0')
        if isinstance(n, str) and n.endswith('_condition'):
            out[f].append((n, x.get('1'), tuple(x.get('2') or []), ctx))
            return
        c2 = ctx
        if isinstance(x.get('1'), list) and x['1'] and all(isinstance(s, str) for s in x['1']) and isinstance(x.get('0'), int):
            c2 = ctx + [x['1'][0]]
        for k, v in x.items():
            walk(v, f, c2 if k != '0' else ctx)
    elif isinstance(x, list):
        for v in x: walk(v, f, ctx)


for p in sorted(glob.glob('j/*.json')):
    f = os.path.basename(p)[:-5]
    walk(json.load(open(p, encoding='utf-8')), f, [])

summary = {}
for f, cs in out.items():
    c = collections.Counter((n, op) for n, op, a, ctx in cs)
    summary[f] = {'%s/%s' % k: v for k, v in c.most_common()}
json.dump(summary, open('cond_summary.json', 'w'), indent=1)
ph = collections.Counter()
for f, cs in out.items():
    for n, op, a, ctx in cs:
        if n == 'phase_condition': ph[(f, op)] += 1
for k, v in sorted(ph.items(), key=str): print(k, v)
json.dump({f: [list(map(str, c[:3])) for c in cs] for f, cs in out.items()}, open('cond_all.json', 'w'), indent=0)

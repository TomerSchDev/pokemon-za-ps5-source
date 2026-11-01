"""Compare enumerated per-species data files with personal presence (internal vs national numbering)."""
import json
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
pers = json.load(open(S + '/out/personal-2.0.2.json'))
files = json.load(open(S + '/out/species-data-files.json'))
present_int = {r['internal'] for r in pers if r['present']}
present_nat = {r['national'] for r in pers if r['present']}
all_int = {r['internal'] for r in pers}
int2name = {r['internal']: r['name'] for r in pers if r['form'] == 0}
for kind, lst in files.items():
    ns = {int(x[:4]) for x in lst}
    print(kind, 'distinct', len(ns),
          '| in present-internal', len(ns & present_int), '| in present-national', len(ns & present_nat),
          '| absent (by internal id)', len(ns - present_int))
    extra = sorted(ns - present_int)
    print('   absent examples (internal->name):', [(n, int2name.get(n, '?')) for n in extra[:40]])
    missing = sorted(present_int - ns)
    print('   present species WITHOUT a file:', len(missing), [(n, int2name.get(n, '?')) for n in missing[:15]])

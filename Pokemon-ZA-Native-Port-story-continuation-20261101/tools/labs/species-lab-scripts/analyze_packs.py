"""Group the 2.0.2 pack names (out/pack-names.json) by kind; per-species pack inventory. Names only."""
import json, re, collections, sys
OUT = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/out'
d = json.load(open(OUT + '/pack-names.json'))
packs = d['packs']
# kinds of pokemon-related packs: strip pm numbers to a template
tmpl = collections.Counter()
examples = {}
for name, nf, size in packs:
    if not re.search(r'pm\d{4}|pokemon', name):
        continue
    t = re.sub(r'pm\d{4}', 'pmNNNN', name)
    t = re.sub(r'(?<=pmNNNN_)\d\d_\d\d', 'FF_VV', t)
    t = re.sub(r'(?<=pmNNNN)_\d\d_\d\d', '_FF_VV', t)
    t = re.sub(r'(?<=wild_single)\d{4}_\d\d_\d\d', 'NNNN_FF_VV', t)
    t = re.sub(r'_\d\d_\d\d_\d', '_xx_xx_x', t)
    tmpl[t] += 1
    examples.setdefault(t, (name, nf, size))
for t, c in tmpl.most_common():
    print(f'{c:5d}  {t}   e.g. {examples[t]}')

# species numbers and model dirs
model_dirs = collections.defaultdict(set)
for name, nf, size in packs:
    m = re.match(r'arc/ik_pokemondatapm(\d{4})pm\d{4}_(\d\d)_(\d\d)', name)
    if m:
        model_dirs[int(m.group(1))].add((int(m.group(2)), int(m.group(3))))
print('species dirs with model packs:', len(model_dirs), 'min', min(model_dirs), 'max', max(model_dirs))
print('form/variant dirs total:', sum(len(v) for v in model_dirs.values()))
json.dump({k: sorted(v) for k, v in sorted(model_dirs.items())}, open(OUT + '/model-dirs.json', 'w'))
ws = set()
for name, nf, size in packs:
    m = re.match(r'arc/param_chrdatacharacterpokemonwild_single(\d{4})_(\d\d)_(\d\d)\.(bin|bfbs)', name)
    if m:
        ws.add((int(m.group(1)), int(m.group(2)), int(m.group(3))))
print('wild_single param entries:', len(ws), 'species', len({x[0] for x in ws}))
json.dump(sorted(ws), open(OUT + '/wild-single.json', 'w'))

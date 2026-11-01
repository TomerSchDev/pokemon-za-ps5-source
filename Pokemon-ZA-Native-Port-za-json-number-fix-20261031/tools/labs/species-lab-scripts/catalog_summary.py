"""Summarise catalog.json: species/form/gender keys, pm folder mapping, overlap with personal presence."""
import json, re, collections
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
P = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port/save-workbench/deps/PKHeX/PKHeX.Core'
names = open(P + '/Resources/text/other/en/text_Species_en.txt', encoding='utf-8-sig').read().splitlines()
cat = json.load(open(S + '/out/catalog.json'))
pers = json.load(open(S + '/out/personal-2.0.2.json'))
present_int = {(r['internal'], r['form']) for r in pers if r['present']}
int2nat = {r['internal']: r['national'] for r in pers}
present_species_int = {r['internal'] for r in pers if r['present']}
species = collections.Counter()
mism = []
pm_map = {}
for e in cat:
    info = e.get('info', {})
    sp, fo, ge = info.get('f0', 0), info.get('f1', 0), info.get('f2', 0)
    m = re.match(r'pm(\d{4})/pm\d{4}_(\d\d)_(\d\d)/', e['f1'])
    pm, ff, vv = int(m.group(1)), int(m.group(2)), int(m.group(3))
    species[sp] += 1
    pm_map.setdefault(sp, set()).add(pm)
    if sp not in present_species_int and sp not in (0, 9999):
        mism.append((sp, fo, ge, e['f1']))
print('catalog entries', len(cat), 'distinct species', len(species))
print('catalog species not present in personal:', mism[:20], len(mism))
print('present species missing from catalog:', sorted(present_species_int - set(species))[:20])
diff = {sp: sorted(v) for sp, v in pm_map.items() if any(p != sp for p in v)}
print('species whose pm folder != internal id:', len(diff))
for sp, v in sorted(diff.items())[:60]:
    print('  internal', sp, 'national', int2nat.get(sp), names[int2nat.get(sp, 0)] if sp in int2nat else '?', '-> pm', v)
# info fields semantics: show form/gender variety
kinds = collections.Counter((e.get('info', {}).get('f1', 0) > 0, e.get('info', {}).get('f2', 0)) for e in cat)
print('(has form, f2) counts:', kinds)
ex = [(e.get('info'), e['f1']) for e in cat if e.get('info', {}).get('f2')][:8]
print('examples with f2:', ex)
ex = [(e.get('info'), e['f1']) for e in cat if e.get('info', {}).get('f1')][:12]
print('examples with f1:', ex)
an = collections.Counter(len(e.get('f4', [])) for e in cat)
print('anim-config count per entry:', an)
sk = collections.Counter(len(e.get('f5', [])) for e in cat)
print('skeleton count per entry:', sk)
print('sample f4/f5/f7:', cat[150].get('f4'), cat[150].get('f5'), cat[150].get('f7'))

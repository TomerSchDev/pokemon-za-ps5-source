"""Map every ik_pokemon/data/pmNNNN model folder (from pack names) to the species that the game's own catalog
(poke_resource_table.trpmcatalog) assigns to it; flag folders whose number is not a present national/internal id."""
import collections, json, re
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
P = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port/save-workbench/deps/PKHeX/PKHeX.Core'
names = open(P + '/Resources/text/other/en/text_Species_en.txt', encoding='utf-8-sig').read().splitlines()
packs = json.load(open(S + '/out/pack-names.json'))['packs']
cat = json.load(open(S + '/out/catalog.json'))
pers = json.load(open(S + '/out/personal-2.0.2.json'))
present_nat = {r['national'] for r in pers if r['present']}
present_int = {r['internal'] for r in pers if r['present']}
int2nat = {r['internal']: r['national'] for r in pers if r['form'] == 0}
# folders (pm number + variant dirs) seen in pack names
folders = collections.defaultdict(set)
for name, nf, size in packs:
    m = re.match(r'arc/ik_pokemondatapm(\d{4})pm\d{4}_(\d\d_\d\d)', name)
    if m: folders[int(m.group(1))].add(m.group(2))
# catalog: pm folder -> (internal species, form, gender)
pm2sp = collections.defaultdict(set)
for e in cat:
    m = re.match(r'pm(\d{4})/pm\d{4}_(\d\d_\d\d)/', e['f1'])
    i = e['info']
    pm2sp[int(m.group(1))].add((i.get('f0', 0), i.get('f1', 0), i.get('f2', 0), m.group(2)))
not_nat = sorted(n for n in folders if n not in present_nat)
not_int = sorted(n for n in folders if n not in present_int)
print('model folders (pm numbers) in pack names:', len(folders))
print('pm numbers that are NOT a present species national number:', len(not_nat))
print('pm numbers that are NOT a present species internal id:', len(not_int))
unmapped = [n for n in folders if n not in pm2sp]
print('folders with no catalog entry:', unmapped)
rows = []
for n in not_nat:
    sps = sorted({(s, f) for s, f, g, v in pm2sp.get(n, [])})
    sp = sps[0][0] if sps else None
    nat = int2nat.get(sp) if sp is not None else None
    rows.append(dict(pm=n, internal=sp, national=nat, name=names[nat] if nat is not None and nat < len(names) else '?',
                     forms=sorted({f for s, f in sps}), dirs=sorted(folders[n])))
json.dump(rows, open(S + '/out/pm-folder-map.json', 'w'), indent=1)
# compact listing grouped by generation-ish ranges
for r in rows:
    print(f"pm{r['pm']:04d} -> internal {r['internal']} national {r['national']} {r['name']} forms {r['forms']} dirs {r['dirs']}")
# general law
same = sum(1 for n in folders if n in pm2sp and all(s == n for s, f, g, v in pm2sp[n]))
print('folders whose number == their species internal id:', same, 'of', len(folders))

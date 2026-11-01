"""Read PKHeX's personal_za resource (PersonalInfo9ZA layout, 0x50 bytes/entry) and summarise presence."""
import json, struct, re
P = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port/save-workbench/deps/PKHeX/PKHeX.Core'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
d = open(P + '/Resources/byte/personal/personal_za', 'rb').read()
n = len(d) // 0x50
MAXS = 1000
names = open(P + '/Resources/text/other/en/text_Species_en.txt', encoding='utf-8').read().splitlines() if True else []
rows = []
for i in range(n):
    e = d[i * 0x50:(i + 1) * 0x50]
    rows.append(dict(idx=i, hp=e[0], type1=e[6], type2=e[7], form_index=struct.unpack_from('<H', e, 0x18)[0], form_count=e[0x1A],
                     present=e[0x1C], dex=struct.unpack_from('<H', e, 0x1E)[0], height=struct.unpack_from('<H', e, 0x20)[0]))
# map each row to (species, form)
sf = {}
for sp in range(MAXS + 1):
    r = rows[sp]
    sf[sp] = (sp, 0)
    if r['form_count'] > 1 and r['form_index']:
        for f in range(1, r['form_count']):
            sf[r['form_index'] + f - 1] = (sp, f)
present_species = sorted({sf[i][0] for i in range(n) if rows[i]['present'] and i in sf})
present_forms = sorted(sf[i] for i in range(n) if rows[i]['present'] and i in sf)
absent_species = [s for s in range(1, 1026) if s not in present_species]
in_dex = sorted({sf[i][0] for i in range(n) if rows[i]['dex'] and i in sf})
print('entries', n, 'species rows 0..', MAXS, 'form rows', n - MAXS - 1)
print('present species', len(present_species), 'present species/form pairs', len(present_forms))
print('species with dex index', len(in_dex))
print('absent national species 1..1025:', len(absent_species))
json.dump(dict(present_species=present_species, present_forms=present_forms, absent=absent_species,
               names={s: names[s] for s in range(1, 1026)}), open(S + '/out/pkhex-presence.json', 'w'))
print('first absent:', [(s, names[s]) for s in absent_species[:30]])
print('present > 900:', [(s, names[s]) for s in present_species if s > 900])

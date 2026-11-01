"""Build the rando-v3 asset set from the existing prepared randomizer assets plus raw game tables.

Read-only on every input. Output (game-derived, NOT for git) is a folder the title ships as /app0/randomizer-assets:
the complete r15 asset set (tables.json, templates, starter deltas, city save, reward assets) plus the v3 index
(v3.json), its row chunks and personal.vanilla.bin.

Nothing here needs the missing fb_codec encoder: every field v3 writes already exists, materialised, in a template
that was encoded with force_defaults (progression-wild.bin, trainers.template.bin) or in the original file
(personal_array.bin, research_lv.bin). Offsets come from decoding those files with their .bfbs / vtables and are
cross-checked against the offsets the r15 assets already carry.

usage: py -3 -I prepare-v3-assets.py --prepared DIR --reward-assets DIR --wild-bfbs FILE --trdata-bfbs FILE
                                      --personal FILE --waza FILE --items FILE --reflection-reader DIR --out DIR
"""
from pathlib import Path
import argparse, hashlib, json, re, struct, sys

p = argparse.ArgumentParser()
p.add_argument('--prepared', type=Path, required=True)        # prepared-streamed (tables.json, templates, starters, save)
p.add_argument('--reward-assets', type=Path, required=True)   # port/randomizer/reward-assets
p.add_argument('--wild-bfbs', type=Path, required=True)       # encount_data_array.bfbs
p.add_argument('--trdata-bfbs', type=Path, required=True)     # trdata_array.bfbs
p.add_argument('--personal', type=Path, required=True)        # avalon/data/personal_array.bin
p.add_argument('--waza', type=Path, required=True)            # avalon/data/waza_array.bin
p.add_argument('--items', type=Path, required=True)           # world/exl/item_data/item_data/item_data.bin
p.add_argument('--reflection-reader', type=Path, required=True)  # dir with reflection_reader.py (randomizer-lab)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
sys.path.insert(0, str(a.reflection_reader.resolve()))
from reflection_reader import Buffer, Schema  # noqa: E402

ALGORITHM = 'za202-randomizer-v3'
BUILD = 'b1f12fd919eae86ab8a978317677e64bce443d1f'
CHUNK = 128


def sha(data): return hashlib.sha256(data).hexdigest()


def load_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def walk(v):
    if isinstance(v, dict):
        yield v
        for k, x in v.items():
            if not k.startswith('$'): yield from walk(x)
    elif isinstance(v, list):
        for x in v: yield from walk(x)


out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
manifest = {}


def ship(src: Path, name=None):
    data = src.read_bytes(); name = name or src.name; dst = out / name
    if dst.exists():
        assert sha(dst.read_bytes()) == sha(data), f'{name} differs from the copy already in {out}'
    else:
        dst.write_bytes(data)
    manifest[name] = {'bytes': len(data), 'sha256': sha(data)}
    return data


# ---------------------------------------------------------------- 1. the complete r15 asset set, unchanged
for src in sorted(a.prepared.iterdir()):
    if src.is_file() and src.suffix in {'.json', '.bin'}: ship(src)
for src in sorted(a.reward_assets.iterdir()):
    if src.is_file() and src.suffix in {'.json', '.bin'}: ship(src)
tables = load_json(a.prepared / 'tables.json')
assert tables['schema'] == 1 and tables['build_id'] == BUILD
progression = load_json(a.reward_assets / 'progression.json')
rewards = load_json(a.reward_assets / 'research-rewards.json')
assert progression['schema'] == 4 and rewards['schema'] == 3


def rows_of(table):
    rows = []
    for f in table['rows_files']:
        data = (a.prepared / f['file']).read_bytes(); assert sha(data) == f['sha256']
        rows += json.loads(data)
    assert len(rows) == table['row_count']
    return rows


wild_rows = rows_of(tables['tables']['wild']); trainer_rows = rows_of(tables['tables']['trainers'])
mega_pairs = {(m['species'], m['mega_form']) for m in tables['mega']}
stones = {m['item'] for m in tables['trainer_megas']}

# ---------------------------------------------------------------- 2. wild: progression-wild.bin is the v3 base
wild_schema = Schema(a.wild_bfbs.read_bytes())
assert wild_schema.root == 'ik.fb.wild_pokemon.EncountDataDBArray'
wild_tpl = (a.reward_assets / 'progression-wild.bin').read_bytes()
assert sha(wild_tpl) == progression['wild_template_sha256'] and len(wild_tpl) == progression['wild_bytes']
wild_vanilla = (a.prepared / 'wild.vanilla.bin').read_bytes()
assert sha(wild_vanilla) == tables['tables']['wild']['vanilla_sha256']
# The template must mean exactly what the original file means (force_defaults only materialises defaults).
assert wild_schema.decode(wild_tpl, offsets=False) == wild_schema.decode(wild_vanilla, offsets=False), 'template semantics'
decoded = wild_schema.decode(wild_tpl)
enc_types = {f['name']: f['type']['base'] for o in wild_schema.objects if o['name'] == 'ik.fb.wild_pokemon.EncountData' for f in o['fields']}
assert enc_types['oyabunProbability'] == 11 and enc_types['minLevel'] == 7 and enc_types['devNo'] == 7
by_id = {x['id']: x for x in walk(decoded) if 'devNo' in x}
guards = {g['identity']: g for g in progression['guards']}
assert set(guards) == {r['identity'] for r in wild_rows} == {i for i, x in by_id.items() if x['devNo'] and 'boss' not in i.lower()}
ZONE = re.compile(r'^ect_(a\d{4})_(w\d\d)_v\d\d_z'); OUT = re.compile(r'^ect_outzone_(a\d{4})_'); DUN = re.compile(r'^ect_(d\d\d_\d\d)_'); ZDM = re.compile(r'^ect_(zdm\d+_sp\d\d)_')


def zone_of(identity):
    m = ZONE.match(identity)
    if m: return 'wild', m.group(1) + '_' + m.group(2)
    m = OUT.match(identity)
    if m: return 'outzone', m.group(1)
    m = DUN.match(identity)
    if m: return 'dungeon', m.group(1)
    m = ZDM.match(identity)
    if m: return 'hyperspace', m.group(1)
    return None, None


v3_wild = []
for r in wild_rows:
    x = by_id[r['identity']]; g = guards[r['identity']]; f = x['$fields']
    assert (x['devNo'], x['formNo'], x['sex']) == (r['species'], r['form'], g['original_sex']) == (g['species'], g['form'], g['original_sex'])
    for name in ('devNo', 'formNo', 'sex'):
        assert f[name] == g['fields'][name]['offset'], (r['identity'], name)
    for name in ('minLevel', 'maxLevel', 'oyabunProbability', 'oyabunAdditionalLevel'):
        assert name in f, (r['identity'], name, 'not materialised')
    assert struct.unpack_from('<f', wild_tpl, f['oyabunProbability'])[0] == float(x['oyabunProbability'])
    assert struct.unpack_from('<i', wild_tpl, f['minLevel'])[0] == x['minLevel']
    cls, grp = zone_of(r['identity'])
    authored = bool(x.get('wazaList'))
    assert g['fixed'] == (authored or g['rock_provider']), r['identity']
    v3_wild.append({'identity': r['identity'], 'species': x['devNo'], 'form': x['formNo'], 'sex': x['sex'],
                    'min_level': x['minLevel'], 'max_level': x['maxLevel'], 'oyabun': float(x['oyabunProbability']), 'oyabun_add': x['oyabunAdditionalLevel'],
                    'authored': authored, 'fixed': bool(g['fixed']), 'rock_provider': bool(g['rock_provider']),
                    'mega': (x['devNo'], x['formNo']) in mega_pairs, 'zone_class': cls, 'zone': grp,
                    'fields': {k: {'offset': f[k], 'bytes': 4, 'signed': True} for k in ('devNo', 'formNo', 'sex', 'minLevel', 'maxLevel', 'oyabunAdditionalLevel')}
                    | {'oyabunProbability': {'offset': f['oyabunProbability'], 'bytes': 4, 'float': True}}})
offsets = [o for r in v3_wild for fld in r['fields'].values() for o in range(fld['offset'], fld['offset'] + 4)]
assert len(offsets) == len(set(offsets)), 'overlapping wild offsets'
assert sum(r['fixed'] for r in v3_wild) == 122 and sum(r['rock_provider'] for r in v3_wild) == 2 and sum(r['mega'] for r in v3_wild) == 23
assert sum(1 for r in v3_wild if r['oyabun'] == 100.0) == 140

# ---------------------------------------------------------------- 3. trainers: the r15 template, plus level/sex/original moves
tr_schema = Schema(a.trdata_bfbs.read_bytes()); assert tr_schema.root == 'trainer.TrdataMainArray'
tr_tpl = (a.prepared / 'trainers.template.bin').read_bytes(); assert sha(tr_tpl) == tables['tables']['trainers']['sha256']
tr_vanilla = (a.prepared / 'trainers.vanilla.bin').read_bytes(); assert sha(tr_vanilla) == tables['tables']['trainers']['vanilla_sha256']
assert tr_schema.decode(tr_tpl, offsets=False) == tr_schema.decode(tr_vanilla, offsets=False), 'trainer template semantics'
trainers = {t['trid']: t for t in tr_schema.decode(tr_tpl)['values']}
assert len(trainers) == 3557
v3_trainers = []
for r in trainer_rows:
    trid, slot = r['identity']; t = trainers[trid]; pk = t[f'poke{slot}']; f = pk['$fields']
    assert pk['devId'] == r['species'] and pk['formId'] == r['form'] and pk['item'] == r['item'] and pk['level'] == r['level']
    for name in ('devId', 'formId', 'item', 'sex'):
        assert f[name] == r['fields'][name]['offset'], (r['identity'], name)
    moves = []
    for i in range(1, 5):
        w = pk[f'waza{i}']; wf = w['$fields']
        assert wf['wazaId'] == r['moves'][i - 1]['wazaId']['offset'] and wf['isPlusWaza'] == r['moves'][i - 1]['isPlusWaza']['offset']
        moves.append({'move': w['wazaId'], 'plus': bool(w['isPlusWaza'])})
    assert struct.unpack_from('<i', tr_tpl, f['level'])[0] == pk['level']
    team = [i for i in range(1, 7) if t[f'poke{i}']['devId']]
    v3_trainers.append({'identity': r['identity'], 'mega': r['mega'], 'mega_trainer': bool(t['megEvolution']), 'team_size': len(team),
                        'species': r['species'], 'form': r['form'], 'item': r['item'], 'level': r['level'], 'sex': pk['sex'], 'moves': moves,
                        'fields': r['fields'] | {'level': {'offset': f['level'], 'bytes': 4, 'signed': True}}, 'move_fields': r['moves']})
assert len(v3_trainers) == 8005
held_pool = sorted({r['item'] for r in v3_trainers if r['item'] and r['item'] not in stones})

# ---------------------------------------------------------------- 4. personal_array.bin (in place): base stats, catch rate, forms
personal_raw = a.personal.read_bytes(); assert sha(personal_raw) == progression['source_hashes']['personal']
pb = Buffer(personal_raw); personal = []
for t in pb.tables(pb.scalar(0, 'I'), 0):
    fields = pb.fields(t); info = fields[0]; species = pb.scalar(info, 'H'); form = pb.scalar(info + 2, 'H')
    assert len(fields) == 26 and fields[20] is not None
    stats = [pb.scalar(fields[20] + i, 'B') for i in range(6)]
    entry = {'species': species, 'form': form, 'present': bool(pb.value(t, 1, '?', False)), 'stats': stats, 'stats_offset': fields[20]}
    if fields[9] is not None: entry['catch'] = pb.scalar(fields[9], 'B'); entry['catch_offset'] = fields[9]
    personal.append(entry)
assert len(personal) == 1445 and sum(e['present'] for e in personal) == 594
present = {(e['species'], e['form']) for e in personal if e['present']}
for s in tables['pool']: assert (s, 0) in present
forms = {}
for sp, fm in sorted(present):
    if (sp, fm) in mega_pairs: continue
    forms.setdefault(sp, []).append(fm)
multi_forms = {str(s): f for s, f in forms.items() if len(f) > 1}
assert len(multi_forms) == 43
ship(a.personal, 'personal.vanilla.bin')

# ---------------------------------------------------------------- 5. moves: implemented (usable) move ids
wb = Buffer(a.waza.read_bytes()); assert sha(a.waza.read_bytes()) == progression['source_hashes']['moves']
usable = sorted(wb.value(t, 0, 'H') for t in wb.tables(wb.scalar(0, 'I'), 0) if wb.value(t, 1, '?'))
assert 300 <= len(usable) <= 400 and 0 not in usable
# TM move lists per (species, form) from personal field 22, usable only (the learnsets in tables.json are already usable-only)
tm_moves = {}
for t in pb.tables(pb.scalar(0, 'I'), 0):
    info = pb.field(t, 0); key = f"{pb.scalar(info, 'H')}:{pb.scalar(info + 2, 'H')}"
    tm_moves[key] = sorted(m for m in {pb.scalar(x, 'H') for x in pb.vector(pb.field(t, 22), 2)} if m in set(usable))
usable_set = set(usable)
for pe in tables['personal']:  # every learnset move of a species that exists in Z-A is implemented (absent species are never chosen)
    if pe['present']:
        for m in pe['learnset']: assert m['move'] == 0 or m['move'] in usable_set, ('unusable learnset move', pe['species'], m)

# ---------------------------------------------------------------- 6. held-item pool sanity against item_data (pocket, cap)
ib = Buffer(a.items.read_bytes()); assert sha(a.items.read_bytes()) == progression['source_hashes']['items']
item_rows = {ib.value(t, 0, 'i'): (ib.value(t, 5, 'i'), ib.value(t, 6, 'i')) for t in ib.tables(ib.scalar(0, 'I'), 0)}
for it in held_pool: assert it in item_rows and item_rows[it][0] in (2, 5) and item_rows[it][1] >= 1, it

# ---------------------------------------------------------------- 7. research points (same file research_rewards.cpp writes)
research_raw = (a.reward_assets / 'research-rewards.bin').read_bytes(); assert sha(research_raw) == rewards['sha256']
rb = Buffer(research_raw); research_rows = []
for i, t in enumerate(rb.tables(rb.scalar(0, 'I'), 0), 1):
    fields = rb.fields(t); assert rb.scalar(fields[0], 'I') == i
    if i == 1: assert len(fields) == 1; continue
    level, points = rb.scalar(fields[0], 'I'), rb.scalar(fields[1], 'I')
    row = next(x for x in rewards['rows'] if x['level'] == level); assert row['points'] == points and row['item_offset'] == fields[2]
    research_rows.append({'level': level, 'points': points, 'points_offset': fields[1]})
assert [r['points'] for r in research_rows] == sorted(r['points'] for r in research_rows) and len(research_rows) == 49


# ---------------------------------------------------------------- 8. write the v3 index and chunks
def chunks(name, rows):
    files = []
    for i in range(0, len(rows), CHUNK):
        batch = rows[i:i + CHUNK]; data = json.dumps(batch, separators=(',', ':'), ensure_ascii=True).encode()
        assert len(data) <= 512 * 1024
        fname = f'{name}.rows-{i // CHUNK:03d}.json'; (out / fname).write_bytes(data)
        manifest[fname] = {'bytes': len(data), 'sha256': sha(data)}
        files.append({'file': fname, 'count': len(batch), 'sha256': sha(data)})
    return files


personal_data = json.dumps({'entries': personal, 'multi_forms': multi_forms, 'tm_moves': tm_moves}, separators=(',', ':')).encode()
(out / 'v3.personal.json').write_bytes(personal_data); manifest["v3.personal.json"] = {"bytes": len(personal_data), "sha256": sha(personal_data)}
zones = {}
for r in v3_wild:
    if r['zone_class']: zones.setdefault(r['zone_class'], {}).setdefault(r['zone'], 0); zones[r['zone_class']][r['zone']] += 1
index = {
    'schema': 'za-rando-v3-1', 'algorithm': ALGORITHM, 'build_id': BUILD, 'base_algorithm': tables['algorithm'],
    'wild': {'template': 'progression-wild.bin', 'template_sha256': sha(wild_tpl), 'bytes': len(wild_tpl),
             'vanilla': 'wild.vanilla.bin', 'vanilla_sha256': sha(wild_vanilla), 'path': tables['tables']['wild']['path'],
             'row_count': len(v3_wild), 'rows_files': chunks('v3.wild', v3_wild), 'zones': zones},
    'trainers': {'template': 'trainers.template.bin', 'template_sha256': sha(tr_tpl), 'bytes': len(tr_tpl),
                 'vanilla': 'trainers.vanilla.bin', 'vanilla_sha256': sha(tr_vanilla), 'path': tables['tables']['trainers']['path'],
                 'row_count': len(v3_trainers), 'rows_files': chunks('v3.trainers', v3_trainers), 'held_item_pool': held_pool},
    'personal': {'file': 'personal.vanilla.bin', 'sha256': sha(personal_raw), 'bytes': len(personal_raw), 'path': 'avalon/data/personal_array.bin',
                 'entries_file': 'v3.personal.json', 'entries_sha256': sha(personal_data), 'entries_bytes': len(personal_data), 'present': 594, 'multi_form_species': len(multi_forms)},
    'moves': {'usable': usable, 'source_sha256': progression['source_hashes']['moves']},
    'research': {'file': 'research-rewards.bin', 'sha256': rewards['sha256'], 'rows': research_rows},
    'sources': {'tables_json_sha256': manifest['tables.json']['sha256'], 'progression_json_sha256': manifest['progression.json']['sha256'],
                'research_rewards_json_sha256': manifest['research-rewards.json']['sha256'], 'starter_deltas_sha256': manifest['starter-deltas.json']['sha256'],
                'wild_bfbs_sha256': sha(a.wild_bfbs.read_bytes()), 'trdata_bfbs_sha256': sha(a.trdata_bfbs.read_bytes()),
                'item_data_sha256': progression['source_hashes']['items']},
}
index_data = json.dumps(index, separators=(',', ':'), sort_keys=True).encode()
(out / 'v3.json').write_bytes(index_data); manifest['v3.json'] = {'bytes': len(index_data), 'sha256': sha(index_data)}
(out / 'asset-manifest-v3.json').write_text(json.dumps(manifest, indent=2, sort_keys=True))
(out / 'assets_hashes_v3.h').write_text(
    f'#define ZA_TABLES_SHA256 "{manifest["tables.json"]["sha256"]}"\n#define ZA_STARTERS_SHA256 "{manifest["starter-deltas.json"]["sha256"]}"\n'
    f'#define ZA_REWARDS_SHA256 "{manifest["research-rewards.json"]["sha256"]}"\n#define ZA_PROGRESSION_SHA256 "{manifest["progression.json"]["sha256"]}"\n'
    f'#define ZA_V3_SHA256 "{manifest["v3.json"]["sha256"]}"\n')
print(json.dumps({'status': 'PASS', 'files': len(manifest), 'v3_sha256': manifest['v3.json']['sha256'],
                  'wild_rows': len(v3_wild), 'trainer_rows': len(v3_trainers), 'zones': {k: len(v) for k, v in zones.items()},
                  'usable_moves': len(usable), 'held_item_pool': len(held_pool), 'multi_form_species': len(multi_forms),
                  'bytes': sum(m['bytes'] for m in manifest.values())}))

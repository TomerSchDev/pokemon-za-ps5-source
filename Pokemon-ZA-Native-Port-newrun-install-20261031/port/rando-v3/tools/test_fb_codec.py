"""Round-trip the reconstructed fb_codec against the r15 assets, bit for bit.

Every {"offset","bytes","signed"} record the C++ core consumes today (tables.json wild/trainers/dlc_boss rows and
their move sub-tables, progression.json guard fields on both templates, research-rewards.json offsets) must be
reproduced from the .bfbs + the template bytes alone.

usage: py -3 -I test_fb_codec.py --prepared DIR --reward-assets DIR --wild-bfbs F --trdata-bfbs F --dlc-bfbs F --reflection-reader DIR
"""
from pathlib import Path
import argparse, hashlib, json, struct, sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_codec import Table  # noqa: E402

p = argparse.ArgumentParser()
for name in ('prepared', 'reward_assets', 'wild_bfbs', 'trdata_bfbs', 'dlc_bfbs', 'reflection_reader'):
    p.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
a = p.parse_args()
rr = [a.reflection_reader]


def sha(b): return hashlib.sha256(b).hexdigest()


def rows_of(table):
    rows = []
    for f in table['rows_files']:
        data = (a.prepared / f['file']).read_bytes(); assert sha(data) == f['sha256']; rows += json.loads(data)
    assert len(rows) == table['row_count']; return rows


tables = json.loads((a.prepared / 'tables.json').read_text()); checked = 0

# wild: tables.json rows on wild.template.bin; progression.json guards on progression-wild.bin + generated_fields on wild.template.bin
wild = Table(a.wild_bfbs.read_bytes(), (a.prepared / 'wild.template.bin').read_bytes(), rr)
by_id = {r.value('id'): r for r in wild.rows('ik.fb.wild_pokemon.EncountData')}
for r in rows_of(tables['tables']['wild']):
    assert by_id[r['identity']].fields(('devNo', 'formNo', 'sex')) == r['fields'], r['identity']; checked += 3
prog = json.loads((a.reward_assets / 'progression.json').read_text())
pw = Table(a.wild_bfbs.read_bytes(), (a.reward_assets / 'progression-wild.bin').read_bytes(), rr)
pby = {r.value('id'): r for r in pw.rows('ik.fb.wild_pokemon.EncountData')}
for g in prog['guards']:
    assert pby[g['identity']].fields(('devNo', 'formNo', 'sex')) == g['fields'], g['identity']
    assert by_id[g['identity']].fields(('devNo', 'formNo', 'sex')) == g['generated_fields'], g['identity']; checked += 6
    f = pby[g['identity']].fields(('oyabunProbability',))['oyabunProbability']
    assert f['float'] and f['bytes'] == 4 and struct.unpack_from('<f', pw.data, f['offset'])[0] == pby[g['identity']].value('oyabunProbability')
# The r6 species template intentionally differs in wazaList; only the progression template promises complete
# semantic equality to vanilla, so check that promise rather than hiding the r6 difference behind `or True`.
assert pw.plain() == Table(a.wild_bfbs.read_bytes(), (a.prepared / 'wild.vanilla.bin').read_bytes(), rr).plain()

# trainers: slot scalars + the four WazaSetBattle sub-tables of every slot
tr = Table(a.trdata_bfbs.read_bytes(), (a.prepared / 'trainers.template.bin').read_bytes(), rr)
trainers = {r.value('trid'): r for r in tr.rows('trainer.TrdataMain')}
for r in rows_of(tables['tables']['trainers']):
    trid, slot = r['identity']; node = trainers[trid].node[f'poke{slot}']
    from fb_codec import Row
    pk = Row(tr, node, tr._by_name['PokeDataBattle'])
    assert pk.fields(('devId', 'formId', 'item', 'sex')) == r['fields'], r['identity']; checked += 4
    for i in range(1, 5):
        w = Row(tr, node[f'waza{i}'], tr._by_name['WazaSetBattle'])
        assert w.fields(('wazaId', 'isPlusWaza')) == r['moves'][i - 1], (r['identity'], i); checked += 2
    assert pk.fields(('level',))['level'] == {'offset': node['$fields']['level'], 'bytes': 4, 'signed': True}

# dlc_boss: scalar fields + the reserved battleId string (capacity 128 convention)
dlc = Table(a.dlc_bfbs.read_bytes(), (a.prepared / 'dlc_boss.template.bin').read_bytes(), rr)
drows = {}
for o in dlc.schema.objects:
    names = {f['name'] for f in o['fields']}
    if {'bossLotteryId', 'battleId', 'devNo', 'formNo', 'estimateLevel', 'extensionLevel'} <= names:
        drows = {r.value('bossLotteryId'): r for r in dlc.rows(o['name'])}
for r in rows_of(tables['tables']['dlc_boss']):
    got = drows[r['identity']].fields(('battleId', 'devNo', 'formNo', 'estimateLevel', 'extensionLevel'))
    assert got == r['fields'], r['identity']; checked += 5

# research_lv.bin has no .bfbs: vtable walk only (reflection_reader.Buffer), as prepare-research-rewards.py did
rew = json.loads((a.reward_assets / 'research-rewards.json').read_text())
sys.path.insert(0, str(a.reflection_reader)); from reflection_reader import Buffer  # noqa: E402
rb = Buffer((a.reward_assets / 'research-rewards.bin').read_bytes())
for i, t in enumerate(rb.tables(rb.scalar(0, 'I'), 0), 1):
    if i == 1: continue
    f = rb.fields(t); row = next(x for x in rew['rows'] if x['level'] == i)
    assert (f[2], f[3]) == (row['item_offset'], row['quantity_offset']); checked += 2
print(json.dumps({'status': 'PASS', 'records_reproduced': checked, 'tables': ['wild (2 templates)', 'trainers', 'dlc_boss', 'research_lv']}))

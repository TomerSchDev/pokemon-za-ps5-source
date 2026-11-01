"""Independent Python oracle for rando-v3: recompute every table of a run from the assets and the run's settings,
then compare SHA-256 (or bytes) with what the C++ generator reported or published.

Nothing here imports or calls the C++ code; the sampler (HMAC-SHA256 keyed by the seed), the pools, the zone
groups, the swap groups, the level/Alpha/form arithmetic and the legacy rock-route / research-reward samplers are
re-implemented from the written rules (README-HE.md) and the r15 assets.

    py -3 -I oracle_v3.py --assets DIR --reports OUT/reports.json [--write OUT/verification.json]
    py -3 -I oracle_v3.py --assets DIR --run RUN_DIR          # a published run: report.json + romfs/<tables>
"""
from pathlib import Path
import argparse, hashlib, hmac, json, struct, sys

BASE_ALGORITHM = 'za202-randomizer-alpha1'
BUILD = 'b1f12fd919eae86ab8a978317677e64bce443d1f'
TWO64 = 1 << 64


def dumps(x): return json.dumps(x, separators=(',', ':'), ensure_ascii=False, sort_keys=True)


def sha(b): return hashlib.sha256(b).hexdigest()


class Rng:
    def __init__(self, seed):
        self.key = hashlib.sha256(dumps([BASE_ALGORITHM, BUILD, seed]).encode()).digest()
        self.cache = {}

    def number(self, domain, identity, bound):
        assert bound > 0
        rem = TWO64 % bound
        for retry in range(1000):
            msg = dumps([domain, identity, retry]).encode()
            w = int.from_bytes(hmac.new(self.key, msg, hashlib.sha256).digest()[:8], 'big')
            if rem == 0 or w <= TWO64 - 1 - rem: return w % bound
        raise AssertionError('rejection sampling exhausted')

    def permutation(self, domain, identity, n, cycle):
        perm = list(range(n))
        for i in range(n - 1, 0, -1):
            j = self.number(domain, list(identity) + [i], i if cycle else i + 1)
            perm[i], perm[j] = perm[j], perm[i]
        return perm


class Pool:
    def __init__(self, values): self.values = sorted(values, key=dumps)

    def choose(self, rng, domain, identity, reject):
        cands = [v for v in self.values if not reject(v)]
        if not cands: raise AssertionError('empty pool')
        return cands[rng.number(domain, identity, len(cands))]


def put_i(data, off, width, value):
    struct.pack_into('<' + {1: 'b', 2: 'h', 4: 'i', 8: 'q'}[width] if value < 0 else '<' + {1: 'B', 2: 'H', 4: 'I', 8: 'Q'}[width], data, off, value)


def put_field(data, f, value):
    if f.get('float'): struct.pack_into('<f', data, f['offset'], float(value)); return
    if 'capacity' in f:
        s = value.encode(); cap = f['capacity']; assert len(s) <= cap
        data[f['data']:f['data'] + cap + 1] = bytes(cap + 1); data[f['data']:f['data'] + len(s)] = s
        struct.pack_into('<I', data, f['length'], len(s)); return
    width = f['bytes']
    if f.get('signed'): struct.pack_into('<' + {1: 'b', 2: 'h', 4: 'i', 8: 'q'}[width], data, f['offset'], value)
    else: struct.pack_into('<' + {1: 'B', 2: 'H', 4: 'I', 8: 'Q'}[width], data, f['offset'], value)


def scale_level(level, pct): return max(1, min(100, (level * (100 + pct) + 50) // 100))


class Assets:
    def __init__(self, d):
        self.dir = Path(d)
        self.tables = self.json('tables.json'); self.starters = self.json('starter-deltas.json')
        self.progression = self.json('progression.json'); self.rewards = self.json('research-rewards.json'); self.v3 = self.json('v3.json')
        assert self.v3['schema'] == 'za-rando-v3-1' and self.v3['build_id'] == BUILD
        self.wild_rows = self.rows(self.v3['wild']); self.trainer_rows = self.rows(self.v3['trainers'])
        self.dlc_rows = self.rows(self.tables['tables']['dlc_boss'])
        pe = self.verified(self.v3['personal']['entries_file'], self.v3['personal']['entries_sha256']); self.personal = json.loads(pe)
        self.learnsets = {(p['species'], p['form']): p for p in self.tables['personal']}
        self.bst = {(e['species'], e['form']): sum(e['stats']) for e in self.personal['entries']}
        self.pool = Pool(self.tables['pool']); self.megas = Pool(self.tables['mega']); self.trainer_megas = Pool(self.tables['trainer_megas'])
        self.stones = {m['item'] for m in self.tables['mega'] if m['item'] > 0}

    def json(self, name): return json.loads((self.dir / name).read_text(encoding='utf-8'))

    def verified(self, name, digest, size=None):
        b = (self.dir / name).read_bytes(); assert sha(b) == digest, name
        if size is not None: assert len(b) == size, name
        return b

    def rows(self, table):
        rows = []
        for f in table['rows_files']: rows += json.loads(self.verified(f['file'], f['sha256']))
        assert len(rows) == table['row_count']; return rows

    def entry(self, sp, form):
        e = self.learnsets.get((sp, form))
        if e is None and form: e = self.learnsets.get((sp, 0))
        return e

    def learnset_moves(self, sp, form, level):
        e = self.entry(sp, form)
        if e is None: return []
        learned, available = [], []
        for m in e['learnset']:
            if not m['move'] or m['level'] < 0: continue
            available.append(m)
            if m['level'] > max(1, level): continue
            learned = [x for x in learned if x['move'] != m['move']] + [m]
        if not learned and available: learned = [sorted(available, key=lambda m: m['level'])[0]]
        return learned[-4:]

    def mastery(self, sp, form, move):
        e = self.entry(sp, form)
        return max([m['mastery'] for m in e['learnset'] if m['move'] == move], default=0) if e else 0


# ---------------------------------------------------------------- legacy samplers (rock route, research rewards)
def rock_choose(seed, domain, bound):
    for retry in range(1000):
        msg = json.dumps(['za202-rock-route-v1', seed, domain, retry], separators=(',', ':')).encode()
        v = int.from_bytes(hashlib.sha256(msg).digest()[:8], 'big')
        if v < TWO64 - (TWO64 % bound): return v % bound
    raise AssertionError


def rock_route(spec, seed, wild, rewards):
    r = spec['rock']
    if wild and rock_choose(seed, 'route', 2) == 0:
        out = dict(r['natural_candidates'][rock_choose(seed, 'natural-species', len(r['natural_candidates']))]); out.update(mode='natural', tm_item=0)
    else:
        tm = r['tm_routes'][rock_choose(seed, 'tm-item', len(r['tm_routes'])) if rewards else 0]
        out = dict(tm['candidates'][rock_choose(seed, 'tm-species', len(tm['candidates']))]) if wild else {'species': 659, 'name': 'Bunnelby'}
        out.update(mode='tm', tm_item=tm['item'], tm_name=tm['name'], move=tm['move'])
    out.update(locations=r['locations'], algorithm='za202-rock-route-v1'); return out


def research_rewards(a, seed, route, data):
    spec = a.rewards; locked = {r['item'] for r in spec['rows'] if r['locked']}
    pool = [x for x in spec['pool'] if x['item'] not in locked]
    for row in spec['rows']:
        if row['locked']: continue
        required = route['tm_item'] if row.get('rock_route_reward') and route['mode'] == 'tm' else 0
        eligible = [i for i, p in enumerate(pool) if (p['item'] == required if required else p['item'] != row['item']) and ('allowed_items' not in row or p['item'] in row['allowed_items'])]
        bound = len(eligible)
        for attempt in range(1000):
            msg = json.dumps(['za202-research-rewards-v3', spec['build_id'], seed, row['level'], attempt], separators=(',', ':')).encode()
            word = int.from_bytes(hashlib.sha256(msg).digest()[:8], 'big')
            if word < TWO64 - (TWO64 % bound): break
        else: raise AssertionError
        target = pool.pop(eligible[word % bound])
        struct.pack_into('<I', data, row['item_offset'], target['item']); struct.pack_into('<I', data, row['quantity_offset'], min(row['quantity'], target['max_quantity']))


# ---------------------------------------------------------------- the tables
def zone_groups(rows):
    g = {}
    for i, r in enumerate(rows):
        if r['zone_class']: g.setdefault(r['zone_class'], {}).setdefault(r['zone'], []).append(i)
    return g


def by_level(rows, idx): return sorted(idx, key=lambda i: (rows[i]['min_level'], rows[i]['max_level'], rows[i]['identity']))


def zone_donors(rng, domain, groups):
    donor = {}
    for cls, zones in groups.items():
        order = sorted(zones)
        if len(order) < 2: donor.update({z: z for z in order}); continue
        perm = rng.permutation(domain, [cls], len(order), True)
        for k, z in enumerate(order): donor[z] = order[perm[k]]
    return donor


def wild_table(a, rng, s, route):
    rows = a.wild_rows; idx = a.v3['wild']
    fields_vanilla = s['wild_levels'] == 'vanilla' and s['alpha_rate'] == 'vanilla' and s['forms'] == 'vanilla'
    if s['wild_mode'] == 'off' and fields_vanilla: return a.verified(idx['vanilla'], idx['vanilla_sha256'])
    data = bytearray(a.verified(idx['template'], idx['template_sha256'], idx['bytes']))
    chaos = s['wild_mode'] == 'chaos'
    choice = [(r['species'], r['form'], r['sex']) for r in rows]
    mega_of = lambda r: next(m for m in a.tables['mega'] if m['species'] == r['species'] and m['mega_form'] == r['form'])
    if s['wild_mode'] in ('random', 'chaos'):
        for i, r in enumerate(rows):
            if not chaos and r['rock_provider']: choice[i] = (route['species'], 0, 0); continue
            if not chaos and r['fixed']: continue
            if r['mega']:
                orig = mega_of(r); m = a.megas.choose(rng, 'wild-mega', r['identity'], lambda v: v == orig); choice[i] = (m['species'], m['mega_form'], 0)
            else:
                sp = a.pool.choose(rng, 'wild', r['identity'], lambda v: v == r['species']); choice[i] = (sp, 0, -1 if chaos else 0)
    elif s['wild_mode'] in ('zones', 'in_zone'):
        groups = zone_groups(rows)
        ordinary = lambda members: by_level(rows, [i for i in members if not rows[i]['fixed'] and not rows[i]['mega']])
        if s['wild_mode'] == 'zones':
            donor = zone_donors(rng, 'wild-zone-shuffle', groups)
            for cls, zones in groups.items():
                for zone, members in zones.items():
                    slots, frm = ordinary(members), ordinary(groups[cls][donor[zone]])
                    if not frm or donor[zone] == zone: continue
                    for k, i in enumerate(slots):
                        d = rows[frm[k * len(frm) // len(slots)]]; choice[i] = (d['species'], d['form'], d['sex'])
        else:
            for cls, zones in groups.items():
                for zone, members in zones.items():
                    slots = ordinary(members)
                    if len(slots) < 2: continue
                    perm = rng.permutation('wild-in-zone', [zone], len(slots), False)
                    for k, i in enumerate(slots):
                        d = rows[slots[perm[k]]]; choice[i] = (d['species'], d['form'], d['sex'])
        for i, r in enumerate(rows):
            if r['rock_provider']: choice[i] = (route['species'], 0, 0)
    if s['forms'] == 'random' or chaos:
        multi = a.personal['multi_forms']
        for i, r in enumerate(rows):
            if r['mega'] or (not chaos and (r['fixed'] or r['rock_provider'])): continue
            forms = multi.get(str(choice[i][0]))
            if forms: choice[i] = (choice[i][0], forms[rng.number('wild-form', r['identity'], len(forms))], choice[i][2])
    levels = [(r['min_level'], r['max_level']) for r in rows]
    protected = lambda i: not chaos and rows[i]['rock_provider']
    if s['wild_levels'] in ('plus10', 'plus25'):
        pct = 10 if s['wild_levels'] == 'plus10' else 25
        levels = [lv if protected(i) else (scale_level(lv[0], pct), scale_level(lv[1], pct)) for i, lv in enumerate(levels)]
    elif s['wild_levels'] == 'range':
        for i, r in enumerate(rows):
            if protected(i): continue
            lo = max(1, min(100, r['min_level'] + rng.number('wild-level-range-min', r['identity'], 11) - 5))
            hi = max(1, min(100, r['max_level'] + rng.number('wild-level-range-max', r['identity'], 11) - 5))
            levels[i] = (min(lo, hi), max(lo, hi))
    elif s['wild_levels'] == 'mixed':
        groups = zone_groups(rows); donor = zone_donors(rng, 'wild-level-zones', groups)
        for cls, zones in groups.items():
            for zone, members in zones.items():
                slots, frm = by_level(rows, members), by_level(rows, groups[cls][donor[zone]])
                if not frm or donor[zone] == zone: continue
                for k, i in enumerate(slots):
                    if protected(i): continue
                    d = rows[frm[k * len(frm) // len(slots)]]; levels[i] = (d['min_level'], d['max_level'])
    for i, r in enumerate(rows):
        f = r['fields']
        put_field(data, f['devNo'], choice[i][0]); put_field(data, f['formNo'], choice[i][1]); put_field(data, f['sex'], choice[i][2])
        put_field(data, f['minLevel'], levels[i][0]); put_field(data, f['maxLevel'], levels[i][1])
        p = r['oyabun']
        if 0 < p < 100 and (chaos or not r['rock_provider']):
            p = {'vanilla': p, 'x2': min(100.0, p * 2), 'x5': min(100.0, p * 5), 'always': 100.0}[s['alpha_rate']]
        if p != r['oyabun']: put_field(data, f['oyabunProbability'], p)
    return bytes(data)


def swap_donors(rng, rows):
    teams = {}
    for i, r in enumerate(rows):
        t = teams.setdefault(r['identity'][0], {'trid': r['identity'][0], 'max': 0, 'slots': []}); t['max'] = max(t['max'], r['level']); t['slots'].append(i)
    by_key = {}
    for t in teams.values():
        mask = sum(1 << k for k, i in enumerate(t['slots']) if rows[i]['mega']); t['key'] = len(t['slots']) * 64 + mask
        by_key.setdefault(t['key'], []).append(t)
    donor = {}
    for key in sorted(by_key):
        lst = sorted(by_key[key], key=lambda t: (t['max'], t['trid'])); groups, cur = [], []
        for t in lst:
            if cur and len(cur) >= 4 and t['max'] - cur[0]['max'] > 10: groups.append(cur); cur = []
            cur.append(t)
        if cur:
            if len(cur) < 4 and groups: groups[-1] += cur
            else: groups.append(cur)
        for g, members in enumerate(groups):
            if len(members) < 2: donor.update({t['trid']: t['trid'] for t in members}); continue
            perm = rng.permutation('trainer-swap', [key, g], len(members), True)
            for k, t in enumerate(members): donor[t['trid']] = members[perm[k]]['trid']
    return donor


def trainers_table(a, rng, s):
    rows = a.trainer_rows; idx = a.v3['trainers']
    fields_vanilla = s['trainer_levels'] == 'vanilla' and s['trainer_moves'] == 'learnset' and s['trainer_items'] == 'vanilla'
    if s['trainers_mode'] == 'off' and s['mega_trainers'] == 'off' and fields_vanilla: return a.verified(idx['vanilla'], idx['vanilla_sha256'])
    data = bytearray(a.verified(idx['template'], idx['template_sha256'], idx['bytes']))
    team_slots = {}
    for i, r in enumerate(rows): team_slots.setdefault(r['identity'][0], []).append(i)
    donor = swap_donors(rng, rows) if s['trainers_mode'] == 'swap' else {}
    usable = a.v3['moves']['usable']; held = idx['held_item_pool']
    pct = {'vanilla': 0, 'plus10': 10, 'plus20': 20, 'plus30': 30}[s['trainer_levels']]
    for i, r in enumerate(rows):
        trid, slot = r['identity']; identity = [trid, slot]
        species, form, item, sex = r['species'], r['form'], r['item'], r['sex']; level = scale_level(r['level'], pct) if pct else r['level']
        moves = [(m['move'], m['plus']) for m in r['moves']]; from_learnset = False
        if r['mega']:
            if s['mega_trainers'] == 'on':
                m = a.trainer_megas.choose(rng, 'trainer-mega', identity, lambda v: v['species'] == r['species'] and v['form'] == r['form'])
                species, form, item, sex = m['species'], m['form'], m['item'], 0; from_learnset = True
        elif s['trainers_mode'] == 'random':
            species = a.pool.choose(rng, 'trainer', identity, lambda v: v == r['species']); form = 0; sex = 0; from_learnset = True
            if item in a.stones: item = 0
        elif s['trainers_mode'] == 'strength':
            target = a.bst.get((r['species'], r['form']), a.bst[(r['species'], 0)]); band = max(20, target // 10); chosen = None
            for _ in range(12):
                reject = lambda v, band=band: v == r['species'] or abs(a.bst[(v, 0)] - target) > band
                if sum(1 for v in a.pool.values if not reject(v)) >= 8: chosen = a.pool.choose(rng, 'trainer-strength', identity, reject); break
                band = band * 3 // 2
            assert chosen is not None
            species, form, sex = chosen, 0, 0; from_learnset = True
            if item in a.stones: item = 0
        elif s['trainers_mode'] == 'swap':
            frm = donor[trid]
            if frm != trid:
                pos = team_slots[trid].index(i); d = rows[team_slots[frm][pos]]; assert not d['mega']
                species, form, item, sex = d['species'], d['form'], 0 if d['item'] in a.stones else d['item'], d['sex']
                moves = [(m['move'], m['plus']) for m in d['moves']]
        if not r['mega'] and s['trainer_items'] == 'random': item = held[rng.number('trainer-item', identity, len(held))]
        elif not r['mega'] and s['trainer_items'] == 'none': item = 0
        if s['trainer_moves'] == 'learnset':
            if from_learnset:
                learned = a.learnset_moves(species, form, level); assert learned
                moves = [(learned[k]['move'], 0 < learned[k]['mastery'] <= level) if k < len(learned) else (0, False) for k in range(4)]
        else:
            if s['trainer_moves'] == 'any': cands = list(usable)
            else:
                e = a.entry(species, form); st = {m['move'] for m in e['learnset'] if m['move']} if e else set()
                tm = a.personal['tm_moves'].get(f'{species}:{form}', a.personal['tm_moves'].get(f'{species}:0', [])); cands = sorted(st | set(tm))
            moves = []
            for k in range(4):
                if not cands: moves.append((0, False)); continue
                at = rng.number('trainer-move', [trid, slot, k], len(cands)); move = cands.pop(at)
                mastery = a.mastery(species, form, move) if s['trainer_moves'] == 'legal' else 0
                moves.append((move, 0 < mastery <= level))
        f = r['fields']
        put_field(data, f['devId'], species); put_field(data, f['formId'], form); put_field(data, f['sex'], sex); put_field(data, f['item'], item); put_field(data, f['level'], level)
        for k in range(4): put_field(data, r['move_fields'][k]['wazaId'], moves[k][0]); put_field(data, r['move_fields'][k]['isPlusWaza'], 1 if moves[k][1] else 0)
    return bytes(data)


def dlc_table(a, rng, s):
    t = a.tables['tables']['dlc_boss']
    if s['dlc_rematches'] == 'off': return a.verified('dlc_boss.vanilla.bin', t['vanilla_sha256'])
    data = bytearray(a.verified(t['file'], t['sha256'], t['bytes'])); rows = a.dlc_rows
    ids = sorted(r['identity'] for r in rows); sources = {r['identity']: r['source'] for r in rows}
    for i in range(len(ids) - 1, 0, -1):
        j = rng.number('dlc-mega-rematch', i, i + 1); ids[i], ids[j] = ids[j], ids[i]
    mapping = {ids[i]: ids[(i + 1) % len(ids)] for i in range(len(ids))}
    for r in rows:
        for f, value in sources[mapping[r['identity']]].items(): put_field(data, r['fields'][f], value)
    return bytes(data)


def research_table(a, seed, s, route):
    if s['research_rewards'] == 'off' and s['research_requirements'] == 'vanilla': return None
    data = bytearray(a.verified('research-rewards.bin', a.rewards['sha256'], a.rewards['bytes']))
    if s['research_rewards'] == 'on': research_rewards(a, seed, route, data)
    if s['research_requirements'] != 'vanilla':
        prev = 0
        for row in a.v3['research']['rows']:
            p = row['points']; scaled = p // 2 if s['research_requirements'] == 'easier' else p * 3 // 2
            nxt = min(max(scaled, prev + 1), 0xFFFFFFFF); struct.pack_into('<I', data, row['points_offset'], nxt); prev = nxt
    return bytes(data)


def personal_table(a, rng, s):
    if s['base_stats'] == 'vanilla' and s['catch_rate'] == 'vanilla': return None
    idx = a.v3['personal']; data = bytearray(a.verified(idx['file'], idx['sha256'], idx['bytes']))
    for e in a.personal['entries']:
        if not e['present']: continue
        ident = [e['species'], e['form']]; stats = list(e['stats'])
        if s['base_stats'] == 'shuffle':
            perm = rng.permutation('base-stats', ident, 6, False); stats = [stats[perm[k]] for k in range(6)]
        elif s['base_stats'] == 'random':
            stats = [max(1, min(255, (stats[k] * (70 + rng.number('base-stat-random', ident + [k], 61)) + 50) // 100)) for k in range(6)]
        data[e['stats_offset']:e['stats_offset'] + 6] = bytes(stats)
        if s['catch_rate'] != 'vanilla' and 'catch_offset' in e:
            data[e['catch_offset']] = 255 if s['catch_rate'] == 'max' else min(255, e['catch'] * 2)
    return bytes(data)


def starter_save(a, rng, s):
    pick = s.get('starter_pick')
    if not pick: pick = Pool([e['species'] for e in a.starters['entries']]).choose(rng, 'city-starter-v1', 0, lambda v: False)
    entry = next(e for e in a.starters['entries'] if e['species'] == pick)
    save = bytearray(a.verified('city-save.bin', a.starters['template_sha256'], a.starters['template_bytes']))
    for p in entry['patches']:
        b = bytes.fromhex(p['hex']); save[p['offset']:p['offset'] + len(b)] = b
    assert sha(save) == entry['output_sha256']
    return pick, bytes(save)


def recompute(a, seed, s):
    rng = Rng(seed)
    route = rock_route(a.progression, seed, s['wild_mode'] != 'off', s['research_rewards'] == 'on')
    out = {'wild': wild_table(a, rng, s, route), 'trainers': trainers_table(a, rng, s), 'dlc_boss': dlc_table(a, rng, s)}
    rt = research_table(a, seed, s, route)
    if rt is not None: out['research_rewards'] = rt
    pt = personal_table(a, rng, s)
    if pt is not None: out['personal'] = pt
    pick, save = starter_save(a, rng, s)
    return route, out, pick, save


def check_report(a, report, tables_bytes=None):
    """tables_bytes: {name: bytes} of published files (run mode); else compare SHA-256 with the report."""
    s = report['ui_options_resolved']['values']; seed = report['seed']
    route, tables, pick, save = recompute(a, seed, s)
    failures = []
    if route != report['rock_route']: failures.append('rock_route')
    if pick != report['starter'] or sha(save) != report['save_sha256']: failures.append('starter/save')
    if set(tables) != set(report['table_sha256']): failures.append('table set %s vs %s' % (sorted(tables), sorted(report['table_sha256'])))
    for name, data in tables.items():
        if name not in report['table_sha256']: continue
        if sha(data) != report['table_sha256'][name]: failures.append(name)
        if tables_bytes is not None and name in tables_bytes and tables_bytes[name] != data: failures.append(name + ' (published bytes)')
    return failures, sorted(tables)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--assets', type=Path, required=True); p.add_argument('--reports', type=Path); p.add_argument('--run', type=Path)
    p.add_argument('--write', type=Path); p.add_argument('--limit', type=int, default=0)
    args = p.parse_args(); a = Assets(args.assets)
    result = {'status': 'PASS', 'checked': 0, 'failed': [], 'tables_seen': {}, 'labels': {}}
    if args.reports:
        entries = json.loads(args.reports.read_text(encoding='utf-8'))
        if args.limit: entries = entries[:args.limit]
        for e in entries:
            failures, names = check_report(a, e['report'])
            result['checked'] += 1; result['labels'][e['label']] = result['labels'].get(e['label'], 0) + 1
            for n in names: result['tables_seen'][n] = result['tables_seen'].get(n, 0) + 1
            if failures: result['failed'].append({'label': e['label'], 'seed': e['seed'], 'failures': failures}); print('FAIL', e['label'], e['seed'], failures, flush=True)
    if args.run:
        report = json.loads((args.run / 'report.json').read_text(encoding='utf-8'))
        published = {}
        for t in report['native_tables'] + report.get('native_extra_tables', []):
            name = next(n for n, tb in a.tables['tables'].items() if tb['path'] == t['path']) if any(tb['path'] == t['path'] for tb in a.tables['tables'].values()) else \
                ('research_rewards' if t['path'] == 'ik_event/bin/research_lv/research_lv.bin' else 'personal' if t['path'] == a.v3['personal']['path'] else t['path'])
            published[name] = (args.run / 'romfs' / t['path']).read_bytes(); assert sha(published[name]) == t['sha256']
        failures, names = check_report(a, report, published)
        result['checked'] += 1; result['run'] = str(args.run)
        if failures: result['failed'].append({'run': str(args.run), 'failures': failures})
        if (args.run / 'save/save_0/main').exists() and sha((args.run / 'save/save_0/main').read_bytes()) != report['save_sha256']: result['note'] = 'save differs from the starting template (progress saved?)'
    if result['failed']: result['status'] = 'FAIL'
    if args.write: args.write.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'failed'} | {'failed': len(result['failed'])}))
    sys.exit(0 if result['status'] == 'PASS' else 1)

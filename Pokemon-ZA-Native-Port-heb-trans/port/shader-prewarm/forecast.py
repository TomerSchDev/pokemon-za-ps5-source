"""Read-only encounter forecast for shader-prewarm research; never writes game data.

Uses the final postprocessed wild table, verifies it against the console receipt,
then joins explicit spawner -> encounter and spawner -> zone/scene references.
It deliberately does not claim species IDs are shader IDs or evaluate save flags.
"""
from pathlib import Path
import argparse, collections, hashlib, json, sys

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PC = Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
WILD_PATH = 'world/ik_data/field/pokemon/encount_data/encount_data/encount_data_array.bin'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if not k.startswith('$')}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def rows(value):
    if 'root' in value:
        return value['root']
    return [r for group in value['values'] for r in group['root']]


def unique_index(items, key):
    result = {r[key]: r for r in items}
    if len(result) != len(items):
        raise ValueError('Duplicate ' + key)
    return result


def build_forecast(encounters, spawners, transforms, personal, zones):
    enc = unique_index(encounters, 'id')
    unique_index(spawners, 'id')
    positions = collections.defaultdict(list)
    for row in transforms:
        if row.get('Name'):
            positions[row['Name']].append(clean(row))
    people = {(r['species'], r['form']): r for r in personal}
    known_zones = unique_index(zones, 'zoneId')
    groups, unresolved, missing = {}, [], []
    referenced = set()

    def group_for(kind, key):
        token = kind + ':' + key
        if token not in groups:
            groups[token] = dict(kind=kind, id=key, spawners=[], encounters=[], species_forms=[])
            if kind == 'zone':
                groups[token]['zone_configuration'] = clean(known_zones.get(key))
        return groups[token]

    for sp in spawners:
        locations = collections.defaultdict(list)
        for obj in sp.get('appearanceSpawnerObjectInfoList', []):
            zone = (obj.get('zoneInfo') or {}).get('zoneId')
            scene = obj.get('createScenePath')
            kind, key = ('zone', zone) if zone else ('scene', scene)
            if not key or key in ('./', '.', '/'):
                kind, key = 'unlocated', 'explicit-location-missing'
            location = clean(obj)
            location['transforms'] = positions.get(obj.get('objectName'), [])
            locations[kind, key].append(location)
        if not locations:
            locations['unlocated', 'explicit-location-missing'] = []
        for (kind, key), objects in locations.items():
            group = group_for(kind, key)
            group['spawners'].append(dict(id=sp['id'], locations=objects,
                activation_condition=clean(sp.get('activationCondition', []))))
            if kind == 'unlocated':
                unresolved.append(sp['id'])
            for link in sp.get('encountDataInfoList', []):
                identity = link['encountDataId']
                if identity not in enc:
                    missing.append(dict(spawner=sp['id'], encounter=identity))
                    continue
                referenced.add(identity)
                e = enc[identity]
                p = people.get((e['devNo'], e['formNo']))
                if p is None:
                    raise ValueError(f'Missing personal record: {identity}, {e["devNo"]}:{e["formNo"]}')
                authored = sorted({v for v in (e.get('wazaList') or {}).values() if isinstance(v, int) and v > 0})
                # Conservative candidate set, not an assertion of the four active moves.
                # Include all learnable-at-or-below-level moves and explicit authored moves.
                upper = e['maxLevel'] + max(0, link.get('additionalLevel', 0)) + max(0, e.get('oyabunAdditionalLevel', 0))
                level_moves = sorted({m['move'] for m in p.get('learnset', []) if 0 <= m['level'] <= upper})
                group['encounters'].append(dict(id=identity, spawner=sp['id'],
                    species=e['devNo'], form=e['formNo'], national=p['national'], name=p['name'],
                    base_level=[e['minLevel'], e['maxLevel']],
                    additional_level=link.get('additionalLevel', 0),
                    alpha_additional_level=e.get('oyabunAdditionalLevel', 0),
                    authored_moves=authored, move_candidates=authored or level_moves,
                    move_candidates_are_exact=bool(authored),
                    encounter_conditions=clean(e.get('activationCondition', [])),
                    spawn_link=clean(link)))

    for group in groups.values():
        subset = {}
        for e in group['encounters']:
            key = e['species'], e['form']
            if key not in subset:
                subset[key] = {k: e[k] for k in ('species', 'form', 'national', 'name')}
                subset[key].update(encounter_ids=set(), move_candidates=set())
            subset[key]['encounter_ids'].add(e['id'])
            subset[key]['move_candidates'].update(e['move_candidates'])
        group['species_forms'] = [dict(p, encounter_ids=sorted(p['encounter_ids']),
            move_candidates=sorted(p['move_candidates'])) for _, p in sorted(subset.items())]
        group['spawners'].sort(key=lambda r: r['id'])
        group['encounters'].sort(key=lambda r: (r['id'], r['spawner']))
    result = dict(schema=1, kind='content-forecast-not-compiled-shaders',
        counts=dict(encounter_rows=len(enc), spawner_rows=len(spawners),
            referenced_encounter_rows=len(referenced), unreferenced_encounter_rows=len(enc.keys()-referenced),
            zone_groups=sum(g['kind']=='zone' for g in groups.values()),
            scene_groups=sum(g['kind']=='scene' for g in groups.values()),
            unlocated_spawners=len(set(unresolved)), missing_encounter_links=len(missing)),
        groups=[groups[k] for k in sorted(groups)],
        unreferenced_encounter_ids=sorted(enc.keys()-referenced), missing_encounter_links=missing,
        limits=[
            'Conditional superset: day/night, weather, quest and phase predicates are retained, not evaluated.',
            'Trainer battles, scripted actors, party members, environment, UI and global effects require additional inputs.',
            'Explicit zone/scene joins only. Missing scene context is not guessed from identifier prefixes.',
            'Move candidates from learnsets are a superset, not the exact runtime move assignment.',
            'No model/material-to-shader or portable pipeline recipe map exists in this output.',
            'No shaders are compiled, no native runtime is changed, and no console writes occur.'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pc', type=Path, default=DEFAULT_PC)
    parser.add_argument('--assets', type=Path, default=ROOT/'artifacts/randomizer-r15/PPSA91762/randomizer-assets')
    parser.add_argument('--run', type=Path, default=ROOT/'evidence/randomizer-run-20261028-041247Z')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.pc/'randomizer-lab'))
    sys.path.insert(0, str(ROOT/'port/randomizer'))
    from reflection_reader import Schema
    from run_oracle import replay_wild
    spec = read(args.assets/'progression.json')
    tables = read(args.assets/'tables.json')
    report = read(args.run/'report.json')
    assert tables['build_id'] == report['build_id'] == spec['build_id']
    final_wild = replay_wild(spec, (args.assets/'progression-wild.bin').read_bytes(),
        (args.run/'host-core/wild.bin').read_bytes(), report)
    expected = next(t['sha256'] for t in report['native_tables'] if t['path'] == WILD_PATH)
    if sha(final_wild) != expected:
        raise ValueError('Final wild table differs from verified console receipt')
    extracted = ROOT/'evidence/randomizer-field-move-audit/extracted'
    schema = Schema((extracted/WILD_PATH).with_suffix('.bfbs').read_bytes())
    decoded = ROOT/'evidence/randomizer-field-move-audit/decoded'
    inputs = [decoded/(n+'.json') for n in ('pokemon_spawner_data_array', 'pokemon_spawner_transform_array', 'wild_zone')]
    forecast = build_forecast(rows(schema.decode(final_wild, offsets=False)),
        rows(read(inputs[0])), rows(read(inputs[1])), tables['personal'], rows(read(inputs[2])))
    forecast.update(build_id=report['build_id'], run_id=report['native_run_id'], seed=report['seed'],
        wild_sha256=expected, source_receipts=[dict(file=str(p), sha256=sha(p.read_bytes())) for p in inputs],
        starter=report.get('starter'))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/'area-forecast.json').write_text(json.dumps(forecast, indent=2, ensure_ascii=False), encoding='utf-8')
    summary = {k: forecast[k] for k in ('build_id', 'run_id', 'seed', 'wild_sha256', 'counts', 'limits')}
    summary['areas'] = [dict(kind=g['kind'], id=g['id'], spawners=len(g['spawners']),
        encounter_rows=len({e['id'] for e in g['encounters']}), species_forms=len(g['species_forms'])) for g in forecast['groups']]
    summary['first_zone_example'] = next(g['species_forms'] for g in forecast['groups'] if g['id']=='a0102_w01')
    (args.out/'forecast-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(dict(counts=forecast['counts'], first_zone=summary['first_zone_example']), indent=2))


if __name__ == '__main__':
    main()

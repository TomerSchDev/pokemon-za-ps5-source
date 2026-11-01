"""Audit the isolated Smoliv mod against the native game and authentic Violet geometry."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'pilot/tools'))
import za_schemas as Z
from fbcodec import same


def main():
    mod = Path(sys.argv[1]) / 'species-pilot/romfs'
    out = Path(sys.argv[2])
    cat_schema = Z.catalog_schema()
    original = cat_schema.decode(Z.read(Z.CATALOG))
    current = cat_schema.decode((mod / Z.CATALOG).read_bytes())
    added = [r for r in current['table'] if r['species_info'].get('species', 0) == 935]
    assert len(added) == 1
    assert not any(r['species_info'].get('species', 0) == 935 for r in original['table'])
    retained = [r for r in current['table'] if r['species_info'].get('species', 0) != 935]
    assert same(retained, original['table']), 'Existing catalogue entries changed'
    personal_schema = Z.personal_schema()
    old_personal = personal_schema.decode(Z.read(Z.PERSONAL))['Table']
    new_personal = personal_schema.decode((mod / Z.PERSONAL).read_bytes())['Table']
    assert len(old_personal) == len(new_personal)
    changed = [i for i, (a, b) in enumerate(zip(old_personal, new_personal)) if not same(a, b)]
    assert len(changed) == 1
    personal = new_personal[changed[0]]
    assert personal['Info']['SpeciesInternal'] == 935
    assert personal['Info']['SpeciesNational'] == 928
    assert personal['IsPresentInGame'] is True
    param_audit = {}
    for stem, key in ((Z.MODEL_PARAM, 'devId'), (Z.MOVEMENT_PARAM, 'devNo')):
        s = Z.bfbs_schema(stem)
        old = s.decode(Z.read(stem + '.bin'))['values']
        new = s.decode((mod / (stem + '.bin')).read_bytes())['values']
        extra = [db for db in new if db['root'][0].get(key, 0) == 935]
        kept = [db for db in new if db['root'][0].get(key, 0) != 935]
        assert len(extra) == 1 and same(kept, old)
        param_audit[stem] = dict(added=935, native_rows_preserved=len(kept))
    encounter_schema = Z.bfbs_schema(Z.ENCOUNT)
    def encounter_rows(raw):
        return {r['id']: r for db in encounter_schema.decode(raw)['values'] for r in db.get('root', [])}
    old_encounters = encounter_rows(Z.read(Z.ENCOUNT + '.bin'))
    new_encounters = encounter_rows((mod / (Z.ENCOUNT + '.bin')).read_bytes())
    assert old_encounters.keys() == new_encounters.keys()
    encounters = []
    for key, row in new_encounters.items():
        before = old_encounters[key]
        if not same(before, row):
            restored = dict(row, devNo=before['devNo'])
            assert row['devNo'] == 935 and same(restored, before)
            encounters.append(dict(id=key, before=before['devNo'], after=935))
    assert len(encounters) == 1
    source = ROOT / 'work/smoliv-source/pokemon/data/pm1039/pm1039_00_00'
    target = mod / 'ik_pokemon/data/pm0935/pm0935_00_00'
    assets = []
    for ext in ('.trmbf', '.trmsh', '.trskl'):
        raw = (source / ('pm1039_00_00' + ext)).read_bytes()
        result = (target / ('pm0935_00_00' + ext)).read_bytes()
        assert raw.replace(b'pm1039', b'pm0935') == result, ext + ' differs from authentic source'
        assets.append(dict(kind=ext, source_sha256=hashlib.sha256(raw).hexdigest(),
                           target_sha256=hashlib.sha256(result).hexdigest(),
                           authentic_source_payload=True))
    payloads = []
    for file in sorted(source.iterdir()):
        if file.is_file() and file.suffix in ('.bntx', '.tranm', '.tracm', '.trmbf', '.trmsh', '.trskl'):
            converted = target / file.name.replace('pm1039', 'pm0935')
            assert file.read_bytes().replace(b'pm1039', b'pm0935') == converted.read_bytes(), file.name
            payloads.append(dict(source_file=file.name, suffix=file.suffix,
                                 target_sha256=hashlib.sha256(converted.read_bytes()).hexdigest()))
    result = dict(national_species=928, internal_species=935, catalog_added=added,
                  original_catalog_entries_unchanged=len(retained),
                  native_mareep_unchanged=True, personal_rows_changed=changed,
                  parameter_tables=param_audit, encounters_changed=encounters,
                  base_stats=personal['Base'], types=[personal.get('Type1', 0), personal.get('Type2', 0)],
                  source_geometry=assets, authentic_geometry_texture_motion_payloads=payloads,
                  runtime_verification_is_separate=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(national=928, internal=935, native_catalog_entries_preserved=len(retained),
                          authentic_geometry_payloads=len(assets), authentic_source_payloads=len(payloads),
                          personal_rows_changed=len(changed)), indent=2))


if __name__ == '__main__':
    main()

"""Edit copies in RAM and decode again. Never save or install changed game files."""
import copy
import hashlib
import json
from pathlib import Path
import struct

from reflection_reader import FMT, Schema

ROOT = Path(__file__).resolve().parent


def descend(tree, path):
    for key in path:
        tree = tree[key]
    return tree


def changes(a, b, path=()):
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return [path]
        return [p for k in a for p in changes(a[k], b[k], path + (k,))]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [path]
        return [p for i in range(len(a)) for p in changes(a[i], b[i], path + (i,))]
    return [] if a == b else [path]


def scalar_copy(raw, schema, table_type, row, field_name, new_value):
    obj = next(o for o in schema.objects if o['name'] == table_type)
    field = next(f for f in obj['fields'] if f['name'] == field_name)
    fmt = FMT.get(field['type']['base'])
    if fmt is None:
        raise ValueError('Only scalar fields are supported')
    offset = row['$fields'].get(field_name)
    if offset is None:
        raise ValueError('Default field absent: requires a proper table rebuild')
    old = struct.unpack_from('<' + fmt, raw, offset)[0]
    if old != row[field_name]:
        raise ValueError('Decoded value does not match source')
    result = bytearray(raw)
    struct.pack_into('<' + fmt, result, offset, new_value)
    return bytes(result), offset, struct.calcsize('<' + fmt)


def run():
    cases = [
        ('trainer', 'world/ik_data/trainer/trdata/trdata_array', 'Ev_m01_0070', 'trid', 'poke1', 'devId', 25),
        ('wild', 'world/ik_data/field/pokemon/encount_data/encount_data/encount_data_array', 'ect_a0201_w01_v01_z225', 'id', None, 'devNo', 25),
        ('event-npc', 'world/ik_data/field/pokemon/pokemon_data/pokemon_data/pokemon_data_array', 'npc_pokemon_001', 'id', None, 'devNo', 25),
    ]
    results = []
    for category, basename, identity, id_field, child, field, new_value in cases:
        path = ROOT / 'private-tables' / (basename + '.bin')
        raw = path.read_bytes()
        original_sha = hashlib.sha256(raw).hexdigest()
        schema = Schema(path.with_suffix('.bfbs').read_bytes())
        original = schema.decode(raw)
        paths = [('values', i) for i in range(len(original['values']))] if child else [
            ('values', i, 'root', j)
            for i, group in enumerate(original['values']) for j in range(len(group['root']))]
        selected = [p for p in paths if descend(original, p)[id_field] == identity]
        assert len(selected) == 1, (identity, len(selected))
        row_path = selected[0] + ((child,) if child else ())
        row = descend(original, row_path)
        table_type = next(o['name'] for o in schema.objects
                          if any(f['name'] == field for f in o['fields']))
        changed, offset, width = scalar_copy(raw, schema, table_type, row, field, new_value)
        reread = schema.decode(changed)
        expected = copy.deepcopy(original)
        descend(expected, row_path)[field] = new_value
        assert reread == expected, 'Unexpected collateral modification or shared table alias'
        deltas = changes(original, reread)
        assert deltas == [row_path + (field,)]
        changed_bytes = [i for i, (a, b) in enumerate(zip(raw, changed)) if a != b]
        assert changed_bytes and all(offset <= i < offset + width for i in changed_bytes)
        form = 'formId' if child else 'formNo'
        assert form not in row['$fields']
        try:
            scalar_copy(raw, schema, table_type, row, form, 1)
        except ValueError as error:
            assert 'Default field absent' in str(error)
        else:
            raise AssertionError('Absent field was not rejected')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == original_sha
        results.append(dict(category=category, path=basename + '.bin', id=identity,
                            source_sha256=original_sha, schema_root=schema.root,
                            field=field, offset=offset, width_bytes=width,
                            before=row[field], after=new_value, changed_bytes=changed_bytes,
                            only_requested_field_changed=True, absent_form_rejected=True,
                            on_disk_original_unchanged=True))
    return dict(status='PASS', scope='In-memory scalar edits and full-table decode comparison only',
                game_execution=False, installed_mod=False, cases=results)


if __name__ == '__main__':
    result = run()
    (ROOT / 'scalar-edit-validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

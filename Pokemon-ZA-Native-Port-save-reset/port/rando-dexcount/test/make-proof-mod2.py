"""Second proof mod (same method as make-proof-mod.py): the area's encounter rows mapped to Hyperspace-only species
with one species per ORIGINAL species slot, so that the common ground spawn of Wild Zone 1 (the Bunnelby slot,
z659 rows) becomes a species not caught yet in the proof fixtures. Inputs read-only; output folder must be new.
usage: make-proof-mod2.py PREPARED_DIR OUT_MOD_ROOT
"""
from pathlib import Path
import hashlib, json, re, sys

# original species -> Hyperspace-only replacement (all present, DexIndex > 232)
SLOT = {659: 316, 661: 56, 179: 174, 16: 174, 664: 56, 13: 316, 172: 56}  # only species not caught in the fixtures: Gulpin, Mankey, Igglybuff
FALLBACK = [316, 56, 174]
AREA = re.compile(r'^ect_(a0101|a0102)_w\d\d_|^ect_outzone_(a0101|a0102)_')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def put(data, field, value):
    off, n = field['offset'], field['bytes']
    assert n == 4 and field['signed'] and 0 <= off <= len(data) - 4
    data[off:off + 4] = int(value).to_bytes(4, 'little', signed=True)


def main():
    prepared, out = Path(sys.argv[1]), Path(sys.argv[2])
    tables = json.loads((prepared / 'tables.json').read_text())
    wild = tables['tables']['wild']
    raw = (prepared / wild['file']).read_bytes()
    assert sha(raw) == wild['sha256']
    personal = {(p['species'], p['form']): p for p in tables['personal']}
    data = bytearray(raw)
    rows = []
    for i, row in enumerate(r for r in wild['rows'] if AREA.match(r['identity'])):
        new = SLOT.get(row['species'], FALLBACK[i % len(FALLBACK)])
        p = personal[(new, 0)]
        assert p['present'] and p['dex'] > 232 and new in tables['pool']
        put(data, row['fields']['devNo'], new)
        put(data, row['fields']['formNo'], 0)
        put(data, row['fields']['sex'], 0)
        rows.append(dict(identity=row['identity'], original=[row['species'], row['form']], species=new, name=p['name'],
                         dex=p['dex']))
    target = out / 'dexcount-proof/romfs' / wild['path']
    target.parent.mkdir(parents=True, exist_ok=False)
    target.write_bytes(bytes(data))
    manifest = dict(path=wild['path'], template_sha256=wild['sha256'], output_sha256=sha(bytes(data)),
                    rows_changed=len(rows), mapping=SLOT, rows=rows)
    (out.parent / (out.name + '-manifest.json')).write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k: manifest[k] for k in ('path', 'output_sha256', 'rows_changed')}, indent=2))


if __name__ == '__main__':
    main()

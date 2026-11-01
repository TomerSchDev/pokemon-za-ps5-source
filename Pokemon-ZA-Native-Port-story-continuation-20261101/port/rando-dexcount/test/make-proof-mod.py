"""Build the PC proof's LayeredFS mod: the randomizer's own wild table (the prepared template the in-game generator
patches) with every encounter of the area where main mission 2 is taken (a0101 streets, a0102 = Wild Zone 1, the
two tutorial rows included) set to Hyperspace-only (Mega Dimension DLC) species, exactly the way the generator writes
a randomized row (devNo, formNo, sex). Nothing else changes. Inputs are only read; the output folder must be new.
Game data: the output stays on this PC (lab folder), never in git.

usage: make-proof-mod.py PREPARED_DIR OUT_MOD_ROOT
"""
from pathlib import Path
import hashlib, json, re, sys

DLC_SPECIES = [41, 52, 325, 316, 56, 174]  # Zubat, Meowth, Spoink, Gulpin, Mankey, Igglybuff: Hyperspace dex only
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
    assert sha(raw) == wild['sha256'], 'prepared wild template does not match tables.json'
    personal = {(p['species'], p['form']): p for p in tables['personal']}
    for s in DLC_SPECIES:
        p = personal[(s, 0)]
        assert p['present'] and p['dex'] > 232 and s in tables['pool'], s
    data = bytearray(raw)
    changed = []
    for row in wild['rows']:
        if not AREA.match(row['identity']):
            continue
        new = DLC_SPECIES[len(changed) % len(DLC_SPECIES)]
        put(data, row['fields']['devNo'], new)
        put(data, row['fields']['formNo'], 0)
        put(data, row['fields']['sex'], 0)
        changed.append(dict(identity=row['identity'], original=[row['species'], row['form']], species=new,
                            name=personal[(new, 0)]['name'], dex=personal[(new, 0)]['dex']))
    target = out / 'dexcount-proof/romfs' / wild['path']
    target.parent.mkdir(parents=True, exist_ok=False)
    target.write_bytes(bytes(data))
    manifest = dict(path=wild['path'], template_sha256=wild['sha256'], output_sha256=sha(bytes(data)),
                    rows_changed=len(changed), dlc_species=DLC_SPECIES, rows=changed)
    (out / 'dexcount-proof-manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k: manifest[k] for k in ('path', 'output_sha256', 'rows_changed', 'dlc_species')}, indent=2))


if __name__ == '__main__':
    main()

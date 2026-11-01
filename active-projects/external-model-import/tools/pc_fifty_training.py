"""Inspect the existing native encounter schema for a possible PC-only QA target.

Default is read-only. --native-capture-root writes one diagnostic encounter override
in a new isolated folder; it never changes the source game or establishes a pass.
"""
import argparse,copy,hashlib,json
import os
from pathlib import Path
from storage_paths import data_root

os.environ['ZA_ROMFS_PATH'] = str(Path(__file__).resolve().parents[3] / 'hebrew-lab/qa-game-reference-20261030/romfs.bin')
from catalog_inventory import Z
from build_smoliv_model import encode_checked
from integrate_model_assets import atomic

def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--native-capture-root',type=Path)
    a=parser.parse_args()
    schema = Z.bfbs_schema(Z.ENCOUNT)
    tree = schema.decode(Z.read(Z.ENCOUNT + '.bin'))
    wanted = 'ect_a0102_w01_v01_z659'
    rows = [row for row in nodes(tree) if row.get('id') == wanted]
    assert len(rows) == 1
    if a.native_capture_root:
        work=Path(__file__).resolve().parents[3]/'pc-fifty-20261031-r1'
        out=a.native_capture_root.resolve();assert out.is_relative_to(work.resolve()) and not out.exists()
        before=copy.deepcopy(tree);original=copy.deepcopy(rows[0])
        rows[0].update(devNo=661,minLevel=9,maxLevel=9,formNo=0,sex=-1,
                       oyabunProbability=0.0,oyabunAdditionalLevel=0,
                       wazaList=dict(waza1=33,waza2=98,waza3=0,waza4=0))
        data=encode_checked(schema,tree)
        changed=copy.deepcopy(rows[0]);rows[0].clear();rows[0].update(original)
        assert tree==before,'Unexpected second encounter change'
        target=out/'03-native-capture-scene/romfs'/(Z.ENCOUNT+'.bin')
        atomic(target,data)
        report=dict(PC_only=True,diagnostic_only=True,QA_pass_allowed=False,
                    purpose='Fresh native capture control; actual Pokemon creation occurs in the game',
                    changed_encounters=1,identity=wanted,original=original,replacement=changed,
                    output_sha256=hashlib.sha256(data).hexdigest())
        atomic(out/'native-capture-scene.json',json.dumps(report,indent=1).encode())
        print(json.dumps(dict(mods=str(out),native_species=661,level=9,moves=[33,98],changed_encounters=1)),flush=True)
        return
    fields = schema.tables['ik.fb.wild_pokemon.EncountData']
    print(json.dumps({'read_only': True, 'row': rows[0],
                     'move_field': [field for field in fields if field[1] == 'wazaList'],
                     'move_tables': {name: value for name, value in schema.tables.items() if 'Waza' in name}}, ensure_ascii=False))

if __name__ == '__main__':
    main()

"""Add Smoliv as its own species in an isolated mod, with the real source model bridge."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT.parent
sys.path.insert(0,str(LAB/'pilot/tools'))
import build_mods as pilot

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('out',type=Path)
parser.add_argument('--slot',default=pilot.SLOT)
args=parser.parse_args()
out=args.out
builder=pilot.Out(out)
pilot.copy_folder(builder)
pilot.build_catalog(builder,'step2')
pilot.build_personal(builder)
pilot.insert_row(builder,pilot.Z.MODEL_PARAM,'devId','formId','sex','poke_model_param')
pilot.insert_row(builder,pilot.Z.MOVEMENT_PARAM,'devNo','formNo','sex','poke_movement_param')
pilot.build_per_species_files(builder)
pilot.build_encounter(builder,args.slot)
builder.finish(dict(mode='real-model-step2',render_bridge='smoliv-real-r6',donor=pilot.DONOR,new=pilot.NEW))
source=ROOT/'build/smoliv-real-r6/mods/smoliv-real-model/romfs/ik_pokemon/data/pm0935'
target=out/'species-pilot/romfs/ik_pokemon/data/pm0935'
shutil.copytree(source,target,dirs_exist_ok=True)
icon_source=next((ROOT/'work/smoliv-source/pokemon/data/pm1039/pm1039_00_00/icon').glob('*.bntx'))
for rare in (0,1):
    # ZA has two icon slots. Both use the authentic source icon until the shiny icon is resolved.
    icon=target/f'pm0935_00_00/icon/pm0935_00_00_00_{rare}.bntx'
    icon.write_bytes(icon_source.read_bytes().replace(b'pm1039',b'pm0935'))
files={str(p.relative_to(out)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
(out/'real-model-manifest.json').write_text(json.dumps(dict(species_national=928,species_internal=935,files=files,
    gameplay_runtime_tested=False,visual_bridge_proven=True,notes=['Real Smoliv assets, ZA controller/hurtbox adaptation','Shiny UI icon currently shares the authentic normal icon','14 animation actions use recorded source-motion fallbacks']),indent=2),encoding='utf-8')
print('Smoliv species mod built:',out,flush=True)

"""Stage the donor's missing per-species behavior data in a separate PC-only overlay."""
from pathlib import Path
import hashlib,json
from build_smoliv_model import Z
from integrate_model_assets import atomic
import za_folder

def main():
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1'
    za_folder.GAME=str(lab/'hebrew-lab/qa-game-reference-20261030/romfs.bin');game=za_folder.game()
    result=[]
    for label,base,enabled in (('behavior',Z.BEHAVIOR,True),('collision','world/ik_data/pokemon/collision/pokemon_collision_unique_data/',False)):
        folder=work/'mods'/(( '' if enabled else '_')+'02-yamper-'+label+'-r1')
        for species,donor in ((835,172),(836,135)):
            assert not game.has(base+f'{species:04d}_00_00.bin')
            for ext in ('.bin','.bfbs'):
                source=base+f'{donor:04d}_00_00'+ext;raw=game.read(source)
                target=folder/'romfs'/(base+f'{species:04d}_00_00'+ext);atomic(target,raw)
                result.append(dict(kind=label,species=species,donor=donor,path=str(target),source=source,sha256=hashlib.sha256(raw).hexdigest(),enabled=enabled))
    atomic(work/'yamper-behavior-probe-r1.json',json.dumps(dict(PC_only=True,diagnostic_only=True,files=result),indent=1).encode())
    print(json.dumps(dict(files=len(result),behavior_enabled=True,collision_enabled=False)),flush=True)

if __name__=='__main__':main()

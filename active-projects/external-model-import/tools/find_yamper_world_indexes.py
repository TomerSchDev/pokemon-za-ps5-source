"""Read-only hash probing for the world behavior/collision registration lists."""
from pathlib import Path
from collections import Counter
import json
from build_smoliv_model import Z
from fbcodec import Schema
import za_folder

def main():
    lab=Path(__file__).resolve().parents[3];za_folder.GAME=str(lab/'hebrew-lab/qa-game-reference-20261030/romfs.bin');g=za_folder.game()
    for pn,rows in g.packs:
        if 'pokemon_species_behavior_data0744' not in pn:continue
        print(json.dumps(dict(pack=pn,sizes=Counter(r['size'] for r in rows).most_common(20))),flush=True)
        for r in rows:
            if r['size']<1000 or r['size']>100000:continue
            d=g.unpack(r)
            print(json.dumps(dict(hash=f"{r['hash']:016x}",size=len(d),schema=Schema.from_bfbs(d).root if d[4:8]==b'BFBS' else None,strings=sorted(za_folder.strings(d))[:8])),flush=True)
    words=('unique_path','unique_path_data','unique_path_array','unique_path_data_array','unique_data','path','path_list','path_data','path_array','data_path','data_paths','list','table','catalog','index','file_list','file_paths','paths')
    prefixes=('','pokemon_','pokemon_species_behavior_','pokemon_species_behavior_data_','pokemon_collision_','pokemon_collision_unique_','pokemon_collision_unique_data_')
    dirs=('world/ik_data/pokemon/','world/ik_data/pokemon/ai/','world/ik_data/pokemon/collision/','world/ik_data/pokemon/ai/pokemon_species_behavior_data/','world/ik_data/pokemon/collision/pokemon_collision_unique_data/')
    found=[]
    for base in dirs:
        for prefix in prefixes:
            for word in words:
                for nested in ('',prefix+word+'/'):
                    for ext in ('.bin','.bfbs'):
                        p=base+nested+prefix+word+ext
                        if g.has(p):
                            item=dict(path=p,hash=f"{za_folder.za_romfs.fnv1a64(p):016x}")
                            if p.endswith('.bin'):
                                item['strings']=sorted(za_folder.strings(g.read(p)))[:8]
                            found.append(item)
    print(json.dumps(dict(candidate_matches=found),indent=1),flush=True)

if __name__=='__main__':main()

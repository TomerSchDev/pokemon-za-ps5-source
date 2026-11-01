"""Read-only inspection of the small shared Pokemon AI parameter pack."""
from pathlib import Path
import json,re
from build_smoliv_model import Z
from fbcodec import Schema
import za_folder

def main():
    lab=Path(__file__).resolve().parents[3];za_folder.GAME=str(lab/'hebrew-lab/qa-game-reference-20261030/romfs.bin');g=za_folder.game()
    host_packs={g.files[za_folder.za_romfs.fnv1a64(p+e)]['pack'] for p in (Z.MODEL_PARAM,Z.MOVEMENT_PARAM) for e in ('.bin','.bfbs')}
    for pn,pr in g.packs:
        if pn not in host_packs:continue
        print(json.dumps(dict(parameter_pack=pn,files=len(pr),bytes=sum(r['size'] for r in pr))),flush=True)
        for rec in pr:
            if rec['size']>1000000:continue
            d=g.unpack(rec)
            if d[4:8]==b'BFBS':
                s=Schema.from_bfbs(d)
                print(json.dumps(dict(root=s.root,hash=f"{rec['hash']:016x}",tables={k:v for k,v in s.tables.items() if not k.startswith('gfl.')})),flush=True)
    name,rows=next((n,r) for n,r in g.packs if 'pokemon_species_cant_action_array.bin' in n)
    result=[]
    for rec in rows:
        data=g.unpack(rec);strings=sorted(za_folder.strings(data))
        info=dict(hash=f"{rec['hash']:016x}",size=len(data),strings=[s for s in strings if len(s)>8][:120])
        if data[4:8]==b'BFBS':
            s=Schema.from_bfbs(data);info.update(root=s.root)
            if s.root in ('PokemonAiNatureTableArray','PokemonSpeciesCantActionArray','pokemon_ai.wild.WildPokemonActionDataArray'):
                info['tables']={k:v for k,v in s.tables.items() if not k.startswith(('gfl.','GF.'))}
            if 'UniquePath' in s.root:
                info['schema_fields']=len(s.tables[s.root])
                candidate=next(r for r in rows if r['hash']==int('3a807f5a445d2927',16))
                info['decoded']=s.decode(g.unpack(candidate))
        result.append(info)
    out=lab/'pc-fifty-20261031-r1/yamper-ai-pack-inspection-r1.json';out.write_text(json.dumps(result,indent=1),encoding='utf-8')
    stems=('pokemon_unique_path_data','pokemon_unique_path','pokemon_species_behavior_data','pokemon_species_behavior_path_data','pokemon_species_behavior_path','pokemon_species_behavior_data_path','pokemon_species_behavior_data_path_array','pokemon_collision_unique_data','pokemon_collision_unique_path_data','pokemon_collision_unique_path','pokemon_collision_unique_data_path','pokemon_collision_unique_data_path_array')
    stems=tuple(set(stems)|{v+'_array' for v in stems}|{'pokemon_species_behavior_data_list','pokemon_collision_unique_data_list'})
    for base in ('world/ik_data/pokemon/','world/ik_data/pokemon/ai/','world/ik_data/pokemon/collision/'):
        for stem in stems:
            for middle in ('',stem+'/','pokemon_species_behavior_data/','pokemon_collision_unique_data/'):
                for ext in ('.bin','.bfbs'):
                    p=base+middle+stem+ext
                    if g.has(p):print(json.dumps(dict(path=p,hash=f"{za_folder.za_romfs.fnv1a64(p):016x}")),flush=True)
    print(json.dumps(dict(report=str(out),schemas=[r.get('root') for r in result if 'root' in r])),flush=True)

if __name__=='__main__':main()

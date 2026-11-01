"""Inspect the effective per-species behaviour/animation tables and model modules."""
from pathlib import Path
import json
from build_smoliv_model import Z,schema
from fbcodec import Schema
import za_folder

def main():
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1';root=work/'mods/all-models/romfs'
    result={}
    za_folder.GAME=str(lab/'hebrew-lab/qa-game-reference-20261030/romfs.bin');game=za_folder.game()
    result['related_packs']=[(name,len(rows)) for name,rows in game.packs if name.startswith('arc/worldik_datapokemon') or (name.startswith('arc/param_chr') and 'pokemon' in name and 'wild_single' not in name)]
    print(json.dumps({'related_packs':result['related_packs']},indent=1),flush=True)
    extras={}
    for base in (Z.BEHAVIOR,'world/ik_data/pokemon/collision/pokemon_collision_unique_data/'):
        values={}
        for n in (172,835,706):
            stem=base+f'{n:04d}_00_00'
            if not game.has(stem+'.bin'):values[str(n)]={'exists':False};continue
            s=Schema.from_bfbs(game.read(stem+'.bfbs'));values[str(n)]={'exists':True,'value':s.decode(game.read(stem+'.bin'))}
        extras[base]=values
    result['optional_tables']=extras
    for base in (Z.WILD_SINGLE,Z.CHARA_ANIME):
        path=root/(base+'0835_00_00')
        s=Schema.from_bfbs(Path(str(path)+'.bfbs').read_bytes())
        result[base]=s.decode(Path(str(path)+'.bin').read_bytes())
    folder=root/'ik_pokemon/data/pm2835/pm2835_00_00'
    for ext in ('tracn','tracr'):
        value=schema(ext,'SV/Flatbuffers/animation' if ext=='tracn' else 'ZA/Flatbuffers').decode((folder/f'pm2835_00_00_base.{ext}').read_bytes())
        if ext=='tracr':value={'attack_tracks':[v for v in value['track_list']['list'] if 'attack' in v['track_name']]}
        result[ext]=value
    (work/'yamper-battle-assets-inspection-r1.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({'report':str(work/'yamper-battle-assets-inspection-r1.json')}),flush=True)

if __name__=='__main__':main()

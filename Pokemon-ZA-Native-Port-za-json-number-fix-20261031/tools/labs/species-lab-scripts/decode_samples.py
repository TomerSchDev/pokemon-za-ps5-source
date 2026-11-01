"""Decode a few extracted per-species tables with their shipped .bfbs schemas (read-only, prints a short summary)."""
import json, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/randomizer-lab')
from reflection_reader import Schema
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/samples/'
def show(schema, data, n=900):
    s = Schema(open(S + schema, 'rb').read())
    print('==', schema, 'root', s.root)
    print('   objects:', [(o['name'].split('.')[-1], [f['name'] for f in o['fields']]) for o in s.objects][:10])
    if data:
        d = s.decode(open(S + data, 'rb').read(), offsets=False)
        print('   data:', json.dumps(d)[:n])
    return s
show('world/ik_data/pokemon/ai/pokemon_species_behavior_data/0058_00_00.bfbs', 'world/ik_data/pokemon/ai/pokemon_species_behavior_data/0058_00_00.bin')
show('world/ik_data/pokemon/ai/pokemon_species_behavior_data/0058_00_00.bfbs', 'world/ik_data/pokemon/ai/pokemon_species_behavior_data/0025_00_00.bin')
show('world/ik_data/pokemon/collision/pokemon_collision_unique_data/0004_00_00.bfbs', 'world/ik_data/pokemon/collision/pokemon_collision_unique_data/0004_00_00.bin', 600)
show('param_ai/data/ai/action/poke_ride/poke_ride_array.bfbs', 'param_ai/data/ai/action/poke_ride/poke_ride_array.bin')
s = show('world/ik_data/pokemon/ai/pokemon_species_cant_action/pokemon_species_cant_action_array.bfbs', 'world/ik_data/pokemon/ai/pokemon_species_cant_action/pokemon_species_cant_action_array.bin', 700)

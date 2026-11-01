"""Inventory potential extensions without modifying any game data."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'evidence/randomizer-field-move-audit/decoded'
def walk(x):
    if isinstance(x,dict):
        yield x
        for k,v in x.items():
            if not k.startswith('$'):yield from walk(v)
    elif isinstance(x,list):
        for v in x:yield from walk(v)
def read(name):return json.loads((BASE/(name+'.json')).read_bytes())
pokemon=[x for x in walk(read('pokemon_data_array')) if 'id' in x and 'devNo' in x]
ids={x['id'] for x in pokemon}
refs=[x['encountId'] for x in walk(read('placement_npc_spawner_data_array')) if x.get('encountId') in ids]
boss=[x for x in walk(read('encount_data_array')) if 'id' in x and 'devNo' in x and 'boss' in x['id'].lower()]
conditions=[x for x in walk(read('pokemon_spawner_data_array')) if x.get('condition') in ('phase_condition','flag_condition')]
record={'source':'ZA 2.0.2 merged local game tables; read-only audit',
 'npc_pokemon_records':len(pokemon),'unique_npc_pokemon_ids':len(ids),
 'placement_references_to_npc_pokemon':len(refs),'distinct_referenced_npc_ids':len(set(refs)),
 'story_boss_named_encounter_records':len(boss),'spawner_phase_or_flag_conditions':len(conditions),
 'examples':{'npc':pokemon[0]['id'],'placement_reference':refs[0] if refs else None,'boss':[x['id'] for x in boss[:5]]},
 'currently_enabled':['Wild encounters','Trainer teams','Mega trainer teams','21 complete DLC Mega rematch battle-reference permutations','Selected research rewards'],
 'not_enabled':['Main-story boss order','Cutscene actors','Scripted gifts','General event/quest reward randomization'],
 'findings':[
 'NPC species and forms have separate encounter records referenced by placement encountId: a concrete next extension point.',
 'This does not establish that all cinematic actors use these records. No universal cutscene substitution is implemented.',
 'Story spawners contain mission phase/flag conditions; changing encounter species is not a permutation of story missions.',
 'The earlier PC experimental boss option substitutes species, not order; its own implementation warns of arena AI/progression issues.',
 'DLC rematch permutation already moves battleId, species, form and level data together. Main story needs separate event/arena/actor validation.'],
 'proposed_next_steps':['Optional decorative NPC mapping for selected actors with visual checks',
 'Map one story boss encounter plus its phase/flag, arena and cutscene references before expanding',
 'Audit event reward source identities and protect progression before adding non-research item rewards'],
 'limits':'Inventory and implementation review only; no new boss/cutscene feature has passed a console test.'}
(ROOT/'evidence/randomizer-r14-expansion-audit.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2))

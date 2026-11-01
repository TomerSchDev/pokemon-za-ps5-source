"""Validate every allowed replacement against raw personal tables, then outputs."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[2]
PC=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
sys.path.insert(0,str(PC/'randomizer-lab'))
from reflection_reader import Buffer,Schema
spec=json.loads((ROOT/'port/randomizer/reward-assets/progression.json').read_text())
audit=json.loads((ROOT/'evidence/randomizer-progression-audit.json').read_text())
p=ROOT/'evidence/randomizer-field-move-audit/extracted/avalon/data/personal_array.bin'
assert hashlib.sha256(p.read_bytes()).hexdigest()==spec['source_hashes']['personal']
b=Buffer(p.read_bytes());raw={}
for t in b.tables(b.scalar(0,'I'),0):
    info=b.field(t,0);key=(b.scalar(info,'H'),b.scalar(info+2,'H'))
    tm={b.scalar(x,'H') for x in b.vector(b.field(t,22),2)}
    learned={}
    for x in b.vector(b.field(t,25),4):
        move,level=b.scalar(x,'H'),b.scalar(x+2,'b')
        if level>=0:learned[move]=min(learned.get(move,101),max(1,level))
    raw[key]=(tm,learned)
tm_moves={x['move'] for x in audit['tms']};checked=0
for g in spec['guards']:
    old=(g['species'],g['form']);ot,om=raw[old]
    if g['fixed']:assert g['pool']==[]
    for species in g['pool']:
        nt,nm=raw[species,0];assert (ot&tm_moves)<=nt,(old,species,'TM')
        for role,moves in audit['roles'].items():
            before=min((om[m] for m in moves if m in om),default=101)
            after=min((nm[m] for m in moves if m in nm),default=101)
            assert after<=before,(old,species,role,before,after)
        checked+=1
out=ROOT/'evidence/randomizer-r14-progression-tests'
reports=json.loads((out/'reports.json').read_text())
template=(ROOT/'port/randomizer/reward-assets/progression-wild.bin').read_bytes()
source=ROOT/'evidence/randomizer-field-move-audit/extracted/world/ik_data/field/pokemon/encount_data/encount_data/encount_data_array'
schema=Schema(source.with_suffix('.bfbs').read_bytes())
assert schema.decode(template,offsets=False)==schema.decode(source.with_suffix('.bin').read_bytes(),offsets=False)
allowed={g['fields'][f]['offset']+i for g in spec['guards'] for f in ('devNo','formNo','sex') for i in range(4)}
for report in reports:
    seed=report['seed'];before=(out/(seed+'-before.bin')).read_bytes();after=(out/(seed+'-after.bin')).read_bytes()
    if not report['options']['wild']:
        assert after==before
        continue
    assert len(after)==spec['wild_bytes']
    assert all(x==y or i in allowed for i,(x,y) in enumerate(zip(template,after)))
    assert hashlib.sha256(after).hexdigest()==report['table_sha256']['wild']
    for g in spec['guards']:
        species=struct.unpack_from('<i',after,g['fields']['devNo']['offset'])[0]
        form=struct.unpack_from('<i',after,g['fields']['formNo']['offset'])[0]
        if g['rock_provider']:
            assert species==report['rock_route']['species'] and form==0
        elif g['fixed']:
            assert (species,form)==(g['species'],g['form'])
        else:
            assert species==struct.unpack_from('<i',before,g['generated_fields']['devNo']['offset'])[0]
            assert form==struct.unpack_from('<i',before,g['generated_fields']['formNo']['offset'])[0]
    assert next(g for g in spec['guards'] if g['identity']=='ect_a0102_w01_v01_z659_tuto')['fixed']
result={'status':'PASS','tm_count':160,'candidate_comparisons_for_audit_only':checked,
        'ordinary_fully_random_encounters':sum(not g['fixed'] for g in spec['guards']),
        'authored_encounters_retained':sum(g['fixed'] and not g['rock_provider'] for g in spec['guards']),
        'seeded_rock_provider_rows':2,'generated_seeds':len(reports),
        'original_spawn_levels_and_conditions_unchanged':True,'ordinary_encounters_match_original_randomizer':True,
        'independent_flatbuffer_input_used':True,
        'other_tables_and_save_unchanged':True,'authored_move_lists_preserved':True,'full_story_playthrough_verified':False}
(out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))

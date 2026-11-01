"""Offline regression using the real r11 report and its progressed save snapshot."""
from pathlib import Path
import hashlib,importlib.util,json,struct
from run_oracle import rock,route_for_run
ROOT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('repair',Path(__file__).with_name('repair-existing-run.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
source=ROOT/'evidence/randomizer-run-20261027-222327Z'
raw=(source/'report.json').read_bytes();report=json.loads(raw)
oldassets=ROOT/'artifacts/randomizer-r11/PPSA91762/randomizer-assets'
guard=json.loads((oldassets/'progression.json').read_bytes())
oldwild=bytearray((source/'host-core/wild.bin').read_bytes())
for row in guard['guards']:
    choices=[] if row['fixed'] else [x for x in row['pool'] if x!=row['species']]
    species=row['species'];form=row['form']
    if choices:
        for attempt in range(1000):
            msg=json.dumps(['za202-field-capabilities-v1',report['seed'],row['identity'],attempt],separators=(',',':')).encode()
            word=int.from_bytes(hashlib.sha256(msg).digest()[:8],'big')
            if word<(1<<64)-((1<<64)%len(choices)):break
        species=choices[word%len(choices)];form=0
    for f,v in [('devNo',species),('formNo',form),('sex',row['original_sex'] if species==row['species'] else 0)]:
        struct.pack_into('<i',oldwild,row['fields'][f]['offset'],v)
assert m.sha(oldwild)==report['table_sha256']['wild']
files={'report.json':raw,'save/save_0/main':(source/'main').read_bytes(),
       'romfs/'+m.WILD:bytes(oldwild),'romfs/'+m.REWARDS:(source/'research-rewards.bin').read_bytes()}
for table in report['native_tables']:
    path=table['path']
    if path not in (m.WILD,m.REWARDS):
        filename='dlc_boss.bin' if 'dimension_boss' in path else 'trainers.bin'
        files['romfs/'+path]=(source/'host-core'/filename).read_bytes()
assets=ROOT/'port/randomizer/reward-assets'
spec=json.loads((assets/'progression.json').read_bytes())
rewards=json.loads((oldassets/'research-rewards.json').read_bytes())
new,r=m.repair(files,spec,(assets/'progression-wild.bin').read_bytes(),(source/'host-core/wild.bin').read_bytes(),rewards,'r0000000000000000-00000000')
assert files['report.json']==raw and json.loads(raw)==report
assert new['save/save_0/main']==files['save/save_0/main']
assert r['save_sha256']!=m.sha(new['save/save_0/main']),'Fixture must include actual gameplay progress'
for key in files:
    if key not in ('report.json','romfs/'+m.WILD):assert new[key]==files[key],key
assert new['romfs/'+m.WILD]!=files['romfs/'+m.WILD]
for g in spec['guards']:
    if not g['fixed']:
        for field in ('devNo','formNo','sex'):
            assert struct.unpack_from('<i',new['romfs/'+m.WILD],g['fields'][field]['offset'])==struct.unpack_from('<i',(source/'host-core/wild.bin').read_bytes(),g['generated_fields'][field]['offset'])
# If the old reward differs from a freshly planned TM, the old reward must win.
tm_cases=0;natural_cases=0
for seed in map(str,range(100)):
    test=dict(r,seed=seed);candidate=route_for_run(spec,test)
    if candidate['mode']=='tm':
        assert candidate['tm_item']==358
        pool=next(x['candidates'] for x in spec['rock']['tm_routes'] if x['item']==358)
        assert candidate['species'] in {x['species'] for x in pool};tm_cases+=1
    else:assert candidate==rock.plan(spec,seed,True,True);natural_cases+=1
assert tm_cases and natural_cases
out={'status':'PASS','source_run':report['native_run_id'],'source_seed':report['seed'],
     'progressed_save_sha256':m.sha(files['save/save_0/main']),'save_and_all_other_tables_byte_identical':True,
     'ordinary_encounters_match_unconstrained_core':True,'original_report_unchanged':True,
     'rock_route':r['rock_route'],'old_reward_retained_in_TM_cases':tm_cases,'natural_cases':natural_cases,
     'remote_repair_tested':False}
(ROOT/'evidence/randomizer-r14-repair-offline-verification.json').write_bytes(m.encode(out));print(json.dumps(out,indent=2))

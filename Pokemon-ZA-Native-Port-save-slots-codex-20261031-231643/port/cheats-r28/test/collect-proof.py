from pathlib import Path
import json,re,hashlib,shutil
own=Path(__file__).resolve().parents[1];evidence=own/'evidence';evidence.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
build=read(own/'work/pc-build-05/build-result.json')
assert build['item_helper_object_reproduced']
for n,h in build['source_hashes'].items():assert sha(own/n)==h,n
runs=['pc-batch-02','pc-reload-cap-01']
results=[]
for run in runs:
 folder=own/'work'/run;r=read(folder/'run.json');v=read(folder/'pkhex-verify.json')
 assert r['source_unchanged'] and r['dll_sha256']==build['library_sha256'] and v['count']==199
 batch=(folder/'r28items-batch.log').read_text().splitlines();assert len(batch)==199
 assert all('accepted=1' in line and 'pending=0' in line for line in batch)
 if run==runs[0]:assert all('status=ADDED ' in line for line in batch)
 else:assert all('status=ITEM / POCKET FULL ' in line for line in batch)
 for name in ['run.json','pkhex-verify.json','r28items-batch.log','stderr.log']:
  shutil.copy2(folder/name,evidence/(run+'-'+name))
 results.append(dict(name=run,save_sha256=r['copy_after_sha256'],source_unchanged=True,items=199,
   status='ADDED' if run==runs[0] else 'ITEM / POCKET FULL',applied=199 if run==runs[0] else 0))
catalog=re.findall(r'\[r28-catalog\] id=(\d+) pocket=(\d+) cap=(\d+) valid=(\d+)',(own/'work/pc-batch-02/stderr.log').read_text())
assert {int(x[0]) for x in catalog if x[3]=='1'}=={x['id'] for x in read(own/'research/menu-catalog.json')}
assert not [x for x in catalog if x[3]!='1']
proof=dict(items_verified=True,save_verified=True,reload_verified=True,cap_verified=True,
 console_access_performed=False,real_saves_written=False,source_hashes=build['source_hashes'],
 pc_library_sha256=build['library_sha256'],pc_helper_object_reproduced=True,runs=results,
 alpha=dict(enabled=False,reason='Schema identifies oyabunProbability but no type-verified spawn reader / live-table re-read or caught PA9 IsAlpha proof was established; disabled as requested',candidate_functions=238,flatbuffer_windows=84,spawn_statistics_tested=False,caught_isalpha_tested=False),
 validation='Original game add function; all 199 ids/pockets/caps validated in the loaded game table. 39 consumables at999 and160 TMs at1 persisted and reloaded. A second set of199 requests at cap was refused, KItem block unchanged. PKHeX hash and party checksums pass; unrequested inventory quantities and money unchanged.',
 pc_diagnostics='Bulk catalog QA replays independent public requests on the synchronous guest callback; not part of the PS5 build. Actual scripted menu open/save/load used. Earlier single Rare Candy99 test used the same byte-identical helper.',
 hardware_acceptance_pending=True)
(evidence/'pc-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
shutil.copy2(own/'work/patcher-negative-tests/result.json',evidence/'patcher-negative-tests.json')
shutil.copy2(own/'research/menu-catalog.json',evidence/'menu-catalog.json')
print(json.dumps({k:proof[k] for k in ['items_verified','save_verified','reload_verified','cap_verified','pc_library_sha256']},indent=2))

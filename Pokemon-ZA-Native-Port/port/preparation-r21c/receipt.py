"""Preservation/import/test/packaging gate for observer-only r21c."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
EVID=ROOT/'evidence/preparation-r21c'
BASE=Path('/home/tomer/ps5-za-native/preparation-r21b-20261028')
WORK=Path('/home/tomer/ps5-za-native/preparation-r21c-20261028')
ART=ROOT/'artifacts/randomizer-r21c-preparation/PPSA91762'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()
manifest=json.loads((EVID/'preparation.json').read_text())
for rel,h in manifest['runtime_sources'].items():
    assert sha(BASE/'source/runtime'/rel)==sha(WORK/'source/runtime'/rel)==h,rel
for rel,h in manifest['runtime_objects'].items():
    assert sha(BASE/'source/build/ps5/rt'/rel)==sha(WORK/'source/build/ps5/rt'/rel)==h,rel
for name,h in manifest['extra_objects'].items():
    assert sha(BASE/'objects-r21b'/name)==h,name
    if name not in ('observer.o','title_entry.o'):assert sha(WORK/'objects-r21c'/name)==h,name
before=json.loads((ROOT/'evidence/preparation-r21/preservation-audit.json').read_text())
for key in ('game_archive','driver'):assert sha(Path(before[key]['path']))==before[key]['sha256'],key
nm='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk/bin/llvm-nm'
imports=[]
for tree in (BASE,WORK):
    text=subprocess.check_output([nm,'--dynamic','--undefined-only',str(tree/'source/build/ps5/title/llvm-pie.elf')],text=True)
    imports.append(sorted(line.split()[-1] for line in text.splitlines() if line.split()))
assert imports[0]==imports[1], 'Dynamic imports changed'
test=max(EVID.glob('host-tests-*/result.json'),key=lambda p:p.stat().st_mtime)
tr=json.loads(test.read_text());assert tr['observer_tests']=='passed ASan+UBSan' and tr['client_tests']=='passed'
receipts=[json.loads(p.read_text()) for p in (test.parent/'store').glob('session_*/ack_*.json')]
retire=[x for x in receipts if x.get('op')=='retire_capture']
assert {'retired','already_absent','rejected_target','invalid_session_directory','missing_snapshot_ack','invalid_snapshot_ack','invalid_capture_file'} <= {x['result'] for x in retire}
assert all(x['removed']==(x['result']=='retired') and x['file']=='' for x in retire)
audit={'unchanged_runtime_sources':len(manifest['runtime_sources']),'unchanged_runtime_objects':len(manifest['runtime_objects']),
       'changed_extra_objects':['observer.o','title_entry.o'],'same_dynamic_imports':True,'dynamic_import_count':len(imports[0]),
       'game_archive':before['game_archive'],'driver':before['driver'],'retirement_receipts':len(retire),
       'retirement_tests':tr,'host_tests_path':str(test),'no_console_access':True,'no_save_operations':True}
(EVID/'preservation-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
result={'title_revision':'randomizer-r21c-preparation','title_id':'PPSA91762','snapshot':str(WORK),
        'eboot':{'path':str(ART/'eboot.bin'),'size':(ART/'eboot.bin').stat().st_size,'sha256':sha(ART/'eboot.bin')},
        'profile_startup':'baseline','packaged_defaults':{n:(ART/n).read_text() for n in ('submission-options.txt','local-shader-options.txt')},
        'scope':'Observer/client capture retirement only; exact unchanged r21 runtime sources and object bytes. No save/game/driver/compiler changes.',
        'retire_contract':'retire_capture SID:seq targets only a strict matching snapshot/saved ack and canonical regular PNG in fixed observer namespace. Parent must first verify local and remote bytes. Menu allowed; no command polling during settle/measure.',
        'tests_and_audit':audit,'files':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
        'patch_sha256':sha(EVID/'observer-r21c.patch'),'registration_sha256':sha(EVID/'registration.json'),
        'hardware_validation':'pending','console_access_by_agent':False,'saves_modified':False}
(EVID/'ready.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'ready':True,'eboot':result['eboot'],'audit':audit},indent=2))

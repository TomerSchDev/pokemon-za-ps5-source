"""Pin observer-only startup option, unchanged runtime and reviewed driver."""
from pathlib import Path
import difflib,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OBS=ROOT/'port/slot-depth-r23c-observer';OLDOBS=ROOT/'port/slot-depth-r23b-observer'
EVID=ROOT/'evidence/slot-depth-r23c'
BASE=Path('/home/tomer/ps5-za-native/slot-depth-r23b-20261028')
WORK=Path('/home/tomer/ps5-za-native/slot-depth-r23c-20261028')
ART=ROOT/'artifacts/randomizer-r23c-slot-depth/PPSA91762'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()

def main():
    m=json.loads((EVID/'preparation.json').read_text())
    actual={str(p.relative_to(WORK/'source/runtime')):sha(p) for p in (WORK/'source/runtime').rglob('*') if p.is_file()}
    assert actual==m['runtime_sources'],'Runtime source identity'
    for rel,h in m['runtime_sources'].items():assert sha(BASE/'source/runtime'/rel)==h,rel
    objs={str(p.relative_to(WORK/'source/build/ps5/rt')):sha(p) for p in (WORK/'source/build/ps5/rt').rglob('*.o')}
    assert objs==m['runtime_objects'],'Runtime object identity'
    for rel,h in m['runtime_objects'].items():assert sha(BASE/'source/build/ps5/rt'/rel)==h,rel
    changed=[]
    for name,h in m['extra_objects'].items():
        assert sha(BASE/'objects-r23b'/name)==h,name
        if sha(WORK/'objects-r23c'/name)!=h:changed.append(name)
    assert set(changed)=={'observer.o','title_entry.o'},changed
    before=json.loads((ROOT/'evidence/slot-depth-r23/preservation-audit.json').read_text())
    for key in ('game_archive','driver'):assert sha(Path(before[key]['path']))==before[key]['sha256'],key
    imports=[]
    for tree in (BASE,WORK):
        out=subprocess.check_output(['llvm-nm-21','--dynamic','--undefined-only',str(tree/'source/build/ps5/title/llvm-pie.elf')],text=True)
        imports.append(sorted(line.split()[-1] for line in out.splitlines() if line.split()))
    assert imports[0]==imports[1],'Dynamic imports changed'
    obs=json.loads((ROOT/'evidence/slot-depth-r23c-observer/ready.json').read_text())
    assert obs['observer_tests']=='passed ASan+UBSan' and obs['client_tests']=='passed'
    for name,h in obs['source_sha256'].items():assert sha(OBS/name)==h,name
    for name in ('slot-depth-control.h','slot-depth-observer.inc','slot-depth-client.inc','retire-capture.inc','immutable-observer.inc','preparation-observer-api.h','client.py'):
        assert (OBS/name).read_bytes()==(OLDOBS/name).read_bytes(),name
    patch=[]
    for file in sorted(OBS.iterdir()):
        if not file.is_file():continue
        old=OLDOBS/('observer-r23b.c' if file.name=='observer-r23c.c' else file.name)
        if not old.exists():oldtext=[]
        else:oldtext=old.read_text().splitlines(True)
        patch.extend(difflib.unified_diff(oldtext,file.read_text().splitlines(True),fromfile='r23b/'+old.name,tofile='r23c/'+file.name))
    (EVID/'observer-r23c.patch').write_text(''.join(patch))
    defaults={n:(ART/n).read_text() for n in ('submission-options.txt','local-shader-options.txt','slot-depth-options.txt')}
    assert defaults['submission-options.txt']=='batch4\n' and defaults['local-shader-options.txt']=='local\n'
    assert defaults['slot-depth-options.txt'] in ('8\n','16\n')
    audit={'unchanged_runtime_sources':len(actual),'unchanged_runtime_objects':len(objs),'changed_extra_objects':changed,
        'same_dynamic_imports':True,'dynamic_import_count':len(imports[0]),'game_archive':before['game_archive'],'driver':before['driver'],
        'observer_tests':obs,'no_console_access':True,'no_save_operations':True}
    (EVID/'preservation-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    ready={'title_revision':'randomizer-r23c-slot-depth','title_id':'PPSA91762','snapshot':str(WORK),
        'eboot':{'path':str(ART/'eboot.bin'),'size':(ART/'eboot.bin').stat().st_size,'sha256':sha(ART/'eboot.bin')},
        'base_eboot_sha256':m['base_eboot_sha256'],'slot_process_startup':8,'slot_capacity':16,'packaged_defaults':defaults,
        'scope':'Observer-only bounded native fd startup read; all r23 runtime source/object bytes unchanged. No game/save/driver/compiler/clock changes.',
        'startup_contract':'Read /app0/slot-depth-options.txt once before capture opt-in. Exact8 or16, optionally one LF; missing/invalid=>8. Request16 once after first successful non-represented present outside observer settle/measurement, via unchanged checked drain/memory/preflight switch. Rejection leaves8; no retries. Startup state persists across in-process reset.',
        'capture_opt_in_required':False,'runtime_tests_inherited':str(ROOT/'evidence/slot-depth-r23/host-tests-0nqpl_zw/result.json'),
        'observer_tests':obs,'audit':audit,'files':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
        'observer_source_sha256':obs['source_sha256'],'patch_sha256':sha(EVID/'observer-r23c.patch'),
        'registration_sha256':sha(EVID/'registration.json'),'diagnosis_sha256':sha(EVID/'diagnosis.json'),
        'native_read_contract':'Fixed path; O_RDONLY|O_NOFOLLOW|O_NONBLOCK. At most4 bytes and4 read calls, partial reads advance, errors fail without retry, EOF and exact value required, close checked before acceptance. Stage-specific raw results and errno logged.',
        'hardware_validation':'pending','installed':False,
        'console_access_by_agent':False,'saves_modified':False}
    (EVID/'ready.json').write_text(json.dumps(ready,indent=2)+'\n')
    print(json.dumps({'ready':True,'eboot':ready['eboot'],'defaults':defaults,'unchanged_runtime_sources':len(actual),'unchanged_runtime_objects':len(objs)},indent=2))

if __name__=='__main__':main()

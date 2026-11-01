"""Fail-closed preservation and source/test/hash gates for independent r22."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
EVID=ROOT/'evidence/immutable-spans-r22-integration'
BASE=Path('/home/tomer/ps5-za-native/preparation-r21c-20261028')
WORK=Path('/home/tomer/ps5-za-native/immutable-spans-r22-20261028')
ART=ROOT/'artifacts/randomizer-r22-immutable-spans/PPSA91762'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()

def function(text,name):
    found=re.search(r'(?m)^(?:static )?[\w *]+\b'+name+r'\([^;]*?\)\s*\{[\s\S]*?^\}',text)
    assert found,name
    return found[0]

def main():
    manifest=json.loads((EVID/'preparation.json').read_text())
    for rel,h in manifest['runtime_sources'].items():assert sha(BASE/'source/runtime'/rel)==h,'Base changed: '+rel
    for rel,h in manifest['candidate_runtime_sources'].items():assert sha(WORK/'source/runtime'/rel)==h,'Candidate changed since generation: '+rel
    changed=[rel for rel,h in manifest['runtime_sources'].items() if sha(WORK/'source/runtime'/rel)!=h]
    assert set(changed)=={'nvn/objects.c','nvn/vulkan/exec.c'},changed
    added=set(manifest['candidate_runtime_sources'])-set(manifest['runtime_sources'])
    assert added=={'nvn/vulkan/'+n for n in ('za_immutable_spans_r22.inc','za_immutable_spans_r22.h','za_immutable_control_r22.h','za_immutable_boundary_r22.inc')},added
    object_changed=[]
    for rel,h in manifest['runtime_objects'].items():
        assert sha(BASE/'source/build/ps5/rt'/rel)==h,'Base object changed: '+rel
        if sha(WORK/'source/build/ps5/rt'/rel)!=h:object_changed.append(rel)
    assert set(object_changed)=={'nvn/objects.o','nvn/vulkan/exec.o'},object_changed
    extras=[]
    for rel,h in manifest['extra_objects'].items():
        assert sha(BASE/'objects-r21c'/rel)==h,rel
        if sha(WORK/'objects-r22'/rel)!=h:extras.append(rel)
    assert set(extras)=={'observer.o','title_entry.o'},extras
    for name in ('analyze.py','observer.h','preparation-observer-api.h','retire-capture.inc','test-retire.inc'):
        assert sha(HERE/name)==sha(ROOT/'port/preparation-r21c'/name)==manifest['observer_base_files'][name],name
    for a,b in [('immutable-spans.inc','za_immutable_spans_r22.inc'),('immutable-spans.h','za_immutable_spans_r22.h')]:
        assert sha(ROOT/'port/immutable-spans-r22'/a)==sha(WORK/'source/runtime/nvn/vulkan'/b),a
    old=(BASE/'source/runtime/nvn/vulkan/exec.c').read_text();new=(WORK/'source/runtime/nvn/vulkan/exec.c').read_text()
    functions={}
    for name in ('sub','vk_cmd','vk_upload_cmd','vk_transient','vk_transient_copy','guest_copy','vc_flush','xm_copy_back',
                 'renderer_fence_seq','renderer_wait_seq','dispatch_compute','draw','vk_pace_frame'):
        a=function(old,name);b=function(new,name);assert a==b,name;functions[name]=hashlib.sha256(a.encode()).hexdigest()
    before=json.loads((ROOT/'evidence/preparation-r21c/preservation-audit.json').read_text())
    for key in ('game_archive','driver'):assert sha(Path(before[key]['path']))==before[key]['sha256'],key
    nm='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk/bin/llvm-nm'
    imports=[]
    for tree in (BASE,WORK):
        text=subprocess.check_output([nm,'--dynamic','--undefined-only',str(tree/'source/build/ps5/title/llvm-pie.elf')],text=True)
        imports.append(sorted(line.split()[-1] for line in text.splitlines() if line.split()))
    assert imports[0]==imports[1],'Dynamic imports changed'
    test=max(EVID.glob('host-tests-*/result.json'),key=lambda p:p.stat().st_mtime)
    tr=json.loads(test.read_text());assert tr['status']=='passed'
    for rel,h in tr['input_sha256'].items():assert sha(ROOT/rel)==h,'Test source changed: '+rel
    for rel,h in tr['runtime_sha256'].items():assert sha(WORK/'source'/rel)==h,'Test runtime changed: '+rel
    audit={'changed_runtime_sources':changed,'added_runtime_sources':sorted(added),
        'unchanged_runtime_sources':len(manifest['runtime_sources'])-len(changed),
        'changed_runtime_objects':object_changed,'unchanged_runtime_objects':len(manifest['runtime_objects'])-len(object_changed),
        'changed_extra_objects':extras,'unchanged_functions_sha256':functions,'r21c_retirement_identical':True,
        'tb1_helper_identical':True,'same_dynamic_imports':True,'dynamic_import_count':len(imports[0]),
        'game_archive':before['game_archive'],'driver':before['driver'],'host_tests_path':str(test),
        'no_console_access':True,'no_save_operations':True}
    (EVID/'preservation-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    ready={'title_revision':'randomizer-r22-immutable-spans','title_id':'PPSA91762','snapshot':str(WORK),
        'eboot':{'path':str(ART/'eboot.bin'),'size':(ART/'eboot.bin').stat().st_size,'sha256':sha(ART/'eboot.bin')},
        'immutable_startup':'off','preparation_startup':'baseline','preparation_profiles':['baseline','plan-only','lazy-only','optimized'],
        'packaged_defaults':{n:(ART/n).read_text() for n in ('submission-options.txt','local-shader-options.txt')},
        'scope':'Only three reviewed immutable literals within logical sequence; explicit drained off/on control. Independent future A/B build, not deployed.',
        'command':'immutable_spans off|on','collect':'--immutable-spans off|on / expected_immutable_spans=mode',
        'tests':tr,'audit':audit,'files':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
        'patch_sha256':sha(EVID/'runtime-r22.patch'),'registration_sha256':sha(EVID/'registration.json'),
        'hardware_validation':'pending','console_access_by_agent':False,'saves_modified':False,'installed':False}
    assert ready['packaged_defaults']=={'submission-options.txt':'batch4\n','local-shader-options.txt':'local\n'}
    (EVID/'ready.json').write_text(json.dumps(ready,indent=2)+'\n')
    print(json.dumps({'ready_for_review':True,'eboot':ready['eboot'],'audit':audit},indent=2))

if __name__=='__main__':main()

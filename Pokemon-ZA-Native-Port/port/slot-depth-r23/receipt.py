"""Pin the r23 build, exact runtime preservation, tests and observer contract."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
EVID=ROOT/'evidence/slot-depth-r23';BASE=Path('/home/tomer/ps5-za-native/immutable-spans-r22-20261028')
WORK=Path('/home/tomer/ps5-za-native/slot-depth-r23-20261028');ART=ROOT/'artifacts/randomizer-r23-slot-depth/PPSA91762'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()
def function(text,name):
    m=re.search(r'(?m)^(?:static )?[\w *]+\b'+name+r'\([^;]*?\)\s*\{[\s\S]*?^\}',text);assert m,name;return m[0]
def main():
    m=json.loads((EVID/'preparation.json').read_text());changes=[]
    for rel,h in m['runtime_sources'].items():
        assert sha(BASE/'source/runtime'/rel)==h,rel
        if sha(WORK/'source/runtime'/rel)!=h:changes.append(rel)
    assert set(changes)=={'nvn/vulkan/exec.c','nvn/objects.c','nvn/vulkan/za_submission_queue_r20.inc'},changes
    for rel,h in m['candidate_runtime_sources'].items():assert sha(WORK/'source/runtime'/rel)==h,rel
    added=set(m['candidate_runtime_sources'])-set(m['runtime_sources'])
    assert added=={'nvn/vulkan/'+x for x in ('slot-depth-control.h','za_slot_policy_r23.h','za_slot_state_r23.inc','za_slot_runtime_r23.inc')}
    changed_objects=[]
    for rel,h in m['runtime_objects'].items():
        assert sha(BASE/'source/build/ps5/rt'/rel)==h,rel
        if sha(WORK/'source/build/ps5/rt'/rel)!=h:changed_objects.append(rel)
    assert set(changed_objects)=={'nvn/objects.o','nvn/vulkan/exec.o'},changed_objects
    changed_extras=[]
    for rel,h in m['extra_objects'].items():
        assert sha(BASE/'objects-r22'/rel)==h,rel
        if sha(WORK/'objects-r23'/rel)!=h:changed_extras.append(rel)
    assert set(changed_extras)=={'observer.o','title_entry.o'},changed_extras
    old=(BASE/'source/runtime/nvn/vulkan/exec.c').read_text();new=(WORK/'source/runtime/nvn/vulkan/exec.c').read_text()
    preserved={}
    for name in ('vk_wait_seq','begin_cb','vk_cmd','vk_upload_cmd','vk_alloc_set','vk_transient','vk_transient_copy','guest_copy','vc_flush','xm_copy_back','renderer_fence_seq','renderer_wait_seq','dispatch_compute','draw','vk_pace_frame','vk_exec_reset'):
        a=function(old,name);b=function(new,name);assert a==b,name;preserved[name]=hashlib.sha256(a.encode()).hexdigest()
    assert function(old,'vk_submit_extra').replace('(cur_sub + 1) % SUBS','(cur_sub + 1) % za_slot_active')==function(new,'vk_submit_extra')
    before=json.loads((ROOT/'evidence/immutable-spans-r22-integration/preservation-audit.json').read_text())
    for key in ('driver','game_archive'):assert sha(Path(before[key]['path']))==before[key]['sha256'],key
    nm='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk/bin/llvm-nm'
    imports=[]
    for tree in (BASE,WORK):
        text=subprocess.check_output([nm,'--dynamic','--undefined-only',str(tree/'source/build/ps5/title/llvm-pie.elf')],text=True)
        imports.append(sorted(line.split()[-1] for line in text.splitlines() if line.split()))
    assert imports[0]==imports[1],'Dynamic imports changed'
    test=max(EVID.glob('host-tests-*/result.json'),key=lambda p:p.stat().st_mtime);tr=json.loads(test.read_text());assert tr['status']=='passed'
    for rel,h in tr['input_sha256'].items():assert sha(ROOT/rel)==h,rel
    for rel,h in tr['runtime_sha256'].items():assert sha(WORK/'source'/rel)==h,rel
    obs=json.loads((ROOT/'evidence/slot-depth-r23-observer/ready.json').read_text())
    assert obs['observer_tests']=='passed ASan+UBSan' and obs['client_tests']=='passed'
    for name,h in obs['source_sha256'].items():assert sha(ROOT/'port/slot-depth-r23-observer'/name)==h,name
    assert sha(HERE/'slot-depth-control.h')==sha(WORK/'source/runtime/nvn/vulkan/slot-depth-control.h')==obs['source_sha256']['slot-depth-control.h']
    audit={'changed_runtime_sources':changes,'added_runtime_sources':sorted(added),'unchanged_runtime_sources':len(m['runtime_sources'])-len(changes),
       'changed_runtime_objects':changed_objects,'unchanged_runtime_objects':len(m['runtime_objects'])-len(changed_objects),
       'changed_extra_objects':changed_extras,'same_dynamic_imports':True,'dynamic_import_count':len(imports[0]),
       'game_archive':before['game_archive'],'driver':before['driver'],'unchanged_functions_sha256':preserved,
       'submission_order_function_only_modulus_changed':True,'runtime_test_result':str(test),'observer_test_result':obs['test_result'],
       'no_console_access':True,'no_save_operations':True}
    (EVID/'preservation-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    ready={'title_revision':'randomizer-r23-slot-depth','title_id':'PPSA91762','snapshot':str(WORK),
       'eboot':{'path':str(ART/'eboot.bin'),'size':(ART/'eboot.bin').stat().st_size,'sha256':sha(ART/'eboot.bin')},
       'slot_startup':8,'slot_capacity':16,'preparation_startup':'baseline','immutable_startup':'off',
       'packaged_defaults':{n:(ART/n).read_text() for n in ('submission-options.txt','local-shader-options.txt')},
       'scope':'Logical slot depth only; same batch4 ordering/retirement. Checked completion and memory-gated8/16 explicit post-present switch; no shader/game/driver/clock changes.',
       'memory_gate':'Largest free contiguous direct-memory extent >=1GiB before and after extra pool/CB/CQ preflight. Admission threshold, not a reservation or future-growth guarantee.32-bit descriptor placement is checked by actual pool creation. Extra transient chunks may persist when returning8.',
       'reset_semantics':'Default8 at process startup. Active depth and monotonic timeline persist across in-process reset; explicit switch8 reverts.',
       'command':'slot_depth 8|16','collect':'expected_slot_depth=8|16 / --slot-depth 8|16',
       'runtime_tests':tr,'observer_tests':obs,'audit':audit,
       'files':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},'observer_source_sha256':obs['source_sha256'],
       'patch_sha256':sha(EVID/'runtime-r23.patch'),'registration_sha256':sha(EVID/'registration.json'),
       'hardware_validation':'pending','installed':False,'console_access_by_agent':False,'saves_modified':False}
    assert ready['packaged_defaults']=={'submission-options.txt':'batch4\n','local-shader-options.txt':'local\n'}
    (EVID/'ready.json').write_text(json.dumps(ready,indent=2)+'\n')
    print(json.dumps({'ready_for_review':True,'eboot':ready['eboot'],'audit':audit},indent=2))
if __name__=='__main__':main()

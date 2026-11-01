"""Isolated r23 clone and exact-anchor patch of finalized r22; no console I/O."""
from pathlib import Path
import difflib,hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
EVID=ROOT/'evidence/slot-depth-r23'
BASE=Path('/home/tomer/ps5-za-native/immutable-spans-r22-20261028')
WORK=Path('/home/tomer/ps5-za-native/slot-depth-r23-20261028')

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()
def once(text,old,new):
    assert text.count(old)==1,old[:100]
    return text.replace(old,new,1)
def patched():
    runtime=BASE/'source/runtime'
    text=(runtime/'nvn/vulkan/exec.c').read_text()
    text=once(text,'#include "za_preparation_r21.h"','#include "za_preparation_r21.h"\n#include "za_slot_policy_r23.h"')
    text=once(text,'#define SUBS 8','#define SUBS ZA_SLOT_DEPTH_CAPACITY')
    text=once(text,'static int cur_sub;','static int cur_sub;\n#include "za_slot_state_r23.inc"')
    text=once(text,'        vk_wait_seq(s->seq);','''        uint64_t za_before = za_slots_before_wait(s->seq);
        uint64_t za_t0 = SDL_GetTicksNS();
        vk_wait_seq(s->seq);
        za_slots_after_wait(s->seq,za_before,SDL_GetTicksNS()-za_t0);''')
    text=once(text,'cur_sub = (cur_sub + 1) % SUBS;','cur_sub = (cur_sub + 1) % za_slot_active;')
    text=once(text,'#include "za_immutable_spans_r22.inc"','#include "za_immutable_spans_r22.inc"\n#include "za_slot_runtime_r23.inc"')
    text=once(text,'    za_preparation_report();','    za_preparation_report();\n    za_slots_report();')
    queue=(runtime/'nvn/vulkan/za_submission_queue_r20.inc').read_text()
    queue=once(queue,'    VK_CHECK(sr);','    VK_CHECK(sr);\n    za_slots_physical_submit(si);')
    objects=(runtime/'nvn/objects.c').read_text()
    at=objects.index('int za_preparation_switch_profile(')
    objects=objects[:at]+'''#include "vulkan/slot-depth-control.h"
extern int backend_slot_depth_switch(const char*,uint64_t);
extern void backend_slot_depth_status(ZaSlotDepthStatus*);
int za_slot_depth_switch(const char *depth,uint64_t frame) {
    exec_lock_take();
    int applied=backend_slot_depth_switch(depth,frame);
    exec_lock_give();
    return applied;
}
void za_slot_depth_status(ZaSlotDepthStatus *out) {
    if(!out)return;
    exec_lock_take();backend_slot_depth_status(out);exec_lock_give();
}

'''+objects[at:]
    return {'nvn/vulkan/exec.c':text,'nvn/vulkan/za_submission_queue_r20.inc':queue,'nvn/objects.c':objects}
def sync_sources():
    patch=[]
    for rel,text in patched().items():
        (WORK/'source/runtime'/rel).write_text(text,newline='\n')
        old=(BASE/'source/runtime'/rel).read_text()
        patch.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='r22/'+rel,tofile='r23/'+rel))
    for old,new in [('slot-depth-control.h','slot-depth-control.h'),('slot-policy.h','za_slot_policy_r23.h'),('slot-state.inc','za_slot_state_r23.inc'),('slot-runtime.inc','za_slot_runtime_r23.inc')]:
        text=(HERE/old).read_text()
        (WORK/'source/runtime/nvn/vulkan'/new).write_text(text,newline='\n')
        patch.extend(difflib.unified_diff([],text.splitlines(True),fromfile='/dev/null',tofile='r23/nvn/vulkan/'+new))
    (EVID/'runtime-r23.patch').write_text(''.join(patch))
    m=json.loads((EVID/'preparation.json').read_text())
    m['candidate_runtime_sources']={str(p.relative_to(WORK/'source/runtime')):sha(p) for p in (WORK/'source/runtime').rglob('*') if p.is_file()}
    (EVID/'preparation.json').write_text(json.dumps(m,indent=2)+'\n')
def main():
    ready=json.loads((ROOT/'evidence/immutable-spans-r22-integration/ready.json').read_text())
    pin=json.loads((ROOT/'evidence/immutable-spans-r22-integration/preparation.json').read_text())
    for rel,h in pin['candidate_runtime_sources'].items():assert sha(BASE/'source/runtime'/rel)==h,rel
    assert not WORK.exists() and not EVID.exists(),'Do not overwrite a prior experiment'
    EVID.mkdir(parents=True)
    m={'base':str(BASE),'work':str(WORK),'base_eboot_sha256':ready['eboot']['sha256'],
       'runtime_sources':pin['candidate_runtime_sources'],
       'runtime_objects':{str(p.relative_to(BASE/'source/build/ps5/rt')):sha(p) for p in (BASE/'source/build/ps5/rt').rglob('*.o')},
       'extra_objects':{p.name:sha(p) for p in (BASE/'objects-r22').glob('*.o')}}
    (EVID/'preparation.json').write_text(json.dumps(m,indent=2)+'\n')
    for name in ('source','port','inc','shaders','evidence'):
        shutil.copytree(BASE/name,WORK/name,symlinks=True,ignore=shutil.ignore_patterns('build','.git') if name=='source' else None)
    for name in ('rt','inc'):shutil.copytree(BASE/'source/build/ps5'/name,WORK/'source/build/ps5'/name,symlinks=True)
    shutil.copytree(BASE/'objects-r22',WORK/'objects-r23')
    sync_sources();print('Prepared',WORK)
if __name__=='__main__':main()

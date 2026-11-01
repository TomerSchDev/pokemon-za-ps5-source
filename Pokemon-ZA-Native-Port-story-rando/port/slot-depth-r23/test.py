"""Compile/run real changed helpers, extracted lifecycle functions and queue tests."""
from pathlib import Path
import hashlib,importlib.util,json,re,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
EVID=ROOT/'evidence/slot-depth-r23';WORK=Path('/home/tomer/ps5-za-native/slot-depth-r23-20261028')
spec=importlib.util.spec_from_file_location('prepare',HERE/'prepare.py');prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
prepare.sync_sources()
T=Path(tempfile.mkdtemp(prefix='host-tests-',dir=EVID))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def function(text,name):
    m=re.search(r'(?m)^(?:static )?[\w *]+\b'+name+r'\([^;]*?\)\s*\{[\s\S]*?^\}',text);assert m,name;return m[0]
runtime=WORK/'source/runtime';src=(runtime/'nvn/vulkan/exec.c').read_text();obj=(runtime/'nvn/objects.c').read_text()
code=(HERE/'test-runtime-prefix.c').read_text()+'\n'+function(src,'sub')+'\n'+function(src,'renderer_fence_seq')+'\n'
code+='static int wrapper_lock; static void exec_lock_take(void){assert(!wrapper_lock);wrapper_lock=1;} static void exec_lock_give(void){assert(wrapper_lock);wrapper_lock=0;}\n'
code+=function(obj,'za_slot_depth_switch')+'\n'+function(obj,'za_slot_depth_status')+'\n'+(HERE/'test-runtime-suffix.c').read_text()
(T/'runtime-test.c').write_text(code)
base=(ROOT/'port/submission-r20b/test-executor.c').read_text()
base=base.replace('static uint64_t slots[8];','static uint64_t slots[16]; static unsigned test_slot_depth=8;').replace('slot = (slot + 1) % 8;','slot = (slot + 1) % test_slot_depth;')
base=base.replace('#include "queue.inc"','static void za_slots_physical_submit(const VkSubmitInfo2 *si){assert(captured_n && si->signalSemaphoreInfoCount==captured[captured_n-1].signals);}\n#include "queue.inc"')
base=base.replace('int main(void) {','static int run_suite(void) {')+'\nint main(void){test_slot_depth=8;assert(!run_suite());test_slot_depth=16;assert(!run_suite());return 0;}\n'
(T/'queue-test.c').write_text(base)
for source,target in [('za_submission_r20.h','submission.h'),('za_submission_queue_r20.inc','queue.inc'),('za_submission_executor_r20.inc','executor.inc'),('za_submission_boundary_r20b.inc','boundary.inc')]:
    shutil.copy2(runtime/'nvn/vulkan'/source,T/target)
inputs={str(p.relative_to(ROOT)):sha(p) for p in HERE.iterdir() if p.is_file()}
with (T/'tests.log').open('w') as log:
    for name in ('runtime','queue'):
        args=['clang-21','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-pthread',
              '-I/home/tomer/ps5-za-native/PS5_Mesa/include','-I'+str(HERE),'-I'+str(T),str(T/(name+'-test.c')),'-o',str(T/(name+'-test'))]
        subprocess.run(args,check=True,stdout=log,stderr=log)
        subprocess.run([str(T/(name+'-test'))],check=True,stdout=log,stderr=log)
for p,h in inputs.items():assert sha(ROOT/p)==h,'Changed during test: '+p
result={'status':'passed','runtime_tests':'passed ASan+UBSan','queue_tests':'passed ASan+UBSan','actual_sub_and_fence_and_lock_wrappers':True,
        'actual_queue_and_executor_both_slot_depths':True,'input_sha256':inputs,'runtime_sha256':{str(p.relative_to(WORK/'source')):sha(p) for p in (runtime/'nvn/vulkan').glob('za_slot*')},
        'test_log_sha256':sha(T/'tests.log'),'host_generated_sources':{p.name:sha(p) for p in T.glob('*.c')}}
for p in ('runtime/nvn/vulkan/exec.c','runtime/nvn/vulkan/za_submission_queue_r20.inc','runtime/nvn/objects.c','runtime/nvn/vulkan/slot-depth-control.h'):
    result['runtime_sha256'][p]=sha(WORK/'source'/p)
(T/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print((T/'tests.log').read_text());print(T/'result.json')

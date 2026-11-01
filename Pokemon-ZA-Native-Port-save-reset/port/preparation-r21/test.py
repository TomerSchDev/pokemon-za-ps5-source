"""Extract actual baseline/candidate functions; compare API writes and exact copied bytes."""
from pathlib import Path
import hashlib,json,re,subprocess,os
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=Path('/home/tomer/ps5-za-native/batch-r20b-20261028/source/runtime/nvn/vulkan/exec.c')
WORK=Path('/home/tomer/ps5-za-native/preparation-r21-20261028')
CAND=WORK/'source/runtime/nvn/vulkan/exec.c'
OUT=WORK/'host-tests';OUT.mkdir(exist_ok=True)
EVID=ROOT/'evidence/preparation-r21';EVID.mkdir(exist_ok=True)
def extract(src,name):
    m=re.search(r'(?m)^static VkDescriptorSet '+name+r'\([\s\S]*?^\}',src)
    assert m,name
    return m[0]
base=BASE.read_text();cand=CAND.read_text()
parts=[(HERE/'test-prefix.c').read_text(),extract(base,'stage_set').replace('stage_set(', 'stage_set_r20b_reference(',1)]
parts += [extract(cand,name) for name in ('stage_set_original','stage_set_prepared','stage_set')]
parts += [(HERE/'test-suffix.c').read_text()]
harness=OUT/'extracted-preparation.c';harness.write_text('\n\n'.join(parts)+'\n')
cmd=['clang-21','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-pthread',
     '-I/home/tomer/ps5-za-native/PS5_Mesa/include','-I'+str(HERE),str(harness),'-o',str(OUT/'test-preparation')]
build=subprocess.run(cmd,capture_output=True,text=True)
(EVID/'host-build.log').write_text(build.stdout+build.stderr)
assert build.returncode==0,build.stderr
env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1',UBSAN_OPTIONS='halt_on_error=1')
test=subprocess.run([str(OUT/'test-preparation')],capture_output=True,text=True,env=env)
(EVID/'host-tests.log').write_text(test.stdout+test.stderr)
assert test.returncode==0,test.stdout+test.stderr
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
receipt={'passed':True,'compiler':cmd,'result':test.stdout.strip(),'baseline_exec_sha256':sha(BASE),'candidate_exec_sha256':sha(CAND),
 'harness_sha256':sha(harness),'test_binary_sha256':sha(OUT/'test-preparation'),
 'files':{n:sha(HERE/n) for n in ('preparation.h','counters.inc','boundary.inc','test-prefix.c','test-suffix.c','test.py')},
 'meaning':'Real extracted stage_set functions against mocked side-effect resolvers and normalized Vulkan descriptor outputs, not a hand-written mirror of recipe implementation.',
 'limitations':'No Vulkan driver/GPU execution; parent conducts hardware tests. Observer protocol independently tested.'}
(EVID/'host-tests.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(test.stdout,end='')

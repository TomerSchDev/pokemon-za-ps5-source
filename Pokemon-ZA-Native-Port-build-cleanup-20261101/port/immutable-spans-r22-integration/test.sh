#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/immutable-spans-r22-20261028
evidence="$project/evidence/immutable-spans-r22-integration"
mkdir -p "$evidence"
t=$(mktemp -d "$evidence/host-tests-XXXXXX")
# Preserve the r21c FIFO rejection test on a Linux filesystem, not NTFS.
store=$(mktemp -d /tmp/za-r22-store-XXXXXX)
exec > >(tee "$t/tests.log") 2>&1
python3 - "$project" "$work" "$t" <<'PY'
from pathlib import Path
import hashlib,importlib.util,json,sys
project,work,test=map(Path,sys.argv[1:])
spec=importlib.util.spec_from_file_location('tb1',project/'port/immutable-spans-r22/generate.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
base=Path('/home/tomer/ps5-za-native/preparation-r21c-20261028/source')
old=(base/'runtime/nvn/vulkan/exec.c').read_text();new=(work/'source/runtime/nvn/vulkan/exec.c').read_text()
(test/'extracted-sites.inc').write_text(g.extract_function(old,'ubo_span')+'\n'+g.extract_sites(old,'original')+g.extract_sites(new,'candidate'))
start=old.index('VkSpan vk_transient_copy(');end=old.index('\n}',start)+2
(test/'extracted-copy.inc').write_text(old[start:end]+'\n')
objects=(work/'source/runtime/nvn/objects.c').read_text()
wrapper=(project/'port/immutable-spans-r22-integration/immutable-wrapper.inc').read_text()
assert objects.count(wrapper)==1,'Real objects.c wrapper differs from reviewed source'
(test/'extracted-immutable-wrapper.inc').write_text(wrapper)
# Reviewed TB1 cache and exact literals remain byte identical in integration.
for a,b in [('immutable-spans.inc','za_immutable_spans_r22.inc'),('immutable-spans.h','za_immutable_spans_r22.h')]:
    assert (project/'port/immutable-spans-r22'/a).read_bytes()==(work/'source/runtime/nvn/vulkan'/b).read_bytes()
for a,b in [('immutable-control.h','za_immutable_control_r22.h'),('immutable-boundary.inc','za_immutable_boundary_r22.inc')]:
    assert (project/'port/immutable-spans-r22-integration'/a).read_bytes()==(work/'source/runtime/nvn/vulkan'/b).read_bytes()
PY
flags=(-std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -pthread)
clang-21 "${flags[@]}" -I"$t" -I"$work/source" "$project/port/immutable-spans-r22/test-immutable.c" -o "$t/test-immutable"
ASAN_OPTIONS=detect_leaks=1 "$t/test-immutable"
clang-21 "${flags[@]}" -I"$t" -I"$work/source" "$root/test-boundary.c" -o "$t/test-boundary"
ASAN_OPTIONS=detect_leaks=1 "$t/test-boundary"
clang-21 "${flags[@]}" -I"$root" -DZA_OBSERVER_HOST_TEST=1 \
    "-DZA_OBSERVER_ROOT=\"$store\"" "-DZA_OBSERVER_ENABLE=\"$t/enable.txt\"" \
    "$root/test-observer.c" -o "$t/test-observer"
ASAN_OPTIONS=detect_leaks=1 "$t/test-observer"
cp -a "$store" "$t/store"
PYTHONDONTWRITEBYTECODE=1 python3 "$root/test-client.py" -v
python3 - "$project" "$work" "$t" <<'PY'
from pathlib import Path
import hashlib,json,subprocess,sys
project,work,test=map(Path,sys.argv[1:]);root=project/'port/immutable-spans-r22-integration'
receipts=sorted((test/'store').glob('session_*/ack_*.json'));acks=[json.loads(p.read_text()) for p in receipts]
immutable=[a for a in acks if a['op']=='immutable_spans']
assert {a['mode'] for a in immutable if a['result']=='applied'}=={'off','on'}
assert {'rejected_boundary','rejected_in_menu','drain_failed','receipt_mismatch','rejected_mode'}<={a['result'] for a in immutable}
assert {a['profile'] for a in acks if a['op']=='preparation' and a['result']=='applied'}=={'baseline','plan-only','lazy-only','optimized'}
assert any(a['op']=='retire_capture' and a['result']=='retired' for a in acks)
# Apply the complete patch only to a tiny new private evidence tree.
base=Path('/home/tomer/ps5-za-native/preparation-r21c-20261028/source');trial=test/'apply-check'
for rel in ('runtime/nvn/vulkan/exec.c','runtime/nvn/objects.c'):
    p=trial/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((base/rel).read_bytes())
subprocess.run(['patch','-p1','--batch','--forward','-i',str(project/'evidence/immutable-spans-r22-integration/runtime-r22.patch')],cwd=trial,check=True)
for p in trial.rglob('*'):
    if p.is_file():assert p.read_bytes()==(work/'source'/p.relative_to(trial)).read_bytes(),str(p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result={'status':'passed','immutable_tests':'passed ASan+UBSan','boundary_tests':'passed ASan+UBSan',
    'observer_tests':'passed ASan+UBSan','client_tests':'passed','immutable_receipts':len(immutable),
    'real_helper_and_wrapper':True,'patch_exact_reproduction':True,'hardware_tested':False,
    'input_sha256':{str(p.relative_to(project)):sha(p) for p in root.iterdir() if p.is_file()},
    'runtime_sha256':{},
    'receipt_sha256':{str(p.relative_to(test)):sha(p) for p in receipts}}
# The keys above identify runtime paths, and hash their actual integrated contents.
result['runtime_sha256']={str(p.relative_to(trial)):sha(work/'source'/p.relative_to(trial)) for p in trial.rglob('*') if p.is_file()}
(test/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print('Integration host tests:',test/'result.json')
PY

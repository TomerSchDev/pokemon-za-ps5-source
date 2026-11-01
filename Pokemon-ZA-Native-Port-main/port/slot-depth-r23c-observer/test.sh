#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
evidence="$project/evidence/slot-depth-r23c-observer"
mkdir -p "$evidence"
t=$(mktemp -d "$evidence/host-tests-XXXXXX")
store=$(mktemp -d /tmp/za-r23c-observer-XXXXXX)
startup_store=$(mktemp -d /tmp/za-r23c-startup-XXXXXX)
exec > >(tee "$t/tests.log") 2>&1
python3 - "$t" "$root" <<'PY'
from pathlib import Path
import hashlib,json,sys
test,root=map(Path,sys.argv[1:])
(test/'input-sha.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()},indent=2)+'\n')
PY
clang-21 -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -pthread \
    -I"$root" -DZA_OBSERVER_HOST_TEST=1 \
    "-DZA_OBSERVER_ROOT=\"$store\"" "-DZA_OBSERVER_ENABLE=\"$t/enable.txt\"" \
    "-DZA_SLOT_STARTUP_PATH=\"$t/missing-slot-depth-options.txt\"" \
    "$root/test-observer.c" -o "$t/test-observer"
ASAN_OPTIONS=detect_leaks=1 "$t/test-observer"
cp -a "$store" "$t/store"
clang-21 -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -pthread \
    -I"$root" -DZA_OBSERVER_HOST_TEST=1 \
    "-DZA_OBSERVER_ROOT=\"$startup_store\"" "-DZA_OBSERVER_ENABLE=\"$t/startup-enable.txt\"" \
    "-DZA_SLOT_STARTUP_PATH=\"$startup_store/slot-depth-options.txt\"" \
    "$root/test-startup.c" -o "$t/test-startup"
ASAN_OPTIONS=detect_leaks=1 "$t/test-startup"
cp -a "$startup_store" "$t/startup-store"
PYTHONDONTWRITEBYTECODE=1 python3 "$root/test-client.py" -v
python3 - "$t" "$root" "$project" <<'PY'
from pathlib import Path
import hashlib,json,sys
test,root,project=map(Path,sys.argv[1:]);receipts=sorted((test/'store').glob('session_*/ack_*.json'))
acks=[json.loads(p.read_text()) for p in receipts];slot=[a for a in acks if a['op']=='slot_depth']
assert {a['active_slots'] for a in slot if a['result']=='applied'}=={8,16}
assert {'rejected_boundary','rejected_in_menu','rejected_depth','drain_failed','memory_gate','incompatible_profile','preflight_failed','receipt_mismatch'}<={a['result'] for a in slot}
for a in slot:
    if a['result']=='applied':
        assert a['active_slots']==a['requested_slots']==a['runtime_result']==a['status_result']==a['status_requested_slots']
        assert a['frame']==a['status_frame'] and a['completed_seq']>=a['drained_seq']
        if a['active_slots']==16:assert a['budget_valid']==1 and a['largest_free_extent']>=a['required_headroom_bytes']>=1<<30
assert any(a['op']=='retire_capture' and a['result']=='retired' for a in acks)
assert {a['mode'] for a in acks if a['op']=='immutable_spans' and a['result']=='applied'}=={'off','on'}
assert {a['profile'] for a in acks if a['op']=='preparation' and a['result']=='applied'}=={'baseline','plan-only','lazy-only','optimized'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source_pins=json.loads((test/'input-sha.json').read_text())
assert source_pins=={p.name:sha(p) for p in root.iterdir() if p.is_file()},'Sources changed while tests were running'
for name in ('retire-capture.inc','test-retire.inc','observer.h','analyze.py','preparation-observer-api.h','immutable-control.h','immutable-observer.inc'):
    assert sha(root/name)==sha(project/'port/immutable-spans-r22-integration'/name),name
result={'observer_tests':'passed ASan+UBSan','client_tests':'passed','slot_depth_receipts':len(slot),'total_receipts':len(acks),
    'startup_actual_observer_tests':'passed ASan+UBSan',
    'source_sha256':source_pins,
    'retirement_preserved_exactly':True,'prior_preparation_and_immutable_protocols_preserved':True,
    'receipt_sha256':{str(p.relative_to(test)):sha(p) for p in receipts},'console_access':False,'hardware_validation':'pending'}
for name in ('client.py','test-client.py','slot-depth-control.h','slot-depth-observer.inc','slot-depth-client.inc','retire-capture.inc','test-retire.inc'):
    assert sha(root/name)==sha(project/'port/slot-depth-r23-observer'/name),name
result['r23_protocol_client_retirement_preserved_exactly']=True
(test/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print('Verified r23c startup observer/client:',test/'result.json')
PY

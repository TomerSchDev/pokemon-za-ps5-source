#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
evidence="$project/evidence/preparation-r21c"
mkdir -p "$evidence"
t=$(mktemp -d "$evidence/host-tests-XXXXXX")
# Linux backing is needed for the FIFO rejection test; /mnt/c is NTFS.
store=$(mktemp -d /tmp/za-r21c-store-XXXXXX)
exec > >(tee "$t/tests.log") 2>&1
clang-21 -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -pthread \
    -I"$root" -DZA_OBSERVER_HOST_TEST=1 \
    "-DZA_OBSERVER_ROOT=\"$store\"" "-DZA_OBSERVER_ENABLE=\"$t/enable.txt\"" \
    "$root/test-observer.c" -o "$t/test"
ASAN_OPTIONS=detect_leaks=1 "$t/test"
cp -a "$store" "$t/store"
PYTHONDONTWRITEBYTECODE=1 python3 "$root/test-client.py" -v
python3 - "$t" "$root" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]); receipts=sorted((p/'store').glob('session_*/ack_*.json'))
data=[json.loads(f.read_text()) for f in receipts]
prep=[a for a in data if a['op']=='preparation']
assert {a['profile'] for a in prep if a['result']=='applied'}=={'baseline','plan-only','lazy-only','optimized'}
assert {'rejected_boundary','rejected_in_menu','drain_failed','receipt_mismatch','rejected_profile'} <= {a['result'] for a in prep}
assert any(a['op']=='measure' and a['result']=='complete' for a in data)
result={'observer_tests':'passed ASan+UBSan','client_tests':'passed','preparation_receipts':len(prep),
        'source_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(sys.argv[2]).iterdir() if f.is_file()},
        'receipt_sha256':{str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in receipts}}
(p/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print('Verified real observer receipts:',len(prep),'preparation receipts; result:',p/'result.json')
PY

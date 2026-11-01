#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
source=${1:-/home/tomer/ps5-za-native/preparation-r21-20261028/source}
evidence="$project/evidence/immutable-spans-r22"
mkdir -p "$evidence"
t=$(mktemp -d "$evidence/host-tests-XXXXXX")
exec > >(tee "$t/tests.log") 2>&1
PYTHONDONTWRITEBYTECODE=1 python3 "$root/generate.py" --source "$source" --out "$t/generated"
clang-21 -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -pthread \
    -I"$t/generated" "$root/test-immutable.c" -o "$t/test-immutable"
ASAN_OPTIONS=detect_leaks=1 "$t/test-immutable"
python3 - "$source" "$t" <<'PY'
from pathlib import Path
import hashlib,json,subprocess,sys
source=Path(sys.argv[1]);work=Path(sys.argv[2]);generated=work/'generated'
manifest=json.loads((generated/'manifest.json').read_text())
assert hashlib.sha256((source/'runtime/nvn/vulkan/exec.c').read_bytes()).hexdigest()==manifest['source_sha256']
# Check patch syntax/applicability without writing to the live snapshot.
subprocess.run(['patch','--dry-run','-p1','--batch','--forward','-i',str(generated/'candidate.patch')],cwd=source,check=True)
# Prove that the delivered patch exactly reproduces the generated files, only
# in a private evidence copy containing the one input file.
trial=work/'apply-check'; rel=Path('runtime/nvn/vulkan/exec.c')
(trial/rel.parent).mkdir(parents=True)
(trial/rel).write_bytes((source/rel).read_bytes())
subprocess.run(['patch','-p1','--batch','--forward','-i',str(generated/'candidate.patch')],cwd=trial,check=True)
for name in ('exec.c','za_immutable_spans_r22.inc','za_immutable_spans_r22.h'):
    assert (trial/rel.parent/name).read_bytes()==(generated/rel.parent/name).read_bytes()
result={'status':'passed','source_unchanged':True,'sanitizers':['address','undefined'],
        'source_sha256':manifest['source_sha256'],'generator_manifest':'generated/manifest.json',
        'tests':['real unbound UBO/default vertex/unbound vertex snippets','descriptor addressed bytes/range',
                 'exact kind/size/alignment','initial seq0/logical sequence/reset','bounded collision fallback',
                 'baseline disabled','counters','original allocator failure propagation','patch exactly reproduces generated files in private copy'],
        'runtime_modified':False,'gpu_or_console_test':False}
(work/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print('Result:',work/'result.json')
PY

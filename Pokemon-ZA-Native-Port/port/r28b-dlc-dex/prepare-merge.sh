#!/usr/bin/env bash
# Usage: prepare-merge.sh --runtime-tree TREE --base-out OUT --archive FILE --work NEW_TREE
#        --eboot-sha256 HASH --pie-sha256 HASH --archive-sha256 HASH
set -euo pipefail
renice 10 -p $$ >/dev/null
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$here/prepare-merge-tree.py" "$@"
work_tree=
while [[ $# -gt 0 ]]; do
    case $1 in --work) work_tree=$2; shift 2 ;; *) shift ;; esac
done
[[ -n $work_tree ]] || exit 2
out=$work_tree/r28b
exec > >(tee "$out/evidence/merge-control.log") 2>&1
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
export ZA_PS5_EXTRA_INPUTS="$(cat "$out/evidence/control-link-inputs.txt")"
mapfile -t relative_inputs < "$out/evidence/runtime-inputs.txt"
runtime=(); for relative in "${relative_inputs[@]}"; do runtime+=("$work_tree/source/$relative"); done
cd "$work_tree/source"
bash tools/ps5/link-title.sh "$out/control/llvm-pie.elf" "${runtime[@]}" "$out/base/liblasgame-base.a"
python3 - "$out" <<'PY'
from pathlib import Path
import hashlib,json,sys
out=Path(sys.argv[1]);config=json.loads((out/'evidence/merge-base.json').read_text())
with (out/'control/llvm-pie.elf').open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
assert digest==config['expected_pie_sha256'],'unchanged merge control differs from supplied base'
(out/'evidence/control-rebuild.json').write_text(json.dumps({'base_pie_rebuilt_byte_identical':True,'sha256':digest},indent=2)+'\n')
print('merge base control byte-identical: '+digest)
PY
echo 'The supplied base is preserved. Next run build-feature.sh with this work tree.'

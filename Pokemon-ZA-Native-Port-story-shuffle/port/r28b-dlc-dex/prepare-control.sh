#!/usr/bin/env bash
set -euo pipefail
renice 10 -p $$ >/dev/null
project='/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port'
base_tree=/home/tomer/ps5-za-native/r28a-play-final-20261030
work_tree=${1:?new absolute work tree required}
[[ $work_tree == /home/tomer/ps5-za-native/r28b-dlc-dex-* && ! -e $work_tree ]] || { echo 'work tree must be new and under the approved root' >&2; exit 2; }
[[ $(realpath -m -- "$work_tree") == "$work_tree" ]] || exit 2
pin() { [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]] || { echo "base SHA mismatch: $1" >&2; exit 2; }; }
pin "$base_tree/r28a/eboot.bin" 5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea
pin "$base_tree/r28a/llvm-pie.elf" 4cb7c2127f12f5f3aa700cb3301c21f6b1c214d464bac4449f43af56685eea85
pin "$base_tree/rando-dexcount/liblasgame-r28-dexcount.a" 1f0c586e721f93b80cd86b9b3675a18d95bca338952b5b3d01e7518bcc9a41cc
pin "$base_tree/rando-dexcount/za_dexcount.o" 207e7a1ad5d8f26a8d95673b7d6414df6af99f36201168c412a5c4df9b9ce06f
mkdir "$work_tree"
out=$work_tree/r28b
mkdir -p "$out/evidence" "$out/src" "$out/control"
exec > >(tee "$out/evidence/prepare-control.log") 2>&1
printf 'WORK_TREE=%s\n' "$work_tree"
date -u +'%Y-%m-%dT%H:%M:%SZ'
echo '== copy the immutable r28a inputs into the new tree'
for directory in source port inc rando-dexcount rando-dexcount-src; do cp -a --reflink=auto "$base_tree/$directory" "$work_tree/$directory"; done
mkdir -p "$work_tree/r28a"
cp -a --reflink=auto "$base_tree/r28a/objects" "$work_tree/r28a/objects"
cp -a --reflink=auto "$base_tree/r28a/src" "$work_tree/r28a/src"
cp -a --reflink=auto "$base_tree/r28a/liblasgame-r28.a" "$work_tree/r28a/"
cp -a --reflink=auto "$work_tree/r28a/objects" "$out/objects"
cp "$base_tree/r28a/evidence/runtime-inputs.txt" "$out/evidence/runtime-inputs.txt"
cp "$base_tree/r28a/evidence/link-inputs.txt" "$out/evidence/base-link-inputs.txt"
cp "$project/port/perf-r26/title_entry-r26p.c" "$out/src/"
cp "$project/port/runtime-texfix/verify-r28a.py" "$out/src/verify-r28a.py"
cp "$project/port/local-shader-r19/verify-registration.py" "$out/src/verify-registration.py"
mkdir -p "$out/shader-probe-r18"
cp "$project/port/shader-probe-r18/verify-image.py" "$out/shader-probe-r18/verify-image.py"
cp "$project/port/title/verify-image.py" "$out/src/verify-image.py"
cp "$project/port/r28b-dlc-dex/prepare-control.sh" "$out/src/"

echo '== prove that every linked copied input has identical content'
python3 - "$base_tree" "$work_tree" "$out" <<'PY'
from pathlib import Path
import hashlib,json,shlex,sys
base,work,out=map(Path,sys.argv[1:])
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
records=[]
for rel in (out/'evidence/runtime-inputs.txt').read_text().split():
    before=base/'source'/rel;after=work/'source'/rel
    records.append({'kind':'runtime','path':rel,'sha256':sha(before),'identical':sha(before)==sha(after)})
extra=(out/'evidence/base-link-inputs.txt').read_text().strip()
for token in shlex.split(extra):
    if token.endswith(('.o','.a')):
        before=Path(token)
        after=Path(str(before).replace(str(base)+'/',str(work)+'/',1)) if str(before).startswith(str(base)+'/') else before
        records.append({'kind':'extra','path':token,'copied_path':str(after),'sha256':sha(before),'identical':sha(before)==sha(after)})
assert all(row['identical'] for row in records)
mapped=extra.replace(str(base)+'/',str(work)+'/')
assert str(base)+'/' not in mapped
(out/'evidence/control-link-inputs.txt').write_text(mapped+'\n')
(out/'evidence/copied-inputs.json').write_text(json.dumps({'base':str(base),'work':str(work),'inputs':records,'all_identical':True},indent=2)+'\n')
print(json.dumps({'copied_inputs':len(records),'all_identical':True,'external_libraries_read_only':True}))
PY
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
export ZA_PS5_EXTRA_INPUTS="$(cat "$out/evidence/control-link-inputs.txt")"
mapfile -t relative_inputs < "$out/evidence/runtime-inputs.txt"
runtime=(); for relative in "${relative_inputs[@]}"; do runtime+=("$work_tree/source/$relative"); done
cd "$work_tree/source"
echo '== link an unchanged control PIE before any feature modification'
bash tools/ps5/link-title.sh "$out/control/llvm-pie.elf" "${runtime[@]}" "$work_tree/rando-dexcount/liblasgame-r28-dexcount.a"
control_sha=$(sha256sum "$out/control/llvm-pie.elf" | cut -d' ' -f1)
printf 'CONTROL_PIE_SHA256=%s\n' "$control_sha"
[[ $control_sha == 4cb7c2127f12f5f3aa700cb3301c21f6b1c214d464bac4449f43af56685eea85 ]] || { echo 'control PIE is not byte-identical to r28a' >&2; exit 2; }
echo '{"base_pie_rebuilt_byte_identical":true,"sha256":"4cb7c2127f12f5f3aa700cb3301c21f6b1c214d464bac4449f43af56685eea85"}' > "$out/evidence/control-rebuild.json"
echo 'control clone and byte-identical base relink verified'

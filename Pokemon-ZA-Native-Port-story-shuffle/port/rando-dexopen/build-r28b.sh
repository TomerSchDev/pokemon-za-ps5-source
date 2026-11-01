#!/usr/bin/env bash
# r28b-play = r28a-play FINAL (eboot 5c6777ec...) + rando-dexopen (ps5/apply-r28b.sh: main_287.o and main_115.o replaced
# in a COPY of r28a's game archive - the dexcount archive - plus za_dexopen.o on the link line). Everything else - the 64
# runtime objects (texfix inside), the title objects, za_dexcount.o, the link recipe - is r28a's file, byte for byte
# (verify-r28b.py base / inputs / image).
# A NEW tree, copied from r28a's final tree (which is only read). No console, NAS or save access.
# Usage (WSL): build-r28b.sh [r28a final tree] [new tree]
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
base=${1:-/home/tomer/ps5-za-native/r28a-play-final-20261030}
work=${2:-/home/tomer/ps5-za-native/r28b-play-20261030}
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
r28a_eboot=5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea
r28a_pie=4cb7c2127f12f5f3aa700cb3301c21f6b1c214d464bac4449f43af56685eea85
r28_ref=/home/tomer/ps5-za-native/r28-play-20261030/r28/llvm-pie.elf   # r28-play's PIE: the reference of r28a's image checks
[[ $(sha256sum "$base/r28a/eboot.bin" | cut -d' ' -f1) == "$r28a_eboot" ]] || { echo "r28a's eboot is not $r28a_eboot" >&2; exit 2; }
[[ $(sha256sum "$base/r28a/llvm-pie.elf" | cut -d' ' -f1) == "$r28a_pie" ]] || { echo "r28a's PIE is not $r28a_pie" >&2; exit 2; }
[[ -f $r28_ref ]] || { echo "missing $r28_ref" >&2; exit 2; }
[[ ! -e $work ]] || { echo "the new tree must be new: $work" >&2; exit 2; }
mkdir -p "$work"
out=$work/r28b
mkdir -p "$out/evidence" "$out/src"
exec > >(tee "$out/evidence/build.log") 2>&1
date -u +'started %Y-%m-%dT%H:%M:%SZ'

echo "== [r28b] 1. r28a's final tree, copied: runtime (texfix inside), title objects, the dexcount archive and object"
cp -a "$base/source" "$work/source"
cp -a "$base/port" "$work/port"
cp -a "$base/inc" "$work/inc"
cp -a "$base/r28a/objects" "$out/objects"
mkdir -p "$work/rando-dexcount"
cp -a "$base/rando-dexcount/liblasgame-r28-dexcount.a" "$base/rando-dexcount/za_dexcount.o" \
      "$base/rando-dexcount/dexcount-r28a-manifest.json" "$work/rando-dexcount/"
for f in SHA256SUMS.txt link-inputs.txt runtime-inputs.txt registration.json image-checks.json imports.json final-image.json \
         final-inputs.json dexcount-checks.json dexcount-HANDOFF.json self-inspection.txt source-SHA256SUMS.txt; do
    cp "$base/r28a/evidence/$f" "$out/evidence/r28a-$f"
done
cp "$root/build-r28b.sh" "$root/verify-r28b.py" "$out/src/"
# rando-dexopen is SNAPSHOTTED before it runs (bash reads a script as it executes it: an edit of the live folder while
# the build runs would corrupt the run); the snapshot keeps the folder's layout (apply-r28b.sh finds its sources through
# ps5/..), its hashes are recorded, and the snapshot is what runs
snap=$work/rando-dexopen-src
mkdir -p "$snap/ps5" "$snap/test"
cp "$root/ps5/apply-r28b.sh" "$root/ps5/compare_ar.py" "$snap/ps5/"
cp "$root/za_dexopen.c" "$root/za_dexopen.h" "$root/prepare-dexopen-hooks.py" "$snap/"
cp "$root"/test/*.c "$root"/test/*.py "$root"/test/*.sh "$snap/test/"
mkdir -p "$out/src/rando-dexopen"
cp -a "$snap/." "$out/src/rando-dexopen/"
(cd "$out/src" && find . -type f | sort | xargs sha256sum) > "$out/evidence/source-SHA256SUMS.txt"
grep 'rando-dexopen/' "$out/evidence/source-SHA256SUMS.txt" | tee "$out/evidence/dexopen-sources.sha256"
python3 "$root/verify-r28b.py" base "$base" "$work" "$out/evidence"

echo "== [r28b] 2. rando-dexopen on top of r28a's game archive (the snapshot's script, its own checks)"
dexout=$work/rando-dexopen
bash "$snap/ps5/apply-r28b.sh" "$work" "$dexout"
cp -r "$dexout/evidence" "$out/evidence/dexopen"
cp "$dexout/dexopen-r28b-manifest.json" "$out/evidence/dexopen-r28b-manifest.json"
archive=$dexout/liblasgame-r28-dexopen.a
[[ -f $archive && -f $dexout/za_dexopen.o ]] || { echo "dexopen outputs missing" >&2; exit 2; }
python3 "$root/verify-r28b.py" dexopen "$dexout" "$work/rando-dexcount/liblasgame-r28-dexcount.a" "$out/evidence" "$base/r28a/llvm-pie.elf"

echo "== [r28b] 3. link: r28a's recipe and runtime list, its objects and za_dexcount.o, the dexopen archive and object"
mapfile -t relinputs < "$out/evidence/r28a-runtime-inputs.txt"
runtime=()
for p in "${relinputs[@]}"; do [[ -f $work/source/$p ]] || { echo "missing $work/source/$p" >&2; exit 2; }; runtime+=("$work/source/$p"); done
cp "$out/evidence/r28a-runtime-inputs.txt" "$out/evidence/runtime-inputs.txt"
extra=$(cat "$out/evidence/r28a-link-inputs.txt")
extra=${extra//"$base/r28a/objects/"/"$out/objects/"}
extra=${extra//"$base/rando-dexcount/"/"$work/rando-dexcount/"}
export ZA_PS5_EXTRA_INPUTS="$extra $dexout/za_dexopen.o"
printf '%s\n' "$ZA_PS5_EXTRA_INPUTS" > "$out/evidence/link-inputs.txt"
python3 "$root/verify-r28b.py" inputs "$base" "$work" "$dexout" "$out/evidence"
cd "$work/source"
bash tools/ps5/link-title.sh "$out/llvm-pie.elf" "${runtime[@]}" "$archive"

echo "== [r28b] 4. image checks: r28-play's PIE (r28a's own checks, reused as they are) and r28a's PIE (dexopen)"
python3 "$project/port/local-shader-r19/verify-registration.py" "$r28_ref" "$out/llvm-pie.elf" > "$out/evidence/registration.json"
python3 "$project/port/runtime-texfix/verify-r28a.py" image "$r28_ref" "$out/llvm-pie.elf" "$out/evidence" "$project"
python3 "$root/verify-r28b.py" image "$base/r28a/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence"
nm=/usr/lib/llvm-21/bin/llvm-nm
"$nm" --defined-only "$out/llvm-pie.elf" > "$out/evidence/defined-symbols.txt"
"$sdk/bin/llvm-strip" --strip-debug -o "$out/title-stripped.elf" "$out/llvm-pie.elf"
tool=$PS5_VULKAN/build/host/ps5-native-tool
"$tool" link --in "$out/title-stripped.elf" --out "$out/eboot.elf" --stub-dir "$sdk/target/lib" \
    --stub "$out/ps5-link/stubs/libSceAgc.so" --stub "$out/ps5-link/stubs/libSceAgcDriver.so" \
    --module-sdk 0x02000009 --companion-sdk 0x08050001 --file-name eboot.elf
python3 "$project/port/title/verify-image.py" "$out/title-stripped.elf" "$out/eboot.elf" "$out/evidence/defined-symbols.txt" \
    > "$out/evidence/image-preservation.json"
"$tool" self --sign --in "$out/eboot.elf" --out "$out/eboot.bin" --magic 0x1D3D154F
"$tool" self --inspect --file "$out/eboot.bin" > "$out/evidence/self-inspection.txt"
diff <(sed 's/[0-9a-f]\{64\}/HASH/g; s/[0-9]\{6,\}/N/g' "$out/evidence/r28a-self-inspection.txt") \
     <(sed 's/[0-9a-f]\{64\}/HASH/g; s/[0-9]\{6,\}/N/g' "$out/evidence/self-inspection.txt") > "$out/evidence/self-inspection-vs-r28a.diff" || true
sha256sum "$out/eboot.bin" "$out/llvm-pie.elf" "$out/title-stripped.elf" "$archive" "$dexout/za_dexopen.o" | tee "$out/evidence/SHA256SUMS.txt"
date -u +'finished %Y-%m-%dT%H:%M:%SZ'
echo "r28b-play built and verified offline; no console access performed"

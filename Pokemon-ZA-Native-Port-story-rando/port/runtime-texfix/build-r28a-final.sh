#!/usr/bin/env bash
# r28a-play FINAL = the r28a texfix candidate (build-r28a-candidate.sh: r28-play + the texture-lifetime fix in four
# runtime objects) + rando-dexcount (port/rando-dexcount/ps5/apply-r28a.sh: patched game units in a copy of the game
# archive, plus za_dexcount.o on the link line). Everything else - the runtime objects, the title objects, the link
# recipe - is the candidate's file, byte for byte (verify-r28a.py final).
# A NEW tree, copied from the candidate's (which is only read). No console, NAS or save access.
# Usage (WSL): build-r28a-final.sh [candidate tree] [final tree]
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
cand=${1:-/home/tomer/ps5-za-native/r28a-play-20261030}
work=${2:-/home/tomer/ps5-za-native/r28a-play-final-20261030}
dex=$project/port/rando-dexcount/ps5
handoff=${HANDOFF_OVERRIDE:-$dex/HANDOFF.json}  # (HANDOFF_OVERRIDE: dry runs only)
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
cand_eboot=d87b3a043a73a680f097463b896355f6a8ddd60c283abc6af53d1bdcd1888c7c
[[ -f $handoff ]] || { echo "missing $handoff" >&2; exit 2; }
[[ $(sha256sum "$cand/r28a/eboot.bin" | cut -d' ' -f1) == "$cand_eboot" ]] || { echo "the candidate's eboot is not $cand_eboot" >&2; exit 2; }
[[ ! -e $work ]] || { echo "final tree must be new: $work" >&2; exit 2; }
mkdir -p "$work"
out=$work/r28a
mkdir -p "$out/evidence" "$out/src"
exec > >(tee "$out/evidence/build.log") 2>&1
date -u +'started %Y-%m-%dT%H:%M:%SZ'

echo "== [final] 1. the candidate tree, copied (its runtime objects carry the texfix)"
cp -a "$cand/source" "$work/source"
cp -a "$cand/port" "$work/port"
cp -a "$cand/inc" "$work/inc"
cp -a "$cand/r28a/objects" "$out/objects"
cp -a "$cand/r28a/liblasgame-r28.a" "$out/liblasgame-r28.a"
cp -a "$cand/r28a/src/." "$out/src/"
for f in link-inputs.txt runtime-inputs.txt SHA256SUMS.txt registration.json control.txt apply.txt patched-objects.sha256 \
         runtime-texfix.patch inputs.json image-checks.json r28-SHA256SUMS.txt; do
    cp "$cand/r28a/evidence/$f" "$out/evidence/candidate-$f"
done
cp "$handoff" "$out/evidence/dexcount-HANDOFF.json"
cp "$root/build-r28a-final.sh" "$root/verify-r28a.py" "$out/src/"
# rando-dexcount is SNAPSHOTTED before it runs (bash reads a script as it executes it: an edit of the live folder
# while the build runs would corrupt the run) - the snapshot keeps the folder's layout (apply-r28a.sh finds its sources
# through ps5/..), its sources' hashes are recorded, and the snapshot is what runs
dexsnap=$work/rando-dexcount-src
mkdir -p "$dexsnap/ps5"
cp "$dex/apply-r28a.sh" "$dex/compare_ar.py" "$dexsnap/ps5/"
cp "$dex/../za_dexcount.c" "$dex/../za_dexcount.h" "$dex/../prepare-dexcount-hooks.py" "$dexsnap/"
mkdir -p "$out/src/rando-dexcount"
cp -a "$dexsnap/." "$out/src/rando-dexcount/"
(cd "$out/src" && find . -type f | sort | xargs sha256sum) > "$out/evidence/source-SHA256SUMS.txt"
grep 'rando-dexcount/' "$out/evidence/source-SHA256SUMS.txt" | tee "$out/evidence/dexcount-sources.sha256"
python3 "$root/verify-r28a.py" handoff-sources "$handoff" "$dexsnap"  # (the snapshot is what the HANDOFF pins)

echo "== [final] 2. rando-dexcount on top of the candidate's game archive (the other agent's script, its own checks)"
dexout=$work/rando-dexcount
BASE_ARCHIVE="$out/liblasgame-r28.a" bash "$dexsnap/ps5/apply-r28a.sh" "$work" "$dexout"
cp -r "$dexout/evidence" "$out/evidence/dexcount"
cp "$dexout/dexcount-r28a-manifest.json" "$out/evidence/dexcount-r28a-manifest.json"
archive=$dexout/liblasgame-r28-dexcount.a
[[ -f $archive && -f $dexout/za_dexcount.o ]] || { echo "dexcount outputs missing" >&2; exit 2; }
python3 "$root/verify-r28a.py" dexcount "$handoff" "$dexout" "$out/liblasgame-r28.a" "$out/evidence" "$cand/r28a/llvm-pie.elf"

echo "== [final] 3. link: the candidate's recipe and runtime list, its objects, the dexcount archive and object"
mapfile -t relinputs < "$out/evidence/candidate-runtime-inputs.txt"
runtime=()
for p in "${relinputs[@]}"; do [[ -f $work/source/$p ]] || { echo "missing $work/source/$p" >&2; exit 2; }; runtime+=("$work/source/$p"); done
cp "$out/evidence/candidate-runtime-inputs.txt" "$out/evidence/runtime-inputs.txt"
extra=$(cat "$out/evidence/candidate-link-inputs.txt")
extra=${extra//"$cand/r28a/objects/"/"$out/objects/"}
export ZA_PS5_EXTRA_INPUTS="$extra $dexout/za_dexcount.o"
printf '%s\n' "$ZA_PS5_EXTRA_INPUTS" > "$out/evidence/link-inputs.txt"
python3 "$root/verify-r28a.py" final-inputs "$cand" "$work" "$dexout" "$out/evidence"
cd "$work/source"
bash tools/ps5/link-title.sh "$out/llvm-pie.elf" "${runtime[@]}" "$archive"

echo "== [final] 4. image checks against r28-play's PIE (the candidate's checks) and the candidate's PIE (dexcount)"
ref=/home/tomer/ps5-za-native/r28-play-20261030/r28/llvm-pie.elf
python3 "$project/port/local-shader-r19/verify-registration.py" "$ref" "$out/llvm-pie.elf" > "$out/evidence/registration.json"
python3 "$root/verify-r28a.py" image "$ref" "$out/llvm-pie.elf" "$out/evidence" "$project"
python3 "$root/verify-r28a.py" final-image "$handoff" "$cand/r28a/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence"
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
diff <(sed 's/[0-9a-f]\{64\}/HASH/g; s/[0-9]\{6,\}/N/g' "$cand/r28a/evidence/self-inspection.txt") \
     <(sed 's/[0-9a-f]\{64\}/HASH/g; s/[0-9]\{6,\}/N/g' "$out/evidence/self-inspection.txt") > "$out/evidence/self-inspection-vs-candidate.diff" || true
sha256sum "$out/eboot.bin" "$out/llvm-pie.elf" "$archive" "$dexout/za_dexcount.o" | tee "$out/evidence/SHA256SUMS.txt"
date -u +'finished %Y-%m-%dT%H:%M:%SZ'
echo "r28a-play final built and verified offline; no console access performed"

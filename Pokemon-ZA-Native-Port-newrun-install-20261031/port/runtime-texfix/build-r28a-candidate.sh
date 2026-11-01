#!/usr/bin/env bash
# r28a-play (texfix CANDIDATE) = r28-play (eboot 65f6745f...) + the texture-lifetime fix (port/runtime-texfix) in four
# runtime objects: nvn/objects.o, nvn/vulkan/textures.o, nvn/vulkan/exec.o, nvn/vulkan/device.o. Every other link input
# - the other 59 runtime objects, the title objects, the game archive, the libraries, the link recipe - is r28-play's
# own file, checked byte for byte (verify-r28a.py inputs). The four are compiled with the command that, on the unpatched
# sources, reproduces r28-play's objects byte for byte (checked first: step 2).
# A NEW work tree; r28-play's (/home/tomer/ps5-za-native/r28-play-20261030) is only read. No console, NAS or save access.
# Usage (WSL): build-r28a-candidate.sh [work tree]   (default /home/tomer/ps5-za-native/r28a-play-20261030)
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
prev=/home/tomer/ps5-za-native/r28-play-20261030  # r28-play
r26=/home/tomer/ps5-za-native/perf-r26-20261029   # where r28-play's runtime objects were compiled (their debug paths)
work=${1:-/home/tomer/ps5-za-native/r28a-play-20261030}
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
r28_eboot=65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568
r28_pie=0570bec994a7cbe9512dacb4a6fa8e3bc0340ef3570dd73edf346772928d8288
units=(nvn/objects nvn/vulkan/textures nvn/vulkan/exec nvn/vulkan/device)
[[ $(sha256sum "$prev/r28/eboot.bin" | cut -d' ' -f1) == "$r28_eboot" ]] || { echo "r28-play's eboot.bin is not $r28_eboot" >&2; exit 2; }
[[ $(sha256sum "$prev/r28/llvm-pie.elf" | cut -d' ' -f1) == "$r28_pie" ]] || { echo "r28-play's PIE is not $r28_pie" >&2; exit 2; }
[[ ! -e $work ]] || { echo "work tree must be new: $work" >&2; exit 2; }
mkdir -p "$work"
out=$work/r28a
mkdir -p "$out/evidence" "$out/control" "$out/objects" "$out/src"
exec > >(tee "$out/evidence/build.log") 2>&1
date -u +'started %Y-%m-%dT%H:%M:%SZ'

echo "== [r28a] 1. r28-play's inputs, copied"
cp -a "$prev/source" "$work/source"
cp -a "$prev/port" "$work/port"
cp -a "$prev/inc" "$work/inc"
cp -a "$prev/r28/objects/." "$out/objects/"
cp -a "$prev/r28/liblasgame-r28.a" "$out/liblasgame-r28.a"
for f in link-inputs.txt runtime-inputs.txt SHA256SUMS.txt registration.json; do cp "$prev/r28/evidence/$f" "$out/evidence/r28-$f"; done
cp -r "$root/src" "$root/apply-runtime-texfix.py" "$root/verify-r28a.py" "$root/build-r28a-candidate.sh" "$out/src/"
(cd "$out/src" && find . -type f | sort | xargs sha256sum) > "$out/evidence/source-SHA256SUMS.txt"

echo "== [r28a] 2. the compile command reproduces r28-play's four runtime objects from the unpatched sources"
deps=(-I"$work/port/sdl3-shim/include" -I"$work/port/shaderc-cache/include" -I"$work/inc" -I"$project/port/observer-r17")
cc_rt() {  # the Makefile's (PLATFORM=ps5) $(CC) $(RTFLAGS) -c, PS5_DEPS_INC as r26 built them, its paths by prefix map
    /usr/bin/clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default -isysroot "$sdk" \
        -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" -fno-stack-protector -fno-plt -femulated-tls \
        -fdenormal-fp-math=ieee -O2 -g -fno-strict-aliasing -Wall -Wno-unused-function -Iruntime -Iruntime/nvn \
        -I/home/tomer/ps5-za-native/PS5_Mesa/include "${deps[@]}" -Ithird_party/ps5-stubs/include -DZA_PS5 \
        -DLARECOMP_STATIC_GAMELIB -Wno-format -ffile-prefix-map="$work=$r26" -c "$1" -o "$2"
}
cd "$work/source"
: > "$out/evidence/control.txt"
for u in "${units[@]}"; do
    b=$(basename "$u")
    cc_rt "runtime/$u.c" "$out/control/$b.o"
    cmp -s "$out/control/$b.o" "$prev/source/build/ps5/rt/$u.o" || { echo "control compile differs from r28-play: $u.o" >&2; exit 2; }
    echo "$u.o: unpatched source + this command = r28-play's object, byte for byte ($(sha256sum < "$out/control/$b.o" | cut -c1-16))" \
        | tee -a "$out/evidence/control.txt"
done

echo "== [r28a] 3. the fix, applied to this tree's runtime (port/runtime-texfix/apply-runtime-texfix.py)"
python3 "$root/apply-runtime-texfix.py" "$work/source/runtime" | tee "$out/evidence/apply.txt"
(diff -ruN "$prev/source/runtime" "$work/source/runtime" || true) \
    | sed -e "s|$prev/source/|a/|g" -e "s|$work/source/|b/|g" > "$out/evidence/runtime-texfix.patch"
grep -c '^diff -ruN' "$out/evidence/runtime-texfix.patch" | sed 's/^/files in the patch: /'

echo "== [r28a] 4. the four objects, patched (the same command; no warnings allowed)"
for u in "${units[@]}"; do
    cc_rt "runtime/$u.c" "build/ps5/rt/$u.o" 2> "$out/evidence/compile-$(basename "$u").log"
    if [[ -s $out/evidence/compile-$(basename "$u").log ]]; then cat "$out/evidence/compile-$(basename "$u").log"; echo "warnings in $u" >&2; exit 2; fi
done
(for u in "${units[@]}"; do sha256sum "build/ps5/rt/$u.o"; done) | tee "$out/evidence/patched-objects.sha256"

echo "== [r28a] 5. link: r28-play's recipe, runtime list and inputs"
mapfile -t relinputs < "$out/evidence/r28-runtime-inputs.txt"
runtime=()
for p in "${relinputs[@]}"; do [[ -f $p ]] || { echo "missing $p" >&2; exit 2; }; runtime+=("$work/source/$p"); done
extra=$(cat "$out/evidence/r28-link-inputs.txt")
extra=${extra//"$prev/r28/objects/"/"$out/objects/"}
export ZA_PS5_EXTRA_INPUTS="$extra"
printf '%s\n' "$ZA_PS5_EXTRA_INPUTS" > "$out/evidence/link-inputs.txt"
cp "$out/evidence/r28-runtime-inputs.txt" "$out/evidence/runtime-inputs.txt"
python3 "$root/verify-r28a.py" inputs "$prev" "$work" "$out/evidence"
bash tools/ps5/link-title.sh "$out/llvm-pie.elf" "${runtime[@]}" "$out/liblasgame-r28.a"

echo "== [r28a] 6. image checks against r28-play's PIE"
ref=$prev/r28/llvm-pie.elf
python3 "$project/port/local-shader-r19/verify-registration.py" "$ref" "$out/llvm-pie.elf" > "$out/evidence/registration.json"
python3 "$root/verify-r28a.py" image "$ref" "$out/llvm-pie.elf" "$out/evidence" "$project"
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
diff <(sed 's/[0-9a-f]\{64\}/HASH/g; s/[0-9]\{6,\}/N/g' "$prev/r28/evidence/self-inspection.txt") \
     <(sed 's/[0-9a-f]\{64\}/HASH/g; s/[0-9]\{6,\}/N/g' "$out/evidence/self-inspection.txt") > "$out/evidence/self-inspection-vs-r28.diff" || true
sha256sum "$out/eboot.bin" "$out/llvm-pie.elf" | tee "$out/evidence/SHA256SUMS.txt"
date -u +'finished %Y-%m-%dT%H:%M:%SZ'
echo "r28a texfix candidate built and verified offline; no console access performed"

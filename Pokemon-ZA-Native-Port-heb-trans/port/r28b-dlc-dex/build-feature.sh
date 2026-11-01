#!/usr/bin/env bash
# Add the early DLC dex flag hook to a copied and byte-identically relinked r28a tree.
# Inputs are read only; every product is written in the prepared new work tree.
set -euo pipefail
renice 10 -p $$ >/dev/null
project='/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port'
work_tree=${1:?prepared new r28b work tree required}
[[ $work_tree == /home/tomer/ps5-za-native/r28b-dlc-dex-* && -f $work_tree/r28b/evidence/control-rebuild.json ]] || { echo 'prepare-control.sh must pass first' >&2; exit 2; }
out=$work_tree/r28b
[[ ! -e $out/feature-started ]] || { echo 'feature output already started: use a fresh work tree' >&2; exit 2; }
[[ -f $project/port/dlc-dex-unlock/prepare_dlc_dex_hook.py && -f $project/port/dlc-dex-unlock/za_dlc_dex_unlock.c ]] || { echo 'feature sources not ready' >&2; exit 2; }
touch "$out/feature-started"
mkdir -p "$out/feature-src" "$out/game-objects" "$out/gen"
cp -a "$project/port/dlc-dex-unlock/." "$out/feature-src/"
cp "$project/port/r28b-dlc-dex/build-feature.sh" "$out/src/"
cp "$project/port/r28b-dlc-dex/verify-feature-image.py" "$out/src/"
exec > >(tee "$out/evidence/feature-build.log") 2>&1
date -u +'%Y-%m-%dT%H:%M:%SZ'
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
game=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025
ar=/usr/lib/llvm-21/bin/llvm-ar
nm=/usr/lib/llvm-21/bin/llvm-nm
base_archive=$work_tree/rando-dexcount/liblasgame-r28-dexcount.a
[[ ! -f $out/evidence/merge-base.json ]] || base_archive=$out/base/liblasgame-base.a
compare_ar=$work_tree/rando-dexcount-src/ps5/compare_ar.py
[[ -f $compare_ar ]] || compare_ar=$out/src/compare_ar.py
archive=$out/liblasgame-r28b-dlc-dex.a
echo '== snapshot hashes'
(cd "$out/feature-src"; find . -type f ! -path '*/__pycache__/*' ! -path '*/evidence/*' -print0 | sort -z | xargs -0 sha256sum) > "$out/evidence/feature-source-SHA256SUMS.txt"
echo '== guarded source patch'
python3 "$out/feature-src/prepare_dlc_dex_hook.py" --aot "$game/aot" --nso "$game/game/exefs/main" --out "$out/gen"
cc_unit() {
 /usr/bin/clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default \
  -isysroot "$sdk" -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" \
  -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
  -O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label \
  -fvisibility=hidden -Iruntime -march=x86-64-v3 -DZA_PS5 -c "$1" -o "$2"
}
cd "$work_tree/source"
echo '== unchanged main_287 control must match the archive member byte-for-byte'
cc_unit "$game/aot/main/main_287.c" "$out/control/main_287.o"
"$ar" p "$base_archive" main_287.o > "$out/control/main_287.member.o"
cmp -s "$out/control/main_287.o" "$out/control/main_287.member.o" || { echo 'main_287 base differs: merge its other changes at source level first' >&2; exit 2; }
cc_unit "$out/gen/main_287.c" "$out/game-objects/main_287.o"
"$nm" --defined-only "$out/control/main_287.o" | awk '{print $NF}' | sort > "$out/evidence/main_287.control.defined"
"$nm" --defined-only "$out/game-objects/main_287.o" | awk '{print $NF}' | sort > "$out/evidence/main_287.patched.defined"
cmp -s "$out/evidence/main_287.control.defined" "$out/evidence/main_287.patched.defined" || { echo 'main_287 defined symbols changed' >&2; exit 2; }
comm -13 <("$nm" -u "$out/control/main_287.o" | awk '{print $NF}' | sort) <("$nm" -u "$out/game-objects/main_287.o" | awk '{print $NF}' | sort) > "$out/evidence/main_287.new-imports.txt"
[[ $(cat "$out/evidence/main_287.new-imports.txt") == za_dlc_dex_unlock_pump ]] || { echo 'unexpected added unit imports' >&2; exit 2; }
echo '== helper object'
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
  -DZA_PS5 -DGUEST_VOLATILE -DZA_DLC_DEX_TRACE=1 -DZA_DLC_DEX_KLOG=1 -Iruntime -I"$out/feature-src" \
  -c "$out/feature-src/za_dlc_dex_unlock.c" -o "$out/za_dlc_dex_unlock.o"
"$nm" -u "$out/za_dlc_dex_unlock.o" > "$out/evidence/helper.imports.txt"
echo '== replace only the one new game unit in the already dexcount-patched archive'
cp --reflink=auto "$base_archive" "$archive"
(cd "$out/game-objects"; "$ar" rcs "$archive" main_287.o)
python3 "$compare_ar" "$base_archive" "$archive" main_287.o > "$out/evidence/archive-vs-base.json"
if [[ -f $work_tree/r28a/liblasgame-r28.a ]]; then
 python3 "$compare_ar" "$work_tree/r28a/liblasgame-r28.a" "$archive" main_261.o main_287.o main_310.o > "$out/evidence/archive-vs-r28.json"
fi
echo '== link the preserved base inputs and append the new helper'
export ZA_PS5_EXTRA_INPUTS="$(cat "$out/evidence/control-link-inputs.txt") $out/za_dlc_dex_unlock.o"
printf '%s\n' "$ZA_PS5_EXTRA_INPUTS" > "$out/evidence/link-inputs.txt"
mapfile -t relative_inputs < "$out/evidence/runtime-inputs.txt"
runtime=(); for relative in "${relative_inputs[@]}"; do runtime+=("$work_tree/source/$relative"); done
bash tools/ps5/link-title.sh "$out/llvm-pie.elf" "${runtime[@]}" "$archive"
echo '== preserve imports, registrations, texfix, timing, items, Hebrew, money and dexcount'
r28_reference=/home/tomer/ps5-za-native/r28-play-20261030/r28/llvm-pie.elf
python3 "$out/src/verify-registration.py" "$r28_reference" "$out/llvm-pie.elf" > "$out/evidence/registration.json"
python3 "$out/src/verify-r28a.py" image "$r28_reference" "$out/llvm-pie.elf" "$out/evidence" "$project"
python3 "$out/src/verify-r28a.py" final-image "$project/port/rando-dexcount/ps5/HANDOFF.json" "$out/control/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence"
python3 "$out/src/verify-feature-image.py" "$out/control/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence"
echo '== ELF-to-SELF preservation'
"$nm" --defined-only "$out/llvm-pie.elf" > "$out/evidence/defined-symbols.txt"
"$sdk/bin/llvm-strip" --strip-debug -o "$out/title-stripped.elf" "$out/llvm-pie.elf"
tool=$PS5_VULKAN/build/host/ps5-native-tool
"$tool" link --in "$out/title-stripped.elf" --out "$out/eboot.elf" --stub-dir "$sdk/target/lib" \
 --stub "$out/ps5-link/stubs/libSceAgc.so" --stub "$out/ps5-link/stubs/libSceAgcDriver.so" \
 --module-sdk 0x02000009 --companion-sdk 0x08050001 --file-name eboot.elf
python3 "$out/src/verify-image.py" "$out/title-stripped.elf" "$out/eboot.elf" "$out/evidence/defined-symbols.txt" > "$out/evidence/image-preservation.json"
"$tool" self --sign --in "$out/eboot.elf" --out "$out/eboot.bin" --magic 0x1D3D154F
"$tool" self --inspect --file "$out/eboot.bin" > "$out/evidence/self-inspection.txt"
sha256sum "$out/eboot.bin" "$out/llvm-pie.elf" "$archive" "$out/za_dlc_dex_unlock.o" > "$out/evidence/SHA256SUMS.txt"
cat "$out/evidence/SHA256SUMS.txt"
echo 'r28b image built and statically verified offline; no in-game test or console access'

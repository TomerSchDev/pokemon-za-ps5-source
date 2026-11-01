#!/usr/bin/env bash
set -euo pipefail
renice 10 -p $$ >/dev/null
project='/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port'
work_tree=${1:?work tree required}
variant=${2:-r28b}
[[ $work_tree == /home/tomer/ps5-za-native/r28b-dlc-dex-* && ( $variant == r28b || $variant == r28b-music ) ]] || exit 2
base_out=$work_tree/r28b
out=$work_tree/$variant
[[ -f $out/llvm-pie.elf ]] || exit 2
mkdir -p "$base_out/shader-probe-r18"
cp "$project/port/shader-probe-r18/verify-image.py" "$base_out/shader-probe-r18/verify-image.py"
cp "$project/port/r28b-dlc-dex/verify-feature-image.py" "$base_out/src/verify-feature-image.py"
cp "$project/port/r28b-dlc-dex/finish-image.sh" "$out/src/"
exec > >(tee "$out/evidence/finish-image.log") 2>&1
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
r28_reference=/home/tomer/ps5-za-native/r28-play-20261030/r28/llvm-pie.elf
echo '== registration, legacy linked calls, dexcount and new feature native calls'
python3 "$base_out/src/verify-registration.py" "$r28_reference" "$out/llvm-pie.elf" > "$out/evidence/registration.json"
python3 "$base_out/src/verify-r28a.py" image "$r28_reference" "$out/llvm-pie.elf" "$out/evidence" "$project"
python3 "$base_out/src/verify-r28a.py" final-image "$project/port/rando-dexcount/ps5/HANDOFF.json" "$base_out/control/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence"
python3 "$base_out/src/verify-feature-image.py" "$base_out/control/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence"
if [[ $variant == r28b-music ]]; then
 python3 "$out/src/verify-r29.py" image "$base_out/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence" "$project" fcef0023680e21a305b962d9962bcdafe518d0c9c899d50f841692f9d6471c70 r28
fi
echo '== ELF-to-SELF preservation'
nm=/usr/lib/llvm-21/bin/llvm-nm
"$nm" --defined-only "$out/llvm-pie.elf" > "$out/evidence/defined-symbols.txt"
"$sdk/bin/llvm-strip" --strip-debug -o "$out/title-stripped.elf" "$out/llvm-pie.elf"
tool=$PS5_VULKAN/build/host/ps5-native-tool
"$tool" link --in "$out/title-stripped.elf" --out "$out/eboot.elf" --stub-dir "$sdk/target/lib" \
 --stub "$out/ps5-link/stubs/libSceAgc.so" --stub "$out/ps5-link/stubs/libSceAgcDriver.so" \
 --module-sdk 0x02000009 --companion-sdk 0x08050001 --file-name eboot.elf
python3 "$base_out/src/verify-image.py" "$out/title-stripped.elf" "$out/eboot.elf" "$out/evidence/defined-symbols.txt" > "$out/evidence/image-preservation.json"
"$tool" self --sign --in "$out/eboot.elf" --out "$out/eboot.bin" --magic 0x1D3D154F
"$tool" self --inspect --file "$out/eboot.bin" > "$out/evidence/self-inspection.txt"
sha256sum "$out/eboot.bin" "$out/llvm-pie.elf" > "$out/evidence/SHA256SUMS.txt"
cat "$out/evidence/SHA256SUMS.txt"
echo "$variant image built and statically verified offline; no in-game test or console access"

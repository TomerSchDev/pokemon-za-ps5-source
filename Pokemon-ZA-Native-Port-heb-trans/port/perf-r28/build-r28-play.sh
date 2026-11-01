#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
proof=$(realpath -e -- "${1:?PC proof required}")
prev=/home/tomer/ps5-za-native/r27b-play-20261029
work=/home/tomer/ps5-za-native/r28-play-20261030
lab=$project/../hebrew-lab
own=$project/port/cheats-r28
game=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
python3 "$root/verify-r28.py" gate "$proof" "$own"
[[ $(sha256sum "$prev/money-r27/liblasgame-r27.a" | cut -d' ' -f1) == 0453e8b047b14bee5ce5024094750f9042eb95bd1475b736ca9ae4c95af46d83 ]]
[[ $(sha256sum "$lab/trial/build-r5/eboot.bin" | cut -d' ' -f1) == cd1eb5f6044ab99d56161c6009d6d0972df475d269c0522dee650fab31d4f618 ]]
[[ ! -e $work ]] || { echo 'Work copy must be new'; exit 2; }
mkdir "$work"
cp -a --reflink=auto "$prev/." "$work/"
out=$work/r28
mkdir -p "$out/src" "$out/objects" "$out/evidence" "$out/control"
cp "$root/src/"* "$out/src/"
cp "$own/"{za_items.c,za_items.h,items.inc} "$out/src/"
cp "$lab/trial/build-r5/src/cheats-hebrew.cpp" "$out/src/"
cp "$project/port/perf-r26/title_entry-r26p.c" "$out/src/"
cp "$root/"{build-r28-play.sh,verify-r28.py} "$out/src/"
sha256sum "$out/src/"* > "$out/evidence/source-SHA256SUMS.txt"
cp "$proof" "$out/evidence/pc-proof.json"
exec > >(tee "$out/evidence/build.log") 2>&1
cp -a "$prev/objects-r27/." "$out/objects/"
cp "$lab/trial/build-r5/objects/"{hebrew_trial.o,hebrew_install.o} "$out/objects/"
python3 "$own/prepare-items-hooks.py" "$game/aot/main" "$game/game/exefs/main" "$out/items"
python3 "$project/port/cheats-r27/prepare-money-hooks.py" "$game/aot/main" "$game/game/exefs/main" "$out/control-money" >/dev/null
units=(main_097 main_220 main_333 main_339 main_384 main_1035)
ar=/usr/lib/llvm-21/bin/llvm-ar
base=$prev/money-r27/liblasgame-r27.a
archive=$out/liblasgame-r28.a
cd "$work/source"
cc_unit(){
 /usr/bin/clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default \
  -isysroot "$sdk" -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" \
  -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
  -O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label \
  -fvisibility=hidden -Iruntime -march=x86-64-v3 -DZA_PS5 -c "$1" -o "$2"
}
for u in "${units[@]}"; do
 if grep -qw "main/$u" build/ps5/gen/giants.mk; then echo 'Refusing giant O1';exit 2;fi
 source=$game/aot/main/$u.c
 [[ $u != main_220 && $u != main_384 && $u != main_1035 ]] || source=$out/control-money/$u.c
 cc_unit "$source" "$out/control/$u.o"
 "$ar" p "$base" "$u.o" > "$out/control/$u.member.o"
 cmp -s "$out/control/$u.o" "$out/control/$u.member.o" || { echo "Control mismatch: $u";exit 2; }
 cc_unit "$out/items/$u.c" "$out/items/$u.o"
 echo "Verified control and compiled $u"
done
cp --reflink=auto "$base" "$archive"
objects=();for u in "${units[@]}";do objects+=("$out/items/$u.o");done
"$ar" rcs "$archive" "${objects[@]}"
python3 "$root/verify-r28.py" archive "$base" "$archive" "$out/evidence/archive.json" "$project"
cc(){ sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
mesa=/home/tomer/ps5-za-native/PS5_Mesa/include
deps=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib
incs=(-I"$out/src" -I"$project/port/rando-v2" -I"$project/port/cheats-r27" -I"$work/port/sdl3-shim/include" -I"$mesa"
 -I"$work/source/runtime" -I"$project/port/title" -I"$work/objects-r27" -I"$project/port/randomizer"
 -I"$project/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include")
cc -std=c++20 -fno-exceptions -fno-rtti "${flags[@]}" "${incs[@]}" -DZA_MONEY_HOOK=1 -c "$out/src/cheats-hebrew.cpp" -o "$out/control/cheats.o"
cmp -s "$out/control/cheats.o" "$lab/trial/build-r5/objects/cheats.o" || { echo 'Hebrew menu control mismatch';exit 2; }
cc -std=c++20 -fno-exceptions -fno-rtti "${flags[@]}" "${incs[@]}" -DZA_MONEY_HOOK=1 -c "$out/src/cheats-r28.cpp" -o "$out/objects/cheats.o"
cc -std=c11 "${flags[@]}" "${incs[@]}" -DGUEST_VOLATILE -fno-strict-aliasing -c "$out/src/za_items.c" -o "$out/objects/za_items.o"
titleincs=(-I"$project/port/perf-r26" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title")
cc -std=c11 "${flags[@]}" "${titleincs[@]}" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r27b-play"' -c "$out/src/title_entry-r26p.c" -o "$out/control/title_entry.o"
cmp -s "$out/control/title_entry.o" "$prev/objects-r27/title_entry.o" || { echo 'Title control mismatch';exit 2; }
cc -std=c11 "${flags[@]}" "${titleincs[@]}" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r28-play"' -c "$out/src/title_entry-r26p.c" -o "$out/objects/title_entry.o"
make -s -f "$lab/trial/runtime-inputs.mk" PLATFORM=ps5 print-hebrew-inputs > "$out/evidence/runtime-inputs.txt"
mapfile -t relinputs < "$out/evidence/runtime-inputs.txt"
runtime=();for p in "${relinputs[@]}";do [[ -f $p ]];runtime+=("$work/source/$p");done
extra=$(cat "$project/evidence/perf-r27b/link-inputs.txt")
extra=${extra//"$prev/objects-r27/"/"$out/objects/"}
export ZA_PS5_EXTRA_INPUTS="$extra $out/objects/hebrew_trial.o $out/objects/hebrew_install.o $out/objects/za_items.o --wrap=backend_reset --wrap=za_observer_menu"
printf '%s\n' "$ZA_PS5_EXTRA_INPUTS" > "$out/evidence/link-inputs.txt"
bash tools/ps5/link-title.sh "$out/llvm-pie.elf" "${runtime[@]}" "$archive"
ref=$lab/trial/build-r5/llvm-pie.elf
python3 "$project/port/local-shader-r19/verify-registration.py" "$ref" "$out/llvm-pie.elf" > "$out/evidence/registration.json"
python3 "$root/verify-r28.py" image "$ref" "$out/llvm-pie.elf" "$out/evidence" "$project"
nm=/usr/lib/llvm-21/bin/llvm-nm
"$nm" --defined-only "$out/llvm-pie.elf" > "$out/evidence/defined-symbols.txt"
"$sdk/bin/llvm-strip" --strip-debug -o "$out/title-stripped.elf" "$out/llvm-pie.elf"
tool=$PS5_VULKAN/build/host/ps5-native-tool
"$tool" link --in "$out/title-stripped.elf" --out "$out/eboot.elf" --stub-dir "$sdk/target/lib" \
 --stub "$out/ps5-link/stubs/libSceAgc.so" --stub "$out/ps5-link/stubs/libSceAgcDriver.so" \
 --module-sdk 0x02000009 --companion-sdk 0x08050001 --file-name eboot.elf
python3 "$project/port/title/verify-image.py" "$out/title-stripped.elf" "$out/eboot.elf" "$out/evidence/defined-symbols.txt" > "$out/evidence/image-preservation.json"
"$tool" self --sign --in "$out/eboot.elf" --out "$out/eboot.bin" --magic 0x1D3D154F
"$tool" self --inspect --file "$out/eboot.bin" > "$out/evidence/self-inspection.txt"
sha256sum "$out/eboot.bin" "$out/llvm-pie.elf" > "$out/evidence/SHA256SUMS.txt"
echo 'Offline r28 candidate built and verified; no console access performed'

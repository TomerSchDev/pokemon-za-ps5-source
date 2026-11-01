#!/usr/bin/env bash
# r27-play = exact r26p1 runtime/options + trainer name + PC-proven MONEY hooks.
# Usage: build-r27-play.sh [build]
#        build-r27-play.sh package /absolute/path/to/pc-proof.json
# Build only creates a candidate PIE. Packaging is a separate, source-bound PC-proof gate.
# No console, network, save or Hebrew-work access. Existing revisions are never overwritten.
set -euo pipefail
export LC_ALL=C
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
mode=${1:-build}
[[ $mode == build || $mode == package ]] || { echo 'Expected build or package PC_PROOF.json' >&2; exit 2; }
[[ $mode != build || $# -le 1 ]] || { echo 'build takes no arguments' >&2; exit 2; }
[[ $mode != package || $# == 2 ]] || { echo 'package requires PC_PROOF.json' >&2; exit 2; }

prev=/home/tomer/ps5-za-native/perf-r26p1-20261029
work=${R27_WORK:-/home/tomer/ps5-za-native/r27-play-20261029}
evid=${R27_EVIDENCE:-$project/evidence/perf-r27}
dist=${R27_DIST:-$project/artifacts/randomizer-r27-play}
# Resolve even missing paths, and keep build mutations in a new sibling work copy.
work=$(realpath -m -- "$work")
evid=$(realpath -m -- "$evid")
dist=$(realpath -m -- "$dist")
[[ $work == /home/tomer/ps5-za-native/r27-* && $work != *[[:space:]]* ]] || { echo 'R27_WORK must be a new r27-* sibling without whitespace' >&2; exit 2; }
[[ $evid == "$project"/evidence/* && $dist == "$project"/artifacts/* ]] || { echo 'Evidence/artifacts must remain under this project' >&2; exit 2; }
[[ ${JOBS:-12} =~ ^[1-9][0-9]*$ ]] || { echo 'JOBS must be positive' >&2; exit 2; }
base=$project/artifacts/randomizer-r26p1-play
ref=$base/llvm-pie-r26p1.elf
archive=$work/money-r27/liblasgame-r27.a
obj=$work/objects-r27
pie=$work/source/build/ps5/title/llvm-pie.elf
money=$project/port/cheats-r27
verify=$root/verify-r27-build.py
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
ar=$sdk/bin/llvm-ar
mesa=/home/tomer/ps5-za-native/PS5_Mesa/include
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
research=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research
game=$research/pokeza-pc/update-2.0.2-20261025
deps=$research/za-switch-mods/lib
units=(main_220 main_303 main_315 main_384 main_1035)
pin() { [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]] || { echo "SHA-256 mismatch: $1" >&2; exit 2; }; }
pin "$base/PPSA91762/eboot.bin" c382275b90704d50e50e57875116bd69341e6c6b9c9c4e4d43223b367e19f7fa
pin "$ref" 4eea1378eae9c0914501e3ae1134517d2e4b3bc5a3accedad4980b12581ea787
pin "$prev/dyn-r26/liblasgame-r26.a" dc7fb1cf908fe0af17d6997155897e3c71c9e866dfa9e524a9a2ec87583b1626

if [[ $mode == package ]]; then
    proof=$(realpath -e -- "$2")
    [[ ! -e $dist && -f $evid/build-verification.json ]] || { echo 'Verified candidate required; output must be new' >&2; exit 2; }
    # The gate rechecks candidate/object/runtime/source hashes before any package write.
    python3 -I "$verify" gate "$project" "$prev" "$work" "$evid" "$proof"
    exec > >(tee "$evid/package.log") 2>&1
    TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" \
        bash "$project/port/title/package-title.sh"
    for f in "$base/PPSA91762"/*.txt; do cp -- "$f" "$dist/PPSA91762/"; done
    cp -- "$pie" "$dist/llvm-pie-r27.elf"
    python3 -I "$verify" package "$base/PPSA91762" "$dist/PPSA91762" "$evid"
    sha256sum "$dist/PPSA91762/eboot.bin" "$dist/llvm-pie-r27.elf" > "$evid/SHA256SUMS.txt"
    cat "$evid/SHA256SUMS.txt"
    echo 'r27-play packaged after source-matched PC MONEY proof. Hardware acceptance remains pending.'
    exit 0
fi

[[ ! -e $work && ! -e $evid && ! -e $dist ]] || { echo 'Choose new R27_WORK/R27_EVIDENCE/R27_DIST; an output already exists' >&2; exit 2; }
[[ -f $prev/SNAPSHOT-R26P1 && -d $prev/objects-r26p1 && -d $prev/source/build/ps5/rt ]]
for source in "$money/prepare-money-hooks.py" "$money/za_money.cpp" "$money/za_money.h" "$root/cheats-r27.cpp" \
              "$project/port/rando-v2/"{native_menu,za_player_name,name_keyboard,run_name}.cpp; do
    [[ -f $source ]] || { echo "Missing source: $source" >&2; exit 2; }
done
mkdir -- "$evid"
exec > >(tee "$evid/build.log") 2>&1
python3 -I "$verify" snapshot "$project" "$evid/sources.json"
mkdir -- "$work"
cp -a --reflink=auto -- "$prev/." "$work/"
date -u +%FT%TZ > "$work/SNAPSHOT-R27"
pin "$work/dyn-r26/liblasgame-r26.a" dc7fb1cf908fe0af17d6997155897e3c71c9e866dfa9e524a9a2ec87583b1626
cp -a -- "$work/objects-r26p1" "$obj"
mkdir -- "$work/money-r27"

echo 'Preparing five pinned game units in the isolated work copy'
python3 -I "$money/prepare-money-hooks.py" "$game/aot/main" "$game/game/exefs/main" "$work/money-r27" \
    > "$evid/prepare-money-hooks.json"
cp -- "$work/money-r27/money-hook-manifest.json" "$evid/money-hook-manifest.json"
cd "$work/source"
cc_unit() {
    /usr/bin/clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default \
        -isysroot "$sdk" -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" \
        -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
        -O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label \
        -fvisibility=hidden -Iruntime -march=x86-64-v3 -DZA_PS5 -c "$1" -o "$2"
}
control=$work/money-r27/control
mkdir -- "$control"
: > "$evid/flags-control.txt"
for u in "${units[@]}"; do
    if grep -qw "main/$u" build/ps5/gen/giants.mk; then echo "$u is a giant; refusing O1 recipe" >&2; exit 2; fi
    cc_unit "$game/aot/main/$u.c" "$control/$u.o"
    "$ar" p "$work/dyn-r26/liblasgame-r26.a" "$u.o" > "$control/$u.member.o"
    cmp -s "$control/$u.o" "$control/$u.member.o" || { echo "Unpatched control does not reproduce $u.o" >&2; exit 2; }
    printf '%s: unpatched control is byte-identical; ' "$u" >> "$evid/flags-control.txt"
    sha256sum "$control/$u.o" >> "$evid/flags-control.txt"
    cc_unit "$work/money-r27/$u.c" "$work/money-r27/$u.o"
done
cp --reflink=auto -- "$work/dyn-r26/liblasgame-r26.a" "$archive"
patched_objects=()
for u in "${units[@]}"; do patched_objects+=("$work/money-r27/$u.o"); done
"$ar" rcs "$archive" "${patched_objects[@]}"
python3 -I "$verify" archive "$work/dyn-r26/liblasgame-r26.a" "$archive" "$work/money-r27" "$evid/archive.json"

echo 'Rebuilding NAME, MONEY, overlay and revision objects only'
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
cxx=(-std=c++20 -fno-exceptions -fno-rtti)
incs=(-I"$project/port/rando-v2" -I"$money" -I"$work/port/sdl3-shim/include" -I"$mesa" \
      -I"$work/source/runtime" -I"$project/port/title" -I"$obj" -I"$project/port/randomizer" \
      -I"$project/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include")
for name in native_menu za_player_name name_keyboard run_name; do
    cc "${cxx[@]}" "${flags[@]}" "${incs[@]}" -DJSON_NOEXCEPTION=1 -DZA_RANDOMIZER_PS5=1 \
        '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' -c "$project/port/rando-v2/$name.cpp" -o "$obj/$name.o"
done
cc "${cxx[@]}" "${flags[@]}" "${incs[@]}" -DZA_MONEY_HOOK=1 -c "$root/cheats-r27.cpp" -o "$obj/cheats.o"
cc "${cxx[@]}" "${flags[@]}" "${incs[@]}" -DZA_MONEY_HOOK=1 -c "$money/za_money.cpp" -o "$obj/za_money.o"
# Prove the retained title/options source still reproduces the base object before changing only its revision.
cc -std=c11 "${flags[@]}" -I"$project/port/perf-r26" -I"$work/port/sdl3-shim/include" \
    -I"$work/source/runtime" -I"$project/port/title" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 \
    '-DZA_TITLE_REV="randomizer-r26p-play"' -c "$project/port/perf-r26/title_entry-r26p.c" -o "$control/title_entry.o"
cmp -s "$control/title_entry.o" "$prev/objects-r26p1/title_entry.o" || { echo 'Base title/options control does not reproduce r26p1' >&2; exit 2; }
printf 'title_entry: original revision control is byte-identical; ' >> "$evid/flags-control.txt"
sha256sum "$control/title_entry.o" >> "$evid/flags-control.txt"
cc -std=c11 "${flags[@]}" -I"$project/port/perf-r26" -I"$work/port/sdl3-shim/include" \
    -I"$work/source/runtime" -I"$project/port/title" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 \
    '-DZA_TITLE_REV="randomizer-r27-play"' -c "$project/port/perf-r26/title_entry-r26p.c" -o "$obj/title_entry.o"

# Retain every r26p1 wrapper and glslang library. Runtime objects are copied, not reconfigured.
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
wraps='--wrap=SDL_SavePNG --wrap=radv_ps5_submit --wrap=radv_ps5_submit_times --wrap=za_title_frame_cfg --wrap=za_performance_status'
wraps+=' --wrap=sceAgcSuspendPoint --wrap=clock_gettime --wrap=za_prof_note_render --wrap=za_prof_thread_begin --wrap=za_prof_thread_end'
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) $wraps --start-group $(printf '%s ' "${libs[@]}") --end-group"
printf '%s\n' "$ZA_PS5_EXTRA_INPUTS" > "$evid/link-inputs.txt"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r27.mk <<MAKE
include offline-title.mk
.PHONY: local-title-r27
local-title-r27: \$(TITLE_OBJS)
	@mkdir -p \$(B)/title
	bash tools/ps5/link-title.sh \$(B)/title/llvm-pie.elf \$(TITLE_OBJS) $archive
MAKE
make -s -f local-r27.mk PLATFORM=ps5 -j"${JOBS:-12}" "PS5_DEPS_INC=$runtime_includes" local-title-r27
python3 -I "$project/port/local-shader-r19/verify-registration.py" "$ref" "$pie" > "$evid/registration.json"
python3 -I "$verify" verify "$project" "$prev" "$work" "$evid"
cp -- "$pie" "$evid/llvm-pie-r27-candidate.elf"
sha256sum "$evid/llvm-pie-r27-candidate.elf" > "$evid/CANDIDATE-SHA256SUMS.txt"
echo 'r27 candidate linked and structurally verified. No package created; actual PC proof is required before package mode.'

#!/usr/bin/env bash
# r27b fixes the launcher's missing r17 observer integration. No console access.
# Usage: build-r27b-play.sh [build] | package /absolute/path/to/pc-proof.json
set -euo pipefail
export LC_ALL=C
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
mode=${1:-build}
[[ $mode == build || $mode == package ]] || { echo 'Expected build or package PC_PROOF.json' >&2; exit 2; }
[[ $mode != build || $# -le 1 ]] || { echo 'build takes no arguments' >&2; exit 2; }
[[ $mode != package || $# == 2 ]] || { echo 'package requires PC_PROOF.json' >&2; exit 2; }
prev=/home/tomer/ps5-za-native/perf-r26p1-20261029
r27=/home/tomer/ps5-za-native/r27-play-20261029
work=$(realpath -m -- "${R27B_WORK:-/home/tomer/ps5-za-native/r27b-play-20261029}")
evid=$(realpath -m -- "${R27B_EVIDENCE:-$project/evidence/perf-r27b}")
dist=$(realpath -m -- "${R27B_DIST:-$project/artifacts/randomizer-r27b-play}")
[[ $work == /home/tomer/ps5-za-native/r27b-* && $work != *[[:space:]]* ]] || { echo 'R27B_WORK must be a new r27b-* sibling without whitespace' >&2; exit 2; }
[[ $evid == "$project"/evidence/* && $dist == "$project"/artifacts/* ]] || { echo 'Evidence/artifacts must stay under project' >&2; exit 2; }
base=$project/artifacts/randomizer-r26p1-play
ref=$base/llvm-pie-r26p1.elf
archive=$work/money-r27/liblasgame-r27.a
obj=$work/objects-r27
pie=$work/source/build/ps5/title/llvm-pie.elf
verify=$root/verify-r27b-build.py
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
mesa=/home/tomer/ps5-za-native/PS5_Mesa/include
deps=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib
pin() { [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]] || { echo "SHA-256 mismatch: $1" >&2; exit 2; }; }
pin "$base/PPSA91762/eboot.bin" c382275b90704d50e50e57875116bd69341e6c6b9c9c4e4d43223b367e19f7fa
pin "$ref" 4eea1378eae9c0914501e3ae1134517d2e4b3bc5a3accedad4980b12581ea787
pin "$r27/source/build/ps5/title/llvm-pie.elf" ca6984037a7bd09b65ac857f910ce236f6674c909534d1ad46a2f1127f67faf1

if [[ $mode == package ]]; then
    proof=$(realpath -e -- "$2")
    [[ ! -e $dist && -f $evid/build-verification.json ]] || { echo 'Verified candidate required; output must be new' >&2; exit 2; }
    python3 -I "$verify" gate "$project" "$prev" "$work" "$evid" "$proof"
    exec > >(tee "$evid/package.log") 2>&1
    TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" \
        bash "$project/port/title/package-title.sh"
    for f in "$base/PPSA91762"/*.txt; do cp -- "$f" "$dist/PPSA91762/"; done
    cp -- "$pie" "$dist/llvm-pie-r27b.elf"
    python3 -I "$verify" package "$base/PPSA91762" "$dist/PPSA91762" "$evid"
    sha256sum "$dist/PPSA91762/eboot.bin" "$dist/llvm-pie-r27b.elf" > "$evid/SHA256SUMS.txt"
    cat "$evid/SHA256SUMS.txt"
    exit 0
fi

[[ ! -e $work && ! -e $evid && ! -e $dist ]] || { echo 'Choose new R27B_WORK/R27B_EVIDENCE/R27B_DIST; an output exists' >&2; exit 2; }
mkdir -- "$evid"
exec > >(tee "$evid/build.log") 2>&1
python3 -I "$verify" snapshot "$project" "$evid/sources.json"
mkdir -- "$work"
cp -a --reflink=auto -- "$r27/." "$work/"
date -u +%FT%TZ > "$work/SNAPSHOT-R27B"
python3 -I "$verify" copied "$project" "$work" "$evid"
cp -- "$project/evidence/perf-r27/money-hook-manifest.json" "$evid/"
cp -- "$project/evidence/perf-r27/flags-control.txt" "$evid/"
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
incs=(-I"$project/port/rando-v2" -I"$project/port/cheats-r27" -I"$work/port/sdl3-shim/include" -I"$mesa" \
      -I"$work/source/runtime" -I"$project/port/title" -I"$obj" -I"$project/port/randomizer" \
      -I"$project/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include")
cd "$work/source"
echo 'Rebuilding only the observer-aware launcher and r27b revision label'
cc -std=c++20 -fno-exceptions -fno-rtti "${flags[@]}" "${incs[@]}" -DJSON_NOEXCEPTION=1 -DZA_RANDOMIZER_PS5=1 \
    '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' -c "$project/port/rando-v2/native_menu.cpp" -o "$obj/native_menu.o"
# Reproduce the r27 title object before changing only its compile-time revision.
mkdir -- "$work/control-r27b"
titleincs=(-I"$project/port/perf-r26" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title")
cc -std=c11 "${flags[@]}" "${titleincs[@]}" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 \
    '-DZA_TITLE_REV="randomizer-r27-play"' -c "$project/port/perf-r26/title_entry-r26p.c" -o "$work/control-r27b/title_entry.o"
cmp -s "$work/control-r27b/title_entry.o" "$r27/objects-r27/title_entry.o" || { echo 'r27 title control does not reproduce original' >&2; exit 2; }
printf 'r27b title_entry: r27 revision control is byte-identical; ' >> "$evid/flags-control.txt"
sha256sum "$work/control-r27b/title_entry.o" >> "$evid/flags-control.txt"
cc -std=c11 "${flags[@]}" "${titleincs[@]}" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 \
    '-DZA_TITLE_REV="randomizer-r27b-play"' -c "$project/port/perf-r26/title_entry-r26p.c" -o "$obj/title_entry.o"
# Preserve exact r27 wrapper/library order, changing only the isolated object root.
ZA_PS5_EXTRA_INPUTS=$(cat "$project/evidence/perf-r27/link-inputs.txt")
[[ $ZA_PS5_EXTRA_INPUTS == *"$r27/objects-r27/"* ]] || { echo 'r27 link record lacks expected object paths' >&2; exit 2; }
export ZA_PS5_EXTRA_INPUTS=${ZA_PS5_EXTRA_INPUTS//"$r27/"/"$work/"}
printf '%s\n' "$ZA_PS5_EXTRA_INPUTS" > "$evid/link-inputs.txt"
# No object prerequisites: this target links existing runtime objects only.
cat > local-r27b.mk <<MAKE
include offline-title.mk
.PHONY: local-title-r27b
local-title-r27b:
	@mkdir -p \$(B)/title
	bash tools/ps5/link-title.sh \$(B)/title/llvm-pie.elf \$(TITLE_OBJS) $archive
MAKE
make -s -f local-r27b.mk PLATFORM=ps5 local-title-r27b
python3 -I "$project/port/local-shader-r19/verify-registration.py" "$ref" "$pie" > "$evid/registration.json"
python3 -I "$verify" verify "$project" "$prev" "$work" "$evid"
cp -- "$pie" "$evid/llvm-pie-r27b-candidate.elf"
sha256sum "$evid/llvm-pie-r27b-candidate.elf" > "$evid/CANDIDATE-SHA256SUMS.txt"
echo 'r27b candidate verified; package mode requires the unchanged source-matched PC MONEY proof.'

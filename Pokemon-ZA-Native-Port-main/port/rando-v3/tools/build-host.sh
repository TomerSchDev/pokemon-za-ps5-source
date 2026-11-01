#!/usr/bin/env bash
# rando-v3 host build + tests (WSL, clang-21, ASan/UBSan). No console, no game data in git.
#   bash tools/build-host.sh ASSETS_DIR OUT_DIR [SEEDS]
# ASSETS_DIR = the output of tools/prepare-v3-assets.py (173 files); OUT_DIR gets reports.json for the oracle.
set -euo pipefail
export LC_ALL=C
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
assets=$(realpath -e -- "$1"); out=$(realpath -m -- "$2"); seeds=${3:-100}
work=${RANDO_V3_WORK:-/home/tomer/ps5-za-native/rando-v3-host}
deps=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib
mkdir -p "$work" "$out"
incs=(-I"$here" -I"$here/core" -I"$here/src" -I"$deps/json/include" -I"$deps/mbedtls/include")
# RANDO_V3_SAN=0 builds a plain -O2 binary (for the 100+ seed runs); default is ASan+UBSan.
if [[ ${RANDO_V3_SAN:-1} == 1 ]]; then san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); work=$work-san; else san=(-O2); work=$work-o2; fi
mkdir -p "$work"
for name in sha256 platform_util; do
    clang-21 -O1 -g "${san[@]}" "${incs[@]}" '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' -c "$deps/mbedtls/library/$name.c" -o "$work/$name.o"
done
cxx=(clang++-21 -std=c++20 -O1 -g -Wall -Wextra -Werror -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 "${san[@]}" "${incs[@]}")
echo "-- compile"
"${cxx[@]}" -c "$here/core/randomizer.cpp" -o "$work/randomizer.o"
"${cxx[@]}" -c "$here/src/legacy_progression.cpp" -o "$work/legacy_progression.o"
"${cxx[@]}" -c "$here/src/legacy_research_rewards.cpp" -o "$work/legacy_research_rewards.o"
"${cxx[@]}" -c "$here/src/rando_v3.cpp" -o "$work/rando_v3.o"
if [[ ${RANDO_V3_CONTRACT_ONLY:-0} != 1 ]]; then "${cxx[@]}" -c "$here/test/test_v3.cpp" -o "$work/test_v3.o"; fi
"${cxx[@]}" -c "$here/test/test_ui_contract.cpp" -o "$work/test_ui_contract.o"
"${cxx[@]}" "$work"/randomizer.o "$work"/legacy_progression.o "$work"/legacy_research_rewards.o "$work"/rando_v3.o "$work"/test_ui_contract.o "$work"/sha256.o "$work"/platform_util.o -o "$work/test_ui_contract"
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=print_stacktrace=1 "$work/test_ui_contract" "$here/capabilities.json" 2>&1 | tee "$out/test_ui_contract.log"
if [[ ${RANDO_V3_CONTRACT_ONLY:-0} == 1 ]]; then exit 0; fi
"${cxx[@]}" "$work"/randomizer.o "$work"/legacy_progression.o "$work"/legacy_research_rewards.o "$work"/rando_v3.o "$work"/test_v3.o "$work"/sha256.o "$work"/platform_util.o -o "$work/test_v3"
echo "-- test ($seeds seeds)"
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=print_stacktrace=1 "$work/test_v3" "$assets" "$out" "$seeds" "$here/capabilities.json" 2>&1 | tee "$out/test_v3.log"
exit "${PIPESTATUS[0]}"

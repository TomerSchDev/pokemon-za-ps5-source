#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=/home/tomer/ps5-za-native/randomizer-host-tests
research='/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research'
deps=$research/za-switch-mods/lib
incs=(-I"$root/port/randomizer" -I"$root/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include")
clang++-21 -std=c++20 -O1 -Wall -Wextra -Werror -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 "${incs[@]}" \
    "$root/port/randomizer/core/randomizer.cpp" "$root/port/randomizer/run_store.cpp" "$root/port/randomizer/progression.cpp" \
    "$root/port/randomizer/test-progression.cpp" "$work/sha256.o" "$work/platform_util.o" -o "$work/test-progression"
out="$root/evidence/randomizer-r14-progression-tests"
mkdir -p "$out"
"$work/test-progression" "$research/pokeza-pc/ingame-randomizer/prepared-streamed" "$root/port/randomizer/reward-assets" "$out"

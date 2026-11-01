#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=/home/tomer/ps5-za-native/randomizer-host-tests
deps='/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib'
mkdir -p "$work"
incs=(-I"$root/port/randomizer" -I"$root/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include")
for name in sha256 platform_util; do
    clang-21 -O2 "${incs[@]}" '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' -c "$deps/mbedtls/library/$name.c" -o "$work/$name.o"
done
clang++-21 -std=c++20 -O1 -Wall -Wextra -Werror -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 "${incs[@]}" \
    "$root/port/randomizer/core/randomizer.cpp" "$root/port/randomizer/run_store.cpp" "$root/port/randomizer/test-run-store.cpp" "$work/sha256.o" "$work/platform_util.o" -o "$work/test-run-store"
"$work/test-run-store"
clang++-21 -std=c++20 -O1 -Wall -Wextra -Werror -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 "${incs[@]}" \
    "$root/port/randomizer/core/randomizer.cpp" "$root/port/randomizer/run_store.cpp" "$root/port/randomizer/research_rewards.cpp" "$root/port/randomizer/progression.cpp" \
    "$root/port/randomizer/test-research-rewards.cpp" "$work/sha256.o" "$work/platform_util.o" -o "$work/test-research-rewards"
out="$root/evidence/randomizer-r14-rewards-host-tests"
mkdir -p "$out"
"$work/test-research-rewards" "$root/port/randomizer/reward-assets" "$out"
python3 "$root/port/randomizer/verify-research-rewards.py" "$out"

#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=/home/tomer/ps5-za-native/randomizer-host-tests
deps='/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib'
clang++-21 -std=c++20 -O1 -Wall -Wextra -Werror -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 \
    -I"$root/port/randomizer" -I"$root/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include" \
    "$root/port/randomizer/core/randomizer.cpp" "$root/port/randomizer/run_store.cpp" "$root/port/randomizer/import_repair.cpp" \
    "$root/port/randomizer/test-import-repair.cpp" "$work/sha256.o" "$work/platform_util.o" -o "$work/test-import-repair"
"$work/test-import-repair"

#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
sdk=/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk
deps='/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib/mbedtls'
work=/home/tomer/ps5-za-native/randomizer-copy
mkdir -p "$work" "$root/artifacts/randomizer-copy"
flags=(-O2 -Wall -Wextra -Werror -I"$deps/include" -I"$root/port/randomizer/core" '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"')
for name in sha256 platform_util;do "$sdk/bin/prospero-clang" "${flags[@]}" -c "$deps/library/$name.c" -o "$work/$name.o";done
"$sdk/bin/prospero-clang" "${flags[@]}" "$root/port/randomizer/copy_game_payload.c" "$work/sha256.o" "$work/platform_util.o" -o "$root/artifacts/randomizer-copy/za_randomizer_copy.elf"

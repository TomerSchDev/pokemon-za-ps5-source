#!/usr/bin/env bash
# Host tests (WSL clang, ASan/UBSan) for the rando-v2 name writer and keyboard.
#   bash run-host-tests.sh FIXTURES_DIR OUT_DIR
# FIXTURES_DIR holds plain.bin and mixed.bin from verify/ (PKHeX "fixtures"); copies only, never a live save.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
fixtures=$1 out=$2
mkdir -p "$out/bin"
mbed=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib/mbedtls
core="$here/../../randomizer/core"
flags=(-O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -Wall -Wextra -Werror)
cfg=(-I"$mbed/include" -I"$core" '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"')
json="$(dirname -- "$mbed")/json/include"
for c in sha256 platform_util; do
    clang-21 -std=c11 -O1 -g -fsanitize=address,undefined "${cfg[@]}" -c "$mbed/library/$c.c" -o "$out/bin/mbed_$c.o"
done
clang++-21 -std=c++20 "${flags[@]}" "${cfg[@]}" "$here/../za_player_name.cpp" "$here/test_player_name.cpp" \
    "$out/bin/mbed_sha256.o" "$out/bin/mbed_platform_util.o" -o "$out/bin/test_player_name"
clang++-21 -std=c++20 "${flags[@]}" "${cfg[@]}" "$here/../za_player_name.cpp" "$here/../name_keyboard.cpp" \
    "$here/test_keyboard.cpp" "$out/bin/mbed_sha256.o" "$out/bin/mbed_platform_util.o" -o "$out/bin/test_keyboard"
"$out/bin/test_player_name" "$fixtures" "$out"
"$out/bin/test_keyboard"
clang++-21 -std=c++20 "${flags[@]}" "${cfg[@]}" -I"$core/.." -I"$json" \
    "$here/../za_player_name.cpp" "$here/../run_name.cpp" "$core/randomizer.cpp" "$core/../run_store.cpp" \
    "$here/test_run_name.cpp" "$out/bin/mbed_sha256.o" "$out/bin/mbed_platform_util.o" -o "$out/bin/test_run_name"
"$out/bin/test_run_name" "$fixtures"

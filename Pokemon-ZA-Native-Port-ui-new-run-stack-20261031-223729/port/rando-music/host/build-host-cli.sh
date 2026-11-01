#!/usr/bin/env bash
# Build the r29-music host CLI (same sources as the title's generation path) with ASan/UBSan.
#   bash build-host-cli.sh OUT_BIN
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
music=$(cd "$here/.." && pwd)
project=$(cd "$music/../.." && pwd)
out=$1
mkdir -p "$(dirname "$out")"
deps=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib
mbed=$deps/mbedtls
core=$project/port/randomizer/core
san=(-fsanitize=address,undefined -fno-sanitize-recover=all)
cfg=(-I"$mbed/include" -I"$core" -I"$project/port/randomizer" -I"$project/port/rando-v2" -I"$deps/json/include" -I"$music"
     '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"')
tmp=$(mktemp -d)
for c in sha256 platform_util; do clang-21 -std=c11 -O1 -g "${san[@]}" "${cfg[@]}" -c "$mbed/library/$c.c" -o "$tmp/$c.o"; done
clang++-21 -std=c++20 -O1 -g "${san[@]}" -Wall -Wextra -Werror -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 "${cfg[@]}" \
    "$here/za_music_host.cpp" "$music/za_music.cpp" "$music/run_store_music.cpp" "$core/randomizer.cpp" \
    "$project/port/randomizer/progression.cpp" "$project/port/randomizer/research_rewards.cpp" \
    "$project/port/rando-v2/run_name.cpp" "$project/port/rando-v2/za_player_name.cpp" "$tmp/sha256.o" "$tmp/platform_util.o" -o "$out"
rm -rf "$tmp"
echo "built $out"

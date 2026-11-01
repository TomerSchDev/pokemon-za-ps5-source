#!/usr/bin/env bash
# Compile the rando-v3 title-side sources with the PS5 toolchain (prospero-clang18), the same flags as
# port/rando-music/build-r29-music.sh uses for the randomizer objects. Objects only: no link, no package, no console.
#   bash tools/build-ps5-check.sh [OUT_DIR]
set -euo pipefail
export LC_ALL=C
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
out=${1:-/home/tomer/ps5-za-native/rando-v3-ps5-check}
mkdir -p "$out"
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
deps=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
cxx=(-std=c++20 -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 -DZA_RANDOMIZER_PS5=1 '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"')
# run_store_v3.cpp needs the r29 music header (MusicTableName/MusicBankPath) and the runtime's platform/ps5_compat.h.
runtime=${RANDO_V3_RUNTIME:-/home/tomer/ps5-za-native/r28-play-20261030/source/runtime}
incs=(-I"$here" -I"$here/core" -I"$here/src" -I"$here/../rando-music" -I"$runtime" -I"$deps/json/include" -I"$deps/mbedtls/include")
for f in core/randomizer.cpp src/legacy_progression.cpp src/legacy_research_rewards.cpp src/rando_v3.cpp src/run_store_v3.cpp; do
    echo "[ps5-check] $f"
    cc "${cxx[@]}" "${flags[@]}" "${incs[@]}" -c "$here/$f" -o "$out/$(basename "${f%.cpp}").o"
done
ls -la "$out"/*.o
sha256sum "$out"/*.o > "$out/SHA256SUMS.txt"
echo "PS5 compile check PASS: $(ls "$out"/*.o | wc -l) objects in $out"

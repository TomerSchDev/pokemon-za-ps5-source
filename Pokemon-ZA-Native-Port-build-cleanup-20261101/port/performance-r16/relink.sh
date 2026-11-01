#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
exec > >(tee "$root/evidence/performance-r16/build-final.log") 2>&1
work=/home/tomer/ps5-za-native/perf-r16-20261028
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/randomizer-r16/objects
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$root/port/performance-r16" -c "$root/port/performance-r16/performance.c" -o "$obj/title_performance.o"
export ZA_PS5_EXTRA_INPUTS="$(printf '%s ' "$obj"/*.o)"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc"
make -s -f offline-title.mk PLATFORM=ps5 -j4 "PS5_DEPS_INC=$runtime_includes" \
    GAMELIB=/home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a offline-title
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$root/artifacts/randomizer-r16-validated" bash "$root/port/title/package-title.sh"
printf '30\n' > "$root/artifacts/randomizer-r16-validated/PPSA91762/performance-profile.txt"
printf 'optimized\n' > "$root/artifacts/randomizer-r16-validated/PPSA91762/performance-options.txt"

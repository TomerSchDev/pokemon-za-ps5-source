#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
exec > >(tee "$root/evidence/observer-r17/build.log") 2>&1
work=/home/tomer/ps5-za-native/capture-r17-20261028
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/observer-r17/objects
cc(){ sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
incs=(-I"$work/port/sdl3-shim/include" -I"/home/tomer/ps5-za-native/PS5_Mesa/include" -I"$work/source/runtime" -I"$root/port/title" -I"$root/port/observer-r17" -I"$obj" -I"$root/port/randomizer" -I"$root/port/randomizer/core")
research='/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research'
incs+=(-I"$research/za-switch-mods/lib/json/include")
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
for name in observer title_png; do
    cc -std=c11 "${flags[@]}" "${incs[@]}" -c "$root/port/observer-r17/$name.c" -o "$obj/$name.o"
done
cc -std=c++20 -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 -DZA_RANDOMIZER_PS5=1 "${flags[@]}" "${incs[@]}" -c "$work/native_menu-r17.cpp" -o "$obj/native_menu.o"
cc -std=c11 "${flags[@]}" "${incs[@]}" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r17a-observer"' -c "$work/title_entry-r17.c" -o "$obj/title_entry.o"
export ZA_PS5_EXTRA_INPUTS="$(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$root/port/observer-r17"
make -s -f offline-title.mk PLATFORM=ps5 -j4 "PS5_DEPS_INC=$runtime_includes" GAMELIB=/home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a offline-title
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$root/artifacts/randomizer-r17a-observer-validated" bash "$root/port/title/package-title.sh"
printf 'optimized\n' > "$root/artifacts/randomizer-r17a-observer-validated/PPSA91762/performance-options.txt"
printf 'observe-r17\n' > "$root/artifacts/randomizer-r17a-observer-validated/PPSA91762/observer-enable.txt"

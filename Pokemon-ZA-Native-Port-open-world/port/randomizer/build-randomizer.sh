#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=/home/tomer/ps5-za-native/title-r1-20261027
revision=${RANDO_REV:-r1}
[[ $revision =~ ^r[0-9]+$ ]] || exit 2
obj=$work/randomizer-$revision/objects
dist=$root/artifacts/randomizer-$revision
python3 "$root/port/randomizer/apply-gwin-guard.py" "$work/source"
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
research='/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research'
deps=$research/za-switch-mods/lib
mkdir -p "$obj" "$dist/PPSA91762/randomizer-assets"
python3 "$root/port/randomizer/prepare-assets.py" "$research/pokeza-pc/ingame-randomizer/prepared-streamed" "$dist/PPSA91762/randomizer-assets" "$obj/assets_hashes.h"
cc(){ sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
incs=(-I"$work/port/sdl3-shim/include" -I"/home/tomer/ps5-za-native/PS5_Mesa/include" -I"$work/source/runtime" -I"$root/port/title" -I"$obj" -I"$root/port/randomizer" -I"$root/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include")
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
for f in randomizer/core/randomizer.cpp randomizer/run_store.cpp randomizer/import_repair.cpp randomizer/research_rewards.cpp randomizer/progression.cpp randomizer/menu_display.cpp randomizer/native_menu.cpp; do
    echo "[randomizer] $f"
    cc -std=c++20 -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 -DZA_RANDOMIZER_PS5=1 "${flags[@]}" "${incs[@]}" -c "$root/port/$f" -o "$obj/$(basename "${f%.cpp}").o"
done
extra_defines=()
game_archive=$work/fps-r13/liblasgame-r13.a
if [[ ${RANDO_CHEATS:-0} == 1 ]]; then
    extra_defines=(-DZA_NATIVE_CHEATS=1)
    game_archive=$work/cheats-r12/liblasgame-r12.a
    [[ -f $game_archive ]] || exit 2
    cc -std=c++20 -fno-exceptions -fno-rtti "${flags[@]}" "${incs[@]}" -c "$root/port/randomizer/cheats.cpp" -o "$obj/cheats.o"
fi
for name in sha256 platform_util; do
    cc -std=c11 "${flags[@]}" "${incs[@]}" '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' -c "$deps/mbedtls/library/$name.c" -o "$obj/mbedtls_$name.o"
done
cc -std=c11 "${flags[@]}" "${incs[@]}" "${extra_defines[@]}" -DZA_NATIVE_RANDOMIZER=1 "-DZA_TITLE_REV=\"randomizer-$revision\"" -c "$root/port/title/title_entry.c" -o "$obj/title_entry.o"
# Reuse the exact verified r14 shim objects, filesystem wrapper and frame hook.
# Never overwrite the stock title entry or baseline game code.
for p in "$work"/objects/*.o; do [[ $(basename "$p") == title_entry.o ]] || cp "$p" "$obj/"; done
export ZA_PS5_EXTRA_INPUTS="$(printf '%s ' "$obj"/*.o)"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc"
make -f offline-title.mk PLATFORM=ps5 -j4 "PS5_DEPS_INC=$runtime_includes" "GAMELIB=$game_archive" offline-title
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$root/port/title/package-title.sh"
cp "$root/evidence/title-r14-repeat-pipeline-cache.bin" "$dist/PPSA91762/cache/vk_pipelines.bin"
printf '30\n' > "$dist/PPSA91762/performance-profile.txt"
echo "Randomizer $revision built: $dist/PPSA91762"

#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=${TITLE_WORK:-/home/tomer/ps5-za-native/title-r1-20261027}
[[ -f $work/SNAPSHOT-COMPLETE ]] || { echo 'Run prepare-build.sh first' >&2; exit 2; }
export PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
mesa=${PS5_MESA:-/home/tomer/ps5-za-native/PS5_Mesa}
port=$work/port
mkdir -p "$work/inc" "$work/objects"
msys=${ZA_MSYS2_INC:-/mnt/c/msys64/ucrt64/include}
for d in libavcodec libavformat libavutil libswscale vma; do
    [[ -d $msys/$d ]] && ln -sfn "$msys/$d" "$work/inc/$d"
done
[[ ! -f $msys/vk_mem_alloc.h ]] || ln -sfn "$msys/vk_mem_alloc.h" "$work/inc/vk_mem_alloc.h"
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
inc=(-I"$mesa/include" -I"$port/sdl3-shim/include" -I"$port/shaderc-cache/include" -I"$work/inc")
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
for f in "$port"/sdl3-shim/src/*.c "$port/vk-loader/vk_loader.c" "$port/ffmpeg-stubs/ffmpeg_stubs.c" "$port/shaderc-cache/shaderc_cache.c"; do
    obj=$work/objects/$(basename "${f%.c}").o
    echo "[title] $(basename "$f")"
    cc "${flags[@]}" "${inc[@]}" -c "$f" -o "$obj"
done
cc "${flags[@]}" "${inc[@]}" -DZA_TITLE_REV="\"${TITLE_REV:-r3}\"" -I"$work/source/runtime" -c "$root/port/title/title_entry.c" -o "$work/objects/title_entry.o"
cc "${flags[@]}" -c "$root/port/title/performance.c" -o "$work/objects/title_performance.o"
if grep -q 'Native titles refuse chdir' "$work/source/tools/ps5/link-title.sh"; then
    cc "${flags[@]}" -c "$root/port/title/title_fs.c" -o "$work/objects/title_fs.o"
fi
cp "$root/port/title/offline-title.mk" "$work/source/offline-title.mk"
cd "$work/source"
export ZA_PS5_EXTRA_INPUTS="$(printf '%s ' "$work"/objects/*.o)"
overrides=()
[[ -z ${TITLE_GAMELIB:-} ]] || overrides+=("GAMELIB=$TITLE_GAMELIB")
exec make -f offline-title.mk PLATFORM=ps5 -j"${JOBS:-4}" "PS5_DEPS_INC=${inc[*]}" \
    "TITLE_TEST_SOURCE=$root/port/title/test-link-game.c" "${overrides[@]}" "${1:-offline-runtime}"

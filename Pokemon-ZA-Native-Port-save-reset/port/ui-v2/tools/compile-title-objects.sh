#!/usr/bin/env bash
# r29-ui: compile the ui-v2 title-side objects with the PS5 toolchain (prospero-clang18 = clang-21 at the payload SDK's
# target), -Wall -Wextra -Werror, no exceptions / RTTI, the flags and include set of the r27..r29 title objects
# (port/perf-r28/build-r28-play.sh, port/rando-music/build-r29-music.sh). Objects only; the link is build-r29-ui.sh.
#   compile-title-objects.sh <work tree> <out dir> <assets_hashes.h dir> [build label]
# <work tree>: a prepared r28b-dlc-dex-* merge tree (source/runtime, port/sdl3-shim/include, inc, ...); read only.
set -euo pipefail
[[ $# -ge 3 ]] || { echo "usage: $0 <work tree> <out dir> <assets_hashes.h dir> [label]" >&2; exit 2; }
work=$1 out=$2 hashes=$3 label=${4:-r29-ui}
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)      # port/ui-v2
project=$(cd "$root/../.." && pwd)
export PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
export PS5_PAYLOAD_SDK=${PS5_PAYLOAD_SDK:-$PS5_VULKAN/.deps/native/ps5-payload-sdk}
export PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
mesa=${PS5_MESA:-/home/tomer/ps5-za-native/PS5_Mesa}/include
deps=${ZA_DEPS:-/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib}
[[ -f $hashes/assets_hashes_v3.h ]] || { echo "no $hashes/assets_hashes_v3.h" >&2; exit 2; }
[[ -f $work/source/runtime/ui/menu.h && -d $work/port/sdl3-shim/include && -d $work/inc ]] || { echo "not a prepared tree: $work" >&2; exit 2; }
mkdir -p "$out"
if [[ ${ZA_REQUIRE_HANDOFF:-1} == 1 ]]; then
    python3 "$root/tools/verify-generator-handoff.py" "$project/port/rando-v3/HANDOFF.json" "$hashes" --out "$out/generator-receipt.json"
fi
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-O2 -Wall -Wextra -Werror -Wno-missing-field-initializers -ffunction-sections -fdata-sections)
# ZA_TITLE_PREFIX_MAP=<old>=<new>: one -ffile-prefix-map (also __FILE__), e.g. to compile a worktree as if it were the tree
# the pinned objects came from (their asserts embed the source path); empty = none (as before)
[[ -z ${ZA_TITLE_PREFIX_MAP:-} ]] || flags+=("-ffile-prefix-map=$ZA_TITLE_PREFIX_MAP")
cxx=(-std=c++20 -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 -DZA_RANDOMIZER_PS5=1 -DZA_PS5 '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"'
     -DZA_MONEY_HOOK=1 "-DZA_UI_BUILD_LABEL=\"$label\"")
incs=(-isystem "$root/third_party/stb" -I"$root/src" -I"$project/port/rando-v3/src" -I"$project/port/rando-v3" -I"$project/port/rando-v3/core" -I"$project/port/randomizer"
      -I"$project/port/rando-v2" -I"$project/port/rando-music" -I"$project/port/cheats-r28" -I"$project/port/cheats-r27"
      -I"$project/port/perf-r28/src" -I"$hashes" -I"$work/port/sdl3-shim/include" -I"$mesa" -I"$work/source/runtime"
      -I"$project/port/title" -I"$deps/json/include" -I"$deps/mbedtls/include")
: > "$out/compile.log"
# the pure C++ modules (as phase 1 compiled them) + the new ones
for s in ui_canvas ui_widgets ui_model settings_codes items_picker ui_launcher ui_overlay ui_pad fonts_embedded ui_platform launcher_core launcher_ps5 overlay_ps5; do
    echo "cc $s.cpp" | tee -a "$out/compile.log"
    cc "${cxx[@]}" "${flags[@]}" "${incs[@]}" -c "$root/src/$s.cpp" -o "$out/$s.o" 2>>"$out/compile.log"
done
# the Vulkan quad: the runtime's include path (vk.h -> nvn.h, maxwell/shader.h, VMA from the tree's inc)
echo "cc ui_quad.c" | tee -a "$out/compile.log"
cc -std=c11 "${flags[@]}" -DZA_PS5 -DLARECOMP_STATIC_GAMELIB -I"$root/src" -I"$work/source/runtime" -I"$work/source/runtime/nvn" \
    -I"$mesa" -I"$work/inc" -I"$work/port/sdl3-shim/include" -I"$work/source/third_party/ps5-stubs/include" \
    -c "$root/src/ui_quad.c" -o "$out/ui_quad.o" 2>>"$out/compile.log"
# the title entry (r26p's flags: port/perf-r28/build-r28-play.sh line 75)
echo "cc title_entry_uiv2.c" | tee -a "$out/compile.log"
cc -std=c11 "${flags[@]}" -I"$project/port/perf-r26" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 "-DZA_TITLE_REV=\"randomizer-$label\"" \
    -c "$root/src/title_entry_uiv2.c" -o "$out/title_entry.o" 2>>"$out/compile.log"
(cd "$out" && sha256sum ./*.o | sed 's#\./##') > "$out/SHA256SUMS.txt"
ls -l "$out"/*.o | awk '{print $5, $9}'
echo "title objects compiled with -Werror: $(ls "$out"/*.o | wc -l)"

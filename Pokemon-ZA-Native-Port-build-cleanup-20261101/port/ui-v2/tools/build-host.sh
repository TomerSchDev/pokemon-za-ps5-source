#!/usr/bin/env bash
# ui-v2 host build: the rasterizer, model, screens and legacy-look renderers with the same language constraints as
# the title (C++17, no exceptions, no RTTI, -Werror), then the tests and the mockup PNGs.
#   bash tools/build-host.sh [out dir]            (default: port/ui-v2/build-host, outside git)
# Optional: PS5_CHECK=1 also compiles the title-side sources with the PS5 toolchain (object files only, no link),
# proving they build for the console without touching any existing tree.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
port=$(cd "$root/.." && pwd)
out=${1:-$root/build-host}
mkdir -p "$out" "$root/mockups"
CXX=${CXX:-clang++-21}
# (-Wno-missing-field-initializers: the model's rows are aggregates with trailing default member initializers)
flags=(-std=c++17 -O2 -g -Wall -Wextra -Werror -Wno-missing-field-initializers -fno-exceptions -fno-rtti
       -isystem "$root/third_party/stb" -I"$root/src" -I"$port/randomizer" -I"$port/rando-v2" -I"$port/cheats-r28")
title_srcs=(ui_canvas ui_widgets ui_model items_picker ui_launcher ui_overlay)   # what the title would link
host_srcs=(legacy_look png_write)                                               # host only
objs=()
for s in "${title_srcs[@]}" "${host_srcs[@]}"; do
    "$CXX" "${flags[@]}" -c "$root/src/$s.cpp" -o "$out/$s.o"
    objs+=("$out/$s.o")
done
"$CXX" "${flags[@]}" "$root/src/mockups_main.cpp" "${objs[@]}" -lz -o "$out/mockups"
"$CXX" "${flags[@]}" "$root/test/test_ui.cpp" "${objs[@]}" -lz -o "$out/test_ui"
"$out/test_ui" "$root/fonts" | tee "$out/test.log"
"$out/mockups" "$root/fonts" "$root/mockups" | tee "$out/mockups.log"
if [[ ${PS5_CHECK:-0} == 1 ]]; then
    PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
    export PS5_VULKAN PS5_PAYLOAD_SDK=${PS5_PAYLOAD_SDK:-$PS5_VULKAN/.deps/native/ps5-payload-sdk} PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
    mkdir -p "$out/ps5"
    for s in "${title_srcs[@]}"; do
        sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c++17 -O2 -Wall -Wextra -Werror -Wno-missing-field-initializers -fno-exceptions -fno-rtti \
            -isystem "$root/third_party/stb" -I"$root/src" -I"$port/cheats-r28" -c "$root/src/$s.cpp" -o "$out/ps5/$s.o"
    done
    ls -l "$out/ps5" | tee "$out/ps5-check.log"
    echo "PS5 toolchain: ${#title_srcs[@]} title-side objects compiled (not linked, not packaged)"
fi
(cd "$root/mockups" && sha256sum ./*.png | sed 's#\./##' > SHA256SUMS.txt)
cp "$root/mockups/SHA256SUMS.txt" "$out/mockups-SHA256SUMS.txt"
echo "ui-v2 host build complete: $out"

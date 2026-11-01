#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=/home/tomer/ps5-za-native/shader-prewarm-research
runtime=/home/tomer/ps5-za-native/title-r1-20261027/source/runtime/nvn/maxwell
mkdir -p "$work/offline"
/usr/bin/clang-21 -O2 -fPIC -shared -Wall -Wextra -Werror -Wno-unused-parameter \
    -I"$runtime" "$root/translate_bridge.c" "$runtime/translate.c" -lm -o "$work/offline/libza_translate.so"
cmake --build "$work/host-build" -j 4 --target compiler-worker
sha256sum "$runtime/translate.c" "$runtime/shader.h" "$work/offline/libza_translate.so" > "$work/offline/translator-provenance.txt"

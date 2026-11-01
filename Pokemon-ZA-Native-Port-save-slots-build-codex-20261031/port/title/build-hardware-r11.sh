#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=/home/tomer/ps5-za-native/title-r1-20261027
if [[ ! -f $work/port/shaderc-cache/shaderc_cache.c.before-r11 ]]; then
    cp "$work/port/shaderc-cache/shaderc_cache.c" "$work/port/shaderc-cache/shaderc_cache.c.before-r11"
fi
cp "$root/port/shaderc-cache/shaderc_cache.c" "$work/port/shaderc-cache/shaderc_cache.c"
bash "$root/port/shaderc-cache/tools/compile-missing.sh" "$root/port/title/assets/shaders" "$work/shaders"
TITLE_REV=r11 bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r11-hardware" bash "$root/port/title/package-title.sh"

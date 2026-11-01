#!/usr/bin/env bash
# Host-only integration of real overlay + real money hook; no console/storage.
# Uses a unique temporary directory. Caller may set CXX and MESA_INCLUDE.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$here/../../.." && pwd)
out=$(mktemp -d /tmp/za-r27-overlay-tests.XXXXXX)
trap 'rm -rf -- "$out"' EXIT
cxx=${CXX:-clang++-21}
mesa=${MESA_INCLUDE:-/home/tomer/ps5-za-native/PS5_Mesa/include}
flags=(-std=c++20 -O1 -g -Wall -Wextra -Werror -fno-exceptions -fno-rtti -fno-omit-frame-pointer
       -fsanitize=address,undefined -fno-sanitize-recover=all -DZA_CHEATS_HOST_TEST=1
       -I"$root/port/sdl3-shim/include" -I"$mesa" -I"$root/port/randomizer" -I"$root/port/cheats-r27")
for hook in 1 0; do
    defines=()
    if [[ $hook == 1 ]]; then defines=(-DZA_MONEY_HOOK=1); fi
    echo "[r27 overlay] compile and run, MONEY hook=$hook"
    "$cxx" "${flags[@]}" "${defines[@]}" "$root/port/perf-r27/cheats-r27.cpp" \
        "$root/port/cheats-r27/za_money.cpp" "$here/test_cheats_r27.cpp" -o "$out/test-overlay-$hook"
    "$out/test-overlay-$hook"
done

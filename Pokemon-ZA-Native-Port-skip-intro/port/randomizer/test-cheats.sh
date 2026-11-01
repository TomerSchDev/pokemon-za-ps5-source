#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=/home/tomer/ps5-za-native/randomizer-host-tests/test-cheats
clang++-21 -std=c++20 -O1 -Wall -Wextra -Werror -fno-exceptions -fno-rtti \
    -I"$root/port/sdl3-shim/include" -I/home/tomer/ps5-za-native/PS5_Mesa/include \
    "$root/port/randomizer/cheats.cpp" "$root/port/randomizer/test-cheats.cpp" -o "$out"
"$out"

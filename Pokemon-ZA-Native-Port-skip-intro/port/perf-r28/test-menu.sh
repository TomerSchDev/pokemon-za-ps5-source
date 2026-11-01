#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
out=$root/test-results
mkdir -p "$out"
clang++-21 -std=c++20 -O1 -g -Wall -Wextra -Werror -fno-exceptions -fno-rtti -fno-omit-frame-pointer \
 -fsanitize=address,undefined -fno-sanitize-recover=all -DZA_CHEATS_HOST_TEST=1 -DZA_MONEY_HOOK=1 \
 -I"$root/src" -I"$project/port/randomizer" -I"$project/port/cheats-r28" -I"$project/port/cheats-r27" \
 -I/home/tomer/ps5-za-native/r27b-play-20261029/port/sdl3-shim/include -I/home/tomer/ps5-za-native/PS5_Mesa/include \
 "$root/src/cheats-r28.cpp" "$project/port/cheats-r27/za_money.cpp" "$root/test-menu.cpp" -o "$out/test-menu"
"$out/test-menu" | tee "$out/menu-test.log"

#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=/home/tomer/ps5-za-native/randomizer-host-tests
clang++-21 -std=c++20 -O1 -Wall -Wextra -Werror -fno-exceptions -fno-rtti \
    -I"$root/port/sdl3-shim/include" -I/home/tomer/ps5-za-native/PS5_Mesa/include \
    "$root/port/randomizer/cheats.cpp" "$root/port/randomizer/test-cheat-persistence.cpp" \
    -Wl,--wrap=fopen -Wl,--wrap=rename -o "$work/test-cheat-persistence"
data=$(mktemp -d "$work/cheat-settings-XXXXXX")
"$work/test-cheat-persistence" "$data" run-a set
"$work/test-cheat-persistence" "$data" run-a verify
"$work/test-cheat-persistence" "$data" run-b default
"$work/test-cheat-persistence" "$data" run-a fail
"$work/test-cheat-persistence" "$data" run-a verify
"$work/test-cheat-persistence" "$data" run-c corrupt
echo 'PASS: actual file IO, process restart, independent runs, failed atomic rename retains prior settings, corrupt settings ignored'

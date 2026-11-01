#!/usr/bin/env bash
# r24-clock host tests (Ubuntu, clang-21): the option parser and the clock_gettime counter under ASan/UBSan, a host
# check of the shim's TSC selection code (fake TSC), and a compile of za_clock.c / the title entry / the patched shim
# for the PS5 target.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$here"
rm -rf out && mkdir -p out
cc=/usr/bin/clang-21
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -g -O1)
warn=(-std=c11 -Wall -Wextra -Werror)
"$cc" "${warn[@]}" "${san[@]}" test_options.c -o out/test_options
./out/test_options
"$cc" "${warn[@]}" -Wno-unused-function "${san[@]}" -pthread test_clock.c -o out/test_clock
./out/test_clock
python3 test_analyze.py
# the PS5 target: the same flags as the build (compile only)
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
work=/home/tomer/ps5-za-native/perf-r24clock-20261029
mesa=/home/tomer/ps5-za-native/PS5_Mesa
project=$(cd "$here/../../.." && pwd)
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
ps5cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
ps5cc "${flags[@]}" -c "$here/../za_clock.c" -o out/za_clock.ps5.o
ps5cc "${flags[@]}" -I"$here/.." -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" \
    -I"$project/port/title" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r24-clock"' \
    -c "$here/../title_entry-r24clock.c" -o out/title_entry.ps5.o
if grep -q 'r24-clock: SDL3_PS5_TICKS=tsc' "$work/port/sdl3-shim/src/sdl3_ps5_core.c"; then
    ps5cc "${flags[@]}" -I"$mesa/include" -I"$work/port/sdl3-shim/include" -I"$work/port/shaderc-cache/include" -I"$work/inc" \
        -c "$work/port/sdl3-shim/src/sdl3_ps5_core.c" -o out/sdl3_ps5_core.ps5.o
    echo "PASS PS5 compile: patched sdl3_ps5_core.c"
fi
echo "PASS PS5 compile: za_clock.c, title_entry-r24clock.c (-Wall -Wextra -Werror)"
/usr/lib/llvm-21/bin/llvm-nm --undefined-only out/za_clock.ps5.o | awk '{print $NF}' | sort | tr '\n' ' '; echo
echo "PASS all r24-clock host tests"

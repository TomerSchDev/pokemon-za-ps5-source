#!/usr/bin/env bash
# r24-prof host tests (Ubuntu, clang-21, Python 3): option parser, profiler core and real-signal sampling under
# ASan/UBSan, the symbolizer against a synthetic PIE, and a compile of za_prof.c / the title entry for the PS5 target.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$here"
rm -rf out && mkdir -p out
cc=/usr/bin/clang-21
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -g -O1)
warn=(-std=c11 -Wall -Wextra -Werror)
"$cc" "${warn[@]}" "${san[@]}" test_options.c -o out/test_options
./out/test_options
"$cc" "${warn[@]}" "${san[@]}" -pthread test_core.c -o out/test_core
./out/test_core
"$cc" -g -O0 -fPIE -pie fake/main.c fake/source/runtime/nvn/vulkan/exec_fake.c fake/PS5_Mesa/src/amd/vulkan/radv_fake.c \
    -o out/synthetic.elf
python3 test_symbolize.py
# the PS5 target: the same flags as the build (compile only)
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
work=/home/tomer/ps5-za-native/perf-r24prof-20261029
project=$(cd "$here/../../.." && pwd)
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
sh "$PS5_VULKAN/tooling/prospero-clang18" "${flags[@]}" -I"$here/.." -c "$here/../za_prof.c" -o out/za_prof.ps5.o
sh "$PS5_VULKAN/tooling/prospero-clang18" "${flags[@]}" -I"$here/.." -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" \
    -I"$project/port/title" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r24-prof"' \
    -c "$here/../title_entry-r24prof.c" -o out/title_entry.ps5.o
echo "PASS PS5 compile: za_prof.c, title_entry-r24prof.c (-Wall -Wextra -Werror)"
/usr/lib/llvm-21/bin/llvm-nm --undefined-only out/za_prof.ps5.o | awk '{print $NF}' | sort | tr '\n' ' '; echo
echo "PASS all r24-prof host tests"

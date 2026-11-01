#!/usr/bin/env bash
# r26p host tests (WSL Ubuntu, clang 21). Binaries in a temporary directory; nothing written into the repository.
#   1. test_options_r26p.c: the fps= key through za_r26p_parse (ASan + UBSan)
#   2. test_cheats_r26.cpp: cheats-r26.cpp on the host (-DZA_CHEATS_HOST_TEST, the SDL3 shim headers, Mesa's
#      vulkan.h; Vulkan / SDL / console calls stubbed) - settings, counter, six rows and trial/start/stop/retry
#      (ASan + UBSan)
#   3. PS5 target compile of cheats-r26.cpp and title_entry-r26p.c with the title's flags (-Werror)
# Usage: bash port/perf-r26/test/test-r26p.sh
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
project=$(cd "$here/../.." && pwd)
cc=${CC:-clang-21}
work=${R26_WORK:-/home/tomer/ps5-za-native/perf-r26-20261029}
mesa=/home/tomer/ps5-za-native/PS5_Mesa/include
out=$(mktemp -d /tmp/za-r26p-tests.XXXXXX)
trap 'rm -rf "$out"' EXIT
warn=(-Wall -Wextra -Werror -Wno-sign-conversion)
san=(-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=all)
echo "== compiler: $("$cc" --version | head -1)"

echo "== 1. test_options_r26p.c (ASan + UBSan)"
"$cc" -std=c11 "${warn[@]}" -Wshadow "${san[@]}" -I"$here" "$here/test/test_options_r26p.c" -o "$out/test_options_r26p"
"$out/test_options_r26p"

echo "== 2. test_cheats_r26.cpp (ASan + UBSan; cheats-r26.cpp with -DZA_CHEATS_HOST_TEST)"
"$cc" -std=c++20 "${warn[@]}" "${san[@]}" -fno-exceptions -fno-rtti -DZA_CHEATS_HOST_TEST=1 \
    -I"$work/port/sdl3-shim/include" -I"$mesa" -I"$project/port/randomizer" \
    "$here/cheats-r26.cpp" "$here/test/test_cheats_r26.cpp" -lstdc++ -o "$out/test_cheats_r26"
"$out/test_cheats_r26" | grep -vE '^\[za-cheats\]'

echo "== r16 production policy/API: fallback, retry and restoration (ASan + UBSan)"
for name in test-policy test-api; do
    "$cc" -std=c11 "${warn[@]}" "${san[@]}" "$project/port/performance-r16/$name.c" -o "$out/$name"
    (cd "$out" && "./$name")
done

echo "== 3. PS5 target compile (-Werror) of cheats-r26.cpp and title_entry-r26p.c"
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
ps5cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
research=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research
deps=$research/za-switch-mods/lib
ps5cc -std=c++20 -fno-exceptions -fno-rtti -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$work/port/sdl3-shim/include" -I"$mesa" -I"$work/source/runtime" -I"$project/port/title" -I"$work/objects-r26" \
    -I"$project/port/randomizer" -I"$project/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include" \
    -c "$here/cheats-r26.cpp" -o "$out/cheats.ps5.o"
ps5cc -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -I"$here" -I"$work/port/sdl3-shim/include" \
    -I"$work/source/runtime" -I"$project/port/title" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r26p-play"' \
    -c "$here/title_entry-r26p.c" -o "$out/title_entry.ps5.o"
"$PS5_PAYLOAD_SDK/bin/llvm-nm" --undefined-only "$out/cheats.ps5.o" | awk '{print $NF}' | grep -E '^(renderer_present_count|za_performance_status|za_performance_request|SDL_GetTicksNS|vkCmdClearAttachments|sceKernelDebugOutText)$' | sort | tr '\n' ' '
echo
echo "PASS test-r26p: options, cheats host test, PS5 compiles"

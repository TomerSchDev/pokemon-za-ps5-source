#!/usr/bin/env bash
# r25 host tests (Ubuntu, clang-21): the submitter's core, the cross-core TSC check and the TSC-derived clock, the
# option parser and za_clock_r25.c's radv_threaded path, under ASan/UBSan (and the submitter and the clock once more
# under TSan); then the PS5-target compile of za_clock_r25.c and the title entry with the build's flags.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$here"
rm -rf out && mkdir -p out
cc=/usr/bin/clang-21
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -g -O1)
warn=(-std=c11 -Wall -Wextra -Werror)
"$cc" "${warn[@]}" "${san[@]}" -pthread test_submitter.c -o out/test_submitter
./out/test_submitter
"$cc" "${warn[@]}" -fsanitize=thread -g -O1 -pthread test_submitter.c -o out/test_submitter_tsan
./out/test_submitter_tsan > out/tsan.log 2>&1 || { cat out/tsan.log; exit 1; }
grep -q "PASS za_submitter.h" out/tsan.log && echo "PASS za_submitter.h under ThreadSanitizer (no data race reported)"
"$cc" "${warn[@]}" -Wno-unused-function "${san[@]}" -pthread test_tsc_check.c -o out/test_tsc_check
./out/test_tsc_check
"$cc" "${warn[@]}" "${san[@]}" test_options.c -o out/test_options
./out/test_options
# za_clock_r25.c itself (included, the PS5 imports stubbed; FreeBSD's affinity headers from host-include/)
"$cc" "${warn[@]}" "${san[@]}" -I"$here/host-include" -pthread test_clock_radv.c -o out/test_clock_radv
./out/test_clock_radv
"$cc" "${warn[@]}" -fsanitize=thread -g -O1 -I"$here/host-include" -pthread test_clock_radv.c -o out/test_clock_radv_tsan
./out/test_clock_radv_tsan > out/tsan-clock.log 2>&1 || { cat out/tsan-clock.log; exit 1; }
grep -q "PASS za_clock_r25.c" out/tsan-clock.log && echo "PASS za_clock_r25.c radv_threaded under ThreadSanitizer (no data race reported)"
python3 test_analyze.py
# the PS5 target: the same flags as the build (compile only)
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
work=/home/tomer/ps5-za-native/perf-r25-20261029
project=$(cd "$here/../../.." && pwd)
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
ps5cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
ps5cc "${flags[@]}" -c "$here/../za_clock_r25.c" -o out/za_clock_r25.ps5.o
ps5cc "${flags[@]}" -I"$here/.." -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" \
    -I"$project/port/title" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r25-perf"' \
    -c "$here/../title_entry-r25.c" -o out/title_entry.ps5.o
echo "PASS PS5 compile: za_clock_r25.c, title_entry-r25.c (-Wall -Wextra -Werror)"
echo -n "za_clock_r25.o imports: "
/usr/lib/llvm-21/bin/llvm-nm --undefined-only out/za_clock_r25.ps5.o | awk '{print $NF}' | sort | tr '\n' ' '; echo
echo "PASS all r25 host tests"

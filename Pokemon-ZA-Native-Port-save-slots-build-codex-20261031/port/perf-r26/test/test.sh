#!/usr/bin/env bash
# r26 host tests (WSL Ubuntu, clang 21). Binaries in a temporary directory; nothing written into the repository.
#   1. port/dynamic-timing's own glue tests, unchanged, against the r26 glue (ASan + UBSan)
#   2. r26's glue additions: window accounting and za_dt_report (ASan + UBSan, then TSan with a concurrent reporter)
#   3. the option keys and precedence rules (za_r26_options.h)
#   4. the hook signatures: every `extern ... za_dt_*(...)` declaration in the patched units, compiled together with
#      the glue header (conflicting types fail)
#   5. PS5 target compile of the glue, the model and the title entry with the title's flags (-Werror)
# Usage: bash port/perf-r26/test/test.sh [dir with the patched units, default the r26 work copy's dyn-r26]
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
dt=$(cd "$here/../dynamic-timing" && pwd)
units=${1:-/home/tomer/ps5-za-native/perf-r26-20261029/dyn-r26}
cc=${CC:-clang-21}
out=$(mktemp -d /tmp/za-r26-tests.XXXXXX)
trap 'rm -rf "$out"' EXIT
warn=(-std=c11 -Wall -Wextra -Werror -Wshadow -Wno-sign-conversion)
san=(-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=all)
tsan=(-O1 -g -fsanitize=thread)
echo "== compiler: $("$cc" --version | head -1)"

echo "== 1. port/dynamic-timing/test/test_glue.c against za_dyn_glue_r26.c (ASan + UBSan)"
"$cc" "${warn[@]}" "${san[@]}" -ffp-contract=off -I"$dt" -I"$here" \
    -Dllround=za_dt_llround "$dt/za_dyn_timing.c" "$here/za_dyn_glue_r26.c" "$dt/test/test_glue.c" -lm -lpthread -o "$out/test_glue"
"$out/test_glue" | tail -8

echo "== 2a. test_r26_glue.c (ASan + UBSan)"
"$cc" "${warn[@]}" "${san[@]}" -ffp-contract=off -I"$dt" -I"$here" \
    -Dllround=za_dt_llround "$dt/za_dyn_timing.c" "$here/za_dyn_glue_r26.c" "$here/test/test_r26_glue.c" -lm -lpthread -o "$out/test_r26"
"$out/test_r26"
echo "== 2b. test_r26_glue.c and test_glue.c (TSan)"
"$cc" "${warn[@]}" "${tsan[@]}" -ffp-contract=off -I"$dt" -I"$here" \
    -Dllround=za_dt_llround "$dt/za_dyn_timing.c" "$here/za_dyn_glue_r26.c" "$here/test/test_r26_glue.c" -lm -lpthread -o "$out/test_r26_tsan"
TSAN_OPTIONS=halt_on_error=1 "$out/test_r26_tsan" | tail -2
"$cc" "${warn[@]}" "${tsan[@]}" -ffp-contract=off -I"$dt" -I"$here" \
    -Dllround=za_dt_llround "$dt/za_dyn_timing.c" "$here/za_dyn_glue_r26.c" "$dt/test/test_glue.c" -lm -lpthread -o "$out/test_glue_tsan"
TSAN_OPTIONS=halt_on_error=1 "$out/test_glue_tsan" | tail -1

echo "== 3. test_options.c (ASan + UBSan)"
"$cc" "${warn[@]}" "${san[@]}" -I"$here" "$here/test/test_options.c" -o "$out/test_options"
"$out/test_options"

echo "== 3b. analyze_r26.py on a synthetic klog"
python3 -I "$here/test/test_analyze.py"

echo "== 4. hook signatures from the patched units ($units)"
{
    echo '#include <stdint.h>'
    echo '#include "za_dyn_glue_r26.h"'
    grep -ohE 'extern [a-z0-9_]+ za_dt_[a-z_]+\([^)]*\);' "$units"/main_*.c | sort -u
} > "$out/signatures.c"
grep -c 'extern' "$out/signatures.c" | sed 's/^/   distinct declarations: /'
grep 'extern' "$out/signatures.c" | sed 's/^/   /'
"$cc" -std=c11 -Wall -Wextra -Werror -I"$here" -c "$out/signatures.c" -o "$out/signatures.o"
echo "   compatible with za_dyn_glue.h"

sdk=/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk
work=$(dirname "$units")
if [ -d "$sdk/target/include" ]; then
    echo "== 5. PS5 target compile (-target x86_64-sie-ps5, the title's flags, -Werror)"
    ps5=(/usr/bin/clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default -isysroot "$sdk"
         -isystem "$sdk/target/include" -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee
         -O2 -march=x86-64-v3 -DZA_PS5 -std=c11 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
    "${ps5[@]}" -I"$dt" -Dllround=za_dt_llround -c "$dt/za_dyn_timing.c" -o "$out/za_dyn_timing.o"
    "${ps5[@]}" -I"$here" -c "$here/za_dyn_glue_r26.c" -o "$out/za_dyn_glue_r26.o"
    if /usr/lib/llvm-21/bin/llvm-nm -u "$out/za_dyn_timing.o" "$out/za_dyn_glue_r26.o" | grep -qw llround; then
        echo "llround is still imported" >&2; exit 1; fi
    echo "   no llround import (served by za_dt_llround)"
    if [ -d "$work/source/runtime" ]; then
        "${ps5[@]}" -I"$here" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$here/../title" \
            -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r26-perf"' \
            -c "$here/title_entry-r26.c" -o "$out/title_entry.o"
    fi
    ls -la "$out"/*.o | awk '{print "   " $NF " " $5 " bytes"}'
fi
echo "== all r26 host tests passed"

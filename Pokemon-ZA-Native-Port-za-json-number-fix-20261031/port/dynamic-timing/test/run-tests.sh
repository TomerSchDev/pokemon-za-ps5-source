#!/usr/bin/env bash
# Builds and runs the dynamic-timing host tests (WSL Ubuntu, clang). Binaries go to a temporary directory;
# nothing is written into the repository. Usage: bash port/dynamic-timing/test/run-tests.sh
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cc=${CC:-$(command -v clang-21 || command -v clang)}
out=$(mktemp -d /tmp/za-dyn-tests.XXXXXX)
trap 'rm -rf "$out"' EXIT
warn=(-std=c11 -Wall -Wextra -Werror -Wshadow -Wconversion -Wno-sign-conversion -Wdouble-promotion -Wno-error=double-promotion)
san=(-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=all)
echo "== compiler: $("$cc" --version | head -1)"

echo "== model tests (ASan + UBSan, -ffp-contract=off)"
"$cc" "${warn[@]}" "${san[@]}" -ffp-contract=off -I"$here" \
    "$here/za_dyn_timing.c" "$here/za_rc3_reference.c" "$here/test/test_dyn_timing.c" -lm -o "$out/test_dyn_timing"
"$out/test_dyn_timing"

echo "== glue tests (ASan + UBSan, 4 reader threads)"
"$cc" "${warn[@]}" "${san[@]}" -ffp-contract=off -I"$here" \
    "$here/za_dyn_timing.c" "$here/za_dyn_glue.c" "$here/test/test_glue.c" -lm -lpthread -o "$out/test_glue"
"$out/test_glue"

echo "== model tests again: -O2 -march=x86-64-v3 (FMA contraction allowed, as the PS5 flags)"
"$cc" "${warn[@]}" -O2 -march=x86-64-v3 -I"$here" \
    "$here/za_dyn_timing.c" "$here/za_rc3_reference.c" "$here/test/test_dyn_timing.c" -lm -o "$out/test_dyn_timing_o2"
"$out/test_dyn_timing_o2" > "$out/o2.txt" || { cat "$out/o2.txt"; exit 1; }
tail -1 "$out/o2.txt"

sdk=${PS5_SDK:-/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk}
ps5cc=/usr/bin/clang-21
if [ -d "$sdk/target/include" ] && [ -x "$ps5cc" ]; then
    echo "== PS5 target compile check (-target x86_64-sie-ps5, the title's unit flags, -Werror)"
    for f in za_dyn_timing.c za_dyn_glue.c; do
        "$ps5cc" -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default -isysroot "$sdk" \
            -isystem "$sdk/target/include" -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
            -O2 -march=x86-64-v3 -DZA_PS5 -std=c11 -Wall -Wextra -Werror -I"$here" \
            -c "$here/$f" -o "$out/${f%.c}.o"
        echo "   $f -> $(stat -c %s "$out/${f%.c}.o") bytes"
    done
else
    echo "== PS5 target compile check skipped (no SDK at $sdk)"
fi
echo "== all dynamic-timing tests passed"

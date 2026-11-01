#!/usr/bin/env bash
# Does not clone automatically, mutate the installed runtime, or contact PS5.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=/home/tomer/ps5-za-native/shader-prewarm-research
pin=f0bd0257c308b9a26562c1a30c4748a0219cc951
[[ $(git -C "$work/glslang" rev-parse HEAD) == "$pin" ]] || { echo 'glslang pin differs' >&2; exit 2; }
for target in host ps5; do
    options=()
    [[ $target != ps5 ]] || options+=("-DCMAKE_TOOLCHAIN_FILE=$root/ps5-toolchain.cmake")
    cmake -S "$root" -B "$work/$target-build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        "-DGLSLANG_SOURCE=$work/glslang" "${options[@]}" > "$work/$target-configure.log" 2>&1
    cmake --build "$work/$target-build" -j 4 > "$work/$target-build-final.log" 2>&1
done
bash "$root/link-check.sh" > "$work/ps5-link-final.log" 2>&1
python3 "$root/test_compiler.py" --probe "$work/host-build/compiler-probe" \
    --captured "$root/../../evidence/randomizer-shaders-20261028-041124Z" \
    --out "$root/../../evidence/shader-prewarm-research-20261028/compiler"

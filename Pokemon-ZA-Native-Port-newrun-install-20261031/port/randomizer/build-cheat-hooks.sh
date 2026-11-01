#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=/home/tomer/ps5-za-native/title-r1-20261027
sdk=/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk
research='/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc'
candidate=$work/cheats-r12
python3 "$root/port/randomizer/prepare-cheat-hooks.py" "$research/update-2.0.2-20261025/aot/main" "$research/update-2.0.2-20261025/game/exefs/main" "$candidate"
cp "$candidate/hook-manifest.json" "$root/evidence/randomizer-r12-cheat-hooks.json"
cd "$work/source"
for unit in main_145 main_209; do
    if grep -qw "main/$unit" build/ps5/gen/giants.mk; then echo 'Unexpected unit optimization policy' >&2;exit 2;fi
    clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default \
        -isysroot "$sdk" -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" \
        -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
        -O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label \
        -fvisibility=hidden -Iruntime -march=x86-64-v3 -DZA_PS5 \
        -c "$candidate/$unit.c" -o "$candidate/$unit.o"
done
cp --reflink=auto "$work/fps-r13/liblasgame-r13.a" "$candidate/liblasgame-r12.a"
"$sdk/bin/llvm-ar" rcs "$candidate/liblasgame-r12.a" "$candidate/main_145.o" "$candidate/main_209.o"
"$sdk/bin/llvm-nm" --undefined-only "$candidate/main_145.o" "$candidate/main_209.o" | grep za_cheat

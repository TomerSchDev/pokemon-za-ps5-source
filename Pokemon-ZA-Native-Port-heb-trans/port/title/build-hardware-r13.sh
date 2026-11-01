#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=${TITLE_WORK:-/home/tomer/ps5-za-native/title-r1-20261027}
vulkan=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
sdk=$vulkan/.deps/native/ps5-payload-sdk
research=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc
candidate=$work/fps-r13
python3 "$root/port/title/prepare-fps-hook.py" \
    "$research/update-2.0.2-20261025/aot/main/main_660.c" \
    "$research/update-2.0.2-20261025/game/exefs/main" "$candidate"
cp "$candidate/hook-manifest.json" "$root/evidence/title-r13-fps-hook.json"
clang-21 -std=c11 -Wall -Wextra -Werror "$root/port/title/test-performance.c" -o "$candidate/test-performance"
"$candidate/test-performance" | tee "$root/evidence/title-r13-performance-tests.txt"
cd "$work/source"
if grep -qw 'main/main_660' build/ps5/gen/giants.mk; then
    echo 'Unexpected optimization policy for main_660; refusing' >&2; exit 2
fi
# Match the baseline unit's PS5 flags. Only this alternative object is rebuilt.
/usr/bin/clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default \
    -isysroot "$sdk" -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" \
    -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
    -O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label \
    -fvisibility=hidden -Iruntime -march=x86-64-v3 -DZA_PS5 \
    -c "$candidate/main_660.c" -o "$candidate/main_660.o"
cp --reflink=auto build/ps5/liblasgame.a "$candidate/liblasgame-r13.a"
"$sdk/bin/llvm-ar" rcs "$candidate/liblasgame-r13.a" "$candidate/main_660.o"
"$sdk/bin/llvm-nm" --undefined-only "$candidate/main_660.o" | grep za_title_frame_cfg
TITLE_REV=r13 TITLE_GAMELIB="$candidate/liblasgame-r13.a" bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r13-hardware" bash "$root/port/title/package-title.sh"

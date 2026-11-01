#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
sdk=/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk
mkdir -p "$root/artifacts/randomizer-launcher"
"$sdk/bin/prospero-clang" -O2 -Wall -Wextra -Werror '-DZA_LAUNCH_ID="PPSA91762"' \
    '-DZA_LAUNCH_LOG="/data/za-native-randomizer-launch.log"' "$root/port/title/launch_title.c" \
    -lSceSystemService -lSceUserService -o "$root/artifacts/randomizer-launcher/za_native_randomizer_launch.elf"

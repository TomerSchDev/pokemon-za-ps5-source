#!/usr/bin/env bash
# Cross-compiles the rando-v2 sources for the PS5 title exactly as port/randomizer/build-randomizer.sh compiles the
# randomizer (prospero-clang18 wrapper, clang 21, -Werror), into a scratch folder. Nothing is linked or installed.
#   bash build-check-ps5.sh OUT_DIR
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=${1:?OUT_DIR}
mkdir -p "$out"
work=/home/tomer/ps5-za-native/perf-r26p1-20261029
hashes=$work/objects-r26p1  # compare against the actual installed baseline, including observer integration
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
deps='/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib'
cc(){ sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
incs=(-I"$root/port/rando-v2" -I"$work/port/sdl3-shim/include" -I"/home/tomer/ps5-za-native/PS5_Mesa/include"
      -I"$work/source/runtime" -I"$root/port/title" -I"$hashes" -I"$root/port/randomizer" -I"$root/port/randomizer/core"
      -I"$deps/json/include" -I"$deps/mbedtls/include")
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
cxx=(-std=c++20 -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 -DZA_RANDOMIZER_PS5=1)
for f in za_player_name name_keyboard run_name native_menu; do
    echo "[rando-v2] $f.cpp"
    # The name writer uses the incremental SHA-256 API: same Mbed TLS config as the library objects.
    cc "${cxx[@]}" "${flags[@]}" "${incs[@]}" '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' \
        -c "$root/port/rando-v2/$f.cpp" -o "$out/$f.o"
done
# Symbol-level link check against the last randomizer object set, with these objects replacing native_menu.o:
# no duplicate strong definitions, and every import is either defined there or already imported by it.
nm=/usr/lib/llvm-21/bin/llvm-nm
new=("$out/za_player_name.o" "$out/name_keyboard.o" "$out/run_name.o" "$out/native_menu.o")
syms(){ "$nm" "$@" 2>/dev/null | awk 'NF>=2{print $NF}' | grep -v ':$' | sort -u; }
old=$(ls "$hashes"/*.o | grep -v '/native_menu.o$')
syms --defined-only -g $old > "$out/old-defined.txt"
syms -u $old "$hashes/native_menu.o" > "$out/old-imports.txt"
syms --defined-only -g "${new[@]}" > "$out/new-defined.txt"
dup=$("$nm" --defined-only -g "${new[@]}" |
      awk 'NF==3 && $2 ~ /[TDBR]/ {print $3}' | sort -u | comm -12 - "$out/old-defined.txt")
missing=$(syms -u "${new[@]}" | comm -23 - "$out/new-defined.txt" |
          comm -23 - "$out/old-defined.txt" | comm -23 - "$out/old-imports.txt")
lost=$("$nm" --defined-only -g "$hashes/native_menu.o" | awk 'NF==3 && $2 ~ /[TDBR]/ {print $3}' | sort -u |
       comm -23 - "$out/new-defined.txt")
echo "[rando-v2] duplicate definitions: ${dup:-none}"
echo "[rando-v2] imports the title does not already resolve: ${missing:-none}"
echo "[rando-v2] old native_menu.o exports not provided: ${lost:-none}"
[ -z "$dup$missing$lost" ] || { echo "[rando-v2] link check FAILED"; exit 1; }
echo "[rando-v2] OK: $(ls "$out"/*.o | wc -l) objects compile with -Werror; symbol link check passed"

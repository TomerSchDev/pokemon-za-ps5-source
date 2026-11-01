#!/usr/bin/env bash
# r29-music host tests (WSL clang-21, ASan/UBSan, -Werror, console JSON configuration: no exceptions).
#   bash run-host-tests.sh PLAN.json ROMFS_BIN OUT_DIR
# Reads the game's BGM.bnk read-only from ROMFS_BIN; writes only below OUT_DIR (must be new; keep it out of git).
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
music=$(cd "$here/.." && pwd)
project=$(cd "$music/../.." && pwd)
plan=$1 romfs=$2 out=$3
[[ ! -e $out ]] || { echo "OUT_DIR must be new: $out" >&2; exit 2; }
mkdir -p "$out/bin"
deps=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib
mbed=$deps/mbedtls
core=$project/port/randomizer/core
san=(-fsanitize=address,undefined -fno-sanitize-recover=all)
flags=(-O1 -g "${san[@]}" -Wall -Wextra -Werror -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1)
cfg=(-I"$mbed/include" -I"$core" -I"$project/port/randomizer" -I"$deps/json/include" -I"$music" '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"')
for c in sha256 platform_util; do
    clang-21 -std=c11 -O1 -g "${san[@]}" "${cfg[@]}" -c "$mbed/library/$c.c" -o "$out/bin/mbed_$c.o"
done
mbedobjs=("$out/bin/mbed_sha256.o" "$out/bin/mbed_platform_util.o")
{
echo "== r29-music host tests $(date -u +%FT%TZ)"
sha256sum "$music/za_music.cpp" "$music/za_music.hpp" "$music/run_store_music.cpp" "$here/test_music.cpp" \
    "$here/test_compat.cpp" "$here/oracle_music.py" "$music/tools/za_bgm.py" "$plan"
clang++-21 -std=c++20 "${flags[@]}" "${cfg[@]}" "$music/za_music.cpp" "$music/run_store_music.cpp" "$core/randomizer.cpp" \
    "$here/test_music.cpp" "${mbedobjs[@]}" -o "$out/bin/test_music"
"$out/bin/test_music" "$plan" "$romfs" "$out"
clang++-21 -std=c++20 "${flags[@]}" "${cfg[@]}" "$project/port/randomizer/run_store.cpp" "$core/randomizer.cpp" \
    "$here/test_compat.cpp" "${mbedobjs[@]}" -o "$out/bin/test_compat"
"$out/bin/test_compat" "$out/runs" r1-music r2-plain r3-chaos
python3 -I "$here/oracle_music.py" "$plan" "$romfs" "$out"
echo "== all r29-music host tests passed"
} 2>&1 | tee "$out/host-tests.log"

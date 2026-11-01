#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
own=$(cd "$here/.." && pwd)
aot=${1:-/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/aot}
nso=${2:-$aot/../game/exefs/main}
cc=${CC:-clang-21}
tmp=$(mktemp -d -t dlc-dex-host.XXXXXXXX)
trap 'rm -rf "$tmp"' EXIT
python3 "$own/prepare_dlc_dex_hook.py" --aot "$aot" --nso "$nso" --out "$tmp/gen"
python3 "$here/extract_functions.py" "$aot" "$tmp/gen" "$tmp/inc"
flags=(-std=gnu11 -O1 -g -Wall -Wextra -Werror -Wno-unused-label -Wno-unused-parameter -Wno-unused-function)
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
for trace in off on; do
  extra=()
  if [[ $trace == on ]]; then extra=(-DZA_DLC_DEX_TRACE=1); fi
  "$cc" "${flags[@]}" "${san[@]}" "${extra[@]}" -I"$aot/source/runtime" -I"$tmp/inc" "$here/test_native.c" -o "$tmp/test-native-$trace"
  ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=print_stacktrace=1 "$tmp/test-native-$trace"
done
python3 "$here/test_patcher.py" "$aot" "$nso"
# Full units compile without adding any defined game symbol or other import.
gflags=(-O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label -fvisibility=hidden -march=x86-64-v3)
"$cc" "${gflags[@]}" -I"$aot/source/runtime" -c "$aot/main/main_287.c" -o "$tmp/orig.o"
"$cc" "${gflags[@]}" -I"$aot/source/runtime" -c "$tmp/gen/main_287.c" -o "$tmp/patched.o"
cmp <(nm --defined-only "$tmp/orig.o" | awk '{print $NF}' | sort) <(nm --defined-only "$tmp/patched.o" | awk '{print $NF}' | sort)
added=$(comm -13 <(nm -u "$tmp/orig.o" | awk '{print $NF}' | sort) <(nm -u "$tmp/patched.o" | awk '{print $NF}' | sort))
[[ $added == za_dlc_dex_unlock_pump ]]
"$cc" "${flags[@]}" -DGUEST_VOLATILE -DZA_DLC_DEX_TRACE=1 -DZA_DLC_DEX_KLOG=1 -I"$aot/source/runtime" -c "$own/za_dlc_dex_unlock.c" -o "$tmp/helper.o"
echo 'ALL DLC DEX HOST TESTS PASSED; console/save persistence not tested.'

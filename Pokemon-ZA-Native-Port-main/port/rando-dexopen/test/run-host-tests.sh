#!/usr/bin/env bash
# Host tests for rando-dexopen (WSL/Linux): ASan + UBSan harness over the two real generated functions, original and
# patched, plus the patcher's guard tests. Reads the translated game code only; writes only to a temporary folder.
#   bash test/run-host-tests.sh [AOT_DIR]
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
own=$(cd "$here/.." && pwd)
aot=${1:-/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/aot}
nso=$aot/../game/exefs/main
cc=${CC:-clang-21}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
echo "== patcher: prepare main_287.c + main_115.c"
python3 "$own/prepare-dexopen-hooks.py" "$aot/main" "$nso" "$tmp/gen" > "$tmp/manifest.out"
python3 "$here/extract-functions.py" "$aot/main" "$tmp/gen" "$tmp/inc"
echo "== harness: ASan + UBSan (trace on: the [dexopen] lines below are the test's own)"
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
"$cc" -std=gnu11 -O1 -g "${san[@]}" -Wall -Wextra -Werror -Wno-unused-label -Wno-unused-parameter \
  -DZA_DEXOPEN_TRACE=1 -I"$aot/source/runtime" -I"$own" -I"$tmp/inc" "$here/test_dexopen.c" "$own/za_dexopen.c" -lpthread -o "$tmp/test_dexopen"
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=print_stacktrace=1 "$tmp/test_dexopen"
echo "== za_dexopen.c alone: -Wall -Wextra -Werror -pedantic (C11), trace off / on / on+klog"
"$cc" -std=c11 -pedantic -Wall -Wextra -Werror -c "$own/za_dexopen.c" -o "$tmp/a.o"
"$cc" -std=c11 -pedantic -Wall -Wextra -Werror -DZA_DEXOPEN_TRACE=1 -c "$own/za_dexopen.c" -o "$tmp/b.o"
"$cc" -std=c11 -pedantic -Wall -Wextra -Werror -DZA_DEXOPEN_TRACE=1 -DZA_DEXOPEN_KLOG=1 -c "$own/za_dexopen.c" -o "$tmp/c.o"
echo "== patched units compile with the game flags; same defined symbols; new imports = the one za_dexopen entry point each"
gflags=(-O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label -fvisibility=hidden -march=x86-64-v3)
for u in main_287 main_115; do
  "$cc" "${gflags[@]}" -I"$aot/source/runtime" -c "$tmp/gen/$u.c" -o "$tmp/$u.o"
  "$cc" "${gflags[@]}" -I"$aot/source/runtime" -c "$aot/main/$u.c" -o "$tmp/$u.orig.o"
  cmp <(nm --defined-only "$tmp/$u.orig.o" | awk '{print $NF}' | sort) <(nm --defined-only "$tmp/$u.o" | awk '{print $NF}' | sort)
  added=$(comm -13 <(nm -u "$tmp/$u.orig.o" | awk '{print $NF}' | sort) <(nm -u "$tmp/$u.o" | awk '{print $NF}' | sort) | tr '\n' ' ')
  echo "$u: new imports: $added"
  case "$u:$added" in
    "main_287:za_dexopen_hyperspace_dex_enabled "|"main_115:za_dexopen_mega_dex_flag ") ;;
    *) echo "unexpected imports"; exit 1 ;;
  esac
done
echo "== patcher guards"
python3 "$here/test_patcher.py" "$aot/main" "$nso"
echo "ALL HOST TESTS PASSED"

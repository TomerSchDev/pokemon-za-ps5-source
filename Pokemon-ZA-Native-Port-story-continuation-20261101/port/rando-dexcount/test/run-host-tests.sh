#!/usr/bin/env bash
# Host tests for rando-dexcount (WSL/Linux): ASan + UBSan harness over the two real generated functions, original and
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
echo "== patcher: prepare main_310.c + main_261.c"
python3 "$own/prepare-dexcount-hooks.py" "$aot/main" "$nso" "$tmp/gen" > "$tmp/manifest.out"
python3 "$here/extract-evaluator.py" "$aot/main" "$tmp/gen" "$tmp/inc"
echo "== harness: ASan + UBSan"
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
"$cc" -std=gnu11 -O1 -g "${san[@]}" -Wall -Wextra -Werror -Wno-unused-label -Wno-unused-parameter \
  -I"$aot/source/runtime" -I"$own" -I"$tmp/inc" "$here/test_dexcount.c" "$own/za_dexcount.c" -lpthread -o "$tmp/test_dexcount"
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=print_stacktrace=1 "$tmp/test_dexcount"
echo "== za_dexcount.c alone: -Wall -Wextra -Werror -pedantic (C11), trace on and off"
"$cc" -std=c11 -pedantic -Wall -Wextra -Werror -c "$own/za_dexcount.c" -o "$tmp/a.o"
"$cc" -std=c11 -pedantic -Wall -Wextra -Werror -DZA_DEXCOUNT_TRACE=1 -c "$own/za_dexcount.c" -o "$tmp/b.o"
"$cc" -std=c11 -pedantic -Wall -Wextra -Werror -DZA_DEXCOUNT_TRACE=1 -DZA_DEXCOUNT_KLOG=1 -c "$own/za_dexcount.c" -o "$tmp/c.o"
echo "== patched units compile with the game flags; same defined symbols; new imports = za_dexcount entry points only"
gflags=(-O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label -fvisibility=hidden -march=x86-64-v3)
for u in main_310 main_261; do
  "$cc" "${gflags[@]}" -I"$aot/source/runtime" -c "$tmp/gen/$u.c" -o "$tmp/$u.o"
  "$cc" "${gflags[@]}" -I"$aot/source/runtime" -c "$aot/main/$u.c" -o "$tmp/$u.orig.o"
  cmp <(nm --defined-only "$tmp/$u.orig.o" | awk '{print $NF}' | sort) <(nm --defined-only "$tmp/$u.o" | awk '{print $NF}' | sort)
  added=$(comm -13 <(nm -u "$tmp/$u.orig.o" | awk '{print $NF}' | sort) <(nm -u "$tmp/$u.o" | awk '{print $NF}' | sort) | tr '\n' ' ')
  echo "$u: new imports: $added"
  case "$u:$added" in
    "main_310:za_dexcount_combine za_dexcount_extra_enabled "|"main_261:za_dexcount_display za_dexcount_extra_enabled ") ;;
    *) echo "unexpected imports"; exit 1 ;;
  esac
done
echo "== patcher guards"
python3 "$here/test_patcher.py" "$aot/main" "$nso"
echo "ALL HOST TESTS PASSED"

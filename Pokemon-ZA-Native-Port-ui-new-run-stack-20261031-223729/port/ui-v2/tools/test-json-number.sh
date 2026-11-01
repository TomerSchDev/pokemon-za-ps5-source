#!/usr/bin/env bash
# Read-only input regression. All objects and logs go into a NEW output folder.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
out=${1:?new output directory}
assets=${ZA_UI_ASSETS:?complete frozen v3 asset directory}
platform=${ZA_JSON_PLATFORM_SOURCE:-/home/tomer/ps5-za-native/r29ui-codex-20261031-final-01/tree/source/runtime/platform/ps5.c}
deps=${ZA_DEPS:-/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib}
[[ ! -e $out ]] || { echo 'Output must be new' >&2; exit 2; }
mkdir -p "$out"
python3 - "$platform" "$out/platform-number.c" <<'PY'
import pathlib, sys
text = pathlib.Path(sys.argv[1]).read_text()
start = text.index('double plat_strtod(const char *s, char **end) {')
end = text.index('\nint plat_open_file', start)
pathlib.Path(sys.argv[2]).write_text('#include <stdbool.h>\n#include <stdint.h>\n#include <math.h>\n#include <strings.h>\n' + text[start:end])
PY
cat > "$out/broken-libc.c" <<'C'
#include <locale.h>
#include <stdlib.h>
#ifdef EMPTY_LOCALE
struct lconv *__wrap_localeconv(void) {
    static char empty[] = "";
    static struct lconv lc;
    lc.decimal_point = empty;
    return &lc;
}
#endif
#ifdef BROKEN_STRTOD
double __wrap_strtod(const char *text, char **end) { return (double)strtoll(text, end, 10); }
#endif
C
cc=${CC:-clang-21}
cxx=${CXX:-clang++-21}
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
flags=(-std=c++17 -O1 -g -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 -I"$deps/json/include" "${san[@]}")
"$cc" -std=c11 -O1 -g "${san[@]}" -Wall -Wextra -Werror -c "$root/src/json_number_ps5.c" -o "$out/json_number_ps5.o"
"$cc" -std=c11 -O1 -g "${san[@]}" -c "$out/platform-number.c" -o "$out/platform-number.o"
"$cc" -std=c11 -O1 -g -DEMPTY_LOCALE -c "$out/broken-libc.c" -o "$out/empty-locale.o"
"$cc" -std=c11 -O1 -g -DBROKEN_STRTOD -c "$out/broken-libc.c" -o "$out/broken-strtod.o"
"$cxx" "${flags[@]}" -c "$root/test/test_json_number.cpp" -o "$out/test.o"
"$cxx" "${san[@]}" "$out/test.o" -pthread -o "$out/reference"
"$cxx" "${san[@]}" "$out/test.o" "$out/empty-locale.o" -Wl,--wrap=localeconv -pthread -o "$out/control-empty-locale"
"$cxx" "${san[@]}" "$out/test.o" "$out/broken-strtod.o" -pthread -Wl,--wrap=strtod -o "$out/control-broken-strtod"
"$cxx" "${san[@]}" "$out/test.o" "$out/json_number_ps5.o" "$out/platform-number.o" -pthread -Wl,--wrap=localeconv -Wl,--wrap=strtod -o "$out/fixed"
ulimit -c 0
set +e
"$out/control-empty-locale" --probe > "$out/control-empty-locale.log" 2>&1
empty_rc=$?
"$out/control-broken-strtod" --probe > "$out/control-broken-strtod.log" 2>&1
strtod_rc=$?
set -e
[[ $empty_rc == 134 && $strtod_rc == 134 ]] || { echo "Control mismatch: $empty_rc $strtod_rc"; exit 1; }
grep -q 'endptr == token_buffer.data() + token_buffer.size()' "$out/control-empty-locale.log"
grep -q 'endptr == token_buffer.data() + token_buffer.size()' "$out/control-broken-strtod.log"
"$out/reference" "$assets" > "$out/reference.log" 2> "$out/reference.stderr"
"$out/fixed" "$assets" > "$out/fixed.log" 2> "$out/fixed.stderr"
cmp "$out/reference.log" "$out/fixed.log"
sha256sum "$root/src/json_number_ps5.c" "$root/test/test_json_number.cpp" "$platform" > "$out/source-sha256.txt"
printf 'PASS: both broken controls reproduce scan_number assertion (134); wrapped parser equals host reference across metadata corpus\n'
cat "$out/fixed.log" "$out/fixed.stderr"

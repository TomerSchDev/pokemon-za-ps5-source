#!/usr/bin/env bash
# r28a texfix host tests (WSL / Linux x86-64): the headers the build copies into the runtime, under ASan + UBSan and
# under TSan, plus the negative control (r28-play's live list in the same scenario: it must fail the way the console
# did). Usage: run-host-tests.sh <out dir>   (logs and binaries there; nothing else is written)
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=${1:?out dir}
mkdir -p "$out"
cc=${CC:-clang-21}
flags=(-std=c11 -g -O1 -Wall -Wextra -Werror -fno-omit-frame-pointer -pthread)
"$cc" --version | head -1 | tee "$out/compiler.txt"
sha256sum "$here"/../src/*.h "$here"/*.c "$here"/*.h > "$out/inputs.sha256"

echo "== ASan + UBSan"
"$cc" "${flags[@]}" -fsanitize=address,undefined -fno-sanitize-recover=all "$here/test_texfix.c" -o "$out/test_asan"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
    "$out/test_asan" > "$out/asan-ubsan.log" 2>&1 || { cat "$out/asan-ubsan.log"; echo "ASan/UBSan run FAILED"; exit 1; }
grep -E '^ok |ALL TESTS PASSED' "$out/asan-ubsan.log"

echo "== TSan"
"$cc" "${flags[@]}" -fsanitize=thread "$here/test_texfix.c" -o "$out/test_tsan"
TSAN_OPTIONS=halt_on_error=1:second_deadlock_stack=1 \
    "$out/test_tsan" > "$out/tsan.log" 2>&1 || { cat "$out/tsan.log"; echo "TSan run FAILED"; exit 1; }
grep -E 'ALL TESTS PASSED' "$out/tsan.log"
! grep -q 'WARNING: ThreadSanitizer' "$out/tsan.log"

echo "== negative control: r28-play's live list, same scenario"
"$cc" "${flags[@]}" -fsanitize=address "$here/test_old_livelist.c" -o "$out/old_asan"
set +e
ASAN_OPTIONS=halt_on_error=1 "$out/old_asan" uaf > "$out/old-uaf.log" 2>&1
rc_uaf=$?
"$cc" "${flags[@]}" "$here/test_old_livelist.c" -o "$out/old_plain"
"$out/old_plain" reuse > "$out/old-reuse.log" 2>&1
rc_reuse=$?
set -e
grep -q 'heap-use-after-free' "$out/old-uaf.log" && [[ $rc_uaf != 0 ]] \
    || { cat "$out/old-uaf.log"; echo "control: expected ASan heap-use-after-free"; exit 1; }
echo "old list, freed entry: ASan heap-use-after-free (exit $rc_uaf)"
[[ $rc_reuse == 42 ]] && grep -q 'fault address 0xa2' "$out/old-reuse.log" \
    || { cat "$out/old-reuse.log"; echo "control: expected SIGSEGV at 0xa2"; exit 1; }
grep 'fault address' "$out/old-reuse.log"
echo "ALL HOST TESTS PASSED (logs: $out)"

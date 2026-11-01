#!/usr/bin/env bash
# Host test of the slot.zrs writer (runtime/services/save_slot.c) under ASan + UBSan, then once more without sanitizers.
# Run in Linux / WSL:  bash tools/save_slot/test.sh [out dir]   (ZA_SLOT_FIXTURE_RUN=<launcher-made run folder> optional)
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=${1:-$root/build/save-slot-test}
cc=${CC:-cc}
mkdir -p "$out"
flags=(-std=gnu11 -O1 -g -Wall -Wextra -Wno-unused-function -Wno-unused-parameter -Wno-sign-compare -pthread -DSAVE_SLOT_TEST
       '-DSAVE_SLOT_LOG(...)=test_log(__VA_ARGS__)' -include "$root/tools/save_slot/test_log.h")
"$cc" "${flags[@]}" -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer \
    "$root/runtime/services/save_slot.c" "$root/tools/save_slot/test_save_slot.c" -o "$out/test_save_slot_san"
"$cc" "${flags[@]}" -O2 "$root/runtime/services/save_slot.c" "$root/tools/save_slot/test_save_slot.c" -o "$out/test_save_slot"
echo "== ASan + UBSan"; TMPDIR=${TMPDIR:-$out} "$out/test_save_slot_san"
echo "== plain -O2"; TMPDIR=${TMPDIR:-$out} "$out/test_save_slot"

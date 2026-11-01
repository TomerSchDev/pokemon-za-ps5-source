#!/bin/bash
# Host test of the RomFS overlay's bounded host file descriptors (runtime/services/fs.c, tools/test_fs_overlay_fds.c):
# 2500 loose files read in order, then by 8 threads at random, under a 1024-descriptor limit like the PS5 title's.
# Linux only. Usage: tools/test_fs_overlay_fds.sh [files]   (also under ASan / TSan: CFLAGS=-fsanitize=thread)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/fs_overlay_test"
mkdir -p "$OUT"
CC="${CC:-clang}"  # (the runtime headers use clang builtins)
$CC -std=gnu11 -O1 -g -pthread -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 -Wall -Wno-unused-function -Wno-format -Wno-unused-result ${CFLAGS:-} \
    -I"$ROOT/runtime" -I"$ROOT/runtime/nvn" "$ROOT/tools/test_fs_overlay_fds.c" -o "$OUT/test_fs_overlay_fds" \
    -no-pie -Wl,--unresolved-symbols=ignore-all  # (fs.c's services are never called here)
"$OUT/test_fs_overlay_fds" "$@"

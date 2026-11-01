#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
sdk=/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk
work=/home/tomer/ps5-za-native/title-r1-20261027/branding-r13
mkdir -p "$work" "$root/artifacts/title-r13-branding"
if [[ ! -f $work/sqlite3.o || $root/artifacts/sqlite-source/sqlite3.c -nt $work/sqlite3.o ]]; then
"$sdk/bin/prospero-clang" -O2 -DSQLITE_THREADSAFE=1 -DSQLITE_OMIT_LOAD_EXTENSION \
    -DSQLITE_TEMP_STORE=3 -DSQLITE_DEFAULT_MEMSTATUS=0 \
    -c "$root/artifacts/sqlite-source/sqlite3.c" -o "$work/sqlite3.o"
fi
"$sdk/bin/prospero-clang" -O2 -Wall -Wextra -Werror -I"$root/artifacts/sqlite-source" \
    "$root/port/title/rename_title.c" "$work/sqlite3.o" -lpthread \
    -o "$root/artifacts/title-r13-branding/za_rename_title.elf"

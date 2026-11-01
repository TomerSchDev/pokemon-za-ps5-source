#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/batch-r20b-20261028
mkdir -p "$work/host-tests" "$project/evidence/submission-r20b"
exec > >(tee "$project/evidence/submission-r20b/tests.log") 2>&1
clang-21 -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -pthread \
    -I/home/tomer/ps5-za-native/PS5_Mesa/include -I"$root" "$root/test-executor.c" -o "$work/host-tests/test-executor"
ASAN_OPTIONS=detect_leaks=1 "$work/host-tests/test-executor"
t=$(mktemp -d "$work/host-tests/observer-XXXXXX")
clang-21 -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -pthread \
    -I"$project/port/observer-r17" -I"$root" -DZA_OBSERVER_HOST_TEST=1 \
    "-DZA_OBSERVER_ROOT=\"$t/store\"" "-DZA_OBSERVER_ENABLE=\"$t/enable.txt\"" \
    "$root/test-observer.c" -o "$t/test"
ASAN_OPTIONS=detect_leaks=1 "$t/test"

#!/usr/bin/env bash
set -euo pipefail
p=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
t=$(mktemp -d /tmp/za-r19-input-XXXXXX)
clang-21 -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -pthread \
    -I"$p/../observer-r17" -DZA_OBSERVER_HOST_TEST=1 \
    "-DZA_OBSERVER_ROOT=\"$t/store\"" "-DZA_OBSERVER_ENABLE=\"$t/enable.txt\"" \
    "$p/test-observer-r19.c" -o "$t/test"
"$t/test"

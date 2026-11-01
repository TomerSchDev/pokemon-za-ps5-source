#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
out=${1:?isolated output directory required}
mkdir -p "$out"
clang-21 -x c++ -std=c++20 -lstdc++ -pthread -O1 -g -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer -I"$root" \
  "$root/za_money.cpp" "$root/test/test_money.cpp" -o "$out/test_money"
"$out/test_money"

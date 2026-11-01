#!/usr/bin/env bash
set -euo pipefail
renice 10 -p $$ >/dev/null
base_tree=/home/tomer/ps5-za-native/r28a-play-final-20261030
printf 'BASE_TREE=%s\n' "$base_tree"
ls -ld "$base_tree" "$base_tree/source" "$base_tree/r28a" "$base_tree/rando-dexcount" "$base_tree/rando-dexcount-src"
du -sh "$base_tree/source" "$base_tree/port" "$base_tree/inc" "$base_tree/r28a" "$base_tree/rando-dexcount" "$base_tree/rando-dexcount-src"
sha256sum "$base_tree/r28a/llvm-pie.elf" "$base_tree/r28a/eboot.bin" "$base_tree/rando-dexcount/liblasgame-r28-dexcount.a" "$base_tree/rando-dexcount/za_dexcount.o"
printf 'ROOT_FILES\n'
ls -la "$base_tree"
printf 'R28A_FILES\n'
ls -la "$base_tree/r28a"
printf 'RECIPE_FILES\n'
project='/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port'
ls -l "$project/port/runtime-texfix/"*build*.sh
printf 'LINK_TITLE_RECIPE\n'
sed -n '1,230p' "$base_tree/source/tools/ps5/link-title.sh"
printf 'FINAL_BUILD_RECIPE\n'
sed -n '1,280p' "$project/port/runtime-texfix/build-r28a-final.sh"
printf 'RUNTIME_INPUTS\n'
cat "$base_tree/r28a/evidence/runtime-inputs.txt"

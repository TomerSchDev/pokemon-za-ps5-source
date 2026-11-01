#!/usr/bin/env bash
set -euo pipefail
renice 10 -p $$ >/dev/null
work_tree=/home/tomer/ps5-za-native/r28b-dlc-dex-20261030-c01
df -h / /mnt/c
du -sh "$work_tree"
strings "$work_tree/r28a/objects/title_entry.o" | rg 'randomizer-r2|ZA_TITLE' || true
du -sh "$work_tree/r28b" "$work_tree/source" "$work_tree/rando-dexcount"

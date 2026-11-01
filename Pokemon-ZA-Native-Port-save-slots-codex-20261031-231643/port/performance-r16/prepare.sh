#!/usr/bin/env bash
set -euo pipefail
base=/home/tomer/ps5-za-native/title-r1-20261027
dest=/home/tomer/ps5-za-native/perf-r16-20261028
if [[ ! -e "$dest/SNAPSHOT-COMPLETE" ]]; then
    mkdir -p "$dest"
    cp -a --reflink=auto "$base/source" "$base/port" "$base/objects" "$base/evidence" "$base/shaders" "$base/inc" "$base/SNAPSHOT-COMPLETE" "$dest/"
    mkdir -p "$dest/package"
fi
sha256sum "$dest/source/runtime/nvn/vulkan/exec.c"

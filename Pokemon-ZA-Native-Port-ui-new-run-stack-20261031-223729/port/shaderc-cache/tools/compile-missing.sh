#!/usr/bin/env bash
# shaderc-cache: compile the GLSL files a console run left in its missing-shader directory into cache/spirv/<hash>.spv,
# on the PC (WSL / Linux / MSYS2) with glslc or glslangValidator - the two compilers of the same glslang that shaderc
# wraps. Optimisation off (shaderc_optimization_level_zero, what the runtime uses), target Vulkan 1.3 (SPIR-V 1.6) by
# default; index.txt in the missing directory says which Vulkan version each file was asked for.
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Usage: bash compile-missing.sh <missing dir (from the console: <hash>.vert|frag|comp + index.txt)> <cache/spirv dir>
#        [--target-env vulkan1.3|vulkan1.2]
# The file names carry the hash the runtime will look for; nothing is re-hashed here. The runtime then applies its
# own NoContraction pass to vertex shaders when it loads the file (shaders.c no_contraction: idempotent).
set -euo pipefail
[[ $# -ge 2 ]] || { echo "usage: $0 <missing dir> <cache/spirv dir> [--target-env vulkan1.3]" >&2; exit 2; }
src=$1
dst=$2
target=vulkan1.3
[[ ${3:-} == --target-env && -n ${4:-} ]] && target=$4
mkdir -p "$dst"
n=0
for f in "$src"/*.vert "$src"/*.frag "$src"/*.comp "$src"/*.geom "$src"/*.tesc "$src"/*.tese; do
    [[ -f $f ]] || continue
    hash=$(basename "$f")
    hash=${hash%.*}
    out=$dst/$hash.spv
    if command -v glslc > /dev/null; then
        glslc --target-env="$target" -O0 -o "$out" "$f"
    elif command -v glslangValidator > /dev/null; then
        glslangValidator -V --target-env "$target" -o "$out" "$f" > /dev/null
    else
        echo "neither glslc nor glslangValidator was found" >&2
        exit 2
    fi
    n=$((n + 1))
done
echo "compiled $n shader(s) from $src into $dst ($target); copy $dst to the title's cache/spirv"

#!/usr/bin/env bash
# Research-only link check. No package signing, deployment or console commands.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=/home/tomer/ps5-za-native/shader-prewarm-research
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
build=$work/ps5-build
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
cc -std=c11 -O2 -Wall -Wextra -Werror -I"$root" -c "$root/compiler_probe.c" -o "$work/compiler_probe.o"
cc -std=c11 -O2 -Wall -Wextra -Werror -c "$root/../title/title_fs.c" -o "$work/title_fs.o"
# Reuse the proven title link recipe, including its direct-memory allocator,
# thread wrappers, SDK libc++ and platform imports. No game archive is linked.
bash /home/tomer/ps5-za-native/title-r1-20261027/source/tools/ps5/link-title.sh \
    "$work/compiler-link-check.elf" --gc-sections "$work/compiler_probe.o" "$work/title_fs.o" \
    --start-group "$build/libza_glsl_compiler.a" \
    "$build/glslang/glslang/libglslang.a" \
    "$build/glslang/glslang/libglslang-default-resource-limits.a" \
    "$build/glslang/SPIRV/libSPIRV.a" --end-group
"$PS5_PAYLOAD_SDK/bin/llvm-nm" --dynamic --undefined-only "$work/compiler-link-check.elf" > "$work/compiler-imports.txt"
/usr/lib/llvm-21/bin/llvm-readelf -h "$work/compiler-link-check.elf" > "$work/compiler-elf-header.txt"

#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/shader-probe-r18b
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
build=/home/tomer/ps5-za-native/shader-prewarm-research/ps5-build
tool=$PS5_VULKAN/build/host/ps5-native-tool
dist=$project/artifacts/shader-probe-r18b
mkdir -p "$work" "$dist"
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
cc -std=c11 -O2 -Wall -Wextra -Werror -c "$root/probe.c" -o "$work/probe.o"
cc -std=c11 -O2 -Wall -Wextra -Werror -c "$root/../title/title_fs.c" -o "$work/title_fs.o"
bash /home/tomer/ps5-za-native/title-r1-20261027/source/tools/ps5/link-title.sh \
    "$work/llvm-pie.elf" --gc-sections "$work/probe.o" "$work/title_fs.o" \
    --start-group "$build/libza_glsl_compiler.a" "$build/glslang/glslang/libglslang.a" \
    "$build/glslang/glslang/libglslang-default-resource-limits.a" "$build/glslang/SPIRV/libSPIRV.a" --end-group
"$PS5_PAYLOAD_SDK/bin/llvm-nm" --dynamic --undefined-only "$work/llvm-pie.elf" > "$dist/imports.txt"
"$PS5_PAYLOAD_SDK/bin/llvm-strip" --strip-debug -o "$work/stripped.elf" "$work/llvm-pie.elf"
"$tool" link --in "$work/stripped.elf" --out "$work/eboot.elf" \
    --stub-dir "$PS5_PAYLOAD_SDK/target/lib" --stub "$work/ps5-link/stubs/libSceAgc.so" \
    --stub "$work/ps5-link/stubs/libSceAgcDriver.so" --module-sdk 0x02000009 --companion-sdk 0x08050001 --file-name eboot.elf
"$tool" self --sign --in "$work/eboot.elf" --out "$dist/eboot.bin" --magic 0x1D3D154F
"$tool" self --inspect --file "$dist/eboot.bin" > "$dist/self-inspect.txt"
sha256sum "$dist/eboot.bin" > "$dist/eboot.sha256.txt"
cat "$dist/eboot.sha256.txt"

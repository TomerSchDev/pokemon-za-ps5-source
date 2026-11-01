#!/usr/bin/env bash
# ZA Native Probe - build the Vulkan/pad/audio probe title (PPSA91760, r4) for the PS5.
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Mirrors PS5_Vulkan/tools/build-radv-title.sh (Mihawk-99): our C source and
# the repository's CRT and C++ runtime, linked whole with the RADV release
# archive the Mesa fork builds (-Dradv-winsys=ps5), through tools/radv-link.sh,
# then converted and signed with the PS5 native tool into dist/PPSA91760.
#
# Usage (WSL):  bash build-vk-probe.sh [BUILD_ID]
# Environment:  PS5_VULKAN, PS5_MESA, RADV_ARCHIVE, PS5_CLANG override the defaults.

set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
build_id=${1:-za-vk-probe-a0-20261027-r4}
PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
PS5_MESA=${PS5_MESA:-/home/tomer/ps5-za-native/PS5_Mesa}
archive=${RADV_ARCHIVE:-$PS5_VULKAN/.deps/native/radv-release/lib/libvulkan_radeon.ps5.a}
sdk_root="$PS5_VULKAN/.deps/native/ps5-payload-sdk"
native="$PS5_VULKAN/tooling/native"
tool="$PS5_VULKAN/build/host/ps5-native-tool"
work=${VK_PROBE_WORK:-/home/tomer/ps5-za-native/vk-probe-build}
param="$root/sce_sys/param.json"
# The SDK fork's own wrapper picks clang 21 on this host; the title's objects
# use the same compiler as the archive.
export PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
export PS5_PAYLOAD_SDK="$sdk_root"

module_sdk=0x02000009
companion_sdk=0x08050001
fself_magic=0x1D3D154F

if [[ ! -f $archive ]]; then
    echo "!! the RADV release archive is missing: $archive" >&2
    echo "!! build it first with: (cd $PS5_VULKAN && tools/build-radv.sh release)" >&2
    exit 2
fi
for file in "$tool" "$param" "$sdk_root/bin/prospero-lld" "$PS5_VULKAN/tools/radv-link.sh" \
        "$PS5_VULKAN/runtime/libc.prx" "$PS5_VULKAN/runtime/libc.prx.sha256" "$PS5_CLANG" \
        "$root/src/za_vk_probe.c" "$root/shaders/tri.vert" "$root/shaders/tri.frag"; do
    [[ -e $file ]] || { echo "missing $file" >&2; exit 2; }
done
command -v glslangValidator >/dev/null || { echo "glslangValidator was not found" >&2; exit 2; }

title_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["titleId"])' "$param")
mkdir -p "$work/obj" "$work/stubs" "$work/gen"
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }

echo "==> [vk-probe] shaders"
: > "$work/gen/za_vk_shaders.h.tmp"
glslangValidator -V --target-env vulkan1.3 --vn za_vk_tri_vert "$root/shaders/tri.vert" \
    -o "$work/gen/tri_vert.h" > /dev/null
glslangValidator -V --target-env vulkan1.3 --vn za_vk_tri_frag "$root/shaders/tri.frag" \
    -o "$work/gen/tri_frag.h" > /dev/null
cat "$work/gen/tri_vert.h" "$work/gen/tri_frag.h" >> "$work/gen/za_vk_shaders.h.tmp"
mv "$work/gen/za_vk_shaders.h.tmp" "$work/gen/za_vk_shaders.h"

echo "==> [vk-probe] compiling ($build_id)"
cc -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -DZA_BUILD_ID="\"$build_id\"" \
    -I "$PS5_MESA/include" -I "$work/gen" -c "$root/src/za_vk_probe.c" -o "$work/obj/za_vk_probe.o"
cc -std=c++20 -O2 -Wall -Wextra -fno-exceptions -fno-rtti -ffunction-sections -fdata-sections \
    -c "$native/app_crt.cpp" -o "$work/obj/app_crt.o"
cc -std=c++20 -O2 -Wall -Wextra -fno-exceptions -fno-rtti -ffunction-sections -fdata-sections \
    -c "$native/app_cpp_runtime.cpp" -o "$work/obj/app_cpp_runtime.o"

# AGC comes from system modules; these host-link stubs only name the imports.
stub() {
    local library=$1 source=$2
    cc -std=c11 -O2 -fPIC -c "$PS5_VULKAN/$source" -o "$work/obj/${library}_stub.o"
    "$sdk_root/bin/prospero-lld" --shared -soname "${library}.prx" \
        -o "$work/stubs/${library}.so" "$work/obj/${library}_stub.o"
}
stub libSceAgc vendor/ps5/sdk/stubs/agc_canary_link_stub.c
stub libSceAgcDriver vendor/ps5/sdk/stubs/agc_driver_canary_link_stub.c

echo "==> [vk-probe] linking with $(basename "$(dirname "$(dirname "$archive")")")"
# shellcheck source=/dev/null
source "$PS5_VULKAN/tools/radv-link.sh"
radv_link_recipe "$PS5_VULKAN" "$sdk_root" "$archive" || exit 2
"$sdk_root/bin/prospero-lld" "${radv_linker_script[@]}" --eh-frame-hdr "${radv_link_flags[@]}" \
    --version-script "$native/app-symbols.map" --exclude-libs=ALL \
    -e _start -o "$work/llvm-pie.elf" \
    "$work/obj/app_crt.o" "$work/obj/app_cpp_runtime.o" "$work/obj/za_vk_probe.o" \
    "$work/stubs/libSceAgc.so" "$work/stubs/libSceAgcDriver.so" \
    "${radv_link_inputs[@]}" \
    --as-needed "$sdk_root"/target/lib/*.so
"$tool" link --in "$work/llvm-pie.elf" --out "$work/eboot.elf" \
    --stub-dir "$sdk_root/target/lib" --stub "$work/stubs/libSceAgc.so" \
    --stub "$work/stubs/libSceAgcDriver.so" --module-sdk "$module_sdk" \
    --companion-sdk "$companion_sdk" --file-name eboot.elf

echo "==> [vk-probe] assembling dist/$title_id"
app="$root/dist/$title_id"
rm -rf -- "$app"
mkdir -p "$app/sce_sys" "$app/sce_module" "$app/assets"
"$tool" self --sign --in "$work/eboot.elf" --out "$app/eboot.bin" --magic "$fself_magic"
cp "$param" "$app/sce_sys/param.json"
for asset in icon0.png pic0.dds pic1.dds snd0.at9; do
    [[ -f $root/sce_sys/$asset ]] && cp "$root/sce_sys/$asset" "$app/sce_sys/$asset"
done
cp "$root/assets/banner.txt" "$app/assets/banner.txt"
(cd "$PS5_VULKAN/runtime" && sha256sum --check --strict --quiet libc.prx.sha256)
cp "$PS5_VULKAN/runtime/libc.prx" "$app/sce_module/libc.prx"
"$tool" self --inspect --file "$app/sce_module/libc.prx" > /dev/null
"$tool" self --inspect --file "$app/eboot.bin" > /dev/null

eboot_sha=$(sha256sum "$app/eboot.bin" | cut -d' ' -f1)
eboot_size=$(stat -c %s "$app/eboot.bin")
{
    printf 'build_id: %s\n' "$build_id"
    printf 'built_utc: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'title_id: %s\n' "$title_id"
    printf 'eboot.bin sha256: %s\n' "$eboot_sha"
    printf 'eboot.bin bytes: %s\n' "$eboot_size"
    printf 'libc.prx sha256: %s\n' "$(sha256sum "$app/sce_module/libc.prx" | cut -d' ' -f1)"
    printf 'sdk revision: %s\n' "$(cat "$sdk_root/.ps5-sdk-revision")"
    printf 'ps5_vulkan commit: %s\n' "$(git -C "$PS5_VULKAN" rev-parse HEAD 2>/dev/null || echo unknown)"
    printf 'ps5_mesa commit: %s\n' "$(git -C "$PS5_MESA" rev-parse HEAD 2>/dev/null || echo unknown)"
    printf 'clang: %s\n' "$("$PS5_CLANG" --version | head -1)"
    printf 'archive: %s\n' "$archive"
    printf -- '--- RADV PROVENANCE.txt ---\n'
    cat "$(dirname "$(dirname "$archive")")/PROVENANCE.txt" 2>/dev/null || echo "(no PROVENANCE.txt beside the archive)"
} > "$root/dist/BUILD-INFO.txt"
printf 'VK probe title: %s (%s bytes, sha256 %s)\n' "$app" "$eboot_size" "$eboot_sha"

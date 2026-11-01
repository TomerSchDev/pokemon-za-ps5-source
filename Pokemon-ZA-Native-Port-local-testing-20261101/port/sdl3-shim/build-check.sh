#!/usr/bin/env bash
# SDL3 shim for the PS5 port of Pokemon Legends Z-A Recomp: compile-only check
# with the toolchain of vk-probe/build-vk-probe.sh (the PS5 clang wrapper of
# PS5_Vulkan, clang 21, the payload SDK sysroot, the Mesa Vulkan headers).
# SPDX-License-Identifier: GPL-3.0-or-later
#
# What it checks, in order (any failure stops it):
#   1. every public header compiles on its own, as C11 and as C++20;
#   2. every shim source compiles with -std=c11 -O2 -Wall -Wextra -Werror;
#   3. test/consumer.c (the runtime's usage patterns) compiles with the runtime's
#      flags, as C and as C++ (the .mm UI sources are C++);
#   4. every SDL_* symbol the consumer references is defined by the shim objects;
#   5. the runtime's own SDL-using C files syntax-check against the shim headers
#      (when the recomp source is reachable; RUNTIME_CHECK=skip to leave it out).
# Nothing is linked and nothing is written outside the work directory.
#
# Usage (WSL):  bash build-check.sh
# Environment:  PS5_VULKAN, PS5_MESA, PS5_CLANG, SDL3_SHIM_WORK, POKEZA_RECOMP, RUNTIME_CHECK

set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
PS5_MESA=${PS5_MESA:-/home/tomer/ps5-za-native/PS5_Mesa}
export PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
export PS5_PAYLOAD_SDK="$PS5_VULKAN/.deps/native/ps5-payload-sdk"
work=${SDL3_SHIM_WORK:-${TMPDIR:-/tmp}/sdl3-shim-build}
nm=${LLVM_NM:-/usr/lib/llvm-21/bin/llvm-nm}
recomp=${POKEZA_RECOMP:-/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-recomp}

for file in "$PS5_VULKAN/tooling/prospero-clang18" "$PS5_PAYLOAD_SDK/target/include/stdint.h" \
        "$PS5_MESA/include/vulkan/vulkan.h" "$PS5_CLANG" "$nm"; do
    [[ -e $file ]] || { echo "missing $file" >&2; exit 2; }
done

rm -rf -- "$work"
mkdir -p "$work/obj" "$work/hdr" "$work/rt"
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }

shim_flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -I "$root/include" -I "$PS5_MESA/include")
# runtime/Makefile RTFLAGS (-Wno-format is the Linux OSFLAGS; -Wextra -Werror are ours, stricter)
rt_flags=(-O2 -g -fno-strict-aliasing -Wall -Wextra -Werror -Wno-unused-function -I "$root/include" -I "$PS5_MESA/include")

echo "==> [sdl3-shim] 1. each public header on its own (C11, C++20)"
for header in "$root"/include/SDL3/*.h; do
    name=$(basename "$header")
    printf '#include <SDL3/%s>\n' "$name" > "$work/hdr/${name%.h}.c"
    cc -std=c11 "${shim_flags[@]}" -fsyntax-only -x c "$work/hdr/${name%.h}.c"
    cc -std=c++20 "${shim_flags[@]}" -fno-exceptions -fno-rtti -fsyntax-only -x c++ "$work/hdr/${name%.h}.c"
done
# the order of device.c: SDL.h, SDL_vulkan.h, then vulkan.h - and the other way round
printf '#include <SDL3/SDL.h>\n#include <SDL3/SDL_vulkan.h>\n#define VK_NO_PROTOTYPES\n#include <vulkan/vulkan.h>\n' > "$work/hdr/order_sdl_first.c"
printf '#define VK_NO_PROTOTYPES\n#include <vulkan/vulkan.h>\n#include <SDL3/SDL.h>\n#include <SDL3/SDL_vulkan.h>\n' > "$work/hdr/order_vulkan_first.c"
for order in order_sdl_first order_vulkan_first; do
    cc -std=c11 "${shim_flags[@]}" -fsyntax-only -x c "$work/hdr/$order.c"
    cc -std=c++20 "${shim_flags[@]}" -fno-exceptions -fno-rtti -fsyntax-only -x c++ "$work/hdr/$order.c"
done

echo "==> [sdl3-shim] 2. the shim sources (-std=c11 -O2 -Wall -Wextra -Werror)"
objects=()
for source in "$root"/src/*.c; do
    object="$work/obj/$(basename "${source%.c}").o"
    cc -std=c11 "${shim_flags[@]}" -c "$source" -o "$object"
    objects+=("$object")
done

echo "==> [sdl3-shim] 3. test/consumer.c with the runtime's flags, as C11 and as C++20"
cc -std=c11 "${rt_flags[@]}" -c "$root/test/consumer.c" -o "$work/obj/consumer_c.o"
cc -std=c++20 "${rt_flags[@]}" -fno-exceptions -fno-rtti -x c++ -c "$root/test/consumer.c" -o "$work/obj/consumer_cxx.o"

echo "==> [sdl3-shim] 4. every SDL symbol the consumer references is defined by the shim"
"$nm" --undefined-only "$work/obj/consumer_c.o" | awk '{print $NF}' | grep '^SDL_' | sort -u > "$work/needed.txt"
"$nm" --defined-only "${objects[@]}" | awk '$2 ~ /^[TtDdBbRr]$/ {print $3}' | grep '^SDL_' | sort -u > "$work/defined.txt"
missing=$(comm -23 "$work/needed.txt" "$work/defined.txt" || true)
if [[ -n $missing ]]; then
    echo "!! SDL symbols the consumer needs and the shim does not define:" >&2
    echo "$missing" >&2
    exit 1
fi
echo "    $(wc -l < "$work/needed.txt") referenced, $(wc -l < "$work/defined.txt") defined"
echo "==> [sdl3-shim]    what the shim objects import (the title links: Sony stubs, the RADV archive, libc/pthread):"
"$nm" --undefined-only "${objects[@]}" | awk '$1 !~ /:$/ {print $NF}' | grep -v '^SDL_\|^sdl3_ps5_' | sort -u | tr '\n' ' '
echo

if [[ ${RUNTIME_CHECK:-} != skip && -d $recomp/runtime ]]; then
    echo "==> [sdl3-shim] 5. the runtime's SDL-using C files, syntax-only against the shim headers ($recomp)"
    # device.c, exec.c and textures.c need vk.h (VMA) and are left out; the headers they include are covered by 1.
    for file in runtime/hle/input.c runtime/hle/bindings.c runtime/hle/pl.c runtime/services/audio.c runtime/paths.c \
            runtime/main.c; do
        cc -std=c11 -fsyntax-only -fno-strict-aliasing -Wall -Wno-unused-function -Wno-format \
            -I "$recomp/runtime" -I "$recomp/runtime/nvn" -I "$root/include" -I "$PS5_MESA/include" \
            "$recomp/$file"
        echo "    ok $file"
    done
    # renderer.h needs nvn.h first, as input.c includes them; menu.h and input_bind.h are what the C++ .mm sources include
    printf '#include <SDL3/SDL.h>\n#include "nvn/nvn.h"\n#include "nvn/renderer.h"\n#include "ui/menu.h"\n#include "input_bind.h"\n' > "$work/rt/headers.c"
    cc -std=c11 -fsyntax-only -Wall -I "$recomp/runtime" -I "$recomp/runtime/nvn" -I "$root/include" "$work/rt/headers.c"
    printf '#include <SDL3/SDL.h>\n#include "ui/menu.h"\n#include "input_bind.h"\n' > "$work/rt/headers.cpp"
    cc -std=c++20 -fsyntax-only -Wall -fno-exceptions -fno-rtti -I "$recomp/runtime" -I "$recomp/runtime/nvn" \
        -I "$root/include" -x c++ "$work/rt/headers.cpp"
    echo "    ok nvn/renderer.h, ui/menu.h, input_bind.h (C), ui/menu.h, input_bind.h (C++)"
elif [[ ${RUNTIME_CHECK:-} != skip ]]; then
    echo "==> [sdl3-shim] 5. skipped: the recomp source is not at $recomp (POKEZA_RECOMP to point at it)"
fi

echo "sdl3-shim: build check passed ($(basename "$(dirname "$(dirname "$(dirname "$root")")")")/$(basename "$(dirname "$(dirname "$root")")")/port/sdl3-shim; work $work)"

#!/usr/bin/env bash
# ZA Recomp -> PS5: link the title's PIE from the runtime objects, the game code archive and the RADV archive.
#
# SKELETON. The recipe is vk-probe/build-vk-probe.sh's (Pokemon-ZA-Native-Port, r3/r4: proven on 13.60) with the runtime
# in the probe's place: the SDK's CRT (app_crt.cpp: IEEE FP state, _init_env, static constructors, main) and C++ runtime
# shims, the AGC import stubs, PS5_Vulkan/tools/radv-link.sh (the RADV archive whole, libc++ / libc++abi / libunwind,
# clang's builtins, the platform layer with its --wrap / --defsym bindings), then prospero-lld. It has NOT linked the full
# runtime yet: the SDL3 shim, shaderc and FFmpeg objects do not exist (analysis/ps5-runtime-compile-gaps.md) - give them
# through ZA_PS5_EXTRA_INPUTS when they do. The PIE still needs ps5-native-tool link + self --sign + param.json and
# sce_module/libc.prx around it (the probe's script, steps "linking" to "assembling"; TODO: tools/ps5/package-title.sh).
#
# Called by the Makefile (PLATFORM=ps5): tools/ps5/link-title.sh <out.elf> <objects and archives...>
set -euo pipefail
[[ $# -ge 2 ]] || { echo "usage: $0 <out.elf> <inputs...>" >&2; exit 2; }
out=$1
shift
PS5_SDK=${PS5_SDK:-/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk}
PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
archive=${RADV_ARCHIVE:-$PS5_VULKAN/.deps/native/radv-release/lib/libvulkan_radeon.ps5.a}
native=$PS5_VULKAN/tooling/native
work=$(dirname "$out")/ps5-link
export PS5_CLANG PS5_PAYLOAD_SDK="$PS5_SDK"
for f in "$archive" "$PS5_SDK/bin/prospero-lld" "$PS5_VULKAN/tools/radv-link.sh" "$native/app_crt.cpp" \
         "$native/app_cpp_runtime.cpp" "$native/app-symbols.map" "$PS5_CLANG"; do
    [[ -e $f ]] || { echo "missing $f" >&2; exit 2; }
done
mkdir -p "$work/stubs"
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }

echo "==> [ps5] the SDK's CRT and C++ runtime shims"
cc -std=c++20 -O2 -Wall -fno-exceptions -fno-rtti -ffunction-sections -fdata-sections \
    -c "$native/app_crt.cpp" -o "$work/app_crt.o"
cc -std=c++20 -O2 -Wall -fno-exceptions -fno-rtti -ffunction-sections -fdata-sections \
    -c "$native/app_cpp_runtime.cpp" -o "$work/app_cpp_runtime.o"

# AGC comes from system modules; these host-link stubs only name the imports (as the probe's build does).
stub() {
    local library=$1 source=$2
    cc -std=c11 -O2 -fPIC -c "$PS5_VULKAN/$source" -o "$work/${library}_stub.o"
    "$PS5_SDK/bin/prospero-lld" --shared -soname "${library}.prx" -o "$work/stubs/${library}.so" "$work/${library}_stub.o"
}
stub libSceAgc vendor/ps5/sdk/stubs/agc_canary_link_stub.c
stub libSceAgcDriver vendor/ps5/sdk/stubs/agc_driver_canary_link_stub.c

echo "==> [ps5] linking $out with $(basename "$archive")"
# shellcheck source=/dev/null
source "$PS5_VULKAN/tools/radv-link.sh"
radv_link_recipe "$PS5_VULKAN" "$PS5_SDK" "$archive" || exit 2
# The platform bindings the runtime leans on (analysis/ps5-runtime-compile-gaps.md 3.2): arc4random (runtime/kernel.c's
# seed, runtime/ui/rando_tab.mm; libScePosixForWebKit's stub would leave the import null at run time), and the directory
# streams (libc's are refused to a title: the runtime reaches ps5_opendir and family by name, platform/ps5_compat.h,
# RADV's calls go through the binding). The recipe binds them for every title; checked here, not assumed, and bound
# if a recipe revision drops one.
platform_syms=$("$PS5_SDK/bin/llvm-nm" --defined-only "$PS5_SDK/target/lib/libps5platform.a" 2>/dev/null)
for name in arc4random arc4random_buf arc4random_uniform opendir fdopendir readdir rewinddir dirfd closedir; do
    case " ${radv_link_flags[*]} " in *" --defsym=$name=ps5_$name "*) continue ;; esac
    grep -q " T ps5_$name\$" <<<"$platform_syms" || { echo "no ps5_$name in libps5platform.a: $name would be a null import" >&2; exit 2; }
    echo "==> [ps5] binding $name to ps5_$name (the recipe did not)"
    radv_link_flags+=("--defsym=$name=ps5_$name")
done
# shellcheck disable=SC2206
extra=(${ZA_PS5_EXTRA_INPUTS:-})
# TODO: the title converter wants a .data.rel.ro section (the probe keeps a manifest there) and refuses every
# application export: the runtime's globals stay local through app-symbols.map + --exclude-libs=ALL (unverified here).
"$PS5_SDK/bin/prospero-lld" "${radv_linker_script[@]}" --eh-frame-hdr "${radv_link_flags[@]}" \
    --version-script "$native/app-symbols.map" --exclude-libs=ALL \
    -e _start -o "$out" \
    "$work/app_crt.o" "$work/app_cpp_runtime.o" "$@" "${extra[@]}" \
    "$work/stubs/libSceAgc.so" "$work/stubs/libSceAgcDriver.so" \
    "${radv_link_inputs[@]}" \
    --as-needed "$PS5_SDK"/target/lib/*.so
# What the PIE must not import - null or refused for a title (the gaps report B2, B5, B8, B9; __cpu_model: gamelib.c
# asks cpuid itself); each a fault on the console, so the link fails here instead.
bad=$("$PS5_SDK/bin/llvm-nm" --dynamic --undefined-only "$out" 2>/dev/null | awk '{ print $NF }' |
    grep -xE 'arc4random(_buf|_uniform)?|telldir|seekdir|fork|execvp|waitpid|link|__cpu_model|__cpu_indicator_init' || true)
if [[ -n $bad ]]; then
    echo "$out imports what the console gives a title nothing for:" $bad >&2
    exit 2
fi
# (B10) ucontext is unverified for a title: the fibers switch in the title's own asm (runtime/platform/ps5_fiber.c)
# unless the runtime was built with -DZA_PS5_ASM_FIBERS=0 - said, not refused.
uctx=$("$PS5_SDK/bin/llvm-nm" --dynamic --undefined-only "$out" 2>/dev/null | awk '{ print $NF }' |
    grep -xE 'getcontext|makecontext|swapcontext' || true)
[[ -z $uctx ]] || echo "note: $out imports" $uctx "(ucontext fibers: unverified on the console)" >&2
echo "PIE: $out ($(stat -c %s "$out") bytes); next: ps5-native-tool link + self --sign (vk-probe/build-vk-probe.sh)"

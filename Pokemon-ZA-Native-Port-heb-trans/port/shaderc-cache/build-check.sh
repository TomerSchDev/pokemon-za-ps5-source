#!/usr/bin/env bash
# shaderc-cache for the PS5 port of Pokemon Legends Z-A Recomp: compile-only check with the toolchain of
# vk-probe/build-vk-probe.sh (the PS5 clang wrapper of PS5_Vulkan, clang 21, the payload SDK sysroot), plus one
# host-run unit test of the hash.
# SPDX-License-Identifier: GPL-3.0-or-later
#
# What it checks, in order (any failure stops it):
#   1. every header of include/shaderc compiles on its own, as C11 and as C++20;
#   2. shaderc_cache.c compiles with -std=c11 -O2 -Wall -Wextra -Werror against include/shaderc - and, when MSYS2's
#      real shaderc header is reachable, against that one too (signature parity with shaderc 2025.4);
#   3. test/consumer.c (shaders.c's usage) compiles as C11 and as C++20;
#   4. every shaderc_* symbol the consumer imports, every name of symbols.txt, and every shaderc symbol of the audit's
#      undefined.tsv (when reachable) is defined by shaderc_cache.o (llvm-nm); the object's own imports are listed;
#   5. the runtime's runtime/nvn/vulkan/shaders.c syntax-checks against include/shaderc (needs the recomp clone, the
#      Mesa Vulkan headers and MSYS2's VMA header; RUNTIME_CHECK=skip leaves it out);
#   6. hash parity: src_hash() is cut out of the recomp's shaders.c, compiled natively with shaderc_cache.c and
#      test/hash-parity.c by the host clang, and run - the cache's hash must equal the runtime's.
# Nothing is linked for the PS5 and nothing is written outside the work directory.
#
# Usage (WSL):  bash build-check.sh
# Environment:  PS5_VULKAN, PS5_MESA, PS5_CLANG, HOST_CC, ZA_MSYS2_INC, SHADERC_CACHE_WORK, POKEZA_RECOMP, RUNTIME_CHECK

set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
PS5_MESA=${PS5_MESA:-/home/tomer/ps5-za-native/PS5_Mesa}
export PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
export PS5_PAYLOAD_SDK="$PS5_VULKAN/.deps/native/ps5-payload-sdk"
host_cc=${HOST_CC:-$PS5_CLANG}
msys=${ZA_MSYS2_INC:-/mnt/c/msys64/ucrt64/include}
work=${SHADERC_CACHE_WORK:-${TMPDIR:-/tmp}/shaderc-cache-build}
nm=${LLVM_NM:-$PS5_PAYLOAD_SDK/bin/llvm-nm}
[[ -x $nm ]] || nm=/usr/lib/llvm-21/bin/llvm-nm
recomp=${POKEZA_RECOMP:-/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/pokeza-recomp-ps5}

for file in "$PS5_VULKAN/tooling/prospero-clang18" "$PS5_PAYLOAD_SDK/target/include/stdint.h" "$PS5_CLANG" "$nm"; do
    [[ -e $file ]] || { echo "missing $file" >&2; exit 2; }
done

rm -rf -- "$work"
mkdir -p "$work/obj" "$work/hdr" "$work/inc" "$work/host"
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)

echo "==> [shaderc-cache] 1. each header of include/shaderc on its own (C11, C++20)"
for header in "$root"/include/shaderc/*.h; do
    name=$(basename "$header")
    printf '#include <shaderc/%s>\n' "$name" > "$work/hdr/${name%.h}.c"
    cc -std=c11 "${flags[@]}" -I "$root/include" -fsyntax-only -x c "$work/hdr/${name%.h}.c"
    cc -std=c++20 "${flags[@]}" -I "$root/include" -fno-exceptions -fno-rtti -fsyntax-only -x c++ "$work/hdr/${name%.h}.c"
done

echo "==> [shaderc-cache] 2. shaderc_cache.c (-std=c11 -O2 -Wall -Wextra -Werror) against include/shaderc"
cc -std=c11 "${flags[@]}" -I "$root/include" -c "$root/shaderc_cache.c" -o "$work/obj/shaderc_cache.o"
echo "    ok ($(stat -c %s "$work/obj/shaderc_cache.o") bytes)"
if [[ -f $msys/shaderc/shaderc.h ]]; then
    ln -sfn "$msys/shaderc" "$work/inc/shaderc"
    cc -std=c11 "${flags[@]}" -isystem "$work/inc" -c "$root/shaderc_cache.c" -o "$work/obj/shaderc_cache_real_hdr.o"
    echo "    ok against the real header too ($msys/shaderc, $(grep -c 'SHADERC_EXPORT' "$msys/shaderc/shaderc.h") exported declarations)"
else
    echo "    (no $msys/shaderc/shaderc.h: the real-header compile is skipped; ZA_MSYS2_INC)"
fi

echo "==> [shaderc-cache] 3. test/consumer.c as C11 and as C++20"
cc -std=c11 "${flags[@]}" -I "$root/include" -c "$root/test/consumer.c" -o "$work/obj/consumer_c.o"
cc -std=c++20 "${flags[@]}" -I "$root/include" -fno-exceptions -fno-rtti -x c++ -c "$root/test/consumer.c" -o "$work/obj/consumer_cxx.o"

echo "==> [shaderc-cache] 4. every shaderc symbol needed is defined by shaderc_cache.o"
"$nm" --defined-only "$work/obj/shaderc_cache.o" | awk '$2 == "T" {print $3}' | sort -u > "$work/defined.txt"
"$nm" --undefined-only "$work/obj/consumer_c.o" "$work/obj/consumer_cxx.o" | awk '$1 !~ /:$/ {print $NF}' | grep '^shaderc_' | sort -u > "$work/consumer-needed.txt"
grep -v '^#' "$root/symbols.txt" | grep . | sort -u > "$work/listed.txt"
check() {  # <what> <needed file>
    local missing
    missing=$(comm -23 "$2" "$work/defined.txt" || true)
    if [[ -n $missing ]]; then
        echo "!! $1 needs shaderc symbols shaderc_cache.o does not define:" >&2
        echo "$missing" >&2
        exit 1
    fi
    echo "    $1: $(wc -l < "$2") needed, all defined"
}
check "test/consumer.c" "$work/consumer-needed.txt"
check "symbols.txt" "$work/listed.txt"
audit=$recomp/build/ps5-audit/undefined.tsv
if [[ -f $audit ]]; then
    awk -F'\t' '$1 ~ /^shaderc_/ && $2 == "MISSING" {print $1}' "$audit" | sort -u > "$work/audit.txt"
    check "undefined.tsv" "$work/audit.txt"
else
    echo "    undefined.tsv not at $audit (POKEZA_RECOMP): skipped"
fi
echo "    defined: $(tr '\n' ' ' < "$work/defined.txt")"
echo "    imports (libc / pthread only): $("$nm" --undefined-only "$work/obj/shaderc_cache.o" | awk '{print $NF}' | sort -u | tr '\n' ' ')"

shaders_c=$recomp/runtime/nvn/vulkan/shaders.c
if [[ ${RUNTIME_CHECK:-} != skip && -f $shaders_c ]]; then
    echo "==> [shaderc-cache] 5. the runtime's shaders.c syntax-only against include/shaderc ($recomp)"
    vma=
    for cand in "$msys/vk_mem_alloc.h" "$msys/vma/vk_mem_alloc.h"; do [[ -f $cand ]] && { vma=$cand; break; }; done
    if [[ -n $vma && -f $PS5_MESA/include/vulkan/vulkan.h ]]; then
        ln -sfn "$vma" "$work/inc/vk_mem_alloc.h"
        cc -std=c11 -fsyntax-only -fno-strict-aliasing -Wall -Wno-unused-function -Wno-format -DZA_PS5 -DLARECOMP_STATIC_GAMELIB \
            -I "$recomp/runtime" -I "$recomp/runtime/nvn" -I "$PS5_MESA/include" -I "$work/inc" -I "$root/include" "$shaders_c"
        echo "    ok runtime/nvn/vulkan/shaders.c (VMA: $vma)"
    else
        echo "    skipped: needs MSYS2's vk_mem_alloc.h ($msys) and $PS5_MESA/include/vulkan/vulkan.h"
    fi
elif [[ ${RUNTIME_CHECK:-} != skip ]]; then
    echo "==> [shaderc-cache] 5. skipped: the recomp source is not at $recomp (POKEZA_RECOMP to point at it)"
fi

if [[ ${RUNTIME_CHECK:-} != skip && -f $shaders_c ]]; then
    echo "==> [shaderc-cache] 6. hash parity with the runtime's src_hash (host build, $host_cc)"
    awk '/^static uint64_t src_hash\(/ {p = 1} p {print} p && /^}/ {exit}' "$shaders_c" > "$work/host/runtime_src_hash.inc"
    [[ -s $work/host/runtime_src_hash.inc ]] || { echo "!! src_hash() not found in $shaders_c" >&2; exit 1; }
    "$host_cc" -std=c11 -O1 -Wall -Wextra -Werror -Wno-unused-function -I "$root/include" -I "$work/host" \
        "$root/test/hash-parity.c" "$root/shaderc_cache.c" -o "$work/host/hash-parity" -lpthread
    "$work/host/hash-parity"
fi

echo "shaderc-cache: build check passed (port/shaderc-cache; work $work)"

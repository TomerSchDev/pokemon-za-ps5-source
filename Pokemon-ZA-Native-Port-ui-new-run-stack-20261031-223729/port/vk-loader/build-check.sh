#!/usr/bin/env bash
# vk-loader for the PS5 port of Pokemon Legends Z-A Recomp: compile-only check with the toolchain of
# vk-probe/build-vk-probe.sh (the PS5 clang wrapper of PS5_Vulkan, clang 21, the payload SDK sysroot, the Mesa
# Vulkan headers the RADV archive was built with).
# SPDX-License-Identifier: GPL-3.0-or-later
#
# What it checks, in order (any failure stops it):
#   1. gen_vk_loader.py regenerates vk_loader.c from the PS5_Mesa headers and required-symbols.txt, and the result is
#      byte-identical to the committed file (a changed header or list means: regenerate and commit);
#   2. vk_loader.c compiles with -std=c11 -O2 -Wall -Wextra -Werror against <vulkan/vulkan.h> with its prototypes on,
#      so every trampoline's signature is checked against the header's declaration;
#   3. every vk* symbol of required-symbols.txt - and of the audit's undefined.tsv when it is reachable - is defined
#      by vk_loader.o (llvm-nm), and the object imports no vk[A-Z]* symbol itself;
#   4. the RADV archive defines the ICD entry points the loader imports, and defines none of the symbols the loader
#      defines (no duplicate at link time).
# Nothing is linked and nothing is written outside the work directory.
#
# Usage (WSL):  bash build-check.sh
# Environment:  PS5_VULKAN, PS5_MESA, PS5_CLANG, RADV_ARCHIVE, VK_LOADER_WORK, POKEZA_RECOMP, PYTHON

set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
PS5_MESA=${PS5_MESA:-/home/tomer/ps5-za-native/PS5_Mesa}
export PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
export PS5_PAYLOAD_SDK="$PS5_VULKAN/.deps/native/ps5-payload-sdk"
archive=${RADV_ARCHIVE:-$PS5_VULKAN/.deps/native/radv-release/lib/libvulkan_radeon.ps5.a}
work=${VK_LOADER_WORK:-${TMPDIR:-/tmp}/vk-loader-build}
nm=${LLVM_NM:-$PS5_PAYLOAD_SDK/bin/llvm-nm}
[[ -x $nm ]] || nm=/usr/lib/llvm-21/bin/llvm-nm
python=${PYTHON:-python3}
recomp=${POKEZA_RECOMP:-/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/pokeza-recomp-ps5}

for file in "$PS5_VULKAN/tooling/prospero-clang18" "$PS5_PAYLOAD_SDK/target/include/stdint.h" \
        "$PS5_MESA/include/vulkan/vulkan.h" "$PS5_MESA/include/vulkan/vk_icd.h" "$PS5_CLANG" "$nm" "$archive"; do
    [[ -e $file ]] || { echo "missing $file" >&2; exit 2; }
done
command -v "$python" > /dev/null || { echo "missing $python" >&2; exit 2; }

rm -rf -- "$work"
mkdir -p "$work/obj"
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }

echo "==> [vk-loader] 1. regenerate from $PS5_MESA/include and compare with the committed vk_loader.c"
"$python" -I "$root/gen_vk_loader.py" --vulkan-include "$PS5_MESA/include" --required "$root/required-symbols.txt" \
    --out "$work/vk_loader.c" --list > "$work/commands.txt"
if ! cmp -s "$work/vk_loader.c" "$root/vk_loader.c"; then
    echo "!! vk_loader.c differs from what gen_vk_loader.py makes of $PS5_MESA/include and required-symbols.txt:" >&2
    diff -u "$root/vk_loader.c" "$work/vk_loader.c" | head -40 >&2 || true
    echo "!! regenerate: python3 -I gen_vk_loader.py --vulkan-include $PS5_MESA/include --required required-symbols.txt --out vk_loader.c" >&2
    exit 1
fi
echo "    identical: $(wc -l < "$work/commands.txt") commands ($(awk '{print $1}' "$work/commands.txt" | sort | uniq -c | awk '{printf "%s %s, ", $2, $1}' | sed 's/, $//'))"

echo "==> [vk-loader] 2. compile vk_loader.c (-std=c11 -O2 -Wall -Wextra -Werror, the header's prototypes on)"
cc -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -I "$PS5_MESA/include" \
    -c "$root/vk_loader.c" -o "$work/obj/vk_loader.o"
echo "    ok ($(stat -c %s "$work/obj/vk_loader.o") bytes)"

echo "==> [vk-loader] 3. every required vk* symbol is defined by vk_loader.o"
"$nm" --defined-only "$work/obj/vk_loader.o" | awk '$2 == "T" {print $3}' | grep '^vk[A-Z]' | sort -u > "$work/defined.txt"
grep -v '^#' "$root/required-symbols.txt" | sed 's/[[:space:]]*$//' | grep . | sort -u > "$work/required.txt"
missing=$(comm -23 "$work/required.txt" "$work/defined.txt" || true)
if [[ -n $missing ]]; then
    echo "!! required vk* symbols that vk_loader.o does not define:" >&2
    echo "$missing" >&2
    exit 1
fi
echo "    required-symbols.txt: $(wc -l < "$work/required.txt") required, $(wc -l < "$work/defined.txt") defined"
audit=$recomp/build/ps5-audit/undefined.tsv
if [[ -f $audit ]]; then
    awk -F'\t' '$1 ~ /^vk[A-Z]/ && $2 == "MISSING" {print $1}' "$audit" | sort -u > "$work/audit.txt"
    missing=$(comm -23 "$work/audit.txt" "$work/defined.txt" || true)
    if [[ -n $missing ]]; then
        echo "!! vk* symbols of $audit that vk_loader.o does not define (add them to required-symbols.txt / --sections):" >&2
        echo "$missing" >&2
        exit 1
    fi
    extra=$(comm -13 "$work/required.txt" "$work/audit.txt" || true)
    [[ -z $extra ]] || echo "    note: in undefined.tsv but not in required-symbols.txt (update the list): $extra"
    echo "    undefined.tsv: $(wc -l < "$work/audit.txt") vk* symbols, all defined"
else
    echo "    undefined.tsv not at $audit (POKEZA_RECOMP): the committed list only"
fi
"$nm" --undefined-only "$work/obj/vk_loader.o" | awk '{print $NF}' | sort -u > "$work/imports.txt"
if grep -q '^vk[A-Z]' "$work/imports.txt"; then
    echo "!! vk_loader.o imports vk* symbols it should define:" >&2
    grep '^vk[A-Z]' "$work/imports.txt" >&2
    exit 1
fi
echo "    vk_loader.o imports: $(tr '\n' ' ' < "$work/imports.txt")"

echo "==> [vk-loader] 4. the RADV archive: provides the ICD entry points, defines none of the loader's symbols"
"$nm" --defined-only "$archive" 2>/dev/null | awk 'NF >= 3 && $2 ~ /^[TWDBVRC]$/ {print $3}' | sort -u > "$work/archive-defined.txt"
for sym in vk_icdGetInstanceProcAddr vk_icdNegotiateLoaderICDInterfaceVersion; do
    grep -qx "$sym" "$work/archive-defined.txt" || { echo "!! $archive does not define $sym" >&2; exit 1; }
done
"$nm" --defined-only "$work/obj/vk_loader.o" | awk 'NF >= 3 && $2 ~ /^[TWDBVRC]$/ {print $3}' | sort -u > "$work/loader-defined.txt"
dup=$(comm -12 "$work/loader-defined.txt" "$work/archive-defined.txt" || true)
if [[ -n $dup ]]; then
    echo "!! defined by both vk_loader.o and the RADV archive (duplicate symbols at link time):" >&2
    echo "$dup" >&2
    exit 1
fi
echo "    $(basename "$archive"): $(wc -l < "$work/archive-defined.txt") defined symbols, $(grep -c '^vk_icd' "$work/archive-defined.txt") vk_icd*, $(grep -c '^vk[A-Z]' "$work/archive-defined.txt" || true) vk[A-Z]*; no overlap with the loader's $(wc -l < "$work/loader-defined.txt")"

echo "vk-loader: build check passed (port/vk-loader; work $work)"

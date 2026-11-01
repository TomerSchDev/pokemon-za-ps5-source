#!/usr/bin/env bash
# ZA Recomp -> PS5: compile-only audit of the runtime with the PS5 clang - no generated game code, no link.
#
# Every runtime translation unit the Makefile's PLATFORM=ps5 build compiles (runtime/*.c, hle/, services/, nvn/,
# nvn/maxwell/, nvn/vulkan/*.c, platform/ps5.c; then the C++ ones: nvn/vulkan/*.cpp, ui/*.mm as C++, the ImGui objects)
# is compiled with the same flags, every error kept (-ferror-limit=0), and the objects that came out are checked for
# the symbols they need against what the console gives a title (the SDK's stub libraries, its static libc / platform
# layer / libc++, clang's builtins, the RADV archive): the link-time gaps without a link.
#
# Run in WSL from anywhere:  bash tools/ps5/compile-runtime.sh
# Output in build/ps5-audit/:  logs/<unit>.log (clang's stderr)   results.tsv (kind, unit, rc, errors, warnings, s)
#   errors.tsv (file, line, message)   error-groups.txt   missing-headers.txt   missing-decls.txt   headers.txt
#   undefined.tsv (symbol, provider or MISSING)   summary.txt (printed at the end)
# Environment: PS5_SDK PS5_VULKAN PS5_MESA PS5_CLANG PS5_CLANGXX (ENVIRONMENT.md: the pins), ZA_SDL3_INC (an SDL3
# include dir), ZA_MSYS2_INC (MSYS2's ucrt64/include: shaderc / FFmpeg / VMA), ZA_PC_RESEARCH (research/pokeza-pc), JOBS.
# Real headers are taken from the PC side (ENVIRONMENT.md 5); where none are found, third_party/ps5-stubs stands in.
set -u
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root" || exit 2
PS5_SDK=${PS5_SDK:-/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk}
PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
PS5_MESA=${PS5_MESA:-/home/tomer/ps5-za-native/PS5_Mesa}
PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
PS5_CLANGXX=${PS5_CLANGXX:-/usr/bin/clang++-21}
NM=${PS5_NM:-$PS5_SDK/bin/llvm-nm}
JOBS=${JOBS:-$(nproc)}
pc=${ZA_PC_RESEARCH:-/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc}
msys=${ZA_MSYS2_INC:-/mnt/c/msys64/ucrt64/include}
work=$root/build/ps5-audit

for f in "$PS5_CLANG" "$PS5_CLANGXX" "$NM" "$PS5_SDK/target/include/ps5platform/kernel.h" "$PS5_MESA/include/vulkan/vulkan.h"; do
    [[ -e $f ]] || { echo "missing $f" >&2; exit 2; }
done
rm -rf "$work"
mkdir -p "$work/obj" "$work/logs" "$work/inc" "$work/gen" "$work/providers"

# ---- headers: the real ones where the PC has them, the marked stubs otherwise
inc=(-I"$PS5_MESA/include")  # Vulkan: the Mesa fork's (what the RADV archive implements)
sdl=
for d in "${ZA_SDL3_INC:-}" "$pc/runtime-opt-r1/SDL3-3.4.18/x86_64-w64-mingw32/include" "$msys"; do
    [[ -n $d && -f $d/SDL3/SDL.h ]] && { sdl=$d; break; }
done
# MSYS2's ucrt64/include also holds mingw's own libc headers: never whole on the include path - only its third-party
# subdirectories, linked into a staging dir
if [[ -n $sdl ]]; then
    if [[ $sdl == "$msys" ]]; then ln -sfn "$msys/SDL3" "$work/inc/SDL3"; else inc+=(-I"$sdl"); fi
fi
for sub in shaderc libavcodec libavformat libavutil libswscale vma; do
    [[ -d $msys/$sub ]] && ln -sfn "$msys/$sub" "$work/inc/$sub"
done
[[ -f $msys/vk_mem_alloc.h ]] && ln -sfn "$msys/vk_mem_alloc.h" "$work/inc/vk_mem_alloc.h"
inc+=(-I"$work/inc" -Ithird_party/ps5-stubs/include)
{
    echo "vulkan: $PS5_MESA/include ($(grep -o 'VK_HEADER_VERSION [0-9]*' "$PS5_MESA/include/vulkan/vulkan_core.h" | head -1))"
    if [[ -n $sdl ]]; then
        v=$(grep -ohE 'SDL_(MAJOR|MINOR|MICRO)_VERSION +[0-9]+' "$sdl/SDL3/SDL_version.h" | awk '{printf "%s.", $2}' | sed 's/\.$//')
        echo "SDL3: $sdl ($v)"
    else
        echo "SDL3: STUB (third_party/ps5-stubs)"
    fi
    for sub in shaderc libavcodec libavformat libavutil libswscale vma; do
        if [[ -d $msys/$sub ]]; then echo "$sub: $msys/$sub"; else echo "$sub: STUB (third_party/ps5-stubs)"; fi
    done
    echo "imgui: third_party/imgui"
} > "$work/headers.txt"

# ---- flags: the Makefile's PLATFORM=ps5 (RTFLAGS / CXXFLAGS / UIFLAGS without -g)
target=(-target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default -isysroot "$PS5_SDK"
        -isystem "$PS5_SDK/target/include/c++/v1" -isystem "$PS5_SDK/target/include"
        -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee)
osflags=(-DZA_PS5 -DLARECOMP_STATIC_GAMELIB -Wno-format)
diag=(-ferror-limit=0 -fno-caret-diagnostics -fno-color-diagnostics -Wno-unused-command-line-argument)
rtflags=(-O2 -fno-strict-aliasing -Wall -Wno-unused-function -Iruntime -Iruntime/nvn "${inc[@]}" "${osflags[@]}")
cxxflags=(-O2 -std=c++17 -Ithird_party/imgui -Ithird_party/imgui/backends -Iruntime -Iruntime/nvn "${inc[@]}"
          -DIMGUI_DISABLE_DEFAULT_SHELL_FUNCTIONS)  # (the Makefile's IMGUI_DEFS: no fork / execvp in a title)
gamelib_defs=(-DGAMELIB_ID='"ps5audit"' -DGAMELIB_CFLAGS='"-O1 -DGUEST_VOLATILE -DZA_PS5 -march=x86-64-v3"' -DGAMELIB_SHARED='""')
# SMAA's shader as a C string (the Makefile's $(B)/inc/smaa_hlsl.inc rule)
LC_ALL=C tr -d '\r' < third_party/smaa/SMAA.hlsl | LC_ALL=C tr '\200-\377' '?' |
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/^/"/' -e 's/$/\\n"/' > "$work/gen/smaa_hlsl.inc"

# ---- the units
units=$work/units.txt
: > "$units"
for f in runtime/*.c runtime/hle/*.c runtime/services/*.c runtime/nvn/*.c runtime/nvn/maxwell/*.c runtime/nvn/vulkan/*.c \
         runtime/platform/ps5.c runtime/platform/ps5_fiber.c; do printf 'c\t%s\n' "$f"; done >> "$units"
for f in runtime/nvn/vulkan/*.cpp; do printf 'cpp\t%s\n' "$f"; done >> "$units"
for f in runtime/ui/*.mm; do printf 'mm\t%s\n' "$f"; done >> "$units"
for f in third_party/imgui/imgui.cpp third_party/imgui/imgui_draw.cpp third_party/imgui/imgui_tables.cpp \
         third_party/imgui/imgui_widgets.cpp third_party/imgui/backends/imgui_impl_sdl3.cpp \
         third_party/imgui/backends/imgui_impl_vulkan.cpp; do printf 'imgui\t%s\n' "$f"; done >> "$units"

compile_one() {
    local kind=$1 src=$2
    local name=${src#runtime/}
    name=${name#third_party/imgui/}
    name=${name//\//__}
    local obj=$work/obj/$name.o log=$work/logs/$name.log
    local -a cmd
    case $kind in
        c) cmd=("$PS5_CLANG" "${target[@]}" "${rtflags[@]}" "${diag[@]}") ;;
        cpp) cmd=("$PS5_CLANGXX" "${target[@]}" "${cxxflags[@]}" "${osflags[@]}" "${diag[@]}") ;;
        mm) cmd=("$PS5_CLANGXX" "${target[@]}" "${cxxflags[@]}" -x c++ "${osflags[@]}" "${diag[@]}") ;;
        imgui) cmd=("$PS5_CLANGXX" "${target[@]}" "${cxxflags[@]}" "${diag[@]}") ;;
    esac
    case $src in
        runtime/gamebuild.c|runtime/gamelib.c) cmd+=("${gamelib_defs[@]}") ;;
        runtime/nvn/smaa_data.c) cmd+=(-I"$work/gen" -Ithird_party/smaa/Textures) ;;
    esac
    local t0 t1 rc errors warnings
    t0=$(date +%s.%N)
    "${cmd[@]}" -c "$src" -o "$obj" > "$log" 2>&1
    rc=$?
    t1=$(date +%s.%N)
    errors=$(grep -c ' error: ' "$log")
    warnings=$(grep -c ' warning: ' "$log")
    { printf '%s\t%s\t%d\t%s\t%s\t' "$kind" "$src" "$rc" "$errors" "$warnings"; awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.1f\n", b - a }'; } > "$work/logs/$name.rc"
    [[ $rc -eq 0 ]] || rm -f "$obj"  # (clang leaves no object on error; be sure: only clean objects feed the symbol audit)
}

echo "==> compiling $(wc -l < "$units") units with $JOBS jobs (logs: $work/logs)"
while IFS=$'\t' read -r kind src; do
    compile_one "$kind" "$src" &
    while (( $(jobs -r | wc -l) >= JOBS )); do sleep 0.2; done
done < "$units"
wait

# ---- results and error classes
{ printf 'kind\tunit\trc\terrors\twarnings\tseconds\n'; cat "$work"/logs/*.rc | sort -t$'\t' -k1,1 -k2,2; } > "$work/results.tsv"
grep -h ' error: ' "$work"/logs/*.log | sed -E 's/^([^:]+):([0-9]+):[0-9]+: error: /\1\t\2\t/' | sort -u > "$work/errors.tsv"
awk -F'\t' '{ print $3 }' "$work/errors.tsv" | sed -E "s/'[^']*'/'X'/g" | sort | uniq -c | sort -rn > "$work/error-groups.txt"
grep -hoE "'[^']+' file not found" "$work/errors.tsv" | sort | uniq -c | sort -rn > "$work/missing-headers.txt"
grep -hoE "(use of undeclared identifier|implicit declaration of function|call to undeclared function|unknown type name|no member named|use of undeclared library function) '[^']+'" \
    "$work/errors.tsv" | sort | uniq -c | sort -rn > "$work/missing-decls.txt"

# ---- symbols: what the objects need, and who on the console provides it
objs=("$work"/obj/*.o)
prov=$work/providers
if [[ -e ${objs[0]} ]]; then
    "$NM" --undefined-only "${objs[@]}" 2>/dev/null | awk '$1 == "U" { print $2 }' | sort -u > "$work/sym-needed.txt"
    "$NM" --defined-only "${objs[@]}" 2>/dev/null | awk 'NF >= 3 && $2 ~ /^[TDBRWVC]$/ { print $3 }' | sort -u > "$prov/sym-ours.txt"
fi
defined() { "$NM" "$@" 2>/dev/null | awk 'NF >= 3 && $2 ~ /^[TWDBVRC]$/ { print $3 }' | sort -u; }
for so in "$PS5_SDK"/target/lib/*.so; do defined -D --defined-only "$so" > "$prov/$(basename "$so" .so).txt"; done
for a in libc.a libps5platform.a libc++.a libc++abi.a libunwind.a libpthread.a libdl.a; do
    [[ -f $PS5_SDK/target/lib/$a ]] && defined --defined-only "$PS5_SDK/target/lib/$a" > "$prov/${a%.a}.txt"
done
builtins="$("$PS5_CLANG" --print-resource-dir)/lib/linux/libclang_rt.builtins-x86_64.a"
[[ -f $builtins ]] && defined --defined-only "$builtins" > "$prov/builtins.txt"
radv=$PS5_VULKAN/.deps/native/radv-release/lib/libvulkan_radeon.ps5.a
[[ -f $radv ]] && defined --defined-only "$radv" > "$prov/radv.txt"
# the platform layer's ps5_X stands in for X when the link recipe binds it (PS5_Vulkan/tools/radv-link.sh --defsym)
sed -n 's/^ps5_//p' "$prov/libps5platform.txt" | sort -u > "$prov/libps5platform-bound.txt"
# the bindings tools/ps5/link-title.sh checks and makes itself (B2 arc4random: a null import through
# libScePosixForWebKit's stub otherwise; B4 the directory streams): those come from the platform layer for sure
printf '%s\n' arc4random arc4random_buf arc4random_uniform opendir fdopendir readdir rewinddir dirfd closedir |
    grep -xFf "$prov/libps5platform-bound.txt" > "$prov/linktitle-bound.txt" || true
printf '%s\n' __start_hle_impls __stop_hle_impls __start_services __stop_services __start_resets __stop_resets \
    > "$prov/linker.txt"
order=(linker sym-ours linktitle-bound libkernel libkernel_sys libkernel_web libSceLibcInternal libScePosixForWebKit libc
       libps5platform libps5platform-bound libc++ libc++abi libunwind builtins radv)
: > "$work/provider-map.txt"
for p in "${order[@]}"; do
    [[ -f $prov/$p.txt ]] && awk -v p="$p" '{ print $1 "\t" p }' "$prov/$p.txt" >> "$work/provider-map.txt"
done
for so in "$PS5_SDK"/target/lib/*.so; do
    b=$(basename "$so" .so)
    case " ${order[*]} " in *" $b "*) continue ;; esac
    awk -v p="$b" '{ print $1 "\t" p }' "$prov/$b.txt" >> "$work/provider-map.txt"
done
if [[ -f $work/sym-needed.txt ]]; then
    awk -F'\t' 'NR == FNR { if (!($1 in m)) m[$1] = $2; next } { print $1 "\t" (($1 in m) ? m[$1] : "MISSING") }' \
        "$work/provider-map.txt" "$work/sym-needed.txt" |
        awk -F'\t' 'BEGIN { OFS = "\t" }
            $2 == "libScePosixForWebKit" { $2 = $2 " (null at run time)" }
            $2 == "libkernel_sys" { $2 = $2 " (only if the title imports libkernel_sys)" }
            $1 == "localeconv" && $2 == "libSceLibcInternal" { $2 = $2 " (empty decimal point)" }
            $2 == "libps5platform-bound" { $2 = "libps5platform (ps5_ name: bound only if radv-link.sh lists it)" }
            $2 == "linktitle-bound" { $2 = "libps5platform (ps5_ name: bound by tools/ps5/link-title.sh)" }
            { print }' | sort -t$'\t' -k2,2 -k1,1 > "$work/undefined.tsv"
fi

# ---- summary
{
    echo "ZA Recomp runtime compile audit for the PS5 target - $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "clang: $("$PS5_CLANG" --version | head -1); SDK: $(cat "$PS5_SDK/.ps5-sdk-revision" 2>/dev/null); jobs: $JOBS"
    echo
    cat "$work/headers.txt"
    echo
    awk -F'\t' 'NR > 1 { n[$1]++; if ($3 == 0) ok[$1]++; e[$1] += $4; w[$1] += $5; t[$1] += $6 }
        END { for (k in n) printf "%-6s units %3d  compiled %3d  failed %3d  errors %5d  warnings %5d  cpu %.0fs\n", k, n[k], ok[k], n[k] - ok[k], e[k], w[k], t[k] }' \
        "$work/results.tsv" | sort
    echo
    echo "failed units:"
    awk -F'\t' 'NR > 1 && $3 != 0 { printf "  %-40s %4s errors\n", $2, $4 }' "$work/results.tsv"
    echo
    echo "distinct error lines: $(wc -l < "$work/errors.tsv")"
    echo "error groups (identifiers as X):"
    head -60 "$work/error-groups.txt"
    echo
    echo "missing headers:"
    cat "$work/missing-headers.txt"
    echo
    echo "missing declarations (top 60):"
    head -60 "$work/missing-decls.txt"
    if [[ -f $work/undefined.tsv ]]; then
        echo
        echo "undefined symbols of the compiled objects, by provider:"
        awk -F'\t' '{ c[$2]++ } END { for (k in c) printf "  %6d  %s\n", c[k], k }' "$work/undefined.tsv" | sort -rn
        echo
        # Imports the ps5 branch took out of the runtime, each a fault on the console otherwise (the gaps report 3.2):
        # compiler-rt's CPU model (B6: gamelib.c asks cpuid itself), telldir / seekdir (B5: the title's own, ps5.c),
        # link (B8: romfs_build.c), fork / execvp / waitpid (B9: ImGui's shell function is off), ucontext (B10: the
        # fibers switch in the title's own asm, platform/ps5_fiber.c). Any of them wanted from outside the runtime's
        # own objects is a regression.
        forbidden=(__cpu_model __cpu_indicator_init telldir seekdir link fork execvp waitpid getcontext makecontext swapcontext)
        echo "imports the title must not make (regressions; expected none):"
        awk -F'\t' -v list="${forbidden[*]}" 'BEGIN { n = split(list, f, " "); for (i = 1; i <= n; i++) bad[f[i]] = 1 }
            ($1 in bad) && $2 != "sym-ours" { print "  " $1 " <- " $2; found = 1 } END { if (!found) print "  none" }' \
            "$work/undefined.tsv"
        echo
        # (B7) libc's strtod / strtof / atof see no decimal point on the console; platform/ps5_compat.h sends every unit
        # that includes platform.h (rt.h, hle.h) to the title's own parser. The units still on libc's are listed: each
        # reads fractions as whole numbers there (env variables for tests, so far).
        echo "units still importing libc's atof / strtod / strtof (no decimal point on the console):"
        any=
        for o in "${objs[@]}"; do
            s=$("$NM" --undefined-only "$o" 2>/dev/null | awk '$1 == "U" && ($2 == "atof" || $2 == "strtod" || $2 == "strtof") { print $2 }' | sort -u | tr '\n' ' ')
            [[ -n $s ]] && { echo "  $(basename "$o" .o): $s"; any=1; }
        done
        [[ -n $any ]] || echo "  none"
        echo
        echo "MISSING (no provider at all):"
        awk -F'\t' '$2 == "MISSING" { print "  " $1 }' "$work/undefined.tsv"
    fi
} > "$work/summary.txt"
cat "$work/summary.txt"

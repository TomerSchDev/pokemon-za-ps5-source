#!/usr/bin/env bash
# ZA Recomp -> PS5: how long the PS5 clang takes on representative generated files (the lifted game code), to size the
# full build (1,412 units for 2.0.2) before running it. Each file is compiled with the Makefile's PLATFORM=ps5 GENFLAGS
# (GENOPT "-O1 -DGUEST_VOLATILE", GENARCH -march=x86-64-v3, -DZA_PS5) and its wall time, object size and .text size
# recorded. Nothing is copied: the files are read where they are.
#
# Usage (WSL): bash tools/ps5/time-generated.sh <aot dir> <file relative to it>...
#   e.g. bash tools/ps5/time-generated.sh /mnt/c/.../update-2.0.2-20261025/aot main/main_304.c sdk/sdk_090.c
# Environment: PS5_SDK PS5_CLANG GENOPT GENARCH; ZA_TIME_O0=1 also times each file at -O0 (the giant-function policy
# of runtime/gamebuild.c compiles 160 of 1,412 units that way).
# Output: build/ps5-audit/generated/timing.tsv (+ <file>.o / .log), printed at the end.
set -u
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root" || exit 2
[[ $# -ge 2 ]] || { echo "usage: $0 <aot dir> <file>..." >&2; exit 2; }
aot=$1
shift
PS5_SDK=${PS5_SDK:-/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk}
PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
GENOPT=${GENOPT:--O1 -DGUEST_VOLATILE}
GENARCH=${GENARCH:--march=x86-64-v3}
SIZE=${PS5_SIZE:-/usr/lib/llvm-21/bin/llvm-size}
work=$root/build/ps5-audit/generated
mkdir -p "$work"
target=(-target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default -isysroot "$PS5_SDK"
        -isystem "$PS5_SDK/target/include/c++/v1" -isystem "$PS5_SDK/target/include"
        -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee)
# shellcheck disable=SC2206
genflags=($GENOPT -fno-strict-aliasing -Wno-return-type -Wno-unused-label -fvisibility=hidden -Iruntime $GENARCH -DZA_PS5)
out=$work/timing.tsv
printf 'file\topt\tbytes\tlines\tfunctions\tlabels\twall_s\trc\tobj_bytes\ttext_bytes\n' > "$out"

time_one() {
    local f=$1 opt=$2 src=$aot/$1
    local name obj log t0 t1 rc objb text
    name=$(basename "$f" .c)-$opt
    obj=$work/$name.o
    log=$work/$name.log
    local -a flags=("${genflags[@]}")
    [[ $opt == O0 ]] && flags=(-O0 "${genflags[@]:1}")  # (GENOPT's first word is the -O level)
    t0=$(date +%s.%N)
    "$PS5_CLANG" "${target[@]}" "${flags[@]}" -c "$src" -o "$obj" > "$log" 2>&1
    rc=$?
    t1=$(date +%s.%N)
    objb=$( [[ -f $obj ]] && stat -c %s "$obj" || echo 0 )
    text=$( [[ -f $obj && -x $SIZE ]] && "$SIZE" -A "$obj" | awk '$1 == ".text" { print $2 }' || echo "?" )
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%s\t%s\n' "$f" "$opt" "$(stat -c %s "$src")" "$(wc -l < "$src")" \
        "$(grep -c '^void f_' "$src")" "$(grep -c '^L_' "$src")" \
        "$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.1f", b - a }')" "$rc" "$objb" "$text" >> "$out"
}

echo "==> $PS5_CLANG ${genflags[*]} (one file at a time, wall clock)"
for f in "$@"; do
    [[ -f $aot/$f ]] || { echo "missing $aot/$f" >&2; continue; }
    time_one "$f" "${GENOPT%% *}"
    [[ ${ZA_TIME_O0:-0} == 1 ]] && time_one "$f" O0
done
echo "host: $(nproc) cpus, $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ //'); $("$PS5_CLANG" --version | head -1)"
column -t -s $'\t' "$out" 2>/dev/null || cat "$out"

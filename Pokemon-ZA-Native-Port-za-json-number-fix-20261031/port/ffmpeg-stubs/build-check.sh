#!/usr/bin/env bash
# ffmpeg-stubs for the PS5 port of Pokemon Legends Z-A Recomp: compile-only check with the toolchain of
# vk-probe/build-vk-probe.sh (the PS5 clang wrapper of PS5_Vulkan, clang 21, the payload SDK sysroot) against the
# FFmpeg headers the runtime's compile audit used (MSYS2 ucrt64, FFmpeg 8.0.1: tools/ps5/compile-runtime.sh).
# SPDX-License-Identifier: GPL-3.0-or-later
#
# What it checks, in order (any failure stops it):
#   1. the FFmpeg headers are found (only their libav*/libsw* subdirectories, linked into a staging directory:
#      MSYS2's include dir also holds mingw's libc and must never be on the include path whole);
#   2. ffmpeg_stubs.c compiles with -std=c11 -O2 -Wall -Wextra -Werror against those headers, so every stub's
#      signature is checked against FFmpeg's declaration;
#   3. test/consumer.c (the runtime's usage: movie.c and launcher.mm) compiles as C11 and as C++20;
#   4. every av*/sws* symbol the consumer imports, every name in symbols.txt, and every FFmpeg symbol of the audit's
#      undefined.tsv (when reachable) is defined by ffmpeg_stubs.o (llvm-nm); the stubs' own imports are listed;
#   5. runtime/hle/movie.c syntax-checks against the same headers (when the recomp clone is reachable;
#      RUNTIME_CHECK=skip leaves it out).
# Nothing is linked and nothing is written outside the work directory.
#
# Usage (WSL):  bash build-check.sh
# Environment:  PS5_VULKAN, PS5_CLANG, ZA_MSYS2_INC, FFMPEG_STUBS_WORK, POKEZA_RECOMP, RUNTIME_CHECK

set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PS5_VULKAN=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
export PS5_CLANG=${PS5_CLANG:-/usr/bin/clang-21}
export PS5_PAYLOAD_SDK="$PS5_VULKAN/.deps/native/ps5-payload-sdk"
msys=${ZA_MSYS2_INC:-/mnt/c/msys64/ucrt64/include}
work=${FFMPEG_STUBS_WORK:-${TMPDIR:-/tmp}/ffmpeg-stubs-build}
nm=${LLVM_NM:-$PS5_PAYLOAD_SDK/bin/llvm-nm}
[[ -x $nm ]] || nm=/usr/lib/llvm-21/bin/llvm-nm
recomp=${POKEZA_RECOMP:-/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/pokeza-recomp-ps5}

for file in "$PS5_VULKAN/tooling/prospero-clang18" "$PS5_PAYLOAD_SDK/target/include/stdint.h" "$PS5_CLANG" "$nm"; do
    [[ -e $file ]] || { echo "missing $file" >&2; exit 2; }
done

rm -rf -- "$work"
mkdir -p "$work/obj" "$work/inc"
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }

echo "==> [ffmpeg-stubs] 1. the FFmpeg headers ($msys: libavcodec, libavformat, libavutil, libswscale)"
for sub in libavcodec libavformat libavutil libswscale; do
    [[ -f $msys/$sub/version.h ]] || { echo "!! no $msys/$sub (ZA_MSYS2_INC: MSYS2's ucrt64/include with FFmpeg)" >&2; exit 2; }
    ln -sfn "$msys/$sub" "$work/inc/$sub"
done
version() { grep -ohE "define LIB${1}_VERSION_(MAJOR|MINOR|MICRO) +[0-9]+" "$msys/$2/version_major.h" "$msys/$2/version.h" 2>/dev/null | awk '{printf "%s.", $3}' | sed 's/\.$//'; }
echo "    avcodec $(version AVCODEC libavcodec), avformat $(version AVFORMAT libavformat), avutil $(version AVUTIL libavutil), swscale $(version SWSCALE libswscale)"
# the headers are third-party: -isystem keeps their own warnings out of -Werror; ours stay in
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -isystem "$work/inc")

echo "==> [ffmpeg-stubs] 2. ffmpeg_stubs.c (-std=c11 -O2 -Wall -Wextra -Werror)"
cc -std=c11 "${flags[@]}" -c "$root/ffmpeg_stubs.c" -o "$work/obj/ffmpeg_stubs.o"
echo "    ok ($(stat -c %s "$work/obj/ffmpeg_stubs.o") bytes)"

echo "==> [ffmpeg-stubs] 3. test/consumer.c as C11 and as C++20 (launcher.mm is C++)"
cc -std=c11 "${flags[@]}" -c "$root/test/consumer.c" -o "$work/obj/consumer_c.o"
cc -std=c++20 "${flags[@]}" -fno-exceptions -fno-rtti -x c++ -c "$root/test/consumer.c" -o "$work/obj/consumer_cxx.o"

echo "==> [ffmpeg-stubs] 4. every FFmpeg symbol needed is defined by the stubs"
"$nm" --defined-only "$work/obj/ffmpeg_stubs.o" | awk '$2 == "T" {print $3}' | sort -u > "$work/defined.txt"
"$nm" --undefined-only "$work/obj/consumer_c.o" "$work/obj/consumer_cxx.o" | awk '$1 !~ /:$/ {print $NF}' \
    | grep -E '^(av_|avcodec_|avformat_|sws_|swr_)' | sort -u > "$work/consumer-needed.txt"
grep -v '^#' "$root/symbols.txt" | grep . | sort -u > "$work/listed.txt"
check() {  # <what> <needed file>
    local missing
    missing=$(comm -23 "$2" "$work/defined.txt" || true)
    if [[ -n $missing ]]; then
        echo "!! $1 needs FFmpeg symbols the stubs do not define:" >&2
        echo "$missing" >&2
        exit 1
    fi
    echo "    $1: $(wc -l < "$2") needed, all defined"
}
check "test/consumer.c" "$work/consumer-needed.txt"
check "symbols.txt" "$work/listed.txt"
audit=$recomp/build/ps5-audit/undefined.tsv
if [[ -f $audit ]]; then
    awk -F'\t' '$1 ~ /^(av_|avcodec_|avformat_|sws_|swr_)/ && $2 == "MISSING" {print $1}' "$audit" | sort -u > "$work/audit.txt"
    check "undefined.tsv" "$work/audit.txt"
else
    echo "    undefined.tsv not at $audit (POKEZA_RECOMP): skipped"
fi
echo "    stubs defined: $(wc -l < "$work/defined.txt"); imports (libc only): $("$nm" --undefined-only "$work/obj/ffmpeg_stubs.o" | awk '{print $NF}' | sort -u | tr '\n' ' ')"

if [[ ${RUNTIME_CHECK:-} != skip && -f $recomp/runtime/hle/movie.c ]]; then
    echo "==> [ffmpeg-stubs] 5. runtime/hle/movie.c syntax-only against the same headers ($recomp)"
    cc -std=c11 -fsyntax-only -fno-strict-aliasing -Wall -Wno-unused-function -Wno-format -DZA_PS5 -DLARECOMP_STATIC_GAMELIB \
        -I "$recomp/runtime" -I "$recomp/runtime/nvn" -isystem "$work/inc" "$recomp/runtime/hle/movie.c"
    echo "    ok runtime/hle/movie.c"
elif [[ ${RUNTIME_CHECK:-} != skip ]]; then
    echo "==> [ffmpeg-stubs] 5. skipped: the recomp source is not at $recomp (POKEZA_RECOMP to point at it)"
fi

echo "ffmpeg-stubs: build check passed (port/ffmpeg-stubs; work $work)"

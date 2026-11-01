#!/usr/bin/env bash
# r29-ui: compile ONE runtime translation unit of a prepared merge tree with the command that reproduces the pinned
# runtime objects byte for byte - the Makefile's PLATFORM=ps5 "$(CC) $(RTFLAGS) -c" (PS5_TARGET + RTFLAGS, DEPINC with
# PS5_DEPS_INC as every r2x build passed it), offline-title.mk's "-Dmain=za_game_main" for main, and the compile
# directory of the pinned objects by prefix map: they were compiled in /home/tomer/ps5-za-native/perf-r26-20261029/source
# (DW_AT_comp_dir; that tree is gone), so <work> is mapped onto it and the DWARF directories come out identical.
# Proven (R29UI-TREE.json "compile"): main.o and nvn/vulkan/device.o of r28b-dlc-dex-r29ui-20261031 reproduced, cmp identical.
#
# Usage (WSL):  compile-runtime-object.sh <work tree> <unit> <out.o>
#   <work tree>  a prepared /home/tomer/ps5-za-native/r28b-dlc-dex-* tree with source/runtime, port/sdl3-shim/include,
#                port/shaderc-cache/include, inc, source/third_party/ps5-stubs (prepare-merge.sh + the header copies)
#   <unit>       the runtime unit relative to source/runtime without .c, e.g. main, nvn/vulkan/device, hle/input
#   <out.o>      where to write the object (any path; the pinned object to compare with is <work>/source/build/ps5/rt/<unit>.o)
# Not covered: gamelib / gamebuild (the Makefile adds -DGAMELIB_ID, GAMELIB_CFLAGS, GAMELIB_SHARED) and nvn/smaa_data
# (-I$(B)/inc -Ithird_party/smaa/Textures, a generated smaa_hlsl.inc) - said, not refused.
# Environment (ENVIRONMENT.md pins; the defaults are the Makefile's): PS5_PAYLOAD_SDK PS5_MESA PS5_CLANG
set -euo pipefail
[[ $# -eq 3 ]] || { echo "usage: $0 <work tree> <unit e.g. main|nvn/vulkan/device> <out.o>" >&2; exit 2; }
work=$1 unit=$2 out=$3
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)   # the repo (port/ui-v2/tools/.. /.. /..)
sdk=${PS5_PAYLOAD_SDK:-/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk}
mesa=${PS5_MESA:-/home/tomer/ps5-za-native/PS5_Mesa}
clang=${PS5_CLANG:-/usr/bin/clang-21}
r26=/home/tomer/ps5-za-native/perf-r26-20261029   # where the pinned runtime objects were compiled (their debug paths)
[[ -d $work/source/runtime && -f $work/source/runtime/$unit.c ]] || { echo "no $work/source/runtime/$unit.c" >&2; exit 2; }
for d in "$work/port/sdl3-shim/include" "$work/port/shaderc-cache/include" "$work/inc" "$work/source/third_party/ps5-stubs/include" \
         "$project/port/observer-r17" "$mesa/include" "$sdk/target/include"; do
    [[ -d $d ]] || { echo "missing include dir $d" >&2; exit 2; }
done
[[ -x $clang ]] || { echo "missing $clang" >&2; exit 2; }
case $unit in
    main) unit_flags=(-Dmain=za_game_main) ;;                     # offline-title.mk: $(B)/rt/main.o: RTFLAGS += -Dmain=za_game_main
    gamelib|gamebuild|nvn/smaa_data) unit_flags=(); echo "note: $unit needs the Makefile's extra per-unit flags; this command alone will not reproduce it" >&2 ;;
    *) unit_flags=() ;;
esac
out=$(realpath -m -- "$out")   # the compile runs from <work>/source: relative -I and the relative DW_AT_name "runtime/<unit>.c"
mkdir -p "$(dirname -- "$out")"
cd "$work/source"
exec "$clang" -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default -isysroot "$sdk" \
    -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" \
    -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
    -O2 -g -fno-strict-aliasing -Wall -Wno-unused-function -Iruntime -Iruntime/nvn \
    -I"$mesa/include" -I"$work/port/sdl3-shim/include" -I"$work/port/shaderc-cache/include" -I"$work/inc" \
    -I"$project/port/observer-r17" -Ithird_party/ps5-stubs/include \
    -DZA_PS5 -DLARECOMP_STATIC_GAMELIB -Wno-format "${unit_flags[@]}" \
    -ffile-prefix-map="$work=$r26" -c "runtime/$unit.c" -o "$out"

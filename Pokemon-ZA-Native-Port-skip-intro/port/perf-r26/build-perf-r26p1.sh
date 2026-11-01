#!/usr/bin/env bash
# Restore the missing FPS TRIAL row. Only cheats.o changes from the verified r26p image.
# Use a separate work tree and versioned output; no console or save access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
prev=/home/tomer/ps5-za-native/perf-r26p-20261029
work=/home/tomer/ps5-za-native/perf-r26p1-20261029
base=$project/artifacts/randomizer-r26p-play
dist=$project/artifacts/randomizer-r26p1-play
evid=$project/evidence/perf-r26p1
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
mesa=/home/tomer/ps5-za-native/PS5_Mesa/include
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
research=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research
deps=$research/za-switch-mods/lib
ref=$base/llvm-pie-r26p.elf
[[ ! -e $dist ]] || { echo 'Use a new revision: output already exists' >&2; exit 2; }
[[ $(sha256sum "$ref" | cut -d' ' -f1) == 190f5287440ea95a7103e911497dd7917f44f49544f6470a2c3dbd01f28a98d6 ]]
[[ $(sha256sum "$base/PPSA91762/eboot.bin" | cut -d' ' -f1) == 1e1a58ac19d7ba80f654877562d78586f81c3f7750502db5f5df9f36c7dd493b ]]
mkdir -p "$evid"
exec > >(tee "$evid/build.log") 2>&1
if [[ ! -f $work/SNAPSHOT-R26P1 ]]; then
    [[ ! -e $work ]] || { echo 'Incomplete work copy exists; inspect before retry' >&2; exit 2; }
    mkdir "$work"
    cp -a --reflink=auto "$prev/." "$work/"
    date -u +%FT%TZ > "$work/SNAPSHOT-R26P1"
fi
archive=$work/dyn-r26/liblasgame-r26.a
[[ $(sha256sum "$archive" | cut -d' ' -f1) == dc7fb1cf908fe0af17d6997155897e3c71c9e866dfa9e524a9a2ec87583b1626 ]]
obj=$work/objects-r26p1
[[ ! -e $obj ]]
cp -a "$work/objects-r26p" "$obj"
echo 'Rebuilding the menu object only'
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c++20 -fno-exceptions -fno-rtti -O2 -Wall -Wextra -Werror \
    -ffunction-sections -fdata-sections -I"$work/port/sdl3-shim/include" -I"$mesa" -I"$work/source/runtime" \
    -I"$project/port/title" -I"$obj" -I"$project/port/randomizer" -I"$project/port/randomizer/core" \
    -I"$deps/json/include" -I"$deps/mbedtls/include" -c "$root/cheats-r26.cpp" -o "$obj/cheats.o"
: > "$evid/objects-vs-r26p.txt"
for o in "$obj"/*.o; do
    name=$(basename "$o")
    cmp -s "$o" "$prev/objects-r26p/$name" || echo "changed $name" >> "$evid/objects-vs-r26p.txt"
done
[[ $(cat "$evid/objects-vs-r26p.txt") == 'changed cheats.o' ]]
cd "$work/source"
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
wraps='--wrap=SDL_SavePNG --wrap=radv_ps5_submit --wrap=radv_ps5_submit_times --wrap=za_title_frame_cfg --wrap=za_performance_status'
wraps+=' --wrap=sceAgcSuspendPoint --wrap=clock_gettime --wrap=za_prof_note_render --wrap=za_prof_thread_begin --wrap=za_prof_thread_end'
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) $wraps --start-group $(printf '%s ' "${libs[@]}") --end-group"
incs="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r26p1.mk <<MAKE
include offline-title.mk
.PHONY: local-title-r26p1
local-title-r26p1: \$(TITLE_OBJS)
	@mkdir -p \$(B)/title
	bash tools/ps5/link-title.sh \$(B)/title/llvm-pie.elf \$(TITLE_OBJS) $archive
MAKE
make -s -f local-r26p1.mk PLATFORM=ps5 -j"${JOBS:-12}" "PS5_DEPS_INC=$incs" local-title-r26p1
pie=$work/source/build/ps5/title/llvm-pie.elf
: > "$evid/runtime-objects-vs-r26p.txt"
while IFS= read -r -d '' o; do
    rel=${o#"$work/source/build/ps5/rt/"}
    cmp -s "$o" "$prev/source/build/ps5/rt/$rel" || echo "changed $rel" >> "$evid/runtime-objects-vs-r26p.txt"
done < <(find "$work/source/build/ps5/rt" -name '*.o' -print0 | sort -z)
[[ ! -s $evid/runtime-objects-vs-r26p.txt ]]
python3 "$project/port/local-shader-r19/verify-registration.py" "$ref" "$pie" > "$evid/registration.json"
nm=/usr/lib/llvm-21/bin/llvm-nm
for pair in "r26p:$ref" "r26p1:$pie"; do
    "$nm" --dynamic --undefined-only "${pair#*:}" | awk '{print $NF}' | sort > "$evid/imports-${pair%%:*}.txt"
done
diff "$evid/imports-r26p.txt" "$evid/imports-r26p1.txt" > "$evid/imports-diff.txt"
"$nm" --defined-only --extern-only "$pie" | awk '{print $NF}' | sort | uniq -d > "$evid/duplicate-globals.txt"
[[ ! -s $evid/duplicate-globals.txt ]]
/usr/lib/llvm-21/bin/llvm-objdump -d --no-show-raw-insn --disassemble-symbols=menu_handle_event,menu_render "$pie" > "$evid/menu-callers.s"
grep -q 'call.*<za_performance_request>' "$evid/menu-callers.s"
grep -q 'call.*<__wrap_za_performance_status>' "$evid/menu-callers.s"
echo 'Trial request/status linked; original game archive/runtime/imports/registrations preserved'
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
for f in "$base/PPSA91762"/*.txt; do cp "$f" "$dist/PPSA91762/"; done
cp "$pie" "$dist/llvm-pie-r26p1.elf"
diff -rq "$base/PPSA91762" "$dist/PPSA91762" > "$evid/package-vs-r26p.txt" || true
[[ $(grep -c . "$evid/package-vs-r26p.txt") == 1 ]]
grep -q '/eboot.bin differ$' "$evid/package-vs-r26p.txt"
sha256sum "$dist/PPSA91762/eboot.bin" "$dist/llvm-pie-r26p1.elf" > "$evid/SHA256SUMS.txt"
cat "$evid/SHA256SUMS.txt"
echo 'r26p1 built; hardware installation pending'

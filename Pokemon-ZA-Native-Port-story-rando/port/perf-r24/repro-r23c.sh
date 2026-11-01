#!/usr/bin/env bash
# Reproduce the installed r23c image from the perf-r24 copy BEFORE any r24 change, to prove the recipe:
# port/slot-depth-r23c/build.sh with the work tree, objects and outputs moved to perf-r24 (that script itself
# writes the other agent's evidence/artifacts, so it is not run). No console access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/perf-r24-20261029
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-repro-r23c
dist=$work/repro-r23c-dist
evid=$project/evidence/perf-r24/repro-r23c
rm -rf "$obj" "$dist"
mkdir -p "$obj" "$evid"
cp -a "$work"/objects-r23c/. "$obj"/
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
cc -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r23c-slot-depth"' \
    -c "$project/port/local-shader-r19/title_entry-r19.c" -o "$obj/title_entry.o"
cc -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$project/port/slot-depth-r23c-observer" -I"$project/port/observer-r17" \
    -c "$project/port/slot-depth-r23c-observer/observer-r23c.c" -o "$obj/observer.o"
for o in title_entry.o observer.o; do
    if cmp -s "$obj/$o" "$work/objects-r23c/$o"; then echo "[repro] $o identical to r23c's"; else echo "[repro] $o DIFFERS from r23c's"; fi
done
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-repro-r23c.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-repro
local-title-repro:
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
make -s -f local-repro-r23c.mk PLATFORM=ps5 "PS5_DEPS_INC=$runtime_includes" local-title-repro
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
sha256sum "$dist/PPSA91762/eboot.bin" /home/tomer/ps5-za-native/slot-depth-r23c-20261028/package/eboot.bin | tee "$evid/eboot.sha256.txt"
if cmp -s "$dist/PPSA91762/eboot.bin" /home/tomer/ps5-za-native/slot-depth-r23c-20261028/package/eboot.bin; then
    echo "[repro] eboot.bin IDENTICAL to the installed r23c" | tee "$evid/result.txt"
else
    echo "[repro] eboot.bin differs from r23c" | tee "$evid/result.txt"
fi

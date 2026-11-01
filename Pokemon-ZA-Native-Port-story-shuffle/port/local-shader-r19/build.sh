#!/usr/bin/env bash
# Incremental game build only. No network access or console actions.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/compiler-r19-20261028
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r19
dist=$project/artifacts/randomizer-r19a-local-compiler
mkdir -p "$project/evidence/local-shader-r19" "$dist"
exec > >(tee "$project/evidence/local-shader-r19/build.log") 2>&1
[[ $(git -C "$glsl/glslang" rev-parse HEAD) == f0bd0257c308b9a26562c1a30c4748a0219cc951 ]]
cc(){ sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
incs=(-I"$root" -I"$project/port/shaderc-cache/include" -I"$glsl/glslang" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title")
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
for name in worker compiler_adapter shaderc_cache; do
    cc "${flags[@]}" "${incs[@]}" -c "$root/$name.c" -o "$obj/$name.o"
done
cc "${flags[@]}" "${incs[@]}" -I"$project/port/observer-r17" -c "$root/observer-r19.c" -o "$obj/observer.o"
cc "${flags[@]}" "${incs[@]}" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r19a-local-compiler"' \
    -c "$root/title_entry-r19.c" -o "$obj/title_entry.o"
cp "$root/shaders-r19.c" "$work/source/runtime/nvn/vulkan/shaders.c"
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
# Keep every registration referenced through __start_* while discarding unused
# C++ filesystem code from glslang's archives. Verify registration sizes below.
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
# This target deliberately has no generated-game prerequisite. The immutable
# cheat-enabled archive is a link input, never a make target in this tree.
cat > local-r19.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r19
local-title-r19: $(TITLE_OBJS)
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
make -s -f local-r19.mk PLATFORM=ps5 -j4 "PS5_DEPS_INC=$runtime_includes" local-title-r19
python3 "$root/verify-registration.py" \
    /home/tomer/ps5-za-native/capture-r17-20261028/source/build/ps5/title/llvm-pie.elf \
    "$work/source/build/ps5/title/llvm-pie.elf" > "$project/evidence/local-shader-r19/registration.json"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
printf 'local\n' > "$dist/PPSA91762/local-shader-options.txt"
sha256sum "$dist/PPSA91762/eboot.bin" > "$project/evidence/local-shader-r19/eboot.sha256.txt"
cat "$project/evidence/local-shader-r19/eboot.sha256.txt"

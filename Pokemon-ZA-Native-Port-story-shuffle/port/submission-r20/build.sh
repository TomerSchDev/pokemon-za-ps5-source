#!/usr/bin/env bash
# Isolated incremental runtime build. No game-code generation or console access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/batch-r20-20261028
baseline=/home/tomer/ps5-za-native/compiler-r19-20261028
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r20
dist=$project/artifacts/randomizer-r20-batch
mkdir -p "$project/evidence/submission-r20" "$dist"
exec > >(tee "$project/evidence/submission-r20/build.log") 2>&1
for pair in 'submission.h za_submission_r20.h' 'queue.inc za_submission_queue_r20.inc' 'executor.inc za_submission_executor_r20.inc'; do
    read -r src dst <<< "$pair"
    cp "$root/$src" "$work/source/runtime/nvn/vulkan/$dst"
done
# Rebuild title_entry only; r19a shader worker/compiler/cache/observer and r16
# timing/lean/cheat/randomizer objects are reused byte-for-byte.
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r20-batch"' \
    -c "$project/port/local-shader-r19/title_entry-r19.c" -o "$obj/title_entry.o"
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r20.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r20
local-title-r20: $(TITLE_OBJS)
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
make -s -f local-r20.mk PLATFORM=ps5 -j4 "PS5_DEPS_INC=$runtime_includes" local-title-r20
python3 "$project/port/local-shader-r19/verify-registration.py" \
    "$baseline/source/build/ps5/title/llvm-pie.elf" "$work/source/build/ps5/title/llvm-pie.elf" \
    > "$project/evidence/submission-r20/registration.json"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
printf 'local\n' > "$dist/PPSA91762/local-shader-options.txt"
printf 'batch\n' > "$dist/PPSA91762/submission-options.txt"
sha256sum "$dist/PPSA91762/eboot.bin" > "$project/evidence/submission-r20/eboot.sha256.txt"
cat "$project/evidence/submission-r20/eboot.sha256.txt"

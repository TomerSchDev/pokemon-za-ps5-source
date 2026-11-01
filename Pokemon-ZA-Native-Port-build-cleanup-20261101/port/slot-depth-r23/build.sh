#!/usr/bin/env bash
# Independent future A/B build only. No console or NAS access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/slot-depth-r23-20261028
baseline=/home/tomer/ps5-za-native/immutable-spans-r22-20261028
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r23
dist=$project/artifacts/randomizer-r23-slot-depth
mkdir -p "$project/evidence/slot-depth-r23" "$dist"
exec > >(tee "$project/evidence/slot-depth-r23/build.log") 2>&1
python3 - "$project" "$work" <<'PYGATE'
from pathlib import Path
import hashlib,json,sys
root,work=map(Path,sys.argv[1:]);e=root/'evidence/slot-depth-r23'
t=max(e.glob('host-tests-*/result.json'),key=lambda p:p.stat().st_mtime)
r=json.loads(t.read_text());assert r['status']=='passed'
for rel,h in r['input_sha256'].items():assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==h,rel
for rel,h in r['runtime_sha256'].items():assert hashlib.sha256((work/'source'/rel).read_bytes()).hexdigest()==h,rel
ob=root/'evidence/slot-depth-r23-observer'
r=json.loads(max(ob.glob('host-tests-*/result.json'),key=lambda p:p.stat().st_mtime).read_text())
assert r['status']=='passed' if 'status' in r else r['observer_tests']=='passed ASan+UBSan'
assert (root/'port/slot-depth-r23/slot-depth-control.h').read_bytes()==(root/'port/slot-depth-r23-observer/slot-depth-control.h').read_bytes()
PYGATE
# Keep the r19 shader compiler/cache, all game objects and driver archives intact.
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r23-slot-depth"' \
    -c "$project/port/local-shader-r19/title_entry-r19.c" -o "$obj/title_entry.o"
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$project/port/slot-depth-r23-observer" -I"$project/port/observer-r17" -c "$project/port/slot-depth-r23-observer/observer-r23.c" -o "$obj/observer.o"
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r23.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r23
local-title-r23:
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
# Only these two runtime translation units changed. Build them explicitly;
# linking has no all-object prerequisites and retains the other 62 exact objects.
make -s -f local-r23.mk PLATFORM=ps5 -j2 "PS5_DEPS_INC=$runtime_includes" \
    -W runtime/nvn/objects.c -W runtime/nvn/vulkan/exec.c build/ps5/rt/nvn/objects.o build/ps5/rt/nvn/vulkan/exec.o
make -s -f local-r23.mk PLATFORM=ps5 "PS5_DEPS_INC=$runtime_includes" local-title-r23
python3 "$project/port/local-shader-r19/verify-registration.py" \
    "$baseline/source/build/ps5/title/llvm-pie.elf" "$work/source/build/ps5/title/llvm-pie.elf" \
    > "$project/evidence/slot-depth-r23/registration.json"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
printf 'local\n' > "$dist/PPSA91762/local-shader-options.txt"
printf 'batch4\n' > "$dist/PPSA91762/submission-options.txt"
sha256sum "$dist/PPSA91762/eboot.bin" > "$project/evidence/slot-depth-r23/eboot.sha256.txt"
python3 "$root/receipt.py"

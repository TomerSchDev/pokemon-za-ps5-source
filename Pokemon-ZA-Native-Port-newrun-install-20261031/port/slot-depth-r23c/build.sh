#!/usr/bin/env bash
# Observer-only persisted startup request. No console or NAS access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/slot-depth-r23c-20261028
baseline=/home/tomer/ps5-za-native/slot-depth-r23b-20261028
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r23c
dist=$project/artifacts/randomizer-r23c-slot-depth
mkdir -p "$project/evidence/slot-depth-r23c" "$dist"
exec > >(tee "$project/evidence/slot-depth-r23c/build.log") 2>&1
python3 - "$project" "$work" <<'PYGATE'
from pathlib import Path
import hashlib,json,sys
root,work=map(Path,sys.argv[1:])
r=json.loads((root/'evidence/slot-depth-r23c-observer/ready.json').read_text())
assert r['observer_tests']=='passed ASan+UBSan' and r['client_tests']=='passed'
for n,h in r['source_sha256'].items():assert hashlib.sha256((root/'port/slot-depth-r23c-observer'/n).read_bytes()).hexdigest()==h,n
m=json.loads((root/'evidence/slot-depth-r23c/preparation.json').read_text())
for rel,h in m['runtime_sources'].items():assert hashlib.sha256((work/'source/runtime'/rel).read_bytes()).hexdigest()==h,rel
PYGATE
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r23c-slot-depth"' \
    -c "$project/port/local-shader-r19/title_entry-r19.c" -o "$obj/title_entry.o"
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$project/port/slot-depth-r23c-observer" -I"$project/port/observer-r17" \
    -c "$project/port/slot-depth-r23c-observer/observer-r23c.c" -o "$obj/observer.o"
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r23c.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r23c
local-title-r23c:
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
# No runtime compile targets or dependencies: preserve every runtime object byte.
make -s -f local-r23c.mk PLATFORM=ps5 "PS5_DEPS_INC=$runtime_includes" local-title-r23c
python3 "$project/port/local-shader-r19/verify-registration.py" \
    "$baseline/source/build/ps5/title/llvm-pie.elf" "$work/source/build/ps5/title/llvm-pie.elf" \
    > "$project/evidence/slot-depth-r23c/registration.json"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
printf 'local\n' > "$dist/PPSA91762/local-shader-options.txt"
printf 'batch4\n' > "$dist/PPSA91762/submission-options.txt"
# Parent selected16 after both controlled8/16/8 camera comparisons completed.
# Missing/invalid configuration still defaults8; runtime admission remains checked.
printf '16\n' > "$dist/PPSA91762/slot-depth-options.txt"
sha256sum "$dist/PPSA91762/eboot.bin" > "$project/evidence/slot-depth-r23c/eboot.sha256.txt"
python3 "$root/receipt.py"

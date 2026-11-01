#!/usr/bin/env bash
# Independent future A/B build only. No console or NAS access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/immutable-spans-r22-20261028
baseline=/home/tomer/ps5-za-native/preparation-r21c-20261028
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r22
dist=$project/artifacts/randomizer-r22-immutable-spans
mkdir -p "$project/evidence/immutable-spans-r22-integration" "$dist"
exec > >(tee "$project/evidence/immutable-spans-r22-integration/build.log") 2>&1
python3 - "$project" "$work" <<'PYGATE'
from pathlib import Path
import hashlib,json,sys
root,work=map(Path,sys.argv[1:]);e=root/'evidence/immutable-spans-r22-integration'
receipts=list(e.glob('host-tests-*/result.json'));assert receipts,'Run actual integration tests first'
r=json.loads(max(receipts,key=lambda p:p.stat().st_mtime).read_text())
assert r['status']=='passed'
for key in ('immutable_tests','boundary_tests','observer_tests'):assert r[key]=='passed ASan+UBSan'
assert r['client_tests']=='passed' and r['patch_exact_reproduction']
for rel,h in r['input_sha256'].items():assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==h,rel
for rel,h in r['runtime_sha256'].items():assert hashlib.sha256((work/'source'/rel).read_bytes()).hexdigest()==h,rel
PYGATE
# Keep the r19 shader compiler/cache, all game objects and driver archives intact.
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r22-immutable-spans"' \
    -c "$project/port/local-shader-r19/title_entry-r19.c" -o "$obj/title_entry.o"
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$root" -I"$project/port/observer-r17" -c "$root/observer-r22.c" -o "$obj/observer.o"
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r22.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r22
local-title-r22:
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
# Only these two runtime translation units changed. Build them explicitly;
# linking has no all-object prerequisites and retains the other 62 exact objects.
make -s -f local-r22.mk PLATFORM=ps5 -j2 "PS5_DEPS_INC=$runtime_includes" \
    -W runtime/nvn/objects.c -W runtime/nvn/vulkan/exec.c build/ps5/rt/nvn/objects.o build/ps5/rt/nvn/vulkan/exec.o
make -s -f local-r22.mk PLATFORM=ps5 "PS5_DEPS_INC=$runtime_includes" local-title-r22
python3 "$project/port/local-shader-r19/verify-registration.py" \
    "$baseline/source/build/ps5/title/llvm-pie.elf" "$work/source/build/ps5/title/llvm-pie.elf" \
    > "$project/evidence/immutable-spans-r22-integration/registration.json"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
printf 'local\n' > "$dist/PPSA91762/local-shader-options.txt"
printf 'batch4\n' > "$dist/PPSA91762/submission-options.txt"
sha256sum "$dist/PPSA91762/eboot.bin" > "$project/evidence/immutable-spans-r22-integration/eboot.sha256.txt"
python3 "$root/receipt.py"

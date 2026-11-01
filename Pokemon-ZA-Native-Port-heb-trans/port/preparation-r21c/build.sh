#!/usr/bin/env bash
# Isolated incremental runtime build. No game-code generation or console access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/preparation-r21c-20261028
baseline=/home/tomer/ps5-za-native/preparation-r21b-20261028
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r21c
dist=$project/artifacts/randomizer-r21c-preparation
mkdir -p "$project/evidence/preparation-r21c" "$dist"
exec > >(tee "$project/evidence/preparation-r21c/build.log") 2>&1
# The exact observer/client passed ASan/UBSan and strict offline tests.
python3 - "$project" <<'PYGATE'
import hashlib,json,sys,difflib
from pathlib import Path
root=Path(sys.argv[1])
receipts=list((root/'evidence/preparation-r21c').glob('host-tests-*/result.json'))
assert receipts, 'Observer retirement tests have not passed'
r=json.loads(max(receipts,key=lambda p:p.stat().st_mtime).read_text())
assert r['observer_tests']=='passed ASan+UBSan' and r['client_tests']=='passed'
src=root/'port/preparation-r21c'
for n in ('observer-r21c.c','retire-capture.inc','client.py','test-observer.c','test-retire.inc','test-client.py','test.sh'):
    assert hashlib.sha256((src/n).read_bytes()).hexdigest()==r['source_sha256'][n], 'Changed after test: '+n
patch=[]
for old,new in [('observer-r21b.c','observer-r21c.c'),('client.py','client.py'),('retire-capture.inc','retire-capture.inc')]:
    a=(root/'port/preparation-r21b'/old).read_text();b=(src/new).read_text()
    patch.extend(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='r21b/'+old,tofile='r21c/'+new))
(root/'evidence/preparation-r21c/observer-r21c.patch').write_text(''.join(patch))
PYGATE
# Rebuild title_entry and the private observer; r19a shader worker/compiler/cache and r16
# timing/lean/cheat/randomizer objects are reused byte-for-byte.
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r21c-preparation"' \
    -c "$project/port/local-shader-r19/title_entry-r19.c" -o "$obj/title_entry.o"
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
    -I"$root" -I"$project/port/observer-r17" -c "$root/observer-r21c.c" -o "$obj/observer.o"
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r21c.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r21c
local-title-r21c:
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
make -s -f local-r21c.mk PLATFORM=ps5 -j4 "PS5_DEPS_INC=$runtime_includes" local-title-r21c
python3 "$project/port/local-shader-r19/verify-registration.py" \
    "$baseline/source/build/ps5/title/llvm-pie.elf" "$work/source/build/ps5/title/llvm-pie.elf" \
    > "$project/evidence/preparation-r21c/registration.json"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
printf 'local\n' > "$dist/PPSA91762/local-shader-options.txt"
printf 'batch4\n' > "$dist/PPSA91762/submission-options.txt"
sha256sum "$dist/PPSA91762/eboot.bin" > "$project/evidence/preparation-r21c/eboot.sha256.txt"
cat "$project/evidence/preparation-r21c/eboot.sha256.txt"
python3 "$root/receipt.py"

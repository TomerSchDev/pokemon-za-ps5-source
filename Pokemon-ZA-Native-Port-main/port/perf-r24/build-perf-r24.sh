#!/usr/bin/env bash
# r24-perf: the installed r23c (randomizer PPSA91762) plus switchable performance instrumentation and options.
# Same recipe as port/slot-depth-r23c/build.sh (reproduced byte for byte by repro-r23c.sh) on the isolated copy
# /home/tomer/ps5-za-native/perf-r24-20261029, except that the runtime objects are rebuilt (r24 changes runtime
# sources and kernel.h; the Makefile tracks no header dependencies, so all of build/ps5/rt is rebuilt), the
# title entry / observer / shim video object come from r24 sources, and the link wraps two PS5 winsys functions.
# No console, NAS or save access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/perf-r24-20261029
baseline=/home/tomer/ps5-za-native/slot-depth-r23c-20261028
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
mesa=/home/tomer/ps5-za-native/PS5_Mesa
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r24
dist=$project/artifacts/randomizer-r24-perf
evid=$project/evidence/perf-r24
[[ ! -e $dist ]] || { echo "refusing: $dist exists (use a new revision)" >&2; exit 2; }
rm -rf "$obj"
mkdir -p "$obj" "$evid"
exec > >(tee "$evid/build.log") 2>&1
cp -a "$work"/objects-r23c/. "$obj"/
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
echo "[r24] title_entry.o (port/perf-r24/title_entry-r24.c)"
cc "${flags[@]}" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r24-perf"' \
    -c "$root/title_entry-r24.c" -o "$obj/title_entry.o"
echo "[r24] observer.o (port/perf-r24/observer/observer-r24.c: slot depths 8/16/32/64)"
cc "${flags[@]}" -I"$root/observer" -I"$project/port/observer-r17" \
    -c "$root/observer/observer-r24.c" -o "$obj/observer.o"
echo "[r24] sdl3_ps5_video.o (mode=WxH)"
cc "${flags[@]}" -I"$mesa/include" -I"$work/port/sdl3-shim/include" -I"$work/port/shaderc-cache/include" -I"$work/inc" \
    -c "$work/port/sdl3-shim/src/sdl3_ps5_video.c" -o "$obj/sdl3_ps5_video.o"
for o in "$obj"/*.o; do
    b=$(basename "$o")
    cmp -s "$o" "$work/objects-r23c/$b" || echo "[r24] extra object changed vs r23c: $b"
done
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
# r24: exec.c's __wrap_radv_ps5_submit / __wrap_radv_ps5_submit_times stand between the winsys and its timers.
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG --wrap=radv_ps5_submit --wrap=radv_ps5_submit_times --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
rm -rf build/ps5/rt  # (rebuilt from the r24 sources below)
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r24.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r24
local-title-r24: $(TITLE_OBJS)
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
make -s -f local-r24.mk PLATFORM=ps5 -j"${JOBS:-12}" "PS5_DEPS_INC=$runtime_includes" local-title-r24
pie=$work/source/build/ps5/title/llvm-pie.elf
python3 "$project/port/local-shader-r19/verify-registration.py" \
    "$baseline/source/build/ps5/title/llvm-pie.elf" "$pie" > "$evid/registration.json"
nm=/usr/lib/llvm-21/bin/llvm-nm
"$nm" --dynamic --undefined-only "$baseline/source/build/ps5/title/llvm-pie.elf" | awk '{print $NF}' | sort > "$evid/imports-r23c.txt"
"$nm" --dynamic --undefined-only "$pie" | awk '{print $NF}' | sort > "$evid/imports-r24.txt"
diff "$evid/imports-r23c.txt" "$evid/imports-r24.txt" > "$evid/imports-diff.txt" || true
"$nm" --defined-only "$pie" | grep -E ' (__wrap_radv_ps5_submit|__wrap_radv_ps5_submit_times|radv_ps5_submit|radv_ps5_submit_times|SDL_Vulkan_CreateSurface|rt_dispatch|klock_take)$' \
    > "$evid/key-symbols.txt"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
app=$dist/PPSA91762
# r23c's six option files, byte for byte from its installed package (Update.zip), each checked against the SHA-256
# its Packaging.json records. performance-options.txt is r16's ("optimized\n": key memo and cbuf lean on) - r24's
# own options are in a separate file below.
r23c_package=$project/deliverables/ZA-Performance-r23c-20261028-223050Z
python3 - "$r23c_package" "$app" <<'PY'
import hashlib, json, sys, zipfile
from pathlib import Path
package, app = map(Path, sys.argv[1:])
recorded = json.loads((package / 'Packaging.json').read_text(encoding='utf-8'))['explicit_configs']
with zipfile.ZipFile(package / 'Update.zip') as z:
    for name, pin in sorted(recorded.items()):
        data = z.read('PPSA91762/' + name)
        assert len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'], name
        (app / name).write_bytes(data)
        print(f'[r24] {name}: {data!r} (as r23c, sha256 {pin["sha256"][:16]}...)')
PY
cat > "$app/perf-r24-options.txt" <<'OPTS'
# r24-perf options (read once at start; a missing file or key = r23c behaviour). See port/perf-r24/README-HE.md.
gaps=1
dcache=tls
prof=0
# mode=1920x1080
OPTS
sha256sum "$app/eboot.bin" | tee "$evid/eboot.sha256.txt"
echo "r24-perf built: $app"

#!/usr/bin/env bash
# r24-prof: r24-perf (port/perf-r24/build-perf-r24.sh, eboot a7890eca...6a5610) plus scale / force60 / a sampling
# CPU profiler. Same recipe on the isolated copy /home/tomer/ps5-za-native/perf-r24prof-20261029: the runtime is
# rebuilt after apply-runtime-r24prof.py (kernel.c, nvn/objects.c, nvn/vulkan/device.c), title_entry.o comes from
# title_entry-r24prof.c, za_prof.o is added, and the link wraps r16's frame-mode hook and status
# (za_title_frame_cfg, za_performance_status) and sceAgcSuspendPoint (RADV's kick thread) besides r24's wraps.
# Every other object is r24's, byte for byte. No console, NAS or save access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/perf-r24prof-20261029
r24=/home/tomer/ps5-za-native/perf-r24-20261029
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
mesa=/home/tomer/ps5-za-native/PS5_Mesa
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r24prof
dist=$project/artifacts/randomizer-r24-prof
evid=$project/evidence/perf-r24prof
[[ ! -e $dist ]] || { echo "refusing: $dist exists (use a new revision)" >&2; exit 2; }
rm -rf "$obj"
mkdir -p "$obj" "$evid"
exec > >(tee "$evid/build.log") 2>&1
python3 "$root/apply-runtime-r24prof.py" "$work/source/runtime"
cp -a "$work"/objects-r24/. "$obj"/
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
echo "[r24prof] title_entry.o (port/perf-r24prof/title_entry-r24prof.c)"
cc "${flags[@]}" -I"$root" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r24-prof"' \
    -c "$root/title_entry-r24prof.c" -o "$obj/title_entry.o"
echo "[r24prof] za_prof.o (port/perf-r24prof/za_prof.c)"
cc "${flags[@]}" -I"$root" -c "$root/za_prof.c" -o "$obj/za_prof.o"
for o in "$obj"/*.o; do
    b=$(basename "$o")
    if [[ -f $work/objects-r24/$b ]]; then cmp -s "$o" "$work/objects-r24/$b" || echo "[r24prof] object changed vs r24: $b"
    else echo "[r24prof] object added vs r24: $b"; fi
done
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) --wrap=SDL_SavePNG --wrap=radv_ps5_submit --wrap=radv_ps5_submit_times --wrap=za_title_frame_cfg --wrap=za_performance_status --wrap=sceAgcSuspendPoint --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
rm -rf build/ps5/rt  # (rebuilt: the hooks are in three runtime sources and nothing tracks header dependencies)
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r24prof.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r24prof
local-title-r24prof: $(TITLE_OBJS)
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
make -s -f local-r24prof.mk PLATFORM=ps5 -j"${JOBS:-12}" "PS5_DEPS_INC=$runtime_includes" local-title-r24prof
pie=$work/source/build/ps5/title/llvm-pie.elf
r24pie=$r24/source/build/ps5/title/llvm-pie.elf
python3 "$project/port/local-shader-r19/verify-registration.py" "$r24pie" "$pie" > "$evid/registration.json"
nm=/usr/lib/llvm-21/bin/llvm-nm
objcopy=/usr/lib/llvm-21/bin/llvm-objcopy
"$nm" --dynamic --undefined-only "$r24pie" | awk '{print $NF}' | sort > "$evid/imports-r24.txt"
"$nm" --dynamic --undefined-only "$pie" | awk '{print $NF}' | sort > "$evid/imports-r24prof.txt"
diff "$evid/imports-r24.txt" "$evid/imports-r24prof.txt" > "$evid/imports-diff.txt" || true
"$nm" --defined-only "$pie" | grep -E ' (__wrap_[A-Za-z_]+|za_title_frame_cfg|za_performance_status|za_prof_[a-z_]+|radv_ps5_submit|radv_ps5_submit_times)$' \
    > "$evid/key-symbols.txt"
# runtime objects vs r24's, without debug info: only kernel.o, objects.o and device.o are expected to differ (and
# objects embedding the build path in an assert string - reported separately)
: > "$evid/runtime-objects-vs-r24.txt"
tmp=$(mktemp -d)
while IFS= read -r -d '' o; do
    rel=${o#"$work/source/build/ps5/rt/"}
    ref=$r24/source/build/ps5/rt/$rel
    if [[ ! -f $ref ]]; then echo "added $rel" >> "$evid/runtime-objects-vs-r24.txt"; continue; fi
    "$objcopy" --strip-debug "$o" "$tmp/a.o"; "$objcopy" --strip-debug "$ref" "$tmp/b.o"
    if cmp -s "$tmp/a.o" "$tmp/b.o"; then continue; fi
    # (the build directory's name differs: perf-r24-20261029 vs perf-r24prof-20261029)
    if strings -a "$tmp/a.o" | sed 's/perf-r24prof-20261029/perf-r24-20261029/g' | cmp -s - <(strings -a "$tmp/b.o") &&
       [[ $(stat -c %s "$tmp/a.o") != 0 ]] && ! grep -q "r24-prof\|za_prof" <(strings -a "$tmp/a.o"); then
        echo "path-only $rel" >> "$evid/runtime-objects-vs-r24.txt"
    else
        echo "changed $rel" >> "$evid/runtime-objects-vs-r24.txt"
    fi
done < <(find "$work/source/build/ps5/rt" -name '*.o' -print0 | sort -z)
rm -rf "$tmp"
cat "$evid/runtime-objects-vs-r24.txt"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
app=$dist/PPSA91762
# r23c's six option files, byte for byte from its installed package (Update.zip), each checked against the SHA-256
# its Packaging.json records (as r24-perf). performance-options.txt is r16's ("optimized\n").
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
        print(f'[r24prof] {name}: {data!r} (as r23c, sha256 {pin["sha256"][:16]}...)')
PY
cat > "$app/perf-r24-options.txt" <<'OPTS'
# r24-prof options (read once at start; a missing file or key = r23c behaviour). See port/perf-r24prof/README-HE.md.
gaps=1
dcache=tls
prof=0
# mode=1920x1080
# scale=1
# force60=1
# sample=1
# sample_us=1000
# sample_threads=all
# sample_seconds=20
# sample_keep=30
OPTS
# The exact PIE the image was converted from, for symbolize_samples.py (the build tree's copy is overwritten by the
# next build). Next to the package, not in it.
cp "$pie" "$dist/llvm-pie-r24prof.elf"
sha256sum "$app/eboot.bin" | tee "$evid/eboot.sha256.txt"
sha256sum "$dist/llvm-pie-r24prof.elf" | tee "$evid/pie.sha256.txt"
echo "r24-prof built: $app"

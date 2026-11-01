#!/usr/bin/env bash
# r24-clock: r24-prof (port/perf-r24prof/build-perf-r24prof.sh, eboot 64acf8fa...4fb3) plus vkprof / ticks / tsc and a
# count of every clock_gettime per thread class. Same recipe on the isolated copy
# /home/tomer/ps5-za-native/perf-r24clock-20261029 (rsync -a of perf-r24prof-20261029): the runtime is rebuilt after
# apply-runtime-r24clock.py (exec.c, platform/ps5.c, and the SDL3 shim's sdl3_ps5_core.c in the copy), title_entry.o
# comes from title_entry-r24clock.c, sdl3_ps5_core.o is rebuilt (its unmodified source rebuilds byte-identical to
# r24-prof's object, strip-debug), za_clock.o is added, and the link adds --wrap=clock_gettime and wraps of
# r24-prof's thread hooks to r24-prof's wraps. Every other object is r24-prof's, byte for byte. No console, NAS or
# save access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/perf-r24clock-20261029
prof=/home/tomer/ps5-za-native/perf-r24prof-20261029
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
mesa=/home/tomer/ps5-za-native/PS5_Mesa
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r24clock
dist=$project/artifacts/randomizer-r24-clock
evid=$project/evidence/perf-r24clock
ref_pie=$project/artifacts/randomizer-r24-prof/llvm-pie-r24prof.elf
ref_pie_sha=c8491adbe9fa5dd310aad4e586b7ebe3c87048af50b536fc5704a60d6159b36d
[[ ! -e $dist ]] || { echo "refusing: $dist exists (use a new revision)" >&2; exit 2; }
[[ $(sha256sum "$ref_pie" | cut -d' ' -f1) == "$ref_pie_sha" ]] || { echo "r24-prof's PIE does not match its record" >&2; exit 2; }
rm -rf "$obj"
mkdir -p "$obj" "$evid"
exec > >(tee "$evid/build.log") 2>&1
python3 "$project/port/perf-r24prof/apply-runtime-r24prof.py" "$work/source/runtime"   # (already in the copy: no-op)
python3 "$root/apply-runtime-r24clock.py" "$work"
cp -a "$work"/objects-r24prof/. "$obj"/
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
echo "[r24clock] title_entry.o (port/perf-r24clock/title_entry-r24clock.c)"
cc "${flags[@]}" -I"$root" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r24-clock"' \
    -c "$root/title_entry-r24clock.c" -o "$obj/title_entry.o"
echo "[r24clock] za_clock.o (port/perf-r24clock/za_clock.c)"
cc "${flags[@]}" -c "$root/za_clock.c" -o "$obj/za_clock.o"
echo "[r24clock] sdl3_ps5_core.o (the copy's port/sdl3-shim/src/sdl3_ps5_core.c, ticks=tsc switch)"
cc "${flags[@]}" -I"$mesa/include" -I"$work/port/sdl3-shim/include" -I"$work/port/shaderc-cache/include" -I"$work/inc" \
    -c "$work/port/sdl3-shim/src/sdl3_ps5_core.c" -o "$obj/sdl3_ps5_core.o"
for o in "$obj"/*.o; do
    b=$(basename "$o")
    if [[ -f $work/objects-r24prof/$b ]]; then cmp -s "$o" "$work/objects-r24prof/$b" || echo "[r24clock] object changed vs r24-prof: $b"
    else echo "[r24clock] object added vs r24-prof: $b"; fi
done
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
wraps="--wrap=SDL_SavePNG --wrap=radv_ps5_submit --wrap=radv_ps5_submit_times --wrap=za_title_frame_cfg --wrap=za_performance_status"
wraps+=" --wrap=sceAgcSuspendPoint --wrap=clock_gettime --wrap=za_prof_note_render --wrap=za_prof_thread_begin --wrap=za_prof_thread_end"
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) $wraps --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
rm -rf build/ps5/rt  # (rebuilt: the hooks are in runtime sources and nothing tracks header dependencies)
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r24clock.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r24clock
local-title-r24clock: $(TITLE_OBJS)
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
make -s -f local-r24clock.mk PLATFORM=ps5 -j"${JOBS:-12}" "PS5_DEPS_INC=$runtime_includes" local-title-r24clock
pie=$work/source/build/ps5/title/llvm-pie.elf
python3 "$project/port/local-shader-r19/verify-registration.py" "$ref_pie" "$pie" > "$evid/registration.json"
nm=/usr/lib/llvm-21/bin/llvm-nm
objcopy=/usr/lib/llvm-21/bin/llvm-objcopy
objdump=/usr/lib/llvm-21/bin/llvm-objdump
"$nm" --dynamic --undefined-only "$ref_pie" | awk '{print $NF}' | sort > "$evid/imports-r24prof.txt"
"$nm" --dynamic --undefined-only "$pie" | awk '{print $NF}' | sort > "$evid/imports-r24clock.txt"
diff "$evid/imports-r24prof.txt" "$evid/imports-r24clock.txt" > "$evid/imports-diff.txt" || true
"$nm" --defined-only "$pie" | grep -E ' (__wrap_[A-Za-z_]+|za_clock_report|za_prof_note_render|za_prof_thread_begin|za_prof_thread_end|clock_gettime)$' \
    > "$evid/key-symbols.txt" || true
# Who calls clock_gettime in the image: only __wrap_clock_gettime may call the import; the known users must call the wrap.
"$objdump" -d --no-show-raw-insn \
    --disassemble-symbols=__wrap_clock_gettime,plat_now_ns,ticks_clock_ns,os_time_get_nano,os_time_get_absolute_timeout,SDL_GetTicksNS,sdl3_ps5_now_ns \
    "$pie" > "$evid/clock-callers.s" 2>/dev/null || true
grep -nE "call|jmp.*<" "$evid/clock-callers.s" | grep -E "clock_gettime|__wrap_clock_gettime" > "$evid/clock-calls.txt" || true
# runtime objects vs r24-prof's, without debug info: exec.o and platform/ps5.o are expected to differ (and objects
# embedding the build path in an assert string - reported separately)
: > "$evid/runtime-objects-vs-r24prof.txt"
tmp=$(mktemp -d)
while IFS= read -r -d '' o; do
    rel=${o#"$work/source/build/ps5/rt/"}
    ref=$prof/source/build/ps5/rt/$rel
    if [[ ! -f $ref ]]; then echo "added $rel" >> "$evid/runtime-objects-vs-r24prof.txt"; continue; fi
    "$objcopy" --strip-debug "$o" "$tmp/a.o"; "$objcopy" --strip-debug "$ref" "$tmp/b.o"
    if cmp -s "$tmp/a.o" "$tmp/b.o"; then continue; fi
    if strings -a "$tmp/a.o" | sed 's/perf-r24clock-20261029/perf-r24prof-20261029/g' | cmp -s - <(strings -a "$tmp/b.o") &&
       ! grep -q "r24clock\|r24-clock\|za_clock" <(strings -a "$tmp/a.o"); then
        echo "path-only $rel" >> "$evid/runtime-objects-vs-r24prof.txt"
    else
        echo "changed $rel" >> "$evid/runtime-objects-vs-r24prof.txt"
    fi
done < <(find "$work/source/build/ps5/rt" -name '*.o' -print0 | sort -z)
rm -rf "$tmp"
cat "$evid/runtime-objects-vs-r24prof.txt"
diff -u "$prof/source/runtime/nvn/vulkan/exec.c" "$work/source/runtime/nvn/vulkan/exec.c" > "$evid/exec.c.diff" || true
diff -u "$prof/source/runtime/platform/ps5.c" "$work/source/runtime/platform/ps5.c" > "$evid/ps5.c.diff" || true
diff -u "$prof/port/sdl3-shim/src/sdl3_ps5_core.c" "$work/port/sdl3-shim/src/sdl3_ps5_core.c" > "$evid/sdl3_ps5_core.c.diff" || true
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
app=$dist/PPSA91762
# r23c's six option files, byte for byte from its installed package (Update.zip), each checked against the SHA-256
# its Packaging.json records (as r24-perf / r24-prof). performance-options.txt is r16's ("optimized\n").
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
        print(f'[r24clock] {name}: {data!r} (as r23c, sha256 {pin["sha256"][:16]}...)')
PY
# The quick test's configuration (TEST-CLOCK-r24clock-HE.md, boot A): 4K output rendered at 1080p and the 60 FPS
# mode forced, every measurement key off. A test package, not one to play on (force60 = slow motion below 60 FPS).
cat > "$app/perf-r24-options.txt" <<'OPTS'
# r24-clock options (read once at start; a missing file or key = r23c behaviour). See port/perf-r24clock/README-HE.md.
# Test configuration: 4K output rendered at 1080p, the 60 FPS mode forced (slow motion below 60 FPS; not for play).
scale=1
force60=1
# vkprof=0
# ticks=tsc
# tsc=1
# gaps=1
# dcache=tls
# prof=0
# mode=1920x1080
# sample=1
# sample_us=1000
# sample_threads=all
# sample_seconds=20
# sample_keep=30
OPTS
# The exact PIE the image was converted from, for symbolize_samples.py (the build tree's copy is overwritten by the
# next build). Next to the package, not in it.
cp "$pie" "$dist/llvm-pie-r24clock.elf"
sha256sum "$app/eboot.bin" | tee "$evid/eboot.sha256.txt"
sha256sum "$dist/llvm-pie-r24clock.elf" | tee "$evid/pie.sha256.txt"
echo "r24-clock built: $app"

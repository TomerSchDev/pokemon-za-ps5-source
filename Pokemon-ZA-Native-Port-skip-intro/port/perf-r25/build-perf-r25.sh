#!/usr/bin/env bash
# r25-perf: r24-clock (port/perf-r24clock/build-perf-r24clock.sh, eboot 35ee54da...573e) plus submit=thread (a submitter
# thread for vkQueueSubmit2 / vkQueuePresentKHR), clock=tsc (CLOCK_MONOTONIC from the TSC after a cross-core check, the
# game's timing kept on the real clock) and the render thread's own exec / submit / acquire timers. Same recipe on the
# isolated copy /home/tomer/ps5-za-native/perf-r25-20261029 (rsync -a of perf-r24clock-20261029): the runtime is
# rebuilt after apply-runtime-r25.py (exec.c and its submission .incs, device.c, platform/ps5.c, services/audio.c in the
# copy), title_entry.o comes from title_entry-r25.c, za_clock.o is replaced by za_clock_r25.o (a superset: the same
# counter and wraps, plus clock=tsc, and the radv_threaded=1 path for RADV's recording worker). Every other object is
# r24-clock's, byte for byte. radv_threaded=1 only sets RADV_THREADED_RECORDING: RADV's threaded layer is already in the
# linked archive (PS5_Mesa d0d7325e; checked below). No console, NAS or save access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/perf-r25-20261029
prev=/home/tomer/ps5-za-native/perf-r24clock-20261029
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
mesa=/home/tomer/ps5-za-native/PS5_Mesa
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
obj=$work/objects-r25
dist=$project/artifacts/randomizer-r25-perf
evid=$project/evidence/perf-r25
ref_pie=$project/artifacts/randomizer-r24-clock/llvm-pie-r24clock.elf
ref_pie_sha=8feaf3fd3e2b3c2be21e5639e6032b54ca8b4ce4eb879599dae4c4aff06a62e4
[[ ! -e $dist ]] || { echo "refusing: $dist exists (use a new revision)" >&2; exit 2; }
[[ $(sha256sum "$ref_pie" | cut -d' ' -f1) == "$ref_pie_sha" ]] || { echo "r24-clock's PIE does not match its record" >&2; exit 2; }
rm -rf "$obj"
mkdir -p "$obj" "$evid"
exec > >(tee "$evid/build.log") 2>&1
python3 "$project/port/perf-r24prof/apply-runtime-r24prof.py" "$work/source/runtime"   # (already in the copy: no-op)
python3 "$project/port/perf-r24clock/apply-runtime-r24clock.py" "$work"               # (already in the copy: no-op)
python3 "$root/apply-runtime-r25.py" "$work"
cp -a "$work"/objects-r24clock/. "$obj"/
rm -f "$obj/za_clock.o"   # (replaced by za_clock_r25.o: same symbols, plus clock=tsc)
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
echo "[r25] title_entry.o (port/perf-r25/title_entry-r25.c)"
cc "${flags[@]}" -I"$root" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r25-perf"' \
    -c "$root/title_entry-r25.c" -o "$obj/title_entry.o"
echo "[r25] za_clock_r25.o (port/perf-r25/za_clock_r25.c)"
cc "${flags[@]}" -c "$root/za_clock_r25.c" -o "$obj/za_clock_r25.o"
for o in "$obj"/*.o; do
    b=$(basename "$o")
    if [[ -f $work/objects-r24clock/$b ]]; then cmp -s "$o" "$work/objects-r24clock/$b" || echo "[r25] object changed vs r24-clock: $b"
    else echo "[r25] object added vs r24-clock: $b"; fi
done
for b in $(ls "$work/objects-r24clock"); do [[ -e $obj/$b ]] || echo "[r25] object removed vs r24-clock: $b"; done
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
wraps="--wrap=SDL_SavePNG --wrap=radv_ps5_submit --wrap=radv_ps5_submit_times --wrap=za_title_frame_cfg --wrap=za_performance_status"
wraps+=" --wrap=sceAgcSuspendPoint --wrap=clock_gettime --wrap=za_prof_note_render --wrap=za_prof_thread_begin --wrap=za_prof_thread_end"
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) $wraps --start-group $(printf '%s ' "${libs[@]}") --end-group"
cd "$work/source"
rm -rf build/ps5/rt  # (rebuilt: the hooks are in runtime sources and nothing tracks header dependencies)
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r25.mk <<'MAKE'
include offline-title.mk
.PHONY: local-title-r25
local-title-r25: $(TITLE_OBJS)
	@mkdir -p $(B)/title
	bash tools/ps5/link-title.sh $(B)/title/llvm-pie.elf $(TITLE_OBJS) /home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
MAKE
make -s -f local-r25.mk PLATFORM=ps5 -j"${JOBS:-12}" "PS5_DEPS_INC=$runtime_includes" local-title-r25
pie=$work/source/build/ps5/title/llvm-pie.elf
python3 "$project/port/local-shader-r19/verify-registration.py" "$ref_pie" "$pie" > "$evid/registration.json"
nm=/usr/lib/llvm-21/bin/llvm-nm
objcopy=/usr/lib/llvm-21/bin/llvm-objcopy
objdump=/usr/lib/llvm-21/bin/llvm-objdump
"$nm" --dynamic --undefined-only "$ref_pie" | awk '{print $NF}' | sort > "$evid/imports-r24clock.txt"
"$nm" --dynamic --undefined-only "$pie" | awk '{print $NF}' | sort > "$evid/imports-r25.txt"
diff "$evid/imports-r24clock.txt" "$evid/imports-r25.txt" > "$evid/imports-diff.txt" || true
"$nm" --defined-only "$pie" | grep -E ' (__wrap_[A-Za-z_]+|za_clock_report|za_clock_game_gettime|za_clock_r25_enable|za_clock_r25_radv_threaded|za_r25_[a-z_]+|clock_gettime|radv_threaded_(replaying|recording_enabled|worker|device_init))$' \
    > "$evid/key-symbols.txt" || true
# radv_threaded=1: RADV's threaded layer in the image, the variable it reads, and its worker's clock reads through the
# wrap (the spin between batches: za_clock_r25.c keeps them in cg_radv)
grep -c "RADV_THREADED_RECORDING" "$pie" > "$evid/radv-threaded-string.txt" || true
"$objdump" -d --no-show-raw-insn --disassemble-symbols=radv_threaded_worker,radv_threaded_recording_enabled "$pie" \
    > "$evid/radv-threaded.s" 2>/dev/null || true
grep -nE "<(__wrap_clock_gettime|__real_clock_gettime|clock_gettime|os_get_option|getenv)" "$evid/radv-threaded.s" \
    > "$evid/radv-threaded-refs.txt" || true
cat "$evid/radv-threaded-string.txt" "$evid/radv-threaded-refs.txt"
# global symbols defined twice in the PIE (must be none)
"$nm" --defined-only --extern-only "$pie" | awk '{print $NF}' | sort | uniq -d > "$evid/duplicate-globals.txt" || true
# Who calls clock_gettime / vkQueueSubmit2 / vkQueuePresentKHR / vkAcquireNextImageKHR in the image
"$objdump" -d --no-show-raw-insn \
    --disassemble-symbols=__wrap_clock_gettime,za_clock_game_gettime,plat_now_ns,plat_sleep_until_ns,za_r25_exec,za_submission_driver,za_r25_acquire,za_r25_present,vk_frame_begin,vk_frame_end \
    "$pie" > "$evid/r25-callers.s" 2>/dev/null || true
grep -nE "call.*<(__real_clock_gettime|clock_gettime|__wrap_clock_gettime|za_clock_game_gettime|vkc_QueueSubmit2|vkQueueSubmit2|vkQueuePresentKHR|vkAcquireNextImageKHR|za_r25_[a-z_]+)" \
    "$evid/r25-callers.s" > "$evid/r25-calls.txt" || true
# runtime objects vs r24-clock's, without debug info: exec.o, device.o, platform/ps5.o and services/audio.o are expected
# to differ (and objects embedding the build path in an assert string - reported separately)
: > "$evid/runtime-objects-vs-r24clock.txt"
tmp=$(mktemp -d)
while IFS= read -r -d '' o; do
    rel=${o#"$work/source/build/ps5/rt/"}
    ref=$prev/source/build/ps5/rt/$rel
    if [[ ! -f $ref ]]; then echo "added $rel" >> "$evid/runtime-objects-vs-r24clock.txt"; continue; fi
    "$objcopy" --strip-debug "$o" "$tmp/a.o"; "$objcopy" --strip-debug "$ref" "$tmp/b.o"
    if cmp -s "$tmp/a.o" "$tmp/b.o"; then continue; fi
    if strings -a "$tmp/a.o" | sed 's/perf-r25-20261029/perf-r24clock-20261029/g' | cmp -s - <(strings -a "$tmp/b.o") &&
       ! grep -q "za_r25\|za-r25\|za_clock_game" <(strings -a "$tmp/a.o"); then  # (not bare "r25": the work copy's path has it)
        echo "path-only $rel" >> "$evid/runtime-objects-vs-r24clock.txt"
    else
        echo "changed $rel" >> "$evid/runtime-objects-vs-r24clock.txt"
    fi
done < <(find "$work/source/build/ps5/rt" -name '*.o' -print0 | sort -z)
rm -rf "$tmp"
cat "$evid/runtime-objects-vs-r24clock.txt"
for f in nvn/vulkan/exec.c nvn/vulkan/za_submission_queue_r20.inc nvn/vulkan/za_submission_executor_r20.inc \
         nvn/vulkan/device.c platform/ps5.c services/audio.c; do
    diff -u "$prev/source/runtime/$f" "$work/source/runtime/$f" > "$evid/$(basename "$f").diff" || true
done
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
app=$dist/PPSA91762
# r23c's six option files, byte for byte from its installed package (Update.zip), each checked against the SHA-256
# its Packaging.json records (as r24-perf / r24-prof / r24-clock). performance-options.txt is r16's ("optimized\n").
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
        print(f'[r25] {name}: {data!r} (as r23c, sha256 {pin["sha256"][:16]}...)')
PY
# The test session's base configuration (TEST-r25-HE.md): 4K output rendered at 1080p, the 60 FPS mode forced, cheap
# clocks for the SDL ticks, the renderer's clock-heavy profile off, the GPU timeline on; submit=, clock= and
# radv_threaded= are the A/B keys and stay commented out (= r24-clock behaviour). A test package, not one to play on.
cat > "$app/perf-r24-options.txt" <<'OPTS'
# r25 options (read once at start; a missing file or key = r23c behaviour). See port/perf-r25/README-HE.md.
# Test configuration: 4K output rendered at 1080p, the 60 FPS mode forced (slow motion below 60 FPS; not for play).
scale=1
force60=1
ticks=tsc
vkprof=0
gaps=1
# submit=thread
# clock=tsc
# radv_threaded=1
# tsc=1
# dcache=tls
# prof=0
# mode=1920x1080
# sample=1
# sample_us=1000
# sample_threads=all
# sample_seconds=20
# sample_keep=30
OPTS
cp "$pie" "$dist/llvm-pie-r25.elf"
sha256sum "$app/eboot.bin" | tee "$evid/eboot.sha256.txt"
sha256sum "$dist/llvm-pie-r25.elf" | tee "$evid/pie.sha256.txt"
"$PS5_VULKAN/build/host/ps5-native-tool" self --inspect --file "$app/eboot.bin" > "$evid/self-inspect.txt" 2>&1 || true
tail -3 "$evid/self-inspect.txt"
echo "r25-perf built: $app"

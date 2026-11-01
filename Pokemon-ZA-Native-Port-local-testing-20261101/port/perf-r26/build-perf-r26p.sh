#!/usr/bin/env bash
# r26p-play: r26-perf (port/perf-r26/build-perf-r26.sh, eboot 1685430c...d88c) with the overlay's live FPS counter
# (port/perf-r26/cheats-r26.cpp replaces port/randomizer/cheats.cpp's object) and the fps= key (title_entry-r26p.c,
# za_r26p_options.h), packaged as a PLAY build: perf-r24-options.txt = vkprof=0, ticks=tsc, scale=1, fps=1,
# submit=thread (r25 hardware: submit=thread + slot depth 64 = 53.5 FPS at the cafe vs 47.5, 59.97 at the test spot
# with p99 16.71 ms, no anomalies), slot-depth-options.txt = 64 (r23c's headroom check and fallback to 8 stay),
# submission-options.txt = batch4 (batch8 was 9% slower in r25), clock=tsc / radv_threaded / dyn / force60 off.
# The game archive, the runtime objects and every other title object are r26's, unchanged: only cheats.o and
# title_entry.o are rebuilt. Built on a copy /home/tomer/ps5-za-native/perf-r26p-20261029 of the r26 work copy; the
# r26 copy, its archive and its outputs are not touched. No console, NAS or save access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
prev=/home/tomer/ps5-za-native/perf-r26-20261029
work=/home/tomer/ps5-za-native/perf-r26p-20261029
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
research=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
mesa=/home/tomer/ps5-za-native/PS5_Mesa/include
deps=$research/za-switch-mods/lib
dist=$project/artifacts/randomizer-r26p-play
evid=$project/evidence/perf-r26p
ref_pie=$project/artifacts/randomizer-r26-perf/llvm-pie-r26.elf
ref_pie_sha=b9e35a19b62e82d7e5767d8830924a13d4a5754b84560473f79492404420972c
r26_archive_sha=$(awk '/liblasgame-r26.a/ {print $1}' "$project/evidence/perf-r26/archive.txt")
[[ ! -e $dist ]] || { echo "refusing: $dist exists (use a new revision)" >&2; exit 2; }
[[ $(sha256sum "$ref_pie" | cut -d' ' -f1) == "$ref_pie_sha" ]] || { echo "r26's PIE does not match its record" >&2; exit 2; }
[[ -n $r26_archive_sha ]] || { echo "r26's archive SHA-256 not found in evidence/perf-r26/archive.txt" >&2; exit 2; }
mkdir -p "$evid"
exec > >(tee "$evid/build.log") 2>&1

echo "== [r26p] 1. the work copy: rsync of the r26 copy (its archive, objects and build outputs included)"
if [[ ! -f $work/SNAPSHOT-R26P ]]; then
    rsync -a --delete "$prev/" "$work/"
    date -u +%FT%TZ > "$work/SNAPSHOT-R26P"
fi
archive=$work/dyn-r26/liblasgame-r26.a
[[ $(sha256sum "$archive" | cut -d' ' -f1) == "$r26_archive_sha" ]] || { echo "the r26 archive in the copy does not match its record" >&2; exit 2; }
echo "archive (r26's, unchanged): $r26_archive_sha" | tee "$evid/archive.txt"

echo "== [r26p] 2. title objects: r26's, with cheats.o and title_entry.o rebuilt"
obj=$work/objects-r26p
rm -rf "$obj"; cp -a "$work"/objects-r26/. "$obj"/
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
# cheats.o: port/randomizer/build-randomizer.sh's command (flags and includes), on cheats-r26.cpp
cxxflags=(-std=c++20 -fno-exceptions -fno-rtti -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
incs=(-I"$work/port/sdl3-shim/include" -I"$mesa" -I"$work/source/runtime" -I"$project/port/title" -I"$obj"
      -I"$project/port/randomizer" -I"$project/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include")
cc "${cxxflags[@]}" "${incs[@]}" -c "$root/cheats-r26.cpp" -o "$obj/cheats.o"
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
cc "${flags[@]}" -I"$root" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r26p-play"' \
    -c "$root/title_entry-r26p.c" -o "$obj/title_entry.o"
: > "$evid/objects-vs-r26.txt"
for o in "$obj"/*.o; do
    b=$(basename "$o")
    if [[ -f $work/objects-r26/$b ]]; then cmp -s "$o" "$work/objects-r26/$b" || echo "changed $b" >> "$evid/objects-vs-r26.txt"
    else echo "added $b" >> "$evid/objects-vs-r26.txt"; fi
done
for b in $(ls "$work/objects-r26"); do [[ -e $obj/$b ]] || echo "removed $b" >> "$evid/objects-vs-r26.txt"; done
cat "$evid/objects-vs-r26.txt"
[[ $(sort "$evid/objects-vs-r26.txt" | tr '\n' ' ') == "changed cheats.o changed title_entry.o " ]] || { echo "unexpected object changes" >&2; exit 2; }
"$sdk/bin/llvm-nm" --undefined-only "$obj/cheats.o" | awk '{print $NF}' | grep -E '^(renderer_present_count|za_performance_status|SDL_GetTicksNS|vkCmdClearAttachments)$' | sort | tr '\n' ' ' | tee "$evid/cheats-imports.txt"
echo

echo "== [r26p] 3. link: r26's recipe (its runtime objects as built; the r26 archive)"
cd "$work/source"
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
wraps="--wrap=SDL_SavePNG --wrap=radv_ps5_submit --wrap=radv_ps5_submit_times --wrap=za_title_frame_cfg --wrap=za_performance_status"
wraps+=" --wrap=sceAgcSuspendPoint --wrap=clock_gettime --wrap=za_prof_note_render --wrap=za_prof_thread_begin --wrap=za_prof_thread_end"
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) $wraps --start-group $(printf '%s ' "${libs[@]}") --end-group"
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r26p.mk <<MAKE
include offline-title.mk
.PHONY: local-title-r26p
local-title-r26p: \$(TITLE_OBJS)
	@mkdir -p \$(B)/title
	bash tools/ps5/link-title.sh \$(B)/title/llvm-pie.elf \$(TITLE_OBJS) $archive
MAKE
# the runtime objects are r26's (copied with the tree); make relinks only
make -s -f local-r26p.mk PLATFORM=ps5 -j"${JOBS:-12}" "PS5_DEPS_INC=$runtime_includes" local-title-r26p
pie=$work/source/build/ps5/title/llvm-pie.elf
: > "$evid/runtime-objects-vs-r26.txt"
while IFS= read -r -d '' o; do
    rel=${o#"$work/source/build/ps5/rt/"}
    cmp -s "$o" "$prev/source/build/ps5/rt/$rel" || echo "changed $rel" >> "$evid/runtime-objects-vs-r26.txt"
done < <(find "$work/source/build/ps5/rt" -name '*.o' -print0 | sort -z)
[[ ! -s $evid/runtime-objects-vs-r26.txt ]] || { echo "runtime objects differ from r26's:" >&2; cat "$evid/runtime-objects-vs-r26.txt" >&2; exit 2; }
echo "runtime objects: identical to r26's"

echo "== [r26p] 4. image checks"
python3 "$project/port/local-shader-r19/verify-registration.py" "$ref_pie" "$pie" > "$evid/registration.json"
nm=/usr/lib/llvm-21/bin/llvm-nm
objdump=/usr/lib/llvm-21/bin/llvm-objdump
"$nm" --dynamic --undefined-only "$ref_pie" | awk '{print $NF}' | sort > "$evid/imports-r26.txt"
"$nm" --dynamic --undefined-only "$pie" | awk '{print $NF}' | sort > "$evid/imports-r26p.txt"
diff "$evid/imports-r26.txt" "$evid/imports-r26p.txt" > "$evid/imports-diff.txt" || true
[[ ! -s $evid/imports-diff.txt ]] || { echo "new dynamic imports vs r26:" >&2; cat "$evid/imports-diff.txt" >&2; exit 2; }
"$nm" --defined-only --extern-only "$pie" | awk '{print $NF}' | sort | uniq -d > "$evid/duplicate-globals.txt" || true
[[ ! -s $evid/duplicate-globals.txt ]] || { echo "duplicate globals:" >&2; cat "$evid/duplicate-globals.txt" >&2; exit 2; }
"$objdump" -d --no-show-raw-insn --disassemble-symbols=menu_render,menu_handle_event,za_cheats_init,backend_present "$pie" > "$evid/r26p-callers.s" 2>/dev/null || true
awk '/^[0-9a-f]+ <[^>]+>:$/ {fn=$2} /call/ && /<(renderer_present_count|__wrap_za_performance_status|za_performance_status|SDL_GetTicksNS|vkCmdClearAttachments|menu_render|menu_is_open|za_cheats_init)>/ {print fn, $NF}' \
    "$evid/r26p-callers.s" | sort | uniq -c > "$evid/r26p-calls.txt"
cat "$evid/r26p-calls.txt"
check_call() { grep -q "<$1>: <$2>" "$evid/r26p-calls.txt" || { echo "missing call $1 -> $2" >&2; exit 2; }; }
check_call menu_render renderer_present_count; check_call menu_render SDL_GetTicksNS; check_call menu_render vkCmdClearAttachments
check_call menu_render __wrap_za_performance_status; check_call backend_present menu_render
! grep -q '<menu_render>: <za_performance_status>' "$evid/r26p-calls.txt" || { echo "menu_render bypasses the force60 wrap" >&2; exit 2; }
# the r26 timing hooks are still wired exactly as r26 verified them
"$objdump" -d --no-show-raw-insn --disassemble-symbols=f_7001b29660,f_7001b2a0e4,f_7001b5407c,f_70029f4214,f_7001015260,f_70010273f0,za_dt_frame_cfg "$pie" > "$evid/r26-hooks.s" 2>/dev/null || true
awk '/^[0-9a-f]+ <[^>]+>:$/ {fn=$2} /call/ && /<(za_dt_[a-z_]+|__wrap_za_title_frame_cfg)>/ {print fn, $NF}' "$evid/r26-hooks.s" | sort | uniq -c > "$evid/r26-hooks-calls.txt"
for pair in "f_7001b29660 za_dt_frame_cfg" "f_7001b29660 za_dt_present_mode" "f_7001b2a0e4 za_dt_step_ns" "f_7001b5407c za_dt_step_ns" \
            "f_70029f4214 za_dt_step_ns" "f_7001015260 za_dt_anim_table_ns" "f_70010273f0 za_dt_anim_table_ns" "za_dt_frame_cfg __wrap_za_title_frame_cfg"; do
    set -- $pair; grep -q "<$1>: <$2>" "$evid/r26-hooks-calls.txt" || { echo "r26 hook call missing: $1 -> $2" >&2; exit 2; }
done
echo "r26 hooks: wired as in r26"

echo "== [r26p] 5. package (the play configuration)"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
app=$dist/PPSA91762
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
        print(f'[r26p] {name}: {data!r} (as r23c, sha256 {pin["sha256"][:16]}...)')
PY
# the play configuration (coordinator's decision from the r25 hardware results, 2026-10-29):
printf '64\n' > "$app/slot-depth-options.txt"   # r23c's option: 64 with its 1 GiB headroom check, fallback 8 (r25 D64)
cat > "$app/perf-r24-options.txt" <<'OPTS'
# r26p-play options (read once at start; a missing file or key = r23c behaviour). See port/perf-r26/README-HE.md.
# PLAY configuration: 4K output rendered at 1080p (FSR1), cheap SDL ticks, the renderer's clock-heavy profile off,
# the r25 submitter thread, the live FPS counter on (L3+R3 > FPS COUNTER toggles it; the choice is saved per run).
# 60 FPS: L3+R3 > FPS TRIAL (r16's trial with its fallback to 30). force60 and dyn stay off: dyn until TEST-r26-HE.md.
scale=1
ticks=tsc
vkprof=0
submit=thread
fps=1
# clock=tsc        (r25: refused by its own cross-core check on 13.60 - affinity rc=34)
# radv_threaded=1  (r25: no gain)
# dyn=safe         (r26: not yet tested on the console)
# force60=1        (measurement only: slow motion below 60)
# gaps=1
# tsc=1
# dcache=tls
# prof=0
# mode=1920x1080
# sample=1
OPTS
cp "$pie" "$dist/llvm-pie-r26p.elf"
sha256sum "$app/eboot.bin" | tee "$evid/eboot.sha256.txt"
sha256sum "$dist/llvm-pie-r26p.elf" | tee "$evid/pie.sha256.txt"
"$PS5_VULKAN/build/host/ps5-native-tool" self --inspect --file "$app/eboot.bin" > "$evid/self-inspect.txt" 2>&1 || true
tail -3 "$evid/self-inspect.txt"
diff -rq "$project/artifacts/randomizer-r26-perf/PPSA91762" "$app" > "$evid/package-vs-r26.txt" || true
cat "$evid/package-vs-r26.txt"
[[ $(grep -c . "$evid/package-vs-r26.txt") == 3 ]] || { echo "the package should differ from r26's only in eboot.bin, perf-r24-options.txt and slot-depth-options.txt" >&2; exit 2; }
echo "r26p-play built: $app"

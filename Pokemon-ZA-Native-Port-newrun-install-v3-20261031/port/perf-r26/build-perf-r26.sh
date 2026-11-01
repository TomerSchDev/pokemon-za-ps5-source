#!/usr/bin/env bash
# r26-perf: r25-perf (port/perf-r25/build-perf-r25.sh, eboot 804205b7...b2d6) plus the dynamic frame timing
# (analysis/dynamic-timing-design-HE.md): hooks H1-H7 in five translated units of the game archive, the glue
# (port/perf-r26/za_dyn_glue_r26.c, a copy of port/dynamic-timing/za_dyn_glue.c with window accounting and a report)
# and the model (port/dynamic-timing/za_dyn_timing.c, unchanged) in the title, the dyn= keys in the title entry, and
# the window keys on exec.c's [za-r24-perf] line. Same recipe as r25 on the isolated copy
# /home/tomer/ps5-za-native/perf-r26-20261029 (rsync -a of perf-r25-20261029). No console, NAS or save access.
#
# Game archive: r25 links title-r1-20261027/cheats-r12/liblasgame-r12.a (= fps-r13's archive, whose main_660.o is r13's
# frame-mode hook to za_title_frame_cfg, plus the cheat hooks in main_145.o / main_209.o). r26's archive is a copy of
# it with exactly five members replaced: main_660.o (H1 frame mode, H2 present interval, H3 step), main_665.o (H4),
# main_1049.o (H5), main_467.o (H6), main_468.o (H7). H1 replaces r13's statement; with dyn=off it calls
# za_title_frame_cfg as r13's did. The units are compiled with build-hardware-r13.sh's command - shown below to
# reproduce the base archive's own members byte for byte.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/perf-r26-20261029
prev=/home/tomer/ps5-za-native/perf-r25-20261029
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
research=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025
base_archive=/home/tomer/ps5-za-native/title-r1-20261027/cheats-r12/liblasgame-r12.a
export TITLE_WORK=$work
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
ar=$sdk/bin/llvm-ar
obj=$work/objects-r26
dyn=$work/dyn-r26
dist=$project/artifacts/randomizer-r26-perf
evid=$project/evidence/perf-r26
ref_pie=$project/artifacts/randomizer-r25-perf/llvm-pie-r25.elf
ref_pie_sha=0f440a5b8f8d9a90e662bf74eede4c9da4a527927f6c2e42390789654372f59a
units=(main_660 main_665 main_1049 main_467 main_468)
[[ ! -e $dist ]] || { echo "refusing: $dist exists (use a new revision)" >&2; exit 2; }
[[ $(sha256sum "$ref_pie" | cut -d' ' -f1) == "$ref_pie_sha" ]] || { echo "r25's PIE does not match its record" >&2; exit 2; }
rm -rf "$obj"
mkdir -p "$obj" "$dyn" "$evid"
exec > >(tee "$evid/build.log") 2>&1
sha256sum "$base_archive" | tee "$evid/base-archive.sha256.txt"

echo "== [r26] 1. hook sites (build ID, 21 instruction words, the duration table, unit SHA-256, one occurrence each)"
python3 -I "$project/port/dynamic-timing/prepare-dynamic-hooks.py" "$research/aot/main" "$research/game/exefs/main" \
    --anim --out "$dyn" --syntax "$work/source/runtime" > "$evid/prepare-dynamic-hooks.json"
cp "$dyn/hook-manifest.json" "$evid/hook-manifest.json"

cc_unit() {  # build-hardware-r13.sh's command (the base archive's unit flags; -O1, no giant here)
    /usr/bin/clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default \
        -isysroot "$sdk" -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" \
        -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
        -O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label \
        -fvisibility=hidden -Iruntime -march=x86-64-v3 -DZA_PS5 \
        -c "$1" -o "$2"
}
cd "$work/source"
echo "== [r26] 2. the flags reproduce the base archive's members (unpatched units; main_660 as r13 patched it)"
ctl=$dyn/control; rm -rf "$ctl"; mkdir -p "$ctl/r13"
python3 "$project/port/title/prepare-fps-hook.py" "$research/aot/main/main_660.c" "$research/game/exefs/main" "$ctl/r13" > /dev/null
: > "$evid/flags-control.txt"
for u in "${units[@]}"; do
    if grep -qw "main/$u" build/ps5/gen/giants.mk; then echo "$u is a giant (-O0): refusing" >&2; exit 2; fi
    src=$research/aot/main/$u.c; [[ $u == main_660 ]] && src=$ctl/r13/main_660.c
    cc_unit "$src" "$ctl/$u.o"
    (cd "$ctl" && "$ar" p "$base_archive" "$u.o" > "$u.member.o")
    if cmp -s "$ctl/$u.o" "$ctl/$u.member.o"; then
        echo "$u: $( [[ $u == main_660 ]] && echo "r13's patched unit" || echo "unpatched unit") compiles byte-identical to the base archive's member" | tee -a "$evid/flags-control.txt"
    else
        echo "$u: control compile differs from the base archive's member - refusing" >&2; exit 2
    fi
done
rm -rf "$ctl"

echo "== [r26] 3. the patched units"
for u in "${units[@]}"; do
    cc_unit "$dyn/$u.c" "$dyn/$u.o"
    printf '%s.o %s ' "$u" "$(sha256sum "$dyn/$u.o" | cut -c1-16)"
    "$sdk/bin/llvm-nm" --undefined-only "$dyn/$u.o" | awk '{print $NF}' | grep -E '^(za_dt_|za_title_frame_cfg)' | tr '\n' ' '
    echo
done | tee "$evid/patched-units.txt"
nmu() { "$sdk/bin/llvm-nm" --undefined-only "$dyn/$1.o" | awk '{print $NF}'; }
[[ $(nmu main_660 | grep -cE '^(za_dt_frame_cfg|za_dt_present_mode|za_dt_step_ns)$') == 3 ]] || { echo "main_660.o hooks missing" >&2; exit 2; }
! nmu main_660 | grep -q '^za_title_frame_cfg$' || { echo "main_660.o still calls za_title_frame_cfg directly" >&2; exit 2; }
for u in main_665 main_1049; do nmu $u | grep -q '^za_dt_step_ns$' || { echo "$u.o: no za_dt_step_ns" >&2; exit 2; }; done
for u in main_467 main_468; do nmu $u | grep -q '^za_dt_anim_table_ns$' || { echo "$u.o: no za_dt_anim_table_ns" >&2; exit 2; }; done

echo "== [r26] 4. the game archive: the base with exactly these five members replaced"
archive=$dyn/liblasgame-r26.a
cp --reflink=auto "$base_archive" "$archive"
"$ar" rcs "$archive" $(printf "$dyn/%s.o " "${units[@]}")
"$ar" t "$base_archive" > "$dyn/members-base.txt"
"$ar" t "$archive" > "$dyn/members-r26.txt"
cmp -s "$dyn/members-base.txt" "$dyn/members-r26.txt" || { echo "member list changed" >&2; exit 2; }
ma=$dyn/members-a; mb=$dyn/members-b; rm -rf "$ma" "$mb"; mkdir -p "$ma" "$mb"
(cd "$ma" && "$ar" x "$base_archive") && (cd "$mb" && "$ar" x "$archive")
(cd "$ma" && sha256sum *.o | sort -k2) > "$dyn/members-base.sha256"
(cd "$mb" && sha256sum *.o | sort -k2) > "$dyn/members-r26.sha256"
diff "$dyn/members-base.sha256" "$dyn/members-r26.sha256" | grep '^>' | awk '{print $3}' | sort > "$evid/archive-members-changed.txt" || true
for u in "${units[@]}"; do cmp -s "$mb/$u.o" "$dyn/$u.o" || { echo "$u.o in the archive is not the patched object" >&2; exit 2; }; done
rm -rf "$ma" "$mb"
echo "members: $(wc -l < "$dyn/members-r26.txt"); changed vs base: $(tr '\n' ' ' < "$evid/archive-members-changed.txt")" | tee "$evid/archive.txt"
[[ $(tr '\n' ' ' < "$evid/archive-members-changed.txt") == "main_1049.o main_467.o main_468.o main_660.o main_665.o " ]] \
    || { echo "unexpected archive members changed" >&2; exit 2; }
sha256sum "$archive" | tee -a "$evid/archive.txt"

echo "== [r26] 5. title objects: r25's, with title_entry.o rebuilt and the timing model + glue added"
cp -a "$work"/objects-r25/. "$obj"/
cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
cc "${flags[@]}" -I"$root" -I"$work/port/sdl3-shim/include" -I"$work/source/runtime" -I"$project/port/title" \
    -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r26-perf"' \
    -c "$root/title_entry-r26.c" -o "$obj/title_entry.o"
cc "${flags[@]}" -I"$project/port/dynamic-timing" -Dllround=za_dt_llround -c "$project/port/dynamic-timing/za_dyn_timing.c" -o "$obj/za_dyn_timing.o"
cc "${flags[@]}" -I"$root" -c "$root/za_dyn_glue_r26.c" -o "$obj/za_dyn_glue_r26.o"
: > "$evid/objects-vs-r25.txt"
for o in "$obj"/*.o; do
    b=$(basename "$o")
    if [[ -f $work/objects-r25/$b ]]; then cmp -s "$o" "$work/objects-r25/$b" || echo "changed $b" >> "$evid/objects-vs-r25.txt"
    else echo "added $b" >> "$evid/objects-vs-r25.txt"; fi
done
for b in $(ls "$work/objects-r25"); do [[ -e $obj/$b ]] || echo "removed $b" >> "$evid/objects-vs-r25.txt"; done
cat "$evid/objects-vs-r25.txt"

echo "== [r26] 6. runtime: exec.c's [za-r24-perf] line gets the dyn_* keys; link"
python3 "$root/apply-runtime-r26.py" "$work"
libs=("$glsl/ps5-build/glslang/glslang/libglslang.a" "$glsl/ps5-build/glslang/glslang/libglslang-default-resource-limits.a" \
      "$glsl/ps5-build/glslang/SPIRV/libSPIRV.a")
wraps="--wrap=SDL_SavePNG --wrap=radv_ps5_submit --wrap=radv_ps5_submit_times --wrap=za_title_frame_cfg --wrap=za_performance_status"
wraps+=" --wrap=sceAgcSuspendPoint --wrap=clock_gettime --wrap=za_prof_note_render --wrap=za_prof_thread_begin --wrap=za_prof_thread_end"
export ZA_PS5_EXTRA_INPUTS="--gc-sections -z nostart-stop-gc $(printf '%s ' "$obj"/*.o) $wraps --start-group $(printf '%s ' "${libs[@]}") --end-group"
rm -rf build/ps5/rt  # (rebuilt: the edit is in a runtime source and nothing tracks header dependencies)
runtime_includes="-I$work/port/sdl3-shim/include -I$work/port/shaderc-cache/include -I$work/inc -I$project/port/observer-r17"
cat > local-r26.mk <<MAKE
include offline-title.mk
.PHONY: local-title-r26
local-title-r26: \$(TITLE_OBJS)
	@mkdir -p \$(B)/title
	bash tools/ps5/link-title.sh \$(B)/title/llvm-pie.elf \$(TITLE_OBJS) $archive
MAKE
make -s -f local-r26.mk PLATFORM=ps5 -j"${JOBS:-12}" "PS5_DEPS_INC=$runtime_includes" local-title-r26
pie=$work/source/build/ps5/title/llvm-pie.elf

echo "== [r26] 7. image checks"
python3 "$project/port/local-shader-r19/verify-registration.py" "$ref_pie" "$pie" > "$evid/registration.json"
nm=/usr/lib/llvm-21/bin/llvm-nm
objcopy=/usr/lib/llvm-21/bin/llvm-objcopy
objdump=/usr/lib/llvm-21/bin/llvm-objdump
"$nm" --dynamic --undefined-only "$ref_pie" | awk '{print $NF}' | sort > "$evid/imports-r25.txt"
"$nm" --dynamic --undefined-only "$pie" | awk '{print $NF}' | sort > "$evid/imports-r26.txt"
diff "$evid/imports-r25.txt" "$evid/imports-r26.txt" > "$evid/imports-diff.txt" || true
[[ ! -s $evid/imports-diff.txt ]] || { echo "new dynamic imports vs r25:" >&2; cat "$evid/imports-diff.txt" >&2; exit 2; }
"$nm" --defined-only --extern-only "$pie" | awk '{print $NF}' | sort | uniq -d > "$evid/duplicate-globals.txt" || true
"$nm" --defined-only "$pie" | grep -E ' (za_dt_[a-z_0-9]+|za_title_frame_cfg|__wrap_za_title_frame_cfg|__real_za_title_frame_cfg|za_dt_table_202|f_7001b29660|f_7001b2a0e4|f_7001b5407c|f_70029f4214|f_7001015260|f_70010273f0)$' \
    > "$evid/key-symbols.txt" || true
cat "$evid/key-symbols.txt"
"$objdump" -d --no-show-raw-insn \
    --disassemble-symbols=f_7001b29660,f_7001b2a0e4,f_7001b5407c,f_70029f4214,f_7001015260,f_70010273f0,za_dt_frame_cfg,za_r24_stats,renderer_stats \
    "$pie" > "$evid/r26-callers.s" 2>/dev/null || true
awk '/^[0-9a-f]+ <[^>]+>:$/ {fn=$2} /call/ && /<(za_dt_[a-z_]+|za_title_frame_cfg|__wrap_za_title_frame_cfg|__real_za_title_frame_cfg|plat_now_ns)>/ {print fn, $NF}' \
    "$evid/r26-callers.s" | sort | uniq -c > "$evid/r26-calls.txt"
cat "$evid/r26-calls.txt"
check_call() { grep -q "<$1>: <$2>" "$evid/r26-calls.txt" || { echo "missing call $1 -> $2" >&2; exit 2; }; }
check_call f_7001b29660 za_dt_frame_cfg; check_call f_7001b29660 za_dt_present_mode; check_call f_7001b2a0e4 za_dt_step_ns
check_call f_7001b5407c za_dt_step_ns; check_call f_70029f4214 za_dt_step_ns
check_call f_7001015260 za_dt_anim_table_ns; check_call f_70010273f0 za_dt_anim_table_ns
check_call za_dt_frame_cfg __wrap_za_title_frame_cfg
grep -qE '<(za_r24_stats|renderer_stats)>: <za_dt_report>' "$evid/r26-calls.txt" || { echo "the stats line does not call za_dt_report" >&2; exit 2; }
! grep -qE '^ *[0-9]+ <f_[0-9a-f]+>: <(__wrap_)?za_title_frame_cfg>' "$evid/r26-calls.txt" || { echo "game code still calls the r13 hook" >&2; exit 2; }
# runtime objects vs r25's, without debug info: only nvn/vulkan/exec.o is expected to change (and objects embedding the
# work copy's path in an assert string)
: > "$evid/runtime-objects-vs-r25.txt"
tmp=$(mktemp -d)
while IFS= read -r -d '' o; do
    rel=${o#"$work/source/build/ps5/rt/"}
    ref=$prev/source/build/ps5/rt/$rel
    if [[ ! -f $ref ]]; then echo "added $rel" >> "$evid/runtime-objects-vs-r25.txt"; continue; fi
    "$objcopy" --strip-debug "$o" "$tmp/a.o"; "$objcopy" --strip-debug "$ref" "$tmp/b.o"
    if cmp -s "$tmp/a.o" "$tmp/b.o"; then continue; fi
    if strings -a "$tmp/a.o" | sed 's/perf-r26-20261029/perf-r25-20261029/g' | cmp -s - <(strings -a "$tmp/b.o") &&
       ! grep -q "za_dt_report" <(strings -a "$tmp/a.o"); then
        echo "path-only $rel" >> "$evid/runtime-objects-vs-r25.txt"
    else
        echo "changed $rel" >> "$evid/runtime-objects-vs-r25.txt"
    fi
done < <(find "$work/source/build/ps5/rt" -name '*.o' -print0 | sort -z)
rm -rf "$tmp"
cat "$evid/runtime-objects-vs-r25.txt"
diff -u "$prev/source/runtime/nvn/vulkan/exec.c" "$work/source/runtime/nvn/vulkan/exec.c" > "$evid/exec.c.diff" || true

echo "== [r26] 8. package"
TITLE_ID=PPSA91762 TITLE_NAME='Pokémon Legends: Z-A Randomizer' TITLE_DIST="$dist" bash "$project/port/title/package-title.sh"
app=$dist/PPSA91762
# r23c's six option files, byte for byte from its installed package (Update.zip), each checked against the SHA-256
# its Packaging.json records (as r24-perf ... r25). performance-options.txt is r16's ("optimized\n").
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
        print(f'[r26] {name}: {data!r} (as r23c, sha256 {pin["sha256"][:16]}...)')
PY
# TEST-r26-HE.md's boot A: 4K output rendered at 1080p, cheap SDL ticks, the renderer's clock-heavy profile off, the
# GPU timeline, r25's submitter, and static 60 (force60) - the reference dyn=safe is compared with. dyn= and its test
# knobs stay commented out (= r25 behaviour). A test package: force60 is slow motion below 60 FPS; not for play.
cat > "$app/perf-r24-options.txt" <<'OPTS'
# r26 options (read once at start; a missing file or key = r23c behaviour). See port/perf-r26/README-HE.md.
# Test configuration, TEST-r26-HE.md boot A: static 60 (force60) - slow motion below 60 FPS; not for play.
# force60=1 overrides dyn=: for the dyn boots remove force60 and set dyn=safe.
scale=1
ticks=tsc
vkprof=0
gaps=1
submit=thread
force60=1
# dyn=safe
# dyn_stress_fps=45
# dyn_spike_ms=120
# dyn_spike_every=300
# dyn_anim=table
# dyn_log=2
# fnprof=600:900
# clock=tsc
# radv_threaded=1
# tsc=1
# dcache=tls
# prof=0
# mode=1920x1080
# sample=1
OPTS
cp "$pie" "$dist/llvm-pie-r26.elf"
sha256sum "$app/eboot.bin" | tee "$evid/eboot.sha256.txt"
sha256sum "$dist/llvm-pie-r26.elf" | tee "$evid/pie.sha256.txt"
"$PS5_VULKAN/build/host/ps5-native-tool" self --inspect --file "$app/eboot.bin" > "$evid/self-inspect.txt" 2>&1 || true
tail -3 "$evid/self-inspect.txt"
# the package differs from r25's only in eboot.bin and perf-r24-options.txt
diff -rq "$project/artifacts/randomizer-r25-perf/PPSA91762" "$app" > "$evid/package-vs-r25.txt" || true
cat "$evid/package-vs-r25.txt"
echo "r26-perf built: $app"

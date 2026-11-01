#!/usr/bin/env bash
# r29-music: the MUSIC row (new-run music shuffle) on top of an existing verified build. No console access.
#   build-r29-music.sh PLAN.json PLAN_SHA256 [BASE]
# BASE (default r28):
#   r28            r28-play work tree /home/tomer/ps5-za-native/r28-play-20261030 (pinned)
#   r27b           r27b-play work tree (pinned; make-based link, so that tree is copied first)
#   tree=DIR       any r28-style base work tree DIR (e.g. r28a-play), described by environment variables:
#                    R29_BASE_OUT          its build output dir (objects/, llvm-pie.elf, eboot.bin, evidence/)
#                    R29_BASE_ARCHIVE      its game archive (liblasgame-*.a)
#                    R29_BASE_REV          its ZA_TITLE_REV string (title_entry control), e.g. randomizer-r28a-play
#                    R29_BASE_EBOOT_SHA256 / R29_BASE_ARCHIVE_SHA256   pins
#                    optional: R29_BASE_OBJECTS, R29_BASE_PIE, R29_BASE_LINK_RECORD, R29_BASE_RUNTIME_RECORD,
#                              R29_BASE_CALLS (verifier call set: r28 = ITEMS + Hebrew trial, the default; or r27b),
#                              R29_BASE_TITLE_SRC (title entry source, default port/perf-r26/title_entry-r26p.c)
# Only five randomizer-side objects differ from the base: native_menu.o, run_store.o and title_entry.o are rebuilt
# from port/rando-music (+ revision label), za_music.o and za_music_plan.o are new. The game archive, runtime
# objects, cheats/Hebrew objects and every link option are the base build's own. Before anything is replaced the
# unchanged base sources must rebuild the base's own native_menu.o / title_entry.o byte-for-byte: if a base changed
# those (e.g. another fix edited the menu), the build stops instead of dropping that change. PLAN.json is
# game-derived (tools/make_music_plan.py output) and stays outside git; the generated za_music_plan.cpp stays in
# the work dir.
set -euo pipefail
export LC_ALL=C
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
plan=$(realpath -e -- "$1")
plan_sha=$2
base=${3:-r28}
pin() { [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]] || { echo "SHA-256 mismatch: $1" >&2; exit 2; }; }
title_src=$(realpath -e -- "${R29_BASE_TITLE_SRC:-$project/port/perf-r26/title_entry-r26p.c}")
calls=r28
label=$base
case $base in
tree=*)
    prev=$(realpath -e -- "${base#tree=}")
    prev_out=$(realpath -e -- "${R29_BASE_OUT:?R29_BASE_OUT: the base build output dir}")
    prev_objects=$(realpath -e -- "${R29_BASE_OBJECTS:-$prev_out/objects}")
    prev_pie=${R29_BASE_PIE:-$prev_out/llvm-pie.elf}
    archive=$(realpath -e -- "${R29_BASE_ARCHIVE:?R29_BASE_ARCHIVE: the base game archive}")
    base_rev=${R29_BASE_REV:?R29_BASE_REV: the base ZA_TITLE_REV string}
    pin "$prev_out/eboot.bin" "${R29_BASE_EBOOT_SHA256:?R29_BASE_EBOOT_SHA256}"
    pin "$archive" "${R29_BASE_ARCHIVE_SHA256:?R29_BASE_ARCHIVE_SHA256}"
    link_record=${R29_BASE_LINK_RECORD:-$prev_out/evidence/link-inputs.txt}
    runtime_record=${R29_BASE_RUNTIME_RECORD:-$prev_out/evidence/runtime-inputs.txt}
    [[ -f $link_record && -f $runtime_record && -f $prev_pie ]] || { echo 'base link/runtime records or PIE missing' >&2; exit 2; }
    [[ $prev_objects == "$prev"/* ]] || { echo 'R29_BASE_OBJECTS must be inside the base tree' >&2; exit 2; }
    calls=${R29_BASE_CALLS:-r28}
    label=$(basename "$prev")
    ;;
r28)
    prev=/home/tomer/ps5-za-native/r28-play-20261030
    prev_out=$prev/r28
    prev_objects=$prev_out/objects
    prev_pie=$prev_out/llvm-pie.elf
    archive=$prev_out/liblasgame-r28.a
    base_rev=randomizer-r28-play
    pin "$prev_out/eboot.bin" 65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568
    pin "$archive" a86c3134e7de8d14ce7a960b1000024d35dcc2eabac8b3529036936da494bb30
    link_record=$prev_out/evidence/link-inputs.txt
    runtime_record=$prev_out/evidence/runtime-inputs.txt
    ;;
r27b)
    prev=/home/tomer/ps5-za-native/r27b-play-20261029
    prev_out=$prev
    prev_objects=$prev/objects-r27
    prev_pie=$prev/source/build/ps5/title/llvm-pie.elf
    archive=$prev/money-r27/liblasgame-r27.a
    base_rev=randomizer-r27b-play
    pin "$prev_pie" 4e92c0ef09ba948deef36a4cf144a42532705763ef15d7e2a8ab2b41d4338d95
    pin "$archive" 0453e8b047b14bee5ce5024094750f9042eb95bd1475b736ca9ae4c95af46d83
    link_record=$project/evidence/perf-r27b/link-inputs.txt
    runtime_record=
    calls=r27b
    ;;
*) echo 'base must be r28, r27b or tree=DIR' >&2; exit 2 ;;
esac
work=$(realpath -m -- "${R29_WORK:-/home/tomer/ps5-za-native/r29-music-20261030-$label}")
[[ $work == /home/tomer/ps5-za-native/r29-music-* && ! -e $work ]] || { echo "R29_WORK must be a new r29-music-* folder: $work" >&2; exit 2; }
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
mesa=/home/tomer/ps5-za-native/PS5_Mesa/include
deps=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib
pin "$plan" "$plan_sha"

mkdir "$work"
# r28-style bases (runtime-inputs record): the base work tree is only READ (includes, runtime objects, link tools);
# every output goes to $work/r29. r27b: its make-based link writes into the tree, so that base is copied first.
if [[ -n $runtime_record ]]; then tree=$prev; else cp -a --reflink=auto "$prev/." "$work/"; tree=$work; fi
out=$work/r29
mkdir -p "$out/src" "$out/gen" "$out/objects" "$out/evidence" "$out/control"
exec > >(tee "$out/evidence/build.log") 2>&1
echo "r29-music on $base ($prev, tree $tree, out $prev_out, rev $base_rev, calls $calls), $(date -u +%FT%TZ)"
basepins=("$prev_pie" "$archive" "$prev_objects/native_menu.o" "$prev_objects/run_store.o" "$prev_objects/title_entry.o")
sha256sum "${basepins[@]}" > "$out/evidence/base-before.txt"
wobj=${prev_objects/#$prev/$tree}
cp -a "$wobj/." "$out/objects/"
cp "$root/"{za_music.cpp,za_music.hpp,za_music_plan.hpp,native_menu_music.cpp,run_store_music.cpp,build-r29-music.sh,verify-r29.py} "$out/src/"
cp "$root/tools/"{make_music_plan.py,za_bgm.py,embed_plan.py} "$out/src/"
cp "$title_src" "$out/src/"
sha256sum "$out/src/"* "$plan" > "$out/evidence/source-SHA256SUMS.txt"
python3 "$root/tools/embed_plan.py" "$plan" "$out/gen/za_music_plan.cpp" "$plan_sha"

cc() { sh "$PS5_VULKAN/tooling/prospero-clang18" "$@"; }
flags=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
cxx=(-std=c++20 -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 -DZA_RANDOMIZER_PS5=1 '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"')
incs=(-I"$project/port/rando-v2" -I"$project/port/cheats-r27" -I"$tree/port/sdl3-shim/include" -I"$mesa"
      -I"$tree/source/runtime" -I"$project/port/title" -I"$out/objects" -I"$project/port/randomizer"
      -I"$project/port/randomizer/core" -I"$deps/json/include" -I"$deps/mbedtls/include")
titleincs=(-I"$project/port/perf-r26" -I"$tree/port/sdl3-shim/include" -I"$tree/source/runtime" -I"$project/port/title")
cd "$tree/source"
echo '-- controls: the unchanged base sources must reproduce the base objects with these exact flags'
cc "${cxx[@]}" "${flags[@]}" "${incs[@]}" -c "$project/port/rando-v2/native_menu.cpp" -o "$out/control/native_menu.o"
cc "${cxx[@]}" "${flags[@]}" "${incs[@]}" -c "$project/port/randomizer/run_store.cpp" -o "$out/control/run_store.o"
cc -std=c11 "${flags[@]}" "${titleincs[@]}" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 "-DZA_TITLE_REV=\"$base_rev\"" \
    -c "$title_src" -o "$out/control/title_entry.o"
: > "$out/evidence/controls.txt"
for o in native_menu run_store title_entry; do
    if cmp -s "$out/control/$o.o" "$out/objects/$o.o"; then echo "$o.o: base control byte-identical" | tee -a "$out/evidence/controls.txt"
    else echo "$o.o: base control DIFFERS" | tee -a "$out/evidence/controls.txt"; [[ $o != run_store ]] && exit 2; fi
done
echo '-- r29-music objects'
musicincs=(-I"$root" "${incs[@]}")
cc "${cxx[@]}" "${flags[@]}" "${musicincs[@]}" -c "$root/native_menu_music.cpp" -o "$out/objects/native_menu.o"
cc "${cxx[@]}" "${flags[@]}" "${musicincs[@]}" -c "$root/run_store_music.cpp" -o "$out/objects/run_store.o"
cc "${cxx[@]}" "${flags[@]}" "${musicincs[@]}" -c "$root/za_music.cpp" -o "$out/objects/za_music.o"
cc "${cxx[@]}" "${flags[@]}" "${musicincs[@]}" -c "$out/gen/za_music_plan.cpp" -o "$out/objects/za_music_plan.o"
cc -std=c11 "${flags[@]}" "${titleincs[@]}" -DZA_NATIVE_CHEATS=1 -DZA_NATIVE_RANDOMIZER=1 '-DZA_TITLE_REV="randomizer-r29-music"' \
    -c "$title_src" -o "$out/objects/title_entry.o"
python3 "$root/verify-r29.py" objects "$wobj" "$out/objects" "$out/evidence/objects.json"

echo '-- link with the base build record (object folder swapped, two music objects added)'
extra=$(cat "$link_record")
[[ $extra == *"$prev_objects/"* ]] || { echo 'base link record lacks its object folder' >&2; exit 2; }
extra=${extra//"$prev_objects/"/"$out/objects/"}
export ZA_PS5_EXTRA_INPUTS="$extra $out/objects/za_music.o $out/objects/za_music_plan.o"
printf '%s\n' "$ZA_PS5_EXTRA_INPUTS" > "$out/evidence/link-inputs.txt"
if [[ -n $runtime_record ]]; then
    mapfile -t relinputs < "$runtime_record"
    runtime=(); for p in "${relinputs[@]}"; do [[ -f $p ]]; runtime+=("$tree/source/$p"); done
    cp "$runtime_record" "$out/evidence/runtime-inputs.txt"
    bash tools/ps5/link-title.sh "$out/llvm-pie.elf" "${runtime[@]}" "$archive"
else
    cat > local-r29.mk <<MAKE
include offline-title.mk
.PHONY: local-title-r29
local-title-r29:
	@mkdir -p $out
	bash tools/ps5/link-title.sh $out/llvm-pie.elf \$(TITLE_OBJS) $archive
MAKE
    make -s -f local-r29.mk PLATFORM=ps5 local-title-r29
fi
python3 "$project/port/local-shader-r19/verify-registration.py" "$prev_pie" "$out/llvm-pie.elf" > "$out/evidence/registration.json"
python3 "$root/verify-r29.py" image "$prev_pie" "$out/llvm-pie.elf" "$out/evidence" "$project" "$plan_sha" "$calls"
nm=/usr/lib/llvm-21/bin/llvm-nm
"$nm" --defined-only "$out/llvm-pie.elf" > "$out/evidence/defined-symbols.txt"
"$sdk/bin/llvm-strip" --strip-debug -o "$out/title-stripped.elf" "$out/llvm-pie.elf"
tool=$PS5_VULKAN/build/host/ps5-native-tool
stubs=$out/ps5-link/stubs
[[ -f $stubs/libSceAgc.so ]] || stubs=$tree/source/build/ps5/title/ps5-link/stubs
"$tool" link --in "$out/title-stripped.elf" --out "$out/eboot.elf" --stub-dir "$sdk/target/lib" \
    --stub "$stubs/libSceAgc.so" --stub "$stubs/libSceAgcDriver.so" \
    --module-sdk 0x02000009 --companion-sdk 0x08050001 --file-name eboot.elf
python3 "$project/port/title/verify-image.py" "$out/title-stripped.elf" "$out/eboot.elf" "$out/evidence/defined-symbols.txt" \
    > "$out/evidence/image-preservation.json"
"$tool" self --sign --in "$out/eboot.elf" --out "$out/eboot.bin" --magic 0x1D3D154F
"$tool" self --inspect --file "$out/eboot.bin" > "$out/evidence/self-inspection.txt"
sha256sum "${basepins[@]}" > "$out/evidence/base-after.txt"
cmp -s "$out/evidence/base-before.txt" "$out/evidence/base-after.txt" || { echo 'base build files changed' >&2; exit 2; }
sha256sum "$out/eboot.bin" "$out/llvm-pie.elf" > "$out/evidence/SHA256SUMS.txt"
cat "$out/evidence/SHA256SUMS.txt"
echo "r29-music candidate built and verified on $base; no console access performed"

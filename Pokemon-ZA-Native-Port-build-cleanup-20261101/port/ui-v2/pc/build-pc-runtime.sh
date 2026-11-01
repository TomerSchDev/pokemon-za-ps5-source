#!/usr/bin/env bash
# build-pc-runtime.sh - the Windows ZA Recomp runtime as lasrecomp-uiv2.exe WITHOUT the Dear ImGui UI, built with
# MSYS2 UCRT64 clang/lld from a COPY of the runtime source repo (the repo stays read-only; nothing is built inside it)
# with the upstream Makefile's Windows flags (pc-runtime.mk includes the Makefile). Run from Git Bash / MSYS2.
#
#   build-pc-runtime.sh objects                 sync the source copy, set up SDL3 3.4.18, compile every runtime object
#                                               (RT_OBJ + BACKEND_OBJ minus imgui_glue.o, incl. platform/windows_rc.o
#                                               via windres) and the cheat helper objects; writes
#                                               $ZA_WORK/src/build/pc-objects.txt (+ pc-helpers.txt)
#   build-pc-runtime.sh link ENTRY... [-- LDEXTRA...]
#                                               (objects first, incrementally) then link $OUT/lasrecomp-uiv2.exe and its
#                                               import library $OUT/lasrecomp.dll.a from those objects + ENTRY: your
#                                               entry / launcher / overlay modules as .o, .c (RTFLAGS) or .cpp/.cc
#                                               (CXXFLAGS) files; LDEXTRA after "--" goes to the link line as is.
#                                               The exe name is fixed: the import library records it, and the game DLL
#                                               (lasgame-uiv2.dll) is linked against that name.
#   build-pc-runtime.sh stub                    objects + link pc_entry_stub.c (the no-UI proof exe)
#   build-pc-runtime.sh all                     = stub
#   build-pc-runtime.sh print-flags             the flags make uses (RTFLAGS, CXXFLAGS, LDFLAGS, GENFLAGS)
#
# What ENTRY must define: see pc_entry_stub.c (the UI symbols + rt_version + za_items_pc_batch + za_money_pc_start).
# Always linked unless PC_HELPERS=0: port/cheats-r28/za_items.c, port/cheats-r27/za_money.cpp (the cheat helpers the
# relinked game DLL imports: za_items_pump, za_items_reset, za_cheat_money_component, za_money_lifecycle_reset) and
# pc_guest_calls.c (their calls into the game code).
#
# Environment (defaults in brackets):
#   ZA_PORT   this repo (Pokemon-ZA-Native-Port)        [derived from this script's location]
#   ZA_REPO   the runtime source repo, read-only          [<parent of ZA_PORT>/pokeza-recomp-ps5]
#   ZA_WORK   the work dir (copy, objects, deps)          [<parent of ZA_PORT>/ui-v2-work/pc]
#   OUT       the exe folder (exe, import lib, DLLs)      [$ZA_WORK/out]
#   GAMELIB_ID  id the exe accepts from the game DLL      [7b03da558e0b6144 = the reference PC lasgame.dll]
#   SDL3_DLL  the shipped SDL3.dll the import lib is made from   [<parent>/hebrew-lab/runtime/SDL3.dll]
#   DLL_DIR   the shipped runtime folder whose DLLs are copied next to the exe   [<parent>/hebrew-lab/runtime]
#   JOBS      make -j                                     [nproc]
#   PC_HELPERS=0  leave the cheat helpers out             [1]
#   ZA_TRACE=0    build the helpers without ZA_ITEMS_TRACE / ZA_MONEY_TRACE   [1: "[r28-items] ready" & co. in the log]
#   RT_MAIN_SYMBOL=<name>  compile runtime/main.c's main() under that name (your entry calls it)   [empty]
set -euo pipefail
export PATH="/c/msys64/ucrt64/bin:/c/msys64/usr/bin:$PATH"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZA_PORT="${ZA_PORT:-$(cd "$HERE/../../.." && pwd)}"
BASE="$(dirname "$ZA_PORT")"
ZA_REPO="${ZA_REPO:-$BASE/pokeza-recomp-ps5}"
ZA_WORK="${ZA_WORK:-$BASE/ui-v2-work/pc}"
OUT="${OUT:-$ZA_WORK/out}"
GAMELIB_ID="${GAMELIB_ID:-7b03da558e0b6144}"
SDL3_DLL="${SDL3_DLL:-$BASE/hebrew-lab/runtime/SDL3.dll}"
DLL_DIR="${DLL_DIR:-$BASE/hebrew-lab/runtime}"
JOBS="${JOBS:-$(nproc)}"
PC_HELPERS="${PC_HELPERS:-1}"
ZA_TRACE="${ZA_TRACE:-1}"
RT_MAIN_SYMBOL="${RT_MAIN_SYMBOL:-}"
SRC="$ZA_WORK/src"
DEPS="$ZA_WORK/deps"
LOGS="$ZA_WORK/logs"
EXE_NAME="lasrecomp-uiv2.exe"
# the official SDL3 3.4.18 mingw development package (headers): the shipped SDL3.dll is "SDL-release-3.4.18"
SDL3_DEVEL_URL="https://github.com/libsdl-org/SDL/releases/download/release-3.4.18/SDL3-devel-3.4.18-mingw.tar.gz"
SDL3_DEVEL_SHA256="049b9dd711e3fb3f8d84feb998dfec54a75e17cf539c4a80ff4d058d839771cf"
MAKEVARS=(PLATFORM=windows "GAMELIB_ID=$GAMELIB_ID" DEPS=../deps/sdl3 B=build "RT_MAIN_SYMBOL=$RT_MAIN_SYMBOL")

say() { printf '==> %s\n' "$*"; }
die() { printf 'build-pc-runtime: %s\n' "$*" >&2; exit 1; }
sha() { sha256sum "$1" | cut -c1-64; }
mkvar() { (cd "$SRC" && make -s -f pc-runtime.mk "${MAKEVARS[@]}" "pc-print-$1"); }

sync_source() {
    [ -f "$ZA_REPO/Makefile" ] || die "runtime source repo not found: $ZA_REPO"
    say "source: $ZA_REPO -> $SRC (copy; the repo is never built in)"
    mkdir -p "$SRC/third_party" "$SRC/docs" "$LOGS"
    cp -rpu "$ZA_REPO/runtime" "$SRC/"
    cp -rpu "$ZA_REPO/third_party/smaa" "$SRC/third_party/"
    mkdir -p "$SRC/third_party/imgui"   # headers only: runtime/nvn/texpatch.c includes imgui's stb_truetype copy; no ImGui is compiled
    cp -pu "$ZA_REPO"/third_party/imgui/imstb_*.h "$SRC/third_party/imgui/"
    cp -rpu "$ZA_REPO/tools" "$SRC/"
    cp -rpu "$ZA_REPO/docs/icon" "$SRC/docs/"
    cp -pu "$ZA_REPO/Makefile" "$SRC/Makefile"
    cp -p "$HERE/pc-runtime.mk" "$SRC/pc-runtime.mk"
    rm -rf "$SRC/tools/__pycache__"
    { echo "repo: $ZA_REPO"; git -C "$ZA_REPO" rev-parse HEAD 2>/dev/null || echo "(not a git checkout)";
      git -C "$ZA_REPO" status --porcelain -- runtime third_party/smaa tools Makefile docs/icon 2>/dev/null | sed 's/^/modified: /';
      echo "copied: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; } > "$SRC/SOURCE-REVISION.txt"
}

setup_sdl3() {
    local inc="$DEPS/sdl3/include/SDL3/SDL.h" lib="$DEPS/sdl3/lib/libSDL3.dll.a"
    mkdir -p "$DEPS/download" "$DEPS/sdl3/lib" "$DEPS/sdl3/lib-package"
    if [ ! -f "$inc" ]; then
        local tgz="$DEPS/download/SDL3-devel-3.4.18-mingw.tar.gz"
        if [ ! -f "$tgz" ]; then
            say "SDL3 headers: downloading $SDL3_DEVEL_URL"
            curl -sS -L -m 600 -o "$tgz" "$SDL3_DEVEL_URL"
        fi
        [ "$(sha "$tgz")" = "$SDL3_DEVEL_SHA256" ] || die "SDL3 devel package: sha256 mismatch ($tgz)"
        rm -rf "$DEPS/sdl3-devel-3.4.18" && mkdir -p "$DEPS/sdl3-devel-3.4.18"
        tar -xzf "$tgz" -C "$DEPS/sdl3-devel-3.4.18"
        cp -rp "$DEPS/sdl3-devel-3.4.18/SDL3-3.4.18/x86_64-w64-mingw32/include" "$DEPS/sdl3/"
        cp -p "$DEPS/sdl3-devel-3.4.18/SDL3-3.4.18/x86_64-w64-mingw32/lib/libSDL3.dll.a" "$DEPS/sdl3/lib-package/"
    fi
    grep -q "define SDL_MINOR_VERSION *4" "$DEPS/sdl3/include/SDL3/SDL_version.h" || die "SDL3 headers in $DEPS/sdl3 are not 3.4.x"
    if [ ! -f "$lib" ]; then
        [ -f "$SDL3_DLL" ] || die "shipped SDL3.dll not found: $SDL3_DLL"
        say "SDL3 import library: from the shipped $(basename "$SDL3_DLL") (export table -> SDL3.def -> dlltool)"
        # binutils (objdump, dlltool, nm) can't open paths with non-ASCII characters: cd and use relative names
        ( cd "$(dirname "$SDL3_DLL")" && { echo "LIBRARY SDL3.dll"; echo "EXPORTS";
            objdump -p "$(basename "$SDL3_DLL")" | awk '/\[Ordinal\/Name Pointer\] Table/{f=1;next} f&&/^\s*\[ *[0-9]+\] \+base/{print $NF}'; } ) > "$DEPS/sdl3/lib/SDL3.def"
        ( cd "$(dirname "$SDL3_DLL")" && { strings -n 8 "$(basename "$SDL3_DLL")" | grep -m1 -E '^SDL-release-' || true; sha256sum "$(basename "$SDL3_DLL")"; } ) > "$DEPS/sdl3/SDL3-dll-source.txt"
        [ "$(grep -c '^SDL_' "$DEPS/sdl3/lib/SDL3.def")" -gt 1000 ] || die "SDL3.def: too few exports read from $SDL3_DLL"
        ( cd "$DEPS/sdl3/lib" && dlltool -d SDL3.def -D SDL3.dll -l libSDL3.dll.a -m i386:x86-64 )
        ( cd "$DEPS/sdl3/lib" && nm libSDL3.dll.a | grep -q ' T SDL_SavePNG$' ) || die "libSDL3.dll.a lacks SDL_SavePNG"
    fi
    say "SDL3: headers $(grep -h 'define SDL_M[A-Z]*_VERSION' "$DEPS/sdl3/include/SDL3/SDL_version.h" | awk '{printf "%s.", $3}' | sed 's/\.$//'), import lib from $(head -1 "$DEPS/sdl3/SDL3-dll-source.txt")"
}

make_objects() {
    say "runtime objects: make -j$JOBS -f pc-runtime.mk ${MAKEVARS[*]} pc-objects  (log: $LOGS/make-objects.log)"
    local t0=$SECONDS
    ( cd "$SRC" && make -f pc-runtime.mk -j"$JOBS" "${MAKEVARS[@]}" pc-objects ) 2>&1 | tee "$LOGS/make-objects.log" | grep -vE '^(clang|windres|LC_ALL)' || true
    [ -f "$SRC/build/pc-objects.txt" ] || die "make pc-objects failed (see $LOGS/make-objects.log)"
    grep -qE '^make: \*\*\*|error:' "$LOGS/make-objects.log" && die "make pc-objects reported errors (see $LOGS/make-objects.log)"
    say "runtime objects: $(wc -l < "$SRC/build/pc-objects.txt") objects in $((SECONDS - t0)) s"
}

build_helpers() {
    mkdir -p "$SRC/build/helpers"
    : > "$SRC/build/pc-helpers.txt"
    [ "$PC_HELPERS" = 1 ] || { say "cheat helpers: left out (PC_HELPERS=0)"; return; }
    local gen rt trace_items="" trace_money=""
    gen="$(mkvar genflags | sed 's/ -fvisibility=hidden//')"  # the game DLL's flags (the hook units' ABI), exported from the exe
    rt="$(mkvar rtflags)"
    [ "$ZA_TRACE" = 1 ] && trace_items="-DZA_ITEMS_TRACE=1" && trace_money="-DZA_MONEY_TRACE=1"
    local hflags=($gen -DGUEST_VOLATILE -g "-I$ZA_PORT/port/cheats-r28" "-I$ZA_PORT/port/cheats-r27" "-DGAMELIB_ID=\"$GAMELIB_ID\"")
    say "cheat helpers: za_items.c za_money.cpp pc_guest_calls.c -> build/helpers (flags: ${hflags[*]} $trace_items)"
    ( cd "$SRC" &&
      clang "${hflags[@]}" $trace_items -c "$ZA_PORT/port/cheats-r28/za_items.c" -o build/helpers/za_items.o &&
      clang++ "${hflags[@]}" -std=c++20 -fno-exceptions -fno-rtti $trace_money -c "$ZA_PORT/port/cheats-r27/za_money.cpp" -o build/helpers/za_money.o &&
      clang $rt -c "$HERE/pc_guest_calls.c" -o build/helpers/pc_guest_calls.o ) 2>&1 | tee "$LOGS/helpers.log"
    printf '%s\n' build/helpers/za_items.o build/helpers/za_money.o build/helpers/pc_guest_calls.o > "$SRC/build/pc-helpers.txt"
    { echo "za_items.c   $(sha "$ZA_PORT/port/cheats-r28/za_items.c")"; echo "items.inc    $(sha "$ZA_PORT/port/cheats-r28/items.inc")";
      echo "za_money.cpp $(sha "$ZA_PORT/port/cheats-r27/za_money.cpp")"; echo "flags: ${hflags[*]} $trace_items / $trace_money"; } > "$SRC/build/pc-helpers-sources.txt"
}

objects() { sync_source; setup_sdl3; make_objects; build_helpers; }

link_exe() {
    [ $# -ge 1 ] || die "link: give at least one entry object / source (see pc_entry_stub.c)"
    [ -f "$SRC/build/pc-objects.txt" ] || objects
    local rt cxx ld version entries=() ldextra=() a stem
    rt="$(mkvar rtflags)"; cxx="$(mkvar cxxflags)"; ld="$(mkvar ldflags)"
    version="$(sed -n 's/^#define LARECOMP_VERSION "\(.*\)"/\1/p' "$SRC/runtime/ui/launcher.mm")"
    mkdir -p "$SRC/build/entry" "$OUT/link" "$LOGS"
    while [ $# -gt 0 ]; do
        a="$1"; shift
        [ "$a" = "--" ] && { ldextra=("$@"); break; }
        [ -f "$a" ] || die "link: no such file: $a"
        a="$(cd "$(dirname "$a")" && pwd)/$(basename "$a")"
        stem="$(basename "${a%.*}")"
        case "$a" in
            *.o|*.obj) entries+=("$a") ;;
            *.c)   say "entry: clang $stem.c (RTFLAGS)"; ( cd "$SRC" && clang $rt "-DPC_RT_VERSION=\"$version\"" -c "$a" -o "build/entry/$stem.o" ); entries+=("$SRC/build/entry/$stem.o") ;;
            *.cpp|*.cc|*.cxx) say "entry: clang++ $stem (CXXFLAGS)"; ( cd "$SRC" && clang++ $cxx "-DPC_RT_VERSION=\"$version\"" -c "$a" -o "build/entry/$stem.o" ); entries+=("$SRC/build/entry/$stem.o") ;;
            *) die "link: unknown input type: $a (.o / .c / .cpp)" ;;
        esac
    done
    local helpers=()
    [ -s "$SRC/build/pc-helpers.txt" ] && mapfile -t helpers < "$SRC/build/pc-helpers.txt"
    say "link: $EXE_NAME <- $(wc -l < "$SRC/build/pc-objects.txt") runtime objects + ${#helpers[@]} helpers + ${#entries[@]} entry objects"
    say "link flags: $ld ${ldextra[*]}"
    # linked under its final name in a folder of its own (the import library records the exe's name), then moved
    local t0=$SECONDS
    ( cd "$SRC" && clang++ -o "$OUT/link/$EXE_NAME" @build/pc-objects.txt "${helpers[@]}" "${entries[@]}" $ld "${ldextra[@]}" ) 2>&1 | tee "$LOGS/link.log"
    [ -f "$OUT/link/$EXE_NAME" ] || die "link failed (see $LOGS/link.log)"
    mv -f "$OUT/link/$EXE_NAME" "$OUT/$EXE_NAME"
    cp -p "$SRC/build/lasrecomp.dll.a" "$OUT/lasrecomp.dll.a"
    say "linked in $((SECONDS - t0)) s: $OUT/$EXE_NAME"
    # the DLLs the stock exe runs with, next to it (copied, never moved; the shipped lasrecomp.exe is not taken)
    cp -pu "$DLL_DIR"/*.dll "$OUT/"
    for f in Baloo2-SemiBold.ttf icon.png; do [ -f "$DLL_DIR/$f" ] && cp -pu "$DLL_DIR/$f" "$OUT/"; done
    verify_exe
}

verify_exe() {
    say "verify: imports of $EXE_NAME against the DLL folder and the shipped SDL3.dll's exports"
    local missing=0 d
    # (binutils + non-ASCII paths: run objdump from inside the folder)
    for d in $(cd "$OUT" && objdump -p "$EXE_NAME" | awk '/DLL Name:/{print $3}'); do
        case "$d" in
            KERNEL32.dll|USER32.dll|SHELL32.dll|WINMM.dll|ole32.dll|OLE32.dll|ADVAPI32.dll|GDI32.dll|COMDLG32.dll|SHLWAPI.dll|bcrypt.dll|ntdll.dll|api-ms-win-*|ucrtbase.dll|msvcrt.dll|dbghelp.dll|ws2_32.dll|WS2_32.dll|IMM32.dll|SETUPAPI.dll|VERSION.dll|OLEAUT32.dll|RPCRT4.dll) ;;
            *) [ -f "$OUT/$d" ] || { echo "   MISSING next to the exe: $d"; missing=1; } ;;
        esac
    done
    local sdl_missing nsdl
    grep '^SDL_' "$DEPS/sdl3/lib/SDL3.def" > "$LOGS/sdl3-exports.txt"
    # objdump's import rows: "<vma>  <none>  <hint>  <name>" under their "DLL Name:" line
    (cd "$OUT" && objdump -p "$EXE_NAME" | awk '/DLL Name: SDL3.dll/{f=1;next} /DLL Name:/{f=0} f&&NF>=3&&$1~/^[0-9a-f]+$/&&$NF~/^SDL_/{print $NF}' | sort -u) > "$LOGS/exe-sdl-imports.txt"
    nsdl="$(wc -l < "$LOGS/exe-sdl-imports.txt")"
    sdl_missing="$(grep -vxF -f "$LOGS/sdl3-exports.txt" "$LOGS/exe-sdl-imports.txt" || true)"
    [ "$nsdl" -gt 0 ] || { echo "   no SDL3 imports found in the exe?"; missing=1; }
    if [ -z "$sdl_missing" ]; then echo "   SDL3: all $nsdl imported SDL_ functions are exported by the shipped SDL3.dll (incl. $(grep -cE '^SDL_(SavePNG|LoadPNG)$' "$LOGS/exe-sdl-imports.txt") of SavePNG/LoadPNG)"
    else echo "   SDL functions imported but not exported by the shipped SDL3.dll:"; echo "$sdl_missing"; missing=1; fi
    local implib_name
    implib_name="$(cd "$OUT" && dlltool -I lasrecomp.dll.a 2>/dev/null || true)"
    echo "   import library lasrecomp.dll.a names: ${implib_name:-?} (expected $EXE_NAME)"
    [ "$implib_name" = "$EXE_NAME" ] || missing=1
    local nexp
    nexp="$(cd "$OUT" && objdump -p "$EXE_NAME" | awk '/\[Ordinal\/Name Pointer\] Table/{f=1;next} f&&/^\s*\[ *[0-9]+\]/{n++} END{print n+0}')"
    echo "   exports: $nexp symbols (--export-all-symbols); rt_dispatch/za_items_pump present: $(cd "$OUT" && objdump -p "$EXE_NAME" | grep -cE ' (rt_dispatch|za_items_pump)$')"
    {   echo "built: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; cat "$SRC/SOURCE-REVISION.txt"; echo "GAMELIB_ID: $GAMELIB_ID";
        echo "sdl3: $(head -1 "$DEPS/sdl3/SDL3-dll-source.txt")"; echo "exports: $nexp"; echo "import library name: $implib_name";
        echo "sha256:"; (cd "$OUT" && sha256sum "$EXE_NAME" lasrecomp.dll.a | sed 's/^/  /'); echo "ldflags: $(mkvar ldflags)";
        echo "helpers:"; sed 's/^/  /' "$SRC/build/pc-helpers.txt"; [ -f "$SRC/build/pc-helpers-sources.txt" ] && sed 's/^/  /' "$SRC/build/pc-helpers-sources.txt"; } > "$OUT/build-info-uiv2.txt"
    (cd "$OUT" && sha256sum "$EXE_NAME" lasrecomp.dll.a)
    [ "$missing" = 0 ] || die "verification failed (see above)"
}

case "${1:-}" in
    objects) objects ;;
    link) shift; link_exe "$@" ;;
    stub|all) objects; link_exe "$HERE/pc_entry_stub.c" ;;
    verify) [ -f "$OUT/$EXE_NAME" ] || die "no $OUT/$EXE_NAME"; verify_exe ;;
    stockname)
        # The STOCK game DLL (qa-game-reference's lasgame.dll, like the r28 pc-build-05 one) imports its runtime functions
        # from a module named "lasrecomp.exe" (its import library's name): a process whose exe is lasrecomp-uiv2.exe can't
        # load it (LoadLibrary error 126). For runs with the stock DLL: a byte-identical copy of the exe under that name
        # in a folder of its own, with the same DLLs. lasgame-uiv2.dll (relink-game-dll.sh) needs no such thing.
        [ -f "$OUT/$EXE_NAME" ] || die "no $OUT/$EXE_NAME"
        SN="${STOCKNAME_OUT:-$ZA_WORK/out-stockname}"; mkdir -p "$SN"
        cp -p "$OUT/$EXE_NAME" "$SN/lasrecomp.exe"; cp -pu "$DLL_DIR"/*.dll "$SN/"
        for f in Baloo2-SemiBold.ttf icon.png; do [ -f "$DLL_DIR/$f" ] && cp -pu "$DLL_DIR/$f" "$SN/"; done
        say "stock-name copy for the stock lasgame.dll: $SN/lasrecomp.exe ($(sha "$SN/lasrecomp.exe"))" ;;
    print-flags) [ -f "$SRC/pc-runtime.mk" ] || sync_source; for v in rtflags cxxflags ldflags genflags gamelib-id; do echo "$v: $(mkvar $v)"; done ;;
    *) sed -n '2,38p' "$0"; exit 2 ;;
esac
